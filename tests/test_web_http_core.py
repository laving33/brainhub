import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_package"))

from brainhub_core.web_http import (  # noqa: E402
    ACCEPT_BACKLOG_ENV,
    ARTIFACT_CONTENT_SECURITY_POLICY,
    BROWSER_SOURCE_LOCAL_ONLY,
    BoundedThreadPoolTCPServer,
    CONTENT_SECURITY_POLICY,
    HOST_HEADER_LOCAL_ONLY,
    HOST_HEADER_REQUIRED,
    KEEPALIVE_IDLE_TIMEOUT_ENV,
    LocalRateLimiter,
    MAX_WORKERS_ENV,
    PERMISSIONS_POLICY,
    REQUEST_TIMEOUT_ENV,
    SVG_CONTENT_SECURITY_POLICY,
    ViewerTransportConfig,
    artifact_content_security_policy,
    artifact_security_headers,
    env_bounded_int,
    is_allowed_static_file,
    local_no_store_headers,
    local_security_headers,
    parse_bounded_int,
    parse_frame_ancestors,
    resolve_raw_static_path,
    safe_resolve,
    validate_local_browser_source_headers,
    validate_local_host_header,
    viewer_content_security_policy,
)


class WebHttpCoreTests(unittest.TestCase):
    def test_local_security_headers_include_browser_isolation(self):
        headers = dict(local_security_headers("1"))

        self.assertEqual(headers["X-BrainHub-API-Version"], "1")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["X-DNS-Prefetch-Control"], "off")
        self.assertEqual(headers["X-Permitted-Cross-Domain-Policies"], "none")
        self.assertEqual(headers["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertEqual(headers["Permissions-Policy"], PERMISSIONS_POLICY)
        self.assertEqual(headers["Content-Security-Policy"], CONTENT_SECURITY_POLICY)
        self.assertIn("frame-ancestors 'none'", CONTENT_SECURITY_POLICY)
        self.assertIn("camera=()", PERMISSIONS_POLICY)
        self.assertNotIn("fullscreen=()", PERMISSIONS_POLICY)

    def test_frame_ancestor_allowlist_parses_only_bare_origins(self):
        self.assertEqual(
            parse_frame_ancestors("http://192.168.66.71:23046, https://Portal.Example.com/"),
            ("http://192.168.66.71:23046", "https://portal.example.com"),
        )

        for raw in (
            "",
            None,
            "*",
            "https://*.example.com",
            # A URL, not an origin: the path would be silently ignored by the
            # browser, so an operator who wrote one has the wrong mental model.
            "http://192.168.66.71:23046/page/W9RNRP",
            "192.168.66.71:23046",
            "ftp://example.com",
            "'self'",
        ):
            self.assertEqual(parse_frame_ancestors(raw), (), f"should reject: {raw!r}")

    def test_no_allowlist_leaves_both_policies_byte_identical(self):
        # The opt-in must be invisible when unused: same string, not merely an
        # equivalent one, so an operator diffing headers sees no change.
        self.assertEqual(viewer_content_security_policy(), CONTENT_SECURITY_POLICY)
        self.assertEqual(viewer_content_security_policy(()), CONTENT_SECURITY_POLICY)
        self.assertEqual(artifact_content_security_policy(), ARTIFACT_CONTENT_SECURITY_POLICY)

    def test_allowlist_opens_frame_ancestors_and_retires_x_frame_options(self):
        origins = ("http://192.168.66.71:23046",)
        policy = viewer_content_security_policy(origins)

        self.assertIn("frame-ancestors http://192.168.66.71:23046", policy)
        self.assertNotIn("'none'", policy.split("frame-ancestors")[1])
        # Everything else about the viewer policy is untouched.
        self.assertIn("default-src 'self'", policy)
        self.assertIn("object-src 'none'", policy)

        headers = dict(local_security_headers("1", policy))
        # X-Frame-Options cannot express "this one origin" (ALLOW-FROM is gone
        # from every browser), so leaving DENY behind would contradict the CSP.
        self.assertNotIn("X-Frame-Options", headers)
        self.assertEqual(headers["Content-Security-Policy"], policy)

    def test_allowlist_keeps_the_artifact_gallery_working(self):
        policy = artifact_content_security_policy(("https://portal.example.com",))

        # 'self' stays first: the same-origin gallery frames artifacts today and
        # must keep doing so after an operator opts a portal in.
        self.assertIn("frame-ancestors 'self' https://portal.example.com", policy)
        self.assertIn("sandbox allow-scripts", policy)

        headers = dict(artifact_security_headers("1", policy))
        self.assertNotIn("X-Frame-Options", headers)
        self.assertEqual(headers["Content-Security-Policy"], policy)

    def test_artifact_headers_keep_sameorigin_without_an_allowlist(self):
        headers = dict(artifact_security_headers("1"))

        self.assertEqual(headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn("frame-ancestors 'self'", headers["Content-Security-Policy"])

    def test_local_security_headers_can_use_strict_svg_policy(self):
        headers = dict(local_security_headers("2", SVG_CONTENT_SECURITY_POLICY))

        self.assertEqual(headers["X-BrainHub-API-Version"], "2")
        self.assertEqual(headers["Content-Security-Policy"], SVG_CONTENT_SECURITY_POLICY)
        self.assertIn("script-src 'none'", SVG_CONTENT_SECURITY_POLICY)

    def test_local_no_store_headers_include_legacy_cache_guards(self):
        headers = dict(local_no_store_headers())

        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Pragma"], "no-cache")
        self.assertEqual(headers["Expires"], "0")

    def test_local_rate_limiter_reports_retry_after_window(self):
        now = 100.0

        def clock() -> float:
            return now

        limiter = LocalRateLimiter(max_events=2, window_seconds=10, clock=clock)

        self.assertEqual(limiter.check("127.0.0.1"), (True, 0))
        self.assertEqual(limiter.check("127.0.0.1"), (True, 0))
        self.assertEqual(limiter.check("127.0.0.1"), (False, 10))
        now = 111.0
        self.assertEqual(limiter.check("127.0.0.1"), (True, 0))

    def test_parse_bounded_int_clamps_and_reports_errors(self):
        self.assertEqual(parse_bounded_int("", "limit", 40, 1, 100), (40, None))
        self.assertEqual(parse_bounded_int("250", "limit", 40, 1, 100), (100, None))
        self.assertEqual(parse_bounded_int("0", "limit", 40, 1, 100), (None, "limit must be at least 1"))
        self.assertEqual(parse_bounded_int("bad", "limit", 40, 1, 100), (None, "limit must be an integer"))

    def test_validate_local_host_header_accepts_local_hosts_with_ports(self):
        for host in ("127.0.0.1", "127.0.0.1:3000", "localhost", "localhost:3000"):
            self.assertEqual(validate_local_host_header(host), (True, None))

    def test_validate_local_host_header_rejects_missing_or_remote_hosts(self):
        self.assertEqual(validate_local_host_header(""), (False, HOST_HEADER_REQUIRED))
        self.assertEqual(validate_local_host_header("attacker.example"), (False, HOST_HEADER_LOCAL_ONLY))
        self.assertEqual(validate_local_host_header("localhost.evil.test"), (False, HOST_HEADER_LOCAL_ONLY))
        self.assertEqual(validate_local_host_header("localhost:bad"), (False, HOST_HEADER_LOCAL_ONLY))
        self.assertEqual(validate_local_host_header("localhost attacker"), (False, HOST_HEADER_LOCAL_ONLY))

    def test_validate_local_browser_source_headers_accepts_local_or_missing_sources(self):
        self.assertEqual(validate_local_browser_source_headers("", ""), (True, None))
        self.assertEqual(validate_local_browser_source_headers("http://localhost:3000", ""), (True, None))
        self.assertEqual(validate_local_browser_source_headers("", "http://127.0.0.1:3000/graph"), (True, None))

    def test_validate_local_browser_source_headers_rejects_remote_sources(self):
        self.assertEqual(
            validate_local_browser_source_headers("https://attacker.example", ""),
            (False, BROWSER_SOURCE_LOCAL_ONLY),
        )
        self.assertEqual(
            validate_local_browser_source_headers("", "http://localhost.evil.test/page"),
            (False, BROWSER_SOURCE_LOCAL_ONLY),
        )
        self.assertEqual(validate_local_browser_source_headers("null", ""), (False, BROWSER_SOURCE_LOCAL_ONLY))

    def test_raw_static_resolver_stays_under_raw_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            asset = raw / "asset.png"
            asset.write_bytes(b"png")
            allowed_types = {".png": "image/png"}

            self.assertEqual(
                resolve_raw_static_path(raw, "asset.png", allowed_types),
                (asset.resolve(), "image/png"),
            )
            self.assertEqual(resolve_raw_static_path(raw, "../logo.png", allowed_types), (None, None))
            self.assertEqual(resolve_raw_static_path(raw, "%2e%2e/logo.png", allowed_types), (None, None))
            self.assertEqual(resolve_raw_static_path(raw, "asset.txt", allowed_types), (None, None))

    def test_static_file_allowlist_allows_root_assets_and_raw_media_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            logo = root / "logo.svg"
            image = raw / "image.png"
            note = raw / "note.txt"
            private = root / "serve.py"
            for path in (logo, image, note, private):
                path.write_text("x", encoding="utf-8")

            allowed_types = {".png": "image/png"}
            self.assertTrue(is_allowed_static_file(logo, raw, [logo], allowed_types))
            self.assertTrue(is_allowed_static_file(image, raw, [logo], allowed_types))
            self.assertFalse(is_allowed_static_file(note, raw, [logo], allowed_types))
            self.assertFalse(is_allowed_static_file(private, raw, [logo], allowed_types))

    def test_safe_resolve_handles_malformed_paths(self):
        self.assertIsNone(safe_resolve(Path("bad\0path")))


class ViewerTransportConfigTests(unittest.TestCase):
    def test_defaults_are_sized_for_many_simultaneous_readers(self):
        config = ViewerTransportConfig()
        # socketserver's default backlog of 5 overflows almost immediately, and an
        # overflowed accept queue means dropped SYNs, not an HTTP error.
        self.assertGreaterEqual(config.accept_backlog, 128)
        self.assertGreaterEqual(config.max_workers, 1)
        self.assertGreaterEqual(config.request_timeout_seconds, 1)
        self.assertGreaterEqual(config.keepalive_idle_timeout_seconds, 1)

    def test_every_knob_is_env_overridable(self):
        config = ViewerTransportConfig.from_env({
            ACCEPT_BACKLOG_ENV: "64",
            MAX_WORKERS_ENV: "8",
            REQUEST_TIMEOUT_ENV: "20",
            KEEPALIVE_IDLE_TIMEOUT_ENV: "3",
        })
        self.assertEqual(config.accept_backlog, 64)
        self.assertEqual(config.max_workers, 8)
        self.assertEqual(config.request_timeout_seconds, 20)
        self.assertEqual(config.keepalive_idle_timeout_seconds, 3)

    def test_from_env_falls_back_to_defaults_when_unset(self):
        self.assertEqual(ViewerTransportConfig.from_env({}), ViewerTransportConfig())

    def test_env_bounded_int_prefers_a_working_default_over_failing(self):
        """A typo in a deployment env var should not stop the viewer from booting."""
        for bad in ("", "   ", "not-a-number", "0", "-5", "1.5"):
            with self.subTest(raw=bad):
                self.assertEqual(
                    env_bounded_int("X", 64, 1, 4096, {"X": bad}), 64, f"{bad!r} should fall back"
                )
        self.assertEqual(env_bounded_int("X", 64, 1, 4096, {"X": "8"}), 8)
        # Above the ceiling clamps rather than failing: the kernel would clamp an
        # oversized backlog anyway.
        self.assertEqual(env_bounded_int("X", 64, 1, 100, {"X": "9999"}), 100)


class BoundedThreadPoolTCPServerTests(unittest.TestCase):
    """Behaviour of the pool itself, without going through HTTP.

    A fake handler stands in for finish_request so these stay fast and
    deterministic; the socket is real but nothing is ever accepted on it.
    """

    def _server(self, **transport_kwargs):
        transport = ViewerTransportConfig(**transport_kwargs)

        class _Server(BoundedThreadPoolTCPServer):
            # Bind only; never serve_forever, so no connection is ever accepted.
            def __init__(self, **kwargs):
                self.served = []
                self.release = threading.Event()
                self.started = threading.Semaphore(0)
                super().__init__(("127.0.0.1", 0), None, **kwargs)

            def finish_request(self, request, client_address):
                self.started.release()
                self.release.wait(timeout=5)
                self.served.append(request)

            def shutdown_request(self, request):
                pass

        return _Server(transport=transport)

    def test_backlog_comes_from_the_transport_config(self):
        server = self._server(accept_backlog=64)
        try:
            self.assertEqual(server.request_queue_size, 64)
        finally:
            server.release.set()
            server.server_close()

    def test_worker_count_never_exceeds_the_ceiling(self):
        server = self._server(max_workers=3)
        try:
            for index in range(10):
                server.process_request(index, ("127.0.0.1", 1000 + index))
            # Let the three workers reach finish_request before counting them.
            for _ in range(3):
                self.assertTrue(server.started.acquire(timeout=5), "worker did not start")
            self.assertEqual(server._worker_count, 3, "pool grew past max_workers")
        finally:
            server.release.set()
            server.server_close()

    def test_every_queued_connection_is_still_served_when_saturated(self):
        """Oversubscription must queue, not drop: 10 connections through 2 workers."""
        server = self._server(max_workers=2)
        server.release.set()
        try:
            for index in range(10):
                server.process_request(index, ("127.0.0.1", 1000 + index))
            deadline = time.monotonic() + 5
            while len(server.served) < 10 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(sorted(server.served), list(range(10)))
        finally:
            server.server_close()

    def test_expected_disconnects_do_not_raise_to_the_console(self):
        """Closed tabs and lapsed keep-alives are normal, not errors worth logging."""
        server = self._server()
        server.release.set()
        try:
            for quiet in (BrokenPipeError, ConnectionResetError, TimeoutError):
                with self.subTest(error=quiet.__name__):
                    try:
                        raise quiet()
                    except quiet:
                        # Returns without delegating to the noisy stdlib handler.
                        self.assertIsNone(server.handle_error(None, ("127.0.0.1", 1)))
        finally:
            server.server_close()


if __name__ == "__main__":
    unittest.main()
