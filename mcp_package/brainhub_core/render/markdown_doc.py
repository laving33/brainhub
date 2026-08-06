"""markdown -> ONE self-contained, brand-styled HTML file.

This capability already lived in the library (``markdown.markdown_to_html`` +
``document.wrap_document``) but had **no CLI verb**, so everyone who needed
"a markdown file rendered into something you can send someone" wrote their own
caller. We ended up with FOUR: three copies of ``build_doc.py`` (already drifted
apart — 94 / 81 / 84 lines, and a page-break fix landed in only one of them) and
a whole ``htmlify`` skill with its own hand-copied brand palette.

The capability was never missing. The **verb** was. Missing verbs are how you get
copies, and copies are how things drift.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..markdown import markdown_to_html
from .document import wrap_document
from .fonts import embedded_font_css


# Generic print profile. Anything document-specific (quote/contract chrome,
# signature blocks, numeric columns) belongs in a --css file owned by whoever
# owns that document type, NOT here.
A4_CSS = """
@page { size: A4; margin: 18mm 16mm 20mm; }
@media print {
  html, body { background: #fff; }
  .bh-header, .bh-export { display: none !important; }
}
h1, h2, h3 { break-after: avoid-page; page-break-after: avoid; }
p, li, blockquote { orphans: 3; widows: 3; }
table, figure, pre { break-inside: avoid; page-break-inside: avoid; }
/* Attachments start a new page. The CSS for this shipped long ago in the
   sales-kit; what was missing was anything that PUT the class on an element,
   so it silently never paginated and signature blocks shared a page with
   Attachment A. `render` attaches it below — the rule and its trigger now live
   together. */
.attach { break-before: page; page-break-before: always; }
"""

# ⚠ NO `\b` HERE. A word boundary is an ASCII-shaped idea: between 件 and 一 both
# characters are word chars, so `附件\b` never matches 附件一 — the single most
# common way a Chinese document titles an attachment. The English form
# ("Attachment A") matched fine, so the test passed and the feature was dead for
# exactly the documents we actually produce. (Same ASCII-centric assumption that
# erased Chinese from search; it came back in a two-character regex.)
_ATTACH_H1 = re.compile(r"<h1([^>]*)>(\s*(?:Attachment|Appendix|附件|附錄))")


def render_markdown_document(
    markdown_text: str,
    *,
    title: str = "",
    profile: str = "screen",
    extra_css: str = "",
    body_class: str = "",
    static: bool = False,
    white_label: bool = False,
) -> str:
    """Render markdown into one self-contained HTML document.

    ``profile='a4'`` adds print geometry and page-break discipline. The output is
    a single file with zero external requests (see ``wrap_document``): safe to
    email, safe to open offline, and it carries the aworkr brand automatically —
    which is the whole reason not to hand-copy a palette into a template again.
    """
    lines = markdown_text.split("\n")
    # A leading `# Title` becomes the document title rather than a body heading,
    # so the header does not print twice.
    if not title and lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]

    body = markdown_to_html("\n".join(lines), page_href=lambda name: "#")
    body = body.replace("&lt;br&gt;", "<br>")
    body = _ATTACH_H1.sub(r'<h1\1 class="attach">\2', body)

    # THE DOM CONTRACT for --css. The body is always wrapped in `.bh-doc`, and
    # `--body-class` adds your own hook next to it. Without a documented, stable
    # selector, a caller's stylesheet is accepted, raises nothing, and silently
    # does nothing — a tenant agent fed 22 rules scoped to `.q` and every one of them
    # was dead code. Accepted != in effect.
    wrapper = f"bh-doc {body_class}".strip()

    head = ""
    if profile == "a4":
        head += f"<style>{A4_CSS}</style>"
        # Fonts ride along by default for print/client-facing output. A font-family
        # declaration is only a REQUEST: on the author's machine it is granted and
        # the page looks right forever; on the recipient's it silently falls back to
        # a system face. You cannot see this bug on your own screen — only the
        # client can. So it is not a style concern and cannot be deferred to --css.
        head += embedded_font_css(body)
    if extra_css:
        head += f"<style>{extra_css}</style>"

    # Precedence is a contract too: base stylesheet -> profile -> caller's --css,
    # LAST wins. The caller must be able to override the profile's @page geometry;
    # if they cannot, they cannot control their own page breaks and have no way to
    # fix it. (Note there are THREE @page blocks in a4 output — the base sheet sets
    # one, the profile overrides it, the caller overrides that. Only the last one
    # matters, and a test pins that order.)
    return wrap_document(
        title or "Document",
        f'<div class="{wrapper}">{body}</div>',
        head_extra=head,
        static=static or profile == "a4",
        white_label=white_label,
    )


_NOT_CSS = re.compile(r'^\s*(?:"""|import |from |def |#!/)', re.M)


def read_stylesheet(path: Path) -> str:
    """Read a --css file, refusing things that are plainly not stylesheets.

    Unvalidated, `--css some_module.py` is accepted in silence and the module's
    Python docstring is typeset onto page 1 of a document you are about to send a
    client. (a tenant deployment did exactly this.) Garbage that reaches the client is not
    an acceptable failure mode for a missing check this cheap.
    """
    if path.suffix.lower() != ".css":
        raise ValueError(f"--css expects a .css file, got: {path}")
    text = path.read_text(encoding="utf-8")
    if _NOT_CSS.search(text):
        raise ValueError(f"--css file does not look like CSS (source code?): {path}")
    return text


def render_markdown_file(
    source: Path,
    *,
    title: str = "",
    profile: str = "screen",
    css_files: list[Path] | None = None,
    body_class: str = "",
    static: bool = False,
    white_label: bool = False,
) -> str:
    extra_css = "\n".join(read_stylesheet(path) for path in (css_files or []))
    return render_markdown_document(
        source.read_text(encoding="utf-8"),
        title=title,
        white_label=white_label,
        profile=profile,
        extra_css=extra_css,
        body_class=body_class,
        static=static,
    )
