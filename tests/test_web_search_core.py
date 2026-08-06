import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core.web_search import (  # noqa: E402
    filter_search_results,
    highlight_search_term,
    render_search_page,
    render_search_refine_form,
    render_search_result_groups,
    render_search_type_summary,
    search_type_counts,
)


def _layout(title: str, body: str) -> str:
    return f"<title>{title}</title>{body}"


def test_highlight_search_term_escapes_text_and_marks_matches():
    html = highlight_search_term("<Link> memory link", "link")

    assert "&lt;" in html
    assert "<mark>Link</mark>" in html
    assert "<mark>link</mark>" in html


def test_render_search_page_handles_empty_query():
    html = render_search_page("", [], page_href=lambda name: f"/page/{name}", layout=_layout)

    assert "<title>搜尋</title>" in html
    assert 'class="search-refine"' in html
    assert 'aria-label="搜尋 BrainHub"' in html
    assert "搜尋標題、別名、標籤、摘要與頁面內文。" in html


def test_render_search_page_caps_results_and_escapes_content():
    results = [
        {"name": f"page-{index}", "title": f"Link {index}", "snippet": "<agent memory>"}
        for index in range(3)
    ]

    html = render_search_page("link", results, page_href=lambda name: f"/page/{name}", layout=_layout, limit=2)

    assert "共 3 筆結果，僅顯示前 2 筆" in html
    assert '/graph?q=link' in html
    assert '/brief?q=link' in html
    assert 'data-copy-text="跟 BrainHub 查詢 link"' in html
    assert "複製查詢提示詞" in html
    assert "search-result-groups" in html
    assert '<a class="catalog-chip active" href="/search?q=link"><strong>全部</strong>3</a>' in html
    assert "/page/page-0" in html
    assert "/page/page-1" in html
    assert "/page/page-2" not in html
    assert "&lt;agent memory&gt;" in html
    assert "<mark>Link</mark>" in html
    assert 'value="link"' in html


def test_render_search_page_filters_by_type():
    results = [
        {"name": "agent-memory", "title": "Agent memory", "type": "concept", "snippet": "memory"},
        {"name": "release-notes", "title": "Release notes", "type": "source", "snippet": "memory"},
    ]

    html = render_search_page(
        "memory",
        results,
        page_href=lambda name: f"/page/{name}",
        layout=_layout,
        active_type="source",
    )

    assert "共 1 筆結果" in html
    assert '<a class="catalog-chip active" href="/search?q=memory&amp;type=source"><strong>source</strong>1</a>' in html
    assert 'name="type" value="source"' in html
    assert "Release notes" in html
    assert "Agent memory" not in html
    assert '<a href="/search?q=memory">Clear page-type filter</a>' not in html


def test_render_search_page_empty_type_filter_can_be_cleared():
    results = [
        {"name": "agent-memory", "title": "Agent memory", "type": "concept", "snippet": "memory"},
    ]

    html = render_search_page(
        "memory",
        results,
        page_href=lambda name: f"/page/{name}",
        layout=_layout,
        active_type="source",
    )

    assert "<p>0 筆source 搜尋結果</p>" in html
    assert '<a href="/search?q=memory">清除頁面類型篩選</a>' in html


def test_render_search_page_no_results_guides_recovery():
    html = render_search_page("meeting notes", [], page_href=lambda name: f"/page/{name}", layout=_layout)

    assert "<p>0 筆搜尋結果</p>" in html
    assert "目前沒有符合的頁面" in html
    assert 'href="/ingest"' in html
    assert 'data-copy-text="跟 BrainHub 匯入新的 raw 檔案"' in html
    assert 'data-copy-text="跟 BrainHub 草擬關於 meeting notes 的記憶提案（依 raw 來源）"' in html
    assert "複製匯入提示詞" in html
    assert "複製記憶提案提示詞" in html


def test_search_type_helpers_escape_and_group_results():
    results = [
        {"name": "safe", "title": "Link", "type": "<source>", "snippet": "one"},
        {"name": "concept", "title": "Memory", "type": "concept", "snippet": "two"},
    ]

    assert search_type_counts(results) == {"<source>": 1, "concept": 1}
    assert filter_search_results(results, active_type="concept") == [results[1]]
    summary = render_search_type_summary(
        query="<link>",
        total=2,
        visible=2,
        type_counts=search_type_counts(results),
    )
    groups = render_search_result_groups(results, query="link", page_href=lambda name: f"/page/{name}")

    assert "type=%3Csource%3E" in summary
    assert "&lt;source&gt;" in summary
    assert "<h2>&lt;source&gt; <span>1</span></h2>" in groups


def test_render_search_refine_form_escapes_query_and_filter():
    html = render_search_refine_form('agent "memory"', active_type='source"bad')

    assert 'value="agent &quot;memory&quot;"' in html
    assert 'name="type" value="source&quot;bad"' in html


def test_render_search_page_escapes_actions_and_result_hrefs():
    html = render_search_page(
        'agent "memory"',
        [{"name": 'bad"name', "title": "Agent", "snippet": "memory"}],
        page_href=lambda name: f'/page/{name}?x="bad"',
        layout=_layout,
    )

    assert '/graph?q=agent%20%22memory%22' in html
    assert 'data-copy-text="跟 BrainHub 查詢 agent &quot;memory&quot;"' in html
    assert '/page/bad&quot;name?x=&quot;bad&quot;' in html
