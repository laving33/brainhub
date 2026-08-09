#!/usr/bin/env python3
"""Load test the BrainHub local HTTP viewer with many simultaneous readers.

The companion to ``smoke_http_viewer.py``: that one asks "does each endpoint
answer correctly", this one asks "does the server still answer when N people
open it at once".

Each simulated reader fires a burst of parallel requests, which is what a
browser does on page load (document, then the API calls behind it). That burst
pattern -- not the request rate -- is what exhausts a server's accept queue, so
it is the thing worth reproducing.

Connection-level failures are counted separately from HTTP-level ones on
purpose. "The viewer won't connect" is a socket symptom: the kernel drops the
SYN when the accept queue is full and the browser stalls on a retransmit, with
no HTTP status involved anywhere.

    python scripts/loadtest_http_viewer.py --users 30

Exits non-zero if any request fails. On Linux, pair it with the kernel's own
counter to confirm the accept queue is not overflowing::

    nstat -az TcpExtListenOverflows   # before and after; the delta should be 0
"""
from __future__ import annotations

import argparse
import http.client
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# One reader's page-load burst: the document plus what the page pulls in.
BURST_PATHS = (
    "/",
    "/api/status",
    "/graph",
    "/api/graph-summary?q=agent&limit=5",
    "/health",
    "/api/operations",
)


class LoadFailure(RuntimeError):
    pass


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def create_demo(target: Path, python: str) -> None:
    result = subprocess.run(
        [python, str(ROOT / "brainhub_engine.py"), "demo", str(target), "--force"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise LoadFailure(f"demo creation failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")


def wait_until_ready(base_url: str, process: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=2)
            raise LoadFailure(f"server exited with {process.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}")
        try:
            with urllib.request.urlopen(f"{base_url}/api/status", timeout=3) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.1)
    raise LoadFailure("server did not become ready in time")


def one_request(base_url: str, path: str, timeout: float) -> tuple[str, float, str]:
    """Return (outcome, elapsed_seconds, detail) for a single request."""
    start = time.monotonic()
    try:
        with urllib.request.urlopen(f"{base_url}{path}", timeout=timeout) as response:
            response.read()
            return "ok", time.monotonic() - start, str(response.status)
    except urllib.error.HTTPError as exc:
        # The server answered, just not 2xx: an application problem, not a
        # capacity one. Kept in its own bucket so it cannot be mistaken for one.
        try:
            exc.read()
        except Exception:
            pass
        return "http_error", time.monotonic() - start, f"HTTP {exc.code}"
    except (TimeoutError, socket.timeout):
        return "timeout", time.monotonic() - start, "socket timeout"
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return "timeout", time.monotonic() - start, "timeout"
        detail = f"{type(reason).__name__}: {reason}" if not isinstance(reason, str) else reason
        if isinstance(reason, ConnectionRefusedError):
            return "refused", time.monotonic() - start, detail
        if isinstance(reason, ConnectionResetError):
            return "reset", time.monotonic() - start, detail
        return "conn_error", time.monotonic() - start, detail
    except (http.client.RemoteDisconnected, http.client.BadStatusLine) as exc:
        return "reset", time.monotonic() - start, type(exc).__name__
    except Exception as exc:  # noqa: BLE001 -- any failure mode is a data point
        return "other", time.monotonic() - start, f"{type(exc).__name__}: {exc}"


def run_load(base_url: str, users: int, rounds: int, timeout: float) -> dict:
    outcomes: Counter[str] = Counter()
    details: Counter[str] = Counter()
    latencies: list[float] = []

    def reader_burst(_reader: int) -> list[tuple[str, float, str]]:
        with ThreadPoolExecutor(max_workers=len(BURST_PATHS)) as inner:
            futures = [inner.submit(one_request, base_url, path, timeout) for path in BURST_PATHS]
            return [future.result() for future in futures]

    for _round in range(rounds):
        # Every reader starts at once -- the thundering herd is the point.
        with ThreadPoolExecutor(max_workers=users) as outer:
            futures = [outer.submit(reader_burst, reader) for reader in range(users)]
            for future in as_completed(futures):
                for outcome, elapsed, detail in future.result():
                    outcomes[outcome] += 1
                    if outcome == "ok":
                        latencies.append(elapsed)
                    else:
                        details[f"{outcome}: {detail}"] += 1

    return {"outcomes": outcomes, "details": details, "latencies": latencies}


def report(result: dict, users: int, rounds: int) -> int:
    outcomes = result["outcomes"]
    total = sum(outcomes.values())
    ok = outcomes.get("ok", 0)
    latencies = result["latencies"]

    print(f"=== {users} simultaneous readers x {rounds} rounds x {len(BURST_PATHS)} requests = {total} ===")
    print(f"  ok            : {ok}/{total} ({100.0 * ok / total:.1f}%)")
    for outcome, count in sorted(outcomes.items()):
        if outcome != "ok":
            print(f"  {outcome:<14}: {count}")
    if latencies:
        ordered = sorted(latencies)
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        print(
            f"  latency       : median {statistics.median(latencies) * 1000:.0f}ms"
            f"  p95 {p95 * 1000:.0f}ms  max {max(ordered) * 1000:.0f}ms"
        )
    if result["details"]:
        print("  failure detail:")
        for detail, count in result["details"].most_common(8):
            print(f"    {count:>4}x {detail}")

    failures = total - ok
    print(f"  RESULT: {'PASS' if failures == 0 else 'FAIL'} ({failures} failures)")
    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Load test the BrainHub local HTTP viewer.")
    parser.add_argument("--users", type=int, default=30, help="simultaneous readers (default 30)")
    parser.add_argument("--rounds", type=int, default=3, help="burst rounds per reader (default 3)")
    parser.add_argument("--timeout", type=float, default=10.0, help="per-request timeout seconds")
    parser.add_argument("--work-dir", default="", help="directory for the temporary demo workspace")
    parser.add_argument("--python", default=sys.executable, help="Python executable used to run BrainHub")
    args = parser.parse_args()

    if args.users < 1 or args.rounds < 1:
        print("--users and --rounds must be at least 1", file=sys.stderr)
        return 2

    # absolute() rather than resolve(): the interpreter path has to survive the
    # cwd change below, but a venv's bin/python is a symlink to the base
    # interpreter, and resolving it would silently escape the venv and run
    # BrainHub without its dependencies.
    python = str(Path(args.python).expanduser().absolute())
    work_dir = (
        Path(args.work_dir).expanduser().resolve()
        if args.work_dir
        else Path(tempfile.mkdtemp(prefix="brainhub-loadtest-"))
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    demo_target = work_dir / "loadtest-demo"

    try:
        create_demo(demo_target, python)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        process = subprocess.Popen(
            [python, str(ROOT / "serve.py"), "--root", str(demo_target), "--port", str(port)],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_until_ready(base_url, process)
            result = run_load(base_url, args.users, args.rounds, args.timeout)
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
    except LoadFailure as exc:
        print(f"viewer load test failed: {exc}", file=sys.stderr)
        return 1

    return report(result, args.users, args.rounds)


if __name__ == "__main__":
    raise SystemExit(main())
