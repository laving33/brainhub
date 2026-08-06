"""Standing invariant check for decision boards.

One invariant, stated once:

    a batch whose ``status`` is ``"decided"`` has an outcome recorded on every
    item — never a blank.

The write path enforces it going forward (``serve.py`` refuses an unearned
close), but a rule that only lives in one code path is a rule that stops being
true the moment anything else writes the file: an agent authoring JSON by hand,
a restored backup, a future importer. So the invariant is also *checked*, on
data at rest, by something that runs on its own — the viewer calls
``audit_decisions()`` on every health render, and this module is runnable
directly for a scripted check::

    /home/aworkr/aworkr/tools/brainhub/.venv/bin/python \
        -m brainhub_core.decision_audit /home/aworkr/aworkr/core/brainhub

**Use that interpreter.** The system ``python3`` cannot import this package and
dies with ``ModuleNotFoundError`` — which exits **1**, and if 1 also meant
"violations found", a check that never ran would be indistinguishable from a
check that ran and failed. tam hit exactly that while verifying this module and
nearly reported a passing negative control on a run that never happened.

So the exit codes are chosen to keep those apart:

===== =========================================================================
 0    ran; the invariant holds
 1    **never returned deliberately** — reserved for "this did not run"
       (Python's own code for an uncaught exception / failed import)
 2    usage error (wrong arguments)
 3    ran; violations found
===== =========================================================================

Even so, read the output line rather than the code alone: an exit status is one
number, and one number cannot say both what happened and whether anything
happened at all.

Why it earns a file of its own: a blank behind a "decided" status is not a
cosmetic defect. It reads identically to a deliberate pass, so the decision does
not merely go missing — it goes missing *while looking finished*. That is how
studio-pilot-2026-08-01 closed with two items (副標, 題材) nobody had ever
answered, and how the human who had not answered them found the board would no
longer take his input.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

DECISIONS_DIRNAME = "decisions"


@dataclass(frozen=True)
class DecisionViolation:
    """One batch that claims to be decided while items are still blank."""

    batch_id: str
    path: Path
    undecided: tuple[str, ...]

    def describe(self) -> str:
        ids = ", ".join(self.undecided)
        return (
            f"{self.batch_id}: status=decided 但 {len(self.undecided)} 項沒有 decision"
            f"（{ids}）"
        )


def undecided_item_ids(batch: object) -> list[str]:
    """Ids of items carrying no decision object.

    Deliberately mirrors ``serve._undecided_item_ids``. The duplication is one
    short function and is covered by a test that feeds the same batch to both —
    the alternative is importing ``serve`` (a 3000-line HTTP module) into a
    checker that must stay runnable anywhere the workspace is.
    """
    if not isinstance(batch, dict):
        return []
    items = batch.get("items")
    if not isinstance(items, list):
        return []
    return [
        str(entry.get("id") or f"item-{index + 1}")
        for index, entry in enumerate(items)
        if isinstance(entry, dict) and not isinstance(entry.get("decision"), dict)
    ]


def audit_decisions(workspace: Path | str) -> list[DecisionViolation]:
    """Every batch in ``<workspace>/decisions/`` that violates the invariant.

    An empty list is the healthy answer. Unreadable or non-object JSON is not
    reported here: that is a different failure (a corrupt file), the viewer's
    board loader already treats it as "no batch", and folding it in would let a
    parse error masquerade as a missing decision.
    """
    directory = Path(workspace) / DECISIONS_DIRNAME
    if not directory.is_dir():
        return []
    violations: list[DecisionViolation] = []
    for path in sorted(directory.glob("*.json")):
        try:
            batch = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(batch, dict) or batch.get("status") != "decided":
            continue
        undecided = undecided_item_ids(batch)
        if undecided:
            violations.append(
                DecisionViolation(
                    batch_id=str(batch.get("batch_id") or path.stem),
                    path=path,
                    undecided=tuple(undecided),
                )
            )
    return violations


EXIT_OK = 0
EXIT_DID_NOT_RUN = 1  # never returned here; this is what a failed import exits with
EXIT_USAGE = 2
EXIT_VIOLATIONS = 3


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: <brainhub venv python> -m brainhub_core.decision_audit <workspace>",
              file=sys.stderr)
        return EXIT_USAGE
    violations = audit_decisions(args[0])
    if not violations:
        print("決策板不變式 OK：沒有「已完成但留空白」的批次")
        return EXIT_OK
    print(f"決策板不變式違規 {len(violations)} 批：", file=sys.stderr)
    for violation in violations:
        print(f"  - {violation.describe()}", file=sys.stderr)
    return EXIT_VIOLATIONS


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
