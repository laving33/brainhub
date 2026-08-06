"""CJK contract tests — one per subsystem that was silently broken for Chinese.

The bug class: normalization that whitelists ASCII deletes CJK outright, and word
rules that assume spaces collapse a whole Chinese sentence into one token. It never
raised — it returned empty sets, zero results, or the wrong record. It shipped three
times in three modules, so every subsystem gets a test here, not just search.

If you add a module that touches user text, add a case to this file.
"""
from __future__ import annotations

import ast
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_package"))

import brainhub  # noqa: E402
from brainhub_core import artifact_store, consolidate, memory, text, wiki, wiki_publish  # noqa: E402
from brainhub_core.search import build_fts_index  # noqa: E402
from brainhub_core.text import (  # noqa: E402
    expand_units,
    fts_text,
    normalized_search_text,
    search_words,
    token_ok,
)
from brainhub_core.web_pages import _heading_slug  # noqa: E402


class NormalizationTests(unittest.TestCase):
    def test_no_script_is_deleted(self):
        """The original rule was `[^a-z0-9]+` (erased Chinese). The first repair
        whitelisted the Han ranges we thought of, which still deleted kana, Hangul
        and astral CJK. Enumerating scripts is how you keep this bug."""
        cases = {
            "客戶資料": "客戶資料",      # Han
            "データ分析": "データ分析",    # kana
            "한국어 검색": "한국어 검색",  # Hangul (Korean DOES use spaces)
            "𠮷野家": "𠮷野家",          # astral CJK — a real surname character
            "ㄅㄆㄇ": "ㄅㄆㄇ",           # Bopomofo
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalized_search_text(raw), expected)

    def test_fullwidth_folds_to_halfwidth(self):
        """Chinese/Japanese IMEs emit full-width forms. Unfolded, "Ｅｘｃｅｌ" and
        "excel" are different strings and one of them finds nothing."""
        self.assertEqual(normalized_search_text("Ｅｘｃｅｌ報表"), "excel報表")
        self.assertEqual(normalized_search_text("１２３號"), "123號")

    def test_punctuation_still_separates(self):
        self.assertEqual(normalized_search_text("客戶，資料。隔離"), "客戶 資料 隔離")
        self.assertEqual(normalized_search_text("tenant_guard"), "tenant guard")

    def test_token_length_rule_is_script_aware(self):
        self.assertTrue(token_ok("憑證"))    # 2 chars — most Chinese words are
        self.assertFalse(token_ok("ab"))     # ASCII noise
        self.assertTrue(token_ok("abc"))

    def test_unsegmented_runs_become_overlapping_bigrams(self):
        self.assertEqual(expand_units("訊號驗證"), ["訊號", "號驗", "驗證"])
        # ASCII must stay whole, or "auth" starts matching inside "oauth".
        self.assertEqual(expand_units("daemon隱形"), ["daemon", "隱形"])

    def test_index_and_query_share_one_vocabulary(self):
        """Two tokenizers that disagree are worse than one bad one: each looks
        correct alone, and the lookup misses every time."""
        indexed = search_words("客戶資料隔離")
        self.assertTrue(indexed & set(expand_units(normalized_search_text("資料"))))
        self.assertIn("資料", indexed)


class SearchTests(unittest.TestCase):
    def make_brain(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        workspace = Path(temp_dir.name) / "brainhub"
        brainhub.main(["init", str(workspace)])
        wiki_publish.publish_document(
            workspace,
            "tenant-guard 客戶資料隔離模型",
            "客戶資料的隔離由 hook 強制執行，跨客戶讀取一律擋下。",
            agent="test",
        )
        wiki_publish.publish_document(
            workspace, "Deploy Gate", "All deploys go through a pworker gate.", agent="test",
        )
        return workspace

    def handles(self, workspace: Path, query: str) -> list[str]:
        return [hit["handle"] for hit in wiki_publish.search_documents(workspace, query)]

    def test_query_without_spaces_finds_the_page(self):
        """Chinese is written without spaces, so this is what actually gets typed.
        It returned 0 — indistinguishable from "the brain doesn't know this"."""
        workspace = self.make_brain()
        for query in ("客戶資料要怎麼隔離", "憑證隔離", "隔離模型"):
            with self.subTest(query=query):
                handles = self.handles(workspace, query)
                self.assertTrue(handles, f"{query!r} returned 0 matches")
                self.assertEqual(handles[0], "tenant-guard-客戶資料隔離模型")

    def test_aggregate_pages_never_outrank_the_real_page(self):
        """index/log carry every other page's title in their body, so they match
        any query at all. They must not spend a slot in the agent's top-N."""
        workspace = self.make_brain()
        handles = self.handles(workspace, "客戶資料要怎麼隔離")
        self.assertEqual(handles[0], "tenant-guard-客戶資料隔離模型")
        self.assertNotIn("index", handles)
        self.assertNotIn("log", handles)

    def test_english_word_boundaries_survive(self):
        workspace = self.make_brain()
        self.assertIn("deploy-gate", self.handles(workspace, "deploy gate"))

    def test_token_index_holds_units_the_query_can_hit(self):
        workspace = self.make_brain()
        cache = wiki.build_wiki_cache(workspace / "wiki")
        self.assertIn("客戶", cache["token_index"])
        self.assertIn("隔離", cache["token_index"])


class FtsTests(unittest.TestCase):
    def test_fts_index_matches_a_two_character_chinese_word(self):
        """unicode61 indexes a whole Han run as ONE token (measured on sqlite
        3.45.1), so `客戶` scored 0 inside `客戶資料隔離模型` and the FTS pre-filter
        contributed nothing for Chinese. Bigrams on both sides fix it.

        ⚠ `trigram` is NOT the fix despite the common advice: it needs >=3 chars,
        and most Chinese words are exactly 2.
        """
        pages = [{"name": "iso", "title": "客戶資料隔離模型", "type": "concept",
                  "category": "concepts", "tldr": "", "aliases": [], "tags": []}]
        index = build_fts_index(pages, {"iso": "客戶資料的隔離由 hook 強制執行"})
        if index is None:
            self.skipTest("sqlite FTS5 unavailable on this host")
        self.assertEqual(index.search("客戶", limit=5), ["iso"])
        self.assertEqual(index.search("隔離", limit=5), ["iso"])
        index.close()

    def test_fts_text_expands_only_unsegmented_scripts(self):
        self.assertEqual(fts_text("客戶資料"), "客戶 戶資 資料")
        self.assertEqual(fts_text("deploy gate"), "deploy gate")


class MemoryTests(unittest.TestCase):
    """The worst of the family: `memory_tokens` split on `[^a-z0-9]+`, so every
    Chinese character was a DELIMITER. Chinese memories recalled as []."""

    def record(self) -> dict:
        return {
            "name": "客戶資料必須隔離存放", "title": "客戶資料必須隔離存放",
            "tldr": "客戶資料必須隔離存放，避免跨租戶洩漏。",
            "body": "我們決定客戶資料必須隔離存放，避免跨租戶洩漏。",
            "tags": [], "type": "decision", "status": "active",
        }

    def test_natural_chinese_question_recalls_the_memory(self):
        record = self.record()
        for query in ("客戶資料要怎麼隔離", "資料隔離的規則是什麼"):
            with self.subTest(query=query):
                self.assertGreater(memory.score_memory(record, query), 0)
                hits = memory.recall_memories([record], query)
                self.assertEqual([hit["title"] for hit in hits], ["客戶資料必須隔離存放"])

    def test_distinct_chinese_titles_get_distinct_slugs(self):
        """slugify() mapped EVERY Chinese title to the literal string "memory", so
        the second Chinese memory you ever saved was flagged as a duplicate of the
        first (same_slug -> score 100) and lookups resolved to the wrong record."""
        first = memory.slugify("客戶資料必須隔離存放")
        second = memory.slugify("訊號會說謊")
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, "memory")
        self.assertEqual(memory.slugify("客戶資料"), "客戶資料")

    def test_chinese_tags_are_not_dropped(self):
        self.assertTrue(memory.slugify("財務", fallback=""))

    def test_chinese_negation_is_detected(self):
        """A memory saying "DON'T deploy with root" read to the conflict engine
        exactly like "deploy with root" — the negation was invisible."""
        for text in ("不要用 root 帳號部署", "別把金鑰寫進 repo", "禁止跨租戶讀取", "請勿覆寫"):
            with self.subTest(text=text):
                self.assertTrue(memory.has_negation(text))

    def test_ordinary_words_containing_negation_characters_are_not_negations(self):
        """別 means "don't" only at the head of a clause; 特別/差別/個別 are not
        negations. Substring matching on unsegmented text has to earn this."""
        for text in ("特別注意這個差別", "用 root 帳號部署", "類別已更新"):
            with self.subTest(text=text):
                self.assertFalse(memory.has_negation(text))


class ConsolidateTests(unittest.TestCase):
    def test_identical_chinese_captures_deduplicate(self):
        """`[a-z0-9]{3,}` is a whitelist, so a Chinese capture yielded set(), the
        caller skipped it, and Jaccard dedup never fired: ten identical Chinese
        captures stayed ten captures. Silent no-op, never an error."""
        snippet = "客戶資料必須隔離存放，避免跨租戶洩漏"
        captures = [
            {"id": f"c{i}", "snippet": snippet, "project": "p", "created": "2026-07-12"}
            for i in range(3)
        ]
        plan = consolidate.build_consolidation_plan(
            captures_payload={"captures": captures},
            inbox_payload={"memories": []},
        )
        self.assertTrue(plan["duplicate_groups"], "identical Chinese captures were not grouped")
        self.assertEqual(plan["duplicate_capture_count"], 2)  # 3 captures -> keep 1, 2 dupes


class SlugTests(unittest.TestCase):
    def test_chinese_titles_get_distinct_artifact_filenames(self):
        """Every Chinese-titled artifact slugged to "artifact.html". The store
        fails closed (`Artifact already exists`) so nothing was overwritten — but
        the second Chinese artifact you ever published could not be saved, and the
        error blamed a duplicate that did not exist."""
        first = artifact_store.slugify_filename("客戶資料報表")
        second = artifact_store.slugify_filename("訊號會說謊")
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, "artifact")

    def test_shared_slugify_keeps_scripts_and_folds_width(self):
        self.assertEqual(text.slugify("客戶資料 隔離"), "客戶資料-隔離")
        self.assertEqual(text.slugify("Ｅｘｃｅｌ 報表"), "excel-報表")
        self.assertEqual(text.slugify("!!!", fallback="page"), "page")

    def test_no_module_reintroduces_an_ascii_only_slug(self):
        """This bug shipped three times because each module wrote its own
        `[^a-z0-9]+` slug/tokenizer. text.py is the SSOT; this test fails the build
        on copy number ten."""
        root = Path(__file__).resolve().parents[1]
        # AST, not grep: the docstrings deliberately quote the old broken regex to
        # explain what went wrong, and a text scan cannot tell prose from a call.
        ascii_class = re.compile(r"\[\^?a-z(?:A-Z)?0-9")
        offenders = []
        for path in list((root / "mcp_package").rglob("*.py")) + [root / "serve.py", root / "brainhub_engine.py"]:
            if path.name == "text.py" or "test" in path.name:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                is_re = isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) \
                    and func.value.id == "re" \
                    and func.attr in {"sub", "split", "findall", "compile", "match", "search"}
                if not is_re:
                    continue
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                            and ascii_class.search(arg.value):
                        offenders.append(f"{path.relative_to(root)}:{node.lineno}  {arg.value!r}")
        self.assertEqual(
            offenders, [],
            "ASCII-only text regex found — it deletes CJK. Import from brainhub_core.text instead:\n"
            + "\n".join(offenders),
        )


class HeadingAnchorTests(unittest.TestCase):
    def test_chinese_headings_get_meaningful_anchors(self):
        """Every Chinese heading used to anchor to #section-2, #section-3..."""
        used: set[str] = set()
        first = _heading_slug("部署流程", used)
        used.add(first)
        second = _heading_slug("客戶資料", used)
        self.assertEqual(first, "部署流程")
        self.assertEqual(second, "客戶資料")

    def test_duplicate_headings_still_deduplicate(self):
        used: set[str] = set()
        first = _heading_slug("部署流程", used)
        used.add(first)
        self.assertNotEqual(_heading_slug("部署流程", used), first)


if __name__ == "__main__":
    unittest.main()
