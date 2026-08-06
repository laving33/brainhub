"""Shared HTML shell for the local BrainHub web UI."""
from __future__ import annotations

import html
from collections.abc import Sequence

from .render import LOGO_SVG
from .ui_classes import (
    FOOTER,
    NAV_LINK,
    NAV_MENU,
    NAV_MORE_MENU,
    NAV_MORE_SUMMARY,
    NAVBAR,
    SEARCH_INPUT,
)
from .web_assets import (
    BRAND_THEME_CSS,
    COPY_BUTTON_JS,
    CSS,
    DAISY_CSS,
    MEMORY_ACTION_JS,
    PROPOSAL_UI_JS,
    RAW_SOURCE_JS,
    THEME_CONTROL_JS,
    THEME_INIT_JS,
)


KEYBOARD_NAV_JS = """
// Keyboard navigation
document.addEventListener('keydown', function(e) {
  var tag = document.activeElement.tagName;
  var inInput = tag === 'INPUT' || tag === 'TEXTAREA';
  // / -> focus search
  if (e.key === '/' && !inInput) {
    e.preventDefault();
    var inp = document.getElementById('search-input');
    if (inp) { inp.focus(); inp.select(); }
  }
  // Escape -> blur search
  if (e.key === 'Escape' && inInput) {
    document.activeElement.blur();
  }
  if (e.key === 'Enter' && document.activeElement.id === 'search-input') {
    var q = document.activeElement.value.trim();
    if (q) {
      e.preventDefault();
      window.location.href = '/search?q=' + encodeURIComponent(q);
    }
  }
  // j/k -> navigate focusable links in page-list
  if ((e.key === 'j' || e.key === 'k') && !inInput) {
    var links = Array.from(document.querySelectorAll('.page-list a, .search-results a'));
    if (!links.length) return;
    var cur = document.activeElement;
    var idx = links.indexOf(cur);
    if (e.key === 'j') idx = idx < links.length - 1 ? idx + 1 : 0;
    else idx = idx > 0 ? idx - 1 : links.length - 1;
    links[idx].focus();
    e.preventDefault();
  }
});
"""

NAV_CURRENT_JS = """
// Mark the active local navigation item.
(function() {
  function cleanPath(path) {
    if (!path) return '/';
    path = path.split('?')[0].split('#')[0];
    if (path.length > 1) path = path.replace(/\\/+$/, '');
    return path || '/';
  }
  var current = cleanPath(window.location.pathname);
  var active = null;
  document.querySelectorAll('header nav a[href]').forEach(function(link) {
    var href = link.getAttribute('href') || '';
    if (!href || href.indexOf('http') === 0) return;
    var target = cleanPath(new URL(href, window.location.origin).pathname);
    if (target === current) active = link;
  });
  if (!active && current.indexOf('/page/') === 0) {
    active = document.querySelector('header nav a[href="/all"]');
  }
  if (!active) return;
  active.setAttribute('aria-current', 'page');
  var more = active.closest('.nav-more');
  if (more) {
    var summary = more.querySelector('summary');
    if (summary) summary.setAttribute('aria-current', 'page');
  }
})();
"""


def render_header_html(memory_enabled: bool = True, populated: bool = False) -> str:
    """The shell header.

    ``populated`` demotes the setup-only entries. "上手引導" and "匯入" are the
    first two things a new install needs and the two nobody touches afterwards,
    but they sat in the top row forever, spending prime nav space on a job that
    is finished. They move into 更多 once the workspace has content.

    The signal is the SAME one the home page branches on (web_home's page-count
    threshold), deliberately rather than a second hand-maintained list: two
    rules answering "is this workspace set up yet?" will disagree eventually,
    and the one that drifts is the one nobody is looking at. An install that
    stays small keeps the tour in the top row, which is right for it.
    """
    logo = f'<span class="logo-mark" aria-hidden="true">{LOGO_SVG}</span>' if LOGO_SVG else "BrainHub"
    setup_nav = "" if populated else f"""
    <a class="{NAV_LINK}" href="/onboard">上手引導</a>
    <a class="{NAV_LINK}" href="/ingest">匯入</a>"""
    setup_more = f"""
        <a href="/onboard">上手引導</a>
        <a href="/ingest">匯入</a>""" if populated else ""
    memory_nav = f"""
    <a class="{NAV_LINK}" href="/brief">記憶簡報</a>
    <a class="{NAV_LINK}" href="/memory">記憶</a>""" if memory_enabled else ""
    memory_more = """
        <a href="/propose">草擬記憶</a>
        <a href="/audit">稽核</a>
        <a href="/inbox">待審清單</a>
        <a href="/captures">擷取紀錄</a>
        <a href="/profile">記憶總覽</a>
        <a href="/wins">成效</a>
        <a href="/memory-log">記憶異動紀錄</a>""" if memory_enabled else ""
    return f"""<header>
  <div class="header-top {NAVBAR}">
    <div class="logo"><a href="/" aria-label="BrainHub 首頁">{logo}</a></div>
    <div class="header-tools">
      <button type="button" class="theme-toggle" data-theme-toggle>
        <span class="theme-icon" aria-hidden="true"></span><span class="theme-text" data-theme-text>系統</span>
      </button>
      <form action="/search" method="get">
        <input type="text" class="{SEARCH_INPUT}" name="q" placeholder="搜尋…（/）" autocomplete="off" id="search-input" aria-label="搜尋 BrainHub">
      </form>
    </div>
  </div>
  <nav class="{NAV_MENU}" aria-label="BrainHub 主選單">
    <a class="{NAV_LINK}" href="/">首頁</a>{setup_nav}{memory_nav}
    <a class="{NAV_LINK}" href="/graph">知識圖譜</a>
    <a class="{NAV_LINK}" href="/artifacts">產出</a>
    <a class="{NAV_LINK}" href="/documents">文件</a>
    <a class="{NAV_LINK}" href="/health">健康度</a>
    <details class="nav-more">
      <summary class="{NAV_MORE_SUMMARY}">更多</summary>
      <div class="nav-more-menu {NAV_MORE_MENU}">{setup_more}
        <a href="/prompts">提示詞</a>{memory_more}
        <a href="/page/log">操作紀錄</a>
        <a href="/all">所有頁面</a>
      </div>
    </details>
  </nav>
</header>"""


def render_footer_html() -> str:
    return f'<footer class="{FOOTER}">BrainHub — 內部 LLM wiki + 記憶 + artifact</footer>'


def render_stat_grid(items: Sequence[tuple[object, str]]) -> str:
    """Render BrainHub's compact stat grid."""
    def _num_class(value: object, label: str) -> str:
        # Attention counts (pending review) render in accent when non-zero.
        try:
            pending = int(str(value)) > 0
        except (TypeError, ValueError):
            pending = False
        return "num num--alert" if pending and "review" in label.lower() else "num"

    stats = "".join(
        f'<div class="stat-item"><span class="{_num_class(value, label)}">{html.escape(str(value))}</span>'
        f'<span class="label">{html.escape(label)}</span></div>'
        for value, label in items
    )
    return f'<div class="home-stats">{stats}</div>'


def render_layout(
    title: str,
    body: str,
    page_class: str = "",
    memory_enabled: bool = True,
    populated: bool = False,
) -> str:
    body_class = f' class="{html.escape(page_class, quote=True)}"' if page_class else ""
    return f"""<!DOCTYPE html>
<html lang="zh-Hant-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} — BrainHub</title>
<link rel="icon" href="/logo.svg" type="image/svg+xml">
<script>{THEME_INIT_JS}</script>
<!-- daisyUI FIRST, and that is the whole safety argument. Everything the
     vendored file still carries lives inside `@layer`, and a layered rule loses
     to an unlayered one no matter how specific it is — so the shell's own two
     stylesheets below cannot be outranked by a component style, whatever class
     a page puts on an element. Moving this tag after them would not change that
     (layers, not order, decide it), but it WOULD hand the file's one unlayered
     block — its inlined copy of the brand tokens — the last word over the
     canonical copy in BRAND_THEME_CSS. One palette, one winner: this one. -->
<style>{DAISY_CSS}</style>
<style>{CSS}</style>
<style>{BRAND_THEME_CSS}</style>
</head>
<body{body_class}>
{render_header_html(memory_enabled=memory_enabled, populated=populated)}
<div class="graph-tooltip" id="graph-tooltip"></div>
{body}
{render_footer_html()}
<script>{KEYBOARD_NAV_JS}</script>
<script>{NAV_CURRENT_JS}</script>
<script>{THEME_CONTROL_JS}</script>
<script>{MEMORY_ACTION_JS}</script>
<script>{COPY_BUTTON_JS}</script>
<script>{RAW_SOURCE_JS}</script>
<script>{PROPOSAL_UI_JS}</script>
</body>
</html>"""
