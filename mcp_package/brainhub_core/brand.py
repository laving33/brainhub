"""Where the viewer and the renderers get their brand assets from.

BrainHub ships **with** a brand theme rather than being unbranded: the vendored
aworkr palette, lockups and font expectations are the bundled default, and a
deployment that wants its own corporate identity replaces them. What was missing
was a single place to do that replacing.

Before this module the three assets resolved independently — the logo had a
four-level lookup, the fonts had one env var pointing at an absolute path, and the
colour tokens had no override at all. So a deployment could swap its logo and
still render every document in someone else's palette, with nothing to warn it.

One brand pack fixes that. Point ``BRAINHUB_BRAND_DIR`` at a directory:

    my-brand/
      tokens.css      # colour/spacing tokens -- the usual swap point
      logo.svg        # header + document lockup
      daisyui.css     # optional: only if you rebuilt the component sheet
      fonts/          # .woff2 / .ttf faces to embed

Anything the directory does not provide falls back to the per-asset env var, then
to the bundled theme, then to nothing at all. Missing assets never raise: a brand
pack with only ``logo.svg`` in it is a valid brand pack.

Resolution happens when the reading module is imported, matching how the viewer
already loads its stylesheets, so set the variable before starting BrainHub rather
than mid-process.
"""
from __future__ import annotations

import os
from pathlib import Path

BRAND_DIR_ENV = "BRAINHUB_BRAND_DIR"
LOGO_ENV = "BRAINHUB_BRAND_LOGO"
FONTS_ENV = "BRAINHUB_BRAND_FONTS"

# Asset names inside a brand pack.
TOKENS_ASSET = "tokens.css"
LOGO_ASSET = "logo.svg"
DAISY_ASSET = "daisyui.css"
FONTS_ASSET = "fonts"


def brand_dir() -> Path | None:
    """The configured brand pack directory, or None when unset//missing."""
    raw = os.environ.get(BRAND_DIR_ENV, "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def pack_file(asset: str) -> Path | None:
    """A readable file from the brand pack, or None.

    ``asset`` is a bare name from this module's ``*_ASSET`` constants; a value
    containing a path separator is refused rather than allowed to escape the pack.
    """
    if "/" in asset or "\\" in asset or asset in ("", ".", ".."):
        raise ValueError(f"invalid brand asset name: {asset!r}")
    root = brand_dir()
    if root is None:
        return None
    candidate = root / asset
    return candidate if candidate.is_file() else None


def pack_dir(asset: str) -> Path | None:
    """A subdirectory of the brand pack (``fonts/``), or None."""
    if "/" in asset or "\\" in asset or asset in ("", ".", ".."):
        raise ValueError(f"invalid brand asset name: {asset!r}")
    root = brand_dir()
    if root is None:
        return None
    candidate = root / asset
    return candidate if candidate.is_dir() else None


def env_path(name: str) -> Path | None:
    """A path from a per-asset env var, kept for the pre-brand-pack overrides."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def text_asset(asset: str, env_var: str | None = None) -> str | None:
    """Read a text brand asset: brand pack, then per-asset env var, else None.

    Returning None means "the caller should use the bundled default", which is not
    the same as returning "" — an empty override file is a deliberate choice to
    render nothing and is passed through as such.
    """
    for candidate in (pack_file(asset), env_path(env_var) if env_var else None):
        if candidate is None:
            continue
        try:
            return candidate.read_text(encoding="utf-8")
        except OSError:
            continue
    return None


def fonts_dir(bundled_default: Path) -> Path:
    """The directory to embed faces from: brand pack, env var, else the bundled path.

    The bundled path may not exist -- an install with no brand fonts embeds none and
    renders fine -- so this returns a path to try, not a path that is known good.
    """
    return pack_dir(FONTS_ASSET) or env_path(FONTS_ENV) or bundled_default
