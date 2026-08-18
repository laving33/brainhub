"""Renderer registry for BrainHub self-contained artifact builds.

A *renderer* turns a small JSON spec into an HTML *body fragment* plus optional
head content (renderer-specific inline ``<style>``/``<script>``). The shared
document layer (:mod:`.document`) wraps that fragment into ONE self-contained
``<!DOCTYPE html>`` file with zero external requests.

Renderers self-register at import time by calling :func:`register` (or using the
:func:`renderer` decorator). Adding a new chart type is a NEW module dropped into
``render/renderers/`` — never an edit to this file. The package ``__init__``
auto-imports every module in that directory so their registrations run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class RenderRequest:
    """Input handed to a renderer's ``render_fn``.

    ``spec`` is the already-parsed JSON object describing what to draw.
    ``static`` requests print/capture mode: renderers must emit their final
    frame with no JS-driven animation so a headless PNG/PDF grab is not blank.
    """

    spec: dict
    static: bool = False
    title: str | None = None


@dataclass
class RenderPart:
    """What a renderer returns: a body fragment plus optional head content.

    The renderer never builds the document shell, the CSP, or the flatten CSS —
    the document layer owns those so every artifact is consistent and no two
    renderers can collide on the wrapper. ``body`` and ``head`` must already be
    safe HTML (renderers escape their own untrusted text).
    """

    body: str
    head: str = ""
    title: str | None = None
    # Optional per-render override of the registered ``output_kind``.
    output_kind: str | None = None
    # Extra provenance the renderer wants recorded in the workspace sidecar.
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Renderer:
    """A registered renderer record."""

    kind: str
    render_fn: Callable[[RenderRequest], RenderPart]
    # Artifact directory bucket for the built file: one of ARTIFACT_DIRECTORIES
    # keys ("chart", "html", "report", "export"). Charts -> "chart", rich
    # interactive pages -> "html".
    output_kind: str = "html"
    # Optional validator: receives the raw spec dict, raises ValueError on bad
    # input. Runs before render_fn so renderers can assume a clean spec.
    input_spec: Callable[[dict], None] | None = None
    description: str = ""
    # A minimal spec that renders. This is the kind's spec documentation: the
    # field names differ per kind (labels / categories / x_labels / col_labels /
    # segment_names all name the same idea somewhere), and nothing else in the
    # tree states them. Callers read it, tests render it, and
    # scripts/check_docs_sync.py fails when a registered kind has none — so the
    # example cannot rot into a different shape than the renderer accepts.
    example: dict = field(default_factory=dict)
    # Does the rendered output draw its own visible title? The document layer
    # suppresses the shell heading only for these, or the artifact ends up with
    # the title twice — or, as shipped before, with neither.
    self_titled: bool = False


class RendererError(ValueError):
    """Raised for unknown renderer kinds or invalid specs."""


class Registry:
    """Process-wide map of renderer kind -> :class:`Renderer`."""

    def __init__(self) -> None:
        self._renderers: dict[str, Renderer] = {}

    def register(self, renderer: Renderer) -> Renderer:
        if not renderer.kind or not isinstance(renderer.kind, str):
            raise RendererError("renderer kind must be a non-empty string")
        if renderer.kind in self._renderers:
            raise RendererError(f"renderer already registered: {renderer.kind!r}")
        if not callable(renderer.render_fn):
            raise RendererError(f"renderer {renderer.kind!r} has no callable render_fn")
        self._renderers[renderer.kind] = renderer
        return renderer

    def get(self, kind: str) -> Renderer:
        try:
            return self._renderers[kind]
        except KeyError:
            available = ", ".join(sorted(self._renderers)) or "(none registered)"
            raise RendererError(f"unknown renderer {kind!r}; available: {available}") from None

    def kinds(self) -> list[str]:
        return sorted(self._renderers)

    def __contains__(self, kind: object) -> bool:
        return kind in self._renderers


# Process-wide singleton. Renderers register against this; the CLI/document
# layer reads from it.
registry = Registry()


def register(
    kind: str,
    render_fn: Callable[[RenderRequest], RenderPart],
    *,
    output_kind: str = "html",
    input_spec: Callable[[dict], None] | None = None,
    description: str = "",
    example: dict | None = None,
    self_titled: bool = False,
) -> Renderer:
    """Register a renderer on the shared singleton. Returns the record."""
    return registry.register(
        Renderer(
            kind=kind,
            render_fn=render_fn,
            output_kind=output_kind,
            input_spec=input_spec,
            description=description,
            example=dict(example or {}),
            self_titled=self_titled,
        )
    )


def renderer(
    kind: str,
    *,
    output_kind: str = "html",
    input_spec: Callable[[dict], None] | None = None,
    description: str = "",
    example: dict | None = None,
    self_titled: bool = False,
) -> Callable[[Callable[[RenderRequest], RenderPart]], Callable[[RenderRequest], RenderPart]]:
    """Decorator form of :func:`register`.

    Usage inside a renderer module::

        from ..registry import renderer, RenderRequest, RenderPart

        @renderer("line-chart", output_kind="chart", description="...")
        def render(request: RenderRequest) -> RenderPart:
            ...
    """

    def decorate(fn: Callable[[RenderRequest], RenderPart]) -> Callable[[RenderRequest], RenderPart]:
        register(
            kind,
            fn,
            output_kind=output_kind,
            input_spec=input_spec,
            description=description,
            example=example,
            self_titled=self_titled,
        )
        return fn

    return decorate
