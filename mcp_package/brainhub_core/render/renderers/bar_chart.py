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
from ._series_palette import series_color

# Series colors come from the shared, colorblind-validated palette module
# (``_series_palette.series_color``) so the bar- and line-chart renderers stay
# one visual system and cannot drift. It maps series index -> a --series-* CSS
# custom property (fold-to-Other past 8), never a status color. See that module
# and tests/test_render_palette.py.

_WIDTH = 800
_HEIGHT = 480
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


def _fmt_num(value: float) -> str:
    """Render a number without a noisy trailing '.0' or float dust."""
    rounded = round(value, 4)
    if rounded == int(rounded):
        return str(int(rounded))
    text = f"{rounded:.4f}".rstrip("0").rstrip(".")
    return text


def _nice_ticks(y_min: float, y_max: float, count: int = _TICK_COUNT) -> list[float]:
    """Small dependency-free 'nice numbers' tick generator (like d3.ticks)."""
    if y_min == y_max:
        y_min, y_max = (0.0, 1.0) if y_min == 0 else (y_min - 1, y_max + 1)
    span = y_max - y_min
    raw_step = span / max(count, 1)
    magnitude = 10 ** math.floor(math.log10(raw_step)) if raw_step > 0 else 1
    residual = raw_step / magnitude
    if residual > 5:
        nice = 10
    elif residual > 2:
        nice = 5
    elif residual > 1:
        nice = 2
    else:
        nice = 1
    step = nice * magnitude
    start = math.floor(y_min / step) * step
    end = math.ceil(y_max / step) * step
    n_steps = round((end - start) / step)
    return [round(start + i * step, 10) for i in range(n_steps + 1)]


@renderer(
    "bar-chart",
    output_kind="chart",
    input_spec=_validate,
    description="Bar chart (pure inline SVG, no JS)",
)
def render(request: RenderRequest) -> RenderPart:
    spec = request.spec
    categories = [str(c) for c in spec["categories"]]
    series = [
        (str(entry.get("name") or f"Series {i + 1}"), [float(v) for v in entry["values"]])
        for i, entry in enumerate(spec["series"])
    ]
    title = spec.get("title")
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
    if n_series > 1:
        legend_y = _HEIGHT - _MARGIN_BOTTOM / 2
        entry_width = plot_width / n_series
        for j, (name, _values) in enumerate(series):
            lx = margin_left + j * entry_width
            color = series_color(j)
            parts.append(
                f'<rect x="{lx:.2f}" y="{legend_y - 9:.2f}" width="12" height="12" '
                f'fill="{color}" rx="2" />'
            )
            parts.append(
                f'<text x="{lx + 18:.2f}" y="{legend_y:.2f}" dominant-baseline="middle" '
                f'font-size="12" fill="var(--text)">{html.escape(name)}</text>'
            )

    svg = (
        f'<svg viewBox="0 0 {_WIDTH} {_HEIGHT}" role="img" '
        f'aria-label="{html.escape(title or "Bar chart")}" '
        'style="max-width:100%;height:auto;font-family:inherit;">'
        + "".join(parts)
        + "</svg>"
    )

    caption = (
        f'<figcaption class="bh-bar-chart-title">{html.escape(title)}</figcaption>'
        if title
        else ""
    )
    body = f'<figure class="bh-bar-chart">{caption}{svg}</figure>'

    head = (
        "<style>"
        ".bh-bar-chart{margin:0;padding:0;}"
        ".bh-bar-chart-title{font-size:1rem;font-weight:600;color:var(--text);"
        "margin-bottom:0.5rem;}"
        ".bh-bar-chart svg text{font-family:inherit;}"
        "</style>"
    )

    return RenderPart(body=body, head=head, title=title or "Bar chart")
