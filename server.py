"""
server.py — Jarvis's web UI backend.

A tiny, dependency-free local server (Python stdlib only) that serves the Chrome UI in
web/ and connects it to your Max-plan brain. Speech recognition and speech (the voice)
happen in the browser via Chrome's Web Speech API — which also gives you Google's natural
neural voices — so this backend only has to think.

Run it directly:   python server.py        (then open http://127.0.0.1:8765)
Or use the Raycast "Open Jarvis" command, which starts it and opens Chrome for you.

Binds to 127.0.0.1 only — it is never exposed to your network.
"""

from __future__ import annotations

import json
import queue
import socket
import sys
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
WEB = HERE / "web"
HOST, PORT = "127.0.0.1", 8765

# ---------------------------------------------------------------------------
# Origin / CSRF guard (SEC-01)
# Blocks DNS-rebinding attacks: evil.com → 127.0.0.1 would carry evil.com Origin.
# Same-origin requests (browser nav, curl) carry empty Origin and pass through.
# ---------------------------------------------------------------------------
_ALLOWED_ORIGINS = frozenset({"http://127.0.0.1:8765", "http://localhost:8765"})

# ---------------------------------------------------------------------------
# Brain factory — module global; tests monkeypatch before first use.
# Set to None so the lazy-init path imports Brain on first real use.
# ---------------------------------------------------------------------------
_BRAIN_FACTORY = None  # type: ignore[assignment]  # lazily defaults to Brain; tests override BEFORE first use

# ---------------------------------------------------------------------------
# SessionStore — maps session_token -> Brain instance.
# Each token gets its own Brain (and its own _lock) so different conversation
# threads never cross-block each other (CORE-03 parallelism).
# ---------------------------------------------------------------------------
_sessions = {}           # session_token -> Brain
_sessions_lock = threading.Lock()


def _new_brain():
    """Create a new Brain using _BRAIN_FACTORY (real Brain or test mock)."""
    global _BRAIN_FACTORY
    if _BRAIN_FACTORY is None:
        from brain import Brain
        _BRAIN_FACTORY = Brain
    return _BRAIN_FACTORY()


def _get_session(token):
    """Return (or lazily create) the Brain for this session token."""
    with _sessions_lock:
        if token not in _sessions:
            _sessions[token] = _new_brain()
        return _sessions[token]


# ---------------------------------------------------------------------------
# JobRegistry — maps job_id -> _Job.
# Jobs are created by POST /api/turn and drained by GET /api/stream/<id>.
# ---------------------------------------------------------------------------
class _Job:
    """Holds the event queue for a single brain turn."""

    def __init__(self):
        self.q = queue.Queue()


_jobs = {}            # job_id -> _Job
_jobs_lock = threading.Lock()
_DONE = object()      # sentinel: pushed onto job.q when the generator is exhausted


# ---------------------------------------------------------------------------
# Worker — runs in a daemon thread per turn
# ---------------------------------------------------------------------------
def _run_turn(job, brain, text, control):
    """Execute one brain turn and push events onto job.q.

    Acquires brain._lock for the full duration of think_stream so that two turns
    on the same session_token never overlap (CORE-03 / Pitfall 4: MCP pipe race).
    """
    try:
        with brain._lock:   # single-writer per session — serializes same-session turns
            brain.computer_use = bool(control) and (HERE / "mcp_config.json").exists()
            for ev in brain.think_stream(text):
                job.q.put(ev)
    except Exception as e:  # surface BrainOffline / errors as an event; never crash the thread
        job.q.put({"type": "error", "text": str(e)[:200]})
    finally:
        job.q.put(_DONE)   # always push the sentinel so the SSE loop exits cleanly


# ---------------------------------------------------------------------------
# Local (Ollama) brain — fallback for /api/ask when Max-plan brain is offline
# ---------------------------------------------------------------------------
_local = None           # cached LocalBrain instance once probed, else None
_local_checked = False  # guard so Ollama availability is probed only once


def _local_brain():
    """Return the offline LocalBrain if Ollama is reachable, else None.

    Probes availability once and caches the result. Uses None (not a bool sentinel)
    for the unavailable case so the return type stays a clean LocalBrain-or-None
    (fixes the Pylance reportAttributeAccessIssue on lb.think()).
    """
    global _local, _local_checked
    if not _local_checked:
        _local_checked = True
        try:
            from local_brain import LocalBrain
            lb = LocalBrain()
            _local = lb if lb.available() else None
        except Exception:
            _local = None
    return _local


# ---------------------------------------------------------------------------
# Static content types
# ---------------------------------------------------------------------------
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".json": "application/json",
    ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _send(self, code, body, ctype="application/json"):
        # type: (int, bytes, str) -> None
        """Send a standard JSON (or other) response with Content-Length."""
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _start_sse(self):
        """Send SSE response headers.

        MUST NOT set Content-Length (streaming) or Cache-Control: no-store
        (would break proxy/browser SSE buffering per PITFALLS Pitfall 1).
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

    def _origin_ok(self):
        # type: () -> bool
        """Return True if the request is from an allowed origin.

        Empty Origin (curl, native callers, browser navigation) always passes.
        A non-empty Origin that is NOT in _ALLOWED_ORIGINS returns False → 403.
        """
        origin = self.headers.get("Origin", "")
        return (not origin) or (origin in _ALLOWED_ORIGINS)

    # ------------------------------------------------------------------
    # GET routing
    # ------------------------------------------------------------------

    def do_GET(self):
        # SEC-01: block foreign-origin GET requests (DNS rebinding)
        if not self._origin_ok():
            self._send(403, b'{"error":"forbidden"}')
            return

        path = self.path.split("?", 1)[0]

        # --- /api/health ---
        if path == "/api/health":
            try:
                import computer
                acc, scr = computer.has_accessibility(), computer.has_screen_recording()
            except Exception:
                acc = scr = False
            self._send(200, json.dumps({"ok": True, "accessibility": acc,
                                        "screen_recording": scr}).encode())
            return

        # --- /api/stream/<job_id> — SSE drain loop (CORE-02) ---
        if path.startswith("/api/stream/"):
            job_id = path[len("/api/stream/"):]
            with _jobs_lock:
                job = _jobs.get(job_id)
            if job is None:
                self._send(404, b'{"error":"not found"}')
                return
            # Force close after stream ends so the client's resp.read() returns
            # (HTTP/1.1 persistent connections would otherwise keep both sides waiting).
            self.close_connection = True
            self._start_sse()
            while True:
                try:
                    event = job.q.get(timeout=25)
                except queue.Empty:
                    # Send a keepalive comment so the connection stays alive
                    try:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    continue
                if event is _DONE:
                    try:
                        self.wfile.write(b"event: done\ndata: {}\n\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    break
                payload = json.dumps(event, ensure_ascii=False).encode("utf-8")
                try:
                    self.wfile.write(b"data: " + payload + b"\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
            with _jobs_lock:
                _jobs.pop(job_id, None)  # cleanup finished job
            return

        # --- Static files ---
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = (WEB / rel).resolve()
        if not str(f).startswith(str(WEB.resolve())) or not f.is_file():
            self._send(404, b"not found", "text/plain")
            return
        self._send(200, f.read_bytes(), _CONTENT_TYPES.get(f.suffix, "application/octet-stream"))

    # ------------------------------------------------------------------
    # POST routing
    # ------------------------------------------------------------------

    def do_POST(self):
        # SEC-01: block foreign-origin POST requests (CSRF / DNS rebinding)
        if not self._origin_ok():
            self._send(403, b'{"error":"forbidden"}')
            return

        path = self.path.split("?", 1)[0]

        # --- /api/reset — clear session_id for a given (or default) session ---
        if path == "/api/reset":
            try:
                n = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(n)) if n else {}
            except Exception:
                data = {}
            token = data.get("session_token") or "__default__"
            with _sessions_lock:
                if token in _sessions:
                    _sessions[token].session_id = None
            self._send(200, b'{"ok": true}')
            return

        # --- /api/turn — non-blocking job dispatch (CORE-01) ---
        if path == "/api/turn":
            try:
                n = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                self._send(400, b'{"error":"bad request"}')
                return
            text = (data.get("text") or "").strip()
            if not text:
                self._send(400, b'{"error":"empty text"}')
                return
            if len(text) > 10000:
                self._send(400, b'{"error":"too long"}')
                return
            session_token = data.get("session_token") or "__default__"
            brain = _get_session(session_token)
            job_id = uuid.uuid4().hex[:12]
            job = _Job()
            with _jobs_lock:
                _jobs[job_id] = job
            threading.Thread(
                target=_run_turn,
                args=(job, brain, text, bool(data.get("control"))),
                daemon=True,
            ).start()
            # Returns immediately — brain runs in the background thread
            self._send(200, json.dumps({"job_id": job_id}).encode())
            return

        # --- /api/ask — legacy synchronous endpoint (backward compat) ---
        if path == "/api/ask":
            try:
                n = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                self._send(400, b'{"error":"bad request"}')
                return
            text = (data.get("text") or "").strip()
            if not text:
                self._send(200, json.dumps({"reply": ""}).encode())
                return
            if len(text) > 10000:
                self._send(400, b'{"error":"too long"}')
                return
            from brain import BrainOffline
            session_token = data.get("session_token") or "__default__"
            lang = data.get("lang", "en")
            brain = _get_session(session_token)
            try:
                with brain._lock:
                    brain.computer_use = (
                        bool(data.get("control")) and (HERE / "mcp_config.json").exists()
                    )
                    reply = brain.think(text)
                result = {"reply": reply, "source": "max"}
            except BrainOffline:
                lb = _local_brain()
                if lb:
                    result = {"reply": lb.think(text, language=lang), "source": "ollama"} # type: ignore
                else:
                    msg = (
                        "I can't reach my main brain and have no offline brain set up yet."
                        if lang != "pt" else
                        "Não consigo acessar meu cérebro principal e ainda não tenho um offline."
                    )
                    result = {"reply": msg, "source": "offline"}
            except Exception as e:  # never 500 the UI; surface a spoken-friendly error
                result = {"reply": f"Something went wrong: {e}", "source": "error"}
            self._send(200, json.dumps(result, ensure_ascii=False).encode())
            return

        self._send(404, b'{"error":"not found"}')


def main():
    open_browser = "--no-open" not in sys.argv[1:]
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    # Defeat Nagle buffering so SSE events are flushed to the browser immediately.
    httpd.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    url = f"http://{HOST}:{PORT}"
    print(f"\U0001f310 Jarvis UI on {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Jarvis UI.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
