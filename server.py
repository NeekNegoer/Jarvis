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
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
WEB = HERE / "web"
HOST, PORT = "127.0.0.1", 8765

_brain = None
_brain_lock = threading.Lock()
_local = None

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".json": "application/json",
    ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def _get_brain():
    global _brain
    with _brain_lock:
        if _brain is None:
            from brain import Brain
            _brain = Brain()  # computer use auto-enabled if mcp_config.json exists
        return _brain


def _local_brain():
    global _local
    if _local is None:
        try:
            from local_brain import LocalBrain
            lb = LocalBrain()
            _local = lb if lb.available() else False
        except Exception:
            _local = False
    return _local or None


def _ask(text: str, control: bool, lang: str) -> dict:
    """Run one brain turn. `control` toggles whole-Mac computer use for this turn."""
    from brain import BrainOffline
    brain = _get_brain()
    try:
        with _brain_lock:
            brain.computer_use = bool(control) and (HERE / "mcp_config.json").exists()
            reply = brain.think(text)
        return {"reply": reply, "source": "max"}
    except BrainOffline:
        lb = _local_brain()
        if lb:
            return {"reply": lb.think(text, language=lang), "source": "ollama"}
        msg = ("I can't reach my main brain and have no offline brain set up yet."
               if lang != "pt" else
               "Não consigo acessar meu cérebro principal e ainda não tenho um offline.")
        return {"reply": msg, "source": "offline"}
    except Exception as e:  # never 500 the UI; surface a spoken-friendly error
        return {"reply": f"Something went wrong: {e}", "source": "error"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            try:
                import computer
                acc, scr = computer.has_accessibility(), computer.has_screen_recording()
            except Exception:
                acc = scr = False
            self._send(200, json.dumps({"ok": True, "accessibility": acc,
                                        "screen_recording": scr}).encode())
            return
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = (WEB / rel).resolve()
        if not str(f).startswith(str(WEB.resolve())) or not f.is_file():
            self._send(404, b"not found", "text/plain")
            return
        self._send(200, f.read_bytes(), _CONTENT_TYPES.get(f.suffix, "application/octet-stream"))

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/reset":
            # Forget the running conversation so the next turn starts fresh. The brain
            # keeps context by resuming a session_id; dropping it begins a new one.
            with _brain_lock:
                if _brain is not None:
                    _brain.session_id = None
            self._send(200, b'{"ok": true}')
            return
        if path != "/api/ask":
            self._send(404, b'{"error":"not found"}')
            return
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
        result = _ask(text, bool(data.get("control")), data.get("lang", "en"))
        self._send(200, json.dumps(result, ensure_ascii=False).encode())


def main():
    open_browser = "--no-open" not in sys.argv[1:]
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"🌐 Jarvis UI on {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Jarvis UI.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
