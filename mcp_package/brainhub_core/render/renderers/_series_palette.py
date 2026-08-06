"""Shared categorical chart series palette (bar-chart + line-chart).

One source of truth for the series colors so the two inline-SVG chart renderers
cannot drift. The hex values live in the theme CSS custom properties
(``web_assets.py`` ``--series-1``..``--series-8`` / ``--series-other``, defined
for BOTH light and dark scopes); here we only reference them as ``var(--…)`` so
charts follow light/dark theming automatically with no per-renderer hex.

The palette is FIXED-ORDER and colorblind-validated — the dataviz reference
palette, checked by ``scripts/validate_palette.py`` and pinned by
``tests/test_render_palette.py``. It deliberately contains NO status colors: a
chart series must never borrow ``--ok`` (status green) or ``--caution`` (status
amber), which would make series 2/3 read as "good"/"warning" — a fake semantic
unrelated to the data. That was the bug this module replaced.

The module name is underscore-prefixed so ``render.load_renderers()`` skips it
(it registers no renderer kind); it is imported directly by the chart modules.
"""
from __future__ import annotations

# CSS custom properties, in fixed slot order. Consumed as SVG fill/stroke.
SERIES_TOKENS: list[str] = [f"var(--series-{i})" for i in range(1, 9)]
# Neutral gray for the 9th+ series (see series_color).
SERIES_OTHER = "var(--series-other)"


def series_color(index: int) -> str:
    """Return the color token for the ``index``-th series (0-based).

    Slots 0..7 map to ``--series-1``..``--series-8``. Index 8 and beyond FOLD to
    the neutral ``--series-other`` rather than wrapping back to slot 0 — a
    repeated hue reads as "same category", which is a lie once you have more than
    eight series. Fold-to-Other, never cycle.
    """
    if 0 <= index < len(SERIES_TOKENS):
        return SERIES_TOKENS[index]
    return SERIES_OTHER
