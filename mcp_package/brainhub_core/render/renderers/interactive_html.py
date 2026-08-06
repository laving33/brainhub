"""Interactive HTML briefing renderer: tabs / accordion (kind='interactive-html').

Turns a small structured spec — a title, an optional intro, and a list of
{heading, body} sections — into a self-contained interactive fragment so
agents don't hand-write HTML for briefings. Two layouts:

* ``accordion`` (default): native ``<details>``/``<summary>`` elements. Zero
  JS, works fine under the document layer's ``script-src 'unsafe-inline'``
  CSP (it needs no script at all), and prints/captures correctly because a
  ``<details open>`` is just visible content — no JS-driven state to lose.
* ``tabs``: a small inline ``<script>`` (permitted by the CSP) toggles the
  ``hidden`` attribute on panel ``<div>``s when a real ``<button>`` is
  clicked. Buttons are real ``<button>`` elements (not links) so this works
  with zero external JS and no keyboard-trap.

Static/print handling (``RenderRequest.static``): a headless PNG/PDF capture
only ever sees ONE frame, so hidden tab panels or closed accordion sections
would silently vanish from a static export. When ``static`` is true this
module (a) force-opens every ``<details>`` and (b) renders every tab panel
without a ``hidden`` attribute, tagging the root with an ``is-static`` class
whose CSS also unhides any panel defensively (belt and braces) and hides the
now-inert tab nav.

All user-supplied text is treated as UNTRUSTED plain text: it is
``html.escape``'d and blank-line-separated paragraphs become ``<p>`` tags.
No external ``<script src>``/``<link>``/``<img src=http>`` — this module
carries no assets beyond inline CSS/JS it writes itself.

Self-contained module: registers exactly one renderer against the shared
``render.registry`` singleton at import time (via the ``@renderer``
decorator) and edits no other file — see ``render/renderers/__init__.py``
auto-discovery and ``render/registry.py`` for the contract.
"""
from __future__ import annotations

import html

from ..registry import RenderPart, RenderRequest, renderer

_VALID_LAYOUTS = ("tabs", "accordion")


def _validate(spec: dict) -> None:
    sections = spec.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("interactive-html spec requires a non-empty 'sections' list")
    for i, section in enumerate(sections):
        if not isinstance(section, dict) or not section.get("heading"):
            raise ValueError(f"interactive-html sections[{i}] is missing a 'heading'")
    layout = spec.get("layout", "accordion")
    if layout not in _VALID_LAYOUTS:
        raise ValueError(f"interactive-html 'layout' must be one of {_VALID_LAYOUTS}, got {layout!r}")


def _paragraphs(text: object) -> str:
    """Escape untrusted plain text; blank-line-separated chunks become <p>s."""
    raw = str(text or "")
    chunks = [chunk.strip() for chunk in raw.split("\n\n") if chunk.strip()]
    if not chunks:
        return ""
    return "\n".join(f"<p>{html.escape(chunk).replace(chr(10), '<br>')}</p>" for chunk in chunks)


_STYLE = """<style>
.brainhub-interactive { color: var(--text); }
.brainhub-interactive .ih-intro { margin: 0 0 1.25em; }
.brainhub-interactive .ih-intro p { margin: 0 0 0.75em; }
.brainhub-interactive .ih-intro p:last-child { margin-bottom: 0; }

.brainhub-interactive details.ih-section {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin: 0 0 0.75em;
  background: var(--surface);
  overflow: hidden;
}
.brainhub-interactive summary.ih-summary {
  cursor: pointer;
  padding: 0.75em 1em;
  font-weight: 600;
  list-style: none;
}
.brainhub-interactive summary.ih-summary::-webkit-details-marker { display: none; }
.brainhub-interactive summary.ih-summary::before {
  content: "\\25B8";
  display: inline-block;
  width: 1em;
  margin-right: 0.4em;
  color: var(--accent);
  transition: transform 0.15s ease;
}
.brainhub-interactive details[open] summary.ih-summary::before { transform: rotate(90deg); }
.brainhub-interactive details[open] summary.ih-summary { border-bottom: 1px solid var(--border); }
.brainhub-interactive .ih-body { padding: 0.85em 1.1em; }
.brainhub-interactive .ih-body p { margin: 0 0 0.75em; }
.brainhub-interactive .ih-body p:last-child { margin-bottom: 0; }

.brainhub-interactive .ih-tabnav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4em;
  border-bottom: 1px solid var(--border);
  margin: 0 0 1em;
  padding: 0 0 0.6em;
}
.brainhub-interactive .ih-tabbtn {
  font: inherit;
  color: var(--text);
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.4em 0.9em;
  cursor: pointer;
}
.brainhub-interactive .ih-tabbtn[aria-selected="true"] {
  background: var(--accent);
  color: var(--accent-fg);
  border-color: var(--accent);
}
.brainhub-interactive .ih-tabpanel {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1em 1.1em;
  background: var(--surface);
  margin: 0 0 0.75em;
}
.brainhub-interactive .ih-tabpanel[hidden] { display: none; }
.brainhub-interactive .ih-tabpanel h3 { margin-top: 0; }
.brainhub-interactive .ih-tabpanel p { margin: 0 0 0.75em; }
.brainhub-interactive .ih-tabpanel p:last-child { margin-bottom: 0; }

/* Static/print mode: a headless capture only ever sees one frame, so every
   tab panel must be visible in the output and the now-inert nav is hidden. */
.brainhub-interactive.is-static .ih-tabnav { display: none; }
.brainhub-interactive.is-static .ih-tabpanel[hidden] { display: block; }
</style>
"""

_TAB_SCRIPT = """<script>
(function () {
  document.querySelectorAll('.brainhub-interactive[data-ih-layout="tabs"]').forEach(function (root) {
    if (root.classList.contains('is-static')) { return; }
    var buttons = root.querySelectorAll('.ih-tabbtn');
    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var target = btn.getAttribute('data-target');
        buttons.forEach(function (b) {
          b.setAttribute('aria-selected', b === btn ? 'true' : 'false');
        });
        root.querySelectorAll('.ih-tabpanel').forEach(function (panel) {
          if (panel.id === target) { panel.removeAttribute('hidden'); }
          else { panel.setAttribute('hidden', ''); }
        });
      });
    });
  });
})();
</script>
"""


def _render_accordion(sections: list[dict], static: bool) -> str:
    items = []
    for section in sections:
        heading = html.escape(str(section["heading"]))
        body = _paragraphs(section.get("body", ""))
        open_attr = " open" if (static or section.get("open")) else ""
        items.append(
            f'<details class="ih-section"{open_attr}>'
            f'<summary class="ih-summary">{heading}</summary>'
            f'<div class="ih-body">{body}</div>'
            f"</details>"
        )
    return "\n".join(items)


def _render_tabs(sections: list[dict], static: bool) -> str:
    nav_items = []
    panel_items = []
    for idx, section in enumerate(sections):
        heading = html.escape(str(section["heading"]))
        body = _paragraphs(section.get("body", ""))
        panel_id = f"ih-panel-{idx}"
        selected = "true" if idx == 0 else "false"
        nav_items.append(
            f'<button type="button" class="ih-tabbtn" role="tab" '
            f'aria-selected="{selected}" aria-controls="{panel_id}" '
            f'data-target="{panel_id}">{heading}</button>'
        )
        # Static mode: never hide a panel (see module docstring + CSS above).
        hidden_attr = "" if (idx == 0 or static) else " hidden"
        panel_items.append(
            f'<div class="ih-tabpanel" id="{panel_id}" role="tabpanel"{hidden_attr}>'
            f"<h3>{heading}</h3>{body}</div>"
        )
    nav = f'<div class="ih-tabnav" role="tablist">{"".join(nav_items)}</div>'
    return nav + "\n" + "\n".join(panel_items)


@renderer(
    "interactive-html",
    output_kind="html",
    input_spec=_validate,
    description="Interactive briefing (tabs/accordion)",
)
def render(request: RenderRequest) -> RenderPart:
    spec = request.spec
    sections = spec["sections"]
    layout = spec.get("layout", "accordion")
    static = request.static
    title = spec.get("title") or "Briefing"

    intro_html = ""
    intro = spec.get("intro")
    if intro:
        intro_html = f'<div class="ih-intro">{_paragraphs(intro)}</div>'

    if layout == "tabs":
        content = _render_tabs(sections, static)
    else:
        content = _render_accordion(sections, static)

    root_classes = "brainhub-interactive is-static" if static else "brainhub-interactive"
    body = (
        f'<div class="{root_classes}" data-ih-layout="{html.escape(layout)}">'
        f"{intro_html}{content}</div>"
    )

    head = _STYLE
    if layout == "tabs":
        head += _TAB_SCRIPT

    return RenderPart(body=body, head=head, title=str(title))
