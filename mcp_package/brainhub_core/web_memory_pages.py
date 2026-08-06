"""HTML page renderers for BrainHub's memory web views."""
from __future__ import annotations

import html
import urllib.parse
from collections.abc import Callable, Mapping

from .web_ingest import copy_button
from .web_layout import render_stat_grid
from .web_memory import (
    MemoryActionHints,
    render_capture_section,
    render_memory_action_commands,
    render_memory_next_actions,
    render_memory_section,
)


PageHref = Callable[[str], str]
PageLayout = Callable[[str, str], str]


def render_brief_page(
    brief: Mapping[str, object],
    query: str,
    *,
    page_href: PageHref,
    action_hints: MemoryActionHints,
    layout: PageLayout,
) -> str:
    profile = _mapping(brief.get("profile"))
    captures = _mapping(brief.get("captures"))
    review = _mapping(brief.get("review"))
    stats = render_stat_grid([
        (profile.get("active_count", 0), "使用中"),
        (brief.get("relevant_count", 0), "相關"),
        (review.get("count", 0), "待審"),
        (captures.get("count", 0), "擷取紀錄"),
    ])
    guidance = "".join(
        f"<li>{html.escape(str(item))}</li>"
        for item in _sequence(brief.get("agent_guidance"))
    )
    project = str(brief.get("project") or "")
    project_field = (
        f'<input type="hidden" name="project" value="{html.escape(project, quote=True)}">'
        if project else ""
    )
    brief_prompt = _brief_prompt(query, project)
    query_prompt = str(query or "").strip()
    query_action = (
        copy_button(f"跟 BrainHub 查詢 {query_prompt}", "複製查詢提示詞")
        if query_prompt else ""
    )
    relevant_memories = _dict_list(brief.get("relevant_memories"))
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 簡報</div>'
        '<h1>記憶簡報</h1>'
        '<div class="memory-profile">'
        '<p class="summary">在 agent 開始回答、寫程式或規劃之前，先提供的啟動情境。</p>'
        '<form class="brief-form" action="/brief" method="get">'
        f'<input type="text" name="q" value="{html.escape(str(query), quote=True)}" placeholder="輸入任務或問題">'
        f'{project_field}<button type="submit">產生簡報</button></form>'
        f'<div class="page-actions">{copy_button(brief_prompt, "複製簡報提示詞")}{query_action}</div>'
        f'{_project_line(project)}'
        f'{stats}'
        f'<h2>Agent 指引</h2><ul>{guidance}</ul>'
        f'{render_memory_section("相關記憶", relevant_memories, "目前沒有相關記憶。", page_href=page_href, action_hints=action_hints)}'
        f'{_render_empty_brief_actions(query_prompt) if not relevant_memories else ""}'
        f'{render_memory_section("審核佇列", _dict_list(review.get("items")), "目前沒有待審記憶項目。", page_href=page_href, action_hints=action_hints, href="/inbox", include_issues=True)}'
        f'{render_capture_section(_dict_list(captures.get("items")))}'
        '</div>'
    )
    return layout("記憶簡報", body)


def _render_empty_brief_actions(query: str) -> str:
    query_text = str(query or "").strip()
    proposal_prompt = (
        f"跟 BrainHub 草擬關於 {query_text} 的記憶提案（依 raw 來源）"
        if query_text else "跟 BrainHub 草擬記憶提案（依 raw 來源）"
    )
    return (
        '<div class="memory-next"><strong>在產生下一份簡報前，先讓 BrainHub 學會這些</strong>'
        "<ul>"
        '<li>如果這個情境內容在筆記、文件或逐字稿裡，<a href="/ingest">新增來源資料</a>。</li>'
        '<li>在儲存為長期記憶前，先<a href="/propose">審核記憶提案</a>。</li>'
        f"<li>{copy_button(proposal_prompt, '複製記憶提案提示詞')}</li>"
        "</ul></div>"
    )


def _brief_prompt(query: str, project: str = "") -> str:
    task = str(query or "").strip()
    project_name = str(project or "").strip()
    if task and project_name:
        return f"跟 BrainHub 要一份關於 {task} 的簡報（專案 {project_name}）"
    if task:
        return f"跟 BrainHub 要一份關於 {task} 的簡報"
    if project_name:
        return f"跟 BrainHub 要一份專案 {project_name} 的簡報"
    return "先跟 BrainHub 對一下，再繼續"


def _copy_actions(actions: list[tuple[str, str]]) -> str:
    buttons = "".join(copy_button(prompt, label) for prompt, label in actions if prompt)
    return f'<div class="page-actions">{buttons}</div>' if buttons else ""


def _memory_overview_prompt(project: str = "") -> str:
    project_name = str(project or "").strip()
    if project_name:
        return f"BrainHub 記得關於專案 {project_name} 的哪些事？"
    return "BrainHub 記得我的哪些事？"


def _audit_prompt(project: str = "") -> str:
    project_name = str(project or "").strip()
    if project_name:
        return f"稽核 BrainHub 專案 {project_name} 的記憶"
    return "稽核 BrainHub 的記憶"


def _inbox_prompt(project: str = "") -> str:
    project_name = str(project or "").strip()
    if project_name:
        return f"審核 BrainHub 專案 {project_name} 的記憶待審清單"
    return "審核 BrainHub 的記憶待審清單"


def _capture_prompt(project: str = "") -> str:
    project_name = str(project or "").strip()
    if project_name:
        return f"審核 BrainHub 專案 {project_name} 的 raw 擷取紀錄"
    return "審核 BrainHub 的 raw 擷取紀錄"


def render_memory_dashboard_page(
    dashboard: Mapping[str, object],
    *,
    page_href: PageHref,
    action_hints: MemoryActionHints,
    layout: PageLayout,
) -> str:
    stats = render_stat_grid([
        (dashboard.get("memory_count", 0), "記憶"),
        (dashboard.get("active_count", 0), "使用中"),
        (dashboard.get("review_count", 0), "待審"),
        (dashboard.get("updated_count", 0), "已更新"),
        (dashboard.get("capture_count", 0), "擷取紀錄"),
        (dashboard.get("archived_count", 0), "已封存"),
    ])
    counts = ""
    by_type = _mapping(dashboard.get("by_type"))
    by_scope = _mapping(dashboard.get("by_scope"))
    if by_type:
        counts += _counts_line("類型", by_type)
    if by_scope:
        counts += _counts_line("範圍", by_scope)
    project = str(dashboard.get("project") or "")
    dashboard_actions = _copy_actions([
        (_memory_overview_prompt(project), "複製總覽提示詞"),
        (_brief_prompt("", project), "複製簡報提示詞"),
        (_audit_prompt(project), "複製稽核提示詞"),
    ])
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 記憶</div>'
        '<h1>記憶儀表板</h1>'
        '<div class="memory-dashboard">'
        '<p class="summary">唯讀指揮中心，一覽本機 agent 能記住什麼、哪些需要審核，以及最近有哪些變動。</p>'
        f'{dashboard_actions}'
        f'{_project_line(project)}'
        f'{stats}'
        f'{render_memory_next_actions(_dict_list(dashboard.get("next_actions")))}'
        f'{counts}'
        f'{render_memory_section("待審記憶", _dict_list(dashboard.get("review")), "目前沒有記憶需要審核。", page_href=page_href, action_hints=action_hints, href="/inbox", include_issues=True)}'
        f'{render_capture_section(_dict_list(dashboard.get("captures")))}'
        f'{render_memory_section("近期更新", _dict_list(dashboard.get("recent_updates")), "目前沒有記憶更新。", page_href=page_href, action_hints=action_hints)}'
        f'{render_memory_section("使用中的記憶", _dict_list(dashboard.get("active")), "目前沒有使用中的記憶。", page_href=page_href, action_hints=action_hints, href="/profile")}'
        f'{render_memory_section("已封存的記憶", _dict_list(dashboard.get("archived")), "目前沒有已封存的記憶。", page_href=page_href, action_hints=action_hints)}'
        '</div>'
    )
    return layout("記憶儀表板", body)


def render_profile_page(
    profile: Mapping[str, object],
    *,
    page_href: PageHref,
    layout: PageLayout,
) -> str:
    stats = render_stat_grid([
        (profile.get("memory_count", 0), "記憶"),
        (profile.get("active_count", 0), "使用中"),
        (profile.get("review_count", 0), "待審"),
    ])
    archived = _dict_list(profile.get("archived"))
    project = str(profile.get("project") or "")
    profile_actions = _copy_actions([
        (_memory_overview_prompt(project), "複製總覽提示詞"),
        (_brief_prompt("", project), "複製簡報提示詞"),
    ])
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 總覽</div>'
        '<h1>記憶總覽</h1>'
        '<div class="memory-profile">'
        '<p class="summary">BrainHub 目前記住的使用者、專案、決策與偏好。</p>'
        f'{profile_actions}'
        f'{_project_line(project)}'
        f'{stats}'
        f'{_counts_line("類型", _mapping(profile.get("by_type")))}'
        f'{_counts_line("範圍", _mapping(profile.get("by_scope")))}'
        f'{_counts_line("狀態", _mapping(profile.get("by_status")))}'
        f'{_render_empty_profile_actions(project) if not int(profile.get("memory_count") or 0) else ""}'
        f'{_profile_section("近期記憶", _dict_list(profile.get("recent")), page_href=page_href)}'
        f'{_profile_section("偏好設定", _dict_list(profile.get("preferences")), page_href=page_href)}'
        f'{_profile_section("決策", _dict_list(profile.get("decisions")), page_href=page_href)}'
        f'{_profile_section("專案情境", _dict_list(profile.get("projects")), page_href=page_href)}'
        f'{_profile_section("已封存的記憶", archived, page_href=page_href) if archived else ""}'
        '</div>'
    )
    return layout("記憶總覽", body)


def _render_empty_profile_actions(project: str) -> str:
    project_name = str(project or "").strip()
    remember_prompt = (
        f"記住 <偏好或決策>，屬於專案 {project_name}"
        if project_name else "記住 <偏好或決策>"
    )
    return (
        '<div class="memory-next"><strong>目前還沒有長期記憶</strong>'
        "<ul>"
        '<li>如果這個情境該先進 wiki，<a href="/ingest">新增來源資料</a>。</li>'
        '<li>當 raw 筆記裡有偏好、決策或專案事實時，<a href="/propose">審核記憶提案</a>。</li>'
        f"<li>{copy_button(remember_prompt, '複製記住提示詞')}</li>"
        "</ul></div>"
    )


def render_memory_audit_page(
    audit: Mapping[str, object],
    *,
    page_href: PageHref,
    action_hints: MemoryActionHints,
    layout: PageLayout,
) -> str:
    profile = _mapping(audit.get("profile"))
    captures = _mapping(audit.get("captures"))
    inbox = _mapping(audit.get("inbox"))
    stats = render_stat_grid([
        (profile.get("memory_count", 0), "記憶"),
        (profile.get("active_count", 0), "使用中"),
        (profile.get("review_count", 0), "待審"),
        (captures.get("count", 0), "擷取紀錄"),
        (captures.get("warning_count", 0), "警告"),
        (captures.get("read_warning_count", 0), "讀取警告"),
    ])
    risk_factors = _dict_list(audit.get("risk_factors"))
    if risk_factors:
        risk_html = "<h2>需要留意</h2><ul class='memory-issues'>" + "".join(
            f'<li><span class="severity">審核</span> {html.escape(str(item.get("code") or ""))}: '
            f'{html.escape(str(item.get("message") or ""))}</li>'
            for item in risk_factors
        ) + "</ul>"
    else:
        risk_html = "<h2>需要留意</h2><p>未偵測到記憶稽核風險。</p>"
    project = str(audit.get("project") or "")
    audit_actions = _copy_actions([
        (_audit_prompt(project), "複製稽核提示詞"),
        (_inbox_prompt(project), "複製審核提示詞"),
    ])
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 稽核</div>'
        '<h1>記憶稽核</h1>'
        '<div class="memory-profile">'
        '<p class="summary">唯讀健康報告，涵蓋本機 agent 記憶、待審積壓、raw 擷取紀錄，以及安全的下一步。</p>'
        f'{audit_actions}'
        f'{_project_line(project)}'
        f'<p><strong>狀態：</strong> {html.escape(str(audit.get("status") or ""))}</p>'
        f'{stats}'
        f'{risk_html}'
        f'{render_memory_next_actions(_dict_list(audit.get("next_actions")))}'
        f'{render_memory_section("記憶待審清單範例", _dict_list(inbox.get("items")), "目前沒有待審記憶項目。", page_href=page_href, action_hints=action_hints, href="/inbox", include_issues=True)}'
        f'{render_capture_section(_dict_list(captures.get("items")))}'
        '</div>'
    )
    return layout("記憶稽核", body)


def render_captures_page(inbox: Mapping[str, object], *, layout: PageLayout) -> str:
    warning_count = int(inbox.get("warning_count") or 0)
    stats = render_stat_grid([
        (inbox.get("count", 0), "擷取紀錄"),
        (warning_count, "警告"),
        (inbox.get("read_warning_count", 0), "讀取警告"),
    ])
    warning_html = ""
    if warning_count:
        warning_html = (
            '<div class="memory-next"><strong>需要遮蔽敏感資訊</strong>'
            f'<p>有 {warning_count} 筆 raw 擷取紀錄疑似包含機密內容。</p>'
            '<code>python3 brainhub_engine.py redact-capture raw/memory-captures/&lt;capture&gt;.md .</code></div>'
        )
    read_warning_html = ""
    read_warnings = _dict_list(inbox.get("read_warnings"))
    if read_warnings:
        rows = "".join(
            f'<li><code>{html.escape(str(item.get("capture") or ""))}</code> '
            f'{html.escape(str(item.get("error") or "無法讀取"))}</li>'
            for item in read_warnings[:50]
        )
        read_warning_html = (
            '<div class="memory-next"><strong>修正擷取紀錄的讀取問題</strong>'
            '<p>部分 raw 擷取紀錄無法讀取，因此未列入待核准清單。</p>'
            f'<ul>{rows}</ul></div>'
        )
    project = str(inbox.get("project") or "")
    capture_actions = _copy_actions([(_capture_prompt(project), "複製擷取提示詞")])
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 擷取紀錄</div>'
        '<h1>Raw 擷取紀錄待審清單</h1>'
        '<div class="memory-profile">'
        '<p class="summary">已儲存、僅供提案用的工作階段筆記，在成為長期記憶前等待人工審核。</p>'
        f'{capture_actions}'
        f'{_project_line(project)}'
        f'{stats}'
        f'{warning_html}'
        f'{read_warning_html}'
        f'{render_capture_section(_dict_list(inbox.get("captures")))}'
        '</div>'
    )
    return layout("Raw 擷取紀錄待審清單", body)


def render_inbox_page(
    inbox: Mapping[str, object],
    *,
    page_href: PageHref,
    layout: PageLayout,
) -> str:
    stats = render_stat_grid([(inbox.get("review_count", 0), "待審")])
    severity_html = _counts_line("嚴重程度", _mapping(inbox.get("counts_by_severity")))
    items = _dict_list(inbox.get("items"))
    if not items:
        content = "<p>待審清單目前是空的。</p>"
    else:
        rows = "".join(_render_inbox_item(item, page_href=page_href) for item in items)
        content = f"<ul class='page-list'>{rows}</ul>"
    project = str(inbox.get("project") or "")
    inbox_actions = _copy_actions([(_inbox_prompt(project), "複製審核提示詞")])
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 審核收件匣</div>'
        '<h1>記憶審核收件匣</h1>'
        '<div class="memory-profile">'
        '<p class="summary">需要確認、補強中繼資料，或進行清理的記憶。</p>'
        f'{inbox_actions}'
        f'{_project_line(project)}'
        f'{stats}'
        f'{severity_html}'
        f'{content}'
        '</div>'
    )
    return layout("記憶審核收件匣", body)


def render_memory_log_page(log_payload: Mapping[str, object], *, layout: PageLayout) -> str:
    entries = _dict_list(log_payload.get("entries"))
    if entries:
        rows = "".join(_render_memory_log_item(entry) for entry in entries)
        content = f"<ul class='page-list memory-log-list'>{rows}</ul>"
    else:
        content = (
            "<p>目前沒有記憶生命週期事件。</p>"
            '<p><a class="button-link" href="/propose">建立記憶提案</a></p>'
        )
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 記憶異動紀錄</div>'
        '<h1>記憶異動紀錄</h1>'
        '<div class="memory-profile">'
        '<p class="summary">保護隱私的時間軸，記錄記憶的建立、更新、審核、封存、還原、遺忘，以及擷取紀錄核准。</p>'
        f'{render_stat_grid([(log_payload.get("count", 0), "顯示中"), (log_payload.get("total_matching", 0), "符合條件")])}'
        f'<p>{html.escape(str(log_payload.get("privacy_note") or ""))}</p>'
        f'{content}'
        '</div>'
    )
    return layout("記憶異動紀錄", body)


def render_memory_wins_page(
    wins_payload: Mapping[str, object],
    *,
    page_href: PageHref,
    layout: PageLayout,
) -> str:
    wins = _dict_list(wins_payload.get("wins"))
    win_cards = "".join(_render_memory_win_card(win) for win in wins)
    recent = _dict_list(wins_payload.get("recent_memories"))
    recent_html = _profile_section("近期可重複使用的記憶", recent, page_href=page_href) if recent else (
        "<h2>近期可重複使用的記憶</h2><p>目前沒有使用中的記憶。</p>"
    )
    prompts = "".join(
        f"<li>{html.escape(str(prompt))} {copy_button(str(prompt), '複製提示詞')}</li>"
        for prompt in _list(wins_payload.get("prompts"))[:4]
    )
    actions = "".join(
        "<li>"
        f"<strong>{html.escape(str(action.get('label') or '下一步'))}</strong>"
        f"<p>{html.escape(str(action.get('reason') or ''))}</p>"
        f"<code>{html.escape(str(action.get('command') or ''))}</code>"
        f"{copy_button(str(action.get('command') or ''), '複製指令')}"
        "</li>"
        for action in _dict_list(wins_payload.get("next_actions"))
    )
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 成效</div>'
        '<h1>記憶成效</h1>'
        '<div class="memory-profile">'
        '<p class="summary">本機端的佐證訊號，呈現 BrainHub 記憶目前承載的內容；這些數據是從 wiki 計算出來的，不是遙測資料。</p>'
        f'{render_stat_grid([(wins_payload.get("active_count", 0), "使用中"), (wins_payload.get("reviewed_active_count", 0), "已審核"), (wins_payload.get("review_count", 0), "待審"), (wins_payload.get("project_count", 0), "專案")])}'
        f'<p>{html.escape(str(wins_payload.get("honest_note") or ""))}</p>'
        f'<section class="memory-grid">{win_cards}</section>'
        f'{recent_html}'
        '<h2>體驗價值循環</h2>'
        f'<ul class="memory-issues">{prompts}</ul>'
        '<h2>下一步安全動作</h2>'
        f'<ul class="page-list">{actions}</ul>'
        '</div>'
    )
    return layout("記憶成效", body)


def render_memory_explanation_page(
    explanation: Mapping[str, object],
    *,
    body_html: str,
    layout: PageLayout,
) -> str:
    memory = _mapping(explanation.get("memory"))
    recall_info = _mapping(explanation.get("recall"))
    review = _mapping(explanation.get("review"))
    provenance = _mapping(explanation.get("provenance"))
    lifecycle = _mapping(explanation.get("lifecycle"))
    graph = _mapping(explanation.get("graph"))
    title = str(memory.get("title") or memory.get("name") or "記憶")
    memory_name = str(memory.get("name") or "")
    graph_href = f"/graph?focus={urllib.parse.quote(memory_name, safe='')}&depth=2" if memory_name else "/graph"
    summary = memory.get("tldr") or memory.get("snippet") or ""
    issues = "".join(
        f'<li><span class="severity">{html.escape(str(issue.get("severity") or ""))}</span> '
        f'{html.escape(str(issue.get("code") or ""))}: {html.escape(str(issue.get("message") or ""))}</li>'
        for issue in _dict_list(review.get("issues"))
    )
    issue_html = (
        f'<h2>審核問題</h2><ul class="memory-issues">{issues}</ul>'
        if issues else "<h2>審核問題</h2><p>未偵測到問題。</p>"
    )
    primary = _mapping(review.get("primary_action"))
    primary_html = ""
    if primary:
        primary_html = (
            f'<p class="summary"><strong>下一步：</strong> {html.escape(str(primary.get("label") or ""))} '
            f'——{html.escape(str(primary.get("description") or ""))}</p>'
        )
    action_html = f'<h2>操作</h2>{primary_html}{render_memory_action_commands(_dict_list(review.get("actions")))}'
    graph_html = (
        '<h2>知識圖譜</h2>'
        f'<p><a class="button-link" href="{html.escape(graph_href, quote=True)}">開啟本機知識圖譜</a></p>'
        f'<p><strong>正向連結：</strong> {html.escape(", ".join(str(item) for item in _list(graph.get("forward"))) or "無")}</p>'
        f'<p><strong>反向連結：</strong> {html.escape(", ".join(str(item) for item in _list(graph.get("inbound"))) or "無")}</p>'
        f'<p><strong>Wiki 連結：</strong> {html.escape(", ".join(str(item) for item in _list(graph.get("wikilinks"))) or "無")}</p>'
    )
    logs = "".join(
        f'<pre class="log-entry">{html.escape(str(entry))}</pre>'
        for entry in _list(explanation.get("log_entries"))[-5:]
    )
    log_html = f"<h2>操作紀錄</h2>{logs}" if logs else "<h2>操作紀錄</h2><p>沒有符合條件的紀錄。</p>"
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 記憶說明</div>'
        f'<h1>{html.escape(title)}</h1>'
        f'<p class="summary">{html.escape(str(summary))}</p>'
        '<div class="trust-grid">'
        f'<div><strong>回想</strong>{html.escape(str(recall_info.get("state") or ""))}<br><small>{html.escape(str(recall_info.get("reason") or ""))}</small></div>'
        f'<div><strong>審核</strong>{html.escape(str(review.get("status") or ""))} · {html.escape(str(review.get("issue_count", 0)))} 個問題</div>'
        f'<div><strong>狀態</strong>{html.escape(str(lifecycle.get("status") or ""))}</div>'
        f'<div><strong>來源</strong>{html.escape(str(provenance.get("source") or "缺少"))}</div>'
        f'<div><strong>擷取日期</strong>{html.escape(str(provenance.get("date_captured") or "缺少"))}</div>'
        f'<div><strong>路徑</strong>{html.escape(str(provenance.get("path") or ""))}</div>'
        '</div>'
        f'{issue_html}'
        f'{action_html}'
        f'{graph_html}'
        f'{log_html}'
        f'<h2>記憶內容</h2>{body_html}'
    )
    return layout(f"記憶說明：{title}", body)


def _render_memory_log_item(entry: Mapping[str, object]) -> str:
    paths = _list(entry.get("memory_paths"))
    path_html = ""
    if paths:
        path_html = "<div class='memory-meta'>相關記憶：" + html.escape(", ".join(str(path) for path in paths)) + "</div>"
    details = _list(entry.get("details"))
    detail_html = ""
    if details:
        detail_html = "<ul class='memory-issues'>" + "".join(
            f"<li>{html.escape(str(detail))}</li>"
            for detail in details[:4]
        ) + "</ul>"
    changes = _dict_list(entry.get("changes"))
    change_html = ""
    if changes:
        change_html = "<ul class='memory-issues'>" + "".join(
            "<li>"
            f"<strong>{html.escape(str(change.get('field') or '欄位'))}</strong>: "
            f"{html.escape(str(change.get('from') or '未設定'))} → {html.escape(str(change.get('to') or '未設定'))}"
            "</li>"
            for change in changes[:4]
        ) + "</ul>"
    impact = str(entry.get("impact") or "")
    impact_html = f'<p class="summary">{html.escape(impact)}</p>' if impact else ""
    return (
        "<li>"
        f"<strong>{html.escape(str(entry.get('operation') or '事件'))}</strong>"
        f"<div class='memory-meta'>{html.escape(str(entry.get('timestamp') or ''))} · {html.escape(str(entry.get('category') or '記憶'))}</div>"
        f"<p>{html.escape(str(entry.get('description') or ''))}</p>"
        f"<small>{html.escape(str(entry.get('summary') or ''))}</small>"
        f"{impact_html}"
        f"{change_html}"
        f"{path_html}"
        f"{detail_html}"
        "</li>"
    )


def _render_memory_win_card(win: Mapping[str, object]) -> str:
    prompt = str(win.get("prompt") or "")
    return (
        '<article class="memory-card">'
        f'<h2>{html.escape(str(win.get("label") or ""))}</h2>'
        f'<div class="memory-metric">{html.escape(str(win.get("count") or 0))}</div>'
        f'<p>{html.escape(str(win.get("description") or ""))}</p>'
        f'{copy_button(prompt, "複製提示詞") if prompt else ""}'
        '</article>'
    )


def _render_inbox_item(item: Mapping[str, object], *, page_href: PageHref) -> str:
    name = str(item.get("name") or "")
    summary = item.get("tldr") or item.get("snippet") or ""
    meta = f'{item.get("memory_type", "")} · {item.get("scope", "")} · {item.get("status", "")}'
    issues = "".join(
        f'<li><span class="severity">{html.escape(str(issue.get("severity") or ""))}</span> '
        f'{html.escape(str(issue.get("code") or ""))}: {html.escape(str(issue.get("message") or ""))}</li>'
        for issue in _dict_list(item.get("issues"))
    )
    primary = _mapping(item.get("primary_action"))
    primary_html = ""
    if primary:
        primary_html = (
            f'<p class="summary"><strong>下一步：</strong> {html.escape(str(primary.get("label") or ""))} '
            f'——{html.escape(str(primary.get("description") or ""))}</p>'
        )
    return (
        f'<li><a href="{html.escape(page_href(name), quote=True)}">{html.escape(str(item.get("title") or name))}</a>'
        f'<div class="memory-meta">{html.escape(meta)}</div>'
        f'<div class="memory-meta"><a href="/explain-memory?memory={urllib.parse.quote(name, safe="")}">說明</a></div>'
        f'{f"<small>{html.escape(str(summary))}</small>" if summary else ""}'
        f'<ul class="memory-issues">{issues}</ul>'
        f'{primary_html}'
        f'{render_memory_action_commands(_dict_list(item.get("actions")))}</li>'
    )


def _profile_section(
    title: str,
    records: list[dict[str, object]],
    *,
    page_href: PageHref,
    empty: str = "無",
) -> str:
    if not records:
        return f"<h2>{html.escape(title)}</h2><p>{html.escape(empty)}</p>"
    items = ""
    for record in records:
        name = str(record.get("name") or "")
        summary = record.get("tldr") or record.get("snippet") or ""
        meta = f'{record.get("memory_type", "")} · {record.get("scope", "")}'
        items += (
            f'<li><a href="{html.escape(page_href(name), quote=True)}">{html.escape(str(record.get("title") or name))}</a>'
            f'<div class="memory-meta">{html.escape(meta)}</div>'
            f'<div class="memory-meta"><a href="/explain-memory?memory={urllib.parse.quote(name, safe="")}">說明</a></div>'
            f'{f"<small>{html.escape(str(summary))}</small>" if summary else ""}</li>'
        )
    return f"<h2>{html.escape(title)}</h2><ul class='page-list'>{items}</ul>"


def _counts_line(title: str, counts: Mapping[str, object]) -> str:
    if not counts:
        return ""
    parts = ", ".join(
        f"{html.escape(str(name))}: {html.escape(str(count))}"
        for name, count in counts.items()
    )
    return f"<p><strong>{html.escape(title)}：</strong> {parts}</p>"


def _project_line(project: str) -> str:
    return f"<p><strong>專案：</strong> {html.escape(project)}</p>" if project else ""


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _sequence(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _dict_list(value: object) -> list[dict[str, object]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
