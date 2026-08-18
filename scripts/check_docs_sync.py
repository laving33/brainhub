#!/usr/bin/env python3
"""Fail when prose disagrees with the code it describes.

The renderer registry and :data:`VERIFIED_DIAGRAM_TYPES` are executable facts.
The same two lists are also written out in the README, the packaging README, the
``bh_build`` MCP docstring, and the runtime skill — five hand-maintained copies
whose only previous guarantee was that somebody would remember. They did not:
``bh_build`` shipped a docstring naming 4 of 13 renderers, and a later edit to
the same docstring restated the mermaid list with 19 of 22 types.

Nothing here reformats or generates prose. It asserts that each surface *names*
every fact, so a copy can stay differently worded — a selection table is allowed
to be a table, an intro sentence a sentence — while going red the moment one
falls behind. A renderer or diagram type that a surface deliberately omits is
declared below with the reason, and that declaration is itself checked: drop the
kind from the registry and the stale exemption fails.

Usage:
    python3 scripts/check_docs_sync.py

Exit code 0 when every surface is current, 1 otherwise. Importable:
``check() -> list[str]``.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core import render  # noqa: E402  (path set above)
from brainhub_core.render.renderers.mermaid import (  # noqa: E402
    VERIFIED_DIAGRAM_TYPES,
)

# Surfaces that must name every registered renderer kind.
RENDERER_SURFACES = (
    Path("README.md"),
    Path("mcp_package/README.md"),
    Path("skills/46m-bh-runtime/SKILL.md"),
)

# Surfaces that must name every verified mermaid diagram type.
DIAGRAM_SURFACES = (
    Path("README.md"),
    Path("skills/46m-bh-runtime/SKILL.md"),
)

# kind -> why this surface may omit it. Checked for staleness: an entry naming a
# kind the registry no longer has is itself a finding.
RENDERER_OMISSIONS: dict[Path, dict[str, str]] = {}


def _read(path: Path) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _tool_docstring(name: str) -> str | None:
    """Return an MCP tool function's docstring, read statically from source."""
    tree = ast.parse(_read(Path("mcp_package/brainhub_mcp/server.py")))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_docstring(node)
    return None


def _names(text: str, term: str) -> bool:
    """True when ``term`` appears as a whole token, backticked or bare."""
    return re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text) is not None


def check() -> list[str]:
    findings: list[str] = []
    kinds = sorted(render.registry.kinds())

    for surface, omissions in RENDERER_OMISSIONS.items():
        for kind in omissions:
            if kind not in kinds:
                findings.append(
                    f"{surface}: exemption for renderer {kind!r} is stale — "
                    "no such kind is registered"
                )

    for surface in RENDERER_SURFACES:
        text = _read(surface)
        exempt = RENDERER_OMISSIONS.get(surface, {})
        for kind in kinds:
            if kind in exempt or _names(text, kind):
                continue
            findings.append(f"{surface} never names renderer {kind!r}")

    for surface in DIAGRAM_SURFACES:
        text = _read(surface)
        for diagram in VERIFIED_DIAGRAM_TYPES:
            if not _names(text, diagram):
                findings.append(
                    f"{surface} never names verified mermaid type {diagram!r}"
                )

    # Agents read the bh_build docstring as the tool's contract, so a stale one
    # misroutes work that never reaches a human. Read via ast rather than import:
    # importing the server parses argv and exits when no wiki is configured, which
    # a docs check must not depend on.
    doc = _tool_docstring("bh_build")
    if doc is None:
        findings.append("bh_build not found in mcp_package/brainhub_mcp/server.py")
    else:
        for kind in kinds:
            if not _names(doc, kind):
                findings.append(f"bh_build docstring never names renderer {kind!r}")

    # A count claimed in prose is the one thing that cannot self-correct.
    for surface in RENDERER_SURFACES:
        text = _read(surface)
        for claimed in re.findall(r"(\d+)\s+renderers", text):
            if int(claimed) != len(kinds):
                findings.append(
                    f"{surface} claims {claimed} renderers; the registry has {len(kinds)}"
                )
        for claimed in re.findall(r"(\d+)\s+(?:verified\s+)?offline[- ]verified", text):
            if int(claimed) != len(VERIFIED_DIAGRAM_TYPES):
                findings.append(
                    f"{surface} claims {claimed} diagram types; "
                    f"the renderer verifies {len(VERIFIED_DIAGRAM_TYPES)}"
                )
    return findings


def main() -> int:
    findings = check()
    if findings:
        print("FAIL docs sync")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print(
        f"OK docs sync: {len(render.registry.kinds())} renderers and "
        f"{len(VERIFIED_DIAGRAM_TYPES)} mermaid types named on every surface"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
