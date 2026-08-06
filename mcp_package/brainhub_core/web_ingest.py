"""HTML renderer for BrainHub's guided ingest web view."""
from __future__ import annotations

import html
import urllib.parse
from collections.abc import Callable, Mapping

from .mcp_verify import display_command
from .web_layout import render_stat_grid


PageHref = Callable[[str], str]
PageLayout = Callable[[str, str], str]


def render_ingest_page(
    status: Mapping[str, object],
    *,
    page_href: PageHref,
    layout: PageLayout,
) -> str:
    guidance = _mapping(status.get("guidance"))
    agent_prompt = str(guidance.get("agent_prompt") or "")
    commands = _list(status_value=guidance.get("commands"))
    notes = _list(status_value=guidance.get("notes"))
    plan = _mapping(status.get("plan"))
    pending = _dict_list(status.get("pending_raw"))
    represented = _dict_list(status.get("represented_raw"))
    safety = _mapping(status.get("safety"))
    completion = _mapping(status.get("completion"))
    plan_batch = _dict_list(plan.get("batch"))
    plan_first = plan_batch[0] if plan_batch else {}
    first_raw = str(plan_first.get("raw") or "")
    if not first_raw:
        first_raw = str(pending[0].get("raw") or "raw/<file>") if pending else "raw/<file>"
    ingest_prompt = agent_prompt or f"把 {first_raw} 匯入 BrainHub"
    memory_prompt = str(plan.get("memory_prompt") or f"propose memories from {first_raw}")
    propose_href = "/propose?source=" + urllib.parse.quote(first_raw) if pending else "/propose"
    state = str(guidance.get("state") or plan.get("state") or "unknown")
    command_target = str(status.get("target") or "").strip()

    stats = render_stat_grid([
        (int(status.get("raw_count") or 0), "raw"),
        (int(status.get("represented_count") or 0), "已代表"),
        (int(status.get("pending_count") or 0), "待處理"),
        (int(status.get("stale_count") or 0), "已過期"),
        (status.get("backlinks_status") or "unknown", "圖譜"),
        (safety.get("status") or "unknown", "安全性"),
    ])
    safety_html = _render_safety(safety)
    progress_html = _render_progress(status, state)
    actions = _render_actions(agent_prompt, commands)
    next_html, ingest_prompt, optional_memory_html = _render_next_step(
        agent_prompt=agent_prompt,
        commands=commands,
        command_target=command_target,
        state=state,
        first_raw=first_raw,
        propose_href=propose_href,
        memory_prompt=memory_prompt,
    )
    guide_html = _render_guide(
        first_raw,
        ingest_prompt,
        optional_memory_html,
        validate_command=_link_command(command_target, "validate"),
    )
    pending_html = _render_pending(pending, represented)
    notes_html = _render_notes(notes)
    source_warning_html = _render_source_warnings(_dict_list(status.get("source_read_warnings")))
    plan_html = _render_plan(plan)
    completion_html = _render_completion(completion, page_href=page_href)
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 匯入</div>'
        '<h1>匯入</h1>'
        f'<p class="summary">{html.escape(str(guidance.get("summary") or "檢查 raw 來源的匯入狀態。"))}</p>'
        f'{_render_raw_source_form()}'
        f'{stats}'
        f'{progress_html}'
        f'{safety_html}'
        f'{source_warning_html}'
        f'{next_html}'
        f'{guide_html}'
        f'{actions}'
        f'{plan_html}'
        f'{completion_html}'
        f'{pending_html}'
        f'{notes_html}'
    )
    return layout("匯入", body)


def copy_button(text: object, label: str = "複製") -> str:
    value = str(text or "")
    if not value:
        return ""
    return (
        '<button type="button" class="copy-button" '
        f'data-copy-text="{html.escape(value, quote=True)}">{html.escape(label)}</button>'
    )


def _render_safety(safety: Mapping[str, object]) -> str:
    if not safety:
        return ""
    labels = _list(status_value=safety.get("labels"))
    labels_text = ", ".join(html.escape(str(label)) for label in labels)
    labels_html = f"<p>警告：{labels_text}</p>" if labels_text else ""
    return (
        f'<div class="memory-next"><strong>Raw 安全性：{html.escape(str(safety.get("status") or "unknown"))}</strong>'
        f'<p>{html.escape(str(safety.get("summary") or ""))}</p>{labels_html}</div>'
    )


def _render_progress(status: Mapping[str, object], state: str) -> str:
    raw_count = int(status.get("raw_count") or 0)
    represented_count = int(status.get("represented_count") or 0)
    pending_count = int(status.get("pending_count") or 0)
    stale_count = int(status.get("stale_count") or 0)
    backlinks_status = str(status.get("backlinks_status") or "unknown")
    safety = _mapping(status.get("safety"))
    safety_state = str(safety.get("status") or "unknown")

    source_state = "done" if raw_count else "next"
    ingest_state = "done" if represented_count and not pending_count and not stale_count else ("next" if raw_count else "wait")
    validate_state = "done" if backlinks_status == "current" and state == "ready" else ("blocked" if backlinks_status != "current" else "wait")
    memory_state = "next" if represented_count else "wait"
    if safety_state == "blocked":
        source_state = "blocked"
        ingest_state = "blocked"
        validate_state = "wait"
        memory_state = "wait"
    elif stale_count:
        ingest_state = "next"
        validate_state = "wait"

    phases = [
        ("來源", source_state, f"{raw_count} 個 raw 檔案"),
        ("匯入", ingest_state, f"{represented_count} 已代表 · {pending_count} 待處理"),
        ("驗證", validate_state, f"圖譜 {backlinks_status}"),
        ("記憶", memory_state, "提案審核為選用"),
    ]
    rows = "".join(
        '<article class="ingest-progress-step" data-state="'
        f'{html.escape(phase_state, quote=True)}">'
        f'<strong>{html.escape(label)}</strong>'
        f'<span>{html.escape(phase_state)}</span>'
        f'<small>{html.escape(detail)}</small>'
        "</article>"
        for label, phase_state, detail in phases
    )
    return f'<section class="ingest-progress" aria-label="匯入進度">{rows}</section>'


def _render_actions(agent_prompt: str, commands: list[object]) -> str:
    action_rows = ""
    if agent_prompt:
        action_rows += (
            '<div class="memory-action-row"><span class="memory-action-head"><strong>請你的 agent</strong></span>'
            f'{copy_button(agent_prompt, "複製提示詞")}<code>{html.escape(agent_prompt)}</code></div>'
        )
    for command in commands:
        action_rows += (
            '<div class="memory-action-row"><span class="memory-action-head"><strong>執行</strong></span>'
            f'{copy_button(command, "複製指令")}<code>{html.escape(str(command))}</code></div>'
        )
    return f'<div class="memory-actions">{action_rows}</div>' if action_rows else ""


def _render_next_step(
    *,
    agent_prompt: str,
    commands: list[object],
    command_target: str,
    state: str,
    first_raw: str,
    propose_href: str,
    memory_prompt: str,
) -> tuple[str, str, str]:
    if agent_prompt:
        next_detail = "把這段複製到你的 agent 對話中。agent 應該要匯入 raw 來源、重建索引，並在回報完成前先驗證。"
        next_code = agent_prompt
        next_extra = (
            '<p>如果來源內容包含偏好、決策或專案事實，'
            f'請先<a href="{html.escape(propose_href, quote=True)}">開啟記憶提案</a>。</p>'
        )
    elif state == "blocked_secrets":
        next_detail = "在請任何 agent 匯入之前，先塗銷被標記的 raw 來源中疑似機密的內容。"
        next_code = f"edit {first_raw}"
        next_extra = ""
    elif state == "blocked_raw_access":
        next_detail = "在請任何 agent 匯入之前，先修好 raw 檔案的存取權限。BrainHub 無法為了安全檢查而讀取這份來源。"
        next_code = f"inspect {first_raw}"
        next_extra = ""
    elif state == "blocked_source_access":
        next_detail = "在信任匯入狀態之前，先修好來源頁面的存取權限。BrainHub 無法讀取已代表的來源頁面。"
        next_code = _first_command(commands, _link_command(command_target, "ingest-status"))
        next_extra = ""
    elif state == "stale_graph":
        next_detail = "在信任搜尋、脈絡或圖譜檢視之前，先修復圖譜索引。這步之後再執行下面剩下的檢查。"
        next_code = _first_command(commands, _link_command(command_target, "rebuild-backlinks"))
        next_extra = ""
    elif state == "empty":
        next_detail = "在 raw/ 加入一份筆記、文章、逐字稿或專案檔案，然後重新整理這個頁面。"
        next_code = _link_command(command_target, "ingest-status")
        next_extra = ""
    elif state == "ready":
        next_detail = "目前沒有待匯入的內容。可以請 BrainHub 提供脈絡，或在有新素材時再加一份來源。"
        next_code = _link_command(command_target, "brief", "current task")
        next_extra = ""
    else:
        next_detail = "在匯入來源之前，先初始化或修復 BrainHub 資料夾。"
        next_code = _first_command(commands, _link_command(command_target, "init"))
        next_extra = ""

    ingest_prompt = agent_prompt or f"把 {first_raw} 匯入 BrainHub"
    if state == "blocked_secrets":
        ingest_prompt = f"在匯入前先塗銷 {first_raw} 中疑似機密的內容"
        optional_memory_html = '<code>先塗銷，再談記憶提案</code>'
    elif state == "blocked_raw_access":
        ingest_prompt = f"在匯入前先修好 {first_raw} 的存取權限"
        optional_memory_html = '<code>先修好存取權限，再談記憶提案</code>'
    elif state == "blocked_source_access":
        ingest_prompt = "在匯入前先修好來源頁面的存取權限"
        optional_memory_html = '<code>先修好來源存取權限</code>'
    else:
        optional_memory_html = (
            f'<a href="{html.escape(propose_href, quote=True)}"><code>{html.escape(memory_prompt)}</code></a>'
        )
    next_html = (
        '<div class="memory-next"><strong>下一步</strong>'
        f'<p>{html.escape(next_detail)}</p>'
        f'<code>{html.escape(next_code)}</code>'
        f'{copy_button(next_code, "複製下一步")}'
        f'{next_extra}</div>'
    )
    return next_html, ingest_prompt, optional_memory_html


def _render_guide(first_raw: str, ingest_prompt: str, optional_memory_html: str, *, validate_command: str) -> str:
    return (
        '<section class="ingest-path" aria-label="匯入流程">'
        '<article class="ingest-step"><span class="step-num">1</span>'
        '<h3>新增來源</h3><p>把筆記、文章、逐字稿或專案檔案放進 <code>raw/</code>。</p>'
        f'<code>{html.escape(first_raw)}</code></article>'
        '<article class="ingest-step"><span class="step-num">2</span>'
        '<h3>請 agent 處理</h3><p>請你的 agent 把來源轉成有依據的 wiki 頁面。</p>'
        f'<code>{html.escape(ingest_prompt)}</code></article>'
        '<article class="ingest-step"><span class="step-num">3</span>'
        '<h3>驗證</h3><p>在信任結果之前，先檢查頁面結構、連結與圖譜新鮮度。</p>'
        f'<code>{html.escape(validate_command)}</code></article>'
        '<article class="ingest-step"><span class="step-num">4</span>'
        '<h3>選用記憶</h3><p>只有在核可後，才儲存偏好、決策或專案事實。</p>'
        f'{optional_memory_html}</article>'
        '</section>'
    )


def _first_command(commands: list[object], fallback: str) -> str:
    for command in commands:
        text = str(command or "").strip()
        if text:
            return text
    return fallback


def _link_command(command_target: str, *parts: str) -> str:
    command = ["link", *parts]
    if command_target:
        command.append(command_target)
    return display_command(command)


def _render_pending(pending: list[dict[str, object]], represented: list[dict[str, object]]) -> str:
    if not pending:
        return "" if represented else '<p>目前還沒有找到 raw 來源檔案。</p>'
    rows = ""
    for item in pending[:50]:
        raw_path = str(item.get("raw") or "")
        propose_href = "/propose?source=" + urllib.parse.quote(raw_path)
        ingest_prompt = f"把 {raw_path} 匯入 BrainHub" if raw_path else "把 raw/<file> 匯入 BrainHub"
        actions = ""
        secret_warnings = _list(status_value=item.get("secret_warnings"))
        if secret_warnings:
            meta = (
                f'{int(item.get("size_bytes") or 0)} bytes · 機密警告：'
                f'{", ".join(html.escape(str(label)) for label in secret_warnings)} · 匯入前請先塗銷'
            )
            actions = copy_button(f"在匯入前先塗銷 {raw_path} 中疑似機密的內容", "複製塗銷提示詞")
        elif item.get("scan_error"):
            meta = (
                f'{int(item.get("size_bytes") or 0)} bytes · '
                f'無法檢查：{html.escape(str(item.get("scan_error") or ""))} · 匯入前請先修好存取權限'
            )
            actions = copy_button(f"在匯入前先修好 {raw_path} 的存取權限", "複製存取提示詞")
        elif item.get("stale"):
            target_pages = _list(status_value=item.get("source_page_paths"))
            target_label = ", ".join(html.escape(str(page)) for page in target_pages if page)
            target_text = f" · 請重新整理 {target_label}" if target_label else " · 請重新整理既有來源頁面"
            meta = (
                f'{int(item.get("size_bytes") or 0)} bytes · '
                f'{html.escape(str(item.get("stale_reason") or "raw 在 wiki 來源頁面之後又變更了"))}'
                f'{target_text}'
            )
            actions = copy_button(ingest_prompt, "複製匯入提示詞")
        else:
            meta = (
                f'{int(item.get("size_bytes") or 0)} bytes · '
                f'<a href="{html.escape(propose_href, quote=True)}">草擬記憶</a>'
            )
            actions = (
                f'<a href="{html.escape(propose_href, quote=True)}">記憶提案</a>'
                f'{copy_button(ingest_prompt, "複製匯入提示詞")}'
            )
        rows += (
            '<li class="ingest-pending-item">'
            f'<code>{html.escape(raw_path)}</code><span class="type">{meta}</span>'
            f'<span class="ingest-pending-actions">{actions}</span></li>'
        )
    if len(pending) > 50:
        rows += f'<li>… 還有 {len(pending) - 50} 筆</li>'
    return '<div class="section-heading"><h2>待處理的 Raw 檔案</h2><a href="/propose">草擬記憶</a></div><ul class="page-list">' + rows + "</ul>"


def _render_notes(notes: list[object]) -> str:
    return "<ul>" + "".join(f"<li>{html.escape(str(note))}</li>" for note in notes) + "</ul>" if notes else ""


def _render_source_warnings(source_warnings: list[dict[str, object]]) -> str:
    if not source_warnings:
        return ""
    rows = "".join(
        f'<li><code>{html.escape(str(item.get("page") or ""))}</code>'
        f'<span class="type">無法檢查：{html.escape(str(item.get("error") or ""))}</span></li>'
        for item in source_warnings[:50]
    )
    return f'<h2>來源頁面警告</h2><ul class="page-list">{rows}</ul>'


def _render_plan(plan: Mapping[str, object]) -> str:
    if not plan:
        return ""
    steps = _list(status_value=plan.get("steps"))
    batch = _dict_list(plan.get("batch"))
    post_checks = _list(status_value=plan.get("post_checks"))
    step_html = "".join(f"<li>{html.escape(str(step))}</li>" for step in steps[:6])
    batch_html = ""
    if batch:
        rows = "".join(
            f'<li><code>{html.escape(str(item.get("raw") or ""))}</code>'
            f'<span class="type">{html.escape(str(item.get("target_source_page") or item.get("suggested_source_page") or ""))}</span></li>'
            for item in batch[:5]
        )
        batch_html = f'<h3>批次</h3><ul class="page-list">{rows}</ul>'
    checks_html = ""
    if post_checks:
        rows = "".join(
            f'<li><code>{html.escape(str(check))}</code>'
            f'<span class="type">回報完成前先執行 {copy_button(check)}</span></li>'
            for check in post_checks[:6]
        )
        checks_html = f'<h3>匯入後檢查</h3><ul class="page-list">{rows}</ul>'
    return (
        f'<section><h2>{html.escape(str(plan.get("title") or "建議工作流程"))}</h2>'
        f'<p class="summary">{html.escape(str(plan.get("summary") or ""))}</p>'
        f'<ol>{step_html}</ol>{batch_html}{checks_html}</section>'
    )


def _render_completion(completion: Mapping[str, object], *, page_href: PageHref) -> str:
    completion_items = _dict_list(completion.get("items"))
    if not completion_items:
        return ""
    cards = ""
    for item in completion_items:
        raw_path = str(item.get("raw") or "")
        pages = _dict_list(item.get("source_pages"))
        page_links = ""
        for page in pages:
            page_name = str(page.get("name") or "")
            page_title = str(page.get("title") or page_name)
            if not page_name:
                continue
            page_links += (
                f'<a href="{html.escape(page_href(page_name), quote=True)}" '
                f'title="{html.escape(str(page.get("path") or ""), quote=True)}">{html.escape(page_title)}</a>'
            )
        if not page_links:
            page_links = '<span class="type">找不到來源頁面</span>'
        warnings = _list(status_value=item.get("secret_warnings"))
        warning_html = ""
        if warnings:
            warning_html = (
                '<p class="proposal-warning">Raw 警告：'
                + ", ".join(html.escape(str(label)) for label in warnings)
                + "</p>"
            )
        propose_link = "/propose?source=" + urllib.parse.quote(raw_path) if raw_path else "/propose"
        cards += (
            '<article class="ingest-completion-card">'
            f'<h3>{html.escape(raw_path)}</h3>'
            f'<p>{int(item.get("size_bytes") or 0)} bytes，由以下頁面代表：</p>'
            f'<div class="ingest-completion-pages">{page_links}</div>'
            f'{warning_html}'
            '<div class="ingest-completion-actions">'
            f'<a href="{html.escape(propose_link, quote=True)}">草擬記憶</a>'
            f'{copy_button(str(item.get("memory_prompt") or ""), "複製記憶提示詞")}'
            f'{copy_button(str(item.get("query_prompt") or ""), "複製查詢提示詞")}'
            '</div>'
            '</article>'
        )
    more_html = ""
    if completion.get("has_more"):
        more_html = f'<p class="summary">目前顯示 {int(completion.get("represented_count") or 0)} 份已代表來源中的 {int(completion.get("shown_count") or 0)} 份。</p>'
    next_prompt = str(completion.get("next_prompt") or "")
    next_html_for_completion = ""
    if next_prompt:
        next_html_for_completion = (
            '<div class="memory-next"><strong>匯入之後</strong>'
            '<p>在繼續之前，先用這個確認新的脈絡可以被取回。</p>'
            f'<code>{html.escape(next_prompt)}</code>{copy_button(next_prompt, "複製提示詞")}</div>'
        )
    return (
        f'<section><div class="section-heading"><h2>{html.escape(str(completion.get("title") or "匯入完成情形"))}</h2>'
        '<a href="/all">所有頁面</a></div>'
        f'<p class="summary">{html.escape(str(completion.get("summary") or ""))}</p>'
        f'<div class="ingest-completion-grid">{cards}</div>{more_html}{next_html_for_completion}</section>'
    )


def _render_raw_source_form() -> str:
    return (
        '<section><div class="section-heading"><h2>新增 Raw 來源</h2><a href="/propose">記憶提案</a></div>'
        '<p class="summary">貼上一份筆記、文章摘錄、逐字稿或專案脈絡。BrainHub 會把它存到本機的 '
        '<code>raw/</code>，擋下疑似機密的內容，並給你可直接使用的匯入提示詞。</p>'
        '<form class="raw-source-form" data-raw-source-form>'
        '<div class="raw-source-controls">'
        '<label>標題<input name="title" autocomplete="off" placeholder="發布說明、會議逐字稿、專案脈絡"></label>'
        '<label>檔名（選填）<input name="filename" autocomplete="off" placeholder="release-notes.md"></label>'
        '</div>'
        '<label>來源文字<textarea name="text" placeholder="貼上要在匯入前先保存到本機的來源文字。"></textarea></label>'
        '<div class="raw-source-actions"><button type="submit">儲存到 raw/</button>'
        '<span>在你核可記憶提案之前，不會有任何內容變成長期記憶。</span></div>'
        '<div class="raw-source-status" data-raw-source-status aria-live="polite"></div>'
        '</form></section>'
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _list(*, status_value: object) -> list[object]:
    return list(status_value) if isinstance(status_value, list) else []


def _dict_list(value: object) -> list[dict[str, object]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
