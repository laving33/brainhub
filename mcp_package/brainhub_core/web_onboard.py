"""HTML helpers for BrainHub's local onboarding page."""
from __future__ import annotations

import html
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from .mcp_verify import display_command
from .web_ingest import copy_button
from .web_layout import render_stat_grid


PageLayout = Callable[[str, str], str]


def _command_target(wiki_dir: object, fallback: object) -> str:
    raw = str(wiki_dir or fallback or "").strip()
    if not raw:
        return ""
    path = Path(raw)
    return str(path.parent if path.name == "wiki" else path)


def _command_row(command: str, label: str = "複製") -> str:
    return (
        "<li>"
        f"{copy_button(command, label)}"
        f"<code>{html.escape(command)}</code>"
        "</li>"
    )


def _agent_cards(target: str, agents: Sequence[str]) -> str:
    cards = ""
    for agent in agents:
        preview = display_command(["bh", "onboard", target, "--agent", agent])
        write = display_command(["bh", "onboard", target, "--agent", agent, "--write"])
        cards += (
            '<article class="onboard-agent-card">'
            f"<h3>{html.escape(agent)}</h3>"
            "<p>先預覽。等準備好要更新該 agent 設定時再寫入。</p>"
            '<ul class="command-list">'
            f"{_command_row(preview, '複製預覽')}"
            f"{_command_row(write, '複製寫入')}"
            "</ul>"
            "</article>"
        )
    return cards


def _prompt_cards(prompts: object) -> str:
    rows = ""
    prompt_items = prompts if isinstance(prompts, list) else []
    for item in prompt_items:
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or "")
        when = str(item.get("when") or "")
        label = str(item.get("label") or "提示詞")
        rows += (
            '<article class="proposal-card">'
            f"<h3>{html.escape(label)}</h3>"
            f"{copy_button(prompt, '複製提示詞')}"
            f'<code class="proposal-command">{html.escape(prompt)}</code>'
            f'<p class="summary">{html.escape(when)}</p>'
            "</article>"
        )
    return rows


def render_onboard_page(
    status: Mapping[str, object],
    operations: Mapping[str, object],
    starter_prompts: Mapping[str, object],
    *,
    target: str,
    agents: Sequence[str],
    layout: PageLayout,
) -> str:
    """Render a guided first-run page for humans setting up BrainHub with agents."""
    command_target = target or _command_target(status.get("wiki"), operations.get("wiki"))
    ready = bool(status.get("ready"))
    validation = status.get("validation") if isinstance(status.get("validation"), Mapping) else {}
    validation_label = "已通過" if validation.get("passed") else ("未通過" if validation.get("checked") else "尚未檢查")
    health_command = display_command(["bh", "health", command_target])
    onboard_command = display_command(["bh", "onboard", command_target])
    seed_onboard_command = display_command(["bh", "onboard", command_target, "--seed-project", "."])
    seed_command = display_command(["bh", "seed", ".", command_target])
    first_memory_command = display_command([
        "link",
        "onboard",
        command_target,
        "--first-memory",
        "I prefer concise release notes",
    ])
    brief_command = display_command(["bh", "brief", "working with BrainHub", command_target])
    ingest_command = display_command(["bh", "ingest-status", command_target])
    memory_inbox_command = display_command(["bh", "memory-inbox", command_target])

    stats = render_stat_grid([
        ("是" if ready else "否", "就緒"),
        (status.get("content_page_count", 0), "內容頁面"),
        (status.get("memory_count", 0), "記憶"),
        (status.get("needs_review_count", 0), "待審核"),
        (validation_label, "驗證"),
    ])
    setup_cards = (
        '<section class="onboard-steps" aria-label="BrainHub 上手步驟">'
        '<article class="onboard-step" data-state="done"><span>1</span><h2>檢查就緒狀態</h2>'
        '<p>在信任回想結果之前，先確認 wiki 可用。</p>'
        f'<ul class="command-list">{_command_row(health_command)}</ul></article>'
        '<article class="onboard-step" data-state="next"><span>2</span><h2>種入這個專案</h2>'
        '<p>在 repo 裡執行，讓第一次回想就認得這個專案。這只會寫入有來源依據的脈絡，不是長期記憶。</p>'
        f'<ul class="command-list">{_command_row(seed_onboard_command)}{_command_row(seed_command)}</ul></article>'
        '<article class="onboard-step" data-state="next"><span>3</span><h2>種入一則記憶</h2>'
        '<p>從一個明確的偏好或決策開始。BrainHub 會存起來等待審核。</p>'
        f'<ul class="command-list">{_command_row(first_memory_command)}</ul></article>'
        '<article class="onboard-step" data-state="next"><span>4</span><h2>連接 agent</h2>'
        '<p>MCP 與 CLI 不需要 viewer 執行也能運作。viewer 只是本機的檢視介面。</p>'
        f'<ul class="command-list">{_command_row(onboard_command)}</ul></article>'
        '<article class="onboard-step" data-state="next"><span>5</span><h2>開始循環</h2>'
        '<p>開工前先看簡報、匯入來源，再審核哪些內容該變成長期記憶。</p>'
        f'<ul class="command-list">{_command_row(brief_command)}{_command_row(ingest_command)}{_command_row(memory_inbox_command)}</ul></article>'
        "</section>"
    )
    agent_cards = _agent_cards(command_target, agents)
    prompt_cards = _prompt_cards(starter_prompts.get("prompts"))
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 上手引導</div>'
        "<h1>上手引導</h1>"
        '<p class="summary">首次設定的本機檢查清單：健康度、專案脈絡、第一則記憶、agent 連接，以及每日提示詞循環。</p>'
        f"{stats}"
        f"{setup_cards}"
        '<section><div class="section-heading"><h2>Agent 連接</h2><a href="/prompts">入門提示詞</a></div>'
        '<p class="summary">預覽指令是安全的。只有想更新 agent 設定時才加上 <code>--write</code>。</p>'
        f'<div class="onboard-agent-grid">{agent_cards}</div></section>'
        '<section><h2>先問你的 agent</h2>'
        '<p class="summary">這些提示詞能讓 BrainHub 自動生效，同時不會隱藏任何變更。</p>'
        f'<div class="proposal-results">{prompt_cards}</div></section>'
    )
    return layout("上手引導", body)
