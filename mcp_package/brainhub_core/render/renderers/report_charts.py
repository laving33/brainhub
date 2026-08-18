"""Report-chart renderers — brainhub build kinds backed by the
``chart_primitives`` SVG emitter.

Each kind maps a JSON spec straight to a self-contained SVG via
``report_chart.<fn>(**spec)`` — the spec's keys ARE the function's kwargs. The
SVG carries its own ``<style>`` + dark-mode media query + light-hex
presentation-attr fallback for print/``--static``, so no per-kind work is needed
here; the shared document layer wraps it into the self-contained artifact.

Naming follows the mainstream/public term first, then our own (owner ruling
2026-07-12). The legacy ``line-chart`` / ``bar-chart`` renderers take a
different spec shape and answer a different question (numeric x axis, grouped
multi-series) — see their modules.

The primitives theme off ``prefers-color-scheme`` alone, while BrainHub's theme
is an explicit ``[data-theme]`` attribute the reader sets — so toggling the page
to dark left every report chart a white block on a dark page. The CSS below
re-homes the SVG's variables onto the shell's brand tokens, which fixes that and
also lets a brand pack recolour these charts, something they were structurally
denied while their palette was baked in.
"""
from __future__ import annotations

from .. import chart_primitives as rc
from ..registry import RenderPart, RenderRequest, register
from . import _chart_base


def _rows_from_spec(kind: str, spec: dict) -> tuple[list[str], list[list[str]]]:
    """Pull (headers, rows) out of a spec so the chart's numbers can be tabled.

    Each kind stores its data under different keys, so this is a per-kind read
    rather than something generic — the same reason the spec shapes are
    documented per kind rather than described once.
    """
    def txt(value: object) -> str:
        return _chart_base.fmt_num(value) if isinstance(value, (int, float)) else str(value)

    if kind == "kpi":
        tiles = spec.get("tiles") or []
        return ["項目", "數值"], [[str(t.get("label", "")), txt(t.get("value", ""))] for t in tiles]
    if kind == "line":
        series = spec.get("series") or []
        labels = [str(x) for x in (spec.get("x_labels") or [])]
        headers = ["序列", *labels]
        return headers, [
            [str(s.get("name", "")), *[txt(v) for v in (s.get("values") or [])]]
            for s in series
        ]
    if kind in ("bar", "donut"):
        labels = [str(x) for x in (spec.get("labels") or [])]
        values = spec.get("values") or []
        return ["項目", "數值"], [[a, txt(b)] for a, b in zip(labels, values)]
    if kind == "stacked-bar":
        names = [str(x) for x in (spec.get("segment_names") or [])]
        return ["列", *names], [
            [str(r.get("label", "")), *[txt(v) for v in (r.get("segments") or [])]]
            for r in (spec.get("rows") or [])
        ]
    if kind == "heatmap":
        cols = [str(x) for x in (spec.get("col_labels") or [])]
        return ["列", *cols], [
            [str(r.get("label", "")), *[txt(v) for v in (r.get("values") or [])]]
            for r in (spec.get("rows") or [])
        ]
    if kind == "scatter":
        points = spec.get("points") or []
        return ["標籤", "x", "y"], [
            [str(p.get("label", "")), txt(p.get("x", "")), txt(p.get("y", ""))] for p in points
        ]
    if kind == "funnel":
        stages = spec.get("stages") or []
        return ["階段", "數值"], [[str(s.get("label", "")), txt(s.get("value", ""))] for s in stages]
    if kind == "gauge":
        maximum = spec.get("maximum", 1)
        return ["項目", "數值"], [["值", txt(spec.get("value", ""))], ["上限", txt(maximum)]]
    return [], []


def _theme_css() -> str:
    """CSS that re-homes the SVG's variables onto BrainHub's theme.

    The chrome variables point at the SHELL's brand tokens rather than the
    vendored hexes. That fixes two things at once: the chart now follows an
    explicit ``[data-theme]`` switch, and it inherits a brand pack — replacing
    ``tokens.css`` recolours these charts too, which is the whole point of the
    token layer and the one benefit report charts were structurally denied.

    ``rc``'s own constants stay as the fallback inside ``var(…, fallback)``, so
    a page that somehow lacks the shell CSS still renders in the module's own
    colours instead of unstyled.

    Specificity note: the SVG's own rule is ``svg.viz`` (0,1,1). A selector must
    beat that, and ``.brainhub-report-chart svg.viz`` only ties it — the SVG's
    own inline ``<style>`` comes later in document order and would win. Leading
    with ``:root`` raises it to (0,2,1).
    """
    # primitive variable -> shell token carrying the same meaning.
    mapped = {
        "surface": "--surface",
        "plane": "--bg",
        "ink": "--text",
        "ink2": "--muted",
        "muted": "--subtle",
        "grid": "--border",
        "axis": "--border",
    }
    # Aliased on :root first. Writing `--surface: var(--surface)` directly on the
    # SVG is a CYCLE — a custom property referring to itself on the same element
    # is invalid at computed-value time, and the chart rendered with unresolved
    # colours (a black plate in light mode). The alias breaks the cycle because
    # the two names differ.
    aliases = ";".join(
        f"--bh-chart-{name}:var({token},{rc._CHROME_LIGHT[name]})"
        for name, token in mapped.items()
    )
    chrome = ";".join(f"--{name}:var(--bh-chart-{name})" for name in mapped)
    # Series slots now agree with the shell by construction (CAT_LIGHT was
    # re-seated to match), so this only routes them through the theme layer —
    # a brand pack that redefines --series-N reaches these charts too.
    series = ";".join(
        f"--s{i}:var(--series-{i},{rc.CAT_LIGHT[i - 1]})" for i in range(1, 9)
    )
    return (
        f":root{{{aliases}}}"
        f":root .brainhub-report-chart svg.viz{{{chrome};{series}}}"
    )


_HEAD = (
    "<style>"
    ".brainhub-report-chart{margin:0;}"
    ".brainhub-report-chart svg{display:block;max-width:100%;height:auto;}"
    f"{_theme_css()}"
    f"{_chart_base.DATA_TABLE_CSS}"
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
        "Stacked bar — part-to-whole / composition. `segments` are SHARES, "
        "because value_format defaults to percent: raw counts label a segment "
        "'27100%'. Pass value_format='number' to stack counts instead.",
        {
            "rows": [{"label": "第一季", "segments": [0.6, 0.4]}],
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
        headers, rows = _rows_from_spec(kind, spec)
        table = _chart_base.data_table(headers, rows, caption=title or kind)
        body = f'<figure class="brainhub-report-chart">{svg}{table}</figure>'
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
