"""Report-chart renderers — brainhub build kinds backed by the vendored
``report_chart`` primitives (SSoT: lab/catalog ``report_chart.py``, ADR-0101).

Each kind maps a JSON spec straight to a self-contained SVG via
``report_chart.<fn>(**spec)`` — the spec's keys ARE the function's kwargs. The
SVG carries its own ``<style>`` + dark-mode media query + light-hex
presentation-attr fallback for print/``--static``, so no per-kind work is needed
here; the shared document layer wraps it into the self-contained artifact.

Naming follows the mainstream/public term first, then our own (owner ruling
2026-07-12). The legacy ``line-chart`` / ``bar-chart`` renderers use a different
spec shape and are left untouched.
"""
from __future__ import annotations

from ...vendor import report_chart as rc
from ..registry import RenderPart, RenderRequest, register

_HEAD = (
    "<style>"
    ".brainhub-report-chart{margin:0;}"
    ".brainhub-report-chart svg{display:block;max-width:100%;height:auto;}"
    "</style>"
)

# mainstream kind -> (report_chart fn, description). A leading ⚠ marks a form the
# official `dataviz` skill cautions against — kept because it is market-standard
# (Looker / Whatagraph / AgencyAnalytics) and the report gallery requires it, so
# callers reach for it knowingly.
_KINDS: dict[str, tuple] = {
    "kpi":         (rc.tile_row,    "KPI row of stat tiles (value + delta arrow)."),
    "line":        (rc.line,        "Line chart, one or more series over time."),
    "bar":         (rc.hbar,        "Ranked horizontal bar (values pre-sorted upstream)."),
    "stacked-bar": (rc.stacked_bar, "Stacked bar — part-to-whole / composition."),
    "heatmap":     (rc.heatmap,     "Matrix heatmap (cohort retention, time grids, topic x platform)."),
    "scatter":     (rc.scatter,     "Scatter / quadrant (optional median split lines)."),
    "funnel":      (rc.funnel,      "Conversion funnel (ordered stages, optional step rates)."),
    "donut":       (rc.donut,       "Donut share. ⚠ dataviz cautions: part-to-whole prefers stacked-bar and a single ratio prefers a meter; kept as market-standard — use knowingly."),
    "gauge":       (rc.gauge,       "Semicircle gauge for a ratio-against-limit. ⚠ dataviz prefers a linear meter; gauge dials are common but cautioned."),
}


def _make(fn):
    def render(request: RenderRequest) -> RenderPart:
        spec = dict(request.spec)
        title = str(spec.get("title", "") or "") or None
        # spec keys == fn kwargs; report_chart escapes its own text and returns
        # a self-contained <svg> string.
        svg = fn(**spec)
        body = f'<figure class="brainhub-report-chart">{svg}</figure>'
        return RenderPart(body=body, head=_HEAD, title=title)

    return render


for _kind, (_fn, _desc) in _KINDS.items():
    register(_kind, _make(_fn), output_kind="chart", description=_desc)
