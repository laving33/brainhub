"""Canonical URL building and parsing for addressable BrainHub objects."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_package"))

from brainhub_core.addressing import (  # noqa: E402
    KIND_ARTIFACT,
    KIND_PAGE,
    KIND_RAW,
    canonical_path,
    kind_for_sid,
    legacy_path,
    parse_path,
    with_query,
)
from brainhub_core.sid import generate_sid  # noqa: E402

PAGE_SID = generate_sid("W")
ARTIFACT_SID = generate_sid("A")


class KindForSidTests(unittest.TestCase):
    def test_type_char_selects_the_kind(self):
        self.assertEqual(kind_for_sid(PAGE_SID), KIND_PAGE)
        self.assertEqual(kind_for_sid(ARTIFACT_SID), KIND_ARTIFACT)

    def test_invalid_sids_have_no_kind(self):
        # A wrong check symbol must not resolve to anything: a typo has to fail
        # loudly rather than land on some other object.
        broken = PAGE_SID[:5] + ("0" if PAGE_SID[5] != "0" else "1")
        self.assertEqual(kind_for_sid(broken), "")
        self.assertEqual(kind_for_sid("W00000"), "")
        self.assertEqual(kind_for_sid(""), "")
        self.assertEqual(kind_for_sid(None), "")


class CanonicalPathTests(unittest.TestCase):
    def test_shape_is_kind_sid_title(self):
        self.assertEqual(
            canonical_path(KIND_PAGE, PAGE_SID, "chief-home"),
            f"/page/{PAGE_SID}/chief-home",
        )

    def test_title_is_one_url_segment(self):
        path = canonical_path(KIND_PAGE, PAGE_SID, "a/b c")
        self.assertEqual(path, f"/page/{PAGE_SID}/a%2Fb%20c")

    def test_cjk_title_is_percent_encoded(self):
        path = canonical_path(KIND_PAGE, PAGE_SID, "阿仁九條")
        self.assertTrue(path.startswith(f"/page/{PAGE_SID}/%"))

    def test_title_is_optional(self):
        self.assertEqual(canonical_path(KIND_ARTIFACT, ARTIFACT_SID), f"/artifact/{ARTIFACT_SID}")

    def test_lowercase_and_confusable_input_normalizes(self):
        self.assertEqual(
            canonical_path(KIND_PAGE, PAGE_SID.lower(), "x"),
            f"/page/{PAGE_SID}/x",
        )

    def test_unaddressable_input_raises(self):
        with self.assertRaises(ValueError):
            canonical_path(KIND_PAGE, "W00000", "x")
        with self.assertRaises(ValueError):
            canonical_path("search", PAGE_SID, "x")

    def test_raw_sources_are_addressable_too(self):
        raw_sid = generate_sid("R")
        self.assertEqual(kind_for_sid(raw_sid), KIND_RAW)
        self.assertEqual(canonical_path(KIND_RAW, raw_sid, "a.md"), f"/raw/{raw_sid}/a.md")


class ParsePathTests(unittest.TestCase):
    def test_sid_form(self):
        reference = parse_path(f"/page/{PAGE_SID}/whatever-title")
        self.assertEqual(reference.kind, KIND_PAGE)
        self.assertEqual(reference.sid, PAGE_SID)
        self.assertEqual(reference.remainder, "whatever-title")
        self.assertFalse(reference.is_legacy)

    def test_sid_without_title(self):
        reference = parse_path(f"/artifact/{ARTIFACT_SID}")
        self.assertEqual(reference.sid, ARTIFACT_SID)
        self.assertEqual(reference.remainder, "")

    def test_legacy_page_title(self):
        reference = parse_path("/page/chief-home")
        self.assertEqual(reference.sid, "")
        self.assertEqual(reference.remainder, "chief-home")
        self.assertTrue(reference.is_legacy)

    def test_legacy_raw_subpath_keeps_both_segments(self):
        reference = parse_path("/raw/notes/client-call.md")
        self.assertEqual(reference.kind, KIND_RAW)
        self.assertEqual(reference.sid, "")
        self.assertEqual(reference.remainder, "notes/client-call.md")

    def test_legacy_artifact_subpath_keeps_both_segments(self):
        reference = parse_path("/artifact/charts/loop.html")
        self.assertEqual(reference.sid, "")
        self.assertEqual(reference.remainder, "charts/loop.html")

    def test_mistyped_sid_is_treated_as_a_title_not_a_sid(self):
        # Six chars with a bad check symbol must fall through to legacy lookup,
        # not silently resolve to whatever page shares the prefix.
        broken = PAGE_SID[:5] + ("0" if PAGE_SID[5] != "0" else "1")
        reference = parse_path(f"/page/{broken}")
        self.assertEqual(reference.sid, "")
        self.assertEqual(reference.remainder, broken)

    def test_non_addressable_prefixes_return_none(self):
        for path in ("/search", "/graph", "/", "", "/page", f"/{PAGE_SID}/title"):
            self.assertIsNone(parse_path(path), path)

    def test_percent_encoded_title_is_decoded(self):
        reference = parse_path(f"/page/{PAGE_SID}/%E9%98%BF%E4%BB%81")
        self.assertEqual(reference.remainder, "阿仁")


class LegacyAndQueryTests(unittest.TestCase):
    def test_legacy_page_path_is_one_segment(self):
        self.assertEqual(legacy_path(KIND_PAGE, "a b"), "/page/a%20b")

    def test_legacy_artifact_path_keeps_its_separator(self):
        self.assertEqual(legacy_path(KIND_ARTIFACT, "charts/x.html"), "/artifact/charts/x.html")

    def test_query_survives_a_redirect(self):
        # The PDF button hangs off ?format=pdf; dropping it on redirect would
        # silently serve the HTML instead of the download.
        self.assertEqual(with_query("/artifact/A1/x", "format=pdf"), "/artifact/A1/x?format=pdf")
        self.assertEqual(with_query("/artifact/A1/x", ""), "/artifact/A1/x")


if __name__ == "__main__":
    unittest.main()
