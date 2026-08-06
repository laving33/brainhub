"""Every class BrainHub declares must actually exist in the stylesheet it ships.

This is the guard for the quietest failure in a Tailwind build: a class that is
never emitted. Nothing raises, the build reports success, the page renders — just
without that style. Three ways it happens, all seen here:

* **Purged.** The scanner reads source text, so a name assembled at runtime is
  invisible to it. Measured on this project: a written-out ``mt-7`` is emitted, a
  composed ``mt-{n}`` is not.
* **Renamed upstream.** ``input-bordered`` was a daisyUI v4 class and does not
  exist in v5. It was written from habit, read fine in review, and produced a
  search box with no border and no error. This test is what found it.
* **Stale artifact.** The vendored CSS is a build product. Edit the manifest,
  forget ``npm run build``, and the shipped file no longer matches the code.

Eyeballing the page cannot catch these — a missing class usually looks like a
slightly different design rather than a fault, which is why chief asked for a
check that goes red instead.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

MANIFEST = ROOT / "mcp_package" / "brainhub_core" / "ui_classes.py"
VENDORED = ROOT / "mcp_package" / "brainhub_core" / "vendor" / "aworkr-daisyui.css"
CORE = ROOT / "mcp_package" / "brainhub_core"

_DECLARATION = re.compile(r'^[A-Z][A-Z0-9_]*\s*=\s*"([^"]+)"', re.MULTILINE)


def declared_classes() -> set[str]:
    """Every class token named in the manifest."""
    tokens: set[str] = set()
    for match in _DECLARATION.finditer(MANIFEST.read_text(encoding="utf-8")):
        tokens.update(match.group(1).split())
    return tokens


def _is_emitted(css: str, cls: str) -> bool:
    """Look for the class as CSS writes it, escapes and all.

    Do not decompose the name first. An earlier version of this check split on
    ``:`` to strip pseudo-classes, which also tore ``sm:btn-wide`` in half and
    reported eight classes missing that were present — a checker wrong in the
    direction that manufactures work.
    """
    escaped = cls.replace(":", r"\:").replace("/", r"\/").replace(".", r"\.")
    return f".{escaped}" in css


class VendoredDaisyuiCssTests(unittest.TestCase):
    def test_every_declared_class_survives_into_the_built_stylesheet(self):
        css = VENDORED.read_text(encoding="utf-8")
        missing = sorted(c for c in declared_classes() if not _is_emitted(css, c))

        self.assertEqual(
            missing, [],
            msg=(
                f"declared in ui_classes.py but absent from {VENDORED.name}: {missing}. "
                "Either the name does not exist in this daisyUI version, or the "
                "stylesheet is stale — rebuild with `cd build && npm run build`."
            ),
        )

    def test_the_check_can_actually_fail(self):
        """A guard that cannot go red is decoration.

        Pinned because the real check passes on a healthy tree, so nothing else
        would notice if `_is_emitted` started returning True unconditionally.
        """
        css = VENDORED.read_text(encoding="utf-8")

        self.assertTrue(_is_emitted(css, "btn"))
        self.assertFalse(_is_emitted(css, "btn-thisclassdoesnotexist"))

    def test_the_shipped_stylesheet_needs_no_network(self):
        """It is read from disk by installs that have neither Node nor a network,
        and it is inlined into artifacts that are opened offline."""
        css = VENDORED.read_text(encoding="utf-8")

        self.assertNotIn("@import", css)
        self.assertNotRegex(css, r"url\(\s*['\"]?https?:")

    def test_both_brand_themes_are_present(self):
        """Dark mode was half-branded once already — every colour slot the light
        theme re-points has to be re-pointed for dark, or the upstream palette
        shows through at higher specificity."""
        css = VendoredDaisyuiCssTests._css()

        self.assertIn("aworkr-dark", css)
        self.assertIn("--color-primary", css)

    @staticmethod
    def _css() -> str:
        return VENDORED.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Wiring: a stylesheet that ships but is never served is the same as no
# stylesheet, and that is exactly the state this file used to certify as green.
# ---------------------------------------------------------------------------
class DaisyuiIsActuallyOnThePageTests(unittest.TestCase):
    """The manifest matched the artifact for weeks while no page loaded either.

    Every check above passes on a stylesheet that no renderer references — which
    is what BrainHub shipped: 28 constants, a 49KB build product, a test suite
    agreeing they matched, and zero daisyUI classes in the served HTML. These
    assert the other half: the file reaches the browser, and reaches it in a
    state that does not damage the page it lands on.
    """

    def test_the_shell_serves_the_vendored_stylesheet(self):
        from brainhub_core.web_assets import DAISY_CSS
        from brainhub_core.web_layout import render_layout

        page = render_layout("t", "<p>body</p>")

        self.assertIn(DAISY_CSS, page)
        self.assertIn("navbar", page)  # the header wears it, not just the <style>

    def test_tailwind_preflight_is_not_shipped_onto_the_shell(self):
        """Preflight resets elements BrainHub never declares, and those are the
        ones that break silently: `ol,ul,menu {list-style: none}` takes the
        bullets off every list in the wiki, and no rule anywhere says why."""
        from brainhub_core.web_assets import DAISY_CSS

        self.assertNotIn("ol,ul,menu{list-style:none}", DAISY_CSS)
        self.assertNotIn("h1,h2,h3,h4,h5,h6{font-size:inherit", DAISY_CSS)
        # daisyUI's own base survives the cut — themes live in the same layer.
        self.assertIn("[data-theme=aworkr]", DAISY_CSS)

    def test_the_preflight_cut_refuses_a_stylesheet_it_does_not_recognise(self):
        """The cut is positional. If a rebuild moves the boundary it must stop,
        not quietly ship half a reset."""
        from brainhub_core.web_assets import _strip_tailwind_preflight

        with self.assertRaises(ValueError):
            _strip_tailwind_preflight("@layer base{.a{color:red}}")

    def test_daisyui_border_width_cannot_collide_with_the_shell_border_colour(self):
        """`--border` is a WIDTH to daisyUI and a COLOUR to BrainHub. Whichever
        loses, the declaration is invalid at computed-value time and the border
        just disappears — on components or on the page chrome, depending on
        order. The rename removes the shared name."""
        from brainhub_core.web_assets import CSS, DAISY_CSS

        self.assertNotIn("var(--border)", DAISY_CSS)
        self.assertIn("var(--dui-border)", DAISY_CSS)
        self.assertIn("--border:", CSS)  # the shell still owns the plain name

    def test_daisyui_colours_follow_the_shell_theme_switch(self):
        """daisyUI ships built-in `light`/`dark` themes and BrainHub's toggle
        writes exactly those two names, so without this binding a reader who
        picks 深色 gets daisyUI's stock indigo next to the brand's midnight."""
        from brainhub_core.web_assets import BRAND_THEME_CSS

        self.assertIn("--color-base-100: var(--color-bg);", BRAND_THEME_CSS)
        self.assertIn(':root[data-theme="dark"]', BRAND_THEME_CSS)
        self.assertIn(
            "--color-base-100: var(--color-bg-dark);", BRAND_THEME_CSS
        )


class ClassNameCollisionTests(unittest.TestCase):
    """A class BrainHub already used, that daisyUI also styles, is now a merge.

    This is the check the screenshot had to do instead. `<div class="stat">`
    predates the vendoring by months; the moment the stylesheet went on the page
    daisyUI's `.stat` component claimed it, added `display: inline-grid` and
    `width: 100%`, and the home page's figures each took a full row. Nothing
    errored, no test moved, and the markup was untouched — the element simply
    started answering to a second stylesheet.

    An entry here is not a failure. It is a name that has to be looked at before
    it ships: adopt the daisyUI component deliberately, or rename ours.

    Only HAND-TYPED tokens are examined, and that distinction is the whole
    check. Deliberate adoption interpolates a constant — `class="{NAV_LINK}"` —
    so its tokens never appear as literal text; a hand-typed `class="stat"` does.
    An earlier version exempted every name in ui_classes.py instead, which
    excused `stat` on the grounds that `STAT` exists: the check went green on
    the exact bug it was written for. Verified by putting the bug back.
    """

    #: Overlaps that were looked at and are fine, with the reason each is inert.
    REVIEWED = {
        # daisyUI names `.disabled` only inside `:not()` on `.menu` descendants;
        # it styles nothing on its own, and these spans are not inside a menu.
        "disabled",
    }

    @staticmethod
    def _daisyui_class_names() -> set[str]:
        css = VENDORED.read_text(encoding="utf-8")
        names = set()
        for match in re.finditer(r"\.([A-Za-z][A-Za-z0-9_-]*)", css):
            names.add(match.group(1))
        return names

    @staticmethod
    def _classes_brainhub_writes() -> dict[str, set[str]]:
        """Hand-typed class tokens only — f-string holes are removed first, so a
        constant interpolated from ui_classes.py is invisible here by design."""
        holes = re.compile(r"\{[^}]*\}")
        attribute = re.compile(r"""class=["']([^"']*)["']""")
        found: dict[str, set[str]] = {}
        sources = [p for p in CORE.rglob("*.py") if "__pycache__" not in str(p)]
        sources.append(ROOT / "serve.py")
        for path in sources:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in attribute.finditer(text):
                for token in holes.sub(" ", match.group(1)).split():
                    found.setdefault(token, set()).add(path.name)
        return found

    def test_no_unreviewed_class_name_is_shared_with_daisyui(self):
        daisyui = self._daisyui_class_names()
        written = self._classes_brainhub_writes()

        shared = {
            token: sorted(files)
            for token, files in written.items()
            if token in daisyui and token not in self.REVIEWED
        }

        self.assertEqual(
            shared, {},
            msg=(
                "these class names are written by BrainHub AND styled by daisyUI, "
                f"so both stylesheets apply to the same elements: {shared}. Adopt "
                "the component on purpose (add it to ui_classes.py) or rename ours."
            ),
        )

    def test_the_collision_check_can_actually_fail(self):
        """`.stat` is the case that got through — pin that the detector sees it."""
        daisyui = self._daisyui_class_names()

        self.assertIn("stat", daisyui)
        self.assertNotIn("stat-item", daisyui)  # the name BrainHub moved to


if __name__ == "__main__":
    unittest.main()
