#!/usr/bin/env python3
"""Guard against tests that create temp directories nothing ever removes.

`tempfile.mkdtemp()` has no owner. Nothing closes it, no context manager ends its life,
and the directory outlives the process that made it. Every one of them is a small,
invisible deposit into the shared `/tmp`.

On 2026-08-19 that bill came due on the machine this repo is developed on: 34,858
directories, 27.5 GB, all of them created inside one eight-hour window by repeated runs of
this suite. One full run leaked 544 directories and 407 MB — harmless once, and the same
disk also carries a production control plane, which reached 97% full.

The fix is to let the test own the directory:

    tmp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="link-thing-")))

`enterContext` ties the directory's life to the test's, so it goes away when the test
does — whether it passed, failed, or raised. The suite already used exactly this idea
elsewhere via `addCleanup(tmp.cleanup)`; the `mkdtemp` calls were simply never brought
along.

Scripts under `scripts/` are exempt on purpose. A smoke or load test writes a work
directory an operator is meant to open afterwards, and those are few, named, and created
once per invocation rather than once per test.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"

# Deliberately textual rather than an AST walk: the rule is "this call does not appear
# here", and a regex says that in a way anyone reading the failure can check by eye.
BANNED = re.compile(r"\btempfile\.mkdtemp\s*\(")

REMEDY = (
    'Use tmp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="...")))\n'
    "so the directory is removed when the test ends, however it ends."
)


def find_offenders(tests_dir: Path) -> list[str]:
    offenders: list[str] = []
    for path in sorted(tests_dir.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BANNED.search(line):
                rel = path.relative_to(ROOT)
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    return offenders


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", action="store_true", help="list the files that were checked")
    args = parser.parse_args()

    if not TESTS_DIR.is_dir():
        print(f"Temp hygiene guard failed: {TESTS_DIR} does not exist.")
        return 1

    checked = sorted(TESTS_DIR.rglob("*.py"))
    if args.report:
        print(f"Checked {len(checked)} test file(s) under {TESTS_DIR.relative_to(ROOT)}/.")

    offenders = find_offenders(TESTS_DIR)
    if offenders:
        print("Temp hygiene guard failed — these temp directories have no owner:")
        for offender in offenders:
            print(f"- {offender}")
        print("")
        print(REMEDY)
        return 1

    print(f"Temp hygiene guard passed ({len(checked)} test files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
