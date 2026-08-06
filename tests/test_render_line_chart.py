import unittest

from mcp_package.brainhub_core import render


class LineChartRendererTests(unittest.TestCase):
    def test_registered_in_registry(self):
        self.assertIn("line-chart", render.registry.kinds())
        entry = render.registry.get("line-chart")
        self.assertEqual(entry.output_kind, "chart")
        self.assertTrue(entry.description)

    def test_build_document_self_contained(self):
        spec = {
            "title": "CPU vs Memory",
            "x_label": "Time (s)",
            "y_label": "Percent",
            "series": [
                {"name": "cpu", "points": [[0, 10], [1, 40], [2, 20], [3, 80]]},
                {"name": "mem<script>", "points": [[0, 5], [1, 15], [2, 55], [3, 30]]},
            ],
        }
        result = render.build_document("line-chart", spec)
        self.assertEqual(result.output_kind, "chart")
        self.assertIn("<svg", result.html)
        self.assertIn("<polyline", result.html)
        # series/legend names are escaped, not injected raw
        self.assertIn("mem&lt;script&gt;", result.html)
        self.assertNotIn("<script>mem", result.html)
        # zero external references anywhere in the artifact
        lowered = result.html.lower()
        for needle in ("http://", "https://", "cdn", 'src="//'):
            self.assertNotIn(needle, lowered)

    def test_static_mode_has_no_animation_and_is_shape_stable(self):
        spec = {"series": [{"name": "a", "points": [[0, 0], [1, 1], [2, 4]]}]}
        normal = render.build_document("line-chart", spec, static=False)
        static = render.build_document("line-chart", spec, static=True)
        self.assertNotIn("<animate", normal.html.lower())
        self.assertNotIn("<animate", static.html.lower())
        self.assertNotIn("@keyframes", normal.html.lower())
        # static mode only adds the shared flatten-CSS block; the renderer's
        # own SVG output is identical either way (documented no-op).
        self.assertIn("data-brainhub-static", static.html)
        self.assertNotIn("data-brainhub-static", normal.html)

    def test_validate_rejects_missing_series(self):
        with self.assertRaises(ValueError):
            render.build_document("line-chart", {})

    def test_validate_rejects_too_few_points(self):
        with self.assertRaises(ValueError):
            render.build_document("line-chart", {"series": [{"name": "a", "points": [[0, 0]]}]})

    def test_validate_rejects_non_numeric_points(self):
        with self.assertRaises(ValueError):
            render.build_document(
                "line-chart",
                {"series": [{"name": "a", "points": [[0, 0], ["x", 1]]}]},
            )

    def test_validate_rejects_bool_coords(self):
        with self.assertRaises(ValueError):
            render.build_document(
                "line-chart",
                {"series": [{"name": "a", "points": [[0, 0], [True, 1]]}]},
            )

    def test_degenerate_single_value_axis_does_not_crash(self):
        # All points share the same x and y -> would divide by zero without
        # the _nice_ticks/span fallback.
        spec = {"series": [{"name": "flat", "points": [[5, 5], [5, 5]]}]}
        result = render.build_document("line-chart", spec)
        self.assertIn("<svg", result.html)


if __name__ == "__main__":
    unittest.main()
