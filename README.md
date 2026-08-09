# BrainHub

**A local, self-hosted knowledge workspace for AI agent teams.**
Wiki + durable agent memory + rich artifacts (charts, mermaid, interactive HTML,
PDF export) — all plain files on your own machine, every step auditable, zero
external services.

- **Zero dependencies.** The engine, CLI, and web viewer run on Python 3.10+
  standard library alone. No database server, no vector store, no cloud.
- **Chinese output is correct on the recipient's machine, not just yours.** A
  Noto Sans CJK TC subset ships in the package — Big5 plus 99.8% of CJK Ext-A —
  and is embedded into every document that contains CJK, subset to the characters
  that document uses. This is not a typography nicety: a document that falls back
  to the reader's fonts loses CJK bold silently *and* can record a different
  codepoint in the PDF text layer, so the page looks perfect while the client
  cannot search it. You can never see either failure on your own screen — your
  machine has system CJK fonts. If a character falls outside the shipped
  coverage, it is named on stderr rather than dropped quietly.
- **One workspace = one directory.** Wiki pages are Markdown; artifacts are
  self-contained HTML files; provenance rides in sidecar JSON. `tar` it, `grep`
  it, back it up like any folder.
- **Built for agents.** Ships with an MCP server (stdio) and five Claude-Code
  agent skills so your AI workers can publish, retrieve, link, and self-check
  memory without custom glue.

## Requirements

- Python 3.10+ (standard library only)
- Optional: Chrome/Chromium for server-side PDF export — found on PATH
  automatically; override with `BRAINHUB_CHROME_PDF` (see White-label &
  configuration)
- Optional: `pip install ./mcp_package` for the stdio MCP server. It pulls
  `mcp`, the Markdown stack, and `fonttools`/`brotli` — the last two subset the
  shipped CJK face per document, and are hard dependencies rather than an extra
  because "Chinese PDFs whose text layer cannot be searched" is not a degraded
  mode anyone should be able to install into by omission.

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

The viewer's "download PDF" button drives a Chromium-family browser found on
PATH. Point `BRAINHUB_CHROME_PDF` at a wrapper script taking
`(src.html, out.pdf, timeout_ms)` to use house print settings instead. With
neither available the button reports which of the two to fix; everything except
PDF export works normally.

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
(`46m-bh-retrieve`), persist decisions (`46m-bh-memory`), ingest raw files
(`46m-bh-ingest`), self-check the workspace (`46m-bh-health`), and manage
artifacts (`46m-bh-runtime`).

## White-label & configuration

Everything brand-specific is replaceable at deploy time; nothing requires a
code change:

BrainHub ships **with** a brand theme rather than unbranded. To put your own
corporate identity on it, point one variable at a directory — colours, logo and
fonts swap together:

```bash
export BRAINHUB_BRAND_DIR=~/my-brand
#   my-brand/tokens.css    colour/spacing tokens — the usual swap point
#   my-brand/logo.svg      header + document lockup
#   my-brand/fonts/        .woff2 / .ttf faces to embed
#   my-brand/daisyui.css   optional; only if you rebuilt the component sheet
```

A pack only has to provide what it wants to change: anything absent falls back to
the per-asset variable below, then to the bundled theme, then to nothing at all —
a missing asset never raises. daisyUI's themes map onto the same token names, so
replacing `tokens.css` alone recolours the components too, and all 13 chart
renderers with them.

Chart **series** colours are a separate decision. `--series-1`..`--series-8` ship
as a colourblind-validated palette that deliberately contains no status colours, so
series 2 never reads as "good" and series 3 never as "warning". A pack's
`tokens.css` is applied after the built-in one and so *can* redefine them — do that
only if the replacements are checked for distinguishability, because a brand
palette that looks handsome in a logo often collapses into two shades of the same
hue in a stacked bar.

| What | How |
|---|---|
| Whole corporate identity at once | `BRAINHUB_BRAND_DIR=/path/to/brand-pack` |
| Logo in rendered documents/PDFs | Replace `mcp_package/brainhub_core/vendor/brand-logo.svg`, or set `BRAINHUB_BRAND_LOGO=/path/to/logo.svg` |
| Logo in the web viewer | Drop `logo.svg` in the workspace root (served at `/logo.svg`) |
| Embedded Latin fonts in client-facing renders | `BRAINHUB_BRAND_FONTS=/path/to/fonts-dir` (`.ttf`/`.woff2`; absent → graceful no-embed) |
| CJK fonts | Nothing to configure. A Noto Sans CJK TC subset ships in `vendor/` (Big5 + 99.8% of Ext-A) and is embedded automatically, subset to each document. A character outside that coverage is reported on stderr, never dropped silently. |
| PDF export | Nothing to configure if a Chromium-family browser is installed; it is found on PATH. Override with `BRAINHUB_CHROME_PDF=/path/to/chrome-wrapper` taking `(src.html, out.pdf, timeout_ms)`. |
| Default workspace | `BRAINHUB_HOME=/path/to/workspace` |

## Deployment model

BrainHub is designed for a **trusted private LAN**. The viewer binds
`127.0.0.1` by default; bind a LAN address explicitly when the team should
reach it. Write endpoints assume every caller on the network is trusted — do
not expose the port to the public internet.

### Sizing the viewer for a team

The viewer serves concurrent readers from a bounded worker pool. The defaults are
sized for a few dozen simultaneous readers and need no tuning; raise them for a
larger deployment. Anything unparseable falls back to the default rather than
refusing to start.

| Variable | Default | What it bounds |
|---|---|---|
| `BRAINHUB_ACCEPT_BACKLOG` | 512 | Queue depth for connections waiting to be accepted |
| `BRAINHUB_MAX_WORKERS` | 128 | Concurrent connections served at once |
| `BRAINHUB_REQUEST_TIMEOUT` | 15 | Seconds a single request may take |
| `BRAINHUB_KEEPALIVE_IDLE_TIMEOUT` | 5 | Seconds an idle keep-alive connection holds a worker |
| `BRAINHUB_MUTATION_RATE_LIMIT` | 180 | Writes allowed per client IP per window |
| `BRAINHUB_MUTATION_RATE_WINDOW` | 60 | Seconds in that window |

Behind a reverse proxy every reader arrives as the proxy's single address, so they
share one write budget — raise `BRAINHUB_MUTATION_RATE_LIMIT` for shared access.

Verify capacity on your own hardware rather than trusting the defaults:

```bash
python3 scripts/loadtest_http_viewer.py --users 30
```

## Maintainer notes

```bash
python3 -m unittest discover -s tests   # 1085 tests, stdlib only (pytest works too)
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
