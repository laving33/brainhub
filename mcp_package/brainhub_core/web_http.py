"""Shared local HTTP guard and transport helpers for BrainHub's web viewer.

Two layers live here. The guards (host/CSP/path validation, rate limiting) decide
whether a request is allowed; the transport pieces at the bottom decide how many
requests can be in flight at once. Both are shared so ``serve.py`` stays a thin
adapter over them.
"""
from __future__ import annotations

import os
import queue
import socketserver
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping
from urllib.parse import unquote, urlsplit


ALLOWED_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})
HOST_HEADER_REQUIRED = "Host header required"
HOST_HEADER_LOCAL_ONLY = "Host header must be localhost or 127.0.0.1"
BROWSER_SOURCE_LOCAL_ONLY = "Origin/Referer 必須符合本機 BrainHub viewer"
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'"
)
PERMISSIONS_POLICY = (
    "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
    "serial=(), bluetooth=(), accelerometer=(), gyroscope=(), magnetometer=()"
)
SVG_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; "
    "img-src 'self' data:; "
    "style-src 'unsafe-inline'; "
    "script-src 'none'; "
    "object-src 'none'; "
    "sandbox"
)
# Policy for serving a stored, self-contained BrainHub artifact (chart/mermaid/
# interactive HTML). The artifact must run its own inline chart/mermaid scripts,
# so `sandbox allow-scripts` is used instead of a full `sandbox`: allow-scripts
# lets the scripts execute, but the ABSENCE of `allow-same-origin` drops the
# document into a UNIQUE OPAQUE ORIGIN. From that opaque origin the artifact
# cannot read the viewer's cookies/localStorage, cannot make credentialed
# same-origin requests to the viewer's mutation APIs (its Origin becomes
# "null", which the local-action guard rejects), and `connect-src 'none'`
# blocks network egress entirely. `frame-ancestors 'self'` + SAMEORIGIN let the
# same-origin gallery frame it while blocking external embedding.
ARTIFACT_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; "
    "img-src 'self' data:; "
    "style-src 'unsafe-inline'; "
    "script-src 'unsafe-inline'; "
    "font-src data:; "
    "connect-src 'none'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'self'; "
    "sandbox allow-scripts"
)
# Operator opt-in: origins allowed to frame this viewer, e.g. an internal portal
# that shows a BrainHub page beside a conversation. Empty (the default) keeps
# `frame-ancestors 'none'` — nobody may frame the viewer.
FRAME_ANCESTORS_ENV = "BRAINHUB_FRAME_ANCESTORS"


def parse_bounded_int(
    raw: object,
    label: str,
    default: int,
    min_value: int,
    max_value: int,
) -> tuple[int | None, str | None]:
    """Parse a bounded integer query parameter."""
    if raw == "" or raw is None:
        return default, None
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None, f"{label} must be an integer"
    if value < min_value:
        return None, f"{label} must be at least {min_value}"
    return min(value, max_value), None


class LocalRateLimiter:
    """Small in-memory sliding-window limiter for local HTTP mutation APIs."""

    def __init__(
        self,
        max_events: int,
        window_seconds: float,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.max_events = max(1, int(max_events))
        self.window_seconds = max(0.1, float(window_seconds))
        self._clock = clock or time.monotonic
        self._events: dict[str, list[float]] = {}

    def check(self, key: object) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = self._clock()
        key_text = str(key or "local")
        cutoff = now - self.window_seconds
        events = [
            timestamp
            for timestamp in self._events.get(key_text, [])
            if timestamp > cutoff
        ]
        if len(events) >= self.max_events:
            retry_after = max(1, int(round(events[0] + self.window_seconds - now)))
            self._events[key_text] = events
            return False, retry_after
        events.append(now)
        self._events[key_text] = events
        return True, 0


def parse_frame_ancestors(raw: object) -> tuple[str, ...]:
    """Parse the operator's frame-ancestor allowlist into bare origins.

    Deliberately fails closed, unlike :func:`env_bounded_int`: a typo there costs
    a default worker count, a typo here would decide who may frame the viewer. So
    only ``scheme://host[:port]`` survives — a wildcard, a path, a bare host, or a
    non-HTTP scheme is dropped, and a value that drops everything leaves framing
    disabled rather than open.
    """
    origins: list[str] = []
    for token in str(raw or "").replace(",", " ").split():
        candidate = token.strip().rstrip("/")
        if not candidate or "*" in candidate:
            continue
        scheme, separator, rest = candidate.partition("://")
        if not separator or scheme.lower() not in {"http", "https"}:
            continue
        if not rest or "/" in rest:
            continue
        origin = f"{scheme.lower()}://{rest.lower()}"
        if origin not in origins:
            origins.append(origin)
    return tuple(origins)


def _with_frame_ancestors(policy: str, sources: Iterable[str]) -> str:
    """Return ``policy`` with its frame-ancestors source list replaced."""
    replacement = "frame-ancestors " + " ".join(sources)
    directives = [directive.strip() for directive in policy.split(";")]
    return "; ".join(
        replacement if directive.lower().startswith("frame-ancestors") else directive
        for directive in directives
        if directive
    )


def viewer_content_security_policy(frame_ancestors: Iterable[str] = ()) -> str:
    """Viewer CSP, opened to the operator's frame-ancestor allowlist if any."""
    allowed = tuple(frame_ancestors)
    if not allowed:
        return CONTENT_SECURITY_POLICY
    return _with_frame_ancestors(CONTENT_SECURITY_POLICY, allowed)


def artifact_content_security_policy(frame_ancestors: Iterable[str] = ()) -> str:
    """Artifact CSP; the same-origin gallery keeps framing artifacts either way."""
    allowed = tuple(frame_ancestors)
    if not allowed:
        return ARTIFACT_CONTENT_SECURITY_POLICY
    return _with_frame_ancestors(ARTIFACT_CONTENT_SECURITY_POLICY, ("'self'", *allowed))


def frame_options_for_policy(policy: str, default: str = "DENY") -> str | None:
    """Return the X-Frame-Options value matching ``policy``, or None to omit it.

    X-Frame-Options can say "nobody" or "same origin" and nothing else — its
    ALLOW-FROM form was removed from every browser. So once the CSP names an
    origin, the legacy header can only contradict it: browsers that follow the
    CSP spec ignore XFO when frame-ancestors is present, but one that does not
    would block the very embed the operator just allowed. Omitting it leaves a
    single authority for who may frame the page.
    """
    for directive in policy.split(";"):
        name, _, sources = directive.strip().partition(" ")
        if name.lower() != "frame-ancestors":
            continue
        tokens = sources.split()
        if tokens == ["'none'"]:
            return "DENY"
        if tokens == ["'self'"]:
            return "SAMEORIGIN"
        return None
    return default


def local_security_headers(
    api_version: str,
    content_security_policy: str = CONTENT_SECURITY_POLICY,
) -> tuple[tuple[str, str], ...]:
    """Return baseline local-viewer security headers."""
    frame_options = frame_options_for_policy(content_security_policy, "DENY")
    return tuple(
        header
        for header in (
            ("X-BrainHub-API-Version", str(api_version)),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", frame_options) if frame_options else None,
            ("X-DNS-Prefetch-Control", "off"),
            ("X-Permitted-Cross-Domain-Policies", "none"),
            ("Referrer-Policy", "no-referrer"),
            ("Cross-Origin-Resource-Policy", "same-origin"),
            ("Cross-Origin-Opener-Policy", "same-origin"),
            ("Permissions-Policy", PERMISSIONS_POLICY),
            ("Content-Security-Policy", content_security_policy),
        )
        if header is not None
    )


def artifact_security_headers(
    api_version: str,
    content_security_policy: str = ARTIFACT_CONTENT_SECURITY_POLICY,
) -> tuple[tuple[str, str], ...]:
    """Return headers for serving a sandboxed self-contained artifact document.

    Differs from ``local_security_headers`` in two ways, both required so a
    stored chart/mermaid/interactive artifact renders while staying isolated
    from the viewer's origin:

    * ``X-Frame-Options: SAMEORIGIN`` (not DENY) so the same-origin gallery may
      frame it; external framing is still blocked (paired with
      ``frame-ancestors 'self'`` in the CSP). With a frame-ancestor allowlist in
      play the header is omitted instead — see :func:`frame_options_for_policy`.
    * ``Content-Security-Policy: ... sandbox allow-scripts`` so the artifact's
      own inline scripts run inside a unique opaque origin, unable to reach the
      viewer's cookies, storage, or credentialed same-origin APIs.
    """
    frame_options = frame_options_for_policy(content_security_policy, "SAMEORIGIN")
    return tuple(
        header
        for header in (
            ("X-BrainHub-API-Version", str(api_version)),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", frame_options) if frame_options else None,
            ("X-DNS-Prefetch-Control", "off"),
            ("X-Permitted-Cross-Domain-Policies", "none"),
            ("Referrer-Policy", "no-referrer"),
            ("Cross-Origin-Resource-Policy", "same-origin"),
            ("Cross-Origin-Opener-Policy", "same-origin"),
            ("Permissions-Policy", PERMISSIONS_POLICY),
            ("Content-Security-Policy", content_security_policy),
        )
        if header is not None
    )


def local_no_store_headers() -> tuple[tuple[str, str], ...]:
    """Return cache-prevention headers for personal local memory responses."""
    return (
        ("Cache-Control", "no-store"),
        ("Pragma", "no-cache"),
        ("Expires", "0"),
    )


def _host_without_port(host: str) -> str | None:
    if any(char.isspace() for char in host):
        return None
    if host.startswith("["):
        closing = host.find("]")
        if closing < 0:
            return None
        host_name = host[1:closing]
        remainder = host[closing + 1:]
        if remainder:
            if not remainder.startswith(":"):
                return None
            port = remainder[1:]
            if port and not port.isdigit():
                return None
        return host_name
    if host.count(":") == 1:
        host_name, port = host.rsplit(":", 1)
        if port and not port.isdigit():
            return None
        return host_name
    if ":" in host:
        return None
    return host


def validate_local_host_header(
    host_header: object,
    allowed_hosts: Iterable[str] = ALLOWED_LOCAL_HOSTS,
) -> tuple[bool, str | None]:
    """Validate a local-only Host header for the unauthenticated viewer."""
    host = str(host_header or "").strip().lower()
    if not host:
        return False, HOST_HEADER_REQUIRED
    host_name = _host_without_port(host)
    if host_name in set(allowed_hosts):
        return True, None
    return False, HOST_HEADER_LOCAL_ONLY


def _browser_source_host(header_value: object) -> str | None:
    value = str(header_value or "").strip().lower()
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return _host_without_port(parsed.netloc) or ""


def validate_local_browser_source_headers(
    origin_header: object,
    referer_header: object,
    allowed_hosts: Iterable[str] = ALLOWED_LOCAL_HOSTS,
) -> tuple[bool, str | None]:
    """Allow browser-supplied Origin/Referer only from the local viewer."""
    allowed = set(allowed_hosts)
    for header_value in (origin_header, referer_header):
        host = _browser_source_host(header_value)
        if host is None:
            continue
        if host not in allowed:
            return False, BROWSER_SOURCE_LOCAL_ONLY
    return True, None


def safe_resolve(path: Path) -> Path | None:
    """Resolve a path, returning None for malformed filesystem inputs."""
    if "\0" in str(path):
        return None
    try:
        return path.resolve()
    except (OSError, ValueError):
        return None


def is_relative_to(path: Path, root: Path) -> bool:
    """Return whether path stays under root after both paths are resolved."""
    resolved_path = safe_resolve(path)
    resolved_root = safe_resolve(root)
    if not resolved_path or not resolved_root:
        return False
    try:
        resolved_path.relative_to(resolved_root)
        return True
    except ValueError:
        return False


def is_allowed_static_file(
    path: Path,
    raw_dir: Path,
    root_files: Iterable[Path],
    raw_static_types: Mapping[str, str],
) -> bool:
    """Check whether a static file is an allowed root asset or raw media file."""
    resolved_path = safe_resolve(path)
    resolved_raw_dir = safe_resolve(raw_dir)
    if not resolved_path or not resolved_raw_dir:
        return False
    allowed_root_files = {
        resolved
        for root_file in root_files
        if (resolved := safe_resolve(root_file)) is not None
    }
    return resolved_path in allowed_root_files or (
        is_relative_to(resolved_path, resolved_raw_dir)
        and resolved_path.suffix.lower() in raw_static_types
    )


def resolve_raw_static_path(
    raw_dir: Path,
    url_fragment: object,
    raw_static_types: Mapping[str, str],
) -> tuple[Path | None, str | None]:
    """Resolve a /raw/ URL fragment to an allowed local file and MIME type."""
    decoded = unquote(str(url_fragment or "")).lstrip("/")
    resolved_raw_dir = safe_resolve(raw_dir)
    resolved = safe_resolve(raw_dir / decoded)
    if not resolved_raw_dir or not resolved or not is_relative_to(resolved, resolved_raw_dir):
        return None, None
    content_type = raw_static_types.get(resolved.suffix.lower())
    if not content_type:
        return None, None
    return resolved, content_type


# ---------------------------------------------------------------------------
# Transport sizing: how many readers the local viewer can serve at once.
#
# The stdlib defaults are wrong for this traffic shape in two ways, and both
# show up as "the viewer won't connect" rather than as an HTTP error:
#
# * ``socketserver`` gives the accept queue 5 slots. One page view opens a burst
#   of parallel connections, so a handful of simultaneous readers overflows it,
#   and an overflowed queue means the kernel silently drops the SYN -- the
#   browser then stalls on a ~1s retransmit with no status code anywhere.
# * ``BaseHTTPRequestHandler`` speaks HTTP/1.0, so the socket closes after every
#   response and one page view costs a fresh connection per request.
#
# Measured with 30 simultaneous readers: the defaults dropped 896 SYNs and failed
# 34% of requests; the values below dropped none and failed none.
# ---------------------------------------------------------------------------

ACCEPT_BACKLOG_ENV = "BRAINHUB_ACCEPT_BACKLOG"
MAX_WORKERS_ENV = "BRAINHUB_MAX_WORKERS"
REQUEST_TIMEOUT_ENV = "BRAINHUB_REQUEST_TIMEOUT"
KEEPALIVE_IDLE_TIMEOUT_ENV = "BRAINHUB_KEEPALIVE_IDLE_TIMEOUT"


def env_bounded_int(
    name: str,
    default: int,
    min_value: int,
    max_value: int,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Read a bounded integer from the environment, ignoring anything unusable.

    Deliberately total: an operator who exports a typo gets the default and a
    working viewer, not a server that refuses to boot. Shares
    :func:`parse_bounded_int` with the query-parameter path so "what counts as a
    valid bounded int" is defined once.
    """
    source = os.environ if environ is None else environ
    raw = source.get(name, "")
    if isinstance(raw, str):
        raw = raw.strip()
    value, error = parse_bounded_int(raw, name, default, min_value, max_value)
    if error is not None or value is None:
        return default
    return value


@dataclass(frozen=True)
class ViewerTransportConfig:
    """Socket-layer sizing for the local viewer, overridable per deployment.

    Every field is a ceiling or a timeout rather than a behaviour switch, so a
    larger deployment scales by raising numbers instead of taking a different
    code path.
    """

    accept_backlog: int = 512
    max_workers: int = 128
    request_timeout_seconds: int = 15
    keepalive_idle_timeout_seconds: int = 5

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ViewerTransportConfig:
        defaults = cls()
        return cls(
            # A queue depth, so unused slots cost nothing; the ceiling stays under
            # the usual net.core.somaxconn of 4096, above which the kernel would
            # silently clamp it anyway.
            accept_backlog=env_bounded_int(
                ACCEPT_BACKLOG_ENV, defaults.accept_backlog, 8, 4096, environ
            ),
            # One worker serves one connection at a time, so this bounds
            # concurrent *connections*, not readers: a reader's page-load burst
            # reuses its keep-alive connections instead of adding workers.
            # Measured peak was ~75 workers for 50 simultaneous readers.
            max_workers=env_bounded_int(
                MAX_WORKERS_ENV, defaults.max_workers, 1, 4096, environ
            ),
            request_timeout_seconds=env_bounded_int(
                REQUEST_TIMEOUT_ENV, defaults.request_timeout_seconds, 1, 600, environ
            ),
            # Long enough to cover a browser's page-load burst, short enough that
            # workers recycle instead of one being parked per open tab.
            keepalive_idle_timeout_seconds=env_bounded_int(
                KEEPALIVE_IDLE_TIMEOUT_ENV, defaults.keepalive_idle_timeout_seconds, 1, 600, environ
            ),
        )


class BoundedThreadPoolTCPServer(socketserver.TCPServer):
    """Concurrent TCP server whose worker count has a ceiling.

    ``ThreadingMixIn`` is the usual way to get concurrency here, but it spawns one
    thread per connection with no limit, so a burst of readers -- or one client
    holding connections open -- grows the thread count without bound. This serves
    connections from a pool instead: predictable memory and scheduling, and the
    deep accept backlog absorbs anything that arrives while every worker is busy.

    Subclasses supply :attr:`transport`; ``allow_reuse_address`` and
    ``daemon_threads`` keep the restart-friendly behaviour of the stdlib servers.
    """

    daemon_threads = True
    allow_reuse_address = True
    transport = ViewerTransportConfig()

    def __init__(self, *args, transport: ViewerTransportConfig | None = None, **kwargs):
        if transport is not None:
            self.transport = transport
        # TCPServer.__init__ binds and listens, reading request_queue_size as it
        # goes, so the backlog has to be in place before we call up.
        self.request_queue_size = self.transport.accept_backlog
        self._pending: queue.SimpleQueue = queue.SimpleQueue()
        self._pool_lock = threading.Lock()
        self._worker_count = 0
        self._idle_workers = 0
        super().__init__(*args, **kwargs)

    @property
    def max_workers(self) -> int:
        return self.transport.max_workers

    def process_request(self, request, client_address):
        """Hand the connection to the pool instead of spawning a thread for it.

        A worker is added only when every existing one is busy, so a quiet server
        keeps a couple of threads while a busy one grows to the ceiling and stops.
        Connections arriving with the pool saturated wait in the queue rather than
        being refused.
        """
        with self._pool_lock:
            spawn = self._idle_workers == 0 and self._worker_count < self.max_workers
            if spawn:
                self._worker_count += 1
        self._pending.put((request, client_address))
        if spawn:
            threading.Thread(target=self._worker_loop, daemon=self.daemon_threads).start()

    def _worker_loop(self) -> None:
        # Workers live for the server's lifetime once created. Retiring them on an
        # idle timer would race with process_request's decision not to spawn (it
        # may have just counted this worker as available), and the losing outcome
        # is a connection parked in the queue with nobody left to serve it. Idle
        # threads are cheap; a stranded reader is not.
        while True:
            with self._pool_lock:
                self._idle_workers += 1
            item = self._pending.get()
            with self._pool_lock:
                self._idle_workers -= 1
            if item is None:
                with self._pool_lock:
                    self._worker_count -= 1
                return
            request, client_address = item
            try:
                self.finish_request(request, client_address)
            except Exception:
                self.handle_error(request, client_address)
            finally:
                self.shutdown_request(request)

    def handle_error(self, request, client_address):
        """Stay quiet about the ways a browser normally goes away.

        Readers close tabs mid-response and keep-alive connections lapse. At one
        traceback each that noise would bury a real error.
        """
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, TimeoutError)):
            return
        super().handle_error(request, client_address)

    def server_close(self):
        # Release the workers before the socket goes away, so a server restarted
        # in the same process does not leave them parked on a dead queue.
        with self._pool_lock:
            parked = self._worker_count
        for _ in range(parked):
            self._pending.put(None)
        super().server_close()
