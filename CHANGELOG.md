# Changelog

## Unreleased

### Fixed — the test suite now cleans up after itself

281 tests created their scratch directory with `tempfile.mkdtemp()`, which has no
owner: nothing closes it, no context manager ends its life, and the directory
outlives the process that made it. One full run left 544 directories and 407 MB
in `/tmp`.

That is harmless once. On 2026-08-19 the suite ran roughly 64 times overnight on
the development machine and left **34,858 directories and 27.5 GB** — enough to
take that disk to 97% full, with a production control plane sharing it.

Each of those sites now says `self.enterContext(tempfile.TemporaryDirectory(...))`,
which ties the directory's life to the test's: it goes away when the test does,
whether it passed, failed, or raised. The suite already knew this pattern — the
`TemporaryDirectory()` call sites next door all pair with `addCleanup` — the
`mkdtemp` calls were simply never brought along. Measured after: 1219 tests, one
full run, **0 directories and 0 MB** left behind.

`scripts/check_temp_hygiene.py` is a new CI gate so it cannot come back. Smoke
and load scripts under `scripts/` keep their named work directories on purpose:
an operator is meant to open those afterwards, and they are created once per
invocation rather than once per test.

### Added — a portal may now frame the viewer, if you say so

`BRAINHUB_FRAME_ANCESTORS` names the origins allowed to embed viewer pages and
artifacts in an `<iframe>`. Unset — the default — nothing changes: the policy
stays `frame-ancestors 'none'` and the headers are byte-identical to before.

The reason this needed a switch rather than a relaxation: the viewer's refusal
to be framed is correct for a tool with no login. What changed is that a
teammate-facing portal now wants to show a BrainHub page beside a conversation,
and "open it in a new tab" loses the context that made the link worth following.
So the refusal stays the default and the operator names the exception.

The parser fails closed, unlike the sizing knobs next to it: a typo in
`BRAINHUB_MAX_WORKERS` costs a default worker count, a typo here would decide
who may frame the page. Only `scheme://host[:port]` survives — a wildcard, a
path, or a bare host is dropped, and a value that leaves nothing usable keeps
framing off.

With an allowlist set the viewer stops sending `X-Frame-Options`. That header
can say "nobody" or "same origin" and nothing else — its ALLOW-FROM form was
removed from every browser — so once the CSP names an origin the legacy header
can only contradict it. Verified in a real browser rather than argued from the
spec: an allowlisted origin renders the page, an unlisted one is still refused.

This grants framing, not access. The viewer still has no authentication, so who
can read it is still "whoever can reach the port".

### Changed — the chart primitives are ours now

`vendor/report_chart.py` is now `render/chart_primitives.py`, owned outright.
Vendoring was right while BrainHub was an aworkr tool that had to ship to
machines with no aworkr checkout. It stopped being right once the product line
separated: the SSoT is not reachable from a BrainHub checkout, so its drift
guard could only skip — and the "do not edit" rule it enforced still blocked
every fix. A guard that cannot run is not protection; it is a rule with no
remaining reason.

Four defects that had nowhere to be fixed, now fixed:

- **The `<desc>` never reached a screen reader.** `<title>` sat after `<style>`
  instead of first, neither carried an id, and nothing referenced them — a
  `<desc>` nothing points at is widely not announced. Since `role="img"` makes
  the plot's own text presentational, that description was the only route the
  numbers had. Ids are derived from the title's content, so the module's
  byte-identical-output contract still holds.
- **The 9th series repeated the 1st series' colour**, which reads as "same
  category" — a false claim about the data. It now folds to a neutral.
- **The slot order failed our own palette validator** (adjacent ΔE 12.9 light,
  7.8 dark, against a floor of 15). The same eight hues, re-seated to the order
  that passes both modes — which is also the shell's order, so one dataset no
  longer draws series 2 green in one renderer and orange in another.
- **Chinese labels were clipped.** The `hbar` label gutter was a fixed 150px
  measured against Latin numerals; a CJK glyph is a full em against roughly
  0.55 for a digit, so Chinese labels ran out of room at about a third as many
  characters, with no ellipsis to show it. The gutter now follows the widest
  label, bounded so one long label cannot squeeze out the bars.


### Fixed — discoverability and the Skill contract

Audited against Anthropic's published Agent Skills specification and authoring
guide, and against Claude Code's Skills documentation.

- **Nothing told an agent that BrainHub can draw.** Of the routes that carry
  that fact, only the `bh_build` tool description did. The server instructions
  injected on connect named recall, remember, ingest, review and admin and said
  nothing about charts, so a model asked for "a chart of these numbers" had no
  reason to look; `bh --help` described `build` as "render a spec into a
  self-contained HTML artifact", which uses none of the words a person says.
  Both now name the thing: chart, diagram, bar, line, heatmap, funnel, mermaid.
- **Every skill description stated only when to use it, never what it does.**
  The guide asks for both, because the description is what a model matches a
  task against out of a hundred skills. All five now lead with the capability.
- **MCP tool names in the runtime skill were unqualified** (`admin(...)`,
  `bh_build(...)`). The guide requires `ServerName:tool_name`, or the name may
  not resolve when several MCP servers are connected — and the failure looks
  like a missing tool rather than a naming problem.
- `tests/test_skills_contract.py` holds all five skills to the specification's
  frontmatter limits (name ≤64 chars and lowercase-kebab with no reserved word,
  description ≤1,024 chars, no XML) and to the guide's recommendations (body
  under 500 lines, third person, no time-sensitive content, one-level-deep
  references that resolve, server-qualified tool names).

### Added — `install.sh`

- **The installer provisions its own Python 3.12 through uv**, so what the
  distribution ships stops deciding which syntax this codebase may use —
  Ubuntu 22.04's 3.10 and 24.04's 3.12 now behave identically. There is no
  system-python fallback by choice: supporting one taxes every future change
  with whatever the oldest supported distribution happens to ship. Without uv
  the installer stops and prints the one line that installs it.
- **The supported floor is now 3.12** in all four places that declare it
  (`_python_check.py`, `mcp_package/pyproject.toml`, `uv.lock`, ruff's
  `target-version`), and a test compares the lockfile against the packaging
  metadata — `uv run --python X` rewrites `uv.lock`'s `requires-python`
  silently, and nothing else noticed.
- **Skills carry fine-grained `allowed-tools`**, so BrainHub's own commands run
  without a prompt each time while the grant stays scoped to those commands
  rather than to Bash at large.
- `_python_check.py` runs before any other import in all three entry points and
  is written in 3.7-compatible syntax on purpose: a guard that only parses on
  the versions it exists to reject never executes. Previously a `datetime.UTC`
  import at the top of `brainhub.py` meant that on stock Ubuntu 22.04 every
  command — `bh --help` included — died with an ImportError naming a stdlib
  module, which reads as a broken install rather than a version floor.

### Fixed

- **"Zero dependencies. The engine, CLI, and web viewer run on Python 3.10+
  standard library alone" was not true**, and had not been for a long time.
  All three entry points import markdown-it-py through
  `brainhub_core.markdown`; none of them starts on a bare interpreter. Nothing
  caught it because every developer, every test run and every CI job happened
  inside an environment that already had the package. The installer's habit of
  executing an entry point on a clean interpreter is what surfaced it. The
  README now states what is actually required, and a test fails on the claim
  returning.

### Fixed

- **The MCP server would not start against a current SDK.** `mcp` 2.0 renamed
  `FastMCP` to `MCPServer` and moved it out of `mcp.server.fastmcp`, and the
  dependency was an unbounded `mcp>=1.0.0` — so a fresh install resolved to 2.x
  and every launch exited with "mcp package not found. Install with: pip
  install mcp" while the package was in fact installed. Both names are now
  accepted (the constructor, `.tool()` and `.run(transport=…)` are unchanged),
  the bound is `>=1.0.0,<3`, and the message names the real problem.

### Added — accessibility and the tool contract

- **Every data chart now ships a `<details>` data table.** WCAG 1.1.1 asks a
  complex image for an alternative that serves the equivalent purpose, and
  W3C's own technique for a chart is a table. `role="img"` makes the plot's
  labels presentational, so before this the numbers existed nowhere a screen
  reader could reach — the `<desc>` was one run of speech with no way to
  compare two values. Plain markup, no JS, and the print CSS already opens
  every `<details>`, so it reaches the PDF too. 11 of 13 kinds; `mermaid` and
  `interactive-html` are not data charts.
- **`bh_build`'s `spec` is typed as an object.** It was `spec: str`, which
  generated `{"type": "string"}` — no schema at all for the one argument whose
  shape the model has to get right. It is now `dict | str` (the string form
  keeps already-configured callers working), and every spec error returns the
  renderer's registered `example`, so a wrong guess is recoverable in one retry.
  The union sits on the PROPERTY, not at the schema root: a root-level
  combinator is the one shape MCP clients refuse or flatten, and a flattened
  schema stops enforcing `required`.
- **Per-renderer spec shapes moved onto the `spec` argument.** With them inline
  in the docstring, `bh_build`'s description reached 2,848 bytes against a
  2,048-byte client cap — it was shipping truncated, losing its own tail. The
  help text is generated from the registered examples, so it cannot drift.
- `serverInfo.version` was the empty string; it now reports `BRAINHUB_VERSION`,
  so a client log can say which build it was talking to.
- `tests/test_mcp_client_compat.py` drives a real stdio session and checks these
  against the tool definitions a client actually receives: the description cap,
  no root-level combinator, an object form for `spec`, every renderer named in
  the spec help, and the reported version.

### Compatibility notes

- Verified against the MCP specification revision **2026-07-28** (the protocol
  is now stewarded by the Agentic AI Foundation under the Linux Foundation,
  donated by Anthropic in December 2025) and Claude Code's documented client
  limits.
- **The server already serves `2026-07-28`, and also the handshake era.** Which
  one a session uses is the client's choice, not ours: a client that opens with
  `server/discover` gets the stateless protocol, one that opens with
  `initialize` gets `2025-11-25`, and each connection then refuses the other
  era's opening move. Verified over real stdio — `server/discover` returns
  `supported_versions: ["2026-07-28"]`, and every result carries the revision's
  new `resultType`, `ttlMs`/`cacheScope` and `_meta` serverInfo. All of it comes
  from the SDK; no protocol code of ours was involved.
- Nothing here uses a feature the revision deprecates (Roots, Sampling,
  Logging). Server logging already goes to stderr, which is the migration the
  spec recommends.
- stdio remains a supported, recommended transport. HTTP+SSE is deprecated in
  favour of Streamable HTTP; we do not use either.

### Fixed — the 13 renderers as one system

Found by rendering every kind with real data and Chinese labels and *looking at
the screenshots*, which is how several of these surfaced at all: each is
invisible in the markup and obvious on screen.

- **A caller's title was dropped by 12 of 13 kinds.** `bh build --title 季度營收`
  produced a chart headed `Ranked`, `Trend`, `KPI`, `Gauge` or `Share` — the
  vendored default — or, for `bar-chart` / `line-chart` / `mermaid`, no visible
  title at all, while the browser tab showed the real one. The shell heading was
  suppressed for everything with `output_kind == "chart"` on the assumption that
  charts title themselves; renderers now declare `self_titled`, and every
  renderer resolves `request.title` ahead of the spec's.
- **Report charts ignored the theme.** Their SVG themed off
  `prefers-color-scheme` alone, so switching the page to dark left a white block
  on a dark page (9 of 13 kinds, plus the viewer's dashboard trend chart). Their
  variables are now re-homed onto the shell's brand tokens, which also means a
  brand pack finally recolours them.
- **Two palettes disagreed on every slot but the first.** The vendored order and
  `--series-1..8` held the same eight hues in different positions, so one
  dataset drew series 2 green in one renderer and orange in another — and the
  vendored order fails `validate_palette.py` (adjacent ΔE 12.9 light, 7.8 dark,
  against a floor of 15) where the shell's passes. Report charts now point at
  the validated order.
- **Two charts of the same kind on one page shared their accessible-name ids.**
  The prefix was a module constant, so it separated line from bar but not line
  from line; a screen reader announced the second chart with the first one's
  name. It is now a content hash, which keeps output deterministic.
- **`<desc>` described the shape, not the data.** `role="img"` makes the plot's
  own text presentational, so "line chart, 1 series over 3 points" was the
  entire content a screen-reader user received. Descriptions now carry values.
- `line-chart`'s tick generator was named `_nice_ticks` and divided the range
  evenly, producing axis labels like 289.25. Both charts now use one d3-style
  generator with geometric thresholds, and scale to the ticks rather than to the
  raw data range (which had pushed the outermost label outside the plot).
- The two charts' captions sat on opposite sides of the plot, their legends in
  different places — the line chart's floated inside the plot area, over the
  data — and their margins differed by a few pixels each way. All shared now.

### Added

- `render/renderers/_chart_base.py` — the shared geometry, formatting and markup
  the two hand-written chart renderers had each implemented separately.
  Includes `estimate_text_width`, which knows a CJK glyph is a full em: layout
  constants sized against Latin digits truncate Chinese labels at roughly a
  third of the characters, which matters for a Chinese-first product.
- `bh_build`'s docstring now carries the spec shape for every renderer and says
  that `title` outranks the spec's. It is the contract an agent actually reads,
  and it previously said only "a JSON-object string describing what to draw" —
  leaving the field names discoverable nowhere, for a set of names that is not
  consistent between kinds.
- Renderers now register an `example` spec. It is the only place the field names
  exist — they are not consistent between kinds (five names for "the category
  labels", and `series` means two incompatible shapes) and appeared in no prose.
  Tests render it, `SKILL.md` quotes it in a new spec table, and
  `check_docs_sync.py` fails when a kind lacks one or the table omits a field.
  This replaced three separate copies of the same fixtures, two of which were
  wrong: they passed raw counts to fields the primitive formats as a percentage,
  so the canonical donut labelled a slice "300%" and the canonical stacked bar
  labelled a segment "27100%". Both were found by looking at a screenshot, and
  a test now fails on any percent-formatted example that exceeds 100%.

### Security

- **Artifacts no longer permit arbitrary inline script.** `script-src` was
  `'unsafe-inline'`, so any `<script>` that reached the markup would run —
  escaping was the only thing standing between a chart label or diagram source
  and execution. Each artifact now pins the sha256 of every script it actually
  carries, and admits nothing else. Verified in headless Chromium: a smuggled
  `<script>` is refused while every renderer's own scripts still run.
  - The PDF button's `onclick` moved into a script, because an event-handler
    attribute cannot be covered by a hash and one of them would have forced the
    whole document back to `'unsafe-inline'`.
  - Anything splicing script into a built artifact must now call
    `render.document.authorize_injected_scripts`; the viewer's PDF-button
    upgrade and print-reveal shim do. Artifacts built before this change keep
    the permissive policy and are unaffected.

### Added

- **`scripts/verify_artifact.py`** — checks a built artifact carries no remote
  reference, no executable attribute, no nested-document tag, and no non-image
  `data:` URL. This is the static mirror of the CSP: a CSP is enforced in the
  reader's browser, where a violation renders wrong silently and nobody who
  built the file finds out. Runs over all 13 kinds in the test suite. Its first
  run found every artifact shipping an inline `onclick`.
- **`scripts/check_docs_sync.py`** — the renderer registry and the verified
  mermaid type list are executable facts restated in five prose surfaces. This
  fails when any of them falls behind, with per-kind exemptions that are
  themselves checked for staleness.
- **`.github/workflows/ci.yml`** — the suite previously ran only when somebody
  remembered. Matrix over Python 3.10 and 3.12 (later 3.12 and 3.13, once
  `install.sh` began provisioning the interpreter); every gate runs even after
  an earlier one fails; installs `./mcp_package` and nothing else.
- Tests for what already existed but was never enforced: the version string
  across five files, the series palette against `validate_palette.py` in both
  modes, and the accessible-name contract for chart SVGs.

### Fixed

- **The mermaid init script never ran.** The vendored bundle's shim exposes the
  API at `__esbuild_esm_mermaid_nm.mermaid.default` (the bare `.mermaid` is the
  ESM module namespace), and the init script executed in `<head>` before the
  container element existed — so `initialize()` threw, the error handler itself
  crashed on a null container, and diagrams only rendered because mermaid's own
  auto-start defaults kicked in. Consequence until now: `securityLevel:
  'strict'`, the `neutral` theme, and the `data-brainhub-ready` signal were
  silently never applied. The script now resolves `.default` and defers until
  `DOMContentLoaded`; a regression test pins both.
- The mermaid diagram source is no longer duplicated into a dead JS string
  literal in the init script — it reaches the page only as html-escaped text in
  the `<pre class="mermaid">` block, removing the `</script>` breakout surface
  entirely.
- A report-chart spec with an unknown key now raises `ValueError` (which
  `bh build` and `bh_build` report cleanly) instead of leaking `TypeError` from
  the chart function's kwargs.
- `bh_build`'s MCP docstring and `mcp_package/README.md` no longer claim only 4
  renderers exist; both now list all 13 kinds, and the docstring gained a
  job-based selection guide and a diagram complexity budget.
- **Python 3.10 works again — the declared floor had never been run.**
  `pyproject.toml` claims `>=3.10` while `uv.lock` pins the dev environment to
  `>=3.12`, so nothing ever executed the floor; four modules imported
  `datetime.UTC`, which is 3.11+, and every one of them failed at import on
  3.10. Replaced with `timezone.utc`. Found by adding 3.10 to the new CI matrix
  and confirmed by running the full suite on a provisioned 3.10 interpreter.

### Added

- **22 mermaid diagram types verified offline.** Each rendered end-to-end in
  headless Chromium against the artifact CSP (no network): flowchart, sequence,
  class, state, gantt, pie, ER, journey, quadrant, timeline, mindmap, gitGraph,
  xychart, sankey, kanban, packet, block, radar, treemap, C4, architecture
  (built-in icons), and venn. The verified list is documented in the renderer,
  README, and the `46m-bh-runtime` skill, with stand-ins for the types that have
  no first-class support (swimlane → `flowchart` + `subgraph`, org chart →
  `flowchart TD`, layer stack → `block-beta`).
- Mermaid diagrams now carry an accessible name. Mermaid emits its `<svg>` as
  `role="graphics-document"` with no name at all, so a diagram announced as an
  unnamed graphic; the init script now labels it from the artifact title. The
  document shell deliberately does NOT wrap chart bodies in an outer
  `role="img"` — that would make the graphic's own `<title>`/`<desc>` subtree
  presentational, which is worse than the gap it closes.
- The mermaid renderer now honours the caller's title (`bh build --title`,
  `bh_build(title=…)`); it previously read only the spec's `title` key, so a
  caller-supplied title named the document but not the diagram inside it.
- Dedicated test file for the 9 report-chart kinds
  (`tests/test_render_report_charts.py`) — previously they were covered only
  indirectly by the brand-pack suite.
- Artifacts now honour `prefers-reduced-motion: reduce` unconditionally. The
  motion-flattening CSS existed but shipped only for `--static` builds, which
  is a build-time choice about capture; the reader's OS accessibility setting
  was reaching nothing but one button transition.
- `bar-chart` and `line-chart` SVGs now carry `<title>`/`<desc>` with prefixed
  ids and `aria-labelledby`, replacing a bare `aria-label` and no description
  at all. Bare `id="title"`/`id="desc"` are refused by test: two charts on one
  page would make the second announce the first one's name.

## 2.0.0

A breaking release. Every rename below is deliberate and has **no backward
compatibility shim** — the old names were inherited from the project BrainHub was
forked from, and keeping them readable would have kept the old vocabulary alive.
Work through "Migrating" before upgrading a machine that already runs 1.6.0.

### Migrating from 1.6.0

1. **Rename environment variables.** Anywhere you export these — shell profiles,
   systemd units, CI, wrapper scripts:

   | Old | New |
   |---|---|
   | `LINK_CLI_COMMAND` | `BRAINHUB_CLI_COMMAND` |
   | `LINK_PLAIN` | `BRAINHUB_PLAIN` |
   | `LINK_MCP_SURFACE` | `BRAINHUB_MCP_SURFACE` |
   | `LINK_SEMANTIC` | `BRAINHUB_SEMANTIC` |
   | `LINK_SEMANTIC_MODEL` | `BRAINHUB_SEMANTIC_MODEL` |
   | `LINK_SEMANTIC_PROVIDER` | `BRAINHUB_SEMANTIC_PROVIDER` |

   An old variable is now simply ignored, which is silent: the CLI keeps working
   with default behaviour instead of erroring, so grep your configs rather than
   waiting for a failure.

2. **Re-run `bh connect <agent>` for each configured agent.** The MCP server key
   changed from `link` to `46m-bh`, so agent tool names change from
   `mcp__link__*` to `mcp__46m-bh__*`. Reconnecting migrates the config: the old
   entry is removed rather than left beside the new one, which would otherwise
   register the same server twice and show duplicate tools.

3. **Re-link the skills.** `skills/brainhub-*` are now `skills/46m-bh-*`. If you
   copied or symlinked them into `~/.claude/skills/`, remove the old five and link
   the new ones.

4. **Check your workspace path.** The default workspace moved from `~/link` to
   `~/.brainhub`, which is what the docs and `brainhub.py` already promised — the
   MCP server and the CLI defaults were the parts that disagreed. If your wiki
   lives at `~/link/wiki`, either move it or pin the old location:

   ```bash
   export BRAINHUB_HOME=~/link
   ```

   Nothing is moved for you, and a wrong default shows up as an *empty* wiki
   rather than an error.

### Breaking

- `LINK_*` environment variables renamed to `BRAINHUB_*` with no fallback.
- MCP server key in agent configs: `link` → `46m-bh`.
- Skills renamed: `brainhub-{health,ingest,memory,retrieve,runtime}` →
  `46m-bh-{...}`.
- Default workspace: `~/link` → `~/.brainhub` (single definition, shared by the
  CLI defaults, the MCP server, and the onboarding text).
- MCP registry name: `aworkr.internal/brainhub` → `46m.internal/bh`.
- `LINK_VERSION` constant renamed to `BRAINHUB_VERSION`.

### Added

- **Brand pack.** `BRAINHUB_BRAND_DIR` points at one directory holding
  `tokens.css`, `logo.svg`, `fonts/` and optionally `daisyui.css`, replacing the
  whole corporate identity at once. Previously the three assets resolved down
  three unrelated paths — the logo had a four-level lookup, fonts had one
  variable, and the colour tokens had no override at all, so a deployment could
  swap its logo and still render every page in someone else's palette. A pack
  need only provide what it changes; anything absent falls back to the per-asset
  variable, then the bundled theme, then nothing, and a missing asset never
  raises.
- **`bh artifact capture`.** Stores a page an agent just wrote, completing it into
  a standalone document first. `add` copies bytes verbatim, which is right for a
  file that is already a document; a page an agent authored usually is not,
  because whatever rendered it supplied the `<html>`/`<head>` shell. On disk that
  file has no doctype (so it opens in quirks mode) and its `<title>` sits in the
  body where browsers discard it. `capture` hoists `<title>`/`<style>` into a real
  `<head>`, then records the same provenance as `add`. A file that is already a
  document passes through untouched.
- **Viewer capacity controls.** `BRAINHUB_ACCEPT_BACKLOG`, `BRAINHUB_MAX_WORKERS`,
  `BRAINHUB_REQUEST_TIMEOUT`, `BRAINHUB_KEEPALIVE_IDLE_TIMEOUT`,
  `BRAINHUB_MUTATION_RATE_LIMIT`, `BRAINHUB_MUTATION_RATE_WINDOW`. Each falls back
  to its default when unparseable rather than refusing to start.
- `scripts/loadtest_http_viewer.py` — reproduces concurrent-reader load so viewer
  capacity is verifiable on the hardware that will run it.
- `scripts/build_cjk_subset.py` — rebuilds the vendored CJK face. The repertoire
  is derived from Python's `big5` codec rather than a hand-kept character list,
  because a hand-kept list is what silently misses the rare character in a
  client's name — and a missing character looks fine on the machine that
  rendered it.

### Fixed

- **Chinese documents rendered with no embedded CJK face on any install but ours.**
  The print pipeline took its CJK face from a brand asset directory that is not in
  the distributed package, and needed `fontTools` — an optional extra — to subset
  it. On a clean install neither was present, so every Chinese document fell back
  to the reader's own fonts. Both consequences pass a page-by-page human review,
  which is why a whole production run shipped before anyone noticed:
  CJK bold silently stops working (`<strong>` is still in the markup, the paper
  looks the same), and the PDF **text layer** records whatever codepoint the
  substituted glyph was reachable by — observed as Kangxi Radicals, `山` U+5C71
  arriving as `⼭` U+2F2D. The glyph is the right shape, so nobody sees it; the
  client just cannot search the document and copy-paste yields broken characters.
  Whoever renders can never see either one: their machine has system CJK fonts.

  Now a CJK face always ships: `vendor/NotoSansCJKtc-subset.woff2`, built by
  `scripts/build_cjk_subset.py` from the OFL-licensed Noto Sans CJK TC, covering
  the Big5 repertoire plus 99.8% of CJK Ext-A and what the source carries of
  Ext-B and the compatibility ideographs — 31,340 codepoints, weight axis intact
  so bold still works. `fonttools`/`brotli` are hard dependencies rather than an
  extra, and `make_dist.sh` refuses to build a package missing the face or its
  licence. A character outside that coverage is named on stderr instead of
  silently falling back.

  Two things about the face are load-bearing and must not be "tidied":
  the **Kangxi Radicals block is excluded on purpose**. Noto Sans CJK shares one
  glyph between a radical and its han character and names it after the radical
  (`山` U+5C71 and `⼭` U+2F2D both map to `uni2F2D`); a shared glyph is ambiguous
  when a PDF's text layer is built by reverse-mapping, and the lower codepoint
  wins — which is the reported corruption, and would hit 207 characters including
  `一` U+4E00. The build refuses if the radical block is ever added back. And the
  **pan-CJK face is used rather than Noto Sans TC** because that one carries only
  8.7% of Ext-A, and being TrueType-flavoured its `gvar` table made subsetting take
  7.4s per document instead of 0.3s.
- **The viewer's download-PDF button could not work on any install but ours.** It
  invoked one absolute path to an in-house wrapper script, so elsewhere the
  endpoint just answered 404. A Chromium-family browser is now discovered on PATH
  (or in the standard macOS/Windows locations) and driven with `--print-to-pdf`;
  `BRAINHUB_CHROME_PDF` still overrides, and when nothing is available the reason
  says which of the two to fix.
- **The viewer dropped connections under a handful of simultaneous readers.** Two
  stdlib defaults were wrong for this traffic and both presented as "the viewer
  won't connect" with no HTTP status anywhere: the accept queue was 5 deep (one
  page view opens a burst of parallel connections, and once the queue overflows
  the kernel drops the SYN, leaving the browser waiting on a ~1s retransmit), and
  the handler spoke HTTP/1.0, so every request cost a fresh TCP connection.
  Measured with 30 simultaneous readers: 34% of requests failed and the kernel
  dropped 896 SYNs; after the fix, no failures and no drops, with median latency
  down from 2021ms to under 500ms. Verified to 50 readers.
- Request handling is now concurrent **and bounded**. `ThreadingMixIn` spawned one
  thread per connection with no ceiling, so a burst of readers — or one client
  holding connections open — grew the thread count without limit.
- `bh artifact add`/`update` no longer report a good workspace as uninitialized. A
  wiki-only workspace (what `brainhub_engine.py demo` produces) is initialized; it
  just has no artifact store, and the old message sent its owner to re-initialize
  something already fine. The three causes — wrong path, wiki-only workspace,
  unknown artifact kind — now read differently and name the fix.
- Font-repair tests skip where the brand fonts are absent instead of erroring, so
  a standalone install has a green suite. Absent brand fonts already degraded
  gracefully at runtime (no embed, no error); a permanently red suite cannot tell
  anyone that they just broke something.

### Changed

- `LICENSE`: fork attribution is now `46.money`. The upstream author's copyright
  line stays, as the MIT terms require.
- Viewer transport sizing and the bounded pool live in
  `brainhub_core/web_http.py`; brand resolution lives in `brainhub_core/brand.py`.
  `serve.py` stays a thin adapter over both.
