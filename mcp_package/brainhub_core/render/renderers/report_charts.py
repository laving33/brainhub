"""Report-chart renderers — brainhub build kinds backed by the vendored
``report_chart`` primitives (SSoT: lab/catalog ``report_chart.py``, ADR-0101).

Each kind maps a JSON spec straight to a self-contained SVG via
``report_chart.<fn>(**spec)`` — the spec's keys ARE the function's kwargs. The
SVG carries its own ``<style>`` + dark-mode media query + light-hex
presentation-attr fallback for print/``--static``, so no per-kind work is needed
here; the shared document layer wraps it into the self-contained artifact.

Naming follows the mainstream/public term first, then our own (owner ruling
2026-07-12). The legacy ``line-chart`` / ``bar-chart`` renderers take a
different spec shape and answer a different question (numeric x axis, grouped
multi-series) — see their modules.

Two things the vendored SVG gets wrong for an artifact, both corrected here in
CSS because the vendored file is a byte-frozen mirror we must not edit:

* **Theme.** Its ``<style>`` themes off ``prefers-color-scheme`` alone, while
  BrainHub's theme is an explicit ``[data-theme]`` attribute the reader sets.
  Toggling the page to dark left every report chart a white block on a dark
  page (verified by screenshot, 2026-08-19).
* **Series slot order.** It bakes its own ``--s1``..``--s8`` in an order that
  differs from the shell's ``--series-1``..``--series-8`` in every slot but the
  first, so the same data drew series 2 green here and orange there. Worse, its
  order fails ``scripts/validate_palette.py`` (adjacent ΔE 12.9 light / 7.8
  dark, both under the 15 floor) while the shell's passes. Re-pointing the
  variables adopts the validated order without touching the mirror.
"""
from __future__ import annotations

from ...vendor import report_chart as rc
from ..registry import RenderPart, RenderRequest, register


def _theme_css() -> str:
    """CSS that re-homes the vendored SVG's variables onto BrainHub's theme.

    The chrome variables point at the SHELL's brand tokens rather than the
    vendored hexes. That fixes two things at once: the chart now follows an
    explicit ``[data-theme]`` switch, and it inherits a brand pack — replacing
    ``tokens.css`` recolours these charts too, which is the whole point of the
    token layer and the one benefit report charts were structurally denied.

    ``rc``'s own constants stay as the fallback inside ``var(…, fallback)``, so
    a page that somehow lacks the shell CSS still renders in the vendored
    colours instead of unstyled.

    Specificity note: the vendored rule is ``svg.viz`` (0,1,1). A selector must
    beat that, and ``.brainhub-report-chart svg.viz`` only ties it — the SVG's
    own inline ``<style>`` comes later in document order and would win. Leading
    with ``:root`` raises it to (0,2,1).
    """
    # vendored variable -> shell token carrying the same meaning.
    mapped = {
        "surface": "--surface",
        "plane": "--bg",
        "ink": "--text",
        "ink2": "--muted",
        "muted": "--subtle",
        "grid": "--border",
        "axis": "--border",
    }
    chrome = ";".join(
        f"--{name}:var({token},{rc._CHROME_LIGHT[name]})" for name, token in mapped.items()
    )
    # Series slots adopt the shell's validated order. The shell defines
    # --series-N per theme, so this needs no light/dark branch either.
    series = ";".join(
        f"--s{i}:var(--series-{i},{rc.CAT_LIGHT[i - 1]})" for i in range(1, 9)
    )
    return f":root .brainhub-report-chart svg.viz{{{chrome};{series}}}"


_HEAD = (
    "<style>"
    ".brainhub-report-chart{margin:0;}"
    ".brainhub-report-chart svg{display:block;max-width:100%;height:auto;}"
    f"{_theme_css()}"
    "</style>"
)

# mainstream kind -> (report_chart fn, description, example spec).
#
# The example is the kind's spec documentation — these field names appear
# nowhere else in the tree, and they are not consistent between kinds
# (labels / x_labels / col_labels / segment_names all name the same idea).
#
# A leading ⚠ marks a form the official `dataviz` skill cautions against — kept
# because it is market-standard (Looker / Whatagraph / AgencyAnalytics) and the
# report gallery requires it, so callers reach for it knowingly.
_KINDS: dict[str, tuple] = {
    "kpi": (
        rc.tile_row,
        "KPI row of stat tiles (value + delta arrow).",
        {"tiles": [{"label": "營收", "value": "1,234"}]},
    ),
    "line": (
        rc.line,
        "Line chart over evenly spaced categories; series are direct-labelled "
        "at their endpoint. For a numeric/irregular x axis use `line-chart`.",
        {"series": [{"name": "營收", "values": [1, 2]}], "x_labels": ["一月", "二月"]},
    ),
    "bar": (
        rc.hbar,
        "Ranked horizontal bar, one measure in one hue (values pre-sorted "
        "upstream). For several series per category use `bar-chart`.",
        {"values": [3, 1], "labels": ["台北", "台中"]},
    ),
    "stacked-bar": (
        rc.stacked_bar,
        "Stacked bar — part-to-whole / composition.",
        {
            "rows": [{"label": "第一季", "segments": [1, 2]}],
            "segment_names": ["新客", "回購"],
        },
    ),
    "heatmap": (
        rc.heatmap,
        "Matrix heatmap (cohort retention, time grids, topic x platform).",
        {
            "rows": [{"label": "第一週", "values": [1, 2]}],
            "col_labels": ["台北", "台中"],
        },
    ),
    "scatter": (
        rc.scatter,
        "Scatter / quadrant (optional median split lines). Single hue: it takes "
        "flat points, not series.",
        {"points": [{"x": 1, "y": 2, "label": "台北"}]},
    ),
    "funnel": (
        rc.funnel,
        "Conversion funnel (ordered stages, optional step rates).",
        {"stages": [{"label": "造訪", "value": 10}, {"label": "成交", "value": 5}]},
    ),
    "donut": (
        rc.donut,
        "Donut share. `values` are SHARES that sum to 1, not raw counts — the "
        "default value_format is percent, so [3, 1] labels a slice '300%'. "
        "⚠ dataviz cautions: part-to-whole prefers stacked-bar and a single "
        "ratio prefers a meter; kept as market-standard — use knowingly.",
        {"values": [0.75, 0.25], "labels": ["直客", "通路"]},
    ),
    "gauge": (
        rc.gauge,
        "Semicircle gauge for a ratio-against-limit. ⚠ dataviz prefers a linear "
        "meter; gauge dials are common but cautioned.",
        {"value": 0.42},
    ),
}

# Exceptions the vendored primitives raise for a malformed spec. CPython turns a
# wrong kwarg into TypeError, a missing dict key inside a row/point into
# KeyError, and a short sequence into IndexError; pipeline.build_document
# documents ValueError as the bad-spec signal, so all three are normalised.
_SPEC_ERRORS = (TypeError, KeyError, IndexError, ValueError)


def _make(kind: str, fn, example: dict):
    expected = ", ".join(sorted(example))

    def render(request: RenderRequest) -> RenderPart:
        spec = dict(request.spec)
        # The caller's --title outranks the spec's. Without this the vendored
        # default wins and the chart draws "Ranked"/"Trend"/"Gauge" while the
        # document is titled something else entirely.
        title = request.title or str(spec.get("title", "") or "") or None
        if title:
            spec["title"] = title
        try:
            svg = fn(**spec)
        except _SPEC_ERRORS as exc:
            detail = f"missing key {exc}" if isinstance(exc, KeyError) else str(exc)
            # Name the kind the caller asked for. The vendored function has a
            # different name (`bar` is `hbar`) and CPython puts that name in the
            # TypeError, which sends people looking for an option that does not
            # exist. The primitives' own messages are written for their author,
            # not the caller, so the expected fields are stated outright.
            detail = detail.replace(f"{fn.__name__}()", f"renderer {kind!r}")
            raise ValueError(
                f"invalid spec for renderer {kind!r}: {detail} "
                f"(expected fields: {expected})"
            ) from exc
        body = f'<figure class="brainhub-report-chart">{svg}</figure>'
        return RenderPart(body=body, head=_HEAD, title=title)

    return render


for _kind, (_fn, _desc, _example) in _KINDS.items():
    register(
        _kind,
        _make(_kind, _fn, _example),
        output_kind="chart",
        description=_desc,
        example=_example,
        # Every report_chart primitive draws its title inside the plot.
        self_titled=True,
    )
