"""Tests for the sid short-code system: alphabet/check math, engine assignment
on publish, resolution surfaces (read/link/search/[[sid]]/validate), and the
one-time backfill for existing documents and artifacts."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "mcp_package") not in sys.path:
    sys.path.insert(0, str(ROOT / "mcp_package"))

import brainhub  # noqa: E402
from brainhub_core.sid import (  # noqa: E402
    CHECK_ALPHABET,
    CROCKFORD32,
    check_symbol,
    generate_sid,
    is_sid,
    normalize_sid,
)
from brainhub_core.validation import validate_wiki  # noqa: E402
from mcp_package.brainhub_core import wiki_publish  # noqa: E402


class SidMathTests(unittest.TestCase):
    def test_alphabet_is_crockford_base32_plus_check_symbols(self):
        self.assertEqual(CROCKFORD32, "0123456789ABCDEFGHJKMNPQRSTVWXYZ")
        for banned in "ILOU":
            self.assertNotIn(banned, CROCKFORD32)
        self.assertEqual(CHECK_ALPHABET, CROCKFORD32 + "*~$=U")

    def test_check_symbol_known_vectors(self):
        # decode(W)=28 -> 28*32^4 = 29360128; 29360128 mod 37 = 36 -> "U"
        self.assertEqual(check_symbol("W0000"), "U")
        # decode(A)=10 -> 10*32^4 = 10485760; mod 37 = 34 -> "$"
        self.assertEqual(check_symbol("A0000"), "$")
        # case-insensitive
        self.assertEqual(check_symbol("w0000"), "U")

    def test_generate_shape_uniqueness_and_type_codes(self):
        existing: set[str] = set()
        for _ in range(200):
            sid = generate_sid("W", existing)
            self.assertEqual(len(sid), 6)
            self.assertTrue(sid.startswith("W"))
            self.assertTrue(all(char in CROCKFORD32 for char in sid[:5]))
            self.assertEqual(sid[5], check_symbol(sid[:5]))
            self.assertTrue(is_sid(sid))
            self.assertNotIn(sid, existing)
            existing.add(sid)
        self.assertTrue(generate_sid("A").startswith("A"))
        with self.assertRaises(ValueError):
            generate_sid("Z")

    def test_normalize_accepts_lowercase_and_confusables(self):
        sid = generate_sid("W")
        self.assertEqual(normalize_sid(sid.lower()), sid)
        # I/L fold to 1 and O folds to 0 in the random part
        prefix = "W10AB"
        typed = "WIOAB" + check_symbol(prefix)
        self.assertEqual(normalize_sid(typed), prefix + check_symbol(prefix))

    def test_normalize_rejects_bad_input(self):
        sid = generate_sid("W")
        bad_check = sid[:5] + ("0" if sid[5] != "0" else "1")
        for value in ("", "W123", sid + "X", "Z" + sid[1:], bad_check, "not-a-sid"):
            self.assertEqual(normalize_sid(value), "", value)


class SidEngineTests(unittest.TestCase):
    def make_workspace(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        workspace = Path(temp_dir.name) / "brainhub"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(brainhub.main(["init", str(workspace)]), 0)
        return workspace

    def test_publish_assigns_sid_and_preserves_it_on_republish(self):
        workspace = self.make_workspace()

        first = wiki_publish.publish_document(workspace, "Sid Page", "First body.", agent="t")
        self.assertTrue(is_sid(first["sid"]))
        self.assertTrue(first["sid"].startswith("W"))

        again = wiki_publish.publish_document(workspace, "Sid Page", "Second body.", agent="t")
        self.assertEqual(again["sid"], first["sid"])

        other = wiki_publish.publish_document(workspace, "Other Page", "Other body.", agent="t")
        self.assertNotEqual(other["sid"], first["sid"])

    def test_read_and_search_resolve_sid(self):
        workspace = self.make_workspace()
        result = wiki_publish.publish_document(workspace, "Sid Target", "A quorlith body.", agent="t")
        sid = result["sid"]

        by_sid = wiki_publish.read_document(workspace, sid)
        self.assertEqual(by_sid["handle"], "sid-target")
        self.assertEqual(by_sid["sid"], sid)
        # lowercase sid resolves too
        self.assertEqual(wiki_publish.read_document(workspace, sid.lower())["handle"], "sid-target")

        hits = wiki_publish.search_documents(workspace, "quorlith")
        self.assertEqual(hits[0]["handle"], "sid-target")
        self.assertEqual(hits[0]["sid"], sid)

        # CLI read accepts the sid directly
        output = io.StringIO()
        with redirect_stdout(output):
            code = brainhub.main(["read", sid, str(workspace), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["handle"], "sid-target")

    def test_link_accepts_sids_and_canonicalizes_to_handles(self):
        workspace = self.make_workspace()
        target = wiki_publish.publish_document(workspace, "Link Target", "Target body.", agent="t")
        source = wiki_publish.publish_document(workspace, "Link Source", "Source body.", agent="t")

        result = wiki_publish.link_documents(workspace, source["sid"], target["sid"])

        self.assertTrue(result["linked"])
        self.assertEqual(result["from_handle"], "link-source")
        self.assertEqual(result["to_handle"], "link-target")

    def test_body_sid_wikilink_resolves_and_validate_accepts_it(self):
        workspace = self.make_workspace()
        target = wiki_publish.publish_document(workspace, "Sid Anchor", "Anchor body.", agent="t")
        sid = target["sid"]

        result = wiki_publish.publish_document(
            workspace, "Sid Referrer", f"TLDR: refers to [[{sid}]] inline.", agent="t",
        )

        # the [[sid]] target is known -> no dead-link warning
        self.assertEqual(result["warnings"], [])
        self.assertIn(sid.lower(), result["links"])

        validation = validate_wiki(workspace / "wiki")
        dead = [f for f in validation["findings"] if f["code"] == "dead_wikilink"]
        self.assertEqual(dead, [])

    def test_sid_backfill_assigns_missing_sids_once(self):
        workspace = self.make_workspace()
        wiki_dir = workspace / "wiki"

        # legacy document page published before the sid era (no sid: line)
        legacy = wiki_dir / "documents" / "legacy-page.md"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(
            "---\n"
            "type: document\n"
            'title: "Legacy Page"\n'
            "handle: legacy-page\n"
            "status: active\n"
            'date_published: "2026-01-01T00:00:00+00:00"\n'
            'date_updated: "2026-01-01T00:00:00+00:00"\n'
            'published_by: "t"\n'
            "tags: [document]\n"
            "---\n\n# Legacy Page\n\n> **TLDR:** legacy.\n\nBody.\n",
            encoding="utf-8",
        )
        # legacy artifact record without a sid
        report = workspace / "artifacts" / "reports" / "old.md"
        report.write_text("old report\n", encoding="utf-8")
        report.with_name("old.md.meta.json").write_text(
            json.dumps({"kind": "report", "task": "t", "agent": "t"}) + "\n",
            encoding="utf-8",
        )

        output = io.StringIO()
        with redirect_stdout(output):
            code = brainhub.main(["sid-backfill", str(workspace), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["documents"]["count"], 1)
        self.assertEqual(payload["artifacts"]["count"], 1)

        # frontmatter gained a sid; handle/title untouched
        text = legacy.read_text(encoding="utf-8")
        meta, _body = wiki_publish.parse_frontmatter(text)
        self.assertTrue(is_sid(meta.get("sid")))
        self.assertEqual(meta.get("handle"), "legacy-page")
        self.assertEqual(meta.get("title"), "Legacy Page")
        artifact_meta = json.loads(report.with_name("old.md.meta.json").read_text(encoding="utf-8"))
        self.assertTrue(is_sid(artifact_meta.get("sid")))
        self.assertTrue(artifact_meta["sid"].startswith("A"))

        # idempotent: second run assigns nothing
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(brainhub.main(["sid-backfill", str(workspace), "--json"]), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["documents"]["count"], 0)
        self.assertEqual(payload["artifacts"]["count"], 0)

    def test_artifact_add_assigns_artifact_sid(self):
        workspace = self.make_workspace()
        source = workspace.parent / "input.md"
        source.write_text("artifact body\n", encoding="utf-8")

        with redirect_stdout(io.StringIO()):
            code = brainhub.main([
                "artifact", "add", str(source), str(workspace),
                "--kind", "report", "--task", "t", "--agent", "t",
            ])
        self.assertEqual(code, 0)

        meta_path = workspace / "artifacts" / "reports" / "input.md.meta.json"
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertTrue(is_sid(metadata["sid"]))
        self.assertTrue(metadata["sid"].startswith("A"))


if __name__ == "__main__":
    unittest.main()
