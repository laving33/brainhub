"""Markdown -> HTML for the BrainHub web UI, on a CommonMark implementation.

This used to be a hand-written line loop supporting a deliberately small subset.
The subset turned out to be the problem: an author writing an ordinary image
(``![chart](x.png)``) got nothing, so they pasted raw SVG instead and the page
rendered as hundreds of lines of escaped source. The tool did not offer the
standard way to do the thing, so people invented non-standard ways.

So the parser is now markdown-it-py (CommonMark + GFM tables, strikethrough,
task lists, footnotes, definition lists), and the rules that are *ours* are
implemented as plugins on top of it rather than as a competing parser:

* ``[[wikilink]]`` — an inline rule, so it does NOT fire inside code spans or
  fenced blocks. A regex pre-pass over the source would have rewritten wikilinks
  that an author was quoting as literal text.
* HTML is disabled, not sanitised. A wiki page cannot inject markup, which is
  the same guarantee the hand-written renderer gave, reached by configuration
  instead of by having no feature.
* Link and image targets are restricted to http(s), mailto and same-origin
  paths, so a page cannot silently call out to a third party.
"""
from __future__ import annotations

import html
import re
import urllib.parse
from collections.abc import Callable

from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin


def default_page_href(name: str) -> str:
    return "/page/" + urllib.parse.quote(name.strip(), safe="")


_SAFE_SCHEMES = {"http", "https", "mailto"}


def _safe_target(href: str) -> str:
    """Allow http(s)/mailto and same-origin paths; everything else becomes '#'.

    Blocks `javascript:` and friends, and also blocks protocol-relative `//host`
    URLs, which look relative and are not.
    """
    href = html.unescape(str(href or "")).strip()
    if href.startswith("//"):
        return "#"
    parsed = urllib.parse.urlparse(href)
    if parsed.scheme and parsed.scheme.lower() not in _SAFE_SCHEMES:
        return "#"
    return href


def _wikilink_plugin(md: MarkdownIt, page_href: Callable[[str], str]) -> None:
    """Render ``[[target|label]]`` as a link, as an inline rule.

    Registered before markdown-it's own ``link`` rule so ``[[x]]`` is not first
    read as a link whose text is ``[x]``.
    """

    def rule(state, silent: bool) -> bool:
        position = state.pos
        if not state.src.startswith("[[", position):
            return False
        end = state.src.find("]]", position + 2)
        if end == -1:
            return False
        inner = state.src[position + 2:end]
        if not inner.strip() or "\n" in inner:
            return False
        if not silent:
            target, _, label = inner.partition("|")
            label = (label or target).strip()
            token = state.push("link_open", "a", 1)
            token.attrs = {"href": page_href(target.strip())}
            text_token = state.push("text", "", 0)
            text_token.content = label
            state.push("link_close", "a", -1)
        state.pos = end + 2
        return True

    md.inline.ruler.before("link", "wikilink", rule)


def _build(page_href: Callable[[str], str]) -> MarkdownIt:
    md = (
        # linkify is OFF on purpose. It turns every bare domain in prose into a
        # link, which on this wiki means a page listing competitor domains starts
        # linking to competitors — against the standing rule that outward-facing
        # material links to news coverage and never to a competitor's own site.
        # It also emits http:// rather than https://. An author who wants a link
        # writes one; the renderer should not invent them (found by diffing all
        # 278 pages through both renderers, 2026-07-22).
        MarkdownIt("gfm-like", {"html": False, "linkify": False, "typographer": False})
        .use(footnote_plugin)
        .use(deflist_plugin)
        .use(tasklists_plugin, enabled=True)
        .enable("strikethrough")
    )
    _wikilink_plugin(md, page_href)

    def render_link_open(self, tokens, index, options, env):
        token = tokens[index]
        token.attrSet("href", _safe_target(token.attrGet("href") or ""))
        return self.renderToken(tokens, index, options, env)

    def render_image(self, tokens, index, options, env):
        token = tokens[index]
        token.attrSet("src", _safe_target(token.attrGet("src") or ""))
        token.attrSet("loading", "lazy")
        alt = self.renderInlineAsText(token.children or [], options, env)
        token.attrSet("alt", alt)
        return self.renderToken(tokens, index, options, env)

    md.add_render_rule("link_open", render_link_open)
    md.add_render_rule("image", render_image)
    return md


def inline_markdown(text: str, page_href: Callable[[str], str] = default_page_href) -> str:
    """Render one line's inline markup (no block elements, no wrapping <p>)."""
    return _build(page_href).renderInline(str(text))


def markdown_to_html(markdown: str, page_href: Callable[[str], str] = default_page_href) -> str:
    """Render a page body.

    Raw block HTML is fenced first: with HTML disabled the parser escapes it, and
    escaped markup laid out as prose is how an inline chart became a wall of
    text across the reader's screen. Fencing keeps the same bytes, contained.
    """
    return _build(page_href).render(fence_raw_blocks(str(markdown)))


_RAW_BLOCK_TAGS = ("svg", "div", "table", "iframe", "section", "figure", "details", "script", "style", "canvas")
_RAW_BLOCK_OPEN = re.compile(r"^\s*<(" + "|".join(_RAW_BLOCK_TAGS) + r")\b", re.IGNORECASE)


def fence_raw_blocks(markdown: str) -> str:
    """Wrap raw block-level HTML in a code fence so it reads as source, not prose."""
    lines = str(markdown).split("\n")
    out: list[str] = []
    index = 0
    in_fence = False
    while index < len(lines):
        line = lines[index]
        if line.strip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            index += 1
            continue
        opening = None if in_fence else _RAW_BLOCK_OPEN.match(line)
        if not opening:
            out.append(line)
            index += 1
            continue
        tag = opening.group(1).lower()
        closing = re.compile(r"</" + tag + r"\s*>", re.IGNORECASE)
        end = next((scan for scan in range(index, len(lines)) if closing.search(lines[scan])), None)
        if end is None:
            # No closing tag: leave it alone rather than swallow the rest of the page.
            out.append(line)
            index += 1
            continue
        out.append("```html")
        out.extend(lines[index:end + 1])
        out.append("```")
        index = end + 1
    return "\n".join(out)


__all__ = ["default_page_href", "escapeHtml", "fence_raw_blocks", "inline_markdown", "markdown_to_html"]
