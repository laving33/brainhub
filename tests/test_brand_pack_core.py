"""One directory has to be able to replace the whole corporate identity.

BrainHub ships *with* a brand theme (the vendored aworkr palette and lockups) rather
than shipping unbranded. That is deliberate — but before the brand pack the three
assets resolved down three unrelated paths: the logo had a four-level lookup, the
fonts had one env var, and the colour tokens had no override at all. A deployment
could therefore swap its logo, believe it had rebranded, and still render every
document and every viewer page in someone else's palette.

These tests assert the two halves of the fix that a reader actually depends on:
a pack replaces what it provides, and stays out of the way for what it does not.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core import brand  # noqa: E402

CUSTOM_TOKEN = "CUSTOMER-BRAND-MARKER"
CUSTOM_LOGO_TITLE = "CustomerMarkForTests"


def _write_pack(root: Path, *, tokens: bool = True, logo: bool = True, fonts: bool = True) -> Path:
    pack = root / "brand-pack"
    pack.mkdir(parents=True, exist_ok=True)
    if tokens:
        (pack / brand.TOKENS_ASSET).write_text(
            f":root {{ --marker: \"{CUSTOM_TOKEN}\"; }}\n", encoding="utf-8"
        )
    if logo:
        (pack / brand.LOGO_ASSET).write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            f"<title>{CUSTOM_LOGO_TITLE}</title></svg>\n",
            encoding="utf-8",
        )
    if fonts:
        (pack / brand.FONTS_ASSET).mkdir(exist_ok=True)
    return pack


class BrandPackResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="brainhub-brand-pack-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True))
        self.root = Path(self._tmp)

    def test_no_pack_configured_means_the_bundled_theme(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(brand.BRAND_DIR_ENV, None)
            self.assertIsNone(brand.brand_dir())
            self.assertIsNone(brand.pack_file(brand.TOKENS_ASSET))
            self.assertIsNone(brand.text_asset(brand.TOKENS_ASSET))

    def test_a_pack_replaces_the_assets_it_provides(self):
        pack = _write_pack(self.root)
        with patch.dict(os.environ, {brand.BRAND_DIR_ENV: str(pack)}):
            self.assertEqual(brand.brand_dir(), pack)
            self.assertIn(CUSTOM_TOKEN, brand.text_asset(brand.TOKENS_ASSET) or "")
            self.assertIn(CUSTOM_LOGO_TITLE, brand.text_asset(brand.LOGO_ASSET) or "")
            self.assertEqual(brand.pack_dir(brand.FONTS_ASSET), pack / brand.FONTS_ASSET)

    def test_a_partial_pack_is_valid_and_leaves_the_rest_bundled(self):
        """A pack with only a logo must not blank out the palette."""
        pack = _write_pack(self.root, tokens=False, fonts=False)
        with patch.dict(os.environ, {brand.BRAND_DIR_ENV: str(pack)}):
            self.assertIn(CUSTOM_LOGO_TITLE, brand.text_asset(brand.LOGO_ASSET) or "")
            # None, not "" -- the caller must fall back rather than render nothing.
            self.assertIsNone(brand.text_asset(brand.TOKENS_ASSET))
            self.assertIsNone(brand.pack_dir(brand.FONTS_ASSET))

    def test_a_missing_or_unreadable_pack_directory_is_ignored(self):
        """A typo'd path must not take the viewer down; it falls back to bundled."""
        with patch.dict(os.environ, {brand.BRAND_DIR_ENV: str(self.root / "nope")}):
            self.assertIsNone(brand.brand_dir())
            self.assertIsNone(brand.text_asset(brand.TOKENS_ASSET))
        with patch.dict(os.environ, {brand.BRAND_DIR_ENV: "   "}):
            self.assertIsNone(brand.brand_dir())

    def test_pack_asset_names_cannot_escape_the_pack(self):
        pack = _write_pack(self.root)
        with patch.dict(os.environ, {brand.BRAND_DIR_ENV: str(pack)}):
            for bad in ("../tokens.css", "sub/tokens.css", "", ".", ".."):
                with self.subTest(asset=bad):
                    with self.assertRaises(ValueError):
                        brand.pack_file(bad)

    def test_per_asset_env_var_still_works_for_the_logo(self):
        """The pre-brand-pack override stays supported; the pack just outranks it."""
        single = self.root / "single-logo.svg"
        single.write_text(f"<svg><title>{CUSTOM_LOGO_TITLE}</title></svg>", encoding="utf-8")
        with patch.dict(os.environ, {brand.LOGO_ENV: str(single)}):
            os.environ.pop(brand.BRAND_DIR_ENV, None)
            self.assertIn(CUSTOM_LOGO_TITLE, brand.text_asset(brand.LOGO_ASSET, brand.LOGO_ENV) or "")

    def test_fonts_dir_falls_back_to_the_bundled_path(self):
        bundled = self.root / "bundled-fonts"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(brand.BRAND_DIR_ENV, None)
            os.environ.pop(brand.FONTS_ENV, None)
            self.assertEqual(brand.fonts_dir(bundled), bundled)
        pack = _write_pack(self.root)
        with patch.dict(os.environ, {brand.BRAND_DIR_ENV: str(pack)}):
            self.assertEqual(brand.fonts_dir(bundled), pack / brand.FONTS_ASSET)


class BrandPackReachesTheOutputTests(unittest.TestCase):
    """The resolver being right is not the claim; the rendered bytes are.

    The reading modules resolve their assets at import time (the viewer loads its
    stylesheets once), so these reload them under the env var rather than trusting
    that a later change would be picked up.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="brainhub-brand-out-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True))
        self.pack = _write_pack(Path(self._tmp))

    def _reload_with_pack(self, pack: Path | None):
        env = {brand.BRAND_DIR_ENV: str(pack)} if pack else {}
        with patch.dict(os.environ, env, clear=False):
            if pack is None:
                os.environ.pop(brand.BRAND_DIR_ENV, None)
            from brainhub_core import web_assets
            from brainhub_core.render import document
            importlib.reload(web_assets)
            importlib.reload(document)
            return web_assets, document

    def tearDown(self) -> None:
        # Leave the modules holding the bundled theme, or later tests in the same
        # process would inherit this test's palette.
        self._reload_with_pack(None)

    def test_a_pack_recolours_the_viewer_and_the_documents(self):
        web_assets, document = self._reload_with_pack(self.pack)
        self.assertIn(CUSTOM_TOKEN, web_assets.BRAND_TOKENS_CSS)
        self.assertIn(CUSTOM_LOGO_TITLE, document.LOGO_SVG)
        # The component sheet was not overridden, so it must still be the bundled one.
        self.assertGreater(len(web_assets.DAISY_CSS), 1000)

    def test_without_a_pack_the_bundled_theme_is_used(self):
        web_assets, document = self._reload_with_pack(None)
        self.assertNotIn(CUSTOM_TOKEN, web_assets.BRAND_TOKENS_CSS)
        self.assertNotIn(CUSTOM_LOGO_TITLE, document.LOGO_SVG)
        self.assertGreater(len(web_assets.BRAND_TOKENS_CSS), 100)



class EveryRendererHonoursTheBrandPackTests(unittest.TestCase):
    """Iterates the registry, so a renderer added later is covered without edits.

    The gap the brand pack closed was three assets resolving down three unrelated
    paths. A renderer that hardcodes a hex colour, or reads a vendored asset
    directly, reopens exactly that gap — and it would look correct to whoever wrote
    it, because their own deployment is the unbranded default.
    """

    # Specs come from each renderer's registered ``example`` — the single place
    # they are defined. This file used to restate them, one of three copies that
    # could drift from what the renderers actually accept (and one had, passing
    # raw counts to donut's `values`, which means shares, so the canonical
    # example rendered a slice labelled "300%").
    @staticmethod
    def _spec(kind: str) -> dict:
        from brainhub_core.render.registry import registry

        return registry.get(kind).example

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="brainhub-brand-renderers-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True))
        self.pack = _write_pack(Path(self._tmp))

    def _registered_kinds(self) -> list[str]:
        from brainhub_core.render import load_renderers
        from brainhub_core.render.registry import registry

        load_renderers()
        return sorted(registry._renderers)

    def test_every_registered_renderer_ships_an_example_spec(self):
        """A renderer with no example is one nothing here can exercise."""
        missing = [kind for kind in self._registered_kinds() if not self._spec(kind)]
        self.assertEqual(
            missing, [],
            f"renderers with no registered example, so their brand handling is unverified: {missing}",
        )

    def test_every_renderer_renders_and_carries_the_pack_tokens(self):
        kinds = self._registered_kinds()
        self.assertGreaterEqual(len(kinds), 13, "renderer registry looks unexpectedly small")

        failures: list[str] = []
        unbranded: list[str] = []
        with patch.dict(os.environ, {brand.BRAND_DIR_ENV: str(self.pack)}):
            from brainhub_core import web_assets
            from brainhub_core.render import document
            importlib.reload(web_assets)
            importlib.reload(document)
            from brainhub_core.render import pipeline
            importlib.reload(pipeline)

            for kind in kinds:
                try:
                    html = pipeline.build_document(kind, self._spec(kind), title="T").html
                except Exception as exc:  # noqa: BLE001 - collect, do not abort
                    failures.append(f"{kind}: {type(exc).__name__}: {exc}")
                    continue
                if CUSTOM_TOKEN not in html:
                    unbranded.append(kind)

        # Leave the modules on the bundled theme for whatever runs next.
        from brainhub_core import web_assets
        from brainhub_core.render import document, pipeline
        importlib.reload(web_assets)
        importlib.reload(document)
        importlib.reload(pipeline)

        self.assertEqual(failures, [], f"renderers that could not render: {failures}")
        self.assertEqual(unbranded, [], f"renderers that ignored the brand pack: {unbranded}")

    def test_chart_series_colours_come_from_tokens_not_hardcoded_hex(self):
        """Series colours must be var(--series-N) so a theme can move them.

        Hardcoded hex in a renderer is invisible to its author (their deployment is
        the default palette) and unfixable by a deployment that needs its own.
        """
        with patch.dict(os.environ, {brand.BRAND_DIR_ENV: str(self.pack)}):
            from brainhub_core.render import pipeline
            importlib.reload(pipeline)
            html = pipeline.build_document("bar-chart", self._spec("bar-chart"), title="T").html
        self.assertIn("var(--series-1)", html)

if __name__ == "__main__":
    unittest.main()
