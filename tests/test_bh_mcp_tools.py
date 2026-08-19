"""End-to-end tests for the six BrainHub MCP tools (bh_publish / bh_read /
bh_search / bh_link / bh_build / bh_export) exposed by brainhub_mcp/server.py.

The tools are thin wrappers over the SAME engine functions the bh-* CLI verbs
call (wiki_publish.* and brainhub_core.artifact_store.*). These tests import the
server module against a temp BrainHub workspace and invoke each tool handler
directly, asserting:

  * publish -> read round-trips (and republish updates in place);
  * search + link wire documents together;
  * build produces ONE self-contained HTML file (CSP present, zero external
    refs, provenance embedded in the workspace copy);
  * export strips provenance and writes ONLY inside the server-controlled
    artifacts/exports/ dir, rejecting path escapes and unknown handles;
  * the workspace is pinned server-side (no tool takes a workspace/path arg).
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import brainhub

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "mcp_package") not in sys.path:
    sys.path.insert(0, str(ROOT / "mcp_package"))

from mcp_package.brainhub_core import wiki_publish  # noqa: E402


# ── Minimal FastMCP stub so importing the server registers tools as plain
#    callables we can invoke directly (same approach as test_mcp_contract). ──
class _FakeFastMCP:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    def prompt(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    def resource(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    def run(self, transport: str = "stdio") -> None:
        return None


def _install_mcp_stub() -> dict[str, types.ModuleType | None]:
    previous = {
        "mcp": sys.modules.get("mcp"),
        "mcp.server": sys.modules.get("mcp.server"),
        "mcp.server.fastmcp": sys.modules.get("mcp.server.fastmcp"),
    }
    mcp_mod = types.ModuleType("mcp")
    server_mod = types.ModuleType("mcp.server")
    fastmcp_mod = types.ModuleType("mcp.server.fastmcp")
    fastmcp_mod.FastMCP = _FakeFastMCP
    server_mod.fastmcp = fastmcp_mod
    mcp_mod.server = server_mod
    sys.modules["mcp"] = mcp_mod
    sys.modules["mcp.server"] = server_mod
    sys.modules["mcp.server.fastmcp"] = fastmcp_mod
    return previous


def _restore_mcp(previous: dict[str, types.ModuleType | None]) -> None:
    for name, module in previous.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def _import_server(wiki_dir: Path, surface: str = "slim"):
    previous_modules = _install_mcp_stub()
    previous_argv = sys.argv[:]
    module_name = f"bh_mcp_server_{surface}_{id(wiki_dir)}"
    try:
        sys.argv = ["brainhub_mcp.server", "--wiki", str(wiki_dir), "--surface", surface]
        spec = importlib.util.spec_from_file_location(module_name, ROOT / "mcp_package/brainhub_mcp/server.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module, previous_modules, previous_argv, module_name
    except BaseException:
        _restore_mcp(previous_modules)
        sys.argv = previous_argv
        raise


def _teardown_server(module, previous_modules, previous_argv, module_name) -> None:
    if hasattr(module, "_clear_cache"):
        module._clear_cache()
    sys.modules.pop(module_name, None)
    _restore_mcp(previous_modules)
    sys.argv = previous_argv


LINE_SPEC = {
    "title": "Latency",
    "series": [{"name": "p50", "points": [[0, 10], [1, 40], [2, 20], [3, 80]]}],
}


class BhMcpToolTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="bh-mcp-tools-")))
        self.workspace = self._tmp / "brainhub"
        with redirect_stdout(StringIO()):
            self.assertEqual(brainhub.main(["init", str(self.workspace)]), 0)
        self.server, self._prev, self._argv, self._name = _import_server(self.workspace / "wiki", "slim")

    def tearDown(self):
        _teardown_server(self.server, self._prev, self._argv, self._name)

    # ── the pin: no bh_* tool exposes a workspace/path argument ───────────
    def test_no_tool_accepts_a_workspace_or_path_argument(self):
        for name in ("bh_publish", "bh_read", "bh_search", "bh_link", "bh_build", "bh_export"):
            fn = getattr(self.server, name)
            self.assertTrue(callable(fn), name)
            params = set(inspect.signature(fn).parameters)
            self.assertFalse(
                params & {"workspace", "wiki", "path", "target", "root", "abs_path"},
                f"{name} must not accept a caller-controlled workspace/path: {params}",
            )
        # The pin resolves from the launch --wiki arg, not any tool input.
        self.assertEqual(self.server._bh_workspace(), self.workspace)

    # ── publish -> read round-trip + update-in-place ──────────────────────
    def test_publish_read_round_trip_and_update_in_place(self):
        pub = json.loads(self.server.bh_publish(
            "MCP Round Trip", "Body written via bh_publish.", tags="alpha, beta",
        ))
        self.assertTrue(pub["ok"])
        self.assertFalse(pub["updated"])
        handle = wiki_publish.slugify("MCP Round Trip")
        self.assertEqual(pub["handle"], handle)

        read = json.loads(self.server.bh_read(handle))
        self.assertTrue(read["ok"])
        self.assertEqual(read["handle"], handle)
        self.assertIn("Body written via bh_publish.", read["markdown"])

        again = json.loads(self.server.bh_publish("MCP Round Trip", "Second, updated body."))
        self.assertTrue(again["ok"])
        self.assertTrue(again["updated"])
        docs = list((self.workspace / "wiki" / "documents").glob("*.md"))
        self.assertEqual(len(docs), 1, docs)  # updated in place, not copied
        read2 = json.loads(self.server.bh_read(handle))
        self.assertIn("Second, updated body.", read2["markdown"])
        self.assertNotIn("Body written via bh_publish.", read2["markdown"])

    def test_publish_rejects_empty_title(self):
        payload = json.loads(self.server.bh_publish("   ", "body"))
        self.assertFalse(payload["ok"])
        self.assertIn("title", payload["error"])

    def test_read_unknown_handle_fails_loud(self):
        payload = json.loads(self.server.bh_read("no-such-doc"))
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["error"])

    # ── search + link ────────────────────────────────────────────────────
    def test_search_and_link_wire_documents(self):
        self.server.bh_publish("Target Page", "the link target body")
        self.server.bh_publish("Source Page", "a page that will link out")

        hits = json.loads(self.server.bh_search("Target Page"))
        self.assertTrue(hits["ok"])
        self.assertGreaterEqual(hits["count"], 1)
        self.assertIn("target-page", {r["handle"] for r in hits["results"]})

        linked = json.loads(self.server.bh_link("Source Page", "Target Page"))
        self.assertTrue(linked["ok"])
        self.assertTrue(linked["added"])
        source = json.loads(self.server.bh_read("source-page"))
        self.assertIn("[[target-page]]", source["markdown"])

    def test_search_rejects_empty_query(self):
        payload = json.loads(self.server.bh_search("   "))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["count"], 0)

    def test_link_to_missing_target_fails_loud(self):
        self.server.bh_publish("Only Source", "body")
        payload = json.loads(self.server.bh_link("Only Source", "Ghost Target"))
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["error"])

    # ── build: one self-contained file, provenance embedded ───────────────
    def test_build_produces_self_contained_file(self):
        built = json.loads(self.server.bh_build("line-chart", json.dumps(LINE_SPEC), title="Latency"))
        self.assertTrue(built["ok"], built)
        self.assertEqual(built["kind"], "chart")
        self.assertTrue(built["self_contained"])
        self.assertNotIn("path", built)  # absolute server path is not leaked

        stored = self.workspace / built["stored_path"]
        self.assertTrue(stored.is_file(), stored)
        html = stored.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("<svg", html)
        lowered = html.lower()
        for needle in ("http://", "https://", 'src="//', "cdn"):
            self.assertNotIn(needle, lowered)  # zero external requests
        self.assertIn("brainhub:provenance", html)  # workspace copy keeps provenance

    def test_build_rejects_bad_renderer_json_and_spec(self):
        self.assertFalse(json.loads(self.server.bh_build("nope", "{}"))["ok"])
        self.assertFalse(json.loads(self.server.bh_build("line-chart", "{ not json"))["ok"])
        rejected = json.loads(self.server.bh_build("line-chart", json.dumps({"series": []})))
        self.assertFalse(rejected["ok"])  # renderer validates the spec, fail-closed

    # ── export: strip provenance, confine to export dir ───────────────────
    def test_export_strips_provenance_into_export_dir(self):
        built = json.loads(self.server.bh_build("line-chart", json.dumps(LINE_SPEC), title="Export Me"))
        self.assertTrue(built["ok"])

        exported = json.loads(self.server.bh_export(built["filename"], "client-facing.html"))
        self.assertTrue(exported["ok"], exported)
        self.assertEqual(exported["export_path"], "artifacts/exports/client-facing.html")
        self.assertNotIn("target", exported)  # no absolute path leaked

        out = self.workspace / "artifacts" / "exports" / "client-facing.html"
        self.assertTrue(out.is_file())
        text = out.read_text(encoding="utf-8")
        self.assertNotIn("brainhub:provenance", text)  # provenance stripped for the client
        self.assertIn("<!DOCTYPE html>", text)
        self.assertIn("<svg", text)

    def test_export_unknown_handle_fails_loud(self):
        payload = json.loads(self.server.bh_export("never-built", "x.html"))
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["error"])

    def test_export_rejects_path_escaping_filenames(self):
        built = json.loads(self.server.bh_build("line-chart", json.dumps(LINE_SPEC), title="Guard Me"))
        stem = Path(built["stored_path"]).stem
        for bad in ("../escape.html", "sub/dir.html", "/etc/evil.html", "..", "", "a\\b.html"):
            payload = json.loads(self.server.bh_export(stem, bad))
            self.assertFalse(payload["ok"], f"filename {bad!r} must be rejected")
        # Nothing escaped the workspace/export dir.
        self.assertFalse((self._tmp / "escape.html").exists())
        self.assertFalse((self.workspace / "escape.html").exists())
        exports = list((self.workspace / "artifacts" / "exports").glob("*"))
        self.assertEqual(exports, [], exports)

    # ── both surfaces expose the bh_* tools ───────────────────────────────
    def test_tools_present_on_full_surface_too(self):
        full, prev, argv, name = _import_server(self.workspace / "wiki", "full")
        try:
            for tool in ("bh_publish", "bh_read", "bh_search", "bh_link", "bh_build", "bh_export"):
                self.assertTrue(callable(getattr(full, tool)), tool)
        finally:
            _teardown_server(full, prev, argv, name)

    # ── body_file: server-side file path as body, exclusive with body ─────
    def test_publish_body_file_reads_server_side_file(self):
        body_path = self._tmp / "thick-body.md"
        body_path.write_text("Thick body with a zanzibar keyword.\n", encoding="utf-8")

        pub = json.loads(self.server.bh_publish("File Fed", body_file=str(body_path)))
        self.assertTrue(pub["ok"], pub)

        read = json.loads(self.server.bh_read("file-fed"))
        self.assertIn("zanzibar", read["body"])

    def test_publish_body_file_conflicts_and_missing_path_fail_loud(self):
        body_path = self._tmp / "conflict-body.md"
        body_path.write_text("x\n", encoding="utf-8")

        both = json.loads(self.server.bh_publish("Conflict", body="inline", body_file=str(body_path)))
        self.assertFalse(both["ok"])
        self.assertIn("not both", both["error"])

        missing = json.loads(self.server.bh_publish("Conflict", body_file=str(self._tmp / "missing.md")))
        self.assertFalse(missing["ok"])
        self.assertIn("not found", missing["error"])

        neither = json.loads(self.server.bh_publish("Conflict"))
        self.assertFalse(neither["ok"])
        self.assertIn("required", neither["error"])

    # ── sid: publish returns it; read/link accept it; search carries it ───
    def test_sid_flows_through_publish_read_search_link(self):
        pub = json.loads(self.server.bh_publish("Sid Page", "A sid-bearing page body."))
        sid = pub["sid"]
        self.assertEqual(len(sid), 6)
        self.assertTrue(sid.startswith("W"))

        read = json.loads(self.server.bh_read(sid))
        self.assertTrue(read["ok"])
        self.assertEqual(read["handle"], "sid-page")

        hits = json.loads(self.server.bh_search("sid-bearing"))
        self.assertEqual(hits["results"][0]["sid"], sid)

        self.server.bh_publish("Sid Linker", "linker body")
        linked = json.loads(self.server.bh_link("Sid Linker", sid))
        self.assertTrue(linked["ok"])
        self.assertEqual(linked["to_handle"], "sid-page")

    # ── initialize instructions follow the memory_enabled switch ──────────
    def test_instructions_switch_when_memory_layer_disabled(self):
        enabled = self.server._instructions("slim", True)
        self.assertIn("recall", enabled)  # upstream text untouched for enabled workspaces

        disabled = self.server._instructions("slim", False)
        for banned in ("Use recall", "Use remember", "Use review", "Use ingest", "seed_project", "recall_capsule"):
            self.assertNotIn(banned, disabled)
        self.assertIn("bh_search", disabled)
        self.assertIn("disabled", disabled)
        self.assertIn("sid", disabled)

    def test_initialize_instructions_respect_memory_disabled_config(self):
        (self.workspace / "brainhub.config.json").write_text('{"memory_enabled": false}\n', encoding="utf-8")
        server2, prev, argv, name = _import_server(self.workspace / "wiki", "slim")
        try:
            instructions = server2.mcp.kwargs.get("instructions", "")
            self.assertIn("bh_search", instructions)
            self.assertNotIn("Use recall", instructions)
        finally:
            _teardown_server(server2, prev, argv, name)


if __name__ == "__main__":
    unittest.main()
