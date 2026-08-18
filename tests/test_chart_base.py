"""Tests for the shared chart helpers, and for the defects they were extracted to fix."""
import math
import re
import unittest

from mcp_package.brainhub_core import render
from mcp_package.brainhub_core.render.renderers import _chart_base as cb


class NiceTicksTests(unittest.TestCase):
    def test_the_step_is_a_round_number(self):
        # What makes an axis addable in the head is the STEP being 1/2/5 × 10ⁿ —
        # a tick of 1080 is fine when the step is 20. The previous line-chart
        # implementation divided the range evenly, giving steps like 17.6.
        for lo, hi in [(3, 47), (0, 11), (1085, 1157), (0, 1157), (0.2, 0.9)]:
            with self.subTest(domain=(lo, hi)):
                ticks = cb.nice_ticks(lo, hi)
                steps = {round(b - a, 9) for a, b in zip(ticks, ticks[1:])}
                self.assertEqual(len(steps), 1, f"uneven steps: {ticks}")
                step = steps.pop()
                mantissa = step / 10 ** math.floor(math.log10(step))
                self.assertIn(
                    round(mantissa, 6), (1.0, 2.0, 5.0), f"step {step} is not 1/2/5×10ⁿ"
                )

    def test_every_tick_is_a_multiple_of_the_step(self):
        ticks = cb.nice_ticks(1085, 1157)
        step = ticks[1] - ticks[0]
        for tick in ticks:
            self.assertAlmostEqual(tick % step, 0, places=6, msg=f"{tick} is off-grid")

    def test_ticks_enclose_the_domain(self):
        # The caller scales to ticks[0]..ticks[-1]; ticks that sit inside the
        # data range would clip the tallest bar and push the outermost label
        # outside the plot.
        for lo, hi in [(3, 47), (1085, 1157), (-5, 5), (0.2, 0.9)]:
            with self.subTest(domain=(lo, hi)):
                ticks = cb.nice_ticks(lo, hi)
                self.assertLessEqual(ticks[0], lo)
                self.assertGreaterEqual(ticks[-1], hi)

    def test_single_value_domain_does_not_divide_by_zero(self):
        self.assertGreater(len(cb.nice_ticks(5, 5)), 1)
        self.assertGreater(len(cb.nice_ticks(0, 0)), 1)

    def test_fractional_steps_stay_clean(self):
        # Repeated float addition gives 0.30000000000000004; the integer
        # multiply/divide path is what avoids it.
        self.assertEqual(cb.nice_ticks(0, 1), [0.0, 0.2, 0.4, 0.6, 0.8, 1.0])


class TextWidthTests(unittest.TestCase):
    def test_cjk_is_wider_than_latin_digits(self):
        # Layout constants sized against digits truncate Chinese labels; this is
        # the number that has to differ for an adaptive gutter to work at all.
        cjk = cb.estimate_text_width("長條圖折線圖", 12)
        digits = cb.estimate_text_width("123456", 12)
        self.assertGreater(cjk, digits * 1.5)

    def test_width_scales_with_font_size(self):
        self.assertAlmostEqual(
            cb.estimate_text_width("abc", 24), cb.estimate_text_width("abc", 12) * 2
        )


class IdPrefixTests(unittest.TestCase):
    def test_different_specs_get_different_prefixes(self):
        a = cb.id_prefix("bh-line-chart", {"series": [1]})
        b = cb.id_prefix("bh-line-chart", {"series": [2]})
        self.assertNotEqual(a, b)

    def test_same_spec_is_deterministic(self):
        spec = {"series": [{"name": "營收", "points": [[0, 1]]}]}
        self.assertEqual(
            cb.id_prefix("bh-line-chart", spec), cb.id_prefix("bh-line-chart", spec)
        )


class TwoChartsOnOnePageTests(unittest.TestCase):
    """The collision a module-level prefix did not prevent."""

    def _ids(self, spec):
        html = render.build_document("line-chart", spec, title="T").html
        return set(re.findall(r'id="(bh-line-chart-[^"]+)"', html))

    def test_two_line_charts_do_not_share_accessible_name_ids(self):
        first = self._ids({"series": [{"name": "甲", "points": [[0, 1], [1, 2]]}]})
        second = self._ids({"series": [{"name": "乙", "points": [[0, 5], [1, 9]]}]})
        self.assertTrue(first and second)
        self.assertEqual(first & second, set())


class DescriptionCarriesDataTests(unittest.TestCase):
    """role="img" hides the plot's text, so <desc> has to hold the numbers."""

    def test_line_chart_desc_names_the_values(self):
        html = render.build_document(
            "line-chart",
            {"series": [{"name": "營收", "points": [[0, 1085], [1, 1157]]}]},
            title="T",
        ).html
        desc = re.findall(r"<desc[^>]*>([^<]*)</desc>", html)[-1]
        self.assertIn("1085", desc)
        self.assertIn("1157", desc)

    def test_bar_chart_desc_names_the_values(self):
        html = render.build_document(
            "bar-chart",
            {"categories": ["台北", "台中"], "series": [{"name": "營收", "values": [271, 62]}]},
            title="T",
        ).html
        desc = re.findall(r"<desc[^>]*>([^<]*)</desc>", html)[-1]
        self.assertIn("271", desc)
        self.assertIn("台北", desc)


class CaptionConsistencyTests(unittest.TestCase):
    def test_both_charts_put_the_caption_above_the_plot(self):
        # One caption above and one below reads as belonging to the wrong figure
        # when two charts are stacked in a report.
        for kind in ("bar-chart", "line-chart"):
            with self.subTest(kind=kind):
                html = render.build_document(
                    kind, render.registry.get(kind).example, title="季度營收"
                ).html
                body = html.split("<main", 1)[1]
                caption = body.index("<figcaption")
                svg = body.index("<svg")
                self.assertLess(caption, svg, f"{kind}: caption is below the plot")


if __name__ == "__main__":
    unittest.main()
