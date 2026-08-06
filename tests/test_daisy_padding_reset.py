"""The base reset must never out-rank an adopted daisyUI component's padding.

THE BUG THIS EXISTS FOR
-----------------------
``web_assets.CSS`` opens with a universal reset. For most of this project's life
it was one unlayered line::

    * { box-sizing: border-box; margin: 0; padding: 0; }

Unlayered is the strongest position an author rule can occupy: it beats every
rule inside ``@layer`` regardless of specificity. daisyUI declares all of its
component padding from inside ``@layer utilities{@layer daisyui...}``, and
Tailwind's spacing utilities (``p-4``, ``py-3``) sit in ``@layer utilities``.
So a single-character-wide selector silently zeroed the padding of every
component the shell adopted — and of the utilities written beside them.

Measured in Chrome against the served shell, with the reset unlayered and no
hand-written patches::

    .alert                 padding 0px   (daisyUI asks .75rem / 1rem)
    .card-body p-4         padding 0px   (the p-4 utility asks 1rem)
    footer ... p-4         padding-inline 0px
    .navbar / .menu        padding-block 0px  (daisyUI asks .5rem)

With the reset moved into ``@layer base`` the same measurement returns
12/16px, 16px, 16px and 8px respectively. That is the fix that is in place now.

WHY A TEST AND NOT A COMMENT
----------------------------
The failure mode has no symptom. Nothing raises, no test moves, the page
renders — the component just looks a little cramped, which reads as "that is
how the component looks". It was patched three times by hand (``.alert``,
``.card-body``, ``.stat``) before anyone asked why every new component needed
the same patch. A patch list only ever covers the components somebody
remembered, so the list is not the guard: this is.

WHAT IS ASSERTED
----------------
For every daisyUI/Tailwind class named in ``ui_classes.py`` that the vendored
stylesheet gives padding to, the shipped shell must not leave the universal
reset out-ranking it. Two ways to satisfy that, and the test accepts either:

  1. the reset is layered (today's answer, and it covers classes nobody has
     adopted yet), or
  2. an explicit unlayered override for that class exists in the shell.

The premise is checked too, because a check whose assumption has quietly
expired is worse than none: if daisyUI ever ships its padding UNLAYERED, the
"layered loses to unlayered" reasoning stops describing reality, and this test
says so instead of staying green.
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

_DECLARATION = re.compile(r'^[A-Z][A-Z0-9_]*\s*=\s*"([^"]+)"', re.MULTILINE)
_PADDING_DECL = re.compile(r"(?<![\w-])(padding|padding-block|padding-inline|margin)\s*:")

#: at-rules whose braces hold declarations, not nested style rules.
_OPAQUE_AT_RULES = ("@keyframes", "@property", "@font-face", "@counter-style")


# ---------------------------------------------------------------------------
# A cascade-aware reader. `in_layer` is the only fact this file needs, and it
# is the one a substring search cannot answer.
# ---------------------------------------------------------------------------
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def iter_rules(css: str, in_layer: bool = False, _top: bool = True):
    """Yield ``(selector, declarations, in_layer)`` for every style rule.

    Descends through ``@media`` / ``@supports`` (which do not change layer
    membership) and ``@layer`` (which does). Skips at-rules whose body is
    declarations rather than rules.

    Comments are stripped first, and that is not tidiness. This stylesheet
    documents its own cascade traps by quoting CSS in prose — the reset comment
    contains a literal ``* { margin: 0; padding: 0 }`` — so a reader that keeps
    comments parses the explanation as a rule and reports the fixed bug as
    still present. Caught by this file's own box-sizing assertion going red.
    """
    if _top:
        css = _COMMENT.sub(" ", css)
    i, n = 0, len(css)
    prelude_start = 0
    while i < n:
        char = css[i]
        if char == "{":
            prelude = css[prelude_start:i].strip()
            body_start = i + 1
            depth = 1
            j = body_start
            while j < n and depth:
                if css[j] == "{":
                    depth += 1
                elif css[j] == "}":
                    depth -= 1
                j += 1
            body = css[body_start: j - 1]
            if prelude.startswith("@"):
                if prelude.startswith(_OPAQUE_AT_RULES):
                    pass
                elif prelude.startswith("@layer"):
                    yield from iter_rules(body, in_layer=True, _top=False)
                else:
                    yield from iter_rules(body, in_layer=in_layer, _top=False)
            else:
                yield prelude, body, in_layer
            i = j
            prelude_start = i
            continue
        if char == "}":
            prelude_start = i + 1
        i += 1


def declared_class_tokens() -> set[str]:
    """Every class token named in ui_classes.py — the adoption manifest."""
    tokens: set[str] = set()
    for match in _DECLARATION.finditer(MANIFEST.read_text(encoding="utf-8")):
        tokens.update(match.group(1).split())
    return tokens


#: `:not(...)` EXCLUDES what it names, so a class mentioned only there is not
#: being styled by that rule — it is being styled around. Dropping the whole
#: `:not()` before matching is the difference between a detector and a
#: rubber stamp: the shell's button rule ends `:not(.btn)`, and while that
#: counted as a match the checker reported `.btn` as protected by an override
#: that in fact declares "every button EXCEPT this one". Found by printing the
#: offender list instead of trusting a green run.
_NOT_CLAUSE = re.compile(r":not\([^()]*(?:\([^()]*\)[^()]*)*\)")


def _selector_names_class(selector: str, cls: str) -> bool:
    selector = _NOT_CLAUSE.sub(" ", selector)
    escaped = re.escape(cls.replace(":", r"\:").replace("/", r"\/").replace(".", r"\."))
    return re.search(rf"\.{escaped}(?![\w-])", selector) is not None


def adopted_classes_with_padding(vendored: str) -> dict[str, bool]:
    """{adopted class -> daisyUI declares its padding inside a layer}.

    The value is the PREMISE, kept alongside the class rather than assumed, so
    an upstream rebuild that moves a rule out of its layer is visible here.
    """
    wanted = declared_class_tokens()
    found: dict[str, bool] = {}
    for selector, body, in_layer in iter_rules(vendored):
        if not _PADDING_DECL.search(body):
            continue
        for cls in wanted:
            if _selector_names_class(selector, cls):
                # False (unlayered) is the sticky value: one unlayered rule is
                # enough to make the class immune to the reset on its own.
                found[cls] = found.get(cls, True) and in_layer
    return found


def universal_reset_is_unlayered(shell_css: str) -> bool:
    """True when an UNLAYERED `*` rule sets margin/padding — the trap itself."""
    for selector, body, in_layer in iter_rules(shell_css):
        if in_layer:
            continue
        if any(part.strip() == "*" for part in selector.split(",")):
            if _PADDING_DECL.search(body):
                return True
    return False


def classes_with_unlayered_override(shell_css: str, classes) -> set[str]:
    """Adopted classes the shell re-pads by hand, unlayered (the old patches)."""
    covered: set[str] = set()
    for selector, body, in_layer in iter_rules(shell_css):
        if in_layer or not _PADDING_DECL.search(body):
            continue
        for cls in classes:
            if _selector_names_class(selector, cls):
                covered.add(cls)
    return covered


def unprotected_components(shell_css: str, vendored: str) -> list[str]:
    """Adopted components whose padding the universal reset currently eats."""
    adopted = adopted_classes_with_padding(vendored)
    if not universal_reset_is_unlayered(shell_css):
        return []
    at_risk = {cls for cls, layered in adopted.items() if layered}
    return sorted(at_risk - classes_with_unlayered_override(shell_css, at_risk))


def _shell_css() -> str:
    """Exactly the author CSS the browser gets, minus the vendored file."""
    from brainhub_core.web_assets import BRAND_THEME_CSS, CSS

    return CSS + "\n" + BRAND_THEME_CSS


class UnlayeredResetTests(unittest.TestCase):
    def test_no_adopted_component_loses_its_padding_to_the_base_reset(self):
        offenders = unprotected_components(_shell_css(), VENDORED.read_text(encoding="utf-8"))

        self.assertEqual(
            offenders, [],
            msg=(
                "these daisyUI classes are adopted in ui_classes.py and daisyUI "
                f"gives them padding, but the shell renders them with none: {offenders}.\n"
                "CAUSE: the universal reset in web_assets.CSS ("
                "`* { margin: 0; padding: 0 }`) is UNLAYERED, and an unlayered rule "
                "beats every rule inside @layer no matter how specific — daisyUI "
                "declares all component padding inside @layer. The component still "
                "renders, it just has no padding, which looks like a design choice "
                "rather than a fault.\n"
                "FIX: put the margin/padding half of the reset back inside "
                "`@layer base` in web_assets.CSS (its home since 2026-08). Re-padding "
                "each component by hand also silences this test, but only for the "
                "components someone remembers — that is the state this test replaced."
            ),
        )

    def test_the_reset_still_flattens_the_ua_defaults_it_exists_for(self):
        """Layering it must not delete it. Author rules — layered or not — still
        beat the UA stylesheet, which is the reset's actual job: no <h1> margin,
        no <ul> padding, no <body> margin."""
        reset_rules = [
            (sel, body, in_layer)
            for sel, body, in_layer in iter_rules(_shell_css())
            if any(p.strip() == "*" for p in sel.split(","))
        ]
        margins = [b for _, b, _ in reset_rules if re.search(r"margin\s*:\s*0", b)]
        paddings = [b for _, b, _ in reset_rules if re.search(r"padding\s*:\s*0", b)]
        boxes = [b for _, b, _ in reset_rules if "box-sizing" in b]

        self.assertTrue(margins, "the universal margin reset has gone missing entirely")
        self.assertTrue(paddings, "the universal padding reset has gone missing entirely")
        self.assertTrue(boxes, "`* { box-sizing: border-box }` has gone missing")

    def test_box_sizing_stays_unlayered(self):
        """border-box is a layout invariant the whole stylesheet is written
        against, not a value a component gets to contest. Only margin/padding
        were ever the contested pair, so only they were moved."""
        unlayered_box_sizing = any(
            "box-sizing" in body and not in_layer
            for sel, body, in_layer in iter_rules(_shell_css())
            if any(p.strip() == "*" for p in sel.split(","))
        )

        self.assertTrue(unlayered_box_sizing)

    def test_the_premise_is_still_true_upstream(self):
        """`layered loses to unlayered` only matters while daisyUI keeps its
        padding layered. If a rebuild ships it unlayered this reasoning is void,
        and a green test would be asserting nothing."""
        adopted = adopted_classes_with_padding(VENDORED.read_text(encoding="utf-8"))

        self.assertTrue(adopted, "no adopted class has padding in the vendored CSS at all")
        self.assertIn("alert", adopted)
        self.assertIn("card-body", adopted)
        unlayered = sorted(cls for cls, layered in adopted.items() if not layered)
        self.assertEqual(
            unlayered, [],
            msg=(
                f"daisyUI now declares padding for {unlayered} OUTSIDE @layer. "
                "The cascade model this file reasons with no longer matches the "
                "stylesheet — re-derive it before trusting the check again."
            ),
        )


class TheCheckCanGoRedTests(unittest.TestCase):
    """An assertion nobody has seen fail is a decoration.

    These drive the detector with the broken stylesheet instead of the shipped
    one, so the failure path is exercised on every run rather than trusted.
    """

    #: The reset exactly as it shipped before 2026-08 — the real regression.
    UNLAYERED_RESET = "* { box-sizing: border-box; margin: 0; padding: 0; }\n"
    LAYERED_RESET = "* { box-sizing: border-box; }\n@layer base { * { margin: 0; padding: 0; } }\n"

    def test_reverting_the_layering_is_detected(self):
        vendored = VENDORED.read_text(encoding="utf-8")
        broken = self.UNLAYERED_RESET + _shell_css().replace(self.LAYERED_RESET, "")

        offenders = unprotected_components(broken, vendored)

        self.assertIn("alert", offenders)
        self.assertIn("card-body", offenders)
        self.assertIn("navbar", offenders)

    def test_a_hand_written_override_is_recognised_as_protection(self):
        """The other half: the pre-2026-08 shell — unlayered reset PLUS the three
        hand-typed patches — has to come back clean for exactly those three and
        dirty for everything else, or the test is just detecting the reset."""
        vendored = VENDORED.read_text(encoding="utf-8")
        patched = (
            self.UNLAYERED_RESET
            + ".alert { padding-block: 0.75rem; padding-inline: 1rem; }\n"
            ".card-body { padding: 1rem; }\n"
            ".stat { padding-block: 0.75rem; padding-inline: 1rem; }\n"
            + _shell_css().replace(self.LAYERED_RESET, "")
        )

        offenders = unprotected_components(patched, vendored)

        self.assertNotIn("alert", offenders)
        self.assertNotIn("card-body", offenders)
        self.assertNotIn("stat", offenders)
        self.assertIn("navbar", offenders)  # never patched — still eaten

    def test_the_shipped_shell_is_the_clean_case(self):
        """Positive control for the two above: same detector, real stylesheet."""
        self.assertEqual(unprotected_components(_shell_css(), VENDORED.read_text(encoding="utf-8")), [])
        self.assertFalse(universal_reset_is_unlayered(_shell_css()))

    def test_a_class_named_only_inside_not_is_not_an_override(self):
        """`button:not(.btn) { padding: … }` styles every button EXCEPT .btn.
        Reading it as protection is how `.btn` dropped off the offender list
        while its padding was still being eaten."""
        self.assertTrue(_selector_names_class(".btn { padding: 1px }", "btn"))
        self.assertFalse(_selector_names_class("button:not(.copy-button):not(.btn)", "btn"))
        self.assertTrue(_selector_names_class(":is(.btn, .x)", "btn"))

    def test_the_layer_reader_distinguishes_layered_from_unlayered(self):
        """`iter_rules` is doing the only work that matters here; a substring
        search would call both of these the same rule."""
        unlayered = list(iter_rules("* { padding: 0 }"))
        layered = list(iter_rules("@layer base { * { padding: 0 } }"))
        nested = list(iter_rules("@media (min-width: 40em) { @layer base { .a { padding: 1px } } }"))
        media_only = list(iter_rules("@media print { .b { padding: 2px } }"))
        opaque = list(iter_rules("@keyframes x { from { padding: 0 } }"))

        self.assertEqual([r[2] for r in unlayered], [False])
        self.assertEqual([r[2] for r in layered], [True])
        self.assertEqual([r[2] for r in nested], [True])
        self.assertEqual([r[2] for r in media_only], [False])
        self.assertEqual(opaque, [])


if __name__ == "__main__":
    unittest.main()
