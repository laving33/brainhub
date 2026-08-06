"""HTML helpers for BrainHub's local search page."""
from __future__ import annotations

import html
import re
import urllib.parse
from collections.abc import Callable, Mapping, Sequence

from .ui_classes import CARD, CARD_BODY
from .web_ingest import copy_button


PageHref = Callable[[str], str]
PageLayout = Callable[[str, str], str]


def highlight_search_term(text: str, term: str) -> str:
    """Wrap all occurrences of term in mark tags, escaping all other text."""
    if not term or not text:
        return html.escape(text)
    parts = re.split(f"({re.escape(term)})", text, flags=re.IGNORECASE)
    return "".join(
        f"<mark>{html.escape(part)}</mark>" if part.lower() == term.lower() else html.escape(part)
        for part in parts
    )


def render_search_page(
    query: str,
    results: Sequence[dict[str, object]],
    *,
    page_href: PageHref,
    layout: PageLayout,
    limit: int = 30,
    active_type: str = "",
) -> str:
    """Render the local search page for a bounded result set."""
    normalized = query.lower().strip()
    if not normalized:
        return layout(
            "搜尋",
            '<div class="breadcrumb"><a href="/">BrainHub</a> / 搜尋</div>'
            "<h1>搜尋</h1>"
            f"{render_search_refine_form(query)}"
            "<p>搜尋標題、別名、標籤、摘要與頁面內文。</p>",
        )

    filtered_results = filter_search_results(results, active_type=active_type)
    total = len(filtered_results)
    cap_note = f"，僅顯示前 {limit} 筆" if total > limit else ""
    graph_href = "/graph?q=" + urllib.parse.quote(query)
    brief_href = "/brief?q=" + urllib.parse.quote(query)
    type_counts = search_type_counts(results)
    summary = render_search_type_summary(
        query=query,
        total=total,
        visible=min(total, limit),
        type_counts=type_counts,
        active_type=active_type,
    )
    actions = (
        '<div class="page-actions">'
        f'<a class="button-link" href="{html.escape(graph_href, quote=True)}">開啟知識圖譜搜尋</a>'
        f'<a class="button-link" href="{html.escape(brief_href, quote=True)}">開啟記憶簡報</a>'
        f'{copy_button(f"跟 BrainHub 查詢 {query}", "複製查詢提示詞")}'
        "</div>"
    )
    if total == 0:
        ingest_prompt = "跟 BrainHub 匯入新的 raw 檔案"
        proposal_prompt = f"跟 BrainHub 草擬關於 {query} 的記憶提案（依 raw 來源）"
        filtered = f"{html.escape(active_type)} " if active_type else ""
        clear_filter = (
            f'<li><a href="{html.escape(search_href(query), quote=True)}">清除頁面類型篩選</a>。</li>'
            if active_type and results
            else ""
        )
        return layout(
            f"搜尋：{query}",
            f'<div class="breadcrumb"><a href="/">BrainHub</a> / 搜尋</div>'
            f'<h1>搜尋：{html.escape(query)}</h1>'
            f"{render_search_refine_form(query, active_type=active_type)}"
            f"<p>0 筆{filtered}搜尋結果</p>"
            f"{summary}"
            f"{actions}"
            '<div class="memory-next"><strong>目前沒有符合的頁面</strong>'
            "<ul>"
            f"{clear_filter}"
            '<li>針對這個主題，<a href="/ingest">新增來源資料</a>。</li>'
            f"<li>{copy_button(ingest_prompt, '複製匯入提示詞')}</li>"
            f"<li>{copy_button(proposal_prompt, '複製記憶提案提示詞')}</li>"
            "</ul></div>",
        )
    groups = render_search_result_groups(filtered_results[:limit], query=query, page_href=page_href)
    return layout(
        f"搜尋：{query}",
        f'<div class="breadcrumb"><a href="/">BrainHub</a> / 搜尋</div>'
        f'<h1>搜尋：{html.escape(query)}</h1>'
        f"{render_search_refine_form(query, active_type=active_type)}"
        f'<p>共 {total} 筆結果{cap_note}</p>'
        f"{summary}"
        f'{actions}'
        f'{groups}',
)


def render_search_refine_form(query: str, *, active_type: str = "") -> str:
    type_input = (
        f'<input type="hidden" name="type" value="{html.escape(active_type, quote=True)}">'
        if active_type else ""
    )
    return (
        '<form class="search-refine" action="/search" method="get">'
        f'<input type="search" name="q" value="{html.escape(query, quote=True)}" '
        'placeholder="搜尋標題、標籤與頁面內文" autocomplete="off" aria-label="搜尋 BrainHub">'
        f"{type_input}"
        '<button type="submit">搜尋</button>'
        "</form>"
    )


def filter_search_results(results: Sequence[dict[str, object]], *, active_type: str = "") -> list[dict[str, object]]:
    if not active_type:
        return list(results)
    return [
        result for result in results
        if str(result.get("type") or result.get("category") or "root").lower() == active_type
    ]


def search_type_counts(results: Sequence[Mapping[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        label = str(result.get("type") or result.get("category") or "root")
        counts[label] = counts.get(label, 0) + 1
    return counts


def render_search_type_summary(
    *,
    query: str,
    total: int,
    visible: int,
    type_counts: Mapping[str, int],
    active_type: str = "",
) -> str:
    if not type_counts:
        return ""
    all_count = sum(int(count) for count in type_counts.values())
    all_class = " active" if not active_type else ""
    all_chip = (
        f'<a class="catalog-chip{all_class}" href="{html.escape(search_href(query), quote=True)}">'
        f"<strong>全部</strong>{all_count}</a>"
    )
    chips = "".join(
        '<a class="catalog-chip{active}" href="{href}"><strong>{label}</strong>{count}</a>'.format(
            active=" active" if label == active_type else "",
            href=html.escape(search_href(query, page_type=label), quote=True),
            label=html.escape(label),
            count=count,
        )
        for label, count in sorted(
            ((str(label or "root"), int(count)) for label, count in type_counts.items()),
            key=lambda item: (-item[1], item[0]),
        )
    )
    subject = f"{html.escape(active_type)} " if active_type else ""
    return (
        f'<div class="catalog-summary search-summary {CARD}"><div class="{CARD_BODY}">'
        f"<p>顯示 {total} 筆{subject}結果中的 {visible} 筆，依頁面類型分組。</p>"
        f'<div class="catalog-chips">{all_chip}{chips}</div>'
        "</div></div>"
    )


def render_search_result_groups(
    results: Sequence[dict[str, object]],
    *,
    query: str,
    page_href: PageHref,
) -> str:
    grouped: dict[str, list[dict[str, object]]] = {}
    for result in results:
        label = str(result.get("type") or result.get("category") or "root")
        grouped.setdefault(label, []).append(result)
    sections = []
    for label, group_results in grouped.items():
        items = "".join(
            f'<li><a href="{html.escape(page_href(str(result["name"])), quote=True)}">'
            f'{highlight_search_term(str(result["title"]), query)}</a>'
            f'<br><small>...{highlight_search_term(str(result.get("snippet", "")), query)}...</small></li>'
            for result in group_results
        )
        sections.append(
            '<section class="page-group search-result-group">'
            f"<h2>{html.escape(label)} <span>{len(group_results)}</span></h2>"
            f'<ul class="page-list search-results">{items}</ul>'
            "</section>"
        )
    return '<div class="page-groups search-result-groups">' + "".join(sections) + "</div>"


def search_href(query: str, page_type: str = "") -> str:
    params = {"q": query}
    if page_type:
        params["type"] = page_type
    return "/search?" + urllib.parse.urlencode(params)
