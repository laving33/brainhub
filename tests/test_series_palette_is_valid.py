"""The shipped series palette must pass the validator that lives next to it.

`scripts/validate_palette.py` computes the checks that colour cannot be
eyeballed for (OKLCH lightness band, chroma floor, CVD separation, contrast).
It existed, and nothing ran it — so the palette it validates could drift in
`web_assets.py` and the script would only notice if a human thought to invoke
it by hand.

Run as a test rather than a CI step so the same gate applies locally.
"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_palette.py"
TOKENS = ROOT / "mcp_package" / "brainhub_core" / "web_assets.py"

SERIES_SLOTS = 8


def _series_palette(mode: str) -> list[str]:
    """Extract the series ramp for one mode.

    Dark mode is a SELECTED set of steps, not an automatic flip of the light
    one — validating the light hexes against the dark surface would fail four
    slots on the lightness band and say nothing true about what ships. So each
    token is attributed to the CSS block it is declared in.
    """
    css = TOKENS.read_text(encoding="utf-8")
    # Where each theme block begins; a token belongs to the nearest one above it.
    blocks = [
        (m.start(), "dark" if "dark" in m.group(0) else "light")
        for m in re.finditer(
            r"^(?::root(?:\[data-theme=\"dark\"\])?|@media \(prefers-color-scheme: dark\)) \{",
            css,
            re.MULTILINE,
        )
    ]
    colors: dict[int, str] = {}
    for match in re.finditer(r"--series-([1-8]):\s*([^;]+);", css):
        owner = [kind for start, kind in blocks if start < match.start()]
        if owner and owner[-1] == mode:
            colors.setdefault(int(match.group(1)), match.group(2).strip())
    return [colors[slot] for slot in sorted(colors)]


class SeriesPaletteTests(unittest.TestCase):
    def test_both_modes_define_all_eight_series_tokens(self):
        for mode in ("light", "dark"):
            with self.subTest(mode=mode):
                self.assertEqual(
                    len(_series_palette(mode)),
                    SERIES_SLOTS,
                    f"a --series-N token is missing from {mode} mode; charts "
                    "would fall back to an undefined CSS variable",
                )

    def test_the_two_modes_are_separately_chosen_not_a_shared_ramp(self):
        self.assertNotEqual(
            _series_palette("light"),
            _series_palette("dark"),
            "dark mode reuses the light ramp verbatim; steps must be chosen "
            "against the dark surface, not inherited from the light one",
        )

    def test_palette_passes_the_validator_in_light_mode(self):
        self._run_validator("light")

    def test_palette_passes_the_validator_in_dark_mode(self):
        self._run_validator("dark")

    def _run_validator(self, mode: str) -> None:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), ",".join(_series_palette(mode)),
             "--mode", mode],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"series palette fails the {mode}-mode checks:\n{result.stdout}\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
