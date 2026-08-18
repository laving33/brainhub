# ─────────────────────────────────────────────────────────────
# Owned by BrainHub. Formerly vendored from lab/catalog as a byte-frozen
# mirror, which was the right shape while BrainHub was an aworkr tool: it had
# to ship to machines with no aworkr checkout. It stopped being the right shape
# once the product line separated — the SSoT is not reachable from a BrainHub
# checkout, so its drift guard could only skip, and defects found here (an
# unreadable <desc>, a 9th series that repeats the 1st colour, a slot order
# that fails our own palette validator, CJK labels overflowing their gutter)
# had nowhere to be fixed. Adopted 2026-08.
# ─────────────────────────────────────────────────────────────
"""chart_primitives — zero-dependency, deterministic static-SVG chart emitter.

Wave-0 render-layer enabler for the aworkr report gallery
(data/report-gallery/37-card-viz-review-2026-07.md §5). This module is the
**Tier-1 canonical / ship** half of the dual-track render path: pure hand-written
SVG that runs on a bare client Claude-Code node with **stdlib only** — no
matplotlib / plotly / chart libs, no headless chrome, no network. The Tier-2
rich/interactive path (brainhub chart directives) is emitted by
``report_render.render_viz_block(mode="directive")`` and is NOT this module.

Why this exists (review §5 rationale):
  * **deterministic** — same input dict → *byte-identical* SVG. No timestamps, no
    ``random``, no ``id()``-derived attributes, no dependence on dict iteration
    order (every primitive consumes ordered ``list`` inputs). This is the load-
    bearing property: the SVG can be diffed, byte-cached, and grep-audited against
    the envelope numbers it renders (防線紀律 #1). ``tests/test_report_chart.py``
    asserts it.
  * **portable** — ADR-0068. A ``_lib`` *helper* module (imported, never executed
    as an entry-point), so it carries **no venv re-exec bootstrap** by design: the
    bootstrap idiom only belongs on entry-point scripts (skill ``run.py`` / pack
    ``scripts/*.py``) that a client invokes directly; a library imported by an
    already-bootstrapped entry-point must not re-exec (it would hijack the caller).
    stdlib-only keeps it importable everywhere with zero setup.
  * **lintable** — every number rendered as *text* is a verbatim slot-fill of a
    passed value (no thousands-commas, no rounding of data), so ``grep`` finds the
    exact envelope figure inside the ``<svg>``.

Layer-C boundary (ADR-0054). The primitives do **presentation geometry only** —
scaling already-precomputed values to pixels / arc-angles to fit the canvas
(min/max ranging for axes, share→arc mapping for the donut). They never derive a
**reported metric**: they do not sort rows (the envelope is pre-sorted upstream),
and they do not compute shares / deltas / totals that appear as claims (upstream
``synthesize`` precomputes those). The only arithmetic here maps a value to a
coordinate; the value itself passes through untouched. The pack-audit viz
invariant (I38 / ADR-0101) enforces that a spec's ``viz.*_field`` points at a
field the section already declares, so the render layer can only *project* fields
that upstream already produced.

Palette / typography constants come from the official Claude-Code ``dataviz``
skill (``references/palette.md`` + ``marks-and-anatomy.md``): the validated 8-slot
categorical set (light + dark columns), the blue sequential ramp, the fixed
4-role status palette, chart chrome inks, and the system-sans stack — defined once
here so every chart in every card reads as one system. Colors are emitted as a
CSS-variable theme (light default + ``prefers-color-scheme: dark`` override) with
the light hex baked as a presentation-attribute fallback, so a CSS-aware viewer
(brainhub, browsers) gets accessible light+dark and a ``<style>``-stripping viewer
(e.g. GitHub-flavored markdown) still shows the validated light palette.

Self-test (doctest only, synthetic data — no tenant data per R2):
    python3 -m doctest -v skills/_lib/report_chart.py
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Mapping, Sequence

__version__ = "0.1.0"

__all__ = [
    "ChartError",
    "CHART_TYPES",
    "CAT_LIGHT",
    "CAT_DARK",
    "SEQ_LIGHT",
    "STATUS",
    "tile_row",
    "line",
    "hbar",
    "donut",
    "stacked_bar",
    "heatmap",
    "funnel",
    "gauge",
    "scatter",
]


class ChartError(ValueError):
    """A primitive was called with structurally unusable data (never rendered)."""


# The 9 render primitives (8 charts + the tile_row figure) — review §3 vocabulary
# plus the scatter §3 second-tier exception. The optional ``table`` viz type is a
# render-layer concern (auto-degrade), not a chart primitive, so it is not here.
CHART_TYPES = frozenset({
    "tile_row", "line", "hbar", "donut", "stacked_bar",
    "heatmap", "funnel", "gauge", "scatter",
})


# ── dataviz palette constants (references/palette.md — validated defaults) ──────

# Categorical: same eight hues, light column + dark column stepped for the dark
# surface (NOT a separate palette). Slot ORDER is the CVD-safety mechanism.
# The ORDER is the CVD-safety mechanism, and this order is the one that passes
# scripts/validate_palette.py. The previous order put #e87ba4 next to #eb6834
# (adjacent ΔE 12.9 in light, 7.8 in dark, against a floor of 15) — two slots a
# full-colour reader cannot reliably tell apart. Same eight hues, re-seated, and
# now identical to the shell's --series-1..8 so one dataset does not draw series
# 2 green in one renderer and orange in another.
CAT_LIGHT = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100",
             "#e87ba4", "#008300", "#4a3aa7", "#e34948")
CAT_DARK = ("#3987e5", "#d95926", "#199e70", "#c98500",
            "#d55181", "#008300", "#9085e9", "#e66767")
# Ninth series and beyond: a neutral, so "I ran out of hues" is visible rather
# than disguised as a repeated category.
CAT_OTHER = "#898781"

# Sequential blue ramp 100→700 (heatmap / choropleth continuous magnitude).
SEQ_LIGHT = ("#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
             "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b")

# Status palette — fixed, never themed (good / warning / serious / critical).
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}

# Chart chrome & ink (light / dark columns from palette.md).
_CHROME_LIGHT = {
    "surface": "#fcfcfb", "plane": "#f9f9f7", "ink": "#0b0b0b", "ink2": "#52514e",
    "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7",
}
_CHROME_DARK = {
    "surface": "#1a1a19", "plane": "#0d0d0d", "ink": "#ffffff", "ink2": "#c3c2b7",
    "muted": "#898781", "grid": "#2c2c2a", "axis": "#383835",
}

# System sans — the only face anywhere (no display/serif). palette.md §Typeface.
# Single-quoted 'Segoe UI' so the stack is safe inside a double-quoted SVG attr.
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def _build_style() -> str:
    """Build the CSS-variable theme block (light default + dark media override).

    Deterministic: iterates fixed-order tuples / literal dicts only. Emitted once
    inside every ``<svg>`` so a CSS-aware viewer themes light↔dark from one place;
    ``<style>``-stripping viewers fall back to the baked light presentation attrs.
    """
    def _vars(chrome: Mapping[str, str], cats: Sequence[str]) -> str:
        rows = [f"--{k}:{v}" for k, v in chrome.items()]
        rows += [f"--s{i + 1}:{c}" for i, c in enumerate(cats)]
        rows += [f"--st-{k}:{v}" for k, v in STATUS.items()]
        rows += [f"--seq{i}:{c}" for i, c in enumerate(SEQ_LIGHT)]
        return ";".join(rows)

    light = _vars(_CHROME_LIGHT, CAT_LIGHT)
    dark = _vars(_CHROME_DARK, CAT_DARK)
    return (
        f"svg.viz{{{light}}}"
        f"@media(prefers-color-scheme:dark){{svg.viz{{{dark}}}}}"
    )


_STYLE = _build_style()


# ── deterministic formatting helpers ────────────────────────────────────────────

def _c(x: float) -> str:
    """Coordinate/geometry formatter — round to 2dp, strip trailing zeros, kill -0.

    Geometry only (pixel positions), never a reported data value.

    >>> _c(12.0), _c(12.500), _c(-0.0), _c(1/3)
    ('12', '12.5', '0', '0.33')
    """
    v = round(float(x) + 0.0, 2)
    if v == 0:
        v = 0.0  # normalize -0.0 → 0.0
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _fmt(v: Any, fmt: str = "number") -> str:
    """Display formatter for a **data** value — verbatim by default (no commas).

    Verbatim keeps the rendered text grep-matchable against the envelope figure
    (review §5 lintability). ``percent`` is the one display transform (×100, ≤1dp)
    for precomputed *fractions* (0.42 → 42%); ``percent_points`` is for upstreams
    that already store percent UNITS (Google Ads IS-lost stores 9.0 meaning 9%) —
    it appends ``%`` verbatim with NO ×100, so a percent-unit field never renders
    100× too large; ``currency`` prepends ``$`` (no grouping).

    >>> _fmt(128400), _fmt(0.423, "percent"), _fmt(12.5), _fmt(1000, "currency")
    ('128400', '42.3%', '12.5', '$1000')
    >>> _fmt(9.0, "percent_points"), _fmt(50.0, "percent_points")
    ('9%', '50%')
    >>> _fmt(3.0), _fmt(True)
    ('3', 'true')
    """
    if isinstance(v, bool):
        return "true" if v else "false"
    if fmt == "percent_points" and isinstance(v, (int, float)):
        p = round(float(v), 1)
        return (f"{p:.1f}".rstrip("0").rstrip(".")) + "%"
    if fmt == "percent" and isinstance(v, (int, float)):
        p = round(float(v) * 100, 1)
        return (f"{p:.1f}".rstrip("0").rstrip(".")) + "%"
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        s = f"{v:.6f}".rstrip("0").rstrip(".")
        return s
    if isinstance(v, int):
        s = str(v)
    else:
        s = str(v)
    if fmt == "currency":
        return "$" + s
    return s


def _esc(s: Any) -> str:
    """XML-escape text content / attribute values (deterministic).

    >>> _esc('A & B <x> "q"')
    'A &amp; B &lt;x&gt; &quot;q&quot;'
    """
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _fill(var: str, hexc: str) -> str:
    """``fill`` presentation attr (universal fallback) + themed CSS var override."""
    return f'fill="{hexc}" style="fill:var(--{var})"'


def _stroke(var: str, hexc: str, width: float = 1) -> str:
    """``stroke`` presentation attr (fallback) + themed CSS var override + width."""
    return f'stroke="{hexc}" style="stroke:var(--{var})" stroke-width="{_c(width)}"'


def _fill_ring(var: str, hexc: str, ring_w: float = 2) -> str:
    """Filled mark + 2px surface-color ring (dataviz mark spec) in ONE ``style`` attr.

    A separate ``fill`` var and ``stroke`` var would each emit ``style=`` → duplicate
    attribute (invalid XML); this merges them so dots/arcs stay legible where they
    overlap (marks-and-anatomy §surface ring) and the SVG parses.
    """
    return (
        f'fill="{hexc}" stroke="{_CHROME_LIGHT["surface"]}" stroke-width="{_c(ring_w)}"'
        f' style="fill:var(--{var});stroke:var(--surface)"'
    )


def _cat(i: int, light: bool = True) -> tuple[str, str]:
    """Return (var_name, light_hex) for categorical slot i.

    Past the last slot this folds to a neutral grey rather than wrapping back to
    slot 1. Wrapping gave the 9th series the 1st series' colour, which reads as
    "same category" — a claim about the data that is simply false. Eight
    distinguishable hues is the honest limit; beyond it, say "other".
    """
    if i >= len(CAT_LIGHT):
        return ("other", CAT_OTHER)
    return (f"s{i + 1}", CAT_LIGHT[i])


def _text(x: float, y: float, s: Any, *, size: int = 12, anchor: str = "start",
          var: str = "ink", hexc: str | None = None, weight: str = "normal",
          tabular: bool = False) -> str:
    """A themed <text> node (labels/values always use text tokens, never data color).

    ``hexc`` overrides the presentation-attr fallback (needed for status-palette
    vars like ``st-good`` that are not chrome roles); defaults to the chrome hex.
    """
    tn = ' font-variant-numeric="tabular-nums"' if tabular else ""
    w = f' font-weight="{weight}"' if weight != "normal" else ""
    fallback = hexc if hexc is not None else _CHROME_LIGHT.get(var, "#0b0b0b")
    return (
        f'<text x="{_c(x)}" y="{_c(y)}" font-family="{FONT}" font-size="{size}"'
        f' text-anchor="{anchor}"{w}{tn} {_fill(var, fallback)}>'
        f'{_esc(s)}</text>'
    )


# Advance widths as a fraction of font size. Estimated, never measured: this
# module is stdlib-only by design, and the font stack resolves to whatever the
# reader's system supplies, so a "precise" number would be precise about the
# wrong face. Rounded up, so the estimate reports overflow before a real one.
def _estimate_text_width(text: str, size: float) -> float:
    total = 0.0
    for ch in text:
        code = ord(ch)
        if (0x1100 <= code <= 0x115F or 0x2E80 <= code <= 0xA4CF
                or 0xAC00 <= code <= 0xD7A3 or 0xF900 <= code <= 0xFAFF
                or 0xFE30 <= code <= 0xFE6F or 0xFF00 <= code <= 0xFF60
                or 0xFFE0 <= code <= 0xFFE6):
            total += 1.0
        elif ch.isdigit():
            total += 0.55
        elif ch.isupper():
            total += 0.67
        else:
            total += 0.5
    return total * size


def _svg(width: float, height: float, body: str, *, title: str, desc: str = "") -> str:
    """Wrap primitive body in a deterministic, accessible <svg>.

    Three details, each of which was wrong while this file could not be edited:

    * ``<title>`` is the FIRST child, ahead of ``<style>``. Assistive tech may
      ignore a title placed later.
    * ``<title>``/``<desc>`` carry ids and ``aria-labelledby`` names both. A
      ``<desc>`` nothing references is widely not announced at all, so the
      description — the only place the chart's numbers reach a screen reader,
      since ``role="img"`` makes the plot's own text presentational — was
      silently dropped.
    * The ids are derived from the title's content, keeping the module's
      deterministic contract (same input → byte-identical SVG) while letting
      two charts sit on one page without the second borrowing the first's name.
    """
    slug = hashlib.sha256(f"{title}\x00{desc}".encode("utf-8")).hexdigest()[:8]
    described = f' {slug}-desc' if desc else ""
    d = f'<desc id="{slug}-desc">{_esc(desc)}</desc>' if desc else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" class="viz" role="img"'
        f' aria-labelledby="{slug}-title{described}"'
        f' viewBox="0 0 {_c(width)} {_c(height)}" width="{_c(width)}" height="{_c(height)}">'
        f'<title id="{slug}-title">{_esc(title)}</title>{d}'
        f"<style>{_STYLE}</style>"
        f'<rect x="0" y="0" width="{_c(width)}" height="{_c(height)}" {_fill("surface", _CHROME_LIGHT["surface"])}/>'
        f"{body}</svg>"
    )


def _polar(cx: float, cy: float, r: float, deg: float) -> tuple[float, float]:
    """Clockwise-from-top polar → cartesian (SVG y-down). deg 0 = 12 o'clock."""
    rad = math.radians(deg)
    return (cx + r * math.sin(rad), cy - r * math.cos(rad))


def _luma_ink(hexc: str) -> tuple[str, str]:
    """Pick label (var,hex) — white on dark fill, ink on light fill (WCAG on-fill)."""
    h = hexc.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    return ("surface", "#ffffff") if lum < 0.55 else ("ink", "#0b0b0b")


def _seq_color(frac: float) -> tuple[str, str]:
    """Map a 0..1 magnitude to a sequential-ramp (var,hex) — geometry, not data."""
    frac = 0.0 if frac < 0 else (1.0 if frac > 1 else frac)
    idx = int(round(frac * (len(SEQ_LIGHT) - 1)))
    return (f"seq{idx}", SEQ_LIGHT[idx])


def _as_list(v: Any, name: str) -> list:
    if not isinstance(v, (list, tuple)) or len(v) == 0:
        raise ChartError(f"{name} must be a non-empty list, got {v!r}")
    return list(v)


# ── 1. tile_row — KPI scorecard row (figure, not a chart) ───────────────────────

def tile_row(tiles: Sequence[Mapping[str, Any]], *, title: str = "KPI") -> str:
    """A row of stat tiles: label · value · optional signed delta (dataviz figure contract).

    Each tile: ``{"label": str, "value": <num|str>, "value_format"?: str,
    "delta"?: <num>, "delta_good"?: bool}``. Values are verbatim slot-fills. Delta
    color = direction × whether up-is-good (status palette). No arithmetic on data.

    >>> svg = tile_row([{"label": "GMV", "value": 128400, "value_format": "currency",
    ...                  "delta": 0.12, "delta_good": True}])
    >>> svg.startswith("<svg") and "$128400" in svg and "GMV" in svg
    True
    """
    tl = _as_list(tiles, "tiles")
    tw, th, gap, pad = 172, 96, 14, 40
    width = pad + len(tl) * (tw + gap) - gap + pad if tl else pad * 2
    height = 44 + th + 20
    body = [_text(pad, 30, title, size=15, weight="600")]
    x = pad
    for t in tl:
        if not isinstance(t, Mapping) or "label" not in t or "value" not in t:
            raise ChartError(f"tile must have label+value, got {t!r}")
        y0 = 44
        body.append(
            f'<rect x="{_c(x)}" y="{_c(y0)}" width="{tw}" height="{th}" rx="8"'
            f' {_fill("plane", _CHROME_LIGHT["plane"])}'
            f' stroke="rgba(11,11,11,0.10)" stroke-width="1"/>'
        )
        body.append(_text(x + 16, y0 + 26, t["label"], size=12, var="ink2"))
        body.append(_text(x + 16, y0 + 58, _fmt(t["value"], t.get("value_format", "number")),
                          size=26, weight="600", var="ink"))
        if "delta" in t and t["delta"] is not None:
            good = bool(t.get("delta_good", True))
            up = float(t["delta"]) >= 0
            role = "st-good" if (up == good) else "st-critical"
            hexc = STATUS["good"] if role == "st-good" else STATUS["critical"]
            arrow = "▲" if up else "▼"
            body.append(_text(x + 16, y0 + 82,
                              f'{arrow} {_fmt(abs(float(t["delta"])), t.get("delta_format", "percent"))}',
                              size=13, var=role, hexc=hexc))
        x += tw + gap
    return _svg(width, height, "".join(body), title=title,
                desc=f"KPI row of {len(tl)} stat tiles")


# ── 2. line — trend (single or multi series) ────────────────────────────────────

def line(series: Sequence[Mapping[str, Any]], x_labels: Sequence[Any], *,
         title: str = "Trend", value_format: str = "number") -> str:
    """Line chart. ``series`` = ``[{"name": str, "values": [num, ...]}, ...]`` (one
    entry = single-series, no legend per dataviz). ``x_labels`` aligns to values.

    Scales to the data's own [min(0,·), max] range (pixel geometry). Endpoint of
    each series is direct-labelled with its verbatim last value; axis extremes show
    verbatim min/max data (no synthetic round ticks → nothing but real numbers).

    >>> svg = line([{"name": "GMV", "values": [96250, 128400]}], ["06-01", "06-02"])
    >>> svg.startswith("<svg") and "128400" in svg and "<polyline" in svg
    True
    """
    sl = _as_list(series, "series")
    xs = _as_list(x_labels, "x_labels")
    all_vals: list[float] = []
    for s in sl:
        vv = _as_list(s.get("values"), "series.values")
        if len(vv) != len(xs):
            raise ChartError(f"series {s.get('name')!r} has {len(vv)} values but {len(xs)} x_labels")
        all_vals += [float(v) for v in vv]
    dmin, dmax = min(all_vals), max(all_vals)
    lo = min(0.0, dmin)
    hi = dmax if dmax != lo else lo + 1.0
    W, H = 680, 300
    L, R, T, B = 64, 120, 40, 52
    pw, ph = W - L - R, H - T - B

    def px(i: int) -> float:
        return L + (pw * (i / (len(xs) - 1)) if len(xs) > 1 else pw / 2)

    def py(v: float) -> float:
        return T + ph * (1 - (v - lo) / (hi - lo))

    body = [_text(L, 24, title, size=15, weight="600")]
    # baseline + min/max gridlines (hairline, solid)
    for gv in (lo, hi):
        yy = py(gv)
        body.append(f'<line x1="{_c(L)}" y1="{_c(yy)}" x2="{_c(L + pw)}" y2="{_c(yy)}"'
                    f' {_stroke("grid", _CHROME_LIGHT["grid"], 1)}/>')
        body.append(_text(L - 8, yy + 4, _fmt(gv, value_format), size=11, anchor="end",
                          var="muted", tabular=True))
    # x labels (first, last, and mid if many) — sparing, per marks-and-anatomy
    idxs = sorted({0, len(xs) - 1, len(xs) // 2})
    for i in idxs:
        body.append(_text(px(i), T + ph + 20, xs[i], size=11, anchor="middle", var="muted"))
    # series
    for si, s in enumerate(sl):
        var, hexc = _cat(si)
        vv = [float(v) for v in s["values"]]
        pts = " ".join(f"{_c(px(i))},{_c(py(v))}" for i, v in enumerate(vv))
        body.append(f'<polyline points="{pts}" fill="none" {_stroke(var, hexc, 2)}'
                    f' stroke-linejoin="round" stroke-linecap="round"/>')
        # end marker with surface ring + direct end-label
        ex, ey = px(len(vv) - 1), py(vv[-1])
        body.append(f'<circle cx="{_c(ex)}" cy="{_c(ey)}" r="4" {_fill_ring(var, hexc)}/>')
        name = s.get("name", f"series {si + 1}")
        lbl = f"{name} {_fmt(vv[-1], value_format)}" if len(sl) > 1 else _fmt(vv[-1], value_format)
        body.append(_text(ex + 10, ey + 4, lbl, size=11, var="ink2", tabular=True))
    return _svg(W, H, "".join(body), title=title, desc=f"line chart, {len(sl)} series over {len(xs)} points")


# ── 3. hbar — ranked horizontal bars (caller pre-sorts) ─────────────────────────

def hbar(values: Sequence[float], labels: Sequence[Any], *, title: str = "Ranked",
         value_format: str = "number", truncated: bool = False) -> str:
    """Horizontal bar chart. ``values`` are pre-sorted upstream (render never sorts).

    Bar length = value / max(values) × plot-width (pixel geometry). Value printed
    at the tip, verbatim. ``truncated=True`` renders an honesty note (top-N slice).

    >>> svg = hbar([120, 80, 45], ["A", "B", "C"], title="Campaigns")
    >>> svg.startswith("<svg") and "120" in svg and "<rect" in svg
    True
    """
    vv = [float(v) for v in _as_list(values, "values")]
    ll = _as_list(labels, "labels")
    if len(vv) != len(ll):
        raise ChartError(f"hbar got {len(vv)} values but {len(ll)} labels")
    mx = max(vv) if max(vv) > 0 else 1.0
    W, rh = 660, 30
    # The label gutter follows the widest label instead of a fixed 150px. A CJK
    # glyph is a full em against roughly 0.55 for a digit, so a gutter measured
    # against Latin numerals clipped Chinese labels at about a third as many
    # characters — silently, with no ellipsis. Bounded so one long label cannot
    # squeeze the bars out of existence; past the bound it still clips, but the
    # common case stops doing so.
    gutter = max(90.0, min(300.0, _estimate_text_width(max((str(x) for x in ll), key=len, default=""), 12) + 20))
    T, B, R = 40, 20 + (18 if truncated else 0), 70
    H = T + len(vv) * rh + B
    pw = W - gutter - R
    body = [_text(16, 24, title, size=15, weight="600")]
    for i, (v, lab) in enumerate(zip(vv, ll)):
        y = T + i * rh
        bar = pw * (v / mx)
        var, hexc = _cat(0)  # single-series sequential-ish → slot 1 (one hue)
        body.append(_text(gutter - 8, y + rh / 2 + 4, lab, size=12, anchor="end", var="ink2"))
        body.append(f'<rect x="{_c(gutter)}" y="{_c(y + 4)}" width="{_c(max(bar, 0))}"'
                    f' height="{_c(rh - 10)}" rx="3" {_fill(var, hexc)}/>')
        body.append(_text(gutter + bar + 6, y + rh / 2 + 4, _fmt(v, value_format),
                          size=11, var="ink2", tabular=True))
    if truncated:
        body.append(_text(gutter, H - 6, "▤ top-N shown — tail truncated (see table)",
                          size=10, var="muted"))
    return _svg(W, H, "".join(body), title=title, desc=f"ranked horizontal bars, {len(vv)} rows")


# ── 4. donut — part-to-whole share (shares precomputed) ─────────────────────────

def donut(values: Sequence[float], labels: Sequence[Any], *, title: str = "Share",
          value_format: str = "percent", total_note: str | None = None) -> str:
    """Donut. ``values`` are precomputed shares/magnitudes; each maps to an arc
    proportional to its slice of the passed total (geometry — the total is the
    circle, never a reported metric). Render never normalizes away an honest gap.

    >>> svg = donut([0.5, 0.3, 0.2], ["A", "B", "C"], title="Channels")
    >>> svg.startswith("<svg") and "50%" in svg and "<path" in svg
    True
    """
    vv = [float(v) for v in _as_list(values, "values")]
    ll = _as_list(labels, "labels")
    if len(vv) != len(ll):
        raise ChartError(f"donut got {len(vv)} values but {len(ll)} labels")
    total = math.fsum(vv)
    if total <= 0:
        raise ChartError("donut values sum to <= 0 (cannot form a circle)")
    W, H = 420, 250
    cx, cy, ro, ri = 130, 130, 92, 56
    body = [_text(16, 24, title, size=15, weight="600")]
    angle = 0.0
    for i, (v, lab) in enumerate(zip(vv, ll)):
        sweep = 360.0 * (v / total)
        a0, a1 = angle, angle + sweep
        angle = a1
        var, hexc = _cat(i)
        if sweep >= 359.999:  # single full slice → ring
            body.append(f'<circle cx="{_c(cx)}" cy="{_c(cy)}" r="{_c((ro + ri) / 2)}"'
                        f' fill="none" {_stroke(var, hexc, ro - ri)}/>')
        else:
            large = 1 if sweep > 180 else 0
            ox0, oy0 = _polar(cx, cy, ro, a0)
            ox1, oy1 = _polar(cx, cy, ro, a1)
            ix1, iy1 = _polar(cx, cy, ri, a1)
            ix0, iy0 = _polar(cx, cy, ri, a0)
            d = (f"M{_c(ox0)},{_c(oy0)} A{_c(ro)},{_c(ro)} 0 {large} 1 {_c(ox1)},{_c(oy1)}"
                 f" L{_c(ix1)},{_c(iy1)} A{_c(ri)},{_c(ri)} 0 {large} 0 {_c(ix0)},{_c(iy0)} Z")
            body.append(f'<path d="{d}" {_fill_ring(var, hexc)}/>')
    # legend (right) — always present for ≥2 slices (identity channel)
    lx, ly = cx + ro + 30, 44
    for i, (v, lab) in enumerate(zip(vv, ll)):
        var, hexc = _cat(i)
        yy = ly + i * 22
        body.append(f'<rect x="{_c(lx)}" y="{_c(yy - 9)}" width="12" height="12" rx="2" {_fill(var, hexc)}/>')
        body.append(_text(lx + 18, yy + 1, f"{lab} {_fmt(v, value_format)}", size=12, var="ink2"))
    if total_note:
        body.append(_text(cx, cy + 4, _esc(total_note), size=11, anchor="middle", var="muted"))
    return _svg(W, H, "".join(body), title=title, desc=f"donut, {len(vv)} slices")


# ── 5. stacked_bar — 100% composition rows ──────────────────────────────────────

def stacked_bar(rows: Sequence[Mapping[str, Any]], segment_names: Sequence[str], *,
                title: str = "Composition", value_format: str = "percent") -> str:
    """Horizontal stacked bars. Each row: ``{"label": str, "segments": [num, ...]}``
    aligned to ``segment_names``. Segments map to widths proportional to the row's
    own passed total (geometry); a 2px surface gap separates touching segments.

    ``value_format`` formats the in-bar segment labels (default ``percent`` = the
    fraction convention, 0.6 → 60%). An upstream storing percent UNITS (9.0 = 9%)
    must pass ``percent_points`` — before 2026-07-12 this primitive hard-coded
    ``percent``, so such a field rendered 100× too large (D5 IS-lost: 9.0 → "900%")
    while every other primitive honoured the caller's format. Widths were always
    correct (geometry uses the raw value); only the label text was wrong.

    >>> svg = stacked_bar([{"label": "Jun", "segments": [0.6, 0.4]}], ["new", "returning"])
    >>> svg.startswith("<svg") and "<rect" in svg and "new" in svg
    True
    >>> "60%" in svg
    True
    >>> # percent-unit upstream: 9.0 means 9%, not 900%
    >>> svg2 = stacked_bar([{"label": "C1", "segments": [9.0, 50.0]}], ["budget", "rank"],
    ...                    value_format="percent_points")
    >>> "9%" in svg2 and "50%" in svg2 and "900%" not in svg2
    True
    """
    rl = _as_list(rows, "rows")
    sn = _as_list(segment_names, "segment_names")
    W, rh, gutter, R = 660, 34, 90, 20
    T, B = 60, 20
    H = T + len(rl) * rh + B
    pw = W - gutter - R
    body = [_text(16, 24, title, size=15, weight="600")]
    # legend
    lx = 16
    for i, name in enumerate(sn):
        var, hexc = _cat(i)
        body.append(f'<rect x="{_c(lx)}" y="34" width="12" height="12" rx="2" {_fill(var, hexc)}/>')
        body.append(_text(lx + 18, 44, name, size=11, var="ink2"))
        lx += 24 + len(str(name)) * 8
    for r, row in enumerate(rl):
        segs = [float(s) for s in _as_list(row.get("segments"), "row.segments")]
        if len(segs) != len(sn):
            raise ChartError(f"row {row.get('label')!r} has {len(segs)} segments but {len(sn)} names")
        tot = math.fsum(segs)
        if tot <= 0:
            raise ChartError(f"row {row.get('label')!r} segments sum to <= 0")
        y = T + r * rh
        body.append(_text(gutter - 8, y + rh / 2 + 4, row.get("label", r), size=12,
                          anchor="end", var="ink2"))
        x = gutter
        for i, sv in enumerate(segs):
            var, hexc = _cat(i)
            w = pw * (sv / tot)
            body.append(f'<rect x="{_c(x)}" y="{_c(y + 5)}" width="{_c(max(w - 2, 0))}"'
                        f' height="{_c(rh - 12)}" {_fill(var, hexc)}/>')
            if w > 34:  # inline label only when it fits with padding
                lv, lh = _luma_ink(hexc)
                body.append(_text(x + w / 2, y + rh / 2 + 4, _fmt(sv, value_format),
                                  size=10, anchor="middle", var=lv))
            x += w
    return _svg(W, H, "".join(body), title=title, desc=f"stacked bars, {len(rl)} rows × {len(sn)} segments")


# ── 6. heatmap — matrix colored by sequential ramp ──────────────────────────────

def heatmap(rows: Sequence[Mapping[str, Any]], col_labels: Sequence[Any], *,
            title: str = "Heatmap", vmin: float | None = None, vmax: float | None = None,
            value_format: str = "number") -> str:
    """Matrix heatmap. Each row: ``{"label": str, "values": [num|None, ...]}`` aligned
    to ``col_labels`` (None → empty cell, e.g. a cohort triangle). Cell color = value
    ramped over [vmin, vmax] (passed, or the data's own min/max — pixel geometry).

    >>> svg = heatmap([{"label": "M0", "values": [1.0, 0.4]}], ["d0", "d30"])
    >>> svg.startswith("<svg") and "<rect" in svg
    True
    """
    rl = _as_list(rows, "rows")
    cl = _as_list(col_labels, "col_labels")
    nums = [float(v) for r in rl for v in (r.get("values") or []) if isinstance(v, (int, float))]
    if not nums:
        raise ChartError("heatmap has no numeric cells")
    lo = vmin if vmin is not None else min(nums)
    hi = vmax if vmax is not None else max(nums)
    span = (hi - lo) or 1.0
    cw, ch, gutter, T = 62, 34, 90, 60
    W = gutter + len(cl) * cw + 16
    H = T + len(rl) * ch + 20
    body = [_text(16, 24, title, size=15, weight="600")]
    for j, clab in enumerate(cl):
        body.append(_text(gutter + j * cw + cw / 2, T - 8, clab, size=10, anchor="middle", var="muted"))
    for i, row in enumerate(rl):
        vals = row.get("values") or []
        y = T + i * ch
        body.append(_text(gutter - 8, y + ch / 2 + 4, row.get("label", i), size=11,
                          anchor="end", var="ink2"))
        for j in range(len(cl)):
            x = gutter + j * cw
            v = vals[j] if j < len(vals) else None
            if not isinstance(v, (int, float)):
                body.append(f'<rect x="{_c(x + 1)}" y="{_c(y + 1)}" width="{cw - 2}"'
                            f' height="{ch - 2}" rx="2" {_fill("plane", _CHROME_LIGHT["plane"])}/>')
                continue
            frac = (float(v) - lo) / span
            var, hexc = _seq_color(frac)
            body.append(f'<rect x="{_c(x + 1)}" y="{_c(y + 1)}" width="{cw - 2}"'
                        f' height="{ch - 2}" rx="2" {_fill(var, hexc)}/>')
            lv, lh = _luma_ink(hexc)
            body.append(_text(x + cw / 2, y + ch / 2 + 4, _fmt(v, value_format),
                              size=10, anchor="middle", var=lv, tabular=True))
    return _svg(W, H, "".join(body), title=title, desc=f"heatmap {len(rl)}×{len(cl)}")


# ── 7. funnel — stage drop-off (values precomputed) ─────────────────────────────

def funnel(stages: Sequence[Mapping[str, Any]], *, title: str = "Funnel",
           value_format: str = "number") -> str:
    """Vertical funnel. Each stage: ``{"label": str, "value": num, "rate"?: num}``.
    Bar width = value / max(value) × plot-width (geometry). Values verbatim; an
    optional precomputed ``rate`` (upstream, not derived here) rides each stage.

    >>> svg = funnel([{"label": "View", "value": 1000}, {"label": "Buy", "value": 120}])
    >>> svg.startswith("<svg") and "1000" in svg and "120" in svg
    True
    """
    st = _as_list(stages, "stages")
    vals = [float(s.get("value")) for s in st]
    mx = max(vals) if max(vals) > 0 else 1.0
    W, rh, T, B = 560, 46, 50, 20
    H = T + len(st) * rh + B
    cx = W / 2
    body = [_text(16, 24, title, size=15, weight="600")]
    for i, s in enumerate(st):
        v = vals[i]
        w = (W - 160) * (v / mx)
        y = T + i * rh
        var, hexc = _cat(0)
        body.append(f'<rect x="{_c(cx - w / 2)}" y="{_c(y + 4)}" width="{_c(w)}"'
                    f' height="{_c(rh - 12)}" rx="3" {_fill(var, hexc)}/>')
        lab = s.get("label", i)
        rate = s.get("rate")
        rtxt = f"  ·  {_fmt(rate, 'percent')}" if isinstance(rate, (int, float)) else ""
        body.append(_text(cx, y + rh / 2 + 4, f"{lab}: {_fmt(v, value_format)}{rtxt}",
                          size=12, anchor="middle", var=_luma_ink(hexc)[0]))
    return _svg(W, H, "".join(body), title=title, desc=f"funnel, {len(st)} stages")


# ── 8. gauge — single ratio against a limit ─────────────────────────────────────

def gauge(value: float, *, maximum: float = 1.0, title: str = "Gauge",
          value_format: str = "percent", status: str | None = None) -> str:
    """Semicircular gauge. Fill arc = value / maximum (geometry). ``status`` (a
    precomputed enum: good/warning/serious/critical) colors the fill; else slot-1.

    >>> svg = gauge(0.82, title="Compliance", status="good")
    >>> svg.startswith("<svg") and "82%" in svg and "<path" in svg
    True
    """
    v = float(value)
    mx = float(maximum) if maximum else 1.0
    frac = 0.0 if v <= 0 else (1.0 if v >= mx else v / mx)
    W, H = 300, 200
    cx, cy, r = 150, 160, 110
    # track: left (-90°) to right (+90°) upper semicircle
    lx, ly = _polar(cx, cy, r, -90)
    rx, ry = _polar(cx, cy, r, 90)
    body = [_text(16, 24, title, size=15, weight="600")]
    body.append(f'<path d="M{_c(lx)},{_c(ly)} A{_c(r)},{_c(r)} 0 0 1 {_c(rx)},{_c(ry)}"'
                f' fill="none" {_stroke("grid", _CHROME_LIGHT["grid"], 16)} stroke-linecap="round"/>')
    ang = -90 + 180 * frac
    ex, ey = _polar(cx, cy, r, ang)
    large = 1 if (ang - (-90)) > 180 else 0
    if status and status in STATUS:
        var, hexc = f"st-{status}", STATUS[status]
    else:
        var, hexc = _cat(0)
    if frac > 0:
        body.append(f'<path d="M{_c(lx)},{_c(ly)} A{_c(r)},{_c(r)} 0 {large} 1 {_c(ex)},{_c(ey)}"'
                    f' fill="none" {_stroke(var, hexc, 16)} stroke-linecap="round"/>')
    body.append(_text(cx, cy - 8, _fmt(v, value_format), size=34, anchor="middle", weight="600", var="ink"))
    if status:
        body.append(_text(cx, cy + 16, status, size=12, anchor="middle", var="ink2"))
    return _svg(W, H, "".join(body), title=title, desc=f"gauge {_fmt(frac,'percent')} of max")


# ── 9. scatter — two-axis / quadrant (values precomputed) ───────────────────────

def scatter(points: Sequence[Mapping[str, Any]], *, title: str = "Scatter",
            x_label: str = "x", y_label: str = "y",
            x_median: float | None = None, y_median: float | None = None) -> str:
    """Scatter / quadrant. Each point: ``{"x": num, "y": num, "label"?: str}``.
    Axes scale to data min/max (geometry). Optional precomputed medians (upstream)
    draw quadrant crosshairs — Rival-IQ benchmark form (review §3 9th primitive).

    >>> svg = scatter([{"x": 3, "y": 5, "label": "A"}, {"x": 7, "y": 2}])
    >>> svg.startswith("<svg") and "<circle" in svg
    True
    """
    pl = _as_list(points, "points")
    xsv = [float(p["x"]) for p in pl]
    ysv = [float(p["y"]) for p in pl]
    xlo, xhi = min(xsv), max(xsv)
    ylo, yhi = min(ysv), max(ysv)
    xsp = (xhi - xlo) or 1.0
    ysp = (yhi - ylo) or 1.0
    W, H = 520, 380
    L, R, T, B = 56, 24, 40, 44
    pw, ph = W - L - R, H - T - B

    def px(x: float) -> float:
        return L + pw * (x - xlo) / xsp

    def py(y: float) -> float:
        return T + ph * (1 - (y - ylo) / ysp)

    body = [_text(16, 24, title, size=15, weight="600")]
    # frame
    body.append(f'<line x1="{_c(L)}" y1="{_c(T + ph)}" x2="{_c(L + pw)}" y2="{_c(T + ph)}"'
                f' {_stroke("axis", _CHROME_LIGHT["axis"], 1)}/>')
    body.append(f'<line x1="{_c(L)}" y1="{_c(T)}" x2="{_c(L)}" y2="{_c(T + ph)}"'
                f' {_stroke("axis", _CHROME_LIGHT["axis"], 1)}/>')
    if x_median is not None:
        xm = px(float(x_median))
        body.append(f'<line x1="{_c(xm)}" y1="{_c(T)}" x2="{_c(xm)}" y2="{_c(T + ph)}"'
                    f' {_stroke("grid", _CHROME_LIGHT["grid"], 1)} stroke-dasharray="4 3"/>')
    if y_median is not None:
        ym = py(float(y_median))
        body.append(f'<line x1="{_c(L)}" y1="{_c(ym)}" x2="{_c(L + pw)}" y2="{_c(ym)}"'
                    f' {_stroke("grid", _CHROME_LIGHT["grid"], 1)} stroke-dasharray="4 3"/>')
    for i, p in enumerate(pl):
        var, hexc = _cat(i)
        cxp, cyp = px(float(p["x"])), py(float(p["y"]))
        body.append(f'<circle cx="{_c(cxp)}" cy="{_c(cyp)}" r="6" {_fill_ring(var, hexc)}/>')
        if p.get("label"):
            body.append(_text(cxp + 9, cyp + 4, p["label"], size=11, var="ink2"))
    body.append(_text(L + pw / 2, H - 10, x_label, size=11, anchor="middle", var="muted"))
    body.append(_text(14, T + ph / 2, y_label, size=11, anchor="middle", var="muted"))
    return _svg(W, H, "".join(body), title=title, desc=f"scatter, {len(pl)} points")


if __name__ == "__main__":  # doctest self-test only — not a CLI (no bootstrap, _lib helper)
    import doctest as _doctest
    import sys as _sys
    _failed, _attempted = _doctest.testmod(verbose="-v" in _sys.argv)
    # byte-determinism smoke: same input → identical bytes
    _a = donut([0.5, 0.3, 0.2], ["A", "B", "C"])
    _b = donut([0.5, 0.3, 0.2], ["A", "B", "C"])
    _det = _a == _b
    print(f"[report_chart self-test] doctests: {_attempted - _failed}/{_attempted} pass; "
          f"byte-determinism: {'ok' if _det else 'FAIL'}")
    _sys.exit(0 if (_failed == 0 and _det) else 1)
