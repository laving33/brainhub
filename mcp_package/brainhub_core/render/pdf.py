"""Resolve how to turn a self-contained HTML file into a PDF on this machine.

The viewer's "download PDF" button used to depend on one absolute path to an
in-house wrapper script. That path only exists on the machines that own it, so on
every other install the endpoint answered 404 and the button silently did nothing
useful — the feature shipped, it just was not present.

Two invocation shapes, because they are not interchangeable:

* a **wrapper script** taking ``(src.html, out.pdf, timeout_ms)`` — kept because
  deployments already point ``BRAINHUB_CHROME_PDF`` at one, and a wrapper can
  apply house print settings a bare browser call cannot.
* a **browser binary** driven directly with ``--headless --print-to-pdf``, found
  on PATH. This is what makes the button work on an install that configured
  nothing.

An explicit ``BRAINHUB_CHROME_PDF`` always wins, so discovery can never override a
deliberate choice.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

CHROME_PDF_ENV = "BRAINHUB_CHROME_PDF"

# Ordered by how likely the result is to render a page the way the reader would
# see it in a browser. Chromium-family only: --print-to-pdf is a Chrome flag, and
# Firefox has no equivalent headless print that honours @media print the same way.
CHROME_BINARIES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
    "microsoft-edge",
    "microsoft-edge-stable",
)

# Checked when nothing is on PATH — the usual macOS and Windows install locations,
# where the binary is normally not on PATH at all.
CHROME_FALLBACK_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
)


@dataclass(frozen=True)
class PdfRenderer:
    """How to invoke PDF rendering here, and where it came from."""

    executable: str
    kind: str  # "wrapper" (src, out, timeout_ms) or "chrome" (--print-to-pdf)
    source: str  # human-readable provenance for the error message

    def command(self, src: Path, out: Path, timeout_ms: int = 20000) -> list[str]:
        if self.kind == "wrapper":
            return [self.executable, str(src), str(out), str(timeout_ms)]
        return [
            self.executable,
            "--headless=new",
            "--disable-gpu",
            # Without this Chrome stamps its own header/footer over the artifact's
            # own @media print layout.
            "--no-pdf-header-footer",
            # A sandbox inside an already-confined service just fails to start.
            "--no-sandbox",
            f"--print-to-pdf={out}",
            src.as_uri(),
        ]


def find_pdf_renderer(environ: dict[str, str] | None = None) -> PdfRenderer | None:
    """The configured wrapper, else a browser on this machine, else None."""
    source = os.environ if environ is None else environ
    configured = (source.get(CHROME_PDF_ENV) or "").strip()
    if configured:
        path = Path(configured).expanduser()
        # Honour it even when missing: reporting "the thing you configured is not
        # there" is more useful than silently discovering something else.
        return PdfRenderer(str(path), "wrapper", f"{CHROME_PDF_ENV}={configured}")

    for name in CHROME_BINARIES:
        found = shutil.which(name)
        if found:
            return PdfRenderer(found, "chrome", f"{name} on PATH")

    for candidate in CHROME_FALLBACK_PATHS:
        if Path(candidate).is_file():
            return PdfRenderer(candidate, "chrome", "standard install location")

    return None


def pdf_unavailable_reason() -> str:
    """One actionable line for when no renderer could be found."""
    return (
        "PDF export needs a Chromium-family browser. Install Chrome/Chromium, or "
        f"point {CHROME_PDF_ENV} at a script taking (src.html, out.pdf, timeout_ms)."
    )
