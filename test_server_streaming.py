"""
test_server_streaming.py — TDD RED scaffold for the Phase 1 server streaming API.

These tests target /api/turn, /api/stream/<id>, server._BRAIN_FACTORY, and the
Origin check — none of which exist yet. Running this file produces RED failures.
Plans 01-02 and 01-03 will make this suite GREEN.

Python 3.9 compatible (no match, no X|Y unions, no str.removeprefix).
Timings: MockBrain sleeps ~0.3s; non-blocking assertions use < 1.0s budget.
"""

from __future__ import annotations

import http.client
import json
import threading
import time

import pytest

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

HOST = "127.0.0.1"

# MockBrain delay — generous enough to detect non-blocking behavior.
# The POST /api/turn must return in < 1.0s EVEN THOUGH think_stream sleeps this long.
MOCK_BRAIN_DELAY = 0.3  # seconds

# Maximum allowed text length: plan contract from 01-VALIDATION.md (SEC-01 DoS guard).
MAX_TEXT_LEN = 10_000


# ---------------------------------------------------------------------------
# MockBrain — in-process substitute for the real Brain class.
# Server tests must never spawn the real `claude` CLI.
# ---------------------------------------------------------------------------


class MockBrain:
    """Mock brain for server integration tests.

    Attributes match the interface server.py will depend on after Phase 1:
      - session_id: str | None
      - computer_use: bool
      - _lock: threading.Lock  (per-Brain serialization, Pitfall 4 in 01-RESEARCH.md)
      - think_stream(text): generator yielding ActivityEvent dicts
      - think(text): blocking str result (keeps /api/ask working)

    Class-level counters track concurrent active think_stream calls so
    test_concurrent_turns_serialize and test_different_sessions_parallel
    can assert the expected serialization / parallelism behaviour.
    """

    # Class-level concurrency tracking (reset via reset_counters() before each test)
    _counter_lock = threading.Lock()
    _active_count = 0
    _max_active = 0

    def __init__(self):
        self.session_id = None
        self.computer_use = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # think() — kept so /api/ask continues to work during transition
    # ------------------------------------------------------------------

    def think(self, text):  # noqa: D401
        return "ok"

    # ------------------------------------------------------------------
    # think_stream() — yields three events after a short configurable sleep
    # ------------------------------------------------------------------

    def think_stream(self, text):
        with MockBrain._counter_lock:
            MockBrain._active_count += 1
            if MockBrain._active_count > MockBrain._max_active:
                MockBrain._max_active = MockBrain._active_count
        try:
            time.sleep(MOCK_BRAIN_DELAY)
            yield {"type": "text", "text": "working"}
            yield {"type": "result", "text": "done"}
            yield {"type": "done"}
        finally:
            with MockBrain._counter_lock:
                MockBrain._active_count -= 1

    # ------------------------------------------------------------------
    # Helpers for overlap-detection tests
    # ------------------------------------------------------------------

    @classmethod
    def reset_counters(cls):
        with cls._counter_lock:
            cls._active_count = 0
            cls._max_active = 0

    @classmethod
    def get_max_active(cls):
        with cls._counter_lock:
            return cls._max_active


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def live_server():
    """Spin up the real server.Handler on an ephemeral port in a daemon thread.

    Injects MockBrain via server._BRAIN_FACTORY (the testability hook that
    Plan 01-03 adds). That attribute does not exist yet, so this fixture sets
    it as a new module-level attribute — safe in Python, ignored by the current
    Handler until Plan 01-03 wires it in.

    Yields: (host: str, port: int)
    Teardown: httpd.shutdown() stops the daemon thread.
    """
    import server
    from http.server import ThreadingHTTPServer

    # Save original factory (likely absent; will be AttributeError-safe)
    _sentinel = object()
    original_factory = getattr(server, "_BRAIN_FACTORY", _sentinel)

    # Inject mock brain factory — Plan 01-03 Handler uses this instead of Brain()
    server._BRAIN_FACTORY = MockBrain

    # Start server on ephemeral port 0; OS assigns the actual port
    httpd = ThreadingHTTPServer((HOST, 0), server.Handler)
    _, port = httpd.server_address  # get the OS-assigned port

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    yield HOST, port

    httpd.shutdown()

    # Restore original module state
    if original_factory is _sentinel:
        try:
            delattr(server, "_BRAIN_FACTORY")
        except AttributeError:
            pass
    else:
        server._BRAIN_FACTORY = original_factory


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------


def post_turn(conn, body, origin=None):
    """POST /api/turn with an optional Origin header.

    body: dict to JSON-encode as request body.
    origin: if provided, sets the Origin header (used for SEC-01 tests).
    Returns: (status_code: int, response_body: dict)
    """
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(payload)),
    }
    if origin is not None:
        headers["Origin"] = origin
    conn.request("POST", "/api/turn", body=payload, headers=headers)
    resp = conn.getresponse()
    status = resp.status
    try:
        data = json.loads(resp.read())
    except Exception:
        data = {}
    return status, data


def read_sse(host, port, path, read_timeout=5.0):
    """Open a GET SSE connection and collect all lines until the stream closes.

    Returns: (status_code: int, lines: list[str])
    Lines include raw SSE protocol lines ("data: ...", "event: done", etc.).
    """
    conn = http.client.HTTPConnection(host, port, timeout=read_timeout)
    conn.request("GET", path)
    resp = conn.getresponse()
    if resp.status != 200:
        resp.read()
        conn.close()
        return resp.status, []
    # Read until connection closes (SSE stream ends after MockBrain is done)
    raw = resp.read().decode("utf-8", errors="replace")
    conn.close()
    lines = [ln for ln in raw.splitlines() if ln]
    return 200, lines


# ---------------------------------------------------------------------------
# Tests — names match VALIDATION.md -k filter slugs exactly.
# All fail RED until server.py gains /api/turn + /api/stream/<id> + Origin check.
# ---------------------------------------------------------------------------


def test_turn_nonblocking(live_server):
    """POST /api/turn returns immediately (<1s) while MockBrain sleeps MOCK_BRAIN_DELAY.

    VALIDATION.md CORE-01: POST /api/turn returns immediately even while brain runs.
    """
    host, port = live_server
    conn = http.client.HTTPConnection(host, port, timeout=5)

    start = time.monotonic()
    status, data = post_turn(conn, {"text": "hi", "session_token": "s1"})
    elapsed = time.monotonic() - start

    conn.close()

    assert status == 200, f"POST /api/turn expected 200, got {status}"
    assert "job_id" in data, f"Response must contain 'job_id', got: {data}"
    assert elapsed < 1.0, f"POST /api/turn took {elapsed:.3f}s (must be < 1.0s non-blocking)"


def test_concurrent_request_not_blocked(live_server):
    """GET /api/health returns 200 in <1s while a turn is mid-flight.

    VALIDATION.md CORE-01: second request not blocked by active turn.
    """
    host, port = live_server

    # Start a turn (will block internally for MOCK_BRAIN_DELAY)
    turn_conn = http.client.HTTPConnection(host, port, timeout=5)
    turn_payload = json.dumps({"text": "hi", "session_token": "s1"}).encode()
    turn_conn.request("POST", "/api/turn", body=turn_payload,
                      headers={"Content-Type": "application/json",
                               "Content-Length": str(len(turn_payload))})

    # Immediately check health — must not be blocked by the in-flight turn
    health_conn = http.client.HTTPConnection(host, port, timeout=5)
    health_start = time.monotonic()
    health_conn.request("GET", "/api/health")
    health_resp = health_conn.getresponse()
    health_resp.read()
    health_elapsed = time.monotonic() - health_start
    health_conn.close()

    turn_resp = turn_conn.getresponse()
    turn_resp.read()
    turn_conn.close()

    assert health_resp.status == 200, f"/api/health expected 200, got {health_resp.status}"
    assert health_elapsed < 1.0, (
        f"/api/health took {health_elapsed:.3f}s while turn in-flight (must be < 1.0s)"
    )


def test_sse_events_incremental(live_server):
    """GET /api/stream/<job_id> receives >=2 data: lines and one event: done line.

    VALIDATION.md CORE-02: GET /api/stream/<id> receives multiple data: events before done.
    """
    host, port = live_server

    # Start a turn and grab the job_id
    conn = http.client.HTTPConnection(host, port, timeout=5)
    status, data = post_turn(conn, {"text": "hi", "session_token": "s1"})
    conn.close()

    assert status == 200, f"POST /api/turn expected 200, got {status}"
    job_id = data.get("job_id")
    assert job_id, f"Response must contain non-empty job_id, got: {data}"

    # Open the SSE stream and collect lines
    sse_status, lines = read_sse(host, port, f"/api/stream/{job_id}")

    assert sse_status == 200, f"GET /api/stream/{job_id} expected 200, got {sse_status}"

    data_lines = [ln for ln in lines if ln.startswith("data:")]
    done_lines = [ln for ln in lines if "event: done" in ln or ln == "event: done"]

    assert len(data_lines) >= 2, (
        f"Expected >=2 data: lines from SSE stream, got: {data_lines}"
    )
    assert done_lines, f"Expected 'event: done' line in SSE stream, got lines: {lines}"


def test_origin_check_post(live_server):
    """POST /api/turn with a foreign Origin header must return 403.

    VALIDATION.md SEC-01: CSRF/DNS-rebinding defence on POST endpoint.
    Pattern from 01-RESEARCH.md Pattern 4 (Origin check).
    """
    host, port = live_server
    conn = http.client.HTTPConnection(host, port, timeout=5)

    status, _data = post_turn(
        conn,
        {"text": "hi", "session_token": "s1"},
        origin="http://evil.com",
    )
    conn.close()

    assert status == 403, (
        f"POST /api/turn with foreign Origin expected 403, got {status}"
    )


def test_origin_check_get(live_server):
    """GET /api/stream/<id> with a foreign Origin header must return 403.

    VALIDATION.md SEC-01: Origin check applies to GET SSE endpoint too.
    """
    host, port = live_server
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request("GET", "/api/stream/anyid",
                 headers={"Origin": "http://evil.com"})
    resp = conn.getresponse()
    status = resp.status
    resp.read()
    conn.close()

    assert status == 403, (
        f"GET /api/stream/<id> with foreign Origin expected 403, got {status}"
    )


def test_origin_check_no_header(live_server):
    """POST /api/turn with NO Origin header must NOT return 403.

    VALIDATION.md SEC-01: same-origin / no-Origin requests pass through.
    Pattern from 01-RESEARCH.md: 'if origin and origin not in _ALLOWED_ORIGINS'
    passes when origin == "" (direct curl, no header).
    """
    host, port = live_server
    conn = http.client.HTTPConnection(host, port, timeout=5)

    # Explicitly do NOT set an Origin header
    status, _data = post_turn(conn, {"text": "hi", "session_token": "s1"}, origin=None)
    conn.close()

    assert status != 403, (
        f"POST /api/turn with no Origin header must not return 403, got {status}"
    )


def test_length_cap(live_server):
    """POST /api/turn with text > 10_000 chars must return 400.

    VALIDATION.md SEC-01 / DoS guard from 01-RESEARCH.md security domain.
    """
    host, port = live_server
    conn = http.client.HTTPConnection(host, port, timeout=5)

    long_text = "x" * (MAX_TEXT_LEN + 1)  # 10_001 chars — exceeds cap
    status, _data = post_turn(conn, {"text": long_text, "session_token": "s1"})
    conn.close()

    assert status == 400, (
        f"POST /api/turn with text > {MAX_TEXT_LEN} chars expected 400, got {status}"
    )


def test_concurrent_turns_serialize(live_server):
    """Two turns on the same session_token must NOT overlap (max concurrency == 1).

    VALIDATION.md CORE-03: concurrent turns on same session_token serialize.
    Pitfall 4 from 01-RESEARCH.md: concurrent claude processes fight over MCP stdio pipe.
    """
    host, port = live_server
    MockBrain.reset_counters()

    results = {}  # thread_name -> (status, data)
    errors = {}

    def fire_turn(name):
        try:
            conn = http.client.HTTPConnection(host, port, timeout=10)
            status, data = post_turn(conn, {"text": "hi", "session_token": "same-session"})
            conn.close()

            job_id = data.get("job_id", "")
            if job_id:
                _sse_status, lines = read_sse(host, port, f"/api/stream/{job_id}")
            else:
                lines = []
            results[name] = (status, lines)
        except Exception as exc:
            errors[name] = exc

    t1 = threading.Thread(target=fire_turn, args=("t1",))
    t2 = threading.Thread(target=fire_turn, args=("t2",))
    t1.start()
    # Small gap to ensure t1 starts first — still "near-simultaneous"
    time.sleep(0.05)
    t2.start()

    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not errors, f"Threads raised exceptions: {errors}"

    # Both turns must complete with 200 and valid job_ids
    for name, (status, lines) in results.items():
        assert status == 200, f"Turn {name} expected 200, got {status}"
        done_lines = [ln for ln in lines if "event: done" in ln]
        assert done_lines, f"Turn {name} SSE stream never reached event: done"

    # The two think_stream() calls must not have overlapped (max active == 1)
    max_active = MockBrain.get_max_active()
    assert max_active <= 1, (
        f"Concurrent turns on same session_token must serialize (max active == 1), "
        f"observed max_active == {max_active}"
    )


def test_different_sessions_parallel(live_server):
    """Two turns on DIFFERENT session_tokens must overlap (max concurrency == 2).

    VALIDATION.md CORE-03: different sessions do not cross-block (parallel execution).
    Pattern from 01-RESEARCH.md Pattern 2 (SessionStore): per-session Brain locks
    only serialize within a session; cross-session turns are fully parallel.
    """
    host, port = live_server
    MockBrain.reset_counters()

    results = {}
    errors = {}

    def fire_turn(name, session_token):
        try:
            conn = http.client.HTTPConnection(host, port, timeout=10)
            status, data = post_turn(
                conn, {"text": "hi", "session_token": session_token}
            )
            conn.close()

            job_id = data.get("job_id", "")
            if job_id:
                _sse_status, lines = read_sse(host, port, f"/api/stream/{job_id}")
            else:
                lines = []
            results[name] = (status, lines)
        except Exception as exc:
            errors[name] = exc

    t1 = threading.Thread(target=fire_turn, args=("t1", "session-A"))
    t2 = threading.Thread(target=fire_turn, args=("t2", "session-B"))
    t1.start()
    t2.start()  # start immediately — no gap

    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not errors, f"Threads raised exceptions: {errors}"

    # Both turns must complete with 200 and event: done
    for name, (status, lines) in results.items():
        assert status == 200, f"Turn {name} expected 200, got {status}"
        done_lines = [ln for ln in lines if "event: done" in ln]
        assert done_lines, f"Turn {name} SSE stream never reached event: done"

    # Different sessions must have run in parallel (max active == 2)
    max_active = MockBrain.get_max_active()
    assert max_active >= 2, (
        f"Different-session turns must run in parallel (max active >= 2), "
        f"observed max_active == {max_active}"
    )
