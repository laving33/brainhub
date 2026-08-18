"""Bar chart renderer — pure inline SVG built in Python, no JS, no library.

Same rationale as the line-chart renderer: drawing the whole chart as static
``<svg>`` markup makes static/print correctness automatic (there is no
JS-driven animation to freeze), and it keeps the artifact dependency-free.
This module mirrors that structure — same shared CSS-variable palette, same
document-layer contract (a ``<figure>`` body fragment + optional ``<style>``
head) — so the two chart kinds read as one system.

Spec shape::

    {
      "categories": ["Q1", "Q2", "Q3"],
      "series": [
        {"name": "Revenue", "values": [10, 12, 9]},
        {"name": "Cost", "values": [6, 7, 8]}
      ],
      "y_label": "USD (thousands)",   # optional
      "title": "Quarterly results"    # optional
    }

A single-entry ``series`` list ("values only") renders one bar per category
with no legend. Multiple entries render grouped bars side by side per
category plus a legend.
"""
from __future__ import annotations

import html
import math

from ..registry import RenderPart, RenderRequest, renderer
from . import _chart_base
from ._series_palette import series_color

# Series colors come from the shared, colorblind-validated palette module
# (``_series_palette.series_color``) so the bar- and line-chart renderers stay
# one visual system and cannot drift. It maps series index -> a --series-* CSS
# custom property (fold-to-Other past 8), never a status color. See that module
# and tests/test_render_palette.py.

_WIDTH = 800
_HEIGHT = 480
# Base for the per-chart id prefix; the spec's content hash is appended per
# render (see _chart_base.id_prefix) so two BAR charts on one page differ too.
_ID_BASE = "bh-bar-chart"
_MARGIN_TOP = 30
_MARGIN_RIGHT = 30
_MARGIN_LEFT = 60
_MARGIN_BOTTOM = 60
_LEGEND_HEIGHT = 30
_TICK_COUNT = 5


def _validate(spec: dict) -> None:
    """Raise ValueError on missing/empty categories, missing series, or a
    values-length mismatch. Runs before render_fn (see registry.Renderer)."""
    if not isinstance(spec, dict):
        raise ValueError("bar-chart spec must be a JSON object")
    categories = spec.get("categories")
    if not isinstance(categories, list) or not categories:
        raise ValueError("bar-chart spec requires a non-empty 'categories' list")
    series = spec.get("series")
    if not isinstance(series, list) or not series:
        raise ValueError("bar-chart spec requires a non-empty 'series' list")
    for entry in series:
        if not isinstance(entry, dict):
            raise ValueError("each 'series' entry must be an object")
        values = entry.get("values")
        if not isinstance(values, list) or not values:
            raise ValueError("each series entry requires a non-empty 'values' list")
        if len(values) != len(categories):
            raise ValueError(
                f"series {entry.get('name', '')!r} has {len(values)} values, "
                f"expected {len(categories)} (one per category)"
            )
        for v in values:
            try:
                fv = float(v)
            except (TypeError, ValueError):
                raise ValueError(
                    f"series {entry.get('name', '')!r} contains a non-numeric value: {v!r}"
                ) from None
            if not math.isfinite(fv):
                raise ValueError(
                    f"series {entry.get('name', '')!r} contains a non-finite value (NaN/Infinity): {v!r}"
                )


_fmt_num = _chart_base.fmt_num


_nice_ticks = _chart_base.nice_ticks


@renderer(
    "bar-chart",
    output_kind="chart",
    input_spec=_validate,
    description=(
        "Grouped bar chart — several series per category, in categorical "
        "colours. For one ranked measure in one hue use `bar`. Pure inline SVG, no JS."
    ),
    example={
        "categories": ["台北", "台中"],
        "series": [{"name": "營收", "values": [1, 2]}],
    },
    # Drawn as a <figcaption> above the plot.
    self_titled=True,
)
def render(request: RenderRequest) -> RenderPart:
    spec = request.spec
    categories = [str(c) for c in spec["categories"]]
    series = [
        (str(entry.get("name") or f"Series {i + 1}"), [float(v) for v in entry["values"]])
        for i, entry in enumerate(spec["series"])
    ]
    # The caller's --title outranks the spec's; without it a caller-supplied
    # title vanished entirely — this renderer drew no visible title at all.
    title = request.title or spec.get("title")
    y_label = spec.get("y_label")
    n_categories = len(categories)
    n_series = len(series)

    # RenderRequest.static is a documented no-op here: the chart is plain
    # <svg> markup with zero JS/CSS animation, so there is nothing to freeze
    # for a headless PNG/PDF capture — static correctness holds by construction.
    _ = request.static

    margin_left = _MARGIN_LEFT + (14 if y_label else 0)
    margin_bottom = _MARGIN_BOTTOM + (_LEGEND_HEIGHT if n_series > 1 else 0)
    plot_width = _WIDTH - margin_left - _MARGIN_RIGHT
    plot_height = _HEIGHT - _MARGIN_TOP - margin_bottom

    all_values = [v for _, values in series for v in values]
    y_max_data = max(0.0, max(all_values))
    y_min_data = min(0.0, min(all_values))
    ticks = _nice_ticks(y_min_data, y_max_data)
    y_min, y_max = ticks[0], ticks[-1]
    y_span = (y_max - y_min) or 1.0

    def y_to_px(v: float) -> float:
        return _MARGIN_TOP + (y_max - v) / y_span * plot_height

    zero_px = y_to_px(0.0)

    category_width = plot_width / n_categories
    group_pad_frac = 0.2
    group_width = category_width * (1 - group_pad_frac)
    bar_gap = group_width * 0.08 if n_series > 1 else 0.0
    bar_width = (group_width - bar_gap * (n_series - 1)) / n_series

    parts: list[str] = []

    # ---- gridlines + y-axis tick labels ------------------------------
    for t in ticks:
        ty = y_to_px(t)
        parts.append(
            f'<line x1="{margin_left}" y1="{ty:.2f}" x2="{_WIDTH - _MARGIN_RIGHT}" '
            f'y2="{ty:.2f}" stroke="var(--border)" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{margin_left - 10}" y="{ty:.2f}" text-anchor="end" '
            f'dominant-baseline="middle" font-size="12" fill="var(--muted)">'
            f"{html.escape(_fmt_num(t))}</text>"
        )

    # ---- zero baseline -------------------------------------------------
    parts.append(
        f'<line x1="{margin_left}" y1="{zero_px:.2f}" x2="{_WIDTH - _MARGIN_RIGHT}" '
        f'y2="{zero_px:.2f}" stroke="var(--border)" stroke-width="1.5" />'
    )

    # ---- bars + category labels ----------------------------------------
    for i, category in enumerate(categories):
        group_x = margin_left + i * category_width + (category_width - group_width) / 2
        for j, (name, values) in enumerate(series):
            value = values[i]
            bar_x = group_x + j * (bar_width + bar_gap)
            bar_top = min(zero_px, y_to_px(value))
            bar_height = abs(y_to_px(value) - zero_px)
            color = series_color(j)
            tooltip = (
                f"{category} · {name}: {_fmt_num(value)}"
                if n_series > 1
                else f"{category}: {_fmt_num(value)}"
            )
            parts.append(
                f'<rect x="{bar_x:.2f}" y="{bar_top:.2f}" width="{max(bar_width, 0):.2f}" '
                f'height="{max(bar_height, 0):.2f}" fill="{color}" rx="2">'
                f"<title>{html.escape(tooltip)}</title></rect>"
            )
        label_x = margin_left + i * category_width + category_width / 2
        parts.append(
            f'<text x="{label_x:.2f}" y="{zero_px + 20:.2f}" text-anchor="middle" '
            f'font-size="12" fill="var(--text)">{html.escape(category)}</text>'
        )

    # ---- y axis label ----------------------------------------------------
    if y_label:
        cy = _MARGIN_TOP + plot_height / 2
        parts.append(
            f'<text x="16" y="{cy:.2f}" text-anchor="middle" font-size="12" '
            f'fill="var(--muted)" transform="rotate(-90 16 {cy:.2f})">'
            f"{html.escape(y_label)}</text>"
        )

    # ---- legend (only when there is more than one series) ----------------
    # Shared with line-chart so the two read as one system.
    if n_series > 1:
        parts.extend(
            _chart_base.legend(
                [name for name, _ in series],
                [series_color(j) for j in range(n_series)],
            )
        )

    # role="img" makes the subtree presentational, so the plot's own <text> is
    # hidden from a screen reader. The description therefore CARRIES the data:
    # naming the series without their values leaves a non-sighted reader with
    # nothing to act on.
    svg_title = title or "Bar chart"
    described = "；".join(
        f"{name}：" + "、".join(
            f"{cat} {_fmt_num(v)}" for cat, v in zip(categories, values)
        )
        for name, values in series
    )
    svg_desc = f"長條圖，{n_categories} 個類別、{n_series} 個資料序列。{described}"
    svg = (
        _chart_base.svg_open(
            title=svg_title,
            desc=svg_desc,
            id_prefix=_chart_base.id_prefix(_ID_BASE, spec),
        )
        + "".join(parts)
        + "</svg>"
    )

    table = _chart_base.data_table(
        ["類別", *[name for name, _ in series]],
        [
            [category, *[_fmt_num(values[i]) for _, values in series]]
            for i, category in enumerate(categories)
        ],
        caption=title or "Bar chart",
    )
    body = _chart_base.figure(
        svg, title or "", css_class="brainhub-bar-chart", extra=table
    )
    head = (
        f"<style>{_chart_base.figure_css('brainhub-bar-chart')}"
        f"{_chart_base.DATA_TABLE_CSS}</style>"
    )

    return RenderPart(body=body, head=head, title=title or "Bar chart")
