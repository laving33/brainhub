import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core.web_layout import render_footer_html, render_header_html, render_layout, render_stat_grid  # noqa: E402


class WebLayoutCoreTests(unittest.TestCase):
    def test_header_has_primary_navigation_and_search(self):
        """Destination and label, not the class attribute.

        These read `href="/x">label</a>` rather than `<a href="/x">label</a>`
        because the opening tag now carries daisyUI classes. Pinning the whole
        tag pinned the styling too: adding one class turned four tests red while
        every destination and every label was still exactly right. What the nav
        owes a reader is that 匯入 goes to /ingest — the class it wears on the
        way is not this test's business.
        """
        html = render_header_html()

        self.assertIn('href="/ingest">匯入</a>', html)
        self.assertIn('href="/health">健康度</a>', html)
        self.assertIn('href="/brief">記憶簡報</a>', html)
        self.assertIn('href="/propose">草擬記憶</a>', html)
        self.assertIn('href="/graph">知識圖譜</a>', html)
        self.assertIn('href="/artifacts">產出</a>', html)
        self.assertIn('href="/documents">文件</a>', html)
        self.assertIn('class="nav-more"', html)
        self.assertRegex(html, r"<summary[^>]*>更多</summary>")
        self.assertIn('id="search-input"', html)
        self.assertIn('aria-label="搜尋 BrainHub"', html)
        self.assertIn("data-theme-toggle", html)
        self.assertIn("<svg", html)

    def test_setup_entries_sit_in_the_top_row_while_a_workspace_is_empty(self):
        """A fresh install still needs the tour where it can be seen."""
        nav = render_header_html(populated=False).split("<details")[0]

        self.assertIn('href="/onboard">上手引導</a>', nav)
        self.assertIn('href="/ingest">匯入</a>', nav)

    def test_setup_entries_are_demoted_once_the_workspace_has_content(self):
        """…and stop spending prime nav space once that job is done.

        Demoted, never deleted: an entry that vanishes is a bug report, an entry
        that moved is a menu. Asserting it is present in 更多 is what separates
        the two — without it this test would also pass if the links were dropped.
        """
        html = render_header_html(populated=True)
        top_row, more_menu = html.split("<details")[0], html.split("nav-more-menu")[1]

        self.assertNotIn('<a href="/onboard">上手引導</a>', top_row)
        self.assertNotIn('<a href="/ingest">匯入</a>', top_row)
        self.assertIn('<a href="/onboard">上手引導</a>', more_menu)
        self.assertIn('<a href="/ingest">匯入</a>', more_menu)

    def test_nav_and_home_page_read_the_same_setup_signal(self):
        """Two rules answering "is this workspace set up yet?" will disagree
        eventually, and the stale one is the one nobody looks at. serve.py must
        derive the nav's answer from web_home's threshold, not restate it.

        Scoped to the function body rather than searched across the whole file:
        the first version of this test looked for a literal within 200 chars of
        the function name, and the docstring alone is longer than that — so it
        passed against a deliberately hardcoded `>= 12`. A guard with a window
        too small to reach what it guards is indistinguishable from no guard.
        """
        source = (ROOT / "serve.py").read_text(encoding="utf-8")
        start = source.index("def _workspace_populated")
        body = source[start:].split("\ndef ", 1)[0]

        self.assertIn(
            "ONBOARDING_PAGE_THRESHOLD", body,
            msg="_workspace_populated must read web_home's threshold",
        )
        self.assertNotRegex(
            body, r">=\s*\d+",
            msg="the nav is comparing against its own literal instead of web_home's threshold",
        )

    def test_footer_carries_brand_without_outbound_link(self):
        html = render_footer_html()

        self.assertIn("BrainHub", html)
        self.assertNotIn("github", html.lower())

    def test_layout_escapes_title_and_page_class(self):
        html = render_layout('<Title>', "<main>Body</main>", page_class='graph" onclick="bad')

        self.assertIn("<title>&lt;Title&gt; — BrainHub</title>", html)
        self.assertIn('class="graph&quot; onclick=&quot;bad"', html)
        self.assertIn("<main>Body</main>", html)
        self.assertIn("document.activeElement.id === 'search-input'", html)
        self.assertIn("window.location.href = '/search?q=' + encodeURIComponent(q);", html)
        self.assertIn("active.setAttribute('aria-current', 'page');", html)
        self.assertIn("current.indexOf('/page/') === 0", html)
        self.assertIn("localStorage.getItem('brainhub-theme')", html)
        self.assertIn("navigator.clipboard.writeText", html)
        self.assertIn("/api/raw-source", html)
        self.assertIn('lang="zh-Hant-TW"', html)
        self.assertIn("--brand-dawn-gold", html)

    def test_stat_grid_escapes_values_and_labels(self):
        html = render_stat_grid([("<2>", "raw <files>")])

        self.assertIn("home-stats", html)
        self.assertIn("&lt;2&gt;", html)
        self.assertIn("raw &lt;files&gt;", html)
        self.assertNotIn("<2>", html)


if __name__ == "__main__":
    unittest.main()
