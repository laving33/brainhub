"""HTML helpers for BrainHub's local memory web views."""
from __future__ import annotations

import html
import urllib.parse
from collections.abc import Callable, Sequence

from .web_ingest import copy_button


MemoryActionHints = Callable[[dict[str, object]], list[dict[str, object]]]
PageHref = Callable[[str], str]


def memory_dashboard_next_actions(
    *,
    memory_count: int,
    review_count: int,
    updated_count: int,
    archived_count: int,
    capture_count: int = 0,
    capture_warning_count: int = 0,
) -> list[dict[str, str]]:
    """Return web dashboard next actions for current memory/capture state."""
    actions: list[dict[str, str]] = []
    if capture_warning_count:
        actions.append({
            "label": "遮蔽擷取紀錄警告",
            "detail": f"有 {capture_warning_count} 筆原始擷取紀錄含疑似機密值。",
            "href": "/captures",
            "command": "python3 brainhub_engine.py redact-capture raw/memory-captures/<capture>.md .",
            "priority": "high",
        })
    if review_count:
        actions.append({
            "label": "審核待處理記憶",
            "detail": f"有 {review_count} 筆記憶需要確認或整理中繼資料。",
            "href": "/inbox",
            "command": "python3 brainhub_engine.py memory-inbox .",
            "priority": "high",
        })
    if updated_count:
        actions.append({
            "label": "稽核近期記憶更新",
            "detail": f"有 {updated_count} 筆記憶更新應檢查其正確性。",
            "href": "/memory",
            "command": "python3 brainhub_engine.py profile .",
            "priority": "medium",
        })
    if archived_count:
        actions.append({
            "label": "檢視已封存記憶",
            "detail": f"有 {archived_count} 筆已封存記憶頁面可查閱，但預設不會被回想。",
            "href": "/profile",
            "command": "python3 brainhub_engine.py profile .",
            "priority": "low",
        })
    if capture_count and not capture_warning_count:
        actions.append({
            "label": "審核原始擷取紀錄",
            "detail": f"有 {capture_count} 筆已儲存的原始擷取紀錄可接受、遮蔽機密或刪除。",
            "href": "/captures",
            "command": "python3 brainhub_engine.py accept-capture raw/memory-captures/<capture>.md . --index 1",
            "priority": "medium",
        })
    if not memory_count:
        actions.append({
            "label": "建立第一筆記憶",
            "detail": "為本機 agent 儲存明確的偏好、決策、專案事實或筆記。",
            "href": "",
            "command": 'python3 brainhub_engine.py remember "User prefers ..." . --type preference --scope user',
            "priority": "high",
        })
    if not actions:
        actions.append({
            "label": "記憶已就緒可回想",
            "detail": "沒有待審核項目或近期更新需要處理。",
            "href": "/profile",
            "command": "python3 brainhub_engine.py profile .",
            "priority": "info",
        })
    return actions[:3]


def render_memory_action_button(action: dict[str, object]) -> str:
    kind = str(action.get("kind") or "")
    if kind not in {"review", "archive", "restore"}:
        return ""
    arguments = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
    identifier = str(arguments.get("identifier") or "")
    if not identifier:
        return ""
    labels = {
        "review": "標記為已審核",
        "archive": "封存",
        "restore": "還原",
    }
    return (
        f'<button type="button" data-memory-action="{html.escape(kind, quote=True)}" '
        f'data-memory="{html.escape(identifier, quote=True)}">'
        f'{html.escape(labels[kind])}</button>'
    )


def render_memory_action_commands(actions: Sequence[dict[str, object]]) -> str:
    if not actions:
        return ""
    rows = ""
    for action in actions:
        label = html.escape(str(action.get("label") or ""))
        if action.get("href"):
            label_html = f'<a href="{html.escape(str(action["href"]))}">{label}</a>'
        else:
            label_html = label
        priority = str(action.get("priority") or "")
        priority_html = f'<span class="memory-meta">{html.escape(priority)}</span>' if priority else ""
        button_html = render_memory_action_button(action)
        command = str(action.get("command") or "")
        copy_html = copy_button(command, "複製指令")
        rows += (
            f'<div class="memory-action-row"><span class="memory-action-head"><strong>{label_html}</strong>'
            f'{priority_html}{button_html}</span>'
            f'<code>{html.escape(command)}</code>{copy_html}</div>'
        )
    return f'<div class="memory-actions">{rows}</div>'


def render_confidence_meter(confidence: str) -> str:
    """Render the T1 segment meter for a recall confidence label."""
    level = str(confidence or "").strip().lower()
    if level not in {"strong", "moderate", "weak"}:
        return ""
    level_labels = {"strong": "高", "moderate": "中", "weak": "低"}
    return (
        f'<span class="conf conf--{level}">'
        '<span class="m"><i></i><i></i><i></i></span>'
        f'{level_labels[level]}</span>'
    )


def render_memory_card(
    record: dict[str, object],
    *,
    page_href: PageHref,
    action_hints: MemoryActionHints | None = None,
    include_issues: bool = False,
) -> str:
    name = str(record.get("name") or "")
    title = str(record.get("title") or name)
    summary = str(record.get("tldr") or record.get("snippet") or "")
    meta_parts = [
        str(record.get("memory_type") or "note"),
        str(record.get("scope") or "user"),
        f'可見度 {record.get("visibility") or "private"}',
        str(record.get("status") or "active"),
    ]
    if record.get("updated_at"):
        meta_parts.append(f'更新於 {record["updated_at"]}')
    elif record.get("date_captured"):
        meta_parts.append(f'擷取於 {record["date_captured"]}')
    if record.get("review_after"):
        meta_parts.append(f'審核期限 {record["review_after"]}')
    if record.get("expires_at"):
        meta_parts.append(f'到期於 {record["expires_at"]}')
    meta = " · ".join(part for part in meta_parts if part)
    issues_html = ""
    if include_issues and record.get("issues"):
        issues_html = "<ul class='memory-issues'>" + "".join(
            f'<li><span class="severity">{html.escape(str(issue["severity"]))}</span> '
            f'{html.escape(str(issue["code"]))}: {html.escape(str(issue["message"]))}</li>'
            for issue in record["issues"]
            if isinstance(issue, dict)
        ) + "</ul>"
    actions = render_memory_action_commands(record.get("actions") or (action_hints(record) if action_hints else []))
    summary_html = f'<p class="summary">{html.escape(summary)}</p>' if summary else ""
    page_url = html.escape(page_href(name), quote=True)
    encoded_name = urllib.parse.quote(name, safe="")
    trust_links = (
        '<div class="memory-meta">'
        f'<a href="/explain-memory?memory={encoded_name}">說明</a>'
        ' · '
        f'<a href="/graph?focus={encoded_name}&amp;depth=2">知識圖譜</a>'
        "</div>"
    )
    confidence_html = render_confidence_meter(str(record.get("confidence") or ""))
    review_status = str(record.get("review_status") or "")
    card_class = "memory-card"
    if review_status and review_status != "reviewed":
        card_class += " needs-review"
    verify_html = ""
    if confidence_html and str(record.get("confidence")) == "weak" and review_status != "reviewed":
        verify_html = '<div class="verify-note">低信心回憶．待審核——採信前請先查證</div>'
    title_html = (
        f'<h3><a href="{page_url}">{html.escape(title)}</a>'
        + (f" {confidence_html}" if confidence_html else "")
        + "</h3>"
    )
    return (
        f'<article class="{card_class}">'
        f'{title_html}'
        f'<div class="memory-meta">{html.escape(meta)}</div>'
        f'{trust_links}'
        f'{summary_html}'
        f'{verify_html}'
        f'{issues_html}'
        f'{actions}'
        '</article>'
    )


def render_memory_section(
    title: str,
    records: list[dict[str, object]],
    empty: str,
    *,
    page_href: PageHref,
    action_hints: MemoryActionHints | None = None,
    href: str = "",
    include_issues: bool = False,
) -> str:
    heading_link = f'<a href="{html.escape(href)}">查看全部</a>' if href else ""
    heading = f'<div class="section-heading"><h2>{html.escape(title)}</h2>{heading_link}</div>'
    if not records:
        return heading + f"<p>{html.escape(empty)}</p>"
    cards = "".join(
        render_memory_card(record, page_href=page_href, action_hints=action_hints, include_issues=include_issues)
        for record in records
    )
    return heading + f'<div class="memory-grid">{cards}</div>'


def render_capture_card(capture: dict[str, object]) -> str:
    title = html.escape(str(capture.get("title") or capture.get("path") or "原始擷取紀錄"))
    path = html.escape(str(capture.get("path") or ""))
    meta_parts = ["原始擷取紀錄"]
    if capture.get("project"):
        meta_parts.append(f'專案 {capture["project"]}')
    if capture.get("date_captured"):
        meta_parts.append(f'擷取於 {capture["date_captured"]}')
    warnings = [str(label) for label in capture.get("secret_warnings") or []]
    if warnings:
        meta_parts.append("疑似機密值警告")
    meta = " · ".join(meta_parts)
    warning_html = ""
    if warnings:
        warning_html = (
            '<p class="summary"><strong>疑似機密值：</strong> '
            + html.escape(", ".join(warnings))
            + "</p>"
        )
    commands = capture.get("commands") or {}
    actions = "".join(
        f'<div><strong>{html.escape(label)}</strong>'
        f'{copy_button(str(command), "複製指令")}'
        f'<code>{html.escape(str(command))}</code></div>'
        for label, command in (
            ("接受提案", commands.get("accept", "")),
            ("遮蔽機密", commands.get("redact", "")),
            ("刪除", commands.get("delete", "")),
        )
        if command
    )
    return (
        '<article class="memory-card">'
        f'<h3>{title}</h3>'
        f'<div class="memory-meta">{html.escape(meta)}</div>'
        f'<p class="summary"><code>{path}</code></p>'
        f'{warning_html}'
        f'<div class="memory-actions">{actions}</div>'
        '</article>'
    )


def render_capture_section(captures: list[dict[str, object]]) -> str:
    heading = '<div class="section-heading"><h2>原始擷取紀錄</h2></div>'
    if not captures:
        return heading + "<p>尚無已儲存的原始擷取紀錄。</p>"
    cards = "".join(render_capture_card(capture) for capture in captures)
    return heading + f'<div class="memory-grid">{cards}</div>'


def render_memory_next_actions(actions: list[dict[str, str]]) -> str:
    items = ""
    for action in actions:
        label = html.escape(action["label"])
        if action.get("href"):
            label_html = f'<a href="{html.escape(action["href"])}">{label}</a>'
        else:
            label_html = label
        items += (
            f'<li><strong>{label_html}</strong>: {html.escape(action["detail"])}'
            f'<br><code>{html.escape(action["command"])}</code>'
            f'{copy_button(action["command"], "複製指令")}</li>'
        )
    return f'<div class="memory-next"><strong>後續行動</strong><ul>{items}</ul></div>'
