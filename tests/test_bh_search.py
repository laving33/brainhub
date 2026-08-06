"""Contract tests for the `search` verb (bh-search): brainhub.main(["search", ...])
and wiki_publish.search_documents.

Only this file is created/edited for the search verb; no shared file is touched.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import brainhub
from mcp_package.brainhub_core import wiki_publish


class BrainHubSearchVerbTests(unittest.TestCase):
    def make_workspace(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        workspace = Path(temp_dir.name) / "brainhub"
        self.assertEqual(brainhub.main(["init", str(workspace)]), 0)
        return workspace

    def publish(self, workspace: Path, title: str, body: str) -> dict:
        return wiki_publish.publish_document(workspace, title, body, agent="test-writer")

    # ------------------------------------------------------------------
    # (1) + (2): stable handle, read-back-able, is_document, correct fields
    # ------------------------------------------------------------------
    def test_search_returns_stable_readback_handle_for_matching_document(self):
        workspace = self.make_workspace()
        self.publish(
            workspace,
            "Quokka Migration Notes",
            "The quokka waddled across the paddock searching for zylenthium crystals.",
        )
        self.publish(
            workspace,
            "Second Unrelated Page",
            "This page talks about kangaroos and eucalyptus only.",
        )

        results = wiki_publish.search_documents(workspace, "zylenthium")

        self.assertTrue(results, "expected at least one match for a distinctive body word")
        hit = results[0]
        for key in ("handle", "title", "category", "type", "snippet", "score", "is_document"):
            self.assertIn(key, hit)
        self.assertEqual(hit["handle"], "quokka-migration-notes")
        self.assertTrue(hit["is_document"])

        # read-back: the returned handle must be directly usable by read_document
        readback = wiki_publish.read_document(workspace, hit["handle"])
        self.assertEqual(readback["title"], "Quokka Migration Notes")
        self.assertIn("zylenthium", readback["body"])

    # ------------------------------------------------------------------
    # (3) documents_only filters out non-document wiki pages (index/log)
    # ------------------------------------------------------------------
    def test_documents_only_filters_to_document_category(self):
        workspace = self.make_workspace()
        self.publish(
            workspace,
            "Filter Test Alpha",
            "mentions the shared word flumberoo for search filtering purposes",
        )
        self.publish(
            workspace,
            "Filter Test Beta",
            "also mentions the shared word flumberoo here",
        )

        all_results = wiki_publish.search_documents(workspace, "flumberoo")
        doc_only_results = wiki_publish.search_documents(workspace, "flumberoo", documents_only=True)

        self.assertTrue(doc_only_results)
        for record in doc_only_results:
            self.assertEqual(record["category"], "documents")
            self.assertTrue(record["is_document"])

        # default (no flag) MAY include other wiki pages; it must at least
        # include every document hit that documents_only returned.
        all_handles = {r["handle"] for r in all_results}
        for record in doc_only_results:
            self.assertIn(record["handle"], all_handles)

    # ------------------------------------------------------------------
    # (4) CLI text output: "Matches: N" header + one line per hit; --json
    # ------------------------------------------------------------------
    def test_cli_text_output_has_matches_header_and_one_line_per_hit(self):
        workspace = self.make_workspace()
        self.publish(
            workspace,
            "CLI Text Output Doc",
            "the word wobblesnatch appears exactly once in this body",
        )

        output = io.StringIO()
        with redirect_stdout(output):
            code = brainhub.main(["search", "wobblesnatch", str(workspace)])
        self.assertEqual(code, 0)

        printed = output.getvalue()
        lines = printed.splitlines()
        self.assertTrue(lines[0].startswith("Matches: "))
        header_count = int(lines[0].split("Matches: ", 1)[1])
        self.assertGreaterEqual(header_count, 1)
        # one result line per hit, formatted "- [handle] title (category)"
        result_lines = [line for line in lines[1:] if line.startswith("- [")]
        self.assertEqual(len(result_lines), header_count)
        self.assertTrue(any("cli-text-output-doc" in line for line in result_lines))

    def test_cli_json_output_is_array_of_dicts_with_handle_and_snippet(self):
        workspace = self.make_workspace()
        self.publish(
            workspace,
            "JSON Output Doc",
            "the word crumplenugget appears exactly once in this body",
        )

        output = io.StringIO()
        with redirect_stdout(output):
            code = brainhub.main(["search", "crumplenugget", str(workspace), "--json"])
        self.assertEqual(code, 0)

        payload = json.loads(output.getvalue())
        self.assertIsInstance(payload, list)
        self.assertTrue(payload)
        for element in payload:
            self.assertIn("handle", element)
            self.assertIn("snippet", element)
        self.assertTrue(any(e["handle"] == "json-output-doc" for e in payload))

    # ------------------------------------------------------------------
    # (5) --limit caps the number of results
    # ------------------------------------------------------------------
    def test_limit_caps_result_count(self):
        workspace = self.make_workspace()
        for index in range(5):
            self.publish(
                workspace,
                f"Limit Test Doc {index}",
                "shared distinctive marker word snorklewhump appears in every doc",
            )

        unlimited = wiki_publish.search_documents(workspace, "snorklewhump", documents_only=True)
        self.assertGreaterEqual(len(unlimited), 5)

        limited = wiki_publish.search_documents(workspace, "snorklewhump", documents_only=True, limit=2)
        self.assertEqual(len(limited), 2)

        # also verify through the CLI --limit flag
        output = io.StringIO()
        with redirect_stdout(output):
            code = brainhub.main([
                "search", "snorklewhump", str(workspace),
                "--documents-only", "--limit", "2", "--json",
            ])
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(len(payload), 2)

    # ------------------------------------------------------------------
    # (6) empty workspace (no documents published) -> empty list, no error
    # ------------------------------------------------------------------
    def test_empty_workspace_returns_empty_list_without_error(self):
        workspace = self.make_workspace()

        results = wiki_publish.search_documents(workspace, "anything")
        self.assertEqual(results, [])

        output = io.StringIO()
        with redirect_stdout(output):
            code = brainhub.main(["search", "anything", str(workspace)])
        self.assertEqual(code, 0)
        self.assertIn("Matches: 0", output.getvalue())

    # ------------------------------------------------------------------
    # tag filtering: colon convention == stored dash form
    # ------------------------------------------------------------------
    def _publish_tagged_fixture(self, workspace: Path) -> None:
        wiki_publish.publish_document(
            workspace, "Catalog Runbook", "Catalog operating notes.",
            agent="catalog", tags=["from:catalog", "domain:lab"],
        )
        wiki_publish.publish_document(
            workspace, "Chief Notes", "Chief operating notes.",
            agent="chief", tags=["from:chief", "domain:bridge"],
        )

    def test_tag_query_tokens_colon_dash_and_tag_prefix_all_filter(self):
        workspace = self.make_workspace()
        self._publish_tagged_fixture(workspace)

        for query in ("from:catalog", "from-catalog", "tag:from:catalog", "tag:from-catalog"):
            results = wiki_publish.search_documents(workspace, query)
            self.assertEqual(
                [hit["handle"] for hit in results], ["catalog-runbook"],
                f"query form {query!r} must resolve to the stored dash-form tag",
            )
            self.assertIn("from-catalog", results[0]["tags"])

    def test_tags_parameter_accepts_colon_and_dash_forms(self):
        workspace = self.make_workspace()
        self._publish_tagged_fixture(workspace)

        for tag in ("from:catalog", "from-catalog"):
            results = wiki_publish.search_documents(workspace, "", tags=[tag])
            self.assertEqual([hit["handle"] for hit in results], ["catalog-runbook"], tag)

    def test_multiple_tag_filters_must_all_match(self):
        workspace = self.make_workspace()
        self._publish_tagged_fixture(workspace)

        results = wiki_publish.search_documents(workspace, "from:catalog domain:lab")
        self.assertEqual([hit["handle"] for hit in results], ["catalog-runbook"])
        results = wiki_publish.search_documents(workspace, "from:catalog domain:bridge")
        self.assertEqual(results, [])

    def test_tag_filter_combines_with_free_text(self):
        workspace = self.make_workspace()
        wiki_publish.publish_document(workspace, "Catalog Alpha", "Talks about penguins.", agent="t", tags=["from:catalog"])
        wiki_publish.publish_document(workspace, "Catalog Beta", "Talks about walruses.", agent="t", tags=["from:catalog"])
        wiki_publish.publish_document(workspace, "Chief Penguins", "Talks about penguins too.", agent="t", tags=["from:chief"])

        results = wiki_publish.search_documents(workspace, "from:catalog penguins")
        self.assertEqual([hit["handle"] for hit in results], ["catalog-alpha"])

    def test_dash_token_stays_free_text_when_wiki_has_no_such_tag(self):
        workspace = self.make_workspace()
        wiki_publish.publish_document(workspace, "Domain-driven Design", "Notes about domain-driven design.", agent="t")

        results = wiki_publish.search_documents(workspace, "domain-driven design")
        self.assertTrue(results, "dash token without a matching tag must stay search text")
        self.assertEqual(results[0]["handle"], "domain-driven-design")

    def test_cli_tag_flag_and_inline_token_filter(self):
        workspace = self.make_workspace()
        self._publish_tagged_fixture(workspace)

        output = io.StringIO()
        with redirect_stdout(output):
            code = brainhub.main(["search", "from:catalog", str(workspace), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual([hit["handle"] for hit in payload], ["catalog-runbook"])

        output = io.StringIO()
        with redirect_stdout(output):
            code = brainhub.main(["search", "notes", str(workspace), "--tag", "from:chief", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual([hit["handle"] for hit in payload], ["chief-notes"])


class BrainHubChineseSearchTests(unittest.TestCase):
    """Chinese is written without spaces, so the query an agent actually types
    ("客戶資料要怎麼隔離") is one unsegmented run. Every regression here showed up
    as `Matches: 0` — which looks exactly like "the brain doesn't know this".
    """

    def make_workspace(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        workspace = Path(temp_dir.name) / "brainhub"
        self.assertEqual(brainhub.main(["init", str(workspace)]), 0)
        return workspace

    def make_brain(self) -> Path:
        workspace = self.make_workspace()
        wiki_publish.publish_document(
            workspace,
            "tenant-guard 客戶資料隔離模型",
            "客戶資料的隔離由 hook 強制執行。跨客戶讀取一律擋下，憑證另有一層。",
            agent="test-writer",
        )
        wiki_publish.publish_document(
            workspace,
            "訊號會說謊 驗證守則",
            "每個訊號都要寫出它會在什麼情況下說謊，交結論前先驗證 ground truth。",
            agent="test-writer",
        )
        return workspace

    def handles(self, workspace: Path, query: str) -> list[str]:
        return [hit["handle"] for hit in wiki_publish.search_documents(workspace, query)]

    def test_unspaced_chinese_query_finds_the_page(self):
        """The reported bug: 「憑證隔離」 returned 0 while 「憑證 隔離」 returned hits."""
        workspace = self.make_brain()
        for query in ("憑證隔離", "客戶資料要怎麼隔離"):
            with self.subTest(query=query):
                handles = self.handles(workspace, query)
                self.assertTrue(handles, f"unspaced Chinese query {query!r} returned 0 matches")
                self.assertEqual(handles[0], "tenant-guard-客戶資料隔離模型")

    def test_spaced_chinese_query_still_works(self):
        workspace = self.make_brain()
        handles = self.handles(workspace, "訊號 驗證")
        self.assertTrue(handles)
        self.assertEqual(handles[0], "訊號會說謊-驗證守則")

    def test_aggregate_pages_do_not_outrank_the_real_page(self):
        """index/log carry every other page's title in their body, so they match
        any query. They must never displace the page the query is about."""
        workspace = self.make_brain()
        handles = self.handles(workspace, "客戶資料要怎麼隔離")
        self.assertEqual(handles[0], "tenant-guard-客戶資料隔離模型")
        self.assertNotIn("index", handles)
        self.assertNotIn("log", handles)

    def test_ascii_word_boundaries_are_not_broken(self):
        """CJK matching is substring-based; ASCII must NOT be, or "auth" starts
        matching inside "oauth"."""
        workspace = self.make_workspace()
        wiki_publish.publish_document(
            workspace, "OAuth Provider Setup", "Configuring the oauth provider handshake.",
            agent="test-writer",
        )
        wiki_publish.publish_document(
            workspace, "Zylenthium Notes", "Nothing to do with logins.", agent="test-writer",
        )
        self.assertNotIn("zylenthium-notes", self.handles(workspace, "oauth"))


if __name__ == "__main__":
    unittest.main()
