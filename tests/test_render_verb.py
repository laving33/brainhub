"""Contract tests for `brainhub render` — markdown -> ONE self-contained HTML file.

This verb exists because the capability (markdown_to_html + wrap_document) was in
the library but had NO CLI verb, so four separate callers grew: three drifted
copies of build_doc.py and an htmlify skill with a hand-copied brand palette.
A missing verb is how you get copies.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_package"))

import brainhub  # noqa: E402


class RenderVerbTests(unittest.TestCase):
    def render(self, markdown: str, *args: str) -> str:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = Path(tmp.name) / "doc.md"
        src.write_text(markdown, encoding="utf-8")
        out = Path(tmp.name) / "doc.html"
        code = brainhub.main(["render", str(src), "--out", str(out), *args])
        self.assertEqual(code, 0)
        return out.read_text(encoding="utf-8")

    def test_output_is_one_self_contained_file(self):
        html = self.render("# 報價單\n\n款到後起算。\n")
        self.assertNotIn("<script src=", html)
        self.assertEqual(re.findall(r'(?:src|href)="(https?://[^"]+)"', html), [])
        self.assertIn("款到後起算", html)

    def test_white_label_omits_the_wordmark_logo(self):
        """2026-07-18 tam 回報：`bh render` 把 aworkr 字標當**內嵌 SVG**注進 header。
        白牌件（交給終端客戶、要隱藏分包）保留它＝當著客戶揭露分包，而且**看不見**：
        SVG 是圖不是字 ⇒ 正文掃描/PDF metadata/scan-doc 三道全瞎（一隻 AM 靠先問白牌
        判準、再肉眼看 HTML 才抓到）。⇒ `--white-label` 必須**結構性不注入**那張圖。

        這條尺為什麼是「看 SVG/元素」不是「看 class 字串」：BRAND_CSS 永遠帶著
        `.brainhub-logo{}` 選擇器（無害的死 CSS），只 grep class 名會把它算進去 ⇒
        誤以為沒拆乾淨。真正的洩漏是**那張圖**，所以驗 `<svg>` 與 `<span class=...>` 元素。"""
        normal = self.render("# 客戶報告\n\n內容。\n")
        wl = self.render("# 客戶報告\n\n內容。\n", "--white-label")
        # 陽性對照：正常渲染，圖層洩漏面（logo <span> + SVG）本來就在——證明尺量得到它
        self.assertIn('<span class="brainhub-logo"', normal)
        self.assertIn("<svg", normal)
        # 白牌：那張圖必須整個不見（元素層，不是只拆 class 字串）
        self.assertNotIn('<span class="brainhub-logo"', wl)
        self.assertNotIn("<svg", wl)
        # 陰性對照：白牌不得把正文一起吃掉（把 header 連內容全拆＝另一種壞）
        self.assertIn("內容", wl)

    def test_render_needs_no_workspace(self):
        """A tenant renders inside drafts/, where there is no brain. Demanding a
        workspace would make the verb useless exactly where it is needed."""
        html = self.render("# T\n\nbody\n")
        self.assertIn("body", html)

    def test_attachments_start_a_new_page_under_a4(self):
        """The `.attach { break-before: page }` CSS shipped long ago, but NOTHING
        ever put the class on an element — so the signature block silently shared
        a page with Attachment A. The rule and its trigger now ship together.

        ⚠ The Chinese forms are the point. The first version of this test only
        checked "Attachment A" and passed, while `附件一` — the way a Chinese
        document actually titles an attachment — did not match, because the regex
        used `\b`, and a word boundary does not exist between 件 and 一. The test
        was green and the feature was dead for every document we really produce.
        """
        for heading in ("Attachment A", "Appendix B", "附件一", "附錄一", "附件 A"):
            with self.subTest(heading=heading):
                html = self.render(f"# 合約\n\n簽署\n\n# {heading}\n\n明細\n", "--profile", "a4")
                self.assertIn('class="attach"', html)
        self.assertIn("@page", self.render("# T\n\nx\n", "--profile", "a4"))

    def test_attachment_pagination_holds_in_a_real_pdf(self):
        """class="attach" is only a PROXY for the thing we care about. The thing we
        care about is that the attachment lands on its own sheet of paper, so this
        one renders a PDF and counts pages."""
        chrome_pdf = Path("/home/aworkr/aworkr/tools/chrome/chrome-pdf")
        if not chrome_pdf.is_file():
            self.skipTest("chrome-pdf not available")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = Path(tmp.name) / "doc.md"
        src.write_text("# 委刊合約\n\n## 簽署\n\n甲方：＿＿＿\n\n# 附件一\n\n明細\n", encoding="utf-8")
        html, pdf = Path(tmp.name) / "doc.html", Path(tmp.name) / "doc.pdf"
        self.assertEqual(brainhub.main(["render", str(src), "--out", str(html), "--profile", "a4"]), 0)
        subprocess.run([str(chrome_pdf), str(html), str(pdf)], check=True,
                       capture_output=True, timeout=120)
        pages = len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))
        self.assertGreaterEqual(pages, 2, "附件一 did not start a new page in the real PDF")

    def test_ordinary_headings_are_not_page_broken(self):
        html = self.render("# 合約\n\n# 付款條件\n\n款到\n", "--profile", "a4")
        self.assertNotIn('class="attach"', html)

    def test_a4_embeds_the_brand_fonts(self):
        """A font-family declaration is a REQUEST, not a guarantee. On the author's
        machine it is granted and the page looks right forever; on the recipient's
        it silently falls back to a system face. You cannot see this bug on your own
        screen — only the client can. So print output carries the bytes."""
        from brainhub_core.render.fonts import BRAND_FONTS
        if not BRAND_FONTS.is_dir():
            self.skipTest("brand fonts not present (standalone install)")
        html = self.render("# 合約\n\n款到後起算。\n", "--profile", "a4")
        self.assertIn("data:font/woff2;base64", html)
        self.assertGreaterEqual(html.count("@font-face"), 3)  # Inter x2 + Noto TC subset
        self.assertEqual(re.findall(r'(?:src|href)="(https?://[^"]+)"', html), [])

    def test_cjk_face_is_subset_not_shipped_whole(self):
        """A full Noto Sans TC is ~9MB. Subset to the document's own glyphs."""
        from brainhub_core.render.fonts import BRAND_FONTS
        if not BRAND_FONTS.is_dir():
            self.skipTest("brand fonts not present (standalone install)")
        html = self.render("# 合約\n\n款到後起算。\n", "--profile", "a4")
        # Precondition, not decoration: this assertion used to be the size check
        # alone, which passes most cleanly when the CJK face is missing entirely
        # — zero is comfortably under 2MB. A gate that goes green *because* the
        # thing it guards is absent vouches for the exact failure it exists to
        # catch (studio, 2026-07-22: shipped installs had no CJK face at all,
        # and this test stayed green through it).
        self.assertIn("Noto Sans TC", html, "no CJK face embedded — size check below would be vacuous")
        self.assertLess(len(html), 2_000_000, "CJK face looks unsubset")

    def test_screen_profile_stays_light(self):
        """Internal reading does not need the fonts inlined — only what gets sent out."""
        html = self.render("# 報告\n\n內容\n")
        self.assertNotIn("data:font/woff2;base64", html)

    def test_brand_comes_from_the_shared_stylesheet(self):
        """htmlify hand-copied the CIS palette into its own template — a third
        definition point. The renderer must inherit brand, never restate it."""
        html = self.render("# T\n\nbody\n")
        self.assertIn("FF8C42", html.upper())


class CssContractTests(unittest.TestCase):
    """--css is only usable if the caller knows what selector to hook and whose
    rules win. Without that contract a stylesheet is accepted, raises nothing, and
    silently does nothing — which is how a tenant agent shipped 22 dead rules."""

    def render(self, markdown: str, *args: str, css: str = "") -> str:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = Path(tmp.name) / "doc.md"
        src.write_text(markdown, encoding="utf-8")
        out = Path(tmp.name) / "doc.html"
        extra: list[str] = []
        if css:
            sheet = Path(tmp.name) / "doc.css"
            sheet.write_text(css, encoding="utf-8")
            extra = ["--css", str(sheet)]
        self.assertEqual(brainhub.main(["render", str(src), "--out", str(out), *extra, *args]), 0)
        return out.read_text(encoding="utf-8")

    def test_body_wrapper_is_a_stable_hook(self):
        html = self.render("# T\n\nbody\n", "--body-class", "q")
        self.assertIn('class="bh-doc q"', html)

    def test_caller_css_is_last_so_it_can_override_the_profile(self):
        """Precedence: base -> profile -> --css. If the profile's @page won, the
        caller could not control their own page geometry and the page breaks would
        wander in ways they cannot fix."""
        html = self.render("# T\n\nbody\n", "--profile", "a4", css="@page { margin: 7mm 9mm; }")
        pages = re.findall(r"@page[^{]*\{[^}]*\}", html)
        self.assertIn("7mm 9mm", pages[-1])

    def test_css_flag_refuses_a_file_that_is_not_css(self):
        """Unchecked, `--css some_module.py` typesets a Python docstring onto page 1
        of a document you are about to send a client. It happened."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = Path(tmp.name) / "doc.md"
        src.write_text("# T\n\nbody\n", encoding="utf-8")
        module = Path(tmp.name) / "print_css.py"
        module.write_text('"""Print styles."""\nPRINT_CSS = "@page {}"\n', encoding="utf-8")
        code = brainhub.main(["render", str(src), "--out", str(Path(tmp.name) / "o.html"),
                              "--css", str(module)])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()


class BrandPaletteHasOneSourceTests(unittest.TestCase):
    """The document shell must not carry its own copy of the palette.

    It used to: `render/document.py` held a hand-typed L1 block alongside the
    viewer's, so a brand change had to be applied twice and a drift between them
    surfaced only as two documents that no longer matched (2026-07-22).
    """

    def test_document_palette_comes_from_the_vendored_file(self):
        from brainhub_core.render.document import BRAND_CSS
        from brainhub_core.web_assets import BRAND_TOKENS_CSS
        self.assertTrue(
            BRAND_CSS.startswith(BRAND_TOKENS_CSS),
            "document shell no longer builds on the vendored tokens — is there a second copy?",
        )

    def test_document_mapping_layer_hardcodes_no_hex(self):
        import re
        from brainhub_core.render.document import BRAND_CSS
        from brainhub_core.web_assets import BRAND_TOKENS_CSS
        mapping = BRAND_CSS[len(BRAND_TOKENS_CSS):]
        # Comments are stripped first: prose about a colour is not a colour, and
        # a checker that cannot tell them apart fails on documentation (studio hit
        # this three separate times on 2026-07-22).
        mapping = re.sub(r"/\*.*?\*/", "", mapping, flags=re.DOTALL)
        self.assertEqual(re.findall(r"#[0-9A-Fa-f]{3,8}", mapping), [])

    def test_the_hex_checker_would_actually_catch_one(self):
        import re
        sample = re.sub(r"/\*.*?\*/", "", "/* about #FFD166 */ a { color: #ABCDEF; }", flags=re.DOTALL)
        self.assertEqual(re.findall(r"#[0-9A-Fa-f]{3,8}", sample), ["#ABCDEF"])
