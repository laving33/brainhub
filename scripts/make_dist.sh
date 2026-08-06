#!/usr/bin/env bash
# Build the distributable BrainHub package: brainhub-<version>.tar.gz
#
# The tarball is the PRODUCT — it ships with the SO platform. It differs from
# this source checkout in exactly three ways, all enforced below:
#   1. No history, no internals: .git (commit messages name internal projects),
#      .venv, caches, and the aworkr-fleet-only hook installer are excluded.
#   2. Neutral brand: the vendored aworkr logo lockups are excluded and a
#      neutral BrainHub mark ships as vendor/brand-logo.svg (the render
#      pipeline resolves brand-logo.svg first; see render/document.py).
#   3. Nothing else: the tree is otherwise byte-identical to the checkout, so
#      "it passed tests here" means something there.
#
# Usage: scripts/make_dist.sh [output-dir]   (default: ./dist)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT/dist}"
VERSION="$(grep -m1 '^version' "$ROOT/mcp_package/pyproject.toml" | sed 's/.*"\(.*\)"/\1/')"
NAME="brainhub-$VERSION"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# ── 1. stage the tree with exclusions ────────────────────────────────────────
EXCLUDES=(
  --exclude='.git'
  --exclude='.venv'
  --exclude='__pycache__'
  --exclude='.pytest_cache'
  --exclude='.ruff_cache'
  --exclude='dist'
  --exclude='uv.lock'
  --exclude='wire-artifact-intercept.py'          # aworkr-fleet-specific hook installer
  --exclude='mcp_package/brainhub_core/vendor/aworkr-logo-*.svg'
  --exclude='tests/test_brand_assets.py'          # anti-drift gate vs the aworkr brand SSOT; meaningless without that tree
)
mkdir -p "$STAGE/$NAME"
tar -C "$ROOT" -cf - "${EXCLUDES[@]}" . | tar -C "$STAGE/$NAME" -xf -

# ── 2. neutral brand mark ────────────────────────────────────────────────────
cp "$ROOT/logo.svg" "$STAGE/$NAME/mcp_package/brainhub_core/vendor/brand-logo.svg"

# ── 3. gates: refuse to ship internals ───────────────────────────────────────
fail() { echo "GATE FAILED: $1" >&2; exit 1; }

[ -e "$STAGE/$NAME/.git" ] && fail ".git leaked into the package"
find "$STAGE/$NAME" -name 'aworkr-logo-*' | grep -q . && fail "aworkr logo leaked"
[ -f "$STAGE/$NAME/wire-artifact-intercept.py" ] && fail "fleet hook installer leaked"
[ -f "$STAGE/$NAME/mcp_package/brainhub_core/vendor/brand-logo.svg" ] || fail "neutral brand-logo.svg missing"
# Upstream identity may live ONLY in LICENSE, the branding guard, and this
# script (all three must name the token to check for it — the classic
# "grep counts its own pattern" self-match).
LEAKS="$(grep -rli 'gowtham' "$STAGE/$NAME" | grep -v -e '/LICENSE$' -e 'test_brainhub_branding.py$' -e 'make_dist.sh$' || true)"
[ -n "$LEAKS" ] && fail "upstream identity outside LICENSE: $LEAKS"
# Client names must never appear in the product tree.
grep -rliE 'simmpo|bremen' "$STAGE/$NAME" | grep -v 'make_dist.sh$' | grep -q . && fail "client name leaked"

# ── 4. tarball ───────────────────────────────────────────────────────────────
mkdir -p "$OUT_DIR"
tar -C "$STAGE" -czf "$OUT_DIR/$NAME.tar.gz" "$NAME"
echo "Built: $OUT_DIR/$NAME.tar.gz"
tar -tzf "$OUT_DIR/$NAME.tar.gz" | wc -l | xargs -I{} echo "Files: {}"
