"""HTML helpers for BrainHub starter prompt pages."""
from __future__ import annotations

import html
from collections.abc import Callable, Mapping

from .web_ingest import copy_button


PageLayout = Callable[[str, str], str]


def render_prompts_page(payload: Mapping[str, object], *, layout: PageLayout) -> str:
    prompt_rows = ""
    for item in payload.get("prompts", []):
        if not isinstance(item, dict):
            continue
        prompt_rows += (
            '<article class="proposal-card">'
            f'<h3>{html.escape(str(item.get("label") or "提示詞"))}</h3>'
            f'{copy_button(item.get("prompt") or "", "複製提示詞")}'
            f'<code class="proposal-command">{html.escape(str(item.get("prompt") or ""))}</code>'
            f'<p class="summary">{html.escape(str(item.get("when") or ""))}</p>'
            "</article>"
        )
    command_rows = "".join(
        f"<li>{copy_button(command, '複製指令')}<code>{html.escape(str(command))}</code></li>"
        for command in payload.get("commands", [])
    )
    project_line = (
        f'<p class="summary">以下範例僅限於專案 <code>{html.escape(str(payload["project"]))}</code>。</p>'
        if payload.get("project")
        else '<p class="summary">這些提示詞適用於個人 BrainHub wiki。加上 <code>?project=slug</code> 可取得專案專屬版本。</p>'
    )
    shortcut = str(payload.get("shortcut") or "")
    shortcut_block = (
        '<section class="callout">'
        "<h2>一鍵指令</h2>"
        "<p>忘記接下來該問什麼時，隨時可以用這個。</p>"
        f'{copy_button(shortcut, "複製指令")}'
        f'<code class="proposal-command">{html.escape(shortcut)}</code>'
        "</section>"
        if shortcut
        else ""
    )
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 提示詞</div>'
        "<h1>入門提示詞</h1>"
        f"{project_line}"
        f"{shortcut_block}"
        f'<section><h2>詢問你的 Agent</h2><div class="proposal-results">{prompt_rows}</div></section>'
        f'<section><h2>本機檢查</h2><ul class="page-list">{command_rows}</ul></section>'
    )
    return layout("入門提示詞", body)
