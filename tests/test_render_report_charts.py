"""Dedicated coverage for the 9 report-chart kinds (kpi/line/bar/stacked-bar/
heatmap/scatter/funnel/donut/gauge).

Before this file existed they were exercised only indirectly through the brand
pack suite; this is the direct render contract per kind.
"""
import unittest

from mcp_package.brainhub_core import render

# Minimal valid input per kind — mirrors the real report_chart signatures
# (kept in sync with tests/test_brand_pack_core.py's SPECS).
SPECS = {
    "bar": {"title": "T", "values": [3, 1], "labels": ["甲", "乙"]},
    "donut": {"title": "T", "values": [3, 1], "labels": ["甲", "乙"]},
    "gauge": {"title": "T", "value": 0.42},
    "heatmap": {"title": "T", "rows": [{"label": "列", "values": [1, 2]}],
                "col_labels": ["甲", "乙"]},
    "kpi": {"title": "T", "tiles": [{"label": "營收", "value": "1,234"}]},
    "line": {"title": "T", "series": [{"name": "s", "values": [1, 2]}],
             "x_labels": ["一", "二"]},
    "stacked-bar": {"title": "T", "rows": [{"label": "列", "segments": [1, 2]}],
                    "segment_names": ["甲", "乙"]},
    "funnel": {"title": "T", "stages": [{"label": "甲", "value": 10},
                                        {"label": "乙", "value": 5}]},
    "scatter": {"title": "T", "points": [{"x": 1, "y": 2, "label": "點"}]},
}


class ReportChartKindsTests(unittest.TestCase):
    def test_all_nine_kinds_registered_as_charts(self):
        kinds = render.registry.kinds()
        for kind in SPECS:
            with self.subTest(kind=kind):
                self.assertIn(kind, kinds)
                entry = render.registry.get(kind)
                self.assertEqual(entry.output_kind, "chart")
                self.assertTrue(entry.description)

    def test_each_kind_renders_a_self_contained_svg_document(self):
        for kind, spec in SPECS.items():
            with self.subTest(kind=kind):
                result = render.build_document(kind, spec, title="標題")
                doc = result.html
                self.assertEqual(result.output_kind, "chart")
                self.assertTrue(doc.startswith("<!DOCTYPE html>"))
                self.assertIn("<svg", doc)
                self.assertIn("Content-Security-Policy", doc)
                # No externally-referencing tags anywhere in the artifact.
                for needle in ('src="http', 'href="http', 'src="//', "<script src="):
                    self.assertNotIn(needle, doc)

    def test_svg_carries_its_own_accessible_name_and_is_not_double_wrapped(self):
        doc = render.build_document("gauge", SPECS["gauge"], title="使用率").html
        # report_chart already emits role="img" + <title>/<desc> on the <svg>.
        self.assertIn('role="img"', doc)
        self.assertIn("<title>", doc)
        # The shell must NOT add an outer role="img" around it: nesting makes
        # the inner subtree presentational, hiding that <title>/<desc>.
        self.assertNotIn('<figure role="img"', doc)

    def test_unknown_spec_key_raises_value_error_not_type_error(self):
        # bh_build and the CLI catch ValueError; a raw TypeError from
        # report_chart's kwargs would crash them instead of reporting.
        for kind in SPECS:
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    render.build_document(kind, {"no_such_key": 1}, title="T")


if __name__ == "__main__":
    unittest.main()
