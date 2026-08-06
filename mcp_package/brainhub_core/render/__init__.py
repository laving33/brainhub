"""BrainHub artifact render subsystem.

Public surface::

    from mcp_package.brainhub_core import render

    render.build_document(kind, spec, static=..., provenance=...)  # -> RenderResult
    render.registry.kinds()                                        # available renderers
    render.strip_provenance(html)                                  # for bh-export

Renderers live in ``render.renderers`` and self-register on import. Importing
this package auto-discovers and imports every module in that subpackage, so any
renderer file dropped in is picked up with no core edit.
"""
from __future__ import annotations

import importlib
import pkgutil

from .document import (
    ARTIFACT_CONTENT_SECURITY_POLICY,
    BRAND_CSS,
    LOGO_SVG,
    STATIC_FLATTEN_CSS,
    flatten_style,
    has_provenance,
    read_vendor,
    render_header,
    strip_provenance,
    wrap_document,
)
from .pipeline import RenderResult, build_document
from .registry import (
    Renderer,
    RendererError,
    RenderPart,
    RenderRequest,
    register,
    registry,
    renderer,
)

__all__ = [
    "ARTIFACT_CONTENT_SECURITY_POLICY",
    "BRAND_CSS",
    "LOGO_SVG",
    "STATIC_FLATTEN_CSS",
    "RenderPart",
    "RenderRequest",
    "RenderResult",
    "Renderer",
    "RendererError",
    "build_document",
    "flatten_style",
    "has_provenance",
    "load_renderers",
    "read_vendor",
    "register",
    "registry",
    "render_header",
    "renderer",
    "strip_provenance",
    "wrap_document",
]


def load_renderers() -> list[str]:
    """Import every module under ``render.renderers`` so they self-register.

    Idempotent and tolerant of an empty renderers package (returns whatever is
    registered). Returns the sorted list of registered renderer kinds.
    """
    from . import renderers as _renderers_pkg

    for module in pkgutil.iter_modules(_renderers_pkg.__path__):
        if module.name.startswith("_"):
            continue
        importlib.import_module(f"{_renderers_pkg.__name__}.{module.name}")
    return registry.kinds()


# Discover renderers on first import of this package.
load_renderers()
