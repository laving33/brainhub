"""HTML helpers for BrainHub wiki page lists."""
from __future__ import annotations

import html
import re
import urllib.parse
from collections.abc import Callable, Mapping, Sequence

from .ui_classes import CARD, CARD_BODY, CARD_TITLE
from .web_ingest import copy_button
from .text import normalized_search_text, short_date


PageHref = Callable[[str], str]
PageLayout = Callable[[str, str], str]

_HEADING_RE = re.compile(r"<h([23])>(.*?)</h\1>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def render_wiki_page(
    title: str,
    *,
    category: str,
    meta: Mapping[str, object],
    body_html: str,
    layout: PageLayout,
    graph_href: str = "",
    proposal_href: str = "",
    proposal_prompt: str = "",
    query_prompt: str = "",
    related_pages: Sequence[Mapping[str, object]] = (),
) -> str:
    """Render a single wiki page shell around already-rendered Markdown."""
    crumb = '<div class="breadcrumb"><a href="/">BrainHub</a>'
    if category:
        crumb += f" / {html.escape(category)}"
    crumb += f" / {html.escape(title)}</div>"
    meta_line = render_page_meta_line(meta)
    action_links = []
    if graph_href:
        action_links.append(
            f'<a class="button-link" href="{html.escape(graph_href, quote=True)}">開啟本機知識圖譜</a>'
        )
    if proposal_href:
        action_links.append(
            f'<a class="button-link" href="{html.escape(proposal_href, quote=True)}">草擬記憶</a>'
        )
    if proposal_prompt:
        action_links.append(copy_button(proposal_prompt, "複製記憶提示詞"))
    if query_prompt:
        action_links.append(copy_button(query_prompt, "複製查詢提示詞"))
    page_actions = f'<div class="page-actions">{"".join(action_links)}</div>' if action_links else ""
    outline_html, body_html = render_page_outline(body_html)
    document_html = f'<article class="wiki-page-document">{body_html}</article>'
    if outline_html:
        document_html = f'<div class="wiki-page-shell">{outline_html}{document_html}</div>'
    related_html = render_related_pages(related_pages)
    return layout(title, crumb + meta_line + page_actions + document_html + related_html)


def render_related_pages(pages: Sequence[Mapping[str, object]]) -> str:
    """The inbound/forward links footer, as a card.

    Same three-class shape the dashboard's sections use (card > card-body >
    card-title) — deliberately, because "one system" is a thing a reader
    recognises across pages, not a thing each page decides for itself. It
    replaces a bare `border-top` rule; the card's own edge does that job now.
    """
    if not pages:
        return ""
    items = "".join(
        '<li><span class="relationship">{relationship}</span>'
        '<a href="{href}">{title}</a></li>'.format(
            relationship=html.escape(str(page.get("relationship") or "相關")),
            href=html.escape(str(page.get("href") or "#"), quote=True),
            title=html.escape(str(page.get("title") or page.get("name") or "未命名")),
        )
        for page in pages
    )
    return (
        f'<section class="related-pages {CARD}"><div class="{CARD_BODY}">'
        f'<h2 class="{CARD_TITLE}">相關頁面</h2><ul>{items}</ul>'
        "</div></section>"
    )


def render_page_outline(body_html: str) -> tuple[str, str]:
    """Add stable heading anchors and return a compact page outline."""
    headings: list[tuple[str, str, str]] = []
    used_slugs: set[str] = set()

    def replace_heading(match: re.Match[str]) -> str:
        level = match.group(1)
        inner_html = match.group(2)
        label = html.unescape(_TAG_RE.sub("", inner_html)).strip()
        if not label:
            return match.group(0)
        slug = _heading_slug(label, used_slugs)
        headings.append((level, label, slug))
        return f'<h{level} id="{html.escape(slug, quote=True)}">{inner_html}</h{level}>'

    updated_body = _HEADING_RE.sub(replace_heading, body_html)
    if len(headings) < 2:
        return "", updated_body

    links = "".join(
        '<a class="level-{level}" href="#{slug}">{label}</a>'.format(
            level=html.escape(level, quote=True),
            slug=html.escape(slug, quote=True),
            label=html.escape(label),
        )
        for level, label, slug in headings
    )
    # `card` and not `card`+`card-body`: the aside IS the list (it carries the
    # `display: grid` the links are laid out on), so an inner body element would
    # have to take that over for one nested child. The card contributes the
    # edge, radius and surface; the padding stays in the stylesheet, which
    # daisyUI's `.card` does not declare and therefore does not contest.
    return (
        f'<aside class="page-outline {CARD}" aria-label="頁面目錄">'
        f"<strong>目錄</strong>{links}</aside>",
        updated_body,
    )


def _heading_slug(label: str, used_slugs: set[str]) -> str:
    # [a-z0-9]+ made every Chinese heading anchor "#section-2", "#section-3"...
    # The TOC still worked, but no anchor was ever meaningful or linkable.
    base = normalized_search_text(label).replace(" ", "-") or "section"
    slug = base
    counter = 2
    while slug in used_slugs:
        slug = f"{base}-{counter}"
        counter += 1
    used_slugs.add(slug)
    return slug


def render_page_meta_line(meta: Mapping[str, object]) -> str:
    """Render compact page metadata shown under the breadcrumb."""
    parts: list[str] = []
    if meta.get("type"):
        parts.append(f'<span class="meta-badge">{html.escape(str(meta["type"]))}</span>')
    if meta.get("maturity"):
        parts.append(html.escape(str(meta["maturity"])))
    if meta.get("source_count"):
        parts.append(f'{html.escape(str(meta["source_count"]))} 個來源')
    if meta.get("date_updated"):
        parts.append(f'更新於 {html.escape(short_date(meta["date_updated"]))}')
    aliases = meta.get("aliases", [])
    if isinstance(aliases, list) and aliases:
        parts.append("別名：" + ", ".join(html.escape(str(alias)) for alias in aliases))
    elif isinstance(aliases, str) and aliases:
        parts.append(f"別名：{html.escape(aliases)}")
    return f'<div class="meta">{" · ".join(parts)}</div>' if parts else ""


def render_all_pages(
    pages: Sequence[dict[str, object]],
    *,
    total: int,
    limit: int,
    offset: int,
    page_href: PageHref,
    layout: PageLayout,
    error: str = "",
    type_counts: Mapping[str, int] | None = None,
    active_type: str = "",
) -> str:
    """Render the paginated all-pages view."""
    controls = render_page_controls(total=total, limit=limit, offset=offset, active_type=active_type)
    warning = f'<p class="error">{html.escape(error)}</p>' if error else ""
    summary = render_page_catalog_summary(
        total=total,
        visible=len(pages),
        type_counts=type_counts,
        active_type=active_type,
        limit=limit,
    )
    groups = render_page_groups(pages, page_href=page_href)
    heading = "所有頁面"
    if active_type:
        heading += f" / {active_type}"
    return layout(
        "所有頁面",
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 所有頁面</div>'
        f"<h1>{html.escape(heading)} ({total})</h1>{warning}{summary}{controls}{groups}{controls}",
    )


def render_page_catalog_summary(
    *,
    total: int,
    visible: int,
    type_counts: Mapping[str, int] | None = None,
    active_type: str = "",
    limit: int = 250,
) -> str:
    """Render a compact type summary for the all-pages catalog."""
    if not type_counts:
        return ""
    all_class = " active" if not active_type else ""
    all_chip = (
        f'<a class="catalog-chip{all_class}" href="{html.escape(_all_pages_href(limit=limit), quote=True)}">'
        f"<strong>全部</strong>{sum(int(count) for count in type_counts.values())}</a>"
    )
    chips = "".join(
        '<a class="catalog-chip{active}" href="{href}"><strong>{label}</strong>{count}</a>'.format(
            active=" active" if label == active_type else "",
            href=html.escape(_all_pages_href(limit=limit, page_type=label), quote=True),
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
        f'<div class="catalog-summary {CARD}"><div class="{CARD_BODY}">'
        f"<p>顯示 {total} 筆{subject}頁面中的 {visible} 筆，依頁面類型分組。</p>"
        f'<div class="catalog-chips">{all_chip}{chips}</div>'
        "</div></div>"
    )


def render_page_groups(pages: Sequence[dict[str, object]], *, page_href: PageHref) -> str:
    """Render visible pages grouped by page type."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for page in pages:
        label = str(page.get("type") or page.get("category") or "root")
        grouped.setdefault(label, []).append(page)
    if not grouped:
        return '<p class="empty-state">找不到頁面。</p>'

    sections = []
    for label, group_pages in grouped.items():
        items = "".join(
            f'<li><a href="{html.escape(page_href(str(page["name"])), quote=True)}">'
            f'{html.escape(str(page["title"]))}</a>'
            f'<span class="type">{html.escape(str(page.get("category") or ""))}</span></li>'
            for page in group_pages
        )
        sections.append(
            '<section class="page-group">'
            f"<h2>{html.escape(label)} <span>{len(group_pages)}</span></h2>"
            f"<ul class='page-list'>{items}</ul>"
            "</section>"
        )
    return '<div class="page-groups">' + "".join(sections) + "</div>"


def render_page_controls(*, total: int, limit: int, offset: int, active_type: str = "") -> str:
    """Render previous/next controls for a bounded page window."""
    if total <= limit and offset <= 0:
        return ""

    start = 0 if total == 0 else offset + 1
    end = min(offset + limit, total)
    next_offset = offset + limit
    prev_offset = max(0, offset - limit)
    prev_href = html.escape(_all_pages_href(limit=limit, offset=prev_offset, page_type=active_type), quote=True)
    next_href = html.escape(_all_pages_href(limit=limit, offset=next_offset, page_type=active_type), quote=True)
    prev_link = (
        f'<a class="button-link" href="{prev_href}">上一頁</a>'
        if offset > 0
        else '<span class="button-link disabled">上一頁</span>'
    )
    next_link = (
        f'<a class="button-link" href="{next_href}">下一頁</a>'
        if next_offset < total
        else '<span class="button-link disabled">下一頁</span>'
    )
    return f'<div class="pager"><span>顯示第 {start} 至 {end} 筆，共 {total} 筆</span>{prev_link}{next_link}</div>'


def _all_pages_href(*, limit: int, offset: int = 0, page_type: str = "") -> str:
    params: dict[str, str] = {"limit": str(limit)}
    if offset:
        params["offset"] = str(offset)
    if page_type:
        params["type"] = page_type
    return "/all?" + urllib.parse.urlencode(params)
