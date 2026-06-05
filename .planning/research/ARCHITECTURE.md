# Architecture Research

**Domain:** Localhost voice assistant — streaming refactor + skill system + PWA
**Researched:** 2026-06-05
**Confidence:** HIGH (streaming/SSE patterns), MEDIUM (claude CLI stream-json event schema), HIGH (PWA/SW on localhost), HIGH (skill/MCP contract)

---

## Standard Architecture

### System Overview

```
┌─────────────────────────────── Browser (Chrome PWA) ──────────────────────────────┐
│  Web Speech API (STT/TTS)   │   Activity Panel (SSE)   │   Chat UI (fetch)         │
│  EventSource /api/stream/<id>│   app.js + sw.js         │   POST /api/turn          │
└─────────────────────────────────────┬──────────────────────────────────────────────┘
                                      │ HTTP / SSE (127.0.0.1:8765)
┌─────────────────────────────── server.py ─────────────────────────────────────────┐
│  Handler                                                                           │
│  POST /api/turn  → JobRegistry.create(job_id)  → spawn BrainThread                │
│  GET  /api/stream/<id>  → SSE loop reads job.queue → flush events to browser      │
│  POST /api/reset → session.session_id = None                                      │
│  GET  /api/health                                                                  │
│  GET  /static/* (cache-first via SW)                                               │
│                                                                                    │
│  JobRegistry  {job_id: Job(queue, status, session_ref)}                            │
│  SessionStore {session_token: Brain}  (one Brain per logical conversation)         │
└──────────────────┬─────────────────────────────────────────────────────────────────┘
                   │ subprocess.Popen (stream-json)
┌─────────────────────────────── brain.py ──────────────────────────────────────────┐
│  Brain.think_stream(text) → subprocess.Popen(claude -p --output-format stream-json│
│                              --mcp-config skills/_generated_mcp_config.json ...)   │
│  reads stdout NDJSON line-by-line → parses → puts ActivityEvent on job.queue      │
│  Brain.think(text) → (kept as sync fallback / Ollama path)                        │
└──────────────────┬─────────────────────────────────────────────────────────────────┘
                   │ MCP stdio (JSON-RPC 2.0)
┌──────────────────┴──────────────── MCP layer ─────────────────────────────────────┐
│  computer_use_server.py    │  skills/google-classroom/server.py  │  (future skills)│
│  (existing, unchanged)     │  (new, same hand-rolled JSON-RPC)   │                  │
└────────────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Boundary |
|-----------|----------------|----------|
| `JobRegistry` (new, in server.py) | Maps job_id → Job(queue, status); TTL cleanup | Owned by server process |
| `SessionStore` (new, in server.py) | Maps session_token → Brain instance; replaces single global `_brain` | Owned by server process |
| `Brain.think_stream()` (new method) | Popen stream-json, parse NDJSON, put ActivityEvents on queue | brain.py |
| `skills/_loader.py` (new) | Scan manifests, emit merged `_generated_mcp_config.json` + tool list + prompt addenda | skills/ dir |
| `skills/*/server.py` (new per skill) | Hand-rolled MCP stdio server for each skill domain | skills/<name>/ |
| `web/sw.js` (new) | Cache-first static, network-only /api/*, pass-through SSE | browser |
| `web/manifest.json` (new) | PWA identity, icons, display: standalone | web/ |

---

## Recommended Project Structure

```
Jarvis/
├── brain.py                        # + think_stream() method
├── server.py                       # + JobRegistry, SessionStore, /api/turn, /api/stream/<id>
├── skills/
│   ├── _loader.py                  # manifest scanner + MCP config aggregator
│   ├── _generated_mcp_config.json  # auto-generated at startup (gitignored)
│   └── google-classroom/
│       ├── manifest.json           # skill contract (id, mcp_server, allowed_tools, ...)
│       ├── server.py               # MCP stdio server (Python 3.9, hand-rolled JSON-RPC)
│       ├── auth.py                 # OAuth token load/refresh (google-auth-oauthlib)
│       └── setup.sh                # one-time: python skills/google-classroom/auth.py --setup
├── web/
│   ├── index.html
│   ├── app.js                      # + SSE client, activity panel, SW registration
│   ├── style.css
│   ├── manifest.json               # PWA manifest
│   ├── sw.js                       # service worker
│   └── icons/                      # 192×192, 512×512 PNG icons
└── mcp_config.json                 # computer-use only (legacy; skills use _generated)
```

### Structure Rationale

- **skills/ at project root:** co-located with the server so relative paths in manifests resolve correctly; `_loader.py` is not a skill, just the assembler.
- **_generated_mcp_config.json:** generated each startup from all enabled manifests — never hand-edited, always disposable. Add to `.gitignore`.
- **web/ unchanged layout:** SW served from `/sw.js` controls the whole origin; manifest at `/manifest.json`.

---

## Architectural Patterns

### Pattern 1: Job-Queue SSE (non-blocking turn)

**What:** `POST /api/turn` returns a `job_id` immediately; the brain runs in a background daemon thread writing to a `queue.Queue`; `GET /api/stream/<job_id>` is an SSE endpoint that drains the queue line-by-line.

**When to use:** Any turn that may block for seconds to minutes (all computer-use turns; any brain turn).

**Trade-offs:** Adds job registry state; client must open two connections per turn (POST then GET SSE). Simpler than WebSocket; stdlib-only; survives browser tab refresh (the job lives until TTL).

**Implementation sketch (Python 3.9, stdlib only):**

```python
# server.py additions

import queue, uuid, threading, time

_DONE = object()          # sentinel
_jobs: dict[str, "Job"] = {}
_jobs_lock = threading.Lock()

class Job:
    def __init__(self, session: "Brain"):
        self.id = str(uuid.uuid4())[:8]
        self.q: queue.Queue = queue.Queue()
        self.session = session
        self.created = time.monotonic()

def _spawn_turn(job: Job, text: str, control: bool, lang: str):
    def run():
        try:
            job.session.computer_use = control
            for event in job.session.think_stream(text):
                job.q.put(event)
        except BrainOffline:
            job.q.put({"type": "error", "msg": "offline"})
        finally:
            job.q.put(_DONE)
    t = threading.Thread(target=run, daemon=True)
    t.start()

# In Handler.do_GET for path /api/stream/<id>:
def _sse_stream(self, job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        self._send(404, b'{"error":"not found"}'); return
    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream")
    self.send_header("Cache-Control", "no-store")
    self.send_header("Connection", "keep-alive")
    self.end_headers()
    self.connection.settimeout(None)          # no read timeout on SSE connection
    while True:
        try:
            event = job.q.get(timeout=25)    # 25s keepalive heartbeat
        except queue.Empty:
            self.wfile.write(b": ping\n\n"); self.wfile.flush(); continue
        if event is _DONE:
            self.wfile.write(b"event: done\ndata: {}\n\n"); self.wfile.flush(); break
        line = ("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode()
        self.wfile.write(line); self.wfile.flush()
```

### Pattern 2: Streaming Brain (think_stream)

**What:** `Brain.think_stream()` uses `subprocess.Popen` with `--output-format stream-json` and reads NDJSON line-by-line from stdout, yielding typed `ActivityEvent` dicts.

**When to use:** All new web UI turns. The sync `Brain.think()` path is kept for the Ollama fallback and terminal entry points (`jarvis.py`, `hotkey.py`).

**Confidence note:** The claude CLI supports `--output-format stream-json` which emits NDJSON. Exact field names (`type`, `message`, `result`, `session_id`) match the json-mode schema — treat the result line as the last NDJSON object with `type == "result"`. MEDIUM confidence on intermediate event shape; parse defensively.

**Implementation sketch:**

```python
# brain.py additions

def _build_stream_cmd(self, user_text: str) -> list[str]:
    cmd = self._build_cmd(user_text)
    # Replace --output-format json with stream-json
    idx = cmd.index("json")   # after --output-format
    cmd[idx] = "stream-json"
    return cmd

def think_stream(self, user_text: str):
    """Generator: yields ActivityEvent dicts, then updates self.session_id."""
    cmd = self._build_stream_cmd(user_text)
    timeout = COMPUTER_TIMEOUT if self.computer_use else CHAT_TIMEOUT
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    final_text = ""
    try:
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = obj.get("type", "")
            if t == "assistant":
                # content blocks: text deltas or tool_use
                for block in (obj.get("message") or {}).get("content", []):
                    if block.get("type") == "tool_use":
                        yield {"type": "tool_use", "name": block.get("name"),
                               "input": block.get("input", {})}
                    elif block.get("type") == "text":
                        yield {"type": "text_delta", "text": block.get("text", "")}
            elif t == "tool_result":
                # may contain base64 screenshot
                for block in obj.get("content", []):
                    if block.get("type") == "image":
                        yield {"type": "screenshot",
                               "data": block.get("source", {}).get("data", "")}
            elif t == "result":
                final_text = (obj.get("result") or "").strip()
                if obj.get("session_id"):
                    self.session_id = obj["session_id"]
                yield {"type": "result", "text": final_text or "Okay."}
    finally:
        proc.wait(timeout=5)
    if proc.returncode != 0 and not final_text:
        stderr = proc.stderr.read()
        if any(w in stderr.lower() for w in ("network", "connect", "timeout", "offline")):
            raise BrainOffline(stderr.strip())
        yield {"type": "error", "text": stderr[:200] or "Something went wrong."}
```

### Pattern 3: Skill Loader — Manifest-Driven MCP Aggregation

**What:** At server startup, `skills/_loader.py` scans `skills/*/manifest.json`, filters enabled skills, and writes `skills/_generated_mcp_config.json` — a single MCP config file with all skill servers plus the existing computer-use server.

**When to use:** Every server startup. Brain reads the generated config instead of (or in addition to) `mcp_config.json`.

**Trade-offs:** Adding a skill requires restart (acceptable for a personal tool). No hot-reload. Generated file must be gitignored.

**Concrete loader:**

```python
# skills/_loader.py

import json
from pathlib import Path

SKILLS_DIR = Path(__file__).parent
HERE = SKILLS_DIR.parent            # project root

def load_skills() -> tuple[Path | None, list[str], str]:
    """
    Returns: (merged_mcp_config_path, extra_allowed_tools, system_prompt_addendum)
    merged_mcp_config_path is None if no skills are enabled.
    """
    servers, tools, prompts = {}, [], []

    # Always include computer-use sidecar if mcp_config.json exists
    base = HERE / "mcp_config.json"
    if base.exists():
        servers.update(json.loads(base.read_text()).get("mcpServers", {}))

    for manifest_path in sorted(SKILLS_DIR.glob("*/manifest.json")):
        m = json.loads(manifest_path.read_text())
        if not m.get("enabled", True):
            continue
        skill_dir = manifest_path.parent
        srv = m.get("mcp_server", {})
        # Resolve relative command paths relative to project root
        if srv.get("command") and not Path(srv["command"]).is_absolute():
            srv["command"] = str(HERE / srv["command"])
        if srv.get("args"):
            srv["args"] = [
                str(HERE / a) if (not Path(a).is_absolute() and (HERE / a).exists()) else a
                for a in srv["args"]
            ]
        servers[m["id"]] = srv
        tools.extend(m.get("allowed_tools", []))
        if m.get("system_prompt_addendum"):
            prompts.append(m["system_prompt_addendum"])

    if not servers:
        return None, tools, "\n".join(prompts)

    out = SKILLS_DIR / "_generated_mcp_config.json"
    out.write_text(json.dumps({"mcpServers": servers}, indent=2))
    return out, tools, "\n".join(prompts)
```

`Brain.__init__()` calls `load_skills()` and stores the results; `_build_cmd()` uses the generated config path and extends `COMPUTER_TOOLS` with `extra_tools`.

---

## Skill Contract (Concrete Spec)

Every skill lives in `skills/<id>/` and provides these files:

### manifest.json

```json
{
  "id": "google-classroom",
  "name": "Google Classroom",
  "version": "1.0.0",
  "description": "List courses, assignments, and announcements from Google Classroom",
  "enabled": true,
  "mcp_server": {
    "command": ".venv/bin/python",
    "args": ["skills/google-classroom/server.py"]
  },
  "allowed_tools": [
    "mcp__google-classroom__list_courses",
    "mcp__google-classroom__list_assignments",
    "mcp__google-classroom__get_announcements",
    "mcp__google-classroom__get_assignment_detail"
  ],
  "system_prompt_addendum": "You have access to Pietro's Google Classroom. Use list_courses to find course IDs, then list_assignments or get_announcements as needed. Always mention due dates in natural language."
}
```

### server.py (hand-rolled MCP stdio, Python 3.9)

Follows the same JSON-RPC 2.0 pattern as `computer_use_server.py`. Must implement:
- `tools/list` → returns tool definitions with `inputSchema`
- `tools/call` → dispatches to handler functions

### Required files

| File | Required | Purpose |
|------|----------|---------|
| `manifest.json` | Yes | Discovery + config |
| `server.py` | Yes | MCP stdio server |
| `requirements.txt` | If deps | `pip install -r skills/<id>/requirements.txt` |
| `setup.sh` | If auth | One-time credential/token setup |
| `auth.py` | OAuth skills | Token load/refresh |

### Importing skills from other Claude Code projects

Point `mcp_server.command` and `args` at the other project's server. Example for a hypothetical `~/Documents/StudyHelper/skills/notes/server.py`:

```json
{
  "id": "study-notes",
  "mcp_server": {
    "command": "/Users/pietrojustino/.venv/bin/python",
    "args": ["/Users/pietrojustino/Documents/StudyHelper/skills/notes/server.py"]
  }
}
```

No bridge needed — it is just a path reference resolved by the loader.

---

## Data Flow

### Streaming turn (new primary path)

```
Browser
  POST /api/turn {text, control, lang, session_token}
      ↓
  server.py: create Job(id), lookup/create Brain for session_token
  spawn daemon thread → brain.think_stream(text)
  return {job_id: "abc123"}
      ↓
  Browser opens: GET /api/stream/abc123   (SSE, long-lived)
      ↓
  BrainThread: Popen claude --output-format stream-json ...
    reads NDJSON stdout line-by-line:
      tool_use event    → job.q.put({"type":"tool_use","name":"mcp__computer__screenshot"})
      tool_result/image → job.q.put({"type":"screenshot","data":"<base64>"})
      text_delta        → job.q.put({"type":"text_delta","text":"..."})
      result            → job.q.put({"type":"result","text":"..."})
                          job.q.put(DONE_SENTINEL)
      ↓
  SSE handler: drains job.q → writes "data: {...}\n\n" + flush per event
      ↓
  Browser: EventSource receives events → renders activity items
    screenshot event → <img src="data:image/png;base64,...">
    tool_use event   → "Using: screenshot" label
    result event     → append to chat, speak via Web Speech API
    done event       → close EventSource
```

### Session model

- Browser generates a `session_token` (UUID) on first load, stored in `localStorage`.
- Every request includes `session_token` in the body.
- `SessionStore` in server.py maps `session_token → Brain`. One Brain per conversation, not per tab.
- `POST /api/reset` clears `Brain.session_id` for that session_token only (not other sessions).
- No global `_brain_lock`. Each Brain has its own `threading.Lock()` so concurrent turns on the same session serialize; different sessions run independently.

### Computer-use tool call within a streaming turn

```
claude CLI (stream-json) ─── MCP stdio ──► computer_use_server.py
  ↑                                              │
  │   tool_result {type:image, data:base64}      │ runs screencapture
  └──────────────────────────────────────────────┘
```

The screenshot base64 appears in the NDJSON stream as a `tool_result` event. The brain thread extracts it and puts `{"type":"screenshot","data":"<base64>"}` on the job queue. The SSE handler forwards it as-is. The browser renders `<img src="data:image/png;base64,...">` inline in the activity panel.

---

## Google Classroom Skill Architecture

**Approach:** MCP tool (not computer-use screen-scraping). Google Classroom REST API v1 — free with a GCP project + OAuth 2.0 (no paid key, no per-request cost).

**Setup flow (one-time):**
1. Pietro creates a GCP project, enables Classroom API, downloads `credentials.json` → `skills/google-classroom/credentials.json`
2. Runs `bash skills/google-classroom/setup.sh` → opens browser for OAuth consent → saves `skills/google-classroom/token.json`
3. `token.json` is gitignored; `auth.py` refreshes the token automatically on expiry

**Tools exposed:**

| Tool | Input | Returns |
|------|-------|---------|
| `list_courses` | `archived: bool` | `[{id, name, section}]` |
| `list_assignments` | `course_id, due_within_days?` | `[{id, title, due_date, link}]` |
| `get_announcements` | `course_id, limit?` | `[{text, created}]` |
| `get_assignment_detail` | `course_id, assignment_id` | `{title, description, due, link}` |

**Dependencies** (pip, Python 3.9 compat):
- `google-auth` >= 2.0
- `google-auth-oauthlib` >= 1.0
- `google-api-python-client` >= 2.0

All are 3.9-compatible (HIGH confidence — Google's client libs support 3.9).

---

## PWA Architecture

### Manifest (`web/manifest.json`)

```json
{
  "name": "Jarvis",
  "short_name": "Jarvis",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0f0f0f",
  "theme_color": "#0f0f0f",
  "icons": [
    {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png"}
  ]
}
```

### Service Worker strategy (`web/sw.js`)

```javascript
const CACHE = "jarvis-v1";
const STATIC = ["/", "/style.css", "/app.js", "/manifest.json",
                "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", e =>
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC))));

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  // API + SSE: always network-only (never cache, never intercept streams)
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(fetch(e.request));
    return;
  }
  // Static: cache-first
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});
```

**Key constraint:** `EventSource` (SSE) connections go to `/api/stream/<id>` — the SW passes them straight through. No special handling needed; browsers bypass SW cache for `EventSource` internally, but the explicit pass-through makes intent clear.

**Localhost + HTTP:** Chrome grants secure-context to `127.0.0.1` — service workers and PWA install work without HTTPS. HIGH confidence (this is a documented Chrome exception).

**SW scope:** Registered from `/sw.js` with no `scope` override → controls the entire `http://127.0.0.1:8765/` origin, which is exactly what we want.

---

## Dependency-Ordered Build Sequence

Phase dependencies flow top-to-bottom: each phase can only start when its predecessors are done.

| # | Component | Depends On | Rationale |
|---|-----------|-----------|-----------|
| 1 | **Job registry + SessionStore in server.py** | Nothing (existing server.py) | Foundation: all other new endpoints need this |
| 2 | **`POST /api/turn` + `GET /api/stream/<id>` SSE** | Phase 1 | Replaces the blocking /api/ask for web turns |
| 3 | **`Brain.think_stream()`** | Phase 2 (needs something to stream to) | Wire to the job queue |
| 4 | **Browser SSE client + activity panel** | Phase 2+3 | Can't build UI without the server endpoint |
| 5 | **`skills/_loader.py` + manifest schema** | Nothing (independent) | Can be built in parallel with 1-4 |
| 6 | **`Brain` skill integration** (`load_skills()` at init) | Phases 3 + 5 | Brain must stream AND understand skill config |
| 7 | **Google Classroom skill** (`manifest.json` + `server.py` + `auth.py`) | Phase 5 (loader contract) | Skill contract must be stable first |
| 8 | **PWA: manifest + icons** | Nothing (static files) | Independent; can be added any time |
| 9 | **PWA: service worker** | Phase 8 (manifest), Phase 2 (SSE endpoints stable) | SW must know which paths to cache vs. pass-through |

**Minimum viable streaming milestone:** Phases 1 → 2 → 3 → 4. The UI unblocks and shows live activity. Skills and PWA can ship separately.

**Minimum viable skill milestone:** Phases 5 → 6 → 7 (can run after streaming is done).

---

## Anti-Patterns

### Anti-Pattern 1: Keep the global brain lock for streaming turns

**What people do:** Hold `_brain_lock` for the entire `think_stream()` generator duration.
**Why it's wrong:** Defeats the non-blocking goal entirely — 600s computer-use turns still freeze all other requests.
**Do this instead:** Per-session Brain instances each with their own lock. No global lock on the request path. The job registry itself is lock-protected only for dict mutations (microseconds).

### Anti-Pattern 2: Forward raw NDJSON to the browser

**What people do:** Pipe the raw `--output-format stream-json` bytes directly to the SSE response.
**Why it's wrong:** The raw schema includes large base64 image payloads, internal Claude CLI metadata, and fields the browser doesn't understand. It couples the browser to the CLI's internal wire format.
**Do this instead:** Parse in `think_stream()`, emit typed `ActivityEvent` dicts (`tool_use`, `screenshot`, `text_delta`, `result`, `error`). The browser only sees this typed contract.

### Anti-Pattern 3: Cache-all service worker

**What people do:** `caches.match(e.request)` for every fetch including API calls.
**Why it's wrong:** Caching `/api/stream/<id>` or `/api/ask` means Jarvis answers from a stale cache instead of thinking. SSE streams can't be cached.
**Do this instead:** Explicit allowlist of static paths to cache; explicit pass-through for `/api/*`.

### Anti-Pattern 4: One MCP config file for everything (hand-edited)

**What people do:** Add every new skill's MCP server directly to `mcp_config.json`.
**Why it's wrong:** Skills become tightly coupled to the main config; enabling/disabling requires manual JSON editing; the computer-use whitelist and skill tool lists get tangled.
**Do this instead:** `skills/_loader.py` generates `_generated_mcp_config.json` at startup from independent manifests. The computer-use config (`mcp_config.json`) remains dedicated to computer tools.

### Anti-Pattern 5: Drive Google Classroom via computer-use

**What people do:** Use the existing screenshot/click tools to scrape `classroom.google.com`.
**Why it's wrong:** Brittle (UI changes break it), slow (multiple screenshot/click cycles), requires the screen to be visible, cannot run headless.
**Do this instead:** Classroom REST API v1 over HTTPS — deterministic, fast, structured JSON, no screen access needed.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Google Classroom API v1 | OAuth 2.0 + REST (HTTPS) from Python | Token stored in `skills/google-classroom/token.json`; gitignored |
| claude CLI | `subprocess.Popen` with `--output-format stream-json` | One process per turn; stream-json adds no new flags |
| Ollama (offline brain) | HTTP REST (`/api/chat`) | Unchanged; sync path only |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| server.py ↔ brain.py | Function call: `brain.think_stream()` yields events | Brain thread owned by server |
| brain.py ↔ claude CLI | subprocess stdin/stdout NDJSON | Popen replaces run for streaming |
| claude CLI ↔ MCP skills | stdio JSON-RPC 2.0 | Same protocol as existing computer-use sidecar |
| server.py ↔ browser | SSE (text/event-stream) for streaming; JSON REST for control | SSE is one-way server→browser |
| browser ↔ SW | Cache API + Fetch intercept | SW transparent to app.js logic |

---

## Sources

- Python stdlib `http.server` + `queue.Queue` — stdlib docs, no external dependency
- SSE spec: `text/event-stream` with `data:` prefix, `\n\n` event delimiter — WHATWG standard
- Claude CLI `--output-format stream-json` — HIGH confidence from Claude Code docs (training data, August 2025); exact intermediate event shape MEDIUM confidence, parse defensively
- Chrome secure-context exception for `localhost`/`127.0.0.1` — Chrome developer docs, HIGH confidence
- Google Classroom REST API v1 — Google Developers docs; Python client 3.9 compat verified in google-api-python-client changelog
- MCP JSON-RPC 2.0 stdio pattern — `computer_use_server.py` existing implementation (HIGH, already working in this codebase)

---

*Architecture research for: Jarvis milestone 2 (streaming + skills + PWA)*
*Researched: 2026-06-05*
