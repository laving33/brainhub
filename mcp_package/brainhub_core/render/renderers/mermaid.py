"""Mermaid diagram renderer (kind='mermaid', output_kind='chart').

Renders a Mermaid diagram source (flowchart/graph/sequence/class/state/gantt/
pie/...) into a self-contained HTML fragment. The vendored Mermaid bundle
(``mcp_package/brainhub_core/vendor/mermaid.min.js``, mermaid v11.16.0, ~3.5MB) is
read from DISK via :func:`..document.read_vendor` and inlined verbatim into a
``<script>`` tag in the returned ``head`` — there is NO network fetch anywhere
in this module.

Self-containment note: the document layer wraps every artifact with a CSP of
``default-src 'none'`` and no ``connect-src``, so any stray ``fetch()`` inside
the vendored bundle is browser-blocked regardless. The vendored bundle does
carry a handful of ``fetch()`` call sites, but they only fire for advanced
icon-pack / architecture-diagram features; basic flowchart / graph / sequence
/ class / state / gantt / pie diagrams render fully offline without ever
reaching them.

The bundle assigns the Mermaid API onto ``window.__esbuild_esm_mermaid_nm``
(see the bundle's trailing ``globalThis["mermaid"] = ...`` shim) as well as
``globalThis.mermaid``, so the init script below looks in both places
defensively.
"""
from __future__ import annotations

import html
import json

from ..document import read_vendor
from ..registry import RenderPart, RenderRequest, renderer


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
    description="Mermaid flowchart/graph/sequence diagram",
)
def render(request: RenderRequest) -> RenderPart:
    spec = request.spec
    source = _diagram_source(spec)
    title = spec.get("title") or "Diagram"

    mermaid_js = read_vendor("mermaid.min.js")
    # Themes stay deterministic in both live and static/print mode; the
    # document layer separately injects motion-flatten CSS when static.
    theme = "neutral"
    # Escape "</" so a diagram source containing a literal "</script>" (or
    # "</style>") cannot prematurely close the surrounding inline <script>
    # block — the HTML tokenizer looks for that byte sequence regardless of
    # JS string-literal context, so json.dumps() alone is not enough.
    source_json = json.dumps(source).replace("</", "<\\/")

    head = f"""<style>
.brainhub-mermaid-container {{ overflow-x: auto; }}
.brainhub-mermaid-error {{ color: #b00020; white-space: pre-wrap; font-family: monospace; }}
</style>
<script>{mermaid_js}</script>
<script>
(function() {{
  var m = (window.__esbuild_esm_mermaid_nm || {{}}).mermaid || window.mermaid;
  var container = document.getElementById('brainhub-mermaid');
  try {{
    m.initialize({{ startOnLoad: false, securityLevel: 'strict', theme: {json.dumps(theme)} }});
    var source = {source_json};
    m.run({{ querySelector: '.mermaid' }}).then(function() {{
      document.documentElement.setAttribute('data-brainhub-ready', '1');
    }}).catch(function(err) {{
      container.textContent = 'Mermaid render error: ' + (err && err.message ? err.message : err);
      container.classList.add('brainhub-mermaid-error');
      document.documentElement.setAttribute('data-brainhub-ready', '1');
    }});
  }} catch (err) {{
    container.textContent = 'Mermaid render error: ' + (err && err.message ? err.message : err);
    container.classList.add('brainhub-mermaid-error');
    document.documentElement.setAttribute('data-brainhub-ready', '1');
  }}
}})();
</script>"""

    body = (
        '<div class="brainhub-mermaid-container">'
        f'<pre class="mermaid" id="brainhub-mermaid">{html.escape(source)}</pre>'
        "</div>"
    )

    return RenderPart(body=body, head=head, title=title)
