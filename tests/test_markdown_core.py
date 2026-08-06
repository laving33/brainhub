import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core.markdown import markdown_to_html  # noqa: E402


class MarkdownCoreTests(unittest.TestCase):
    def test_inline_markdown_sanitizes_html_and_links(self):
        rendered = markdown_to_html(
            "Hello <script>alert(1)</script> "
            "and [bad](javascript:alert%281%29) "
            "and [ok](https://example.com?a=1&b=2) "
            "and [[target|<b>label</b>]] "
            "and `<tag>`"
        )

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        # The guarantee is "a javascript: URL never becomes a clickable link",
        # not "it becomes href='#'". markdown-it refuses to build the link at
        # all and leaves the literal text, which is strictly safer — asserting
        # the old shape would have failed a better implementation.
        self.assertNotIn("<a href=\"javascript:", rendered)
        self.assertNotIn('<a href="#">bad</a>', rendered)
        self.assertIn('<a href="https://example.com?a=1&amp;b=2">ok</a>', rendered)
        self.assertIn('<a href="/page/target">&lt;b&gt;label&lt;/b&gt;</a>', rendered)
        self.assertIn("<code>&lt;tag&gt;</code>", rendered)
        self.assertNotIn("<script>", rendered)
        # Not `assertNotIn("javascript:")`: the refused link survives as escaped
        # literal text, which is safer than the old href="#" and would fail a
        # blanket substring check. The property is "no live javascript: anchor".
        self.assertNotIn('href="javascript:', rendered.lower())

    def test_wikilink_targets_encode_path_separators(self):
        rendered = markdown_to_html("[[../raw/private|private]]")

        self.assertIn('<a href="/page/..%2Fraw%2Fprivate">private</a>', rendered)
        self.assertNotIn("/page/../raw/private", rendered)

    def test_blocks_tables_lists_and_code_blocks(self):
        rendered = markdown_to_html(
            "# Title\n\n"
            "> quote **bold**\n\n"
            "- one\n"
            "- two\n\n"
            "| A | B |\n"
            "|---|---|\n"
            "| `x` | *y* |\n\n"
            "```python\n"
            "<raw>\n"
            "```"
        )

        self.assertIn("<h1>Title</h1>", rendered)
        # CommonMark wraps block content inside a blockquote in a paragraph;
        # the previous hand-written renderer did not. Assert the content and its
        # container, not the exact tag sequence of one implementation.
        self.assertIn("<blockquote>", rendered)
        self.assertIn("quote <strong>bold</strong>", rendered)
        self.assertIn("<ul>", rendered)
        self.assertIn("<li>one</li>", rendered)
        self.assertIn("<table>", rendered)
        self.assertIn("<td><code>x</code></td>", rendered)
        self.assertIn('<pre><code class="language-python">', rendered)
        self.assertIn("&lt;raw&gt;", rendered)


if __name__ == "__main__":
    unittest.main()


class FullMarkdownSyntaxTests(unittest.TestCase):
    """Every standard construct renders, because a missing one is how the
    non-standard workarounds start.

    Images were the case that proved it: `![chart](x.png)` produced nothing, so
    an author pasted raw SVG into the page instead and it rendered as hundreds
    of lines of escaped source. The renderer did not offer the standard way to
    do the thing (owner, 2026-07-22: "要支援 md 所有語法功能").
    """

    def render(self, source: str) -> str:
        return markdown_to_html(source)

    def test_images(self):
        rendered = self.render("![chart](/raw/RX7K2M/q3.png)")
        self.assertIn("<img", rendered)
        self.assertIn('src="/raw/RX7K2M/q3.png"', rendered)
        self.assertIn('alt="chart"', rendered)

    def test_strikethrough(self):
        self.assertRegex(self.render("~~gone~~"), r"<(s|del)>gone</(s|del)>")

    def test_task_lists(self):
        rendered = self.render("- [ ] open\n- [x] done")
        self.assertIn("checkbox", rendered)
        self.assertIn("checked", rendered)

    def test_nested_lists(self):
        rendered = self.render("- outer\n    - inner")
        self.assertGreater(rendered.count("<ul>"), 1)

    def test_ordered_lists_keep_their_start(self):
        self.assertIn('start="3"', self.render("3. three\n4. four"))

    def test_footnotes(self):
        self.assertIn("footnote", self.render("claim[^1]\n\n[^1]: source"))

    def test_definition_lists(self):
        self.assertIn("<dd>", self.render("term\n:   definition"))

    def test_tables_headings_code_and_quotes_still_work(self):
        rendered = self.render(
            "# T\n\n> q\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```py\nx = 1\n```\n"
        )
        for fragment in ("<h1>", "<blockquote>", "<table>", "language-py"):
            self.assertIn(fragment, rendered)

    def test_bare_domains_are_not_auto_linked(self):
        """The renderer must not invent links the author did not write.

        Auto-linking every bare domain turned a page listing competitor domains
        into a page linking to competitors, against the standing rule that
        outward-facing material links to coverage and never to a competitor's
        own site — and it emitted http:// rather than https://. Found by diffing
        all 278 pages through the old and new renderers, not by reading the
        config (2026-07-22).
        """
        rendered = self.render("白名單（chatgpt.com／bmw.com.tw）辨識，見 https://example.com")
        self.assertNotIn("<a", rendered)

    def test_links_the_author_wrote_still_work(self):
        # Positive control: not linking anything would also pass the test above.
        self.assertIn('href="https://example.com"', self.render("[see](https://example.com)"))


class RendererSecurityTests(unittest.TestCase):
    """Enabling every markdown feature must not enable HTML injection with it."""

    def test_raw_html_is_still_inert(self):
        rendered = markdown_to_html("<script>alert(1)</script>\n\n<b>bold</b>")
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<b>bold</b>", rendered)

    def test_dangerous_targets_never_become_reachable_links(self):
        # Assert the property (nothing links to the dangerous target), not a
        # substring. markdown-it refuses some of these outright and leaves the
        # literal text; others it neuters to href="#". Both are fine — what must
        # never happen is a live anchor pointing at the target.
        for source, forbidden in (
            ("[x](javascript:alert(1))", 'href="javascript:'),
            ("[x](JaVaScRiPt:alert(1))", 'href="javascript:'),
            ("[x](vbscript:x)", 'href="vbscript:'),
            ("[x](//evil.example)", 'href="//evil.example'),
        ):
            with self.subTest(source=source):
                self.assertNotIn(forbidden, markdown_to_html(source).lower())

    def test_image_sources_are_filtered_the_same_way(self):
        rendered = markdown_to_html("![x](javascript:alert(1))").lower()
        self.assertNotIn('src="javascript:', rendered)

    def test_ordinary_links_still_work(self):
        # Positive control: the filter above is worthless if it blocks everything.
        rendered = markdown_to_html("[a](https://example.com) [b](/page/x) [c](mailto:x@y.z)")
        self.assertEqual(rendered.count("<a href"), 3)

    def test_wikilinks_inside_code_are_not_links(self):
        self.assertNotIn("<a", markdown_to_html("`[[literal]]`"))
