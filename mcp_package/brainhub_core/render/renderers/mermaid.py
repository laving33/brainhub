"""Mermaid diagram renderer (kind='mermaid', output_kind='chart').

Renders a Mermaid diagram source into a self-contained HTML fragment. The
vendored Mermaid bundle (``mcp_package/brainhub_core/vendor/mermaid.min.js``,
mermaid v11.16.0, ~3.5MB) is read from DISK via :func:`..document.read_vendor`
and inlined verbatim into a ``<script>`` tag in the returned ``head`` — there
is NO network fetch anywhere in this module.

The verified diagram types are :data:`VERIFIED_DIAGRAM_TYPES` — that tuple is
the single source of truth. Each entry was rendered end-to-end in headless
Chromium against the artifact CSP (2026-08-18); the renderer description, the
README, and the runtime skill all restate the list, and
``scripts/check_docs_sync.py`` fails when any of them drifts from it.

Two syntax notes the list cannot carry: ``architecture-beta`` is verified only
with the built-in icons (cloud/database/disk/internet/server), and
``venn-beta``'s keywords are singular — ``set A`` / ``union A, B``.

Self-containment note: the document layer wraps every artifact with a CSP of
``default-src 'none'`` and no ``connect-src``, so any stray ``fetch()`` inside
the vendored bundle is browser-blocked regardless. The bundle's ``fetch()``
call sites only fire for EXTERNAL icon packs (``architecture-beta`` with
non-built-in icons, icon shapes); every diagram type listed above renders
fully offline without ever reaching them.

Diagram types brainhub has no first-class renderer for, and the closest
verified mermaid stand-in: swimlane -> ``flowchart`` with ``subgraph`` lanes;
org chart -> ``flowchart TD``; layer stack -> ``block-beta`` stacked rows.

The bundle exposes the Mermaid API two ways (see its trailing shim
``globalThis["mermaid"] = globalThis.__esbuild_esm_mermaid_nm["mermaid"].default``):
``window.__esbuild_esm_mermaid_nm.mermaid`` is the ESM *module namespace*
(the API lives on its ``.default``), while ``globalThis.mermaid`` is the API
itself. The init script below resolves ``.default`` first and falls back to
``window.mermaid``, and defers until DOMContentLoaded because the document
layer places ``head`` content before the body container exists.
"""
from __future__ import annotations

import html
import json

from ..document import read_vendor
from ..registry import RenderPart, RenderRequest, renderer

# SSoT for "which mermaid diagram types are known to render offline". Every
# prose copy of this list is checked against it by scripts/check_docs_sync.py,
# so adding a type here is what makes the docs go stale-and-red rather than
# stale-and-silent. Names are the short forms used in docs, not the parser
# keywords (the parser wants e.g. "stateDiagram-v2", "xychart-beta").
VERIFIED_DIAGRAM_TYPES = (
    "flowchart",
    "sequence",
    "class",
    "state",
    "gantt",
    "pie",
    "ER",
    "journey",
    "quadrant",
    "timeline",
    "mindmap",
    "gitGraph",
    "xychart",
    "sankey",
    "kanban",
    "packet",
    "block",
    "radar",
    "treemap",
    "C4",
    "architecture",
    "venn",
)


def _validate(spec: dict) -> None:
    diagram = spec.get("diagram")
    if not isinstance(diagram, str) or not diagram.strip():
        diagram = spec.get("definition")
    if not isinstance(diagram, str) or not diagram.strip():
        raise ValueError(
            "mermaid spec requires a non-empty string 'diagram' "
            "(alias: 'definition')"
        )


def _diagram_source(spec: dict) -> str:
    diagram = spec.get("diagram")
    if not isinstance(diagram, str) or not diagram.strip():
        diagram = spec.get("definition")
    return diagram


@renderer(
    "mermaid",
    output_kind="chart",
    input_spec=_validate,
    description=(
        f"Mermaid diagram ({len(VERIFIED_DIAGRAM_TYPES)} verified offline types: "
        f"{', '.join(VERIFIED_DIAGRAM_TYPES)})"
    ),
    example={"diagram": "graph TD; 需求-->設計; 設計-->實作;"},
    # Mermaid draws no title of its own, so the shell heading has to carry it.
    self_titled=False,
)
def render(request: RenderRequest) -> RenderPart:
    spec = request.spec
    source = _diagram_source(spec)
    # The caller's title outranks the spec's: pipeline resolves the document
    # title the same way, and the two must agree or the diagram's accessible
    # name says something different from the document it lives in.
    title = request.title or spec.get("title") or "Diagram"

    mermaid_js = read_vendor("mermaid.min.js")
    # Themes stay deterministic in both live and static/print mode; the
    # document layer separately injects motion-flatten CSS when static.
    # The diagram source reaches the page ONLY as html-escaped text inside the
    # <pre class="mermaid"> body (mermaid reads it back via textContent), so
    # there is no JS string literal for a hostile "</script>" to break out of.
    theme = "neutral"
    # The title IS interpolated into the init script, so escape "</": the HTML
    # tokenizer honours that byte sequence regardless of JS string context.
    title_json = json.dumps(title).replace("</", "<\\/")

    head = f"""<style>
.brainhub-mermaid-container {{ overflow-x: auto; }}
.brainhub-mermaid-error {{ color: #b00020; white-space: pre-wrap; font-family: monospace; }}
</style>
<script>{mermaid_js}</script>
<script>
(function() {{
  function boot() {{
    var ns = window.__esbuild_esm_mermaid_nm;
    var m = (ns && ns.mermaid && ns.mermaid.default) || window.mermaid;
    var container = document.getElementById('brainhub-mermaid');
    function fail(err) {{
      container.textContent = 'Mermaid render error: ' + (err && err.message ? err.message : err);
      container.classList.add('brainhub-mermaid-error');
      document.documentElement.setAttribute('data-brainhub-ready', '1');
    }}
    try {{
      m.initialize({{ startOnLoad: false, securityLevel: 'strict', theme: {json.dumps(theme)} }});
      m.run({{ querySelector: '.mermaid' }}).then(function() {{
        // Mermaid emits role="graphics-document" with NO accessible name, so
        // the diagram would announce as an unnamed graphic. Name it from the
        // artifact title rather than wrapping it in an outer role="img",
        // which would make the diagram's own text presentational.
        var svg = container.querySelector('svg');
        if (svg) {{ svg.setAttribute('aria-label', {title_json}); }}
        document.documentElement.setAttribute('data-brainhub-ready', '1');
      }}).catch(fail);
    }} catch (err) {{
      fail(err);
    }}
  }}
  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', boot);
  }} else {{
    boot();
  }}
}})();
</script>"""

    body = (
        '<div class="brainhub-mermaid-container">'
        f'<pre class="mermaid" id="brainhub-mermaid">{html.escape(source)}</pre>'
        "</div>"
    )

    return RenderPart(body=body, head=head, title=title)
