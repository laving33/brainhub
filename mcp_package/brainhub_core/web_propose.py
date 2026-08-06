"""HTML renderer for BrainHub's memory proposal page."""
from __future__ import annotations

import html
from collections.abc import Callable

from .web_ingest import copy_button


PageLayout = Callable[[str, str], str]


def render_propose_page(project: str = "", source: str = "", *, layout: PageLayout) -> str:
    body = (
        '<div class="breadcrumb"><a href="/">BrainHub</a> / 草擬記憶</div>'
        '<h1>草擬記憶</h1>'
        '<p class="summary">貼上來源筆記、工作階段筆記或 raw 摘錄。BrainHub 會回傳記憶候選，但不會寫入任何內容。</p>'
        '<div class="memory-next"><strong>信任原則</strong>'
        '<p>有來源依據的 wiki 知識，和長期 agent 記憶是兩回事。只儲存你核可的偏好、決策或專案事實。</p></div>'
        '<section><h2>審核關卡</h2><div class="proposal-checklist">'
        '<strong>儲存記憶之前</strong>'
        '<span>一般事實留在 wiki 頁面就好；只儲存長期的偏好、決策、專案脈絡或使用者事實。</span>'
        '<span>檢查來源標籤、範圍、專案、重複候選與衝突警告。</span>'
        '<span>只有在提案很乾淨時才直接核可；否則請把核可提示詞複製到你的 agent 對話中。</span>'
        '</div></section>'
        f'{_render_proposal_path()}'
        f'{_render_after_approval()}'
        '<section><div class="section-heading"><h2>本機 Raw 來源</h2><a href="/captures">擷取紀錄</a></div>'
        '<div class="proposal-source-list" data-proposal-sources aria-live="polite"></div></section>'
        f'<form class="proposal-form" data-proposal-form data-initial-source="{html.escape(source, quote=True)}">'
        '<label>來源或工作階段筆記'
        '<textarea name="text" placeholder="在這裡貼上筆記。範例：我偏好簡短的發布說明。我們決定讓 BrainHub 保持本機優先。"></textarea>'
        '</label>'
        '<div class="proposal-controls">'
        '<label>來源標籤<input name="source" value="web proposal" autocomplete="off"></label>'
        f'<label>專案<input name="project" value="{html.escape(project, quote=True)}" placeholder="選填" autocomplete="off"></label>'
        '<label>上限<input name="limit" type="number" min="1" max="20" value="10"></label>'
        '<button type="submit">草擬</button>'
        '</div>'
        '<div class="proposal-status" data-proposal-status aria-live="polite"></div>'
        '</form>'
        '<section class="proposal-results" data-proposal-results aria-live="polite"></section>'
    )
    return layout("草擬記憶", body)


def _render_proposal_path() -> str:
    return (
        '<section class="ingest-path" aria-label="記憶提案流程">'
        '<article class="ingest-step"><span class="step-num">1</span>'
        '<h3>載入來源</h3><p>貼上筆記，或載入一份安全的本機 raw 檔案。來源會留在本機。</p>'
        '<code>raw/file.md</code></article>'
        '<article class="ingest-step"><span class="step-num">2</span>'
        '<h3>草擬</h3><p>BrainHub 只會回傳候選內容，這一步永遠不會寫入長期記憶。</p>'
        '<code>草擬</code></article>'
        '<article class="ingest-step"><span class="step-num">3</span>'
        '<h3>明確核可</h3><p>只針對你想保留的記憶，把核可提示詞複製到 agent 對話中。</p>'
        '<code>remember that ...</code></article>'
        '<article class="ingest-step"><span class="step-num">4</span>'
        '<h3>之後再審</h3><p>用待審清單與說明檢視畫面來審核、封存、更新或刪除記憶。</p>'
        '<code>bh memory-inbox</code></article>'
        '</section>'
    )


def _render_after_approval() -> str:
    return (
        '<section><h2>核可之後</h2>'
        '<div class="memory-next"><strong>保持記憶可審核</strong>'
        '<p>已儲存的記憶在審核前都維持待審狀態。用待審清單確認、說明、封存、更新或刪除它們。</p>'
        '<div class="page-actions">'
        '<a class="button-link" href="/inbox">開啟記憶待審清單</a>'
        '<a class="button-link" href="/audit">開啟記憶稽核</a>'
        f'{copy_button("先跟 BrainHub 對一下，我們再繼續", "複製簡報提示詞")}'
        f'{copy_button("跟 BrainHub 查詢你記得關於這件事的內容", "複製查詢提示詞")}'
        '</div></div></section>'
    )
