"""Constraints imposed by MCP clients, checked against the real tool definitions.

These are not our rules — they come from the MCP specification and from Claude
Code's documented client limits. Each one is cheap to violate by editing a
docstring, and the symptom is silent: a truncated description or a dropped tool,
with the server still reporting success.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "mcp_package" / "brainhub_mcp" / "server.py"

# Claude Code truncates a tool description and server instructions at 2 KB.
MAX_DESCRIPTION_BYTES = 2048


def _tools(surface: str = "slim") -> list[dict]:
    """List tools over a real stdio session, as a client would see them."""
    with tempfile.TemporaryDirectory() as td:
        wiki = Path(td) / "wiki"
        wiki.mkdir()
        proc = subprocess.Popen(
            [sys.executable, str(SERVER), "--wiki", str(wiki), "--surface", surface],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            def send(payload: dict) -> None:
                proc.stdin.write(json.dumps(payload) + "\n")
                proc.stdin.flush()

            send({
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "compat-test", "version": "1"},
                },
            })
            init = json.loads(proc.stdout.readline())["result"]
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            listed = json.loads(proc.stdout.readline())["result"]["tools"]
            return init, listed
        finally:
            proc.kill()
            proc.wait(timeout=10)
            # Close the pipes explicitly: a killed child leaves them open, and
            # the ResourceWarning fires from whichever test happens to run next.
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()


class ToolDefinitionLimitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.init, cls.tools = _tools()

    def test_no_tool_description_exceeds_the_client_cap(self):
        # bh_build's reached 2,848 bytes when the per-renderer spec shapes were
        # inline in its docstring; a client silently cut off the tail. Long
        # per-argument documentation belongs on the argument.
        oversized = {
            t["name"]: len((t.get("description") or "").encode("utf-8"))
            for t in self.tools
            if len((t.get("description") or "").encode("utf-8")) > MAX_DESCRIPTION_BYTES
        }
        self.assertEqual(oversized, {}, f"descriptions over {MAX_DESCRIPTION_BYTES} bytes")

    def test_no_tool_uses_a_root_level_combinator(self):
        # Claude Code refuses or flattens a root-level anyOf/oneOf/allOf, and a
        # flattened schema stops enforcing `required`. Property-level unions are
        # fine, which is why bh_build's `dict | str` sits on the parameter.
        for tool in self.tools:
            with self.subTest(tool=tool["name"]):
                schema = tool.get("inputSchema") or tool.get("input_schema") or {}
                for keyword in ("anyOf", "oneOf", "allOf"):
                    self.assertNotIn(keyword, schema)

    def test_build_spec_argument_documents_every_renderer(self):
        # The spec's field names exist nowhere else the caller can reach.
        build = next(t for t in self.tools if t["name"] == "bh_build")
        schema = build.get("inputSchema") or build.get("input_schema")
        description = schema["properties"]["spec"].get("description", "")
        sys.path.insert(0, str(ROOT / "mcp_package"))
        from brainhub_core import render

        for kind in render.registry.kinds():
            self.assertIn(kind, description, f"spec help omits {kind!r}")

    def test_spec_accepts_an_object(self):
        # `spec: str` advertised {"type": "string"}, leaving the model no schema
        # for the one argument whose shape it has to get right.
        build = next(t for t in self.tools if t["name"] == "bh_build")
        schema = build.get("inputSchema") or build.get("input_schema")
        spec = schema["properties"]["spec"]
        branches = spec.get("anyOf") or [spec]
        self.assertTrue(
            any(b.get("type") == "object" for b in branches),
            f"spec does not advertise an object form: {spec}",
        )


class StatelessProtocolTests(unittest.TestCase):
    """The 2026-07-28 revision, exercised over a real stdio subprocess.

    Both eras are served, and the client picks: opening with `server/discover`
    gets the stateless protocol, opening with `initialize` gets the handshake
    one. All of this comes from the SDK — no protocol code of ours is involved —
    which is exactly why it is worth a test: an SDK bump could remove it, and
    nothing else here would notice.
    """

    @staticmethod
    def _session(coro):
        import asyncio

        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        async def run():
            with tempfile.TemporaryDirectory() as td:
                wiki = Path(td) / "wiki"
                wiki.mkdir()
                params = StdioServerParameters(
                    command=sys.executable,
                    args=[str(SERVER), "--wiki", str(wiki), "--surface", "slim"],
                )
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        return await coro(session)

        return asyncio.run(run())

    def test_discover_advertises_the_stateless_revision(self):
        result = self._session(lambda s: s.discover())
        self.assertIn("2026-07-28", result.supported_versions)
        self.assertEqual(result.result_type, "complete")

    def test_results_carry_the_revision_s_required_fields(self):
        async def listing(session):
            await session.discover()
            return await session.list_tools()

        result = self._session(listing)
        # resultType is required on every result; ttlMs/cacheScope are required
        # on tools/list via CacheableResult.
        self.assertEqual(result.result_type, "complete")
        self.assertIsNotNone(result.ttl_ms)
        self.assertIn(result.cache_scope, ("public", "private"))
        self.assertTrue(result.tools)

    def test_a_stateless_connection_refuses_the_old_handshake(self):
        async def both(session):
            await session.discover()
            try:
                await session.initialize()
                return None
            except Exception as exc:  # MCPError
                return str(exc)

        message = self._session(both)
        self.assertIsNotNone(message, "initialize should be refused after discover")
        self.assertIn("2026-07-28", message)


class DiscoverabilityTests(unittest.TestCase):
    """Can an agent find out that BrainHub draws charts?

    Three routes carry that fact: the server instructions injected on connect,
    the tool descriptions in tools/list, and the runtime skill's description.
    The instructions named recall, remember, ingest, review and admin and said
    nothing about drawing, so a model asked for "a chart of these numbers" had
    no reason to look — the capability was reachable only by reading the whole
    tool list closely.
    """

    # Words a user actually says, as opposed to "artifact" or "renderer".
    TRIGGERS = ("chart", "diagram")

    @classmethod
    def setUpClass(cls):
        cls.init, cls.tools = _tools()

    def test_server_instructions_advertise_drawing(self):
        instructions = self.init.get("instructions") or ""
        self.assertIn("bh_build", instructions)
        for trigger in self.TRIGGERS:
            self.assertIn(trigger, instructions.lower())

    def test_server_instructions_fit_the_client_cap(self):
        # Claude Code truncates server instructions at 2 KB.
        instructions = self.init.get("instructions") or ""
        self.assertLessEqual(len((instructions).encode("utf-8")), 2048)

    def test_build_tool_description_uses_words_a_user_would_say(self):
        build = next(t for t in self.tools if t["name"] == "bh_build")
        description = (build.get("description") or "").lower()
        for trigger in self.TRIGGERS:
            self.assertIn(trigger, description)

    def test_runtime_skill_description_uses_words_a_user_would_say(self):
        skill = ROOT / "skills" / "46m-bh-runtime" / "SKILL.md"
        description = re.search(
            r"^description:\s*(.+)$", skill.read_text(encoding="utf-8"), re.M
        ).group(1).lower()
        for trigger in self.TRIGGERS:
            self.assertIn(trigger, description)


class HandshakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.init, cls.tools = _tools()

    def test_server_reports_its_version(self):
        # It defaulted to "", so no client log could say which build it was.
        from brainhub_core.version import BRAINHUB_VERSION

        self.assertEqual(self.init["serverInfo"]["version"], BRAINHUB_VERSION)

    def test_server_negotiates_a_dated_protocol_version(self):
        negotiated = self.init["protocolVersion"]
        self.assertRegex(negotiated, r"^\d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
