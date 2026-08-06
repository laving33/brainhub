# BrainHub

**A local, self-hosted knowledge workspace for AI agent teams.**
Wiki + durable agent memory + rich artifacts (charts, mermaid, interactive HTML,
PDF export) — all plain files on your own machine, every step auditable, zero
external services.

- **Zero dependencies.** The engine, CLI, and web viewer run on Python 3.10+
  standard library alone. No database server, no vector store, no cloud.
  ⚠ One exception, and it is only visible to your reader: embedding a **CJK**
  face into `--profile a4` output needs `fontTools` (`pip install fonttools`).
  Without it the document renders and looks correct on your machine — which has
  system CJK fonts — while the copy you send falls back to whatever the
  recipient happens to have. Rendering CJK without it prints a warning to
  stderr; do not ignore it for anything client-facing.
- **One workspace = one directory.** Wiki pages are Markdown; artifacts are
  self-contained HTML files; provenance rides in sidecar JSON. `tar` it, `grep`
  it, back it up like any folder.
- **Built for agents.** Ships with an MCP server (stdio) and five Claude-Code
  agent skills so your AI workers can publish, retrieve, link, and self-check
  memory without custom glue.

## Requirements

- Python 3.10+ (standard library only)
- Optional: Chrome/Chromium wrapper for server-side PDF export
  (`BRAINHUB_CHROME_PDF`, see White-label & configuration)
- Optional: `pip install ./mcp_package` for the stdio MCP server
  (only dependency: `mcp>=1.0.0`)

## Install

```bash
tar xzf brainhub-<version>.tar.gz
cd brainhub

# Optional short alias (recommended — docs use `bh` throughout):
install -d ~/.local/bin
printf '#!/bin/bash\nexec python3 %s/brainhub.py "$@"\n' "$PWD" > ~/.local/bin/bh
chmod +x ~/.local/bin/bh
```

## Quickstart

```bash
# 1. Create a workspace (any directory; one Unix account owns one workspace)
bh init ~/team-brain

# 2. Publish a document (its slug becomes the stable handle)
bh publish "deploy runbook" --body "## Steps ..." ~/team-brain

# 3. Read it back / search
bh read deploy-runbook ~/team-brain
bh search "deploy" ~/team-brain

# 4. Link pages into a knowledge graph
bh link deploy-runbook other-page ~/team-brain

# 5. Serve the read-mostly web viewer (LAN deployment is the intended model)
python3 serve.py --host 127.0.0.1 --port 3000 --root ~/team-brain
```

Every verb also accepts the workspace via the `BRAINHUB_HOME` environment
variable instead of a trailing path argument — **prefer the env form when the
verb takes option flags** (argparse cannot place a trailing positional after
flags: `bh publish t --body b <workspace>` fails; `BRAINHUB_HOME=<workspace>
bh publish t --body b` works).

Engine verbs beyond the core set (`health`, `doctor --fix`, `validate`,
`query`, `backup`, `ingest-status`, …) are forwarded automatically:
`bh health ~/team-brain` just works. `bh --help` lists the core verbs;
`python3 brainhub_engine.py` shows the full engine verb list.

## Artifacts (charts, diagrams, interactive HTML, PDF)

```bash
# Render a spec into ONE self-contained HTML file (9 chart types, mermaid,
# interactive HTML) — zero external requests, safe to email:
bh build spec.json ~/team-brain --renderer line-chart --task "weekly report"

# Render a Markdown file into a brand-styled, print-ready HTML document:
bh render report.md out.html

# Export a stored artifact for a human, stripping internal provenance:
bh export artifacts/html/report.html ~/team-brain --target ./deliverable.html
```

The viewer's "download PDF" button uses a server-side Chrome wrapper when
`BRAINHUB_CHROME_PDF` is configured; without it, everything except PDF export
works normally.

## Hooking up AI agents

**MCP (any MCP-capable agent):**

```bash
pip install ./mcp_package
# register in your agent's MCP config, e.g.:
#   command: brainhub-mcp
#   env:     BRAINHUB_WIKI=/home/you/team-brain/wiki
```

**Claude Code skills:** copy or symlink the directories under `skills/` into
`~/.claude/skills/`. They teach agents when and how to retrieve context
(`brainhub-retrieve`), persist decisions (`brainhub-memory`), ingest raw files
(`brainhub-ingest`), self-check the workspace (`brainhub-health`), and manage
artifacts (`brainhub-runtime`).

## White-label & configuration

Everything brand-specific is replaceable at deploy time; nothing requires a
code change:

| What | How |
|---|---|
| Logo in rendered documents/PDFs | Replace `mcp_package/brainhub_core/vendor/brand-logo.svg`, or set `BRAINHUB_BRAND_LOGO=/path/to/logo.svg` |
| Logo in the web viewer | Drop `logo.svg` in the workspace root (served at `/logo.svg`) |
| Embedded fonts in client-facing renders | `BRAINHUB_BRAND_FONTS=/path/to/fonts-dir` (`.ttf`/`.woff2`; absent → graceful no-embed) |
| PDF export | `BRAINHUB_CHROME_PDF=/path/to/chrome-wrapper` |
| Default workspace | `BRAINHUB_HOME=/path/to/workspace` |

## Deployment model

BrainHub is designed for a **trusted private LAN**. The viewer binds
`127.0.0.1` by default; bind a LAN address explicitly when the team should
reach it. Write endpoints assume every caller on the network is trusted — do
not expose the port to the public internet.

## Maintainer notes

```bash
python3 -m pytest tests/            # 946 tests, stdlib + pytest only
```

- `brainhub.py` — product CLI (publish/read/search/link/build/render/export);
  forwards unknown verbs to the engine.
- `brainhub_engine.py` — storage, search (FTS + CJK bigram), validation,
  backup, memory layer.
- `serve.py` — the web viewer (wiki, artifacts, graph, PDF endpoint).
- `mcp_package/brainhub_core/` — shared core; `mcp_package/brainhub_mcp/` —
  stdio MCP server.
- `BRAINHUB-SCHEMA.md` — the workspace schema contract (copied into each
  workspace at `init`).
- Wiki files must only be modified through the CLI/MCP — the engine maintains
  indexes and backlinks; hand-editing corrupts them (`bh doctor --fix` repairs).
- `tests/test_brainhub_branding.py` documents the project's provenance policy:
  this codebase is a hard fork of an MIT-licensed project; `LICENSE` retains
  the required upstream copyright notice and is the only place it lives.

## License

MIT — see `LICENSE`.
