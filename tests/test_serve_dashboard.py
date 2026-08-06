"""Status dashboard (/dashboard) — the load-bearing tests.

The feature exists because the previous board was a hand-authored artifact that
went five days stale while still printing a fresh-looking date. So the tests
that matter are the staleness ones, and they are written as a matched pair:
fresh data must produce NO warning and old data MUST produce one. Asserting
only the warning would pass just as happily on a banner that always warns.

Uses the same in-process handler harness as test_serve.py.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import serve
from test_serve import reset_wiki, run_handler_raw, write_page

from brainhub_core import web_dashboard
from brainhub_core.schema import write_schema


def _data(updated_at: str, **overrides) -> dict:
    payload = {
        "updated_at": updated_at,
        "title": "公司狀況 SPoG",
        "sections": [
            {
                "id": "P0",
                "title": "P0 · 掉下來就出事（時效）",
                "subtitle": "時效",
                "items": [
                    {"text": "WebPrism 吐明文 live API key", "owner": "平台",
                     "state": "blocked", "note": "owner 立即輪替那兩把 smoke key"},
                ],
            },
            {
                "id": "P3",
                "title": "P3 · 進展中 / 本週已收",
                "subtitle": "",
                "items": [
                    {"text": "tenant-guard bug 修好", "owner": "chief",
                     "state": "done", "note": "73/73 測試綠"},
                ],
            },
        ],
    }
    payload.update(overrides)
    return payload


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) - delta).isoformat()


class DashboardPageTests(unittest.TestCase):
    def make_workspace(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="dashboard-test-"))
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

    def get_dashboard(self) -> str:
        status, body, _ = run_handler_raw("GET", "/dashboard")
        self.assertEqual(status, 200)
        return body.decode("utf-8")

    # (1) The route renders real data: every section title, every item, the
    #     owner chips and the state labels all reach the page.
    def test_route_renders_sections_and_items(self):
        root = self.make_workspace()
        self.write_data(root, _data(_iso(timedelta(hours=2))))

        page = self.get_dashboard()
        self.assertIn("公司狀況 SPoG", page)
        self.assertIn("P0 · 掉下來就出事（時效）", page)
        self.assertIn("P3 · 進展中 / 本週已收", page)
        self.assertIn("WebPrism 吐明文 live API key", page)
        self.assertIn("owner 立即輪替那兩把 smoke key", page)
        self.assertIn("tenant-guard bug 修好", page)
        # state -> label, and the owner rides along as a chip.
        self.assertIn("卡住", page)
        self.assertIn("已收", page)
        self.assertIn("平台", page)
        # It came through the standard shell, not a bare fragment.
        self.assertIn("<!DOCTYPE html>", page)
        self.assertIn("BrainHub", page)
        # KPI tiles are derived from the data: one per section (+ decisions).
        self.assertIn("dash-kpi", page)

    # (2) A missing data file is an empty state with a next step, not a 500 and
    #     not a blank page — and the derived half still renders.
    def test_missing_data_file_renders_empty_state(self):
        root = self.make_workspace()
        self.assertFalse((root / serve.DASHBOARD_DIRNAME).exists())

        page = self.get_dashboard()
        self.assertIn("還沒有資料檔", page)
        self.assertIn("資料檔還不存在", page)
        # The reader is told exactly which file to create.
        self.assertIn(serve.DASHBOARD_FILENAME, page)
        # The section that cannot go stale is still on the page.
        self.assertIn("待決策（自動）", page)
        # No stamp at all is "unknown", and unknown warns rather than reassures.
        self.assertIn('data-stale="unknown"', page)
        self.assertNotIn('data-stale="no"', page)

    # (2b) A corrupt data file degrades the same way (and says why).
    def test_broken_json_renders_empty_state(self):
        root = self.make_workspace()
        path = root / serve.DASHBOARD_DIRNAME / serve.DASHBOARD_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")

        page = self.get_dashboard()
        self.assertIn("還沒有資料檔", page)
        self.assertIn("合法 JSON", page)

    # (3) THE PAIR. Fresh data => no warning. Five-day-old data => warning, with
    #     the age in days. Both directions asserted; either alone proves nothing.
    def test_staleness_banner_fresh_has_no_warning(self):
        root = self.make_workspace()
        self.write_data(root, _data(_iso(timedelta(hours=3))))

        page = self.get_dashboard()
        self.assertIn('data-stale="no"', page)          # verdict: fresh
        self.assertNotIn('data-stale="yes"', page)      # negative control
        # Assert on the banner's class ATTRIBUTE, not on the bare class name:
        # `.dash-stale--warn{...}` ships in the inlined stylesheet on every
        # page, so `assertNotIn("dash-stale--warn")` fails even when fresh.
        # A check can return a true value and still be answering another
        # question — this one was measuring the stylesheet, not the banner.
        # The daisyUI prefix rides in front of the `dash-*` names; matching the
        # whole attribute keeps that from mattering to what is being asked,
        # which is only ever "which of the two banners rendered?".
        self.assertNotIn(f'class="{web_dashboard.ALERT_WARNING} '
                         'dash-stale dash-stale--warn"', page)
        self.assertIn(f'class="{web_dashboard.ALERT} dash-stale dash-stale--fresh"', page)
        self.assertNotIn("可能已過期", page)
        self.assertIn("3 小時前", page)

    def test_staleness_banner_five_days_old_warns(self):
        root = self.make_workspace()
        self.write_data(root, _data(_iso(timedelta(days=5))))

        page = self.get_dashboard()
        self.assertIn('data-stale="yes"', page)         # verdict: stale
        self.assertNotIn('data-stale="no"', page)       # positive control
        self.assertIn(f'class="{web_dashboard.ALERT_WARNING} '
                      'dash-stale dash-stale--warn"', page)
        self.assertNotIn(
            f'class="{web_dashboard.ALERT} dash-stale dash-stale--fresh"', page)
        self.assertIn("可能已過期", page)
        self.assertIn("已 5 天沒更新", page)             # the age, in days
        self.assertIn("5 天前", page)

    # (3b) The 48h threshold itself: 47h is fresh, 49h is not. A banner that
    #      warns "eventually" is a banner nobody can reason about.
    def test_staleness_threshold_is_48_hours(self):
        now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
        fresh = web_dashboard.render_staleness_banner(
            (now - timedelta(hours=47)).isoformat(), now=now)
        stale = web_dashboard.render_staleness_banner(
            (now - timedelta(hours=49)).isoformat(), now=now)
        self.assertIn('data-stale="no"', fresh)
        self.assertIn('data-stale="yes"', stale)

    # (4) The decisions section is derived from decisions/, not from the data
    #     file — the half of the page that cannot go stale.
    def test_open_decision_batch_is_derived_from_disk(self):
        root = self.make_workspace()
        self.write_data(root, _data(_iso(timedelta(hours=1))))
        (root / "decisions" / "live-batch.json").write_text(json.dumps({
            "schema_version": 1,
            "batch_id": "live-batch",
            "title": "報價單要不要出",
            "created_by": "tam",
            "created_at": "2026-08-02T09:00:00Z",
            "status": "open",
            "items": [
                {"id": "item-01", "content_md": "# 決一下", "decision": None},
                {"id": "item-02", "content_md": "# 已決", "options": None,
                 "decision": {"action": "approve"}},
            ],
        }, ensure_ascii=False), encoding="utf-8")

        page = self.get_dashboard()
        self.assertIn("待決策（自動）", page)
        self.assertIn("報價單要不要出", page)
        self.assertIn("1 項待決 · 共 2 項", page)
        self.assertIn('href="/decide/live-batch"', page)

    # (4b) A closed batch is not news; the section says so rather than lying by
    #      omission.
    def test_closed_batches_are_not_listed(self):
        root = self.make_workspace()
        self.write_data(root, _data(_iso(timedelta(hours=1))))
        (root / "decisions" / "done-batch.json").write_text(json.dumps({
            "batch_id": "done-batch", "title": "已結案的板", "status": "decided",
            "items": [{"id": "i1", "decision": {"action": "approve"}}],
        }, ensure_ascii=False), encoding="utf-8")

        page = self.get_dashboard()
        self.assertNotIn("已結案的板", page)
        self.assertIn("（本區目前沒有項目）", page)

    # (5) Text from the data file is escaped, not injected. The dashboard reads
    #     a file other tools write; it is not a place to trust markup.
    def test_data_file_text_is_escaped(self):
        root = self.make_workspace()
        payload = _data(_iso(timedelta(hours=1)))
        payload["sections"][0]["items"][0]["text"] = "<script>alert(1)</script>"
        self.write_data(root, payload)

        page = self.get_dashboard()
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)


class DashboardComponentTests(unittest.TestCase):
    """The modules on their own — no server, no files."""

    # Brand tokens only. A hardcoded hex would silently opt the board out of
    # dark mode and any retheme, and would look completely fine in review.
    def test_css_uses_theme_tokens_and_no_literal_hex(self):
        import re
        self.assertIsNone(
            re.search(r"#[0-9a-fA-F]{3,8}\b", web_dashboard.DASHBOARD_CSS),
            "DASHBOARD_CSS must use CSS custom properties, not literal colours",
        )
        for token in ("--surface", "--border", "--muted", "--text",
                      "--caution", "--caution-fg", "--ok", "--accent"):
            self.assertIn(f"var({token})", web_dashboard.DASHBOARD_CSS)

    def test_kpi_tile_tone_maps_to_class_and_unknown_degrades(self):
        self.assertIn("dash-tone-caution", web_dashboard.render_kpi_tile("P0", 3, "caution"))
        self.assertIn("dash-tone-ok", web_dashboard.render_kpi_tile("已收", 5, "ok"))
        # Unknown tone renders neutral rather than raising — a dashboard renders.
        self.assertIn("dash-tone-neutral", web_dashboard.render_kpi_tile("x", 1, "chartreuse"))

    def test_status_item_states_and_missing_fields(self):
        blocked = web_dashboard.render_status_item("卡住的事", "owner", "blocked", "note")
        self.assertIn("卡住", blocked)
        self.assertIn("dash-item--caution", blocked)
        self.assertIn("owner", blocked)
        # Only text supplied: still a valid row, no empty chips.
        bare = web_dashboard.render_status_item("只有標題")
        self.assertIn("只有標題", bare)
        self.assertNotIn("dash-chips", bare)
        # Nothing supplied at all: labelled, not blank.
        self.assertIn("（未命名項）", web_dashboard.render_status_item(""))

    def test_priority_section_renders_empty_as_information(self):
        empty = web_dashboard.render_priority_section("P0", "時效", [])
        self.assertIn("P0", empty)
        self.assertIn("（本區目前沒有項目）", empty)

    def test_parse_timestamp_accepts_z_and_offsets_and_rejects_junk(self):
        self.assertEqual(
            web_dashboard.parse_timestamp("2026-08-02T12:00:00Z"),
            datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            web_dashboard.parse_timestamp("2026-08-02T20:00:00+08:00"),
            datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc),
        )
        self.assertIsNone(web_dashboard.parse_timestamp("上週吧"))
        self.assertIsNone(web_dashboard.parse_timestamp(None))


if __name__ == "__main__":
    unittest.main()
