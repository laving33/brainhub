"""HTML helpers for BrainHub's local health page."""
from __future__ import annotations

import html
from collections.abc import Callable, Mapping
from pathlib import Path

from .mcp_verify import display_command
from .web_ingest import copy_button
from .web_layout import render_stat_grid


PageLayout = Callable[[str, str], str]


def _dict_list(value: object) -> list[dict[str, object]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _render_issue_list(title: str, items: list[dict[str, object]], empty: str) -> str:
    if not items:
        return f"<section><h2>{html.escape(title)}</h2><p>{html.escape(empty)}</p></section>"
    rows = ""
    for item in items:
        code = str(item.get("code") or item.get("operation") or item.get("label") or "issue")
        message = str(item.get("message") or item.get("description") or item.get("detail") or item.get("command") or "")
        detail = str(item.get("detail") or item.get("marker") or item.get("tool") or "").strip()
        rows += (
            "<li>"
            f"<strong>{html.escape(code)}</strong>"
            f"<span>{html.escape(message)}</span>"
            f"{f'<code>{html.escape(detail)}</code>' if detail else ''}"
            "</li>"
        )
    return f'<section><h2>{html.escape(title)}</h2><ul class="page-list">{rows}</ul></section>'


def _render_commands(commands: list[str]) -> str:
    rows = "".join(
        "<li>"
        f"<code>{html.escape(command)}</code>"
        f"{copy_button(command, '複製')}"
        "</li>"
        for command in commands
    )
    return f'<section><h2>修復指令</h2><ul class="command-list">{rows}</ul></section>'


def _render_operation_actions(operations: Mapping[str, object]) -> str:
    actions = _dict_list(operations.get("next_actions"))
    if not actions:
        return ""
    rows = ""
    for action in actions:
        command = str(action.get("command") or "").strip()
        label = str(action.get("label") or command or "下一步")
        command_html = f"<code>{html.escape(command)}</code>{copy_button(command, '複製')}" if command else ""
        rows += (
            "<li>"
            f"<strong>{html.escape(label)}</strong>"
            f"{command_html}"
            "</li>"
        )
    return f'<section><h2>操作的下一步</h2><ul class="command-list">{rows}</ul></section>'


def _command_target(status: Mapping[str, object], operations: Mapping[str, object]) -> str:
    raw = str(operations.get("wiki") or status.get("wiki") or "").strip()
    if not raw:
        return ""
    path = Path(raw)
    return str(path.parent if path.name == "wiki" else path)


def _link_command(command_target: str, *parts: str) -> str:
    command = ["link", *parts]
    if command_target:
        command.append(command_target)
    return display_command(command)


def _render_persistent_cache_item(status: Mapping[str, object]) -> str:
    persistent_cache = status.get("persistent_cache")
    if not isinstance(persistent_cache, Mapping):
        return ""
    state = "已啟用" if persistent_cache.get("enabled") else "未啟用"
    detail = (
        f"重複使用 {persistent_cache.get('reused_records', 0)}/"
        f"{persistent_cache.get('total_records', 0)} 個頁面"
    )
    return (
        "<li><strong>持久化快取</strong>"
        f"<span>{html.escape(state)}</span>"
        f"<small>{html.escape(detail)}</small></li>"
    )


def _render_fts_item(status: Mapping[str, object]) -> str:
    fts_index = status.get("fts_index")
    if not isinstance(fts_index, Mapping) or not fts_index.get("available"):
        return ""
    state = "持久化" if fts_index.get("persistent") else "記憶體"
    detail = f"reused={bool(fts_index.get('reused'))}"
    return (
        "<li><strong>全文檢索索引</strong>"
        f"<span>{html.escape(state)}</span>"
        f"<small>{html.escape(detail)}</small></li>"
    )


def _command_for_action(action: Mapping[str, object], command_target: str) -> str:
    command = str(action.get("command") or "").strip()
    if command:
        return command
    tool = str(action.get("tool") or "").strip()
    arguments = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
    if tool == "doctor":
        return _link_command(command_target, "doctor", "--fix") if arguments.get("fix") else _link_command(
            command_target, "doctor"
        )
    if tool == "validate_wiki":
        return _link_command(command_target, "validate")
    if tool == "rebuild_backlinks":
        return _link_command(command_target, "rebuild-backlinks")
    if tool == "migrate_wiki":
        return _link_command(command_target, "migrate")
    if tool == "ingest_status":
        return _link_command(command_target, "ingest-status")
    if tool == "starter_prompts":
        return _link_command(command_target, "prompts")
    if tool == "memory_inbox":
        return _link_command(command_target, "memory-inbox")
    if tool == "backup_wiki":
        return _link_command(command_target, "backup")
    if tool == "query_link":
        query = str(arguments.get("query") or "").strip()
        if not query or query == "<user task>":
            query = "what should I know before continuing?"
        return _link_command(command_target, "query", query)
    if tool == "memory_brief":
        query = str(arguments.get("query") or "").strip()
        if not query or query == "<user task>":
            query = "working with BrainHub"
        return _link_command(command_target, "brief", query)
    return ""


def _render_primary_next_action(status: Mapping[str, object], operations: Mapping[str, object]) -> str:
    command_target = _command_target(status, operations)
    operation_actions = _dict_list(operations.get("next_actions"))
    status_actions = _dict_list(status.get("next_actions"))
    if operation_actions:
        action = operation_actions[0]
        label = str(action.get("label") or "檢視中斷的操作")
        detail = "在做更多修復之前，應該先檢查中斷的寫入。"
    elif status_actions:
        action = status_actions[0]
        label = str(action.get("label") or action.get("tool") or "執行下一項健康檢查")
        detail = str(action.get("description") or action.get("detail") or "在信任 BrainHub 之前，先執行這一步。")
    elif int(status.get("needs_review_count") or 0):
        action = {"tool": "memory_inbox"}
        label = "審核待處理的記憶"
        detail = "確認或封存那些暫時不該影響回想結果的記憶。"
    else:
        action = {"tool": "memory_brief", "arguments": {"query": "working with BrainHub"}}
        label = "可以開始 agent 工作了"
        detail = "用簡報或查詢 BrainHub 取得專案脈絡，讓 agent 先熱身。"
    command = _command_for_action(action, command_target)
    command_html = f"<code>{html.escape(command)}</code>{copy_button(command, '複製')}" if command else ""
    return (
        '<section class="health-next">'
        "<h2>下一個安全動作</h2>"
        f"<p><strong>{html.escape(label)}</strong><span>{html.escape(detail)}</span></p>"
        f"{command_html}"
        "</section>"
    )


def _render_validation_details(validation: Mapping[str, object]) -> str:
    if not validation.get("checked"):
        return "<section><h2>驗證關卡</h2><p>這次健康檢查還沒有執行驗證。</p></section>"
    error_codes = [str(code) for code in validation.get("error_codes") or [] if str(code)]
    warning_codes = [str(code) for code in validation.get("warning_codes") or [] if str(code)]
    if not error_codes and not warning_codes:
        return "<section><h2>驗證關卡</h2><p>驗證通過，沒有錯誤或警告。</p></section>"
    rows = "".join(
        f"<li><strong>{html.escape(kind)}</strong><span>{html.escape(', '.join(codes))}</span></li>"
        for kind, codes in (("錯誤", error_codes), ("警告", warning_codes))
        if codes
    )
    return f'<section><h2>驗證關卡</h2><ul class="page-list">{rows}</ul></section>'


def _render_decision_invariant(violations: list[str]) -> str:
    """The decision-board invariant, stated on the page whether or not it holds.

    A check that only prints when it fails is indistinguishable from a check
    nobody wired up, so the healthy case says so out loud.
    """
    if not violations:
        return (
            "<section><h2>決策板不變式</h2>"
            "<p>沒有「已標記完成、卻留著空白決定」的批次。</p></section>"
        )
    rows = "".join(f"<li><span>{html.escape(line)}</span></li>" for line in violations)
    return (
        "<section><h2>決策板不變式</h2>"
        f"<p>{len(violations)} 批違規：status 是 decided，但裡面還有項目沒有 decision。"
        "空白跟「刻意略過」長得一模一樣，讀的人分不出來。</p>"
        f'<ul class="page-list">{rows}</ul></section>'
    )


def _render_health_cards(
    status: Mapping[str, object],
    operations: Mapping[str, object],
    decision_violations: list[str] | None = None,
) -> str:
    validation = status.get("validation") if isinstance(status.get("validation"), dict) else {}
    ready_state = "done" if status.get("ready") else "blocked"
    validation_checked = bool(validation.get("checked"))
    validation_passed = bool(validation.get("passed"))
    validation_state = "done" if validation_checked and validation_passed else ("blocked" if validation_checked else "wait")
    stale_count = int(operations.get("stale_count") or 0)
    failed_count = int(operations.get("failed_count") or 0)
    active_count = int(operations.get("active_count") or 0)
    operations_state = "blocked" if stale_count or failed_count else ("next" if active_count else "done")
    needs_review_count = int(status.get("needs_review_count") or 0)
    memory_state = "next" if needs_review_count else "done"
    decision_count = len(decision_violations or ())
    validation_detail = (
        f"{int(validation.get('error_count') or 0)} 個錯誤 · {int(validation.get('warning_count') or 0)} 個警告"
        if validation_checked
        else "執行 bh health"
    )
    cards = [
        (
            "就緒狀態",
            "就緒" if status.get("ready") else "需要處理",
            ready_state,
            f"{status.get('content_page_count', 0)} 個內容頁面",
        ),
        (
            "驗證",
            "已通過" if validation_passed else ("未通過" if validation_checked else "尚未檢查"),
            validation_state,
            validation_detail,
        ),
        (
            "操作",
            "正常" if operations_state == "done" else ("進行中" if operations_state == "next" else "需要檢視"),
            operations_state,
            f"{stale_count} 個過期 · {active_count} 個進行中",
        ),
        (
            "記憶審核",
            "正常" if not needs_review_count else f"{needs_review_count} 筆待處理",
            memory_state,
            f"{status.get('active_memory_count', 0)} 則使用中的記憶",
        ),
        (
            "決策板",
            "正常" if not decision_count else f"{decision_count} 批違規",
            "done" if not decision_count else "blocked",
            "已完成的批次沒有留空白" if not decision_count else "已完成卻留著沒決定的項目",
        ),
    ]
    rows = "".join(
        '<article class="health-card" data-state="'
        f'{html.escape(state, quote=True)}">'
        f"<strong>{html.escape(label)}</strong>"
        f"<span>{html.escape(value)}</span>"
        f"<small>{html.escape(detail)}</small>"
        "</article>"
        for label, value, state, detail in cards
    )
    return f'<section class="health-cards" aria-label="健康度總覽">{rows}</section>'


def render_health_page(
    status: Mapping[str, object],
    operations: Mapping[str, object],
    *,
    layout: PageLayout,
    decision_violations: list[str] | None = None,
) -> str:
    """Render a human-readable health and readiness page for the local viewer."""
    validation = status.get("validation") if isinstance(status.get("validation"), dict) else {}
    schema = status.get("schema") if isinstance(status.get("schema"), dict) else {}
    ready = "是" if status.get("ready") else "否"
    validation_label = "已通過" if validation.get("passed") else "尚未檢查"
    if validation.get("checked") and not validation.get("passed"):
        validation_label = "未通過"
    stats = render_stat_grid([
        (ready, "就緒"),
        (status.get("content_page_count", 0), "內容頁面"),
        (status.get("memory_count", 0), "記憶"),
        (status.get("needs_review_count", 0), "待審核"),
        (operations.get("operation_count", 0), "操作"),
        (validation_label, "驗證"),
    ])
    warnings = _dict_list(status.get("warnings"))
    next_actions = _dict_list(status.get("next_actions"))
    operation_items = _dict_list(operations.get("operations"))
    command_target = _command_target(status, operations)
    commands = [
        _link_command(command_target, "status", "--validate"),
        _link_command(command_target, "onboard"),
        _link_command(command_target, "operations"),
        _link_command(command_target, "doctor", "--fix"),
        _link_command(command_target, "validate"),
        _link_command(command_target, "benchmark", "agent memory"),
    ]
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 健康度</div>'
        "<h1>健康度</h1>"
        '<p class="summary">一次看完就緒狀態、驗證結果、中斷的寫入，以及修復指令。</p>'
        f"{_render_health_cards(status, operations, decision_violations)}"
        f"{_render_primary_next_action(status, operations)}"
        f"{stats}"
        "<section><h2>就緒狀態</h2>"
        '<ul class="page-list">'
        f"<li><strong>搜尋後端</strong><span>{html.escape(str(status.get('search_backend') or 'unknown'))}</span></li>"
        f"{_render_fts_item(status)}"
        f"{_render_persistent_cache_item(status)}"
        f"<li><strong>Schema</strong><span>{html.escape(str(schema.get('status') or 'unknown'))}</span></li>"
        f"<li><strong>使用中的記憶</strong><span>{html.escape(str(status.get('active_memory_count') or 0))}</span></li>"
        f"<li><strong>中斷的操作</strong><span>{html.escape(str(operations.get('stale_count') or 0))} 個過期 · {html.escape(str(operations.get('active_count') or 0))} 個進行中</span></li>"
        "</ul></section>"
        f"{_render_validation_details(validation)}"
        f"{_render_decision_invariant(list(decision_violations or ()))}"
        f"{_render_issue_list('警告', warnings, '目前沒有就緒警告。')}"
        f"{_render_issue_list('中斷的操作', operation_items, '沒有待處理、失敗或中斷的 BrainHub 操作。')}"
        f"{_render_operation_actions(operations)}"
        f"{_render_issue_list('下一步', next_actions, '目前不需要修復動作。')}"
        f"{_render_commands(commands)}"
    )
    return layout("健康度", body)
