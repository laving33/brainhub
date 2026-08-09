# Changelog

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
