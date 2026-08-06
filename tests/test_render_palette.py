"""Gate for the categorical chart series palette.

Locks three things the July-2026 palette bug got wrong:

1. The shipped ``--series-1``..``--series-8`` hexes (light AND dark, read from
   ``web_assets.CSS`` — the real shipping values, not a copy) PASS the vendored
   colorblind validator. A NEGATIVE CONTROL (two near-identical blues) must FAIL
   the same validator — otherwise the gate proves nothing.
2. The renderers color series from ``--series-*`` and fold the 9th+ series to a
   neutral ``--series-other`` instead of cycling/repeating a hue.
3. No chart MARK (bar/line/legend swatch) is filled with a status color
   (``--ok``/``--caution``) or the near-invisible axis ink (``--muted``); those
   were the fake-semantics defects.
"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

from mcp_package.brainhub_core import render
from mcp_package.brainhub_core.render.renderers._series_palette import (
    SERIES_OTHER,
    SERIES_TOKENS,
    series_color,
)
from mcp_package.brainhub_core.web_assets import CSS

_VALIDATOR = Path(__file__).resolve().parents[1] / "scripts" / "validate_palette.py"

# The validated dataviz reference palette, pinned. Editing a shipped hex must
# break this test (and then be re-run through the validator) — a silent palette
# edit is exactly how the status-color regression slipped in.
EXPECTED_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
                  "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
EXPECTED_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500",
                 "#d55181", "#008300", "#9085e9", "#e66767"]
# Task-specified validation surfaces (dataviz reference light/dark surfaces).
SURFACE = {"light": "#fcfcfb", "dark": "#1a1a19"}

# Colors that must NEVER appear as a chart-mark fill/stroke: --ok/--caution are
# status colors (fake "good"/"warning" semantics on data series); --muted is
# axis ink (near-invisible as a series, clashes with gridlines).
_FORBIDDEN_MARK_COLORS = {
    "var(--ok)", "var(--caution)", "var(--muted)",
    "var(--accent)", "var(--link)", "var(--accent-soft)",
}


def _series_hexes(token_index: int) -> list[str]:
    """All ``--series-<token_index>: #hex`` values in web_assets.CSS, in document
    order. Expect exactly 3 (one light :root block + two dark scopes)."""
    return re.findall(rf"--series-{token_index}:\s*(#[0-9a-fA-F]{{6}})", CSS)


def _run_validator(palette_csv: str, mode: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_VALIDATOR), palette_csv,
         "--mode", mode, "--surface", SURFACE[mode]],
        capture_output=True, text=True,
    )


class SeriesPaletteTokensTests(unittest.TestCase):
    def test_tokens_defined_for_light_and_dark_and_match_validated_values(self):
        # Each --series-N is defined in all three theme scopes (1 light + 2 dark),
        # so "defined for BOTH light and dark" is verified mechanically, and the
        # two dark scopes agree with each other.
        light, dark = [], []
        for n in range(1, 9):
            hexes = _series_hexes(n)
            self.assertEqual(
                len(hexes), 3,
                f"--series-{n} should be defined in 3 scopes (1 light + 2 dark), got {hexes}",
            )
            self.assertEqual(hexes[1].lower(), hexes[2].lower(),
                             f"--series-{n} dark scopes disagree: {hexes[1]} vs {hexes[2]}")
            light.append(hexes[0].lower())
            dark.append(hexes[1].lower())
        self.assertEqual(light, EXPECTED_LIGHT)
        self.assertEqual(dark, EXPECTED_DARK)
        # --series-other is likewise defined in all three scopes.
        self.assertEqual(len(re.findall(r"--series-other:\s*#[0-9a-fA-F]{6}", CSS)), 3)

    def test_no_status_color_left_in_series_tokens(self):
        # The 8 series tokens are all --series-* var()s, never --ok/--caution/etc.
        self.assertEqual(SERIES_TOKENS, [f"var(--series-{i})" for i in range(1, 9)])
        for tok in SERIES_TOKENS:
            self.assertNotIn(tok, _FORBIDDEN_MARK_COLORS)


class ValidatorGateTests(unittest.TestCase):
    """The gate itself: real hexes PASS, a deliberately-bad palette FAILS."""

    def test_light_palette_passes(self):
        r = _run_validator(",".join(EXPECTED_LIGHT), "light")
        self.assertEqual(r.returncode, 0, f"light palette should PASS:\n{r.stdout}\n{r.stderr}")
        self.assertIn("ALL CHECKS PASS", r.stdout)

    def test_dark_palette_passes(self):
        r = _run_validator(",".join(EXPECTED_DARK), "dark")
        self.assertEqual(r.returncode, 0, f"dark palette should PASS:\n{r.stdout}\n{r.stderr}")
        self.assertIn("ALL CHECKS PASS", r.stdout)

    def test_negative_control_bad_palette_fails(self):
        # Two near-identical blues: if the validator does not FAIL this, the gate
        # is worthless. Proves it actually catches indistinguishable palettes.
        r = _run_validator("#2a78d6,#2b79d7,#1baf7a", "light")
        self.assertNotEqual(r.returncode, 0,
                            f"bad palette must FAIL — validator is toothless otherwise:\n{r.stdout}")
        self.assertIn("FAILED", r.stdout)


class SeriesColorFoldTests(unittest.TestCase):
    def test_first_eight_map_in_order(self):
        for i in range(8):
            self.assertEqual(series_color(i), f"var(--series-{i + 1})")

    def test_ninth_and_beyond_fold_to_other_not_cycle(self):
        # The bug was _PALETTE[j % len]: series 9 reused series 1's color.
        self.assertEqual(series_color(8), SERIES_OTHER)
        self.assertEqual(series_color(20), SERIES_OTHER)
        self.assertNotEqual(series_color(8), series_color(0))


class ChartMarkColorTests(unittest.TestCase):
    """Rendered charts must color marks from --series-* only — no status colors.

    Scoped to the chart ``<figure>`` (the emitted SVG), NOT the wrapping HTML
    document: the page-shell stylesheet legitimately contains ``var(--ok)`` /
    ``var(--caution)`` for the status-UI components, which is unrelated to charts.
    """

    _ALLOWED = set(SERIES_TOKENS) | {SERIES_OTHER}

    def _bar_svg(self, n_series: int) -> str:
        spec = {
            "title": "T",
            "categories": ["A", "B", "C"],
            "series": [
                {"name": f"s{i}", "values": [1 + i, 3 - (i % 3), 2]}
                for i in range(n_series)
            ],
        }
        html = render.build_document("bar-chart", spec).html
        m = re.search(r'<figure class="bh-bar-chart">.*?</figure>', html, re.S)
        self.assertIsNotNone(m, "bar-chart figure not found in rendered document")
        return m.group(0)

    def _line_svg(self) -> str:
        spec = {
            "title": "T",
            "series": [
                {"name": "a", "points": [[0, 1], [1, 2], [2, 3]]},
                {"name": "b", "points": [[0, 3], [1, 2], [2, 1]]},
                {"name": "c", "points": [[0, 2], [1, 3], [2, 1]]},
            ],
        }
        html = render.build_document("line-chart", spec).html
        m = re.search(r'<figure class="brainhub-line-chart">.*?</figure>', html, re.S)
        self.assertIsNotNone(m, "line-chart figure not found in rendered document")
        return m.group(0)

    def test_bar_marks_use_series_tokens_only(self):
        svg = self._bar_svg(3)
        rect_fills = re.findall(r'<rect[^>]*\bfill="([^"]+)"', svg)
        self.assertTrue(rect_fills, "no bar/legend rects found")
        for tok in ("var(--series-1)", "var(--series-2)", "var(--series-3)"):
            self.assertIn(tok, rect_fills, f"expected {tok} on a bar/legend swatch")
        for fill in rect_fills:
            self.assertIn(fill, self._ALLOWED, f"bar mark used non-series fill {fill!r}")
            self.assertNotIn(fill, _FORBIDDEN_MARK_COLORS)
        # No status color anywhere in the emitted chart SVG (--muted legitimately
        # remains on axis tick labels, so it is only forbidden ON MARKS above).
        self.assertNotIn("var(--ok)", svg)
        self.assertNotIn("var(--caution)", svg)

    def test_bar_ninth_series_folds_to_other(self):
        svg = self._bar_svg(9)
        rect_fills = set(re.findall(r'<rect[^>]*\bfill="([^"]+)"', svg))
        self.assertIn(SERIES_OTHER, rect_fills, "9th series should fold to --series-other")
        self.assertIn("var(--series-1)", rect_fills)
        # No token outside the allowed series set leaked in (no cycle/repeat).
        self.assertTrue(rect_fills <= self._ALLOWED, f"unexpected fills: {rect_fills - self._ALLOWED}")

    def test_line_marks_use_series_tokens_only(self):
        svg = self._line_svg()
        strokes = re.findall(r'<polyline[^>]*\bstroke="([^"]+)"', svg)
        self.assertTrue(strokes, "no polyline series found")
        for tok in ("var(--series-1)", "var(--series-2)", "var(--series-3)"):
            self.assertIn(tok, strokes, f"expected {tok} on a line series")
        for stroke in strokes:
            self.assertIn(stroke, self._ALLOWED, f"line used non-series stroke {stroke!r}")
            self.assertNotIn(stroke, _FORBIDDEN_MARK_COLORS)
        self.assertNotIn("var(--ok)", svg)
        self.assertNotIn("var(--caution)", svg)


if __name__ == "__main__":
    unittest.main()
