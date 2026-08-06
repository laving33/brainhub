"""Build pipeline: renderer spec in -> one self-contained HTML document out."""
from __future__ import annotations

from dataclasses import dataclass, field

from .document import wrap_document
from .registry import RenderRequest, registry


@dataclass
class RenderResult:
    """The finished artifact: a full self-contained HTML document + metadata."""

    html: str
    output_kind: str
    title: str
    kind: str
    meta: dict = field(default_factory=dict)


def build_document(
    kind: str,
    spec: dict,
    *,
    title: str | None = None,
    static: bool = False,
    provenance: dict | None = None,
) -> RenderResult:
    """Render ``spec`` with renderer ``kind`` into a self-contained document.

    Raises :class:`~.registry.RendererError` for an unknown kind and
    ``ValueError`` for a spec the renderer rejects. The optional ``provenance``
    dict is embedded (strippable) into the returned HTML for the workspace copy.
    """
    if not isinstance(spec, dict):
        raise ValueError("render spec must be a JSON object (dict)")
    renderer = registry.get(kind)
    if renderer.input_spec is not None:
        renderer.input_spec(spec)
    part = renderer.render_fn(RenderRequest(spec=spec, static=static, title=title))
    doc_title = title or part.title or kind
    output_kind = part.output_kind or renderer.output_kind
    document = wrap_document(
        doc_title,
        part.body,
        head_extra=part.head,
        static=static,
        provenance=provenance,
        # Chart artifacts self-title inside the plot; suppress the shell header
        # title so it is not shown twice (browser <title> still uses doc_title).
        header_title="" if output_kind == "chart" else None,
    )
    return RenderResult(
        html=document,
        output_kind=output_kind,
        title=doc_title,
        kind=kind,
        meta=dict(part.meta),
    )
