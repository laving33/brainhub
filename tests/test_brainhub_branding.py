"""Guard: no upstream identity may re-enter this fork.

BrainHub is a hard fork (no upstream remote). The previous version of this file
asserted the *presence* of "BrainHub" in the upstream marketing site — a check
pointed the wrong way: it stayed green while 46 links to the upstream GitHub repo
sat in the tree. This version asserts the *absence* of upstream identity instead,
so re-vendoring an upstream file turns the suite red.
"""
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Unambiguous upstream identity. Deliberately NOT the bare word "link": this repo
# is a wiki engine, so "backlink"/"wikilink"/"<link rel=>" are legitimate English.
# Every token here is a name, handle, or URL that only the upstream project owns.
FORBIDDEN_TOKENS = (
    "gowtham",
    "homebrew-link",
    "io.github.gowtham",
    "Link logo",
    "why-link",
    "registry.modelcontextprotocol.io",
)

# This file names every forbidden token, so it would match itself — the classic
# "grep counts its own pattern" false positive. Excluded by path, not by content.
SELF = Path(__file__).relative_to(ROOT).as_posix()

# LICENSE carries the upstream MIT copyright notice. MIT requires that notice to
# survive in copies, so it is exempt from the scrub by decision, not by accident.
# If that decision is reversed, delete the file and drop it from this tuple.
# make_dist.sh is the packaging gate — like this file, it must name the
# forbidden tokens in order to check for them.
EXEMPT_PATHS = (SELF, "LICENSE", "scripts/make_dist.sh")


_WALK_SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "dist"}


def tracked_text_files() -> list[str]:
    """git ls-files when available; plain filesystem walk in the distributed
    package, which ships without git history."""
    try:
        listing = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        )
        return [line for line in listing.stdout.splitlines() if line]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    found: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in _WALK_SKIP_DIRS for part in relative.parts):
            continue
        found.append(relative.as_posix())
    return found


class UpstreamIdentityAbsentTests(unittest.TestCase):
    def test_no_upstream_identity_in_tracked_files(self):
        offenders: list[str] = []
        for relative_path in tracked_text_files():
            if relative_path in EXEMPT_PATHS:
                continue
            try:
                text = (ROOT / relative_path).read_text(encoding="utf-8")
            except (UnicodeDecodeError, FileNotFoundError):
                continue
            lowered = text.lower()
            for token in FORBIDDEN_TOKENS:
                if token.lower() in lowered:
                    offenders.append(f"{relative_path}: {token}")
        self.assertEqual(offenders, [], f"upstream identity found in {len(offenders)} place(s)")

    def test_guard_detects_a_planted_token(self):
        """Negative control: the scan above only means something if it can fail."""
        planted = "https://github.com/gowtham0992/link"
        self.assertTrue(
            any(token.lower() in planted.lower() for token in FORBIDDEN_TOKENS),
            "guard would not catch a literal upstream repo URL",
        )
