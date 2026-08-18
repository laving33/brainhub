# BrainHub

**A local, self-hosted knowledge workspace for AI agent teams.**
Wiki + durable agent memory + rich artifacts (charts, mermaid, interactive HTML,
PDF export) — all plain files on your own machine, every step auditable, zero
external services.

- **No services to run.** No database server, no vector store, no cloud, no
  build toolchain. `./install.sh` creates one virtualenv and that is the whole
  installation; the Python dependencies are a Markdown stack and the font
  subsetter, pinned in `mcp_package/pyproject.toml`.
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

- [uv][uv]. `./install.sh` uses it to provision Python 3.12, so the
  distribution's Python never decides anything. There is no system-python
  path: supporting one taxes every future change with whatever the oldest
  supported distribution ships.
- Optional: Chrome/Chromium for server-side PDF export — found on PATH
  automatically; override with `BRAINHUB_CHROME_PDF` (see White-label &
  configuration)
- The Python dependencies are declared in `mcp_package/pyproject.toml` and
  installed by `install.sh`: `mcp` for the stdio server, the Markdown stack
  (every entry point imports it), and `fonttools`/`brotli`. The last two subset
  the shipped CJK face per document, and are hard dependencies rather than an
  extra because "Chinese PDFs whose text layer cannot be searched" is not a
  degraded mode anyone should be able to install into by omission.

[uv]: https://docs.astral.sh/uv/

## Install

```bash
tar xzf brainhub-<version>.tar.gz
cd brainhub
./install.sh          # creates the environment and the `bh` command
```

`install.sh` provisions Python 3.12 through uv, so what the distribution ships
never matters — Ubuntu 22.04 and 24.04 behave identically. `--python` pins a
different version, `--venv` and `--bin-dir` relocate what it writes. Without
uv it stops and prints the one line that installs it.

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
bh serve ~/team-brain --port 3000
```

Every verb also accepts the workspace via the `BRAINHUB_HOME` environment
variable instead of a trailing path argument — **prefer the env form when the
verb takes option flags** (argparse cannot place a trailing positional after
flags: `bh publish t --body b <workspace>` fails; `BRAINHUB_HOME=<workspace>
bh publish t --body b` works).

Engine verbs beyond the core set (`health`, `doctor --fix`, `validate`,
`query`, `backup`, `ingest-status`, …) are forwarded automatically:
`bh health ~/team-brain` just works. `bh --help` lists the core verbs;
for the full engine verb list, run `brainhub_engine.py` with the interpreter
`install.sh` created:

```bash
~/.local/share/brainhub/venv/bin/python brainhub_engine.py
```

The scripts run on that interpreter, not on a bare `python3` — every entry
point imports the Markdown stack.

## Artifacts (charts, diagrams, interactive HTML, PDF)

13 renderers: 9 report-chart kinds (`kpi`, `line`, `bar`, `stacked-bar`,
`heatmap`, `scatter`, `funnel`, `donut`, `gauge`), plus `line-chart`,
`bar-chart`, `mermaid` and `interactive-html`.

`line-chart` and `bar-chart` are not older versions of `line` and `bar` — the
names suggest they are, and the capability is what differs. `line` spaces its x
axis evenly by category; `line-chart` scales x numerically, so it can plot
irregular intervals. `bar` is one ranked measure in a single hue; `bar-chart`
is several series per category. Picking `line` for irregular x values silently
evenly-spaces them.

Each renderer registers an `example` spec, which is where its field names are
documented — they are not consistent between kinds. The table in
`skills/46m-bh-runtime/SKILL.md` lists them all, and `check_docs_sync.py` keeps
it honest. `--title` names both the document and the chart drawn inside it.

The `mermaid` renderer covers 22 diagram types verified to render fully offline
under the artifact CSP: flowchart, sequence, class, state, gantt, pie, ER, user
journey, quadrant, timeline, mindmap, gitGraph, xychart, sankey, kanban,
packet, block, radar, treemap, C4 context, architecture (built-in icons), and
venn. For a swimlane use `flowchart` with `subgraph` lanes; for an org chart
use `flowchart TD`; for a layer stack use `block-beta`.

```bash
# Render a spec into ONE self-contained HTML file — zero external requests,
# safe to email:
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

For Claude Code, that is `.mcp.json` (project) or `~/.claude.json` (personal):

```json
{"mcpServers": {"46m-bh": {"type": "stdio", "command": "brainhub-mcp",
  "args": ["--wiki", "/home/you/team-brain/wiki"]}}}
```

The server speaks stdio and serves both protocol eras: a client that opens with
`server/discover` gets the stateless `2026-07-28` revision, one that opens with
`initialize` gets `2025-11-25`. It works with SDK 1.x and 2.x — `mcp` 2.0
renamed `FastMCP` to `MCPServer`, and both are accepted.
`tests/test_mcp_client_compat.py` drives real sessions over both eras and holds
the tool definitions to the limits clients impose (2 KB descriptions, no
root-level schema combinator).

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

### Showing a page inside another app

By default nothing may frame the viewer (`frame-ancestors 'none'`), so a portal
that embeds a BrainHub page in an `<iframe>` gets a blank box. Name the framing
origins to allow it:

```bash
BRAINHUB_FRAME_ANCESTORS="http://portal.internal:20777 https://portal.example.com"
```

Origins only — `scheme://host[:port]`, space- or comma-separated. A wildcard, a
path, or a bare host is dropped, and a value that leaves nothing usable keeps
framing off rather than opening it up. With an allowlist set the viewer stops
sending `X-Frame-Options`, which cannot name an origin and would otherwise
contradict the policy.

This grants **framing, not access**: the viewer has no login, so anyone who can
reach the port can already read it. Put an authenticating proxy in front if that
is not acceptable.

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
# Run these with the interpreter install.sh created, not a bare python3:
#   PY=~/.local/share/brainhub/venv/bin/python
$PY -m unittest discover -s tests     # the suite (pytest works too)
$PY scripts/check_docs_sync.py        # docs still describe the real registry
$PY scripts/verify_artifact.py FILE   # a built artifact is self-contained
$PY scripts/check_runtime_duplication.py
```

CI (`.github/workflows/ci.yml`) runs the first, second and fourth of those on
Python 3.12 and 3.13, and every gate runs even after an earlier one fails, so
one push reports every problem rather than one per round trip. 3.12 is what
`install.sh` provisions; 3.13 is there to see a break coming.

Prose that restates a fact the code owns is checked, not trusted: the renderer
list, the verified mermaid diagram list, the version string across five files,
and the chart palette all have gates. Adding a renderer touches several of them
— `BRAINHUB.md` lists the steps, each naming the gate that fails if skipped.

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
