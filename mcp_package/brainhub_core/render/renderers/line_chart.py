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
from . import _chart_base
from ._series_palette import series_color

# SVG canvas + margins for axes/labels/legend.
_WIDTH = 800
_HEIGHT = 480
# Base for the per-chart id prefix. A constant alone only separates line from
# bar — two LINE charts on one page still emitted the same ids, and a screen
# reader announced the second with the first one's name. The spec's content
# hash is appended per render; see _chart_base.id_prefix.
_ID_BASE = "bh-line-chart"
_MARGIN_LEFT = 64
_MARGIN_RIGHT = 24
_MARGIN_TOP = 32
_MARGIN_BOTTOM = 64
_PLOT_LEFT = _MARGIN_LEFT
_PLOT_RIGHT = _WIDTH - _MARGIN_RIGHT
_PLOT_TOP = _MARGIN_TOP
# Set per render: a legend needs room under the plot, or it lands on the
# x-axis labels (it did — the legend printed over the bottom y tick).
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


_fmt = _chart_base.fmt_num


_nice_ticks = _chart_base.nice_ticks


@renderer(
    "line-chart",
    output_kind="chart",
    input_spec=_validate,
    description=(
        "Line chart on a numeric x axis — points are [x, y] pairs, so x may be "
        "irregular. For evenly spaced categories use `line`. Pure inline SVG, no JS."
    ),
    example={
        "x_labels": ["一月", "二月"],
        "series": [{"name": "營收", "points": [[0, 1], [1, 2]]}],
    },
    # Drawn as a <figcaption> under the plot.
    self_titled=True,
)
def render(request: RenderRequest) -> RenderPart:
    spec = request.spec
    series = spec["series"]
    x_label = str(spec.get("x_label", "") or "")
    y_label = str(spec.get("y_label", "") or "")
    # The caller's --title outranks the spec's; without it the figcaption read
    # "Line chart" while the document was titled something else.
    title = request.title or str(spec.get("title", "") or "") or "Line chart"

    all_x: list[float] = []
    all_y: list[float] = []
    norm_series: list[tuple[str, list[tuple[float, float]]]] = []
    for s in series:
        name = str(s.get("name", "") or "")
        points = [(float(p[0]), float(p[1])) for p in s["points"]]
        norm_series.append((name, points))
        all_x.extend(x for x, _ in points)
        all_y.extend(y for _, y in points)

    # A legend is drawn under the plot, so the plot has to end higher or the
    # two overlap — the legend used to print across the bottom y tick label.
    has_legend = len(norm_series) > 1 or (norm_series and norm_series[0][0])
    plot_bottom = _chart_base.plot_bottom(bool(has_legend))

    x_min, x_max = min(all_x), max(all_x)
    # Ticks first, then scale to THEM: nice_ticks widens the range outward to
    # round numbers, so scaling to the raw data range instead puts the outermost
    # tick outside the plot — the bottom label printed below the x axis.
    y_ticks = _nice_ticks(min(all_y), max(all_y), _GRID_LINES)
    x_ticks = _nice_ticks(x_min, x_max, _GRID_LINES)
    y_min, y_max = y_ticks[0], y_ticks[-1]
    x_span = (x_max - x_min) or 1.0
    y_span = (y_max - y_min) or 1.0

    def sx(x: float) -> float:
        return _PLOT_LEFT + (x - x_min) / x_span * (_PLOT_RIGHT - _PLOT_LEFT)

    def sy(y: float) -> float:
        # SVG y grows downward; plot origin (y_min) sits at the bottom.
        return plot_bottom - (y - y_min) / y_span * (plot_bottom - _PLOT_TOP)

    parts: list[str] = []
    # role="img" makes the subtree presentational, so every <text> in the plot
    # is hidden from a screen reader. The description therefore has to CARRY the
    # data, not just describe the shape: "1 series over 3 points" tells a
    # non-sighted reader nothing they could act on.
    id_prefix = _chart_base.id_prefix(_ID_BASE, spec)
    described = "；".join(
        f"{name} 由 {_fmt(points[0][1])} 至 {_fmt(points[-1][1])}"
        for name, points in norm_series
        if points
    )
    desc = f"折線圖，{len(norm_series)} 個資料序列：{described}"
    parts.append(
        _chart_base.svg_open(title=title, desc=desc, id_prefix=id_prefix)
    )

    # Gridlines + y tick labels.
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
    for tx in x_ticks:
        gx = sx(tx)
        parts.append(
            f'<line x1="{gx:.2f}" y1="{_PLOT_TOP}" x2="{gx:.2f}" y2="{plot_bottom}" '
            f'stroke="var(--border)" stroke-width="1" stroke-opacity="0.5" />'
        )
        parts.append(
            f'<text x="{gx:.2f}" y="{plot_bottom + 18}" text-anchor="middle" '
            f'font-size="12" fill="var(--muted)">{html.escape(_fmt(tx))}</text>'
        )

    # Axis lines.
    parts.append(
        f'<line x1="{_PLOT_LEFT}" y1="{_PLOT_TOP}" x2="{_PLOT_LEFT}" y2="{plot_bottom}" '
        f'stroke="var(--text)" stroke-width="1.5" />'
    )
    parts.append(
        f'<line x1="{_PLOT_LEFT}" y1="{plot_bottom}" x2="{_PLOT_RIGHT}" y2="{plot_bottom}" '
        f'stroke="var(--text)" stroke-width="1.5" />'
    )

    # Axis labels.
    if x_label:
        parts.append(
            f'<text x="{(_PLOT_LEFT + _PLOT_RIGHT) / 2:.2f}" y="{_HEIGHT - 12}" '
            f'text-anchor="middle" font-size="13" fill="var(--text)">{html.escape(x_label)}</text>'
        )
    if y_label:
        cy = (_PLOT_TOP + plot_bottom) / 2
        parts.append(
            f'<text x="16" y="{cy:.2f}" text-anchor="middle" font-size="13" '
            f'fill="var(--text)" transform="rotate(-90 16 {cy:.2f})">{html.escape(y_label)}</text>'
        )

    # One polyline per series, plus point markers.
    legend_names: list[str] = []
    legend_colors: list[str] = []
    for i, (name, points) in enumerate(norm_series):
        color = series_color(i)
        coords = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in points)
        parts.append(
            f'<polyline points="{coords}" fill="none" stroke="{color}" '
            f'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />'
        )
        for x, y in points:
            parts.append(f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="3" fill="{color}" />')

        legend_names.append(name if name else f"Series {i + 1}")
        legend_colors.append(color)

    # One legend strip under the plot, shared with bar-chart. It used to float
    # inside the plot at PLOT_RIGHT-150, which collides with the data the moment
    # a series rises into that corner — and nothing checked.
    if has_legend:
        parts.extend(_chart_base.legend(legend_names, legend_colors, swatch="line"))

    parts.append("</svg>")
    svg = "".join(parts)

    table = _chart_base.data_table(
        ["序列", "x", "y"],
        [
            [name or f"Series {i + 1}", _fmt(x), _fmt(y)]
            for i, (name, points) in enumerate(norm_series)
            for x, y in points
        ],
        caption=title,
    )
    body = _chart_base.figure(
        svg, title, css_class="brainhub-line-chart", extra=table
    )
    head = (
        f"<style>{_chart_base.figure_css('brainhub-line-chart')}"
        f"{_chart_base.DATA_TABLE_CSS}</style>"
    )

    return RenderPart(body=body, head=head, title=title)
