"""HTML helpers for BrainHub's artifact gallery and document list pages.

The viewer stores self-contained artifacts (charts, mermaid diagrams,
interactive HTML, exports) under ``<root>/artifacts/<kind>/*.html`` and
publishes wiki documents under ``<root>/wiki/documents/*.md``. These helpers
render read-only browse surfaces around the provenance catalog and the wiki
document pages; the artifact bytes themselves are served (sandboxed) by the
``/artifact/<subpath>`` route, and documents open through the existing
``/page/<name>`` wiki renderer.
"""
from __future__ import annotations

import html
from collections.abc import Callable, Mapping, Sequence

from .ui_classes import CARD, CARD_BODY

PageLayout = Callable[[str, str], str]
# (stored_path, sid) -> URL. The sid comes straight from the catalog record so
# the caller never has to search the catalog back for it.
ArtifactHref = Callable[[str, str], str]

# Ordered zh-TW labels for each logical artifact kind. Order controls the
# section order on the gallery page.
KIND_LABELS: tuple[tuple[str, str], ...] = (
    ("chart", "圖表"),
    ("html", "互動 HTML"),
    ("report", "報告"),
    ("export", "匯出"),
)


def _kind_label(kind: str) -> str:
    for key, label in KIND_LABELS:
        if key == kind:
            return label
    return kind or "其他"


def _artifact_title(record: Mapping[str, object]) -> str:
    """Prefer an explicit meta title, else a readable filename stem."""
    title = str(record.get("title") or "").strip()
    if title:
        return title
    stored = str(record.get("stored_path") or "")
    stem = stored.rsplit("/", 1)[-1]
    if stem.endswith(".html"):
        stem = stem[: -len(".html")]
    return stem or "未命名產出"


def _record_meta_line(record: Mapping[str, object]) -> str:
    parts: list[str] = []
    agent = str(record.get("agent") or record.get("generated_by") or "").strip()
    if agent:
        parts.append(f"產生者：{html.escape(agent)}")
    renderer = str(record.get("renderer") or "").strip()
    if renderer:
        parts.append(f"渲染器：{html.escape(renderer)}")
    task = str(record.get("task") or "").strip()
    if task:
        parts.append(f"任務：{html.escape(task)}")
    created = str(record.get("created_at") or "").strip()
    if created:
        parts.append(f"建立於 {html.escape(created)}")
    return " · ".join(parts)


def render_artifacts_page(
    catalog: Mapping[str, object],
    *,
    layout: PageLayout,
    artifact_href: ArtifactHref,
) -> str:
    """Render the artifact gallery grouped by kind.

    ``catalog`` is the read-only provenance payload from
    ``artifact_catalog`` (keys: ``count``, ``artifacts``). ``artifact_href``
    maps a stored path (``artifacts/<subdir>/<name>``) to an open URL.
    """
    records = [r for r in _dict_list(catalog.get("artifacts")) if r.get("stored_path")]
    total = len(records)

    grouped: dict[str, list[Mapping[str, object]]] = {}
    for record in records:
        grouped.setdefault(str(record.get("kind") or "其他"), []).append(record)

    intro = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 產出</div>'
        f"<h1>產出 ({total})</h1>"
        f'<div class="catalog-summary {CARD}"><div class="{CARD_BODY}">'
        "<p>由 bh_build 產生的自帶樣式 artifact（圖表、"
        "流程圖、互動 HTML、匯出檔）。每個 artifact 都在隔離的沙箱來源中開啟，"
        "其內建腳本可以繪圖但無法存取檢視器本身。</p></div></div>"
    )

    if not records:
        return layout(
            "產出",
            intro + '<p class="empty-state">目前還沒有任何產出。用 bh_build 產生圖表或互動 HTML 後就會出現在這裡。</p>',
        )

    sections: list[str] = []
    ordered_kinds = [key for key, _ in KIND_LABELS if key in grouped]
    ordered_kinds += [k for k in grouped if k not in ordered_kinds]
    for kind in ordered_kinds:
        group = grouped[kind]
        rows = "".join(
            "<li>"
            f'<a href="{html.escape(artifact_href(str(record["stored_path"]), str(record.get("sid", ""))), quote=True)}" '
            'target="_blank" rel="noopener">'
            f'{html.escape(_artifact_title(record))}</a>'
            f'<span class="type">{_record_meta_line(record)}</span>'
            "</li>"
            for record in group
        )
        sections.append(
            '<section class="page-group">'
            f'<h2>{html.escape(_kind_label(kind))} <span>{len(group)}</span></h2>'
            f'<ul class="page-list">{rows}</ul>'
            "</section>"
        )
    body = intro + '<div class="page-groups">' + "".join(sections) + "</div>"
    return layout("產出", body)


def render_documents_page(
    documents: Sequence[Mapping[str, object]],
    *,
    layout: PageLayout,
) -> str:
    """Render the published-document list; each opens via the wiki renderer."""
    total = len(documents)
    intro = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 文件</div>'
        f"<h1>文件 ({total})</h1>"
        f'<div class="catalog-summary {CARD}"><div class="{CARD_BODY}">'
        "<p>由 bh_publish 發佈的 wiki 文件與報告，"
        "點擊即以本機 wiki 檢視器開啟。</p></div></div>"
    )
    if not documents:
        return layout(
            "文件",
            intro + '<p class="empty-state">目前還沒有發佈任何文件。用 bh_publish 發佈報告或文件後就會出現在這裡。</p>',
        )

    rows = ""
    for doc in documents:
        title = str(doc.get("title") or doc.get("name") or "未命名文件")
        href = str(doc.get("href") or "#")
        meta_parts: list[str] = []
        date = str(doc.get("date") or "").strip()
        if date:
            meta_parts.append(f"更新於 {html.escape(date)}")
        tags = doc.get("tags")
        if isinstance(tags, (list, tuple)) and tags:
            meta_parts.append("、".join(html.escape(str(tag)) for tag in tags))
        meta_html = f'<span class="type">{" · ".join(meta_parts)}</span>' if meta_parts else ""
        rows += (
            "<li>"
            f'<a href="{html.escape(href, quote=True)}">{html.escape(title)}</a>'
            f"{meta_html}"
            "</li>"
        )
    body = (
        intro
        + '<section class="page-group"><h2>文件 '
        f"<span>{total}</span></h2>"
        f'<ul class="page-list">{rows}</ul></section>'
    )
    return layout("文件", body)


def _dict_list(value: object) -> list[dict[str, object]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
