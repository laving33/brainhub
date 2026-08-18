"""The vendored brand assets must be byte-identical to the brand SSOT.

Why this test exists — the most expensive kind of silent bug we have:

``render/document.py`` inlines the aworkr logo from ``brainhub_core/vendor/`` so
that every artifact is one self-contained file with zero external requests. The
source comment calls it a "frozen mirror". It froze, and the brand moved: on
2026-07-12 the wordmark was redrawn (Inter-outlined Λ with a *bevelled* foot ->
custom glyph with a *flat* foot) and the old one was archived as **retired, do
not use**. The mirror kept the retired one.

So every BrainHub document, report, artifact and PDF across the whole fleet went
on printing a logo the brand had explicitly retired. It never errored. It was
found by a human — the CXO looked at a **contract we were about to send a client**
and said "that logo is wrong".

Swapping the two files back only resets the drift; it does not stop it. This test
is the thing that stops it: touch the brand, and the mirror goes red until it is
re-synced. Rule and trigger live together.
"""
from __future__ import annotations

import unittest
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[1] / "mcp_package" / "brainhub_core" / "vendor"
BRAND = Path("/home/aworkr/aworkr/core/library/brand/assets/logo")

MIRRORED = ("aworkr-logo-wordmark.svg", "aworkr-logo-primary.svg")

# Vendored CODE, same disease as the vendored logo: a frozen mirror of someone
# else's SSoT. It drifted within a day — catalog fixed `value_format` in the SSoT
# (labels were 100x off on stacked bars) and the mirror kept the bug, so every
# stacked-bar chart BrainHub rendered was mislabelled by 100x. Nothing errored.
# catalog's own words: "這個保證靠『catalog 記得通知 chief』＝人腦保證＝一定會爛，
# 而且漂了沒人會知道。" This test is what replaces the human promise.
# Same mechanism, and not only for .py: `aworkr-tokens.css` is the brand token
# file the viewer + every artifact actually read at runtime. It is vendored (not
# referenced across repos) because BrainHub ships as its own product line and gets
# installed on machines that have no aworkr core/ at all — owner, 2026-07-21.
# Vendoring is therefore the CORRECT shape here, not a shortcut; what it still
# needs is this drift guard, because a frozen palette that silently disagrees with
# the brand is the same bug as the frozen logo above.
# report_chart.py used to be here. It is now render/chart_primitives.py, owned
# outright: the SSoT was unreachable from a BrainHub checkout, so this guard
# could only skip, while the "do not edit" rule it enforced still blocked every
# fix. A guard that cannot run is not protection.
VENDORED_CODE = {
    "aworkr-tokens.css": Path(
        "/home/aworkr/aworkr/core/library/brand/assets/tokens/tokens.css"
    ),
}


class VendoredBrandAssetTests(unittest.TestCase):
    def test_vendored_logos_match_the_brand_ssot(self):
        if not BRAND.is_dir():
            self.skipTest("brand SSOT not present (standalone BrainHub install)")
        for name in MIRRORED:
            with self.subTest(asset=name):
                mirror, source = VENDOR / name, BRAND / name
                self.assertTrue(mirror.is_file(), f"vendored asset missing: {mirror}")
                self.assertTrue(source.is_file(), f"brand SSOT missing: {source}")
                self.assertEqual(
                    mirror.read_bytes(),
                    source.read_bytes(),
                    f"{name} has drifted from the brand SSOT. BrainHub is printing a "
                    f"stale logo on every document it renders — including client-facing "
                    f"ones. Re-sync: cp {source} {mirror}",
                )

    def test_vendored_code_matches_its_upstream_ssot(self):
        """The vendored file is `VENDORED header + the SSoT, byte for byte`.

        Both halves matter, and they pull against each other:
        - The BYTES must match, or the mirror drifts (labels went 100x wrong).
        - The HEADER must exist, or the next person to open the file has no idea
          it is a mirror, edits it in place, and drift starts over. That header is
          the only thing standing between this file and the next drift.

        I learned that the hard way an hour after fixing the drift: my `cp` fixed
        the bytes and DELETED the anti-drift marker — I used the drift repair to
        remove the drift guard. So the comparison is body-only, and the header is
        asserted separately. (catalog-am caught it.)
        """
        for name, source in VENDORED_CODE.items():
            with self.subTest(module=name):
                if not source.is_file():
                    self.skipTest(f"upstream SSoT not present: {source}")
                mirror = VENDOR / name
                self.assertTrue(mirror.is_file(), f"vendored module missing: {mirror}")
                mirror_bytes, source_bytes = mirror.read_bytes(), source.read_bytes()
                self.assertIn(
                    b"VENDORED into brainhub", mirror_bytes,
                    f"{name} lost its VENDORED header. Without it the next person to "
                    f"open this file does not know it mirrors {source} — they edit it "
                    f"here and the drift starts again.",
                )
                self.assertTrue(
                    mirror_bytes.endswith(source_bytes),
                    f"{name} has drifted from its SSoT ({source}). BrainHub renders with "
                    f"a stale copy — silently, possibly into client-facing reports. "
                    f"Re-sync: keep the VENDORED header, then append {source} verbatim.",
                )

    def test_no_retired_asset_sits_next_to_the_live_one(self):
        """A retired logo kept beside the live one is how it gets re-inlined by the
        next person who greps the directory. Archives belong in the brand library."""
        strays = [p.name for p in VENDOR.glob("_archive*")]
        self.assertEqual(strays, [], f"retired brand assets must not live in vendor/: {strays}")


if __name__ == "__main__":
    unittest.main()
