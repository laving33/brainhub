"""HTML helpers for BrainHub's local home page."""
from __future__ import annotations

import html
import re
from collections.abc import Callable, Mapping, Sequence

from .text import short_date
from .web_ingest import copy_button


PageHref = Callable[[str], str]
PageLayout = Callable[[str, str], str]


def plural_type_label(page_type: str) -> str:
    irregular = {"entity": "entities", "memory": "memories"}
    if page_type in irregular:
        return irregular[page_type]
    return page_type if page_type.endswith("s") else page_type + "s"


def render_home_page(
    pages: Sequence[dict[str, object]],
    *,
    starter_prompts: Mapping[str, object],
    page_href: PageHref,
    layout: PageLayout,
    memory_enabled: bool = True,
) -> str:
    # A workspace with content and a workspace without it need opposite front
    # doors. Empty: the reader has nothing to look at and needs to learn what
    # this is — the product tour and starter prompts are the page. Populated:
    # they came to find something, and a tour they read weeks ago is pushing the
    # knowledge below the fold. Measured on the workspace this was written
    # against: 271 pages, and "recent" sat fourth behind three onboarding blocks.
    if len(pages) < ONBOARDING_PAGE_THRESHOLD:
        body = (
            "<h1>BrainHub</h1>"
            "<p>內部 LLM wiki + 富 artifact，agent 記憶是其中一層。知識在這裡持續累積。</p>"
            f"{_render_product_lanes()}"
            f"{_render_prompt_strip(starter_prompts)}"
            f"{_render_next_steps(memory_enabled=memory_enabled)}"
            f"{_render_recent_pages(pages, page_href=page_href)}"
            f"{_render_stats(pages)}"
            f"{_render_page_sections(pages, page_href=page_href)}"
        )
        return layout("BrainHub", body)

    body = (
        f"{_render_home_pages(pages, page_href=page_href)}"
        f"{_render_recent_pages(pages, page_href=page_href)}"
        f"{_render_stats(pages)}"
        f"{_render_page_sections(pages, page_href=page_href)}"
        f"{_render_onboarding_details(starter_prompts, memory_enabled=memory_enabled)}"
    )
    return layout("BrainHub", body)


# Below this many pages a workspace is still being set up, and the tour is the
# most useful thing on the page.
ONBOARDING_PAGE_THRESHOLD = 12


def _render_home_pages(pages: Sequence[dict[str, object]], *, page_href: PageHref) -> str:
    """The per-author index pages, when a workspace keeps them.

    Derived from the naming convention rather than a configured list, so an
    install that does not use home pages simply gets nothing here instead of an
    empty section or someone else's worker names.
    """
    homes = sorted(
        (page for page in pages if str(page.get("name") or "").lower().endswith("-home")),
        key=lambda page: str(page.get("name") or ""),
    )
    if not homes:
        return ""
    # Nine links reading "bd home", "catalog home", "chief home" are a list, not
    # a map — the reader still has to open each one to find out what is behind
    # it. The page's own summary is what makes it navigable at a glance.
    items = "".join(
        f'<li><a href="{html.escape(page_href(str(page.get("name") or "")), quote=True)}">'
        f'{_glue_counted_units(html.escape(str(page.get("title") or page.get("name") or "")))}</a>'
        + (f'<span class="type">{html.escape(_summary_line(page.get("tldr"), str(page.get("title") or "")))}</span>'
           if _summary_line(page.get("tldr"), str(page.get("title") or "")) else "")
        + "</li>"
        for page in homes
    )
    return (
        '<div class="section-heading"><h2>知識地圖</h2>'
        # nbsp: a count and its CJK counter must not split across a phone line
        # ("9" stranded at one line's end, "個入口" starting the next).
        f'<span class="muted">{len(homes)}&nbsp;個入口</span></div>'
        f'<ul class="page-list home-index">{items}</ul>'
    )


def _render_onboarding_details(starter_prompts: Mapping[str, object], *, memory_enabled: bool = True) -> str:
    """Keep the tour reachable on a populated workspace, but folded away."""
    return (
        "<details class=\"onboarding\"><summary>第一次用 BrainHub？看說明與提示詞</summary>"
        f"{_render_product_lanes()}"
        f"{_render_prompt_strip(starter_prompts)}"
        f"{_render_next_steps(memory_enabled=memory_enabled)}"
        "</details>"
    )


def _render_stats(pages: Sequence[dict[str, object]]) -> str:
    counts: dict[str, int] = {}
    for page in pages:
        page_type = str(page.get("type") or "other")
        counts[page_type] = counts.get(page_type, 0) + 1

    stats_items = f'<div class="stat-item"><span class="num">{len(pages)}</span><span class="label">頁面</span></div>'
    type_labels = {
        "memory": "記憶",
        "source": "來源",
        "concept": "概念",
        "entity": "實體",
        "comparison": "比較",
        "exploration": "探索",
    }
    for page_type in ["memory", "source", "concept", "entity", "comparison", "exploration"]:
        count = counts.get(page_type, 0)
        if count > 0:
            stats_items += (
                f'<div class="stat-item"><span class="num">{count}</span>'
                f'<span class="label">{type_labels.get(page_type, plural_type_label(page_type))}</span></div>'
            )
    return f'<div class="home-stats">{stats_items}</div>'


def _render_page_sections(pages: Sequence[dict[str, object]], *, page_href: PageHref) -> str:
    categories: dict[str, list[dict[str, object]]] = {}
    for page in pages:
        category = str(page.get("category") or "")
        if category == "root":
            continue
        categories.setdefault(category, []).append(page)

    if not categories:
        return (
            '<div class="memory-next"><strong>wiki 目前是空的</strong>'
            "<ul>"
            '<li><a href="/ingest">新增第一份 raw 來源</a>。</li>'
            f"<li>{copy_button('把新的 raw 檔案匯入 BrainHub', '複製匯入提示詞')}</li>"
            "</ul></div>"
        )

    sections = ""
    for category in sorted(categories):
        items = "".join(
            f'<li><a href="{html.escape(page_href(str(page["name"])), quote=True)}">'
            f'{_glue_counted_units(html.escape(str(page["title"])))}</a>'
            f'<span class="type">{html.escape(str(page.get("type") or ""))}</span></li>'
            for page in sorted(categories[category], key=lambda item: str(item.get("title") or ""))
        )
        sections += f'<h2>{html.escape(category)}</h2><ul class="page-list">{items}</ul>'
    return sections


def _summary_line(value: object, title: str = "", limit: int = 64) -> str:
    """A page's own TLDR, reduced to something readable beside its title.

    Stored TLDRs are excerpts of a page's first line, so they arrive wearing
    whatever markup that line had: a heading marker, a blockquote arrow, bold
    runs — and very often the page's own title again, which renders as
    "bd home · bd home — Sales loop：獵新客". Strip the markup, drop the
    repeated title, and keep it to one phone line.
    """
    text = str(value or "").strip()
    while text[:1] in {"#", ">"}:
        text = text[1:].strip()
    text = re.sub(r"\*{1,2}", "", text)
    text = re.sub(r"^TLDR:?\s*", "", text, flags=re.IGNORECASE).strip()
    title = str(title or "").strip()
    if title and text.lower().startswith(title.lower()):
        text = text[len(title):].lstrip(" —-–:：·|").strip()
    text = " ".join(text.split())
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# Measure words only — NOT "any CJK character after a digit". 「3 天」 is a
# quantity; 「2026 年度計畫」 happens to start with one and 「5 個人」 ends with
# one, so the list is what keeps this from gluing arbitrary prose. Extend it
# when a real title needs it; do not replace it with a general pattern.
_COUNTERS = (
    "天日週月年次回筆件份個隻頁則條家位人台間種名張篇章版層級輪期度"
    "元萬億秒分步組套支部本"
)
# A digit run this long is an id, a year range or a figure — not a count that
# needs its unit held beside it. Capping the run also caps how wide an
# unbreakable token can get, which is the thing that would overflow a phone.
_GLUE_MAX_DIGITS = 4
_COUNTED_UNIT_RE = re.compile(rf"(?<!\d)(\d{{1,{_GLUE_MAX_DIGITS}}}) ([{_COUNTERS}])")


def _glue_counted_units(escaped: str) -> str:
    """Bind a number to the ONE measure word after it, for display only.

    「海巡跑通（欠 3 天已還）」 wraps on a phone as 「…（欠 3」 / 「天已還）」 —
    the number is stranded from what it counts. The wiki page titles this fixes
    belong to other workers (and some are work logs, which are not ours to
    rewrite), so the join happens at render time and the stored text is never
    touched.

    Operates on already-escaped HTML because the joiner is an entity: escaping
    afterwards would emit a literal ``&amp;nbsp;``.
    """
    return _COUNTED_UNIT_RE.sub(r"\1&nbsp;\2", escaped)




def _render_recent_pages(pages: Sequence[dict[str, object]], *, page_href: PageHref, limit: int = 6) -> str:
    recent = [
        page for page in pages
        if str(page.get("category") or "") != "root" and str(page.get("date_updated") or "").strip()
    ]
    if not recent:
        return ""
    items = "".join(
        f'<li><a href="{html.escape(page_href(str(page["name"])), quote=True)}">'
        f'{_glue_counted_units(html.escape(str(page["title"])))}</a>'
        f'<span class="type">{html.escape(str(page.get("type") or ""))} · 更新於 {html.escape(short_date(page.get("date_updated")))}</span></li>'
        for page in sorted(recent, key=_recent_page_key, reverse=True)[:limit]
    )
    return (
        '<section class="home-recent">'
        '<div class="section-heading"><h2>最近更新</h2><a href="/all">所有頁面</a></div>'
        f'<ul class="page-list">{items}</ul>'
        "</section>"
    )


def _recent_page_key(page: Mapping[str, object]) -> tuple[str, str]:
    return str(page.get("date_updated") or ""), str(page.get("title") or "")


def _render_product_lanes() -> str:
    return (
        '<div class="product-lanes" aria-label="BrainHub 如何保存脈絡">'
        '<section class="product-lane"><h2>1. 來源變成 wiki 知識</h2>'
        '<p>把檔案放進 <code>raw/</code>，然後說 <code>把 raw/file.md 匯入 BrainHub</code>。'
        'BrainHub 會建立有來源依據的頁面、概念、反向連結、索引項目與紀錄。</p></section>'
        '<section class="product-lane"><h2>2. Remember 儲存 agent 記憶</h2>'
        '<p>當某個偏好、決策或專案事實應該影響之後的 agent 時，說 <code>remember that ...</code>。'
        '單純匯入不會悄悄影響之後的記憶回想。</p></section>'
        '<section class="product-lane"><h2>3. Query 安全地同時使用兩者</h2>'
        '<p>問 <code>query BrainHub for ...</code>，或開啟記憶簡報。BrainHub 會結合已審核的記憶、wiki 頁面與知識圖譜脈絡。</p></section>'
        '</div>'
    )


def _render_prompt_strip(starter_prompts: Mapping[str, object]) -> str:
    prompt_codes = ""
    for item in starter_prompts.get("prompts", []):
        if isinstance(item, dict):
            prompt = str(item.get("prompt") or "")
            prompt_codes += (
                '<div class="prompt-chip">'
                f"<code>{html.escape(prompt)}</code>"
                f"{copy_button(prompt, '複製')}"
                "</div>"
            )
    return (
        '<section class="prompt-strip" aria-label="BrainHub 入門提示詞">'
        '<h2>試試這些提示詞</h2>'
        '<p>可以請 Codex、Claude、Cursor、Kiro 或任何裝有 BrainHub 的 agent 試試看。<a href="/prompts">開啟入門提示詞</a>。</p>'
        '<div class="prompt-grid">'
        f"{prompt_codes}</div></section>"
    )


def _render_next_steps(memory_enabled: bool = True) -> str:
    actions = [
        ("上手引導", "/onboard", "健康度、第一則記憶、agent 連接，以及每日提示詞循環。"),
        ("檢查健康度", "/health", "就緒狀態、驗證、中斷的寫入，以及安全修復。"),
        ("新增來源", "/ingest", "先把 raw 筆記存到本機，再請 agent 匯入。"),
        ("檢視記憶", "/memory", "檢查已記住的偏好、決策與專案脈絡。"),
        ("探索知識圖譜", "/graph", "開啟關係、聚焦鄰近範圍與頁面佐證。"),
    ]
    if not memory_enabled:
        actions = [action for action in actions if action[1] != "/memory"]
    items = "".join(
        '<a class="home-next-card" href="'
        f'{html.escape(href, quote=True)}"><strong>{html.escape(label)}</strong>'
        f'<span>{html.escape(detail)}</span></a>'
        for label, href, detail in actions
    )
    return (
        '<section class="home-next" aria-label="下一步">'
        "<h2>下一步</h2>"
        f'<div class="home-next-grid">{items}</div>'
        "</section>"
    )
