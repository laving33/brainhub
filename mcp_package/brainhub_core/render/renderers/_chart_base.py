"""Shared geometry, formatting and markup for the inline-SVG chart renderers.

``line_chart`` and ``bar_chart`` are one visual system and were built as two.
Every concern below existed twice, and each copy had drifted into a different
answer — different margins, different legend placement, different caption
position, different font sizes, two number formatters rounding at different
precisions, and two functions both called ``_nice_ticks`` where only one
produced nice numbers (the other divided the range evenly, so a 0–1157 axis
drew ticks at 289.25).

The module name is underscore-prefixed so ``render.load_renderers()`` skips it
— it registers no kind. Same reason as ``_series_palette``.

The vendored ``report_chart`` primitives are a separate system with their own
geometry; nothing here applies to them.
"""
from __future__ import annotations

import hashlib
import html
import json
import math

# ── canvas ───────────────────────────────────────────────────────────────────
WIDTH = 800
HEIGHT = 480

# One set of margins for both charts. Previously 64/24/32/64 and 60/30/30/60 —
# close enough to look like a mistake rather than a decision, far enough apart
# that the two charts' plots did not line up when stacked in one report.
MARGIN_LEFT = 64
MARGIN_RIGHT = 30
MARGIN_TOP = 32
MARGIN_BOTTOM = 60
# Reserved under the plot when a legend is drawn (multi-series only).
LEGEND_HEIGHT = 30

TICK_COUNT = 5

PLOT_LEFT = MARGIN_LEFT
PLOT_RIGHT = WIDTH - MARGIN_RIGHT
PLOT_TOP = MARGIN_TOP


def plot_bottom(with_legend: bool = False) -> float:
    """Bottom of the plot area, leaving room for a legend when there is one."""
    return HEIGHT - MARGIN_BOTTOM - (LEGEND_HEIGHT if with_legend else 0)


# ── numbers ──────────────────────────────────────────────────────────────────
def fmt_num(value: float) -> str:
    """Render a number without a trailing '.0' or float dust.

    Used for both tick labels and SVG coordinates, so it has to stay lossless
    enough for geometry: 4 decimals is under a thousandth of a pixel on this
    canvas and still kills artefacts like 0.30000000000000004.
    """
    rounded = round(value, 4)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.4f}".rstrip("0").rstrip(".")


# d3's tick thresholds are GEOMETRIC midpoints (√50, √10, √2), not the integer
# cutoffs a hand-rolled version reaches for. The difference is not cosmetic: on
# 399 sampled domains the integer form disagreed with d3 on half of them, and
# systematically coarser — a 0–11 axis got a step of 5 (four ticks) where d3
# gives 2 (seven ticks).
_E10 = math.sqrt(50)
_E5 = math.sqrt(10)
_E2 = math.sqrt(2)


def nice_ticks(lo: float, hi: float, count: int = TICK_COUNT) -> list[float]:
    """Dependency-free 'nice numbers' ticks, following d3-array's algorithm.

    Ticks land on 1/2/5 × 10ⁿ so a reader can add them up in their head. A plain
    even division of the range cannot do that: it is what produced axis labels
    like 1.33 and 2.67.
    """
    if lo == hi:
        # Degenerate (single-value) axis: fabricate a span rather than divide by
        # zero, and keep 0 as the floor when the value is 0.
        lo, hi = (0.0, 1.0) if lo == 0 else (lo - 1, hi + 1)
    step = (hi - lo) / max(count, 1)
    power = math.floor(math.log10(step))
    error = step / 10**power
    factor = 10 if error >= _E10 else 5 if error >= _E5 else 2 if error >= _E2 else 1

    # d3.ticks() returns ticks strictly INSIDE the domain, which is right for an
    # axis annotation and wrong for a chart: the caller scales to ticks[0] and
    # ticks[-1], so an inside-only list clips the tallest bar. This is d3's
    # nice() behaviour instead — the domain is widened outward to the enclosing
    # round numbers, so every tick is a round number AND the data fits.
    if power < 0:
        # Fractional steps go through integer multiply/divide rather than
        # repeated addition of a float, which is what keeps the output clean
        # (0.1, 0.2, 0.3 — not 0.30000000000000004).
        inc = 10**-power / factor
        start = math.floor(lo * inc)
        end = math.ceil(hi * inc)
        ticks = [i / inc for i in range(int(start), int(end) + 1)]
    else:
        inc = 10**power * factor
        start = math.floor(lo / inc)
        end = math.ceil(hi / inc)
        ticks = [i * inc for i in range(int(start), int(end) + 1)]
    return [round(t, 10) for t in ticks]


def require_finite(value: object, where: str) -> float:
    """Coerce to float, rejecting NaN/Infinity with a caller-facing message.

    JSON has no NaN, but ``json.loads`` accepts the literals, and an infinite
    coordinate silently produces an SVG path the browser drops — a chart that
    renders blank with nothing in the log.
    """
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"{where} must be a number, got {value!r}") from None
    if math.isnan(number) or math.isinf(number):
        raise ValueError(f"{where} must be finite (no NaN/Infinity), got {value!r}")
    return number


# ── text metrics ─────────────────────────────────────────────────────────────
# Advance widths as a fraction of font size. Estimated, never measured: pure
# Python has no getComputedTextLength, and the font stack resolves to whatever
# the reader's system supplies, so a "precise" number would be precise about
# the wrong face. Rounded UP so the estimate reports an overflow slightly
# before a real one, never after.
_ADVANCE_CJK = 1.0  # full-width: CJK, fullwidth forms, most CJK punctuation
_ADVANCE_UPPER = 0.67
_ADVANCE_DIGIT = 0.55
_ADVANCE_OTHER = 0.5


def estimate_text_width(text: str, size: float) -> float:
    """Approximate the rendered width of ``text`` at ``size`` px.

    Exists because layout constants written for Latin digits silently truncate
    Chinese: a CJK glyph is a full em against roughly 0.55 for a digit, so a
    label gutter sized for "1,234" clips at a third as many characters of 中文.
    """
    total = 0.0
    for ch in text:
        code = ord(ch)
        if (
            0x1100 <= code <= 0x115F
            or 0x2E80 <= code <= 0xA4CF
            or 0xAC00 <= code <= 0xD7A3
            or 0xF900 <= code <= 0xFAFF
            or 0xFE30 <= code <= 0xFE6F
            or 0xFF00 <= code <= 0xFF60
            or 0xFFE0 <= code <= 0xFFE6
        ):
            total += _ADVANCE_CJK
        elif ch.isdigit():
            total += _ADVANCE_DIGIT
        elif ch.isupper():
            total += _ADVANCE_UPPER
        else:
            total += _ADVANCE_OTHER
    return total * size


# ── markup ───────────────────────────────────────────────────────────────────
def id_prefix(kind: str, spec: dict) -> str:
    """A per-CHART id prefix, derived from the spec's content.

    A module-level constant only separates one kind from another; two line
    charts on the same page still emitted ``id="bh-line-chart-title"`` twice,
    and a screen reader announces the second with the first one's name. A
    content hash keeps the output deterministic — the same spec must produce
    byte-identical SVG for caching and diffing — while separating instances.
    Two identical charts still collide, and that is harmless: either target
    carries the same text.
    """
    canonical = json.dumps(spec, sort_keys=True, ensure_ascii=False, default=str)
    return f"{kind}-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:8]}"


def svg_open(*, title: str, desc: str, id_prefix: str, extra_style: str = "") -> str:
    """Open an ``<svg>`` that satisfies the accessible-name contract.

    ``<title>`` is the FIRST child, before any ``<defs>``/``<style>``: assistive
    tech may ignore one placed later. ``aria-labelledby`` names both the title
    and the description, because a ``<desc>`` nothing references is widely not
    announced at all. Ids carry a renderer prefix so two charts on one page
    cannot collide — with bare ``id="title"`` the second would be announced with
    the first one's name.

    No ``xmlns``: this is inlined into an HTML5 document, where the parser puts
    it in the SVG namespace on its own. It also keeps the artifact free of a
    literal "http://" that self-containment greps would flag.
    """
    return (
        f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
        f'aria-labelledby="{id_prefix}-title {id_prefix}-desc" '
        f'style="max-width:100%;height:auto;font-family:inherit;{extra_style}">'
        f'<title id="{id_prefix}-title">{html.escape(title)}</title>'
        f'<desc id="{id_prefix}-desc">{html.escape(desc)}</desc>'
    )


def y_gridlines(ticks: list[float], scale_y, *, label_size: int = 12) -> list[str]:
    """Horizontal gridlines with their value labels, left of the plot."""
    parts: list[str] = []
    for tick in ticks:
        y = scale_y(tick)
        parts.append(
            f'<line x1="{PLOT_LEFT}" y1="{fmt_num(y)}" x2="{PLOT_RIGHT}" '
            f'y2="{fmt_num(y)}" stroke="var(--border)" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{PLOT_LEFT - 10}" y="{fmt_num(y)}" text-anchor="end" '
            f'dominant-baseline="middle" font-size="{label_size}" '
            f'fill="var(--muted)">{html.escape(fmt_num(tick))}</text>'
        )
    return parts


def y_axis_label(text: str, *, with_legend: bool = False, size: int = 12) -> str:
    """Rotated y-axis caption, vertically centred on the plot."""
    mid = (PLOT_TOP + plot_bottom(with_legend)) / 2
    x = 18
    return (
        f'<text x="{x}" y="{fmt_num(mid)}" text-anchor="middle" font-size="{size}" '
        f'fill="var(--muted)" transform="rotate(-90 {x} {fmt_num(mid)})">'
        f"{html.escape(text)}</text>"
    )


def legend(names: list[str], colors: list[str], *, swatch: str = "square") -> list[str]:
    """One horizontal legend strip under the plot, for both chart kinds.

    Under the plot rather than floating inside it: a legend placed in the plot
    area (where the line chart used to put it) overlaps the data as soon as the
    series rise into that corner, and nothing in the renderer checks.
    """
    parts: list[str] = []
    y = HEIGHT - MARGIN_BOTTOM + 34
    x = PLOT_LEFT
    for name, color in zip(names, colors):
        if swatch == "line":
            parts.append(
                f'<line x1="{fmt_num(x)}" y1="{y - 4}" x2="{fmt_num(x + 14)}" '
                f'y2="{y - 4}" stroke="{color}" stroke-width="3" '
                'stroke-linecap="round" />'
            )
        else:
            parts.append(
                f'<rect x="{fmt_num(x)}" y="{y - 10}" width="12" height="12" '
                f'rx="2" fill="{color}" />'
            )
        parts.append(
            f'<text x="{fmt_num(x + 20)}" y="{y - 4}" dominant-baseline="middle" '
            f'font-size="12" fill="var(--text)">{html.escape(name)}</text>'
        )
        x += 26 + max(len(name) * 8, 40)
    return parts


def figure(svg: str, title: str, *, css_class: str, extra: str = "") -> str:
    """Wrap a chart SVG in a ``<figure>`` with its caption ABOVE the plot.

    Above, for both kinds: a caption under one chart and over the next reads as
    belonging to the wrong figure when two are stacked in a report. ``extra``
    goes after the plot — that is where the data table belongs.
    """
    caption = (
        f'<figcaption class="{css_class}-title">{html.escape(title)}</figcaption>'
        if title
        else ""
    )
    return f'<figure class="{css_class}">{caption}{svg}{extra}</figure>'


def data_table(headers: list[str], rows: list[list[str]], *, caption: str) -> str:
    """A collapsible table carrying the chart's numbers.

    WCAG 1.1.1 asks a complex image for a text alternative that "serves the
    equivalent purpose", and W3C's own technique for charts is a data table.
    A ``<desc>`` cannot do that job alone: it is announced as one run of speech
    with no way to compare two values, and ``role="img"`` hides the plot's own
    labels, so without this the numbers exist nowhere a screen reader can reach.

    Plain markup, no JS — ``<details>`` works with the artifact's script-src, and
    the document layer already forces every ``<details>`` open when printing, so
    the table lands in the PDF too.
    """
    if not headers or not rows:
        return ""
    head = "".join(f'<th scope="col">{html.escape(h)}</th>' for h in headers)
    body = "".join(
        "<tr>"
        + "".join(
            f'<th scope="row">{html.escape(cell)}</th>' if i == 0
            else f"<td>{html.escape(cell)}</td>"
            for i, cell in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    return (
        '<details class="bh-chart-data">'
        f"<summary>檢視資料表格</summary>"
        f"<table><caption>{html.escape(caption)}</caption>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
        "</details>"
    )


DATA_TABLE_CSS = (
    ".bh-chart-data{margin-top:10px;font-size:13px;}"
    ".bh-chart-data summary{cursor:pointer;color:var(--muted);}"
    ".bh-chart-data table{border-collapse:collapse;margin-top:8px;}"
    ".bh-chart-data caption{text-align:left;color:var(--muted);padding-bottom:4px;}"
    ".bh-chart-data th,.bh-chart-data td{border:1px solid var(--border);"
    "padding:4px 10px;text-align:right;}"
    ".bh-chart-data th[scope=row]{text-align:left;font-weight:500;}"
)


def figure_css(css_class: str) -> str:
    """Shared caption/figure styling, so both charts present identically."""
    return (
        f".{css_class}{{margin:0;}}"
        f".{css_class}-title{{font-size:1rem;font-weight:600;color:var(--text);"
        f"margin:0 0 8px;}}"
        f".{css_class} svg{{display:block;}}"
    )
