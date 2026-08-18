#!/usr/bin/env python3
"""Verify a built artifact is self-contained and carries no executable surface.

This is the STATIC mirror of the runtime guarantee. Two things already protect
an artifact — ``render.document.ARTIFACT_CONTENT_SECURITY_POLICY`` and the
per-renderer "no external requests" unit tests — and neither covers what this
does:

* A CSP is enforced by the *reader's* browser. When it blocks something the
  page renders wrong silently; nobody who built the file finds out. This runs
  where the file is produced and names the offending tag and line.
* A `<meta>` CSP travels inside the document, so anything that rewrites the
  head (an email client, a CMS, a "sanitizer") can drop it and take the whole
  guarantee with it. What the file *contains* is the durable property.
* The per-renderer tests each assert a handful of substrings on their own
  output. Nothing runs over every kind, and a renderer added later inherits no
  coverage at all.

Deliberately parsed, never grepped. A vendored bundle's own source text is full
of strings like ``src="data:text/html;...``; the HTML tokenizer treats
``<script>``/``<style>`` bodies as CDATA, so a parser sees them as text while a
regex over the raw file reports a fleet of false positives.

Usage:
    python3 scripts/verify_artifact.py FILE [FILE ...]

Exit code 0 when every file is clean, 1 when any finding is reported, 2 on a
usage error. Importable: ``verify(path) -> list[str]``.
"""
from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

# Attributes whose value is fetched or navigated to.
REFERENCE_ATTRS = frozenset(
    {
        "src",
        "href",
        "xlink:href",
        "poster",
        "srcset",
        "action",
        "formaction",
        "data",
        "background",
        "manifest",
    }
)

# Tags that embed or redirect to another document. None of them can appear in a
# self-contained artifact, and <base> silently re-points every relative URL.
FORBIDDEN_TAGS = frozenset({"base", "embed", "object", "iframe", "frame", "frameset"})

# data: payloads an artifact may legitimately carry. Everything else — most of
# all data:text/html, which is a document with its own origin — is refused.
SAFE_DATA_PREFIXES = ("data:image/", "data:font/", "data:application/font")

CSS_IMPORT_RE = re.compile(r"@import\b", re.IGNORECASE)
CSS_URL_RE = re.compile(r"url\(\s*(?P<q>['\"]?)(?P<value>.*?)(?P=q)\s*\)", re.DOTALL)


def _compact(value: str) -> str:
    """Casefolded value with C0/space characters removed.

    ``jav&#9;ascript:x`` reaches the parser as a real TAB inside the value; the
    HTML spec has the navigation code strip those before matching the scheme,
    so a check that does not strip them first is trivially bypassed.
    """
    return "".join(ch for ch in value if ord(ch) > 32).casefold()


def _reference_error(tag: str, attr: str, raw: str) -> str | None:
    """Return a finding for one reference value, or None when it is allowed."""
    value = raw.strip()
    if not value or value.startswith("#"):
        return None  # empty, or a same-document fragment
    compact = _compact(value)
    if compact.startswith(("javascript:", "vbscript:", "data:text/html")):
        return f"executable URL in {attr} on <{tag}>: {value[:80]}"
    if compact.startswith(("http://", "https://", "//")):
        return f"remote reference in {attr} on <{tag}>: {value[:80]}"
    if compact.startswith("data:"):
        # "data:," is the document layer's no-op favicon: it exists so browsers
        # stop probing /favicon.ico, and carries no payload at all.
        if compact == "data:," or compact.startswith(SAFE_DATA_PREFIXES):
            return None
        return f"non-image data URL in {attr} on <{tag}>: {value[:80]}"
    scheme = value.split("/", 1)[0]
    if ":" in scheme:
        return f"remote reference in {attr} on <{tag}>: {value[:80]}"
    return f"relative reference in {attr} on <{tag}>: {value[:80]}"


class _ArtifactParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.findings: list[str] = []
        self.styles: list[str] = []
        self.element_count = 0
        self._open_scripts = 0
        self._cdata_tag: str | None = None

    def _add(self, message: str) -> None:
        line, _ = self.getpos()
        self.findings.append(f"line {line}: {message}")

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        self.element_count += 1
        if tag in ("script", "style"):
            self._cdata_tag = tag
        if tag == "script":
            self._open_scripts += 1
        if tag in FORBIDDEN_TAGS:
            self._add(f"forbidden tag <{tag}>")
        for name, value in attrs:
            key = name.casefold()
            value = value or ""
            if key.startswith("on"):
                self._add(f"executable attribute {name} on <{tag}>")
                continue
            if key == "srcdoc":
                self._add(f"srcdoc on <{tag}> embeds a nested document")
                continue
            if key not in REFERENCE_ATTRS:
                continue
            # srcset is a comma-separated candidate list: "a.png 1x, b.png 2x".
            # Checking it whole would clear a list whose second candidate is
            # remote.
            candidates = (
                [part.strip().split()[0] for part in value.split(",") if part.strip()]
                if key == "srcset"
                else [value]
            )
            for candidate in candidates:
                error = _reference_error(tag, key, candidate)
                if error:
                    self._add(error)

    def handle_startendtag(self, tag: str, attrs) -> None:  # noqa: ANN001
        # Self-closing tags never enter CDATA mode; route attributes only.
        cdata, opened = self._cdata_tag, self._open_scripts
        self.handle_starttag(tag, attrs)
        self._cdata_tag, self._open_scripts = cdata, opened

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._open_scripts -= 1
        if tag == self._cdata_tag:
            self._cdata_tag = None

    def handle_data(self, data: str) -> None:
        if self._cdata_tag == "style":
            self.styles.append(data)


def _check_css(source: str) -> list[str]:
    findings = []
    if CSS_IMPORT_RE.search(source):
        findings.append("@import in inline CSS pulls in another stylesheet")
    for match in CSS_URL_RE.finditer(source):
        value = match.group("value").strip()
        if not value or value.startswith("#"):
            continue
        compact = _compact(value)
        if compact == "data:," or compact.startswith(SAFE_DATA_PREFIXES):
            continue
        findings.append(f"CSS url() must be a fragment or embedded asset: {value[:80]}")
    return findings


def verify(path: Path) -> list[str]:
    """Return a list of findings for one artifact. Empty means clean."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"unreadable: {exc}"]

    parser = _ArtifactParser()
    parser.feed(source)
    parser.close()
    findings = list(parser.findings)

    for style in parser.styles:
        findings.extend(_check_css(style))

    if parser._open_scripts > 0:
        # An unclosed <script> swallows the rest of the document as script text,
        # so every check after it silently stops seeing markup.
        findings.append("unclosed <script>: the rest of the document is script text")

    # Meta-assert. Every finding above is evidence of something present; none of
    # them fires when the parser saw nothing, so a file that stops parsing early
    # would otherwise be reported as clean.
    if parser.element_count < 5:
        findings.append(
            f"only {parser.element_count} elements parsed — not an HTML document, "
            "or parsing stopped early"
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+", type=Path, metavar="FILE")
    args = ap.parse_args(argv)

    failed = False
    for path in args.paths:
        findings = verify(path)
        if findings:
            failed = True
            print(f"FAIL {path}")
            for finding in findings:
                print(f"  - {finding}")
        else:
            print(f"OK   {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
