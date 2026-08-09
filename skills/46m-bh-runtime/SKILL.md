---
name: 46m-bh-runtime
description: Use before creating, cataloging, reviewing, or promoting Runtime Node-local workflow artifacts in BrainHub; keep provenance local and use bounded CLI or MCP access.
---

# BrainHub Runtime

BrainHub is a Runtime Node-local workspace for workflow artifacts and
source-backed knowledge. Load this skill before release reports, research
outputs, HTML deliverables, charts, exports, or any task that needs shared local
provenance across agents on one Unix account. It is not a central service or a
cross-VPS sync mechanism.

1. Check or create the workspace from the BrainHub source checkout:
   ```bash
   python3 brainhub.py init [workspace]
   ```
   The default workspace is `~/.brainhub`; use an explicit `[workspace]` when
   the Runtime Node needs an isolated workspace.
2. Preserve every workflow artifact before promoting conclusions into wiki or
   durable memory:
   ```bash
   python3 brainhub.py artifact add <source-file> [workspace] \
     --kind report --task "<workflow task>" --agent "<worker>" \
     --related knowledge/runbooks/<name>.md
   ```
   Use `report`, `html`, `chart`, or `export`. BrainHub copies the source and
   records task, agent, related paths, timestamp, and SHA-256 provenance.
3. For a page you just wrote yourself, use `capture` instead of `add`:
   ```bash
   python3 brainhub.py artifact capture <source-file> [workspace] \
     --kind html --task "<workflow task>" --agent "<worker>" \
     --name <stored-name>.html --title "<document title>" \
     --related wiki/concepts/<name>.md
   ```
   `add` copies bytes verbatim, which is right for a file that is already a whole
   document. A page an agent authored usually is not: whatever rendered it supplied
   the `<html>`/`<head>` shell, so the file alone has no doctype — it opens in
   quirks mode, and its `<title>` is stranded in the body where browsers discard
   it, costing the artifact its name in the tab and in the viewer's listing.
   `capture` completes the document first (hoisting `<title>`/`<style>` into a real
   `<head>`), then records the same provenance as `add`. A file that is already a
   document passes through untouched, so `capture` is safe to reach for either way.

   This is the local alternative to publishing a page to a hosted service: the
   bytes stay in the workspace, and the artifact gains a SID, a SHA-256, its
   generating task and agent, and `--related` edges into the knowledge graph, none
   of which a hosted copy carries.
4. Retrieve only bounded metadata when deciding what already exists:
   ```bash
   python3 brainhub.py artifact list [workspace] --kind report --json
   ```
   Do not treat a catalog record as source-backed knowledge by itself; read or
   verify the referenced artifact before compiling a wiki page.
5. For MCP-configured agents, point the existing local stdio server at
   `[workspace]/wiki`. Prefer the slim surface:
   ```text
   admin(action="artifacts", arguments='{"kind":"report"}')
   ```
   The full compatibility surface also offers `list_artifacts(kind="report")`.
   Both return metadata only; they do not transfer, render, or execute files.
6. The optional human viewer remains loopback-only:
   ```bash
   python3 serve.py --root [workspace]
   ```
   Inspect `GET /api/artifacts?kind=report` from `127.0.0.1` only. MCP works
   without the viewer running.
7. Promote deliberately: artifacts first, then create or update source-backed
   wiki pages, and propose durable memory only after explicit user approval.

Do not expose the viewer, add remote MCP transport, copy artifacts across
Runtime Nodes automatically, or silently convert a workflow artifact into
memory. See `BRAINHUB.md` and `docs/brainhub.html` for installation and
operational verification.
