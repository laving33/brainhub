"""The daisyUI classes BrainHub uses — the single place they are written out.

Two jobs, and the second is why this file exists rather than the classes living
inline in the templates.

1. **It is the build's scan target.** Tailwind finds classes by reading source
   text. Pointed at the whole package it also reads ordinary Python and mistakes
   identifiers for classes: scanning ``mcp_package`` emitted 183 selectors and
   94KB, twelve of them from words like ``table``, ``list``, ``card`` and
   ``collapse`` appearing in unrelated code. Scanning only this file emitted 14
   selectors and 23KB. The difference is not just size — with a whole-tree scan,
   **renaming a Python variable silently changes the shipped stylesheet**.

2. **It forces complete literal names.** The scanner cannot see a class that is
   assembled at runtime: a written-out ``mt-7`` is emitted, a composed
   ``mt-{n}`` is not, and nothing errors — the page just renders without it.
   Composing class names here is impossible by construction, because every value
   is a finished string.

RULES
  - Write the whole class name. Never f-string a fragment together.
  - Add an entry only when markup actually uses it; an unused entry is dead
    weight that still ships.
  - After editing, rebuild: ``cd build && npm run build``. The vendored CSS is
    the artifact — this file alone changes nothing.
"""
from __future__ import annotations

# ── Shell: header / nav / footer ──────────────────────────────────────────
# navbar + menu per the brand guide's 📱 note: a phone wants tap targets of at
# least 44px, so nav items use btn-sm (32px) only alongside the py padding that
# lifts the hit area — measured in the component table, not assumed.
NAVBAR = "navbar min-h-0 px-0 gap-2 flex-wrap"
# No `flex-nowrap` / `overflow-x-auto`, and the second one is not a style
# preference. The nav holds a `<details>` dropdown whose menu is absolutely
# positioned, and `overflow-x: auto` makes the nav a scroll container — which
# clips it. Screenshotted with the disclosure forced open: the whole 更多 menu
# (9 destinations, including 稽核 and 所有頁面) rendered as nothing at all. It
# looks fine closed, which is how it would have shipped. `flex-nowrap` goes with
# it: it was the pair to the scroller, and the shell's own `flex-wrap: wrap`
# outranks it anyway, so it was never doing anything.
NAV_MENU = "menu menu-horizontal gap-1 px-0"
NAV_LINK = "btn btn-ghost btn-sm font-normal"
NAV_LINK_ACTIVE = "btn btn-ghost btn-sm font-normal btn-active"
NAV_MORE_SUMMARY = "btn btn-ghost btn-sm font-normal"
NAV_MORE_MENU = "menu dropdown-content bg-base-100 rounded-box z-10 w-52 p-2 shadow-md"
FOOTER = "footer footer-center text-base-content/60 p-4 text-xs"

# ── Search ────────────────────────────────────────────────────────────────
# No `input-bordered`: it existed in daisyUI v4 and is gone in v5 (inputs carry
# their border by default). Written from habit, it survived review and was only
# caught by the build-artifact test — the class simply never appears in the CSS
# and nothing anywhere errors.
SEARCH_INPUT = "input input-sm w-full"

# ── Index lists ───────────────────────────────────────────────────────────
# NOT ADOPTED, and the reason is a measurement rather than a preference, so it
# does not need re-litigating: `badge-ghost` paints BOTH `background-color` and
# `border-color` as `--color-base-200`, and BrainHub's mapping points that at
# `--color-bg-section` — which is also `--bg`, the page background. Rendered
# against the real shell and read back with getComputedStyle, the badge came out
# `rgb(250,250,247)` on a `rgb(250,250,247)` page with a `rgb(250,250,247)`
# border. Zero contrast on all three, by construction.
#
# It cannot be fixed from here either: `badge-ghost` and `badge-sm` are the only
# badge classes in the vendored build, so there is no `badge-outline` to reach
# for without a rebuild, and re-colouring it from the shell would mean writing
# the palette a second time — the exact drift vendoring removed.
#
# `.meta-badge` (web_assets) keeps the job: mono, small-caps, a real border. It
# measures `rgb(200,200,188)` against the page, i.e. visible.
# ⚠ Left declared so the class stays in the vendored CSS the shell already
# ships; if it is still unadopted at the next `npm run build`, delete it and let
# the scan shrink.
BADGE_TYPE = "badge badge-ghost badge-sm"

# ── Cards / panels ────────────────────────────────────────────────────────
# The shell's one panel. Worn by the dashboard's sections, the wiki page's
# outline and related-pages footer, and the catalog summary on /all, /artifacts,
# /documents and /search — deliberately the same three classes in all of them,
# because "one system" is something a reader recognises across pages.
#
# ⚠ Adopting a component means DELETING the bespoke rule it replaces, not adding
# the class next to it. This stylesheet is unlayered and daisyUI's is not, so a
# leftover `.thing { border-radius: 4px }` silently outranks `.card` and the
# result is a class name that does nothing. Measured on two candidates that were
# rejected for exactly this: `.button-link` + `btn` and `.catalog-chip` +
# `badge` both moved the element by ≤1px, because the BrainHub rule won every
# property that mattered.
CARD = "card bg-base-100 border border-base-300"
CARD_BODY = "card-body p-4"
CARD_TITLE = "card-title text-base font-light"

# ── Stats ─────────────────────────────────────────────────────────────────
STATS = "stats stats-vertical sm:stats-horizontal w-full bg-base-100 border border-base-300"
STAT = "stat place-items-center py-3"
STAT_VALUE = "stat-value text-2xl font-light"
STAT_TITLE = "stat-title text-xs"

# ── Disclosure (the folded product tour) ──────────────────────────────────
COLLAPSE = "collapse collapse-arrow border border-base-300 bg-base-100"
COLLAPSE_TITLE = "collapse-title text-sm font-normal"
COLLAPSE_CONTENT = "collapse-content text-sm"

# ── Alerts (health page, dashboard staleness banner) ──────────────────────
# The bare component, for the state that must NOT shout. The dashboard banner
# is the case: "資料為新" is the answer nobody needs to act on, and running it in
# `alert-info` blue would give the calm state the same visual weight as the
# warning right next to it — which is how a warning stops being read. It takes
# `--color-base-200` and whatever `--alert-border-color` resolves to, i.e. page
# furniture, and the caller tints it from there.
# Also worn by the decision board's standing scope caveat ("this approval is not
# authorisation for money / publishing / anything irreversible"), which appears
# on every board every time: `alert-warning` there would be a permanent amber
# banner, and a warning that is always on is a warning nobody reads. Bare
# `alert` gives it the panel; its own `color` rule gives it the caution ink.
ALERT = "alert"
ALERT_INFO = "alert alert-info"
ALERT_WARNING = "alert alert-warning"
ALERT_ERROR = "alert alert-error"

# ── Buttons ───────────────────────────────────────────────────────────────
BTN = "btn btn-sm"
BTN_PRIMARY = "btn btn-sm btn-primary"
BTN_GHOST = "btn btn-sm btn-ghost"
# btn-block on phones per the guide's 📱 rule; the sm: prefix drops it on wider
# screens so a row of full-width buttons does not follow the reader to desktop.
BTN_BLOCK_MOBILE = "btn btn-sm btn-block sm:btn-wide"

# ── Tables (wiki content) ─────────────────────────────────────────────────
TABLE = "table table-sm table-zebra"
TABLE_WRAP = "overflow-x-auto"
