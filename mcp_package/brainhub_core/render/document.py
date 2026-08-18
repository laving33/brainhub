"""Self-contained HTML document shell for BrainHub artifacts.

This reuses the existing BrainHub web shell primitives found in the codebase rather
than reinventing them:

* the base theme/typography CSS constant ``web_assets.CSS`` (which has NO
  ``url()`` and no animations, so it is safe to inline in an offline file);
* the early theme-init script ``web_assets.THEME_INIT_JS`` for light/dark;
* the security-policy prior art in ``web_http`` (``CONTENT_SECURITY_POLICY`` /
  ``SVG_CONTENT_SECURITY_POLICY``), from which the artifact CSP below is derived.

It deliberately DROPS the BrainHub app chrome (nav header, ``/logo.svg`` favicon,
search box, GitHub footer) because those trigger server-relative requests and
have no place in a client-facing artifact. The whole point of an artifact is
ZERO external requests, so the CSP meta tag below hard-blocks any egress.

Mermaid / chart JS is inlined by renderers reading the vendored asset from disk
(:func:`read_vendor`) — never fetched.

On top of the BrainHub primitives, this module also layers the **aworkr brand
identity** (see :data:`BRAND_CSS`): the L1/L4 design tokens from
``core/library/brand/assets/tokens/tokens.css`` (copied verbatim — that file is
the SSOT, this is a frozen mirror for the shell), an inlined wordmark logo, and
a print/PDF affordance (``window.print()`` button + ``@media print`` rules).
The logo SVG is vendored into ``render/vendor/`` (see :data:`VENDOR_DIR`) and
read from disk at build time — never fetched at view time — exactly like the
mermaid bundle.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
from collections.abc import Sequence
from pathlib import Path

from .. import brand as _brand
from ..web_assets import BRAND_TOKENS_CSS, CSS, THEME_INIT_JS

# brainhub_core/ directory (this file is brainhub_core/render/document.py).
_LINK_CORE_DIR = Path(__file__).resolve().parents[1]
VENDOR_DIR = _LINK_CORE_DIR / "vendor"

# Content-Security-Policy applied to every artifact via a <meta> tag so the
# guarantee travels with the file (file://, any static host, an email preview).
# default-src 'none' denies ALL network by default; only inline styles and
# data: images/fonts are permitted. Derived from web_http's page + SVG CSPs.
#
# script-src is NOT 'unsafe-inline'. Every script an artifact carries is one we
# generated, so each is pinned by its sha256 (see :func:`script_hashes`) and
# anything else — a <script> smuggled in through a chart label, a diagram
# source, a section body — is refused by the browser even if it somehow reaches
# the markup unescaped. Escaping is still the primary defence; this is the layer
# that holds when escaping has a hole. Note a hash cannot authorise an
# ``onclick=`` attribute, which is why the PDF button wires itself in JS.
_CSP_WITHOUT_SCRIPT_SRC = (
    "default-src 'none'; "
    "img-src 'self' data:; "
    "style-src 'unsafe-inline'; "
    "font-src data:; "
    "base-uri 'none'; "
    "form-action 'none'"
)

# The permissive policy, kept for artifacts built BEFORE script hashing (they
# carry unhashed inline scripts and an ``onclick=`` PDF button) — serve.py still
# sends this as the HTTP header so those keep working. New artifacts additionally
# carry the stricter <meta> policy below, and a browser enforces both.
ARTIFACT_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; "
    "img-src 'self' data:; "
    "style-src 'unsafe-inline'; "
    "script-src 'unsafe-inline'; "
    "font-src data:; "
    "base-uri 'none'; "
    "form-action 'none'"
)

# Matches the browser's own tokenizer rule: a script element's text ends at the
# first "</script", regardless of JS string/comment context. Anything that would
# split differently here than in the browser would produce a hash the browser
# never computes, so the script would be silently blocked.
_SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script\s*>", re.DOTALL | re.IGNORECASE)
# Stands in for the policy during assembly; see wrap_document's two passes.
_CSP_PLACEHOLDER = "\x00brainhub-csp\x00"
_META_CSP_RE = re.compile(
    r'(<meta http-equiv="Content-Security-Policy" content=")([^"]*)(">)',
    re.IGNORECASE,
)
# Captures just the script-src directive's source list, up to the next directive.
_SCRIPT_SRC_RE = re.compile(r"script-src([^;]*)", re.IGNORECASE)


def script_hashes(markup: str) -> list[str]:
    """Return CSP ``'sha256-…'`` source tokens for every inline script in ``markup``.

    Order-preserving and de-duplicated, so an artifact that inlines the same
    snippet twice contributes one token.
    """
    tokens: list[str] = []
    for match in _SCRIPT_RE.finditer(markup):
        body = match.group(1)
        if not body.strip():
            continue
        digest = base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
        token = f"'sha256-{digest}'"
        if token not in tokens:
            tokens.append(token)
    return tokens


def artifact_csp(hashes: Sequence[str]) -> str:
    """Build the artifact CSP whose ``script-src`` admits exactly ``hashes``."""
    script_src = " ".join(hashes) if hashes else "'none'"
    return f"{_CSP_WITHOUT_SCRIPT_SRC}; script-src {script_src}"


def authorize_injected_scripts(document: str, injected: str) -> str:
    """Extend a built artifact's ``<meta>`` CSP to admit scripts in ``injected``.

    Anything that splices a ``<script>`` into an already-built artifact (the
    viewer's PDF-button upgrade and its print-reveal shim) must call this, or the
    hash-pinned policy the artifact carries will refuse the addition. Artifacts
    built before script hashing carry ``script-src 'unsafe-inline'`` and are
    returned unchanged — their policy already admits the injection.
    """
    additions = script_hashes(injected)
    if not additions:
        return document

    def _extend(match: re.Match) -> str:
        policy = match.group(2)
        directive = _SCRIPT_SRC_RE.search(policy)
        # Only the script-src value decides this. Testing the whole policy for
        # 'unsafe-inline' would always match — style-src legitimately carries it.
        if directive is None or "'unsafe-inline'" in directive.group(1):
            return match.group(0)
        missing = [h for h in additions if h not in directive.group(1)]
        if not missing:
            return match.group(0)
        extended = policy[: directive.end(1)] + " " + " ".join(missing) + policy[directive.end(1) :]
        return match.group(1) + extended + match.group(3)

    return _META_CSP_RE.sub(_extend, document, count=1)

# Static/print flatten: neutralise CSS animations & transitions so a headless
# PNG/PDF capture lands on the final frame instead of a blank/mid-animation one.
# Injected only when a build requests static mode. Renderers must ALSO skip their
# own JS-driven animation when RenderRequest.static is true (belt and braces).
#
# The same declarations ship unconditionally inside a prefers-reduced-motion
# query (see REDUCED_MOTION_CSS): static mode is a build-time choice about
# capture, while reduced motion is the reader's OS-level accessibility setting,
# and an artifact built without --static was previously honouring neither.
STATIC_FLATTEN_CSS = """
*, *::before, *::after {
  animation-duration: 0s !important;
  animation-delay: 0s !important;
  animation-iteration-count: 1 !important;
  animation-play-state: paused !important;
  transition-duration: 0s !important;
  transition-delay: 0s !important;
  scroll-behavior: auto !important;
  caret-color: transparent !important;
}
html { scroll-behavior: auto !important; }
"""

# Provenance is embedded in the WORKSPACE copy as an HTML comment between these
# sentinels. It never renders. `bh-export` strips it (see strip_provenance) so it
# does not ride out to a client.
# The PDF button's behaviour lives here rather than in an inline ``onclick=``.
# An event-handler attribute is NOT covered by a CSP script hash, so a single
# onclick would pin ``script-src`` to ``'unsafe-inline'`` for the whole
# document — see ARTIFACT_CONTENT_SECURITY_POLICY. Assigning ``.onclick``
# (rather than addEventListener) keeps serve.py's PDF button upgrade a
# replacement rather than a second handler firing alongside this one.
PDF_BUTTON_JS = """
(function() {
  function wire() {
    var button = document.querySelector('.brainhub-pdf-button');
    if (!button) { return; }
    button.onclick = function() {
      if (location.protocol === 'file:') {
        document.querySelectorAll('details').forEach(function(d) { d.open = true; });
        window.print();
        return;
      }
      var url = new URL(location.href);
      url.searchParams.set('format', 'pdf');
      location.assign(url);
    };
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();
"""

PROVENANCE_START = "<!--brainhub:provenance"
PROVENANCE_END = "brainhub:provenance:end-->"
_PROVENANCE_RE = re.compile(
    re.escape(PROVENANCE_START) + r".*?" + re.escape(PROVENANCE_END),
    re.DOTALL,
)


def read_vendor(name: str) -> str:
    """Read a vendored asset (e.g. ``mermaid.min.js``) from disk as text.

    Renderers call this to inline third-party JS. It reads a local file — there
    is NO network fetch. ``name`` is a bare filename; path traversal is refused.
    """
    if "/" in name or "\\" in name or name in ("", ".", ".."):
        raise ValueError(f"invalid vendor asset name: {name!r}")
    path = VENDOR_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"vendored asset not found: {path}")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# aworkr brand identity (SSOT: core/library/brand/assets/tokens/tokens.css).
# ---------------------------------------------------------------------------
# Values below are copied verbatim from the token file's L1 primitive + L4
# semantic layers (see the header comment there: "元件 CSS 只能用 L4 語意
# token（var(--color-*)），禁寫死 hex"). Everything this module adds — the
# header, the PDF button, the print rules — consumes ONLY the L4 `--color-*`
# (or other explicitly-semantic, e.g. `--shadow-sm`) custom properties, never a
# raw hex value. This block is appended as a SEPARATE ``<style>`` tag AFTER
# ``web_assets.CSS`` in the document ``<head>`` (see :func:`wrap_document`), so
# — at equal specificity — it wins the cascade for the handful of BrainHub theme
# variables (``--bg``/``--text``/``--accent``/...) it re-points at the brand
# palette. This re-themes prose, charts and diagrams (which already consume
# those BrainHub variables) to the brand palette with no per-renderer changes.
# The primitives are READ from the vendored token file, not re-typed here.
# This block used to carry its own copy of the palette — the second fork in the
# package — which meant a brand change had to be applied by hand in two places
# and a drift between them would show up only as two documents that no longer
# matched. web_assets.py already reads the vendored file; this reuses it rather
# than adding a third copy.
_BRAND_DOCUMENT_MAPPING = """
:root {
  /* L4 semantic — component layer (this shell) must only use these */
  --color-text: var(--brand-midnight);
  --color-text-muted: var(--brand-quiet-gray);
  --color-text-inverse: var(--brand-white);
  --color-text-on-accent: var(--derived-on-light-gold);
  --color-bg: var(--brand-white);
  --color-bg-section: var(--brand-section-bg);
  --color-bg-soft: var(--brand-soft-light);
  --color-bg-dark: var(--brand-midnight);
  --color-accent: var(--brand-dawn-gold);
  --color-accent-hover: var(--brand-sunrise-orange);
  --color-border: var(--derived-border);
  --color-border-strong: var(--derived-border-strong);
  --shadow-sm: 0 1px 2px rgba(10,10,30,0.04), 0 1px 3px rgba(10,10,30,0.06);

  /* Typography (tokens.css font stack) */
  --font-brand-sans: "Inter", "Noto Sans TC", -apple-system, sans-serif;
  --font-brand-mono: "JetBrains Mono", ui-monospace, "Cascadia Code", monospace;

  /* Re-theme the base BrainHub surface variables so existing prose/chart CSS
     (already written against --bg/--text/--accent/...) picks up the brand
     palette with no per-renderer edits. The categorical chart series colors
     (--series-1..--series-8 / --series-other, defined in web_assets.py) are
     deliberately NOT re-pointed here: they are the fixed, colorblind-validated
     dataviz palette and must survive the brand re-theme unchanged. That palette
     is machine-checked by scripts/validate_palette.py (gate:
     tests/test_render_palette.py), so multi-series legends are measured
     colorblind-distinct — not asserted so. (This block once claimed the OLD
     status-color series palette --ok/--caution/--muted stayed "visually
     distinct"; that was never measured and --ok/--caution also leaked status
     meaning into data series — the bug the --series-* palette replaced.) */
  --bg: var(--color-bg-section);
  --text: var(--color-text);
  --text-strong: var(--color-text);
  --muted: var(--color-text-muted);
  --subtle: var(--color-text-muted);
  --surface: var(--color-bg);
  --border: var(--color-border);
  --border-strong: var(--color-border-strong);
  --accent: var(--color-accent);
  --accent-fg: var(--color-text-on-accent);
  --accent-soft: var(--color-accent-hover);
  --link: var(--color-accent-hover);
  --font-sans: var(--font-brand-sans);
  --font-serif: var(--font-brand-sans);
  --font-mono: var(--font-brand-mono);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --color-text: var(--color-text-inverse);
    --color-bg: var(--color-bg-dark);
    --color-bg-section: var(--brand-deep-sleep);
    --color-text-on-accent: var(--brand-midnight);
    --bg: var(--color-bg);
    --text: var(--color-text);
    --text-strong: var(--color-text);
    --surface: var(--color-bg-section);
    --accent-fg: var(--color-text-on-accent);
  }
}
:root[data-theme="dark"] {
  --color-text: var(--color-text-inverse);
  --color-bg: var(--color-bg-dark);
  --color-bg-section: var(--brand-deep-sleep);
  --color-text-on-accent: var(--brand-midnight);
  --bg: var(--color-bg);
  --text: var(--color-text);
  --text-strong: var(--color-text);
  --surface: var(--color-bg-section);
  --accent-fg: var(--color-text-on-accent);
}

/* Artifact header: inline wordmark logo (top-left) + title + PDF button. */
.brainhub-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 0 0 24px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--color-border);
}
.brainhub-header-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.brainhub-logo {
  display: inline-flex;
  flex: none;
  width: 104px;
  height: auto;
  color: var(--color-text);
}
.brainhub-logo svg {
  display: block;
  width: 100%;
  height: auto;
}
.brainhub-header-title {
  margin: 0;
  padding-left: 12px;
  border-left: 1px solid var(--color-border);
  font-family: var(--font-brand-sans);
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--color-text-muted);
  overflow-wrap: anywhere;
  min-width: 0;
}
.brainhub-pdf-button {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-brand-sans);
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-on-accent);
  background: var(--color-accent);
  border: none;
  border-radius: 999px;
  padding: 8px 16px;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: background-color 0.15s ease, transform 0.15s ease;
}
.brainhub-pdf-button:hover { background: var(--color-accent-hover); }
.brainhub-pdf-button:active { transform: translateY(1px); }
.brainhub-pdf-button:focus-visible {
  outline: 2px solid var(--color-accent-hover);
  outline-offset: 2px;
}
@media (prefers-reduced-motion: reduce) {
  .brainhub-pdf-button { transition: none; }
}
@media (max-width: 560px) {
  .brainhub-header { flex-wrap: wrap; }
  .brainhub-header-title { border-left: none; padding-left: 0; flex-basis: 100%; order: 3; }
}

/* Print / PDF export: hide the button, keep the logo, clean margins, exact
   chart/diagram colors, sane page breaks. */
@media print {
  .brainhub-pdf-button { display: none !important; }
  @page { margin: 14mm 12mm; }
  html, body {
    background: var(--color-bg) !important;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  * , *::before, *::after {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .brainhub-header { break-inside: avoid; page-break-inside: avoid; }
  h1, h2, h3, h4, figure, table, pre,
  .brainhub-line-chart, .brainhub-mermaid-container, .brainhub-interactive details.ih-section {
    break-inside: avoid;
    page-break-inside: avoid;
  }
  a { color: var(--color-text) !important; text-decoration: none; }
  /* Tab panels hide via the [hidden] attribute, so CSS can reveal them for
     print; <details> hide via content-visibility (CSS can't reopen), so the
     offline PDF button force-opens them via JS before printing and the served
     ?format=pdf path injects the same reveal for artifacts of any vintage. */
  .brainhub-interactive .ih-tabnav { display: none !important; }
  .brainhub-interactive .ih-tabpanel[hidden] { display: block !important; }
}
"""

# The palette (vendored, shared with the viewer) followed by this shell's own
# mapping layer. Kept as one name so every existing consumer is unchanged.
BRAND_CSS = BRAND_TOKENS_CSS + _BRAND_DOCUMENT_MAPPING


def _strip_svg_xmlns(svg: str) -> str:
    """Drop ``xmlns``/``xmlns:xlink`` attributes from a standalone SVG file.

    The vendored logo files declare ``xmlns="http://www.w3.org/2000/svg"``
    (required when the file is opened on its own), but once this markup is
    inlined directly into an HTML5 document the declaration is redundant — the
    browser's foreign-content rules pick up ``<svg>`` without it (see
    ``renderers/line_chart.py``'s identical note for its own inline SVG). More
    importantly, leaving it in would put a literal ``http://`` substring in
    every artifact, which would trip the "zero external references" self-
    contained check even though nothing is ever fetched.
    """
    return re.sub(r'\s+xmlns(?::xlink)?="[^"]*"', "", svg)


def _load_logo_svg() -> str:
    """Inline the brand logo from disk — never fetched, import-time safe.

    Resolution order:
    1. A brand pack's ``logo.svg`` (``BRAINHUB_BRAND_DIR``) — the one place a
       deployment sets its whole corporate identity; see ``brand.py``.
    2. ``BRAINHUB_BRAND_LOGO`` env var — the older single-asset override.
    3. ``vendor/brand-logo.svg`` — a deployment's drop-in brand file (absent in
       this source tree, shipped as a neutral BrainHub mark in the distributed
       package).
    4. Vendored aworkr lockups — the bundled theme's default.
    5. Empty string — the header renders without a logo, nothing errors.
    """
    override = _brand.text_asset(_brand.LOGO_ASSET, _brand.LOGO_ENV)
    if override is not None:
        return _strip_svg_xmlns(override)
    for name in ("brand-logo.svg", "aworkr-logo-wordmark.svg", "aworkr-logo-primary.svg"):
        try:
            return _strip_svg_xmlns(read_vendor(name))
        except FileNotFoundError:
            continue
    return ""


# Loaded once at import time — a pure disk read of a vendored asset, not a
# per-request cost, and definitely not a network fetch.
LOGO_SVG = _load_logo_svg()


def render_header(title: str, *, white_label: bool = False) -> str:
    """Build the ``<header>`` fragment: inline logo + title + PDF button.

    Shared by every artifact via :func:`wrap_document` so all renderers
    (line-chart, bar-chart, mermaid, interactive-html, ...) get the same
    brand header for free.

    ⚠ ``white_label=True`` OMITS the wordmark logo. Why this is a structural
    flag, not a post-render strip (2026-07-18 tam 回報)：the logo is inlined
    **SVG (an image, not text)**, so a white-label deliverable that keeps it
    prints the aworkr wordmark **at the top of a report handed to the END
    client — revealing the subcontracting relationship** — and every scanner
    misses it: body-text scan, PDF metadata, and ``doc_register scan-doc
    --white-label`` are all blind to brand text living in the image layer.
    An AM caught one only by asking the white-label question FIRST, then
    eyeballing the HTML. The scan does not grow that eye on its own. ⇒ the
    fix is to never inject it for white-label output, not to strip it after.
    """
    safe_title = html.escape(str(title))
    logo = "" if white_label else (
        f'<span class="brainhub-logo" aria-hidden="true">{LOGO_SVG}</span>' if LOGO_SVG else ""
    )
    # Chart artifacts self-title inside the plot, so wrap_document hands us an
    # empty header title for them — omit the <h1> entirely (logo + PDF button
    # only) so the title is not shown twice (aligns with the dataviz "the chart
    # owns its one title" model). Documents / interactive-html keep the header title.
    title_h1 = f'<h1 class="brainhub-header-title">{safe_title}</h1>' if str(title).strip() else ""
    return (
        '<header class="brainhub-header">'
        '<div class="brainhub-header-brand">'
        f"{logo}"
        f"{title_h1}"
        "</div>"
        '<button type="button" class="brainhub-pdf-button">'
        "⬇ 下載 PDF"
        "</button>"
        "</header>"
    )


REDUCED_MOTION_CSS = (
    "@media (prefers-reduced-motion: reduce) {" + STATIC_FLATTEN_CSS + "}"
)


def flatten_style(static: bool) -> str:
    """Return a ``<style>`` block that flattens motion, or ``""`` when not static."""
    if not static:
        return ""
    return f"<style data-brainhub-static>{STATIC_FLATTEN_CSS}</style>"


def reduced_motion_style() -> str:
    """Return the always-on ``<style>`` honouring the reader's motion setting."""
    return f"<style data-brainhub-reduced-motion>{REDUCED_MOTION_CSS}</style>"


def _provenance_block(provenance: dict | None) -> str:
    if not provenance:
        return ""
    payload = json.dumps(provenance, indent=2, sort_keys=True)
    return f"\n{PROVENANCE_START}\n{payload}\n{PROVENANCE_END}\n"


def strip_provenance(document: str) -> str:
    """Remove any embedded BrainHub provenance block from an artifact's HTML.

    Used by ``bh-export`` before writing a file for a human/client. Idempotent:
    documents with no provenance block are returned unchanged.
    """
    return _PROVENANCE_RE.sub("", document)


def has_provenance(document: str) -> bool:
    """True if the document still carries an embedded provenance block."""
    return PROVENANCE_START in document


def wrap_document(
    title: str,
    body: str,
    *,
    head_extra: str = "",
    body_class: str = "",
    static: bool = False,
    provenance: dict | None = None,
    header_title: str | None = None,
    white_label: bool = False,
) -> str:
    """Wrap a body fragment into ONE self-contained ``<!DOCTYPE html>`` file.

    ``white_label=True`` omits the wordmark logo from the header (see
    :func:`render_header` — the logo is an SVG the scanners cannot see, so
    white-label output must never inject it, not strip it after).

    * ``head_extra`` — renderer-specific inline ``<style>``/``<script>`` (already
      safe). This is where a renderer injects, e.g., inlined mermaid JS.
    * ``static`` — inject :data:`STATIC_FLATTEN_CSS` for headless capture.
    * ``provenance`` — embed a strippable provenance comment (workspace copy).

    The shell deliberately adds NO ``role``/``aria-*`` wrapper around ``body``.
    A graphic's accessible name belongs to the graphic: ``report_chart`` already
    emits ``<svg role="img">`` with ``<title>``/``<desc>``, and wrapping that in
    an outer ``role="img"`` would make the subtree presentational and hide the
    richer text it already carries. A renderer whose output lacks a name adds
    one itself (see ``renderers/mermaid.py``).

    The result has zero external requests: base CSS + theme-init JS are inlined
    from ``web_assets``, the CSP meta blocks egress, and the favicon is a no-op
    ``data:`` URI so browsers do not probe ``/favicon.ico``. The aworkr brand
    palette/typography (:data:`BRAND_CSS`) and a header (inline logo + title +
    PDF-export button, :func:`render_header`) are layered on top so every
    renderer's output reads as one branded artifact.
    """
    safe_title = html.escape(str(title))
    cls = f' class="{html.escape(body_class, quote=True)}"' if body_class else ""
    # Assembled in two passes: the CSP has to name the sha256 of every script the
    # finished document contains, and renderer scripts arrive in head_extra/body,
    # so the policy can only be computed once the document exists. Pass 1 uses a
    # placeholder that no policy syntax can collide with.
    document = f"""<!DOCTYPE html>
<html lang="zh-Hant-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="{_CSP_PLACEHOLDER}">
<meta name="generator" content="brainhub">
<title>{safe_title}</title>
<link rel="icon" href="data:,">
<script>{THEME_INIT_JS}</script>
<script>{PDF_BUTTON_JS}</script>
<style>{CSS}</style>
<style>{BRAND_CSS}</style>
{reduced_motion_style()}
{flatten_style(static)}
{head_extra}
</head>
<body{cls}>{_provenance_block(provenance)}
{render_header(title if header_title is None else header_title, white_label=white_label)}
<main class="brainhub-artifact">
{body}
</main>
</body>
</html>"""
    # Pass 2: pin every script the document actually ended up carrying. The
    # placeholder is replaced, never the policy of a nested document — it appears
    # exactly once and nothing else in the artifact can contain it.
    return document.replace(_CSP_PLACEHOLDER, artifact_csp(script_hashes(document)), 1)
