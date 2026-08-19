"""Decision board (Phase-1 MVP) — the four load-bearing tests.

Parallel to the memory-review surface; touches no MEMORY_* code. Uses the same
in-process handler harness as test_serve.py (run_handler / post_json).
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import serve
from test_serve import post_json, reset_wiki, run_handler_raw, write_page

from brainhub_core.schema import write_schema


def _batch(**overrides) -> dict:
    batch = {
        "schema_version": 1,
        "batch_id": "test-batch",
        "title": "Test batch",
        "created_by": "studio",
        "created_at": "2026-08-03T09:00:00Z",
        "scope": "internal",
        "status": "open",
        "decided_at": None,
        "meta": {},
        "items": [
            {"id": "item-01", "content_md": "# Hi", "options": None,
             "recommendation": {"action": "approve"}, "decision": None, "meta": {}},
            {"id": "item-02", "content_md": "pick one", "options": ["A", "B", "C"],
             "recommendation": {"action": "pick", "option": 1}, "decision": None, "meta": {}},
        ],
    }
    batch.update(overrides)
    return batch


class DecisionBoardTests(unittest.TestCase):
    def make_workspace(self) -> Path:
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="decision-test-")))
        wiki = tmp / "wiki"
        wiki.mkdir()
        write_page(wiki, "index.md", "# Index\n")
        write_page(wiki, "log.md", "# Log\n")
        (wiki / "_backlinks.json").write_text("{}", encoding="utf-8")
        write_schema(wiki)
        reset_wiki(wiki)
        (tmp / "decisions").mkdir()
        return tmp

    def write_batch(self, root: Path, batch: dict) -> Path:
        path = root / "decisions" / f"{batch['batch_id']}.json"
        path.write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8")
        return path

    # (1) POST merges a decision; the file round-trips valid JSON with a
    #     server-stamped decided_at.
    def test_post_merges_decision_and_file_round_trips(self):
        root = self.make_workspace()
        path = self.write_batch(root, _batch())

        status, payload = post_json(
            "/api/decision-board/decide",
            {"batch_id": "test-batch", "item_id": "item-01",
             "decision": {"action": "approve", "decided_by": "self-declared:owner"}},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["saved"])

        saved = json.loads(path.read_text(encoding="utf-8"))  # still valid JSON
        item = saved["items"][0]
        self.assertEqual(item["decision"]["action"], "approve")
        self.assertEqual(item["decision"]["decided_by"], "self-declared:owner")
        # decided_at is server-stamped, not client-supplied.
        self.assertTrue(item["decision"]["decided_at"].endswith("Z"))
        self.assertEqual(payload["decision"]["decided_at"], item["decision"]["decided_at"])

        # A pick with a valid option index merges too.
        pick_status, pick_payload = post_json(
            "/api/decision-board/decide",
            {"batch_id": "test-batch", "item_id": "item-02",
             "decision": {"action": "pick", "option": 2}},
        )
        self.assertEqual(pick_status, 200)
        self.assertTrue(pick_payload["saved"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["items"][1]["decision"]["option"], 2)

        # close -> status decided + batch decided_at stamped.
        close_status, close_payload = post_json(
            "/api/decision-board/decide", {"batch_id": "test-batch", "close": True})
        self.assertEqual(close_status, 200)
        self.assertTrue(close_payload["closed"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "decided")
        self.assertTrue(saved["decided_at"].endswith("Z"))

    # (1b) pick-multi: a `multiple` item stores a validated, de-duped, sorted
    #      index set; out-of-range / empty selections are refused.
    def test_pick_multi_stores_index_set_and_validates(self):
        root = self.make_workspace()
        batch = _batch()
        batch["items"].append(
            {"id": "item-03", "content_md": "pick many", "options": ["X", "Y", "Z"],
             "multiple": True, "recommendation": {"action": "pick-multi", "option": [0]},
             "decision": None, "meta": {}})
        path = self.write_batch(root, batch)

        # Valid multi-pick: out-of-order + duplicate indices are normalised.
        status, payload = post_json(
            "/api/decision-board/decide",
            {"batch_id": "test-batch", "item_id": "item-03",
             "decision": {"action": "pick-multi", "options_selected": [2, 0, 2]}},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["saved"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["items"][2]["decision"]["options_selected"], [0, 2])
        self.assertEqual(saved["items"][2]["decision"]["action"], "pick-multi")

        # Out-of-range index -> 400, file untouched.
        before = path.read_bytes()
        s2, p2 = post_json("/api/decision-board/decide",
                           {"batch_id": "test-batch", "item_id": "item-03",
                            "decision": {"action": "pick-multi", "options_selected": [0, 9]}})
        self.assertEqual(s2, 400)
        self.assertFalse(p2["saved"])
        self.assertEqual(path.read_bytes(), before)

        # Empty selection -> 400 (clearing goes through decision:null, not []).
        s3, p3 = post_json("/api/decision-board/decide",
                           {"batch_id": "test-batch", "item_id": "item-03",
                            "decision": {"action": "pick-multi", "options_selected": []}})
        self.assertEqual(s3, 400)
        self.assertFalse(p3["saved"])

    # (1c) respond: on an option card the human types their own answer instead of
    #      picking; empty / whitespace-only text is refused.
    def test_respond_stores_text_on_option_card(self):
        root = self.make_workspace()
        path = self.write_batch(root, _batch())  # item-02 has options ["A","B","C"]

        status, payload = post_json(
            "/api/decision-board/decide",
            {"batch_id": "test-batch", "item_id": "item-02",
             "decision": {"action": "respond", "text": "都不要，改用 D"}},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["saved"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["items"][1]["decision"]["action"], "respond")
        self.assertEqual(saved["items"][1]["decision"]["text"], "都不要，改用 D")

        # Empty / whitespace-only text -> 400, file untouched.
        before = path.read_bytes()
        s2, p2 = post_json("/api/decision-board/decide",
                           {"batch_id": "test-batch", "item_id": "item-02",
                            "decision": {"action": "respond", "text": "   "}})
        self.assertEqual(s2, 400)
        self.assertFalse(p2["saved"])
        self.assertEqual(path.read_bytes(), before)

    # (1d) sid batch: a D-prefixed sid resolves to <sid>.json (the new filename
    #      scheme); a non-decision sid (wiki W) is rejected; legacy slugs still work.
    def test_decision_sid_batch_resolves(self):
        from brainhub_core.sid import generate_sid, SID_TYPE_DECISION, SID_TYPE_DOCUMENT
        root = self.make_workspace()
        sid = generate_sid(SID_TYPE_DECISION)
        path = root / "decisions" / f"{sid}.json"
        path.write_text(json.dumps(_batch(batch_id=sid), indent=2) + "\n", encoding="utf-8")

        # A decision sid batch_id resolves and a decision saves.
        status, payload = post_json(
            "/api/decision-board/decide",
            {"batch_id": sid, "item_id": "item-01", "decision": {"action": "approve"}})
        self.assertEqual(status, 200)
        self.assertTrue(payload["saved"])
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8"))["items"][0]["decision"]["action"],
            "approve")

        # A wiki-type sid must NOT resolve as a decision batch (path is typed to D).
        wiki_sid = generate_sid(SID_TYPE_DOCUMENT)
        s2, p2 = post_json("/api/decision-board/decide",
                           {"batch_id": wiki_sid, "item_id": "item-01",
                            "decision": {"action": "approve"}})
        self.assertEqual(s2, 400)
        self.assertFalse(p2["saved"])

    # (2) Bad item_id / bad action / bad batch_id charset -> 4xx, file untouched.
    def test_bad_requests_are_rejected_and_file_untouched(self):
        root = self.make_workspace()
        path = self.write_batch(root, _batch())
        before = path.read_bytes()

        # Unknown item_id -> 404.
        s1, p1 = post_json("/api/decision-board/decide",
                           {"batch_id": "test-batch", "item_id": "nope",
                            "decision": {"action": "approve"}})
        self.assertEqual(s1, 404)
        self.assertFalse(p1["saved"])

        # Bad action enum -> 400.
        s2, p2 = post_json("/api/decision-board/decide",
                           {"batch_id": "test-batch", "item_id": "item-01",
                            "decision": {"action": "explode"}})
        self.assertEqual(s2, 400)
        self.assertFalse(p2["saved"])

        # Bad batch_id charset -> 400 (path-confinement gate).
        s3, p3 = post_json("/api/decision-board/decide",
                           {"batch_id": "../etc/passwd", "item_id": "item-01",
                            "decision": {"action": "approve"}})
        self.assertEqual(s3, 400)
        self.assertFalse(p3["saved"])

        # pick with out-of-range option -> 400.
        s4, p4 = post_json("/api/decision-board/decide",
                           {"batch_id": "test-batch", "item_id": "item-02",
                            "decision": {"action": "pick", "option": 9}})
        self.assertEqual(s4, 400)
        self.assertFalse(p4["saved"])

        # A verified:* provenance is refused in this MVP.
        s5, p5 = post_json("/api/decision-board/decide",
                           {"batch_id": "test-batch", "item_id": "item-01",
                            "decision": {"action": "approve", "decided_by": "verified:owner"}})
        self.assertEqual(s5, 400)
        self.assertFalse(p5["saved"])

        # Missing local-action header -> 403.
        s6, p6 = post_json("/api/decision-board/decide",
                           {"batch_id": "test-batch", "item_id": "item-01",
                            "decision": {"action": "approve"}},
                           local_action=False)
        self.assertEqual(s6, 403)
        self.assertFalse(p6["saved"])

        # Nonexistent batch -> 404.
        s7, p7 = post_json("/api/decision-board/decide",
                           {"batch_id": "no-such-batch", "item_id": "item-01",
                            "decision": {"action": "approve"}})
        self.assertEqual(s7, 404)

        # After all rejections the file is byte-identical.
        self.assertEqual(path.read_bytes(), before)

    # (3) Forward-compat: unknown top-level AND item-level AND decision-level
    #     fields survive a decide-POST intact. This is the load-bearing promise.
    def test_forward_compat_unknown_fields_survive(self):
        root = self.make_workspace()
        batch = _batch()
        batch["future_top_level"] = {"experimental": [1, 2, 3]}
        batch["items"][0]["future_item_field"] = "keep-me"
        batch["items"][0]["meta"] = {"priority": "high"}
        path = self.write_batch(root, batch)

        status, payload = post_json(
            "/api/decision-board/decide",
            {"batch_id": "test-batch", "item_id": "item-01",
             "decision": {"action": "approve", "future_decision_field": "also-keep"}},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["saved"])

        saved = json.loads(path.read_text(encoding="utf-8"))
        # Unknown top-level field preserved.
        self.assertEqual(saved["future_top_level"], {"experimental": [1, 2, 3]})
        # Unknown item-level field + item meta preserved.
        self.assertEqual(saved["items"][0]["future_item_field"], "keep-me")
        self.assertEqual(saved["items"][0]["meta"], {"priority": "high"})
        # Unknown decision-level field round-tripped by the writer.
        self.assertEqual(saved["items"][0]["decision"]["future_decision_field"], "also-keep")
        # The untouched second item is entirely intact.
        self.assertEqual(saved["items"][1]["recommendation"], {"action": "pick", "option": 1})
        self.assertIsNone(saved["items"][1]["decision"])

    # (3b) Clearing: an explicit decision:null returns the item to undecided and
    #      preserves every other field (including unknown ones), per SCHEMA LAW 3.
    def test_clear_sets_decision_null_and_preserves_other_fields(self):
        root = self.make_workspace()
        batch = _batch()
        batch["future_top_level"] = {"experimental": [1, 2, 3]}
        batch["items"][0]["future_item_field"] = "keep-me"
        batch["items"][0]["meta"] = {"priority": "high"}
        path = self.write_batch(root, batch)

        # First record a real decision, then clear it.
        set_status, _ = post_json(
            "/api/decision-board/decide",
            {"batch_id": "test-batch", "item_id": "item-01",
             "decision": {"action": "approve", "note": "yes"}},
        )
        self.assertEqual(set_status, 200)
        self.assertIsInstance(
            json.loads(path.read_text(encoding="utf-8"))["items"][0]["decision"], dict)

        clear_status, clear_payload = post_json(
            "/api/decision-board/decide",
            {"batch_id": "test-batch", "item_id": "item-01", "decision": None},
        )
        self.assertEqual(clear_status, 200)
        self.assertTrue(clear_payload["saved"])
        self.assertIsNone(clear_payload["decision"])

        saved = json.loads(path.read_text(encoding="utf-8"))
        # The cleared item is back to undecided...
        self.assertIsNone(saved["items"][0]["decision"])
        # ...but every other field round-trips untouched.
        self.assertEqual(saved["future_top_level"], {"experimental": [1, 2, 3]})
        self.assertEqual(saved["items"][0]["future_item_field"], "keep-me")
        self.assertEqual(saved["items"][0]["meta"], {"priority": "high"})
        self.assertEqual(saved["items"][0]["content_md"], "# Hi")
        # The untouched second item is entirely intact.
        self.assertEqual(saved["items"][1]["recommendation"], {"action": "pick", "option": 1})
        self.assertIsNone(saved["items"][1]["decision"])

    # (4) Atomicity: the write goes through tmp + os.replace, and an injected
    #     failure during replace leaves no partial target and no stray tmp file.
    def test_write_is_atomic_tmp_plus_rename(self):
        root = self.make_workspace()
        path = self.write_batch(root, _batch())
        before = path.read_bytes()
        decisions_dir = root / "decisions"

        seen = {"tmp": None}
        import os as _os
        real_replace = _os.replace

        def spy_replace(src, dst, *a, **k):
            # The engine writes a NamedTemporaryFile then os.replace()s it onto
            # the target — capture the tmp source to prove tmp+rename, then fail.
            if str(dst) == str(path):
                seen["tmp"] = src
                raise OSError("injected replace failure")
            return real_replace(src, dst, *a, **k)

        with patch("os.replace", spy_replace):
            status, payload = post_json(
                "/api/decision-board/decide",
                {"batch_id": "test-batch", "item_id": "item-01",
                 "decision": {"action": "approve"}},
            )

        # The request surfaced a 500 rather than a partial write.
        self.assertEqual(status, 500)
        self.assertFalse(payload["saved"])
        # The rename source was a distinct tmp file in decisions/ (tmp+rename).
        self.assertIsNotNone(seen["tmp"])
        tmp_path = Path(seen["tmp"])
        self.assertEqual(tmp_path.parent, decisions_dir)
        self.assertTrue(tmp_path.name.endswith(".tmp"))
        self.assertNotEqual(tmp_path, path)
        # The original file is byte-identical (no partial write)...
        self.assertEqual(path.read_bytes(), before)
        # ...and no stray .tmp file was left behind in decisions/.
        leftovers = [p for p in decisions_dir.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    # (9) A close must be earned. `status: "decided"` used to be whatever the
    #     client asserted, so a batch could close over items nobody answered —
    #     and a blank `decision` reads exactly like a deliberate pass. This is
    #     the regression test for studio-pilot-2026-08-01.
    def test_close_is_refused_while_items_are_still_blank(self):
        root = self.make_workspace()
        path = self.write_batch(root, _batch())
        before = path.read_bytes()

        status, payload = post_json(
            "/api/decision-board/decide", {"batch_id": "test-batch", "close": True})

        self.assertEqual(status, 409)
        self.assertFalse(payload["saved"])
        # The caller is told exactly which items are missing, not just "no".
        self.assertEqual(payload["undecided"], ["item-01", "item-02"])
        # And nothing was written — a refused close leaves no trace of a close.
        self.assertEqual(path.read_bytes(), before)

        # NEGATIVE CONTROL: the same request on a fully-answered batch succeeds,
        # so the 409 above is the gate firing and not a broken close path.
        for item_id in ("item-01", "item-02"):
            post_json("/api/decision-board/decide",
                      {"batch_id": "test-batch", "item_id": item_id,
                       "decision": {"action": "approve"}})
        ok_status, ok_payload = post_json(
            "/api/decision-board/decide", {"batch_id": "test-batch", "close": True})
        self.assertEqual(ok_status, 200)
        self.assertTrue(ok_payload["closed"])
        self.assertEqual(ok_payload["skipped"], [])

    # (10) The explicit escape hatch: skipping is allowed, but it is recorded as
    #      an outcome with provenance — never left as a blank.
    def test_skip_undecided_writes_a_real_outcome(self):
        root = self.make_workspace()
        path = self.write_batch(root, _batch())
        post_json("/api/decision-board/decide",
                  {"batch_id": "test-batch", "item_id": "item-01",
                   "decision": {"action": "approve"}})

        status, payload = post_json(
            "/api/decision-board/decide",
            {"batch_id": "test-batch", "close": True, "skip_undecided": True,
             "decided_by": "self-declared:owner", "skip_note": "先不決"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["skipped"], ["item-02"])

        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "decided")
        skipped = saved["items"][1]["decision"]
        self.assertEqual(skipped["action"], "skipped")
        self.assertEqual(skipped["decided_by"], "self-declared:owner")
        self.assertEqual(skipped["note"], "先不決")
        self.assertTrue(skipped["decided_at"].endswith("Z"))
        # The item that WAS answered keeps its own decision untouched.
        self.assertEqual(saved["items"][0]["decision"]["action"], "approve")
        # The whole point: no blank survives behind a decided status.
        self.assertEqual(serve._undecided_item_ids(saved), [])

    # (11) LAW 1 covers a skip exactly as it covers a decision — a close can no
    #      more claim verified provenance than an item can.
    def test_skip_rejects_a_provenance_it_did_not_perform(self):
        root = self.make_workspace()
        path = self.write_batch(root, _batch())
        before = path.read_bytes()

        status, payload = post_json(
            "/api/decision-board/decide",
            {"batch_id": "test-batch", "close": True, "skip_undecided": True,
             "decided_by": "verified:owner"},
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["saved"])
        self.assertEqual(path.read_bytes(), before)

    # (12) Re-affirming a choice is not undoing it. The board hides an item 1.4s
    #      after saving, so a human re-clicking to check their answer had saved
    #      used to erase it — the "存不進去" report. Undo has its own button.
    def test_clicking_the_chosen_option_again_does_not_clear_it(self):
        root = self.make_workspace()
        self.write_batch(root, _batch())
        status, body, _ = run_handler_raw("GET", "/decide/test-batch")
        self.assertEqual(status, 200)
        script = body.decode("utf-8")

        # POSITIVE: the re-click path calls reaffirm(), which only flashes.
        self.assertIn("function reaffirm()", script)
        self.assertIn("if(curAction()===a){reaffirm();return;}", script)
        self.assertIn("if(curAction()==='pick'&&curOption()===idx){reaffirm();return;}", script)
        # NEGATIVE CONTROL: the old toggle-to-clear wiring is gone, so this test
        # would have failed on the code that shipped the bug.
        self.assertNotIn("if(curAction()===a){send(null);}", script)
        self.assertNotIn("curOption()===idx){send(null);}", script)
        # Deselecting is still possible — through the control that means it.
        self.assertIn("decision-clear", script)
        # And the on-page instructions no longer teach the toggle.
        self.assertNotIn("再按同一個選項會取消", script)


if __name__ == "__main__":
    unittest.main()
