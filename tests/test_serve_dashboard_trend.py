"""Dashboard trend + honest-boundary tests — the load-bearing ones.

The feature exists because the board had no time dimension: it could say P1 is 4
and could not say whether 4 was better than last week. So the tests that matter
are written as MATCHED PAIRS, the same way the staleness tests are, because each
half alone proves nothing:

  * with history a trend renders  AND  without history the empty state renders
    (not a one-point line, which a reader would read as "flat");
  * a delta appears when there IS a baseline  AND  no delta appears at all when
    there is not (absence of history must read as absence, never as ±0).

A test asserting only the first of each pair would pass just as happily on a
renderer that always draws a chart and always prints ↑0.

Uses the same in-process handler harness as test_serve.py. The existing
test_serve_dashboard.py is untouched: the staleness banner is a separate
guarantee and its tests stay the ones that guard it.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import serve
from test_serve import reset_wiki, run_handler_raw, write_page

from brainhub_core import dashboard_history as dh
from brainhub_core import web_dashboard
from brainhub_core.schema import write_schema


def _data(updated_at: str, *, p0=1, p1=1, bounds=None) -> dict:
    payload = {
        "updated_at": updated_at,
        "title": "公司狀況 SPoG",
        "sections": [
            {"id": "P0", "title": "P0 · 掉下來就出事", "items": [
                {"text": f"P0 第 {i + 1} 條", "state": "blocked"} for i in range(p0)]},
            {"id": "P1", "title": "P1 · 近錢", "items": [
                {"text": f"P1 第 {i + 1} 條", "state": "blocked"} for i in range(p1)]},
            {"id": "P2", "title": "P2 · 議程", "items": []},
            {"id": "P3", "title": "P3 · 已收", "items": [{"text": "收了", "state": "done"}]},
        ],
    }
    if bounds is not None:
        payload["bounds"] = bounds
    return payload


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) - delta).isoformat()


def _row(updated_at: str, **counts) -> dict:
    """One history line, shaped the way build_snapshot shapes it."""
    pending = counts.pop("pending", 0)
    return {
        "updated_at": updated_at,
        "recorded_at": updated_at,
        "counts": {k: v for k, v in counts.items()},
        "kpis": {dh.PENDING_KEY: pending},
    }


class HistoryFileTests(unittest.TestCase):
    """The append-only log on its own — no server."""

    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="dash-history-")))
        self.path = dh.history_path(self.tmp)

    def test_build_snapshot_keeps_counts_and_drops_item_text(self):
        snapshot = dh.build_snapshot(_data("2026-08-01T00:00:00Z", p0=2, p1=3), pending=4)
        self.assertEqual(snapshot["counts"], {"P0": 2, "P1": 3, "P2": 0, "P3": 1})
        self.assertEqual(snapshot["kpis"], {dh.PENDING_KEY: 4})
        self.assertEqual(snapshot["updated_at"], "2026-08-01T00:00:00Z")
        # The whole point of a compact row: no prose rides along.
        self.assertNotIn("P0 第 1 條", json.dumps(snapshot, ensure_ascii=False))

    def test_append_and_read_roundtrip_is_one_object_per_line(self):
        dh.append_snapshot(self.path, _row("2026-08-01T00:00:00Z", P0=1))
        dh.append_snapshot(self.path, _row("2026-08-02T00:00:00Z", P0=2))
        lines = self.path.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertIsInstance(json.loads(line), dict)
        history = dh.read_history(self.path)
        self.assertEqual([dh.metric(r, "P0") for r in history], [1, 2])

    def test_corrupt_line_costs_one_point_not_the_file(self):
        dh.append_snapshot(self.path, _row("2026-08-01T00:00:00Z", P0=1))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write("{half written\n")
        dh.append_snapshot(self.path, _row("2026-08-03T00:00:00Z", P0=3))
        history = dh.read_history(self.path)
        self.assertEqual([dh.metric(r, "P0") for r in history], [1, 3])

    def test_record_is_idempotent_per_data_version(self):
        snapshot = dh.build_snapshot(_data("2026-08-01T00:00:00Z"), pending=1)
        dh.record_snapshot(self.path, snapshot)
        dh.record_snapshot(self.path, snapshot)
        dh.record_snapshot(self.path, snapshot)
        self.assertEqual(len(dh.read_history(self.path)), 1)
        # A new board version DOES append.
        later = dh.build_snapshot(_data("2026-08-02T00:00:00Z"), pending=1)
        dh.record_snapshot(self.path, later)
        self.assertEqual(len(dh.read_history(self.path)), 2)

    def test_stampless_board_records_at_most_one_point_per_day(self):
        day = datetime(2026, 8, 2, 9, 0, tzinfo=timezone.utc)
        first = dh.build_snapshot({"sections": []}, now=day)
        second = dh.build_snapshot({"sections": []}, now=day + timedelta(hours=6))
        dh.record_snapshot(self.path, first)
        dh.record_snapshot(self.path, second)
        self.assertEqual(len(dh.read_history(self.path)), 1)
        tomorrow = dh.build_snapshot({"sections": []}, now=day + timedelta(days=1))
        dh.record_snapshot(self.path, tomorrow)
        self.assertEqual(len(dh.read_history(self.path)), 2)

    def test_append_failure_is_survivable(self):
        # A directory where the file should be: the write cannot succeed.
        self.path.mkdir(parents=True)
        self.assertFalse(dh.append_snapshot(self.path, _row("2026-08-01T00:00:00Z", P0=1)))
        self.assertEqual(dh.read_history(self.path), [])


class TrendSeriesTests(unittest.TestCase):
    """The shaping step: which keys are allowed to become a line."""

    def test_series_and_labels_align(self):
        history = [
            _row("2026-07-28T00:00:00Z", P0=1, P1=4, P2=4, P3=5, pending=1),
            _row("2026-08-02T00:00:00Z", P0=0, P1=3, P2=4, P3=6, pending=2),
        ]
        series, labels, omitted = dh.trend_series(history)
        self.assertEqual(labels, ["07-28", "08-02"])
        self.assertEqual(omitted, [])
        self.assertEqual({s["name"] for s in series},
                         {"P0", "P1", "P2", "P3", dh.PENDING_KEY})
        for entry in series:
            self.assertEqual(len(entry["values"]), len(labels))

    def test_key_missing_from_any_point_is_omitted_not_zero_filled(self):
        # P2 exists only in the newer snapshot. Charting it as 0 for the older
        # point would draw a measurement nobody made.
        history = [
            _row("2026-07-28T00:00:00Z", P0=1, pending=1),
            _row("2026-08-02T00:00:00Z", P0=2, P2=3, pending=1),
        ]
        series, _, omitted = dh.trend_series(history, keys=("P0", "P2"))
        self.assertEqual([s["name"] for s in series], ["P0"])
        self.assertIn("P2", omitted)
        self.assertNotIn(0, [v for s in series for v in s["values"]][:1] or [None])

    def test_window_keeps_the_tail(self):
        history = [_row(f"2026-08-{d:02d}T00:00:00Z", P0=d) for d in range(1, 11)]
        _, labels, _ = dh.trend_series(history, keys=("P0",), window=3)
        self.assertEqual(labels, ["08-08", "08-09", "08-10"])


class DeltaComputationTests(unittest.TestCase):
    """The half of the pair that must produce NOTHING."""

    def test_delta_against_previous_snapshot(self):
        current = _row("2026-08-02T00:00:00Z", P0=1, P1=4, pending=2)
        history = [_row("2026-07-28T00:00:00Z", P0=3, P1=3, pending=2), current]
        baseline = dh.baseline_for(history, dh.snapshot_key(current))
        deltas = dh.compute_deltas(current, baseline)
        self.assertEqual(deltas["P0"], -2)
        self.assertEqual(deltas["P1"], 1)
        self.assertEqual(deltas[dh.PENDING_KEY], 0)   # measured "no change"

    def test_no_baseline_means_no_deltas_at_all(self):
        current = _row("2026-08-02T00:00:00Z", P0=1, P1=4, pending=2)
        # Only the current version is on file: there is nothing to compare to.
        baseline = dh.baseline_for([current], dh.snapshot_key(current))
        self.assertIsNone(baseline)
        self.assertEqual(dh.compute_deltas(current, baseline), {})

    def test_key_absent_from_baseline_gets_no_delta(self):
        current = _row("2026-08-02T00:00:00Z", P0=1, P9=7)
        baseline = _row("2026-07-28T00:00:00Z", P0=3)
        deltas = dh.compute_deltas(current, baseline)
        self.assertIn("P0", deltas)
        self.assertNotIn("P9", deltas)


class DeltaRenderTests(unittest.TestCase):
    def test_none_renders_nothing_and_zero_renders_flat(self):
        self.assertEqual(web_dashboard.render_delta(None), "")
        self.assertNotIn("data-delta", web_dashboard.render_kpi_tile("P1", 4))
        # 0 with a baseline behind it IS a measurement and does render.
        flat = web_dashboard.render_delta(0)
        self.assertIn('data-delta="0"', flat)
        self.assertIn("→0", flat)

    def test_direction_and_sign(self):
        up = web_dashboard.render_kpi_tile("P1", 4, "caution", 1)
        self.assertIn('data-delta="+1"', up)
        self.assertIn("↑1", up)
        down = web_dashboard.render_kpi_tile("P0", 1, "caution", -2)
        self.assertIn('data-delta="-2"', down)
        self.assertIn("↓2", down)

    def test_unusable_delta_degrades_to_nothing(self):
        self.assertEqual(web_dashboard.render_delta("上週吧"), "")


class TrendSectionRenderTests(unittest.TestCase):
    """THE PAIR, at component level."""

    def test_two_points_render_a_chart(self):
        html = web_dashboard.render_trend_section(
            [{"name": "P1", "values": [4, 3]}], ["07-28", "08-02"])
        self.assertIn('data-trend="ok"', html)
        self.assertIn("<svg", html)
        self.assertIn("<polyline", html)

    def test_no_history_renders_the_empty_state_not_a_line(self):
        html = web_dashboard.render_trend_section([], [])
        self.assertIn('data-trend="none"', html)
        self.assertIn("尚無歷史", html)
        self.assertNotIn("<polyline", html)          # negative control
        self.assertNotIn('data-trend="ok"', html)

    def test_one_point_refuses_to_draw(self):
        html = web_dashboard.render_trend_section(
            [{"name": "P1", "values": [4]}], ["08-02"])
        self.assertIn('data-trend="insufficient"', html)
        self.assertNotIn("<polyline", html)
        self.assertIn("兩個點", html)

    def test_points_but_no_drawable_series_says_so(self):
        html = web_dashboard.render_trend_section([], ["07-28", "08-02"])
        self.assertIn('data-trend="insufficient"', html)
        self.assertNotIn("<polyline", html)

    def test_legend_names_every_line_in_the_primitives_slot_order(self):
        # Two series ending on the SAME value put their endpoint labels on
        # identical coordinates, which is how P1/P2 lost their identity on the
        # first real render. The legend is the second channel.
        html = web_dashboard.render_trend_section(
            [{"name": "P1", "values": [3, 4]}, {"name": "P2", "values": [5, 4]}],
            ["07-28", "08-02"])
        self.assertIn("dash-trend-legend", html)
        self.assertIn('dash-trend-swatch-1"></i>P1', html)
        self.assertIn('dash-trend-swatch-2"></i>P2', html)
        # No legend where there is no chart.
        self.assertNotIn("dash-trend-legend", web_dashboard.render_trend_section([], []))

    def test_omitted_keys_are_named_on_the_page(self):
        html = web_dashboard.render_trend_section(
            [{"name": "P1", "values": [4, 3]}], ["07-28", "08-02"], omitted=["待決策"])
        self.assertIn("缺歷史資料、未畫：待決策", html)

    def test_chart_is_self_contained_no_js_no_cdn(self):
        html = web_dashboard.render_trend_section(
            [{"name": "P1", "values": [4, 3]}], ["07-28", "08-02"])
        self.assertIn("<style>", html)               # the SVG carries its theme
        self.assertNotIn("<script", html)
        # Nothing is FETCHED. A bare `assertNotIn("http://")` answers a different
        # question than the one being asked: SVG's own namespace declaration is
        # `xmlns="http://www.w3.org/2000/svg"`, a URL that is never resolved. So
        # assert on the things that would actually cause a request.
        self.assertNotIn("src=", html)
        self.assertNotIn("href=", html)
        self.assertNotIn("@import", html)
        self.assertNotIn("url(", html)
        self.assertNotIn("cdn.", html)
        for token in html.split("http")[1:]:
            self.assertTrue(token.startswith("://www.w3.org/2000/svg"),
                            f"unexpected URL in a self-contained chart: http{token[:60]}")

    def test_broken_chart_data_degrades_instead_of_500(self):
        # values/labels mismatch: report_chart raises, the board must still render.
        html = web_dashboard.render_trend_section(
            [{"name": "P1", "values": [4]}], ["07-28", "08-02"])
        self.assertIn('data-trend="insufficient"', html)
        self.assertNotIn("<polyline", html)


class BoundsSectionRenderTests(unittest.TestCase):
    def test_three_states_render_with_their_labels(self):
        html = web_dashboard.render_bounds_section([
            {"fact": "資料年齡", "state": "measured", "detail": "橫幅算的"},
            {"fact": "卡了幾天", "state": "unmeasured", "detail": "沒有進場時間"},
            {"fact": "DataForSEO", "state": "blocked", "detail": "待 owner 發 key"},
        ])
        for label in ("已量測", "未量測", "被擋"):
            self.assertIn(label, html)
        self.assertIn('data-bound-state="measured"', html)
        self.assertIn('data-bound-state="unmeasured"', html)
        self.assertIn('data-bound-state="blocked"', html)
        self.assertIn("待 owner 發 key", html)

    def test_unknown_state_degrades_to_unmeasured_never_to_measured(self):
        html = web_dashboard.render_bounds_section(
            [{"fact": "某件事", "state": "probably-fine"}])
        self.assertIn('data-bound-state="unmeasured"', html)
        self.assertNotIn('data-bound-state="measured"', html)

    def test_blocked_without_a_reason_is_called_out(self):
        html = web_dashboard.render_bounds_section([{"fact": "某件事", "state": "blocked"}])
        self.assertIn("未註明", html)

    def test_empty_section_still_renders_and_says_it_is_empty(self):
        html = web_dashboard.render_bounds_section([])
        self.assertIn("這塊板子的邊界", html)
        self.assertIn("不代表沒有盲區", html)

    def test_text_is_escaped(self):
        html = web_dashboard.render_bounds_section(
            [{"fact": "<script>alert(1)</script>", "state": "blocked", "detail": "<b>x</b>"}])
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<b>x</b>", html)

    def test_uses_the_shell_components_not_the_report_catalogs_css(self):
        html = web_dashboard.render_bounds_section([{"fact": "x", "state": "measured"}])
        self.assertIn(web_dashboard.CARD, html)
        self.assertIn(web_dashboard.CARD_BODY, html)
        self.assertIn(web_dashboard.ALERT, html)
        # The report catalog's markup is print media on a warm paper palette; the
        # STRUCTURE was borrowed, the CSS deliberately was not. Asserted on whole
        # class attributes, because its `bound-tag` is a substring of this
        # module's own `dash-bound-tag` — a bare substring check here would be
        # measuring the wrong thing and would fail on correct code.
        for borrowed in ('class="bounds"', 'class="vcol', 'class="ev-card"',
                         'class="chip chip--', 'class="bound-item"'):
            self.assertNotIn(borrowed, html)
        # And none of its paper tokens reached the stylesheet.
        for token in ("--terracotta", "--gold-brown", "--olive", "--terra-bg", "--ink-bg"):
            self.assertNotIn(token, web_dashboard.DASHBOARD_CSS)


class DashboardTrendRouteTests(unittest.TestCase):
    """End to end through /dashboard — both controls, on the real page."""

    def make_workspace(self) -> Path:
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="dashboard-trend-")))
        wiki = tmp / "wiki"
        wiki.mkdir()
        write_page(wiki, "index.md", "# Index\n")
        write_page(wiki, "log.md", "# Log\n")
        (wiki / "_backlinks.json").write_text("{}", encoding="utf-8")
        write_schema(wiki)
        reset_wiki(wiki)
        (tmp / "decisions").mkdir()
        return tmp

    def write_data(self, root: Path, payload: dict) -> Path:
        path = root / serve.DASHBOARD_DIRNAME / serve.DASHBOARD_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_history(self, root: Path, rows) -> Path:
        path = root / serve.DASHBOARD_DIRNAME / dh.HISTORY_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return path

    def get_dashboard(self) -> str:
        status, body, _ = run_handler_raw("GET", "/dashboard")
        self.assertEqual(status, 200)
        return body.decode("utf-8")

    # ── CONTROL A: history present -> a real trend, and real deltas ──────────
    def test_with_history_renders_trend_and_deltas(self):
        root = self.make_workspace()
        stamp = _iso(timedelta(hours=2))
        self.write_data(root, _data(stamp, p0=1, p1=4))
        self.write_history(root, [
            _row("2026-07-20T00:00:00Z", P0=3, P1=3, P2=0, P3=1, pending=0),
            _row("2026-07-24T00:00:00Z", P0=2, P1=3, P2=0, P3=1, pending=0),
        ])

        page = self.get_dashboard()
        self.assertIn('data-trend="ok"', page)
        self.assertIn("<polyline", page)
        # P1 went 3 -> 4 against the previous snapshot; P0 went 2 -> 1.
        self.assertIn('data-delta="+1"', page)
        self.assertIn('data-delta="-1"', page)
        self.assertIn("↑1", page)

    # ── CONTROL B: no history -> the empty state, and NO delta anywhere ──────
    def test_without_history_renders_empty_state_and_no_deltas(self):
        root = self.make_workspace()
        self.write_data(root, _data(_iso(timedelta(hours=2))))

        page = self.get_dashboard()
        # The first render seeds one point from the current board, which is a
        # point without a baseline: still not enough for a line.
        self.assertIn('data-trend="insufficient"', page)
        self.assertNotIn('data-trend="ok"', page)
        self.assertNotIn("<polyline", page)
        # THE one that matters: no fabricated ±0 anywhere on the page.
        self.assertNotIn("data-delta", page)
        self.assertNotIn("→0", page)

    def test_first_render_seeds_exactly_one_point_and_repeats_do_not_grow_it(self):
        root = self.make_workspace()
        self.write_data(root, _data(_iso(timedelta(hours=2))))
        path = root / serve.DASHBOARD_DIRNAME / dh.HISTORY_FILENAME
        self.assertFalse(path.exists())

        self.get_dashboard()
        self.assertTrue(path.is_file())
        self.assertEqual(len(dh.read_history(path)), 1)
        self.get_dashboard()
        self.get_dashboard()
        self.assertEqual(len(dh.read_history(path)), 1)

    def test_a_new_data_version_appends_a_point(self):
        root = self.make_workspace()
        self.write_data(root, _data("2026-08-01T00:00:00Z", p1=4))
        self.get_dashboard()
        self.write_data(root, _data("2026-08-02T00:00:00Z", p1=6))
        page = self.get_dashboard()

        path = root / serve.DASHBOARD_DIRNAME / dh.HISTORY_FILENAME
        history = dh.read_history(path)
        self.assertEqual(len(history), 2)
        self.assertEqual([dh.metric(r, "P1") for r in history], [4, 6])
        # Two points now exist, so the chart appears and the delta with it.
        self.assertIn('data-trend="ok"', page)
        self.assertIn('data-delta="+2"', page)

    def test_missing_data_file_writes_no_history(self):
        root = self.make_workspace()
        page = self.get_dashboard()
        path = root / serve.DASHBOARD_DIRNAME / dh.HISTORY_FILENAME
        # A board that failed to load must not log a row of zeros.
        self.assertFalse(path.exists())
        self.assertIn('data-trend="none"', page)
        self.assertNotIn("data-delta", page)

    def test_bounds_section_reaches_the_page_from_the_data_file(self):
        root = self.make_workspace()
        self.write_data(root, _data(_iso(timedelta(hours=2)), bounds=[
            {"fact": "DataForSEO 關鍵字資料", "state": "blocked",
             "detail": "缺 owner 發 credential"},
            {"fact": "交付物有沒有被讀到", "state": "unmeasured", "detail": "沒有收訊端欄位"},
        ]))

        page = self.get_dashboard()
        self.assertIn("這塊板子的邊界", page)
        self.assertIn("DataForSEO 關鍵字資料", page)
        self.assertIn("缺 owner 發 credential", page)
        self.assertIn('data-bound-state="blocked"', page)
        self.assertIn('data-bound-state="unmeasured"', page)

    def test_bounds_section_renders_even_when_the_data_file_has_none(self):
        root = self.make_workspace()
        self.write_data(root, _data(_iso(timedelta(hours=2))))
        page = self.get_dashboard()
        # Vanishing would read as "this board has no blind spots".
        self.assertIn("這塊板子的邊界", page)
        self.assertIn("不代表沒有盲區", page)

    def test_staleness_banner_still_works_alongside_the_new_sections(self):
        root = self.make_workspace()
        self.write_data(root, _data(_iso(timedelta(days=5))))
        page = self.get_dashboard()
        self.assertIn('data-stale="yes"', page)
        self.assertIn("已 5 天沒更新", page)


class TrendCssTests(unittest.TestCase):
    def test_new_css_uses_theme_tokens_and_no_literal_hex(self):
        import re
        css = web_dashboard.DASHBOARD_CSS
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b", css))
        for token in ("--series-1", "--series-8", "--viz-surface", "--border-strong"):
            self.assertIn(token, css)

    def test_chart_theme_bridge_has_no_self_referential_custom_property(self):
        # `--surface: var(--surface)` inside svg.viz would be a cycle and resolve
        # to nothing, i.e. an unpainted chart. The alias hop is what avoids it.
        css = web_dashboard.DASHBOARD_CSS
        for name in ("surface", "muted"):
            self.assertNotIn(f"--{name}:var(--{name})", css)


if __name__ == "__main__":
    unittest.main()
