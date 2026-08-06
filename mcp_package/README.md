# brainhub-mcp — BrainHub MCP package

Internal MCP server for BrainHub workspaces. It exposes local memories, wiki
context, and BrainHub artifact provenance without reading artifact bodies
directly.

## Legacy module names

The Python module, `bh` command, and default `~/.brainhub/wiki` path are legacy
internal names inherited from the codebase BrainHub was forked from. BrainHub
Runtime Node installations use `brainhub.py`, `~/.brainhub`, and a local MCP
client entry named `brainhub`.

This package is internal to aworkr. It is not published to PyPI or listed on any
public MCP registry.

## What You Need

`brainhub-mcp` is the MCP server. It needs a BrainHub wiki to read from. The normal
wiki location is `~/.brainhub/wiki`, created by the main BrainHub installers.

Recommended setup:

```bash
# The engine lives at tools/brainhub in the aworkr monorepo.
cd /home/aworkr/aworkr/tools/brainhub
```

The installer scaffolds `~/link/`, installs or upgrades `brainhub-mcp`, writes agent
instructions, and prints the exact MCP config for your machine.

If BrainHub is already installed and you only need to wire MCP into an agent, use
the CLI helper from the main BrainHub package:

```bash
link connect codex ~/link
link connect codex ~/link --write
link verify-mcp ~/link
```

After install, ask your agent:

```text
is BrainHub ready?
start with BrainHub before we continue
query BrainHub for what you know about this project
```

CLI-first agents and BrainHub skills can run the same startup loop directly:

```bash
bh start ~/link --task "working on BrainHub release"
```

## MCP-Only Install

Use this when you already have a BrainHub wiki and only need the MCP package.

```bash
python3 -m pip install --upgrade brainhub-mcp
```

If macOS/Homebrew Python reports `externally-managed-environment`, use a
dedicated venv:

```bash
python3 -m venv ~/.brainhub-mcp-venv
~/.brainhub-mcp-venv/bin/python -m pip install --upgrade pip brainhub-mcp
```

On Windows, use a venv and configure your MCP client with that Python:

```powershell
py -m venv .brainhub-mcp-venv
.\.brainhub-mcp-venv\Scripts\python -m pip install --upgrade pip brainhub-mcp
```

Then add the server to your MCP client config. Use an absolute wiki path:

```json
{
  "mcpServers": {
    "link": {
      "command": "python3",
      "args": ["-m", "brainhub_mcp", "--wiki", "/Users/YOU/link/wiki", "--surface", "slim"]
    }
  }
}
```

If you installed into the venv, use the venv Python:

```json
{
  "mcpServers": {
    "link": {
      "command": "/Users/YOU/.brainhub-mcp-venv/bin/python",
      "args": ["-m", "brainhub_mcp", "--wiki", "/Users/YOU/link/wiki", "--surface", "slim"]
    }
  }
}
```

Replace `/Users/YOU` with your absolute home path. The default wiki is
`~/.brainhub/wiki/`; override with `--wiki /path/to/wiki`. `--surface slim` is the
recommended LLM-native surface for most agents. Use `--surface full` only when
an older integration or a power-user workflow needs every individual tool.

### BrainHub Runtime Node workspace

When this server runs on a BrainHub Runtime Node, configure `--wiki` with that
node's local workspace path (for example, `~/.brainhub/wiki`). The slim
`admin(action="artifacts")` action and full `list_artifacts(kind?)` tool expose
only valid artifact provenance metadata. They do not read artifact bodies,
transfer files, render HTML, or execute outputs. Install BrainHub from a source
checkout and initialize its local workspace before configuring MCP; see
[`docs/brainhub.html`](../docs/brainhub.html).

BrainHub also exposes six document + artifact tools on both the slim and full
surfaces: `bh_publish` (publish/update a source-backed wiki document in place),
`bh_read` (read one back by handle), `bh_search` (handles + snippets), `bh_link`
(add a wikilink between existing pages), `bh_build` (render a mermaid /
line-chart / bar-chart / interactive-html spec into one self-contained HTML
artifact stored with strippable provenance), and `bh_export` (write a
provenance-stripped client copy into the workspace `artifacts/exports/`
directory). The workspace is pinned server-side from `--wiki`; none of these
tools accept a caller-supplied workspace or output path, and `bh_export` rejects
any filename that is not a bare name inside the export directory.

## Agent Workflow

### Slim Surface

New MCP configs should expose BrainHub through six model-facing tools:

1. `status(include_validation?)` checks readiness and safe next actions.
2. `recall(query, budget?, project?, mode?, limit?)` is the one read tool for
   briefs, answer-ready context packets, wiki search, and graph context.
3. `remember(text, ...)` writes only explicit user-approved durable memories.
4. `ingest(action?, strict?)` checks or validates raw-source ingest work.
5. `review(action?, ...)` handles memory inbox, profile, audit, log, explain,
   archive, restore, forget, visibility, and read-only `consolidate` (backlog
   plan) review workflows.
6. `admin(action, arguments?)` is the escape hatch for backup, migrate,
   validate, graph export, pages, captures, rebuilds, and advanced updates.

BrainHub also exposes MCP prompts `link_start`, `link_brief`, `link_remember`,
`link_session_end`, `link_ingest`, and `link_review`, plus resources
`link://instructions`, `link://health`, `link://brief`, `link://profile`, and
`link://project` for clients that support prompt/resource attachment.
`link_start` and `link://instructions` are the portable startup loop: check
readiness, run a brief recall once, then use bounded recall before broad context
reads. If recall finds no useful project context, agents can call
`admin(action="seed_project", arguments="{\"project_root\":\"/absolute/project/path\"}")`
or ask the user to run `bh seed . ~/link` from the repo before retrying recall.
`link_session_end` is the matching proposal-only shutdown loop: capture
useful session notes, return memory candidates, and wait for user approval
before durable writes.

Slim agents should call:

1. `status(include_validation=true)` when connecting or troubleshooting.
2. `recall(query="", mode="brief")` once at the first substantive turn of a session.
3. `recall(query="<question>", budget="micro"|"small")` before broad file reads or asking the user to repeat durable context.
4. `admin(action="seed_project", arguments="{...}")` when startup recall has no useful project context and the project root is known.
5. `ingest(action="status")` when the user drops files into `raw/`.
6. `remember(...)` only when the user explicitly approves saving durable memory.
7. `admin(action="session_end", arguments="{...}")` at session end to propose memory without silently saving it.
8. `review(action="inbox"|"audit"|"profile"|"explain"|...)` for memory lifecycle review.
9. `review(action="consolidate")` when a brief reports a memory backlog: it returns a read-only plan; apply its actions only after the user approves each one.
10. `admin(action, arguments)` for backup, migrate, validate, graph export, captures, rebuilds, and compatibility actions.

Add `review_after` for memories that should return to the review inbox after a
date, or `expires_at` for temporary context that should leave default recall
after a date. Use `admin(action="propose_memories")` or
`admin(action="capture_session")` / `admin(action="session_end")` for
proposal-only review.
For local CLI setup checks, `link verify-mcp --json` returns structured
`issues` and `next_actions` that agents and scripts can consume without parsing
terminal text.
In the local web proposal picker, unreadable raw files are surfaced as
`Fix access` instead of being loaded as empty proposal text.

## Automatic Session Hooks

Agents with session-hook support (Claude Code, Codex, Cursor) can run the
memory loop automatically: `bh connect <agent> --hooks --write` (from a BrainHub
checkout or installer) installs hooks that inject a bounded memory brief into
every new session and store proposal-only session notes at session end.
Sessions with nothing memory-worthy are skipped, duplicate end events are
deduplicated, and durable memory still requires explicit review. If hooks are
installed, agents should skip the manual startup brief call.

## Optional Semantic Recall (still fully local)

Lexical recall is the default and the fallback. Two optional local tiers add
paraphrase recall:

```bash
pip install "brainhub-mcp[semantic]"          # fast tier: tiny static model
pip install "brainhub-mcp[semantic-quality]"  # quality tier: contextual ONNX model
python3 -m brainhub_mcp --semantic-setup --wiki ~/.brainhub/wiki   # explicit one-time model fetch
```

The models load offline-only at recall time (a query can never trigger a
download), embeddings live in plain JSON under `.brainhub-cache/`, and there is no
vector database or service. Semantic-only matches are labeled
(`match: semantic`, capped confidence) so agents verify before trusting them.

## Privacy and Scale

- Local-first: `brainhub-mcp` reads the wiki path you configure and does not call
  external APIs, send telemetry, or require API keys.
- Bounded by default: slim `recall` and `admin` graph/page actions are designed
  for agent context budgets so large wikis do not have to be dumped into a chat.
- Large-wiki search uses in-memory SQLite FTS when Python provides it, with a
  token-index fallback when FTS is unavailable.
- Use `admin(action="graph_summary")` before full graph export unless the user
  explicitly needs every node and edge.

## Tools

Recommended slim tool set:

| Tool | Description |
|------|-------------|
| `status(include_validation?)` | Readiness summary with package version, wiki path, content/page/memory counts, optional validation summary, warnings, and safe next actions. |
| `recall(query?, budget?, project?, mode?, limit?)` | One read tool for startup briefs, focused memory recall, answer-ready context packets, wiki search, graph context, token budgets, and follow-up actions. |
| `remember(text, ...)` | Save explicit user-approved local memory with duplicate/conflict checks, provenance, review state, visibility, optional `review_after`, and optional `expires_at`. |
| `ingest(action?, strict?)` | Inspect pending raw sources, run validation, or rebuild ingest indexes/backlinks after source edits. |
| `review(action?, ...)` | Memory inbox, profile, audit, log, wins, explain, reviewed, archive, restore, and forget workflows. |
| `admin(action, arguments?)` | Escape hatch for backup, migrate, validate, artifact catalogs, operations, search, context, pages, graph, captures, rebuilds, proposals, updates, and compatibility actions. |

Full compatibility tool set available with `--surface full`:

| Tool | Description |
|------|-------------|
| `link_status(include_validation?)` | Readiness summary with package version, wiki path, content/page/memory counts, optional validation summary, warnings, and safe next actions. |
| `link_operations(limit?)` | Inspect pending, failed, or interrupted local BrainHub write operations with safe next actions. |
| `list_artifacts(kind?)` | List local BrainHub artifact provenance metadata by optional kind without reading, transferring, rendering, or executing artifact files. |
| `starter_prompts(project?)` | First-run natural agent prompts plus local readiness/check commands. |
| `migrate_wiki()` | Apply safe, idempotent wiki schema migrations when `link_status` reports a missing or old schema marker. |
| `ingest_status()` | Raw source ingest state with pending files, graph health, raw safety/access diagnostics, the next agent prompt, guided plan, and follow-up checks. |
| `query_link(query, budget?, project?)` | Build a compact answer-ready packet from local memory, ranked wiki search, graph-neighborhood context, provenance, budget reports with estimated packet size, and follow-up actions. |
| `validate_wiki(strict?)` | Validate agent-generated wiki pages after ingest or large edits: frontmatter, type/directory alignment, required sections, dead links, and backlink freshness. |
| `backup_wiki(label?, include_raw?, list_only?)` | Create or list local `.brainhub-backups/` archives before broad repairs or risky wiki edits; raw sources are excluded by default. |
| `memory_brief(query?, limit?, project?)` | Prime the agent before answering or coding with profile counts, relevant memories, review warnings, and safe memory rules. |
| `memory_audit(limit?, project?)` | Read-only health report for memory review backlog, saved raw captures, risk factors, and next actions. |
| `memory_profile(limit?, project?)` | Summarize what BrainHub remembers by type, scope, status, recency, preferences, decisions, and project context. |
| `memory_inbox(limit?, include_archived?)` | List memories that need user review, cleanup, or stronger metadata with primary actions and tool-call hints. |
| `memory_log(limit?, include_captures?)` | List recent memory lifecycle changes from `wiki/log.md` without raw source or memory bodies. |
| `memory_wins(limit?, project?)` | Summarize local proof signals for what BrainHub memory is carrying without telemetry. |
| `review_memory(identifier, note?)` | Mark a confirmed memory as reviewed. |
| `explain_memory(identifier)` | Explain provenance, lifecycle, graph links, review issues, and recall readiness for one memory. |
| `recall_memory(query, limit?, include_archived?, project?)` | Search durable local memories for preferences, decisions, and project context. |
| `remember_memory(memory, title?, memory_type?, scope?, tags?, source?, allow_duplicate?, allow_conflict?, project?, visibility?, review_after?, expires_at?)` | Save an explicit user-approved local memory under `wiki/memories/`; strong duplicates and likely conflicts require explicit override. `visibility` accepts `private`, `project`, or `team` sharing intent. `review_after` accepts `YYYY-MM-DD` for scheduled re-checks; `expires_at` accepts `YYYY-MM-DD` for temporary memories that should leave default recall. |
| `propose_memories(text, source?, limit?, project?)` | Propose durable memories from chat/session notes without writing them. |
| `capture_session(text, title?, source?, limit?, project?)` | Save long chat/session notes under `raw/memory-captures/` and return proposal-only memory candidates plus secret-looking content warnings. |
| `capture_inbox(limit?, project?)` | Review saved raw captures with redacted snippets, secret-warning labels, and accept/redact/delete commands. |
| `accept_capture(capture, index?, title?, memory_type?, scope?, visibility?, tags?, project?, allow_duplicate?, allow_conflict?)` | Accept one proposal from a saved raw capture using duplicate/conflict-safe memory writes. |
| `redact_capture(capture, replacement?)` | Redact secret-looking values from a saved raw capture after user approval. |
| `delete_capture(capture, confirm?)` | Delete a saved raw capture after explicit confirmation. |
| `update_memory(identifier, memory, source?, allow_conflict?, project?)` | Merge new information into an existing memory, blocking likely conflicts with other active memories by default. |
| `set_memory_visibility(identifier, visibility)` | Change a memory's sharing intent between `private`, `project`, and `team` after explicit user approval. |
| `archive_memory(identifier, reason?)` | Archive stale or wrong memory without deleting the Markdown page. |
| `restore_memory(identifier)` | Restore archived memory to active status. |
| `forget_memory(identifier, confirm?)` | Permanently delete a memory only after explicit user confirmation; prefer archive for reversible cleanup. |
| `search_wiki(query, limit?)` | Ranked search — title (20pts), alias (8pts), tag (5pts), fulltext (2pts). Returns scores + snippets. |
| `get_context(topic)` | **Primary tool.** Best matching page (full content) + inbound/forward graph links in one call. |
| `get_pages(category?, type?, maturity?, limit?, offset?, include_all?)` | Bounded page metadata list with filters and follow-up pagination actions; set `include_all=true` only for explicit full metadata export. |
| `get_backlinks(page_name, limit?, offset?, include_all?)` | Bounded inbound + forward links for a page, with total counts and follow-up pagination actions. |
| `get_graph_summary(topic?, limit?, depth?, max_edges?)` | Bounded graph overview or topic neighborhood for large wikis and agent context budgets. |
| `get_graph()` | Full graph export with all nodes + edges; prefer `get_graph_summary` first on large wikis. |
| `rebuild_index()` | Regenerate `wiki/index.md` from current pages so the human-readable catalog stays complete. |
| `rebuild_backlinks()` | Rebuild `_backlinks.json` after ingest or lint. |

Use the full compatibility surface only for older integrations or power-user workflows that need individual tools. New agents should prefer the slim six-tool surface above.
Web approval APIs keep the safe path only: duplicate/conflict overrides should
go through CLI or MCP after explicit human review.

## Wiki location

Default: `~/.brainhub/wiki/`. Override with `--wiki /path/to/wiki`.

## Requirements

- Python 3.10+
- A BrainHub wiki (scaffolded by `install.sh`)
