"""The decision-board invariant: a closed batch never hides a blank.

Written after a live board (studio-pilot-2026-08-01) was marked `decided` with
two items nobody had ever answered. The batch looked finished, the two decisions
silently ceased to exist, and the human who had not made them could no longer
tell that anything was missing.

Every test here carries its own negative control — the assertion is shown
failing on the old behaviour, not merely passing on the new one, because a check
that cannot go red is not a check (驗證天條 #2/#3).
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "mcp_package"))

from brainhub_core.decision_audit import audit_decisions, undecided_item_ids  # noqa: E402


def _batch(status: str, decisions: list[object]) -> dict:
    return {
        "schema_version": 1,
        "batch_id": "probe",
        "title": "probe",
        "created_by": "test",
        "status": status,
        "decided_at": None,
        "items": [
            {"id": f"item-{index + 1:02d}", "content_md": "x", "decision": decision}
            for index, decision in enumerate(decisions)
        ],
    }


def _approve() -> dict:
    return {"action": "approve", "decided_by": "self-declared:test",
            "decided_at": "2026-08-03T00:00:00Z"}


class UndecidedIdsTest(unittest.TestCase):
    def test_blank_and_non_object_decisions_both_count_as_undecided(self):
        batch = _batch("open", [None, _approve(), "approve", []])
        # POSITIVE: the two blanks and the two malformed values are all undecided.
        self.assertEqual(
            undecided_item_ids(batch), ["item-01", "item-03", "item-04"]
        )
        # NEGATIVE CONTROL: an all-answered batch reports nothing, so a non-empty
        # result can never be an artefact of the walk itself.
        self.assertEqual(undecided_item_ids(_batch("open", [_approve()])), [])

    def test_definition_matches_the_one_the_write_path_uses(self):
        """The audit and the close gate must not drift into two definitions."""
        import serve  # imported lazily: pulls in the whole HTTP module

        for decisions in ([None, _approve()], [_approve()], [], [None, None]):
            batch = _batch("open", decisions)
            self.assertEqual(
                undecided_item_ids(batch),
                serve._undecided_item_ids(batch),
                f"definitions diverged on {decisions!r}",
            )


class AuditDecisionsTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        (self.workspace / "decisions").mkdir()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name: str, batch: dict) -> None:
        (self.workspace / "decisions" / f"{name}.json").write_text(
            json.dumps(batch), encoding="utf-8"
        )

    def test_reports_a_closed_batch_holding_blanks(self):
        # POSITIVE: this is the exact shape studio-pilot-2026-08-01 was in.
        self._write("bad", _batch("decided", [_approve(), None, None]))
        violations = audit_decisions(self.workspace)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].undecided, ("item-02", "item-03"))
        self.assertIn("status=decided", violations[0].describe())

    def test_negative_controls_stay_silent(self):
        # A closed batch with every item answered: legitimately finished.
        self._write("closed_ok", _batch("decided", [_approve(), _approve()]))
        # An open batch with blanks: that is what "still being worked on" is.
        self._write("open_blanks", _batch("open", [None, None]))
        # A closed batch whose blanks were explicitly skipped: an outcome, not a gap.
        skipped = {"action": "skipped", "decided_by": "self-declared:owner",
                   "decided_at": "2026-08-03T00:00:00Z", "note": "略過"}
        self._write("closed_skipped", _batch("decided", [_approve(), skipped]))
        self.assertEqual(audit_decisions(self.workspace), [])

    def test_corrupt_json_is_not_reported_as_a_missing_decision(self):
        (self.workspace / "decisions" / "broken.json").write_text("{oops", encoding="utf-8")
        self.assertEqual(audit_decisions(self.workspace), [])

    def test_missing_directory_is_not_an_error(self):
        import tempfile

        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(audit_decisions(empty), [])

    def test_cli_exit_code_is_the_red_light(self):
        from brainhub_core import decision_audit

        self._write("closed_ok", _batch("decided", [_approve()]))
        # NEGATIVE CONTROL first: a sound workspace must exit 0, otherwise the
        # exit code proves nothing when it later goes non-zero.
        self.assertEqual(decision_audit.main([str(self.workspace)]), 0)
        self._write("bad", _batch("decided", [None]))
        self.assertEqual(decision_audit.main([str(self.workspace)]), 3)

    def test_a_check_that_did_not_run_cannot_look_like_a_finding(self):
        """Exit 1 is reserved for "this never executed".

        Running the module with the system interpreter dies on
        ModuleNotFoundError and exits 1. If a violation also exited 1, a run
        that never happened would be indistinguishable from a run that found
        something — tam hit this while verifying the module and nearly reported
        a passing negative control on a command that had not executed.
        """
        from brainhub_core import decision_audit

        self.assertEqual(decision_audit.EXIT_DID_NOT_RUN, 1)
        # No code path deliberately returns it.
        self._write("bad", _batch("decided", [None]))
        outcomes = {
            decision_audit.main([str(self.workspace)]),          # violations
            decision_audit.main([]),                             # usage error
            decision_audit.main([str(self.workspace), "extra"]),  # usage error
        }
        self.assertNotIn(decision_audit.EXIT_DID_NOT_RUN, outcomes)
        self.assertEqual(outcomes, {3, 2})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
