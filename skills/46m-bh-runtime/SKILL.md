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

## Building charts and diagrams (`bh build` / `bh_build`)

Pick the renderer by the data's job, not by familiarity:

| The reader must… | Renderer |
|---|---|
| See one headline value (+ delta) | `kpi` |
| Follow a trend over time | `line` |
| Compare ranked magnitudes | `bar` |
| See part-to-whole composition | `stacked-bar` |
| Read magnitude across a grid | `heatmap` |
| Judge correlation / quadrants | `scatter` |
| See stage-by-stage drop-off | `funnel` |
| Understand structure, flow, or process | `mermaid` |
| Navigate a tabbed briefing | `interactive-html` |

The registry holds 13 kinds; the four this table leaves out are deliberate, not
missing. `donut` and `gauge` are registered and supported but cautioned — a
part-to-whole reads better as `stacked-bar` and a single ratio as a linear
meter, so reach for them only when a house report format demands the shape.
`line-chart` and `bar-chart` are NOT redundant with `line` and `bar` — the
names suggest they are, and the spec shapes are what actually differ:

| Reach for | When |
|---|---|
| `line` | the x axis is evenly spaced categories (`values` align to `x_labels` by index). Direct-labels each series at its endpoint; no legend box. |
| `line-chart` | the x axis is numeric and possibly irregular (`points` are `[x, y]` pairs, scaled to a real axis with computed ticks). |
| `bar` | one measure, ranked, one hue — a compact horizontal list. |
| `bar-chart` | several series per category, grouped, in categorical colours. |

Picking `line` when the x values are irregular silently evenly-spaces them,
which misstates the data.

`mermaid` covers 22 offline-verified diagram types (flowchart, sequence,
class, state, gantt, pie, ER, journey, quadrant, timeline, mindmap, gitGraph,
xychart, sankey, kanban, packet, block, radar, treemap, C4, architecture with
built-in icons, venn — venn keywords are singular: `set A` / `union A, B`).
No first-class swimlane/org-chart/layer-stack exists: use `flowchart` +
`subgraph` lanes, `flowchart TD`, and `block-beta` respectively.

Complexity budget for any diagram: at most ~9 nodes, ~12 edges, 4 levels of
depth, 5 sequence lifelines. Past the budget, split into one overview diagram
plus per-area detail diagrams — a denser single diagram reads worse, not
more complete. Every node must earn its place; if a relationship is obvious
from layout, drop the arrow.

Do not expose the viewer, add remote MCP transport, copy artifacts across
Runtime Nodes automatically, or silently convert a workflow artifact into
memory. See `BRAINHUB.md` and `docs/brainhub.html` for installation and
operational verification.
