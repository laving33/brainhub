---
name: brainhub-runtime
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
3. Retrieve only bounded metadata when deciding what already exists:
   ```bash
   python3 brainhub.py artifact list [workspace] --kind report --json
   ```
   Do not treat a catalog record as source-backed knowledge by itself; read or
   verify the referenced artifact before compiling a wiki page.
4. For MCP-configured agents, point the existing local stdio server at
   `[workspace]/wiki`. Prefer the slim surface:
   ```text
   admin(action="artifacts", arguments='{"kind":"report"}')
   ```
   The full compatibility surface also offers `list_artifacts(kind="report")`.
   Both return metadata only; they do not transfer, render, or execute files.
5. The optional human viewer remains loopback-only:
   ```bash
   python3 serve.py --root [workspace]
   ```
   Inspect `GET /api/artifacts?kind=report` from `127.0.0.1` only. MCP works
   without the viewer running.
6. Promote deliberately: artifacts first, then create or update source-backed
   wiki pages, and propose durable memory only after explicit user approval.

Do not expose the viewer, add remote MCP transport, copy artifacts across
Runtime Nodes automatically, or silently convert a workflow artifact into
memory. See `BRAINHUB.md` and `docs/brainhub.html` for installation and
operational verification.
