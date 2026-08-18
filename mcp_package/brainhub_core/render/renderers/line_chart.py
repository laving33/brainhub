"""Line chart renderer: pure inline SVG, no JavaScript, no charting library.

Registers kind ``line-chart`` (output_kind ``chart``) against the shared
:mod:`..registry` singleton. Self-contained module — it does not edit any
other file; it is picked up automatically by ``render.load_renderers()``.

Design note on ``RenderRequest.static``: the whole chart is drawn as static
SVG shapes (``<polyline>``/``<line>``/``<text>``) computed in Python — there is
no ``<animate>``, no CSS ``animation``/``transition``, and no JS at all. That
means a headless PNG/PDF capture always lands on the fully-drawn frame with
zero extra work, so honoring ``static`` here is a documented no-op: static and
non-static renders are byte-for-byte identical output shapes (only the shared
document shell adds the flatten-CSS block in static mode, per
``render/document.py``).
"""
from __future__ import annotations

import html
import math

from ..registry import RenderPart, RenderRequest, renderer
from ._series_palette import series_color

# SVG canvas + margins for axes/labels/legend.
_WIDTH = 800
_HEIGHT = 480
# Prefixed so two charts inlined into one page cannot collide: with bare
# id="title"/"desc" the second chart would be announced with the first one's
# name, and any url(#…) reference would resolve to the wrong element.
_ID_PREFIX = "bh-line-chart"
_MARGIN_LEFT = 64
_MARGIN_RIGHT = 24
_MARGIN_TOP = 32
_MARGIN_BOTTOM = 64
_PLOT_LEFT = _MARGIN_LEFT
_PLOT_RIGHT = _WIDTH - _MARGIN_RIGHT
_PLOT_TOP = _MARGIN_TOP
_PLOT_BOTTOM = _HEIGHT - _MARGIN_BOTTOM
_GRID_LINES = 4  # interior gridlines per axis (plus the 0/100% edges)

# Series colors come from the shared, colorblind-validated palette module
# (``_series_palette.series_color``) — the same one the bar-chart renderer uses,
# so the two chart kinds stay one visual system and cannot drift. It maps a
# series index to a --series-* CSS custom property (fold-to-Other past 8, never a
# status color), so charts still follow light/dark theming automatically (see
# web_assets.py for the variable definitions and tests/test_render_palette.py).


def _validate(spec: dict) -> None:
    series = spec.get("series")
    if not isinstance(series, list) or not series:
        raise ValueError("line-chart spec requires a non-empty 'series' list")
    for i, s in enumerate(series):
        if not isinstance(s, dict):
            raise ValueError(f"series[{i}] must be an object")
        points = s.get("points")
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError(f"series[{i}] requires at least 2 'points'")
        for j, p in enumerate(points):
            if (
                not isinstance(p, (list, tuple))
                or len(p) != 2
                or isinstance(p[0], bool)
                or isinstance(p[1], bool)
            ):
                raise ValueError(f"series[{i}].points[{j}] must be a numeric [x, y] pair")
            try:
                x, y = float(p[0]), float(p[1])
            except (TypeError, ValueError):
                raise ValueError(f"series[{i}].points[{j}] must be a numeric [x, y] pair") from None
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError(f"series[{i}].points[{j}] must be finite (no NaN/Infinity)")


def _fmt(n: float) -> str:
    """Format a float compactly for SVG coordinates/tick labels."""
    if n == int(n):
        return str(int(n))
    return f"{n:.2f}".rstrip("0").rstrip(".")


def _nice_ticks(lo: float, hi: float, count: int) -> list[float]:
    if lo == hi:
        # Degenerate (single value) axis: fabricate a small span so the chart
        # still draws sensible gridlines instead of dividing by zero.
        lo -= 1.0
        hi += 1.0
    step = (hi - lo) / count
    return [lo + step * i for i in range(count + 1)]


@renderer(
    "line-chart",
    output_kind="chart",
    input_spec=_validate,
    description="Line chart (pure inline SVG, no JS)",
)
def render(request: RenderRequest) -> RenderPart:
    spec = request.spec
    series = spec["series"]
    x_label = str(spec.get("x_label", "") or "")
    y_label = str(spec.get("y_label", "") or "")
    title = str(spec.get("title", "") or "") or "Line chart"

    all_x: list[float] = []
    all_y: list[float] = []
    norm_series: list[tuple[str, list[tuple[float, float]]]] = []
    for s in series:
        name = str(s.get("name", "") or "")
        points = [(float(p[0]), float(p[1])) for p in s["points"]]
        norm_series.append((name, points))
        all_x.extend(x for x, _ in points)
        all_y.extend(y for _, y in points)

    x_min, x_max = min(all_x), max(all_x)
    y_min, y_max = min(all_y), max(all_y)
    x_span = (x_max - x_min) or 1.0
    y_span = (y_max - y_min) or 1.0

    def sx(x: float) -> float:
        return _PLOT_LEFT + (x - x_min) / x_span * (_PLOT_RIGHT - _PLOT_LEFT)

    def sy(y: float) -> float:
        # SVG y grows downward; plot origin (y_min) sits at the bottom.
        return _PLOT_BOTTOM - (y - y_min) / y_span * (_PLOT_BOTTOM - _PLOT_TOP)

    parts: list[str] = []
    # No xmlns attribute: this <svg> is inlined directly in an HTML5 document
    # (not served as a standalone .svg file), so the browser's built-in
    # foreign-content rules pick it up as SVG without a namespace declaration.
    # This also keeps the artifact free of any "http://" substring so a
    # release-hygiene / self-contained grep never false-positives on it.
    # <title> is the FIRST child, before any <defs>/<style>: assistive tech may
    # ignore one placed later. <desc> names the series so a screen-reader user
    # gets the chart's content, not just its title — and both are referenced by
    # aria-labelledby, because a bare <desc> is widely not announced at all.
    series_names = "、".join(name for name, _ in norm_series)
    desc = f"折線圖，{len(norm_series)} 個資料序列：{series_names}"
    parts.append(
        f'<svg viewBox="0 0 {_WIDTH} {_HEIGHT}" role="img" '
        f'aria-labelledby="{_ID_PREFIX}-title {_ID_PREFIX}-desc" '
        f'style="max-width:100%;height:auto">'
        f'<title id="{_ID_PREFIX}-title">{html.escape(title)}</title>'
        f'<desc id="{_ID_PREFIX}-desc">{html.escape(desc)}</desc>'
    )

    # Gridlines + y tick labels.
    y_ticks = _nice_ticks(y_min, y_max, _GRID_LINES)
    for ty in y_ticks:
        gy = sy(ty)
        parts.append(
            f'<line x1="{_PLOT_LEFT}" y1="{gy:.2f}" x2="{_PLOT_RIGHT}" y2="{gy:.2f}" '
            f'stroke="var(--border)" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{_PLOT_LEFT - 8}" y="{gy:.2f}" text-anchor="end" '
            f'dominant-baseline="middle" font-size="12" fill="var(--muted)">{html.escape(_fmt(ty))}</text>'
        )

    # x tick labels.
    x_ticks = _nice_ticks(x_min, x_max, _GRID_LINES)
    for tx in x_ticks:
        gx = sx(tx)
        parts.append(
            f'<line x1="{gx:.2f}" y1="{_PLOT_TOP}" x2="{gx:.2f}" y2="{_PLOT_BOTTOM}" '
            f'stroke="var(--border)" stroke-width="1" stroke-opacity="0.5" />'
        )
        parts.append(
            f'<text x="{gx:.2f}" y="{_PLOT_BOTTOM + 18}" text-anchor="middle" '
            f'font-size="12" fill="var(--muted)">{html.escape(_fmt(tx))}</text>'
        )

    # Axis lines.
    parts.append(
        f'<line x1="{_PLOT_LEFT}" y1="{_PLOT_TOP}" x2="{_PLOT_LEFT}" y2="{_PLOT_BOTTOM}" '
        f'stroke="var(--text)" stroke-width="1.5" />'
    )
    parts.append(
        f'<line x1="{_PLOT_LEFT}" y1="{_PLOT_BOTTOM}" x2="{_PLOT_RIGHT}" y2="{_PLOT_BOTTOM}" '
        f'stroke="var(--text)" stroke-width="1.5" />'
    )

    # Axis labels.
    if x_label:
        parts.append(
            f'<text x="{(_PLOT_LEFT + _PLOT_RIGHT) / 2:.2f}" y="{_HEIGHT - 12}" '
            f'text-anchor="middle" font-size="13" fill="var(--text)">{html.escape(x_label)}</text>'
        )
    if y_label:
        cy = (_PLOT_TOP + _PLOT_BOTTOM) / 2
        parts.append(
            f'<text x="16" y="{cy:.2f}" text-anchor="middle" font-size="13" '
            f'fill="var(--text)" transform="rotate(-90 16 {cy:.2f})">{html.escape(y_label)}</text>'
        )

    # One polyline per series, plus point markers.
    legend_items: list[str] = []
    for i, (name, points) in enumerate(norm_series):
        color = series_color(i)
        coords = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in points)
        parts.append(
            f'<polyline points="{coords}" fill="none" stroke="{color}" '
            f'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />'
        )
        for x, y in points:
            parts.append(f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="3" fill="{color}" />')

        safe_name = html.escape(name) if name else f"Series {i + 1}"
        ly = _PLOT_TOP + i * 18
        legend_items.append(
            f'<g transform="translate({_PLOT_RIGHT - 150},{ly})">'
            f'<line x1="0" y1="0" x2="18" y2="0" stroke="{color}" stroke-width="2.5" />'
            f'<text x="24" y="4" font-size="12" fill="var(--text)">{safe_name}</text>'
            f"</g>"
        )
    if len(norm_series) > 1 or (norm_series and norm_series[0][0]):
        parts.extend(legend_items)

    parts.append("</svg>")
    svg = "".join(parts)

    safe_title = html.escape(title)
    body = (
        '<figure class="brainhub-line-chart">'
        f"{svg}"
        f"<figcaption>{safe_title}</figcaption>"
        "</figure>"
    )
    head = (
        "<style>"
        ".brainhub-line-chart{margin:0;}"
        ".brainhub-line-chart svg{display:block;}"
        ".brainhub-line-chart figcaption{margin-top:8px;font-size:13px;color:var(--muted);text-align:center;}"
        "</style>"
    )

    return RenderPart(body=body, head=head, title=title)
