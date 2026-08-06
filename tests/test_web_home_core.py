import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core.web_home import plural_type_label, render_home_page  # noqa: E402


def _layout(title: str, body: str) -> str:
    return f"<title>{title}</title>{body}"


def test_plural_type_label_handles_irregular_labels():
    assert plural_type_label("source") == "sources"
    assert plural_type_label("concept") == "concepts"
    assert plural_type_label("entity") == "entities"
    assert plural_type_label("memory") == "memories"


def test_render_home_page_shows_stats_sections_and_prompts():
    pages = [
        {"name": "index", "title": "Index", "type": "", "category": "root"},
        {
            "name": "agent-memory",
            "title": "Agent Memory",
            "type": "concept",
            "category": "concepts",
            "date_updated": "2026-05-01",
        },
        {
            "name": "local-memory",
            "title": "Local Memory",
            "type": "memory",
            "category": "memories",
            "date_updated": "2026-05-02",
        },
    ]
    prompts = {"prompts": [{"prompt": "is Link ready?"}, {"prompt": "ingest raw/<file> into Link"}]}

    html = render_home_page(
        pages,
        starter_prompts=prompts,
        page_href=lambda name: f"/page/{name}",
        layout=_layout,
    )

    assert "<title>BrainHub</title>" in html
    assert "agent 記憶是其中一層" in html
    assert '<span class="label">記憶</span>' in html
    assert '<h2>concepts</h2>' in html
    assert "/page/agent-memory" in html
    assert "試試這些提示詞" in html
    assert "is Link ready?" in html
    assert 'data-copy-text="is Link ready?"' in html
    assert "ingest raw/&lt;file&gt; into Link" in html
    assert 'data-copy-text="ingest raw/&lt;file&gt; into Link"' in html
    assert "下一步" in html
    assert "最近更新" in html
    assert html.index("Local Memory") < html.index("Agent Memory")
    assert "更新於 2026-05-02" in html
    assert 'href="/onboard"' in html
    assert 'href="/health"' in html
    assert 'href="/ingest"' in html
    assert 'href="/memory"' in html
    assert 'href="/graph"' in html
    assert "Index" not in html


def test_render_home_page_escapes_page_fields():
    pages = [
        {"name": "bad", "title": "<script>", "type": "<concept>", "category": "<concepts>"},
    ]

    html = render_home_page(pages, starter_prompts={"prompts": []}, page_href=lambda name: f"/page/{name}", layout=_layout)

    assert "&lt;concepts&gt;" in html
    assert "&lt;script&gt;" in html
    assert "&lt;concept&gt;" in html
    assert "<script>" not in html


def test_render_home_page_handles_empty_wiki():
    html = render_home_page([], starter_prompts={"prompts": []}, page_href=lambda name: f"/page/{name}", layout=_layout)

    assert "wiki 目前是空的" in html
    assert 'href="/ingest"' in html
    assert 'data-copy-text="把新的 raw 檔案匯入 BrainHub"' in html
    assert "複製匯入提示詞" in html


def test_render_home_page_hides_memory_card_when_memory_disabled():
    html = render_home_page(
        [],
        starter_prompts={"prompts": []},
        page_href=lambda name: f"/page/{name}",
        layout=_layout,
        memory_enabled=False,
    )

    assert 'href="/memory"' not in html
    # non-memory next-step cards survive
    assert 'href="/health"' in html
    assert 'href="/graph"' in html


def _pages(count, *, homes=()):
    pages = [
        {"name": f"page-{i}", "title": f"Page {i}", "type": "document",
         "category": "documents", "date_updated": "2026-07-20"}
        for i in range(count)
    ]
    pages += [
        {"name": name, "title": name, "type": "document",
         "category": "documents", "date_updated": "2026-07-21"}
        for name in homes
    ]
    return pages


def test_a_new_workspace_leads_with_the_tour():
    # Nothing to browse yet: the tour is the most useful thing on the page.
    html = render_home_page(_pages(2), starter_prompts={}, page_href=lambda n: f"/page/{n}",
                            layout=_layout)
    assert "1. 來源變成 wiki 知識" in html
    assert "<details" not in html


def test_a_populated_workspace_folds_the_tour_away():
    # 271 pages deep, three onboarding blocks were pushing "recent" below the
    # fold. The tour stays reachable, it just stops being the front door.
    html = render_home_page(_pages(40), starter_prompts={}, page_href=lambda n: f"/page/{n}",
                            layout=_layout)
    assert "<details" in html
    assert html.index("最近更新") < html.index("1. 來源變成 wiki 知識")


def test_home_pages_become_the_map_when_the_workspace_keeps_them():
    html = render_home_page(_pages(40, homes=("bd-home", "chief-home")),
                            starter_prompts={}, page_href=lambda n: f"/page/{n}", layout=_layout)
    assert "知識地圖" in html
    assert html.index("知識地圖") < html.index("最近更新")
    assert "bd-home" in html and "chief-home" in html


def test_no_home_pages_means_no_empty_section():
    # An install that does not use the convention gets nothing, not a heading
    # over an empty list.
    html = render_home_page(_pages(40), starter_prompts={}, page_href=lambda n: f"/page/{n}",
                            layout=_layout)
    assert "知識地圖" not in html


def test_iso_timestamps_are_shortened_to_a_date():
    from brainhub_core.text import short_date as _short_date
    assert _short_date("2026-07-21T19:14:10.232791+00:00") == "2026-07-21"
    assert _short_date("2026-07-21") == "2026-07-21"
    assert _short_date("") == ""
    assert _short_date("last tuesday") == "last tuesday"   # not ISO: passed through


def test_home_map_carries_each_page_summary():
    pages = _pages(40)
    pages.append({"name": "bd-home", "title": "bd home", "type": "document",
                  "category": "documents", "date_updated": "2026-07-21",
                  "tldr": "# bd home — Sales loop：獵新客"})
    html = render_home_page(pages, starter_prompts={}, page_href=lambda n: f"/page/{n}",
                            layout=_layout)
    # Without this the map is nine near-identical links and the reader has to
    # open each one to learn what it is.
    assert "Sales loop" in html
    assert "# bd home" not in html          # heading marker stripped


def test_summary_drops_markup_and_the_repeated_title():
    from brainhub_core.web_home import _summary_line
    # Stored TLDRs are first-line excerpts, so they arrive wearing that line's
    # markup and usually the page title again — rendering "bd home · bd home —…".
    assert _summary_line("# bd home — Sales loop：獵新客", "bd home") == "Sales loop：獵新客"
    assert _summary_line("> **TLDR:** 我的地圖", "cospec home") == "我的地圖"
    assert "*" not in _summary_line("定位 = **lab 驗閘員**", "x")
    assert _summary_line("", "x") == ""


def test_summary_stays_on_one_phone_line():
    from brainhub_core.web_home import _summary_line
    long = "邊" * 200
    out = _summary_line(long, "")
    assert len(out) <= 64 and out.endswith("…")


# ---------------------------------------------------------------------------
# Quantity gluing (display layer only — stored titles are never rewritten)
# ---------------------------------------------------------------------------

from brainhub_core.web_home import _glue_counted_units  # noqa: E402


def test_a_count_is_held_beside_its_measure_word():
    """「欠 3 天已還」 wrapped on a phone as 「欠 3」 / 「天已還」 — the number
    stranded from what it counts. Seen on live at 390px, not theorised."""
    assert _glue_counted_units("欠 3 天已還") == "欠 3&nbsp;天已還"
    assert _glue_counted_units("共 279 筆") == "共 279&nbsp;筆"
    assert _glue_counted_units("10 隻 AM") == "10&nbsp;隻 AM"


def test_prose_that_merely_follows_a_digit_is_left_alone():
    """The guard against a general "digit + any CJK" rule.

    Without the whitelist this would glue 「2026 年度計畫」 into an unbreakable
    run and quietly reshape every title on the page, which is a bigger fault
    than the wrap it set out to fix.
    """
    assert _glue_counted_units("2026 更新計畫") == "2026 更新計畫"
    assert _glue_counted_units("3 隻小豬的故事") == "3&nbsp;隻小豬的故事"
    assert _glue_counted_units("brainhub 定址層") == "brainhub 定址層"


def test_a_long_digit_run_is_not_glued_so_it_can_still_wrap():
    """An unbreakable token wider than a phone column overflows the viewport,
    and an overflow is a worse failure than an awkward wrap. Ids, ranges and
    figures are not counts, so they are left breakable."""
    assert _glue_counted_units("1234567890 筆") == "1234567890 筆"
    assert "&nbsp;" not in _glue_counted_units("20260721 日")
    # …while a real count still binds.
    assert _glue_counted_units("2026 年") == "2026&nbsp;年"


def test_gluing_runs_after_escaping_so_the_entity_survives():
    """Joined before escaping, the & becomes &amp; and readers see a literal
    "&nbsp;" printed in the title."""
    import html as _html

    assert "&amp;nbsp;" not in _glue_counted_units(_html.escape("A & B 3 天"))
    assert "3&nbsp;天" in _glue_counted_units(_html.escape("A & B 3 天"))
