# BrainHub — architecture and contract

BrainHub is a node-local knowledge management workspace for workflow agents.
(Install and quickstart live in `README.md`; this file is the design contract.)

It intentionally has no central server, remote MCP endpoint, or cross-node
sync. One Unix account on one node owns one workspace. Every local agent
configured for that account can retrieve bounded, source-backed context
through stdio MCP or the CLI.

## Workspace layout

```text
<workspace>/                   # any directory; created by `bh init`
├── BRAINHUB.md                # workspace contract (written at init)
├── BRAINHUB-SCHEMA.md         # agent-facing schema instructions
├── raw/                       # immutable source documents (humans drop these)
├── wiki/                      # published documents + reviewed memory
│   ├── documents/             # `bh publish` output (reports, plans, diagnoses)
│   ├── index.md               # master catalog
│   └── log.md                 # chronological operation record
├── knowledge/                 # runbooks and source-backed syntheses
├── decisions/                 # decision boards — one JSON per batch (SCHEMA.md)
├── dashboard/                 # spog.json (the board's data) + history.jsonl
└── artifacts/
    ├── html/                  # self-contained interactive deliverables (`bh build`)
    ├── charts/                # rendered charts / mermaid
    ├── reports/               # markdown reports with provenance
    └── exports/               # final external outputs (PDF via chrome wrapper)
```

`decisions/` and `dashboard/` are siblings of `wiki/`, not children of it. Both
are read and written by the viewer but hold no wiki pages, and putting them
under `wiki/` would put them in the index, the search corpus, and the backlink
graph — three places they do not belong.

## Addressing

Every addressable object carries a sid, and one URL shape addresses it:

```
/page/<SID>/<title>          wiki pages       (sid type W)
/artifact/<SID>/<filename>   stored artifacts (sid type A)
/raw/<SID>/<filename>        raw source files (sid type R)
```

Only the sid is load-bearing — the title segment is decoration, so a renamed
page or a hand-typed title still resolves and redirects to the current one. A
sid carries a check symbol, so a mistyped one 404s instead of landing on a
different object. Pre-sid URLs (`/page/<title>`, `/artifact/<subdir>/<file>`)
redirect to the canonical form; objects that have no sid yet keep serving at
their old URL. `brainhub_core/addressing.py` owns both directions — building
and parsing — so adding an addressable kind is a sid type char plus one entry
in `KIND_BY_SID_TYPE`, not a new URL shape.

Pages keep their sid in frontmatter and artifacts in their `.meta.json`
sidecar, but a raw file is whatever a client sent us and has nowhere to put
one, so raw ids live in `raw/.sids.json` — hidden, because `ingest` walks
`raw/` and would otherwise ingest a sidecar as if it were a source document.
Each entry stores a sha256 beside the path, and resolution falls back to it, so
a raw file that gets renamed or moved is still found by its id. That matters
because a source page currently cites its raw file by **path substring**
(`ingest.source_matches_by_raw`): rename the file and the page silently loses
its link to the evidence it was built from. `brainhub sid-backfill` assigns ids
to any raw files that predate this.

## Provenance

`bh artifact add` never modifies the source artifact. It copies it into the
workspace and writes a `<filename>.meta.json` sidecar containing its kind,
source task, generating agent, related knowledge links, timestamp, stored
path, and SHA-256 checksum. `bh export` strips embedded provenance on the way
out, so client-facing files never carry workspace internals.

`add` is create-only. To iterate on one document instead of growing `-v2`
orphans, use `bh artifact update <new-source> --kind <kind> [--name <stored
filename>]`: it replaces the bytes, keeps the sid and `created_at`, and
refreshes `sha256`, `updated_at`, and `revision`. Overwriting a stored file by
hand does none of that — the sidecar keeps claiming the old checksum, and
nothing reports the mismatch, so `update` warns when it finds one. To repair a
record after such an overwrite, point `update` at the stored file itself: it
skips the copy, warns about the drift it found, and rewrites the sidecar to
match the bytes. `revision` only increments when the checksum actually changed,
so re-running it is a no-op rather than a way to inflate the version count.

## Human-facing surfaces

Three pages exist for a human rather than an agent. They share one rule: **the
page states what it does not know.** A surface that quietly prints a plausible
number is worse than one that prints nothing, because nobody goes looking.

- **Decision board** — `GET /decide/<batch_id>`, write-back `POST
  /api/decision-board/decide`, storage `decisions/<batch_id>.json`. Data
  contract and the enforced LAWS live in that directory's `SCHEMA.md`; how an
  agent drives one is `AGENT_GUIDE.md`. Load-bearing property: `status:
  "decided"` is derived, never asserted — a close over blank items is refused
  (409), and an explicit skip is written as a real outcome. `brainhub_core.
  decision_audit` checks the same invariant on data at rest and the health page
  runs it on every load, because the write path can only defend files it wrote.
- **Status dashboard** — `GET /dashboard`, data `dashboard/spog.json`, history
  `dashboard/history.jsonl` (append-only, one entry per data version). It
  replaced a hand-maintained HTML artifact that went five days stale while
  printing a fresh-looking date. Two properties are the whole point: the page
  states its own age and warns past 48h, and the section derived from
  `decisions/` cannot go stale because nobody maintains it. The trend chart
  refuses to draw a single-point line, and a missing series is named on the page
  rather than filled with a zero — a fabricated zero and a measured zero look
  identical.
- **Health** — `GET /health`. Readiness, validation, interrupted operations, and
  the decision-board invariant. Checks report the healthy case out loud, so a
  check that never fires is distinguishable from a check nobody wired up.

## Design system

The viewer's stylesheet is a **committed artifact**, not a build step:
`brainhub_core/vendor/aworkr-daisyui.css`, generated from `build/` (daisyUI +
Tailwind, versions pinned to the ones the public aworkr site runs). Running
BrainHub needs no Node and no network — it is installed on machines that have
neither the toolchain nor the brand library.

Colour comes from `vendor/aworkr-tokens.css` (a vendored copy of the CIS token
file); no hex literal is written in `build/input.css`. Every daisyUI class the
viewer uses is a **finished string** in `brainhub_core/ui_classes.py`, which is
also the only file Tailwind scans — a composed `f'class="btn-{kind}"'` is
invisible to a text scanner and would silently render unstyled, and scanning the
whole package would let renaming a Python variable change the shipped
stylesheet. `build/README.md` has the measurements behind both rules.

## Adding a renderer

Each step names the gate that fails if you skip it, so none of this depends on
remembering:

1. Drop one module into `mcp_package/brainhub_core/render/renderers/`, calling
   `@renderer("my-kind", output_kind=…, input_spec=…, description=…, example=…,
   self_titled=…)`. Discovery is automatic — no edit to the registry, the CLI,
   or the MCP server.
2. `example` is a minimal spec that renders, and it is the kind's spec
   documentation: field names differ per kind and exist nowhere else. Tests
   render it instead of restating fixtures, so a new renderer cannot enter
   uncovered. *`scripts/check_docs_sync.py` fails when a kind registers none.*
3. `self_titled` says whether the output draws its own visible title. Get it
   wrong and the artifact shows the title twice, or — the way this shipped for a
   long time — shows neither while the browser tab shows the real one.
   Renderers that self-title must resolve `request.title` **ahead of**
   `spec["title"]`, or a caller's `--title` is silently discarded.
4. Name the kind in `README.md`, `mcp_package/README.md`,
   `skills/46m-bh-runtime/SKILL.md`, and the `bh_build` docstring, and add its
   spec to the skill's field table — or declare the omission with a reason in
   `scripts/check_docs_sync.py`'s `RENDERER_OMISSIONS`. *That script fails
   otherwise*, on a missing mention, a missing spec field, and on an exemption
   for a kind that no longer exists.
5. Drawing an `<svg>`? Use `_chart_base.svg_open()` rather than assembling one:
   it applies the accessible-name contract (`role="img"`, `<title>` FIRST,
   non-empty `<desc>`, `aria-labelledby` naming both) and takes a per-chart id
   prefix from `_chart_base.id_prefix(base, spec)` — a module-level constant
   separates one kind from another but not two charts of the same kind, and the
   second then gets announced with the first one's name. Because `role="img"`
   makes the plot's text presentational, the `<desc>` must carry the DATA, not
   describe the shape. *`tests/test_render_a11y_contract.py` and
   `tests/test_chart_base.py` fail otherwise.*
6. Reuse `_chart_base` for geometry too — margins, ticks, legend, caption. Those
   were duplicated once and drifted into different answers in every one of them.
7. Emitting script? It must be a generated constant, never assembled from caller
   data, and must not use an `onclick=` attribute. *`scripts/verify_artifact.py`
   fails on the attribute, and the artifact's own hashed CSP refuses any script
   the build did not produce.*

Fix the source of truth rather than widening a gate: each of these caught a real
defect the first time it ran.

**Look at the output.** Every gate above reads markup. The defects that survived
longest — a chart headed "Ranked" instead of the caller's title, a white chart
on a dark page, a legend printed over its own data — were all invisible to a
string assertion and obvious in a screenshot. Render the kind with realistic
data (Chinese labels included, since CJK is a full em against roughly half that
for a digit) and open it before calling the work done.

## Agent access

Agents use the local stdio MCP connection (`pip install ./mcp_package`,
configure `--wiki <workspace>/wiki`) or the CLI — never a remote endpoint.

- Recommended slim surface: `admin(action="artifacts", arguments='{"kind":"report"}')`.
- Full compatibility surface: `list_artifacts(kind="report")`.

Both are read-only catalog queries returning provenance metadata; artifact
files are not transferred, rendered, or executed through MCP.

Humans browse the same workspace through the viewer (`serve.py`) on a trusted
private LAN. The viewer is read-mostly, but its write endpoints have **no
authentication** — deployment assumes every caller on the network is trusted;
never expose the port publicly.

## Compatibility boundary

### Engine module

Storage, search, validation, and the memory layer live in
`brainhub_engine.py`; `brainhub.py` is the product CLI in front of it and
forwards engine verbs it does not own. The product contract is `brainhub.py`
(alias `bh`) and the `BRAINHUB_HOME` workspace convention — documentation must
not present any other location as the default.

### License

BrainHub is a hard fork of an MIT-licensed project. MIT requires the original
copyright notice to survive in copies, so `LICENSE` is retained verbatim and is
the single place upstream attribution lives. Nothing else in the tree carries
upstream branding — `tests/test_brainhub_branding.py` enforces that.

## Non-goals

- No shared central BrainHub service.
- No cross-node live replication.
- No unauthenticated HTTP exposure.
- No automatic promotion of workflow output to durable memory.

Knowledge and memory promotion remain explicit: artifacts are preserved first,
then agents can compile source-backed wiki pages or submit durable-memory
proposals for review.
