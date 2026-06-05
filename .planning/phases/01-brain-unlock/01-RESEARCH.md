# Phase 1: Brain Unlock — Research

**Researched:** 2026-06-05
**Domain:** Python stdlib HTTP streaming (SSE) + claude CLI stream-json + concurrent turn serialization + Origin-check CSRF defense
**Confidence:** HIGH (stream-json schema — empirically verified this session), HIGH (SSE patterns), HIGH (security/Origin check)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CORE-01 | UI stays responsive during long turns (up to 600 s) | Job-queue SSE pattern decouples POST (returns immediately with job_id) from GET SSE (streams events); brain thread is a daemon |
| CORE-02 | Turn streams incrementally — text and step updates arrive as they happen | think_stream() parses NDJSON line-by-line and puts typed ActivityEvents on job.queue; SSE handler drains queue flushing per event |
| CORE-03 | Concurrent turns/sessions handled safely — single-writer guarantee | Per-session Brain + per-Brain threading.Lock; SessionStore replaces the single global _brain |
| SEC-01 | Local web server rejects cross-origin requests | Origin header check at top of do_POST and do_GET for /api/stream/* — return 403 if origin is not whitelisted |
</phase_requirements>

---

## Summary

Phase 1 refactors two files — `server.py` and `brain.py` — to convert the blocking `/api/ask` pattern into a non-blocking Job-queue + SSE architecture. The browser POSTs to `/api/turn`, gets back a `job_id` immediately, then opens a long-lived SSE connection to `GET /api/stream/<job_id>` to receive incremental `ActivityEvent` dicts. The brain runs in a daemon thread writing to a `queue.Queue`; the SSE handler drains it.

The highest-risk change is `Brain.think_stream()`, which must add `--verbose` to the `claude` CLI invocation (verified empirically — stream-json mode refuses to run without it) and parse a NDJSON schema that delivers text in full blocks (not character deltas). The schema has been empirically verified in this session; exact tool_use and tool_result shapes for computer-use turns remain MEDIUM confidence and must be parsed defensively.

Concurrent-turn safety is achieved by introducing a `SessionStore` that maps session tokens to per-session `Brain` instances, each with its own `threading.Lock`. This replaces the single global `_brain` and global `_brain_lock`, eliminates the race described in CONCERNS.md, and ensures at most one `claude` CLI process is active per session at any time (protecting the shared MCP stdio pipe).

**Primary recommendation:** Implement in build order: (1) `SessionStore` + `JobRegistry`, (2) `/api/turn` + `/api/stream/<id>`, (3) `Brain.think_stream()`, (4) Origin check on all endpoints. Keep `/api/ask` and the existing sync `Brain.think()` intact throughout — they are required by `jarvis.py`, `hotkey.py`, and `wake.py`.

---

## Project Constraints (from CLAUDE.md)

- Python 3.9.6 venv — no official mcp SDK; all new code must be 3.9-compatible
- Brain = `claude` CLI on Max plan — no `ANTHROPIC_API_KEY`
- No sudo/admin — no elevated installs
- Localhost-only — server binds `127.0.0.1` only
- Offline degradation — Ollama LocalBrain fallback must continue to work
- Bilingual — pt-BR / English parity (not directly relevant to Phase 1 mechanics but error messages must remain bilingual)
- No JS build step — vanilla ES2015+ only
- Backward-compat — `/api/ask`, `/api/health`, `/api/reset` must remain; `jarvis.py`, `wake.py`, `hotkey.py` import `brain.Brain` and must not break
- GSD workflow: do not make direct repo edits outside a GSD workflow

---

## Standard Stack

### Core (all Python stdlib — no new pip packages for Phase 1)

| Component | Module | Purpose | Why |
|-----------|--------|---------|-----|
| `queue.Queue` | stdlib | Thread-safe FIFO between brain thread and SSE handler | No external dep; built for producer/consumer; `get(timeout=N)` drives keepalive heartbeats |
| `threading.Thread(daemon=True)` | stdlib | Run `think_stream()` off the request thread | Daemon means it dies with the process; non-blocking for request handler |
| `threading.Lock()` | stdlib | Per-Brain serialization; JobRegistry dict mutation | Prevents session_id race and concurrent MCP pipe access |
| `uuid.uuid4()` | stdlib | Generate unique job_id per turn | Collision-free; short hex prefix sufficient for a single-user tool |
| `subprocess.Popen` | stdlib | Stream NDJSON from `claude --output-format stream-json` | Line-by-line stdout reading; already the codebase pattern |
| `json` | stdlib | Parse each NDJSON line | Already used throughout |
| `http.server.ThreadingHTTPServer` | stdlib | Unchanged; already handles concurrent requests | Phase 1 adds new handler methods, no server replacement |

**No new pip packages required for Phase 1.**

---

## Empirically Verified: `claude --output-format stream-json` Event Schema

**Verification method:** Ran `~/.local/bin/claude -p "say hi" --output-format stream-json --verbose` in this session (2026-06-05). Full output captured and analyzed.

### CRITICAL FINDING: `--verbose` is MANDATORY

```
Error: When using --print, --output-format=stream-json requires --verbose
```

The current `_build_stream_cmd()` sketch in ARCHITECTURE.md omits `--verbose`. The `_build_stream_cmd()` implementation **must** add `--verbose` to the command. [VERIFIED: empirical run]

### Verified Event Types (from simple non-tool "say hi" run)

| `type` field | `subtype` | Contains | Action in think_stream() |
|-------------|-----------|----------|--------------------------|
| `"system"` | `"hook_started"`, `"hook_response"`, `"init"` | SessionStart hook info, tool list, session metadata | **Skip entirely** — not user-facing |
| `"assistant"` | — | `message.content` array with typed blocks | Extract text/tool_use blocks; skip thinking blocks |
| `"rate_limit_event"` | — | Rate limit status and reset time | Skip (log at DEBUG level) |
| `"result"` | `"success"` | `result` (final text), `session_id`, `is_error`, `stop_reason` | Yield `{"type":"result","text":...}`; update `self.session_id` |

### Verified `assistant` Event Structure

Two sequential `assistant` events appear per turn:
1. First: `content: [{"type": "thinking", "thinking": "..."}]` — internal reasoning (SKIP; not user-facing)
2. Second: `content: [{"type": "text", "text": "Hi Pietro! Ready when you are."}]` — the actual reply

**Key insight:** The CLI streams **full message blocks**, not character-by-character deltas. Text arrives in one chunk per content block, not incrementally character-by-character. This is fine for step labels; CORE-02 is satisfied because tool_use and text blocks arrive as each turn segment completes, not only at the very end.

### Verified `result` Event Structure (final line)

```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "result": "Hi Pietro! Ready when you are.",
  "session_id": "be381322-600b-4a32-9a2b-56f85a745e04",
  "stop_reason": "end_turn",
  "duration_ms": 6895
}
```

Fields: `result` = final text, `session_id` = resume token, `is_error` = bool, `api_error_status` = null on success. [VERIFIED: empirical]

### MEDIUM Confidence: Tool-Use and Screenshot Events (not verified in this run)

For computer-use turns, from ARCHITECTURE.md (parsed from training data — not verified empirically in this session):
- `type: "assistant"`, `content[].type == "tool_use"` — carries `name` and `input` for tool calls
- `type: "tool_result"`, `content[].type == "image"` — carries `source.data` (base64 PNG) for screenshots

**Parse defensively:** Use `.get()` at every level; discard lines where `json.loads` raises; log raw lines in `DEBUG` mode for first computer-use turn. [ASSUMED from ARCHITECTURE.md training-data notes]

### `_build_stream_cmd()` Correction

Current architecture sketch calls `cmd.index("json")` to replace the format flag. The correct implementation:

```python
def _build_stream_cmd(self, user_text: str) -> list[str]:
    cmd = self._build_cmd(user_text)
    # Replace --output-format json with stream-json + add --verbose (REQUIRED)
    idx = cmd.index("--output-format")
    cmd[idx + 1] = "stream-json"
    cmd.insert(idx + 2, "--verbose")   # CRITICAL: stream-json refuses to run without --verbose
    return cmd
```

---

## Architecture Patterns

### Pattern 1: Job-Queue SSE (non-blocking turn)

Directly from ARCHITECTURE.md (HIGH confidence, design already finalized):

```
POST /api/turn {text, control, lang, session_token}
  → server: create Job, look up/create Brain for session_token, spawn daemon thread
  → return {"job_id": "abc123"}   immediately (no blocking)

GET /api/stream/abc123   (SSE, long-lived)
  → SSE loop: job.q.get(timeout=25) → write "data: {...}\n\n" + flush
  → heartbeat ": ping\n\n" on Empty
  → break on _DONE sentinel
```

### Pattern 2: SessionStore (per-session Brain)

Replace the global `_brain` + `_brain_lock` with:

```python
_sessions: dict[str, Brain] = {}   # session_token -> Brain
_sessions_lock = threading.Lock()

def _get_session(token: str) -> Brain:
    with _sessions_lock:
        if token not in _sessions:
            _sessions[token] = Brain()
        return _sessions[token]
```

Each Brain has its own `threading.Lock` (already exists: no global lock held for turn duration). `/api/reset` calls `_sessions[token].session_id = None` without affecting other sessions.

### Pattern 3: SSE Response (NOT via `_send`)

The existing `_send` helper writes `Content-Length` — **fatal for SSE**. Use a dedicated method:

```python
def _start_sse(self):
    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream")
    self.send_header("Cache-Control", "no-cache")   # NOT no-store
    self.send_header("Connection", "keep-alive")
    # NO Content-Length header
    self.end_headers()
    # Defeat Nagle buffering: each flush must reach the browser immediately
```

After each event: `self.wfile.write(b"data: " + payload + b"\n\n"); self.wfile.flush()`.

### Pattern 4: Origin Check (SEC-01)

At the top of both `do_POST` and `do_GET` (before routing):

```python
_ALLOWED_ORIGINS = {"http://127.0.0.1:8765", "http://localhost:8765"}

origin = self.headers.get("Origin", "")
if origin and origin not in _ALLOWED_ORIGINS:
    self._send(403, b'{"error":"forbidden"}')
    return
```

Note: requests from the same origin (browser navigation, curl without Origin header) have `origin == ""` — the `if origin and ...` guard passes them through. Only cross-origin requests carry an `Origin` header, so this check doesn't block legitimate same-origin use.

### Recommended Project Structure (Phase 1 changes only)

```
server.py    # + SessionStore, JobRegistry, /api/turn, /api/stream/<id>, Origin check
             # keep: /api/ask, /api/reset, /api/health (unchanged)
brain.py     # + think_stream() method
             # keep: think(), _build_cmd(), Brain.__init__() (unchanged)
```

No new files required for Phase 1.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread-safe producer/consumer queue | Custom queue with conditions | `queue.Queue` | Already handles blocking get, timeout, Empty exception |
| Unique turn identifiers | Sequential int or timestamp | `uuid.uuid4()` | Collision-free; no shared counter needed |
| SSE keepalive | Custom timer thread | `queue.Queue.get(timeout=25)` → write ping on `Empty` | One mechanism serves both keepalive and event delivery |
| Per-session state | Session database | Dict + Lock | Single-user localhost; dict is sufficient |

---

## Common Pitfalls

### Pitfall 1: Missing `--verbose` flag for stream-json
**What goes wrong:** `claude -p ... --output-format stream-json` exits immediately with `Error: When using --print, --output-format=stream-json requires --verbose`. The Popen process exits non-zero with no NDJSON output; think_stream() yields nothing.
**How to avoid:** Add `--verbose` to the command immediately after `stream-json`. [VERIFIED: empirical]

### Pitfall 2: Reusing `_send` for SSE responses
**What goes wrong:** `_send` writes `Content-Length`, which the browser treats as a fixed-length blob. Events never arrive incrementally; the UI freezes exactly as today.
**How to avoid:** Dedicated `_start_sse()` method — no `Content-Length`, `Cache-Control: no-cache` (not `no-store`). Call `self.wfile.flush()` after every event write.

### Pitfall 3: Global brain lock held for full turn
**What goes wrong:** Current `_ask()` holds `_brain_lock` for the entire `brain.think()` duration. A second request during a 600s computer-use turn blocks indefinitely.
**How to avoid:** Per-session Brain instances; only the session dict mutation is lock-protected (microseconds). Each Brain's own lock serializes concurrent turns on the SAME session (protecting MCP pipe) but different sessions run in parallel.

### Pitfall 4: Concurrent claude processes fighting over MCP stdio pipe
**What goes wrong:** If two turns start simultaneously on the same session (race before the per-session lock is acquired), both spawn a `claude` process. Both try to use `computer_use_server.py` over the same stdio pipe — garbled JSON-RPC.
**How to avoid:** The per-Brain lock (`with brain._lock:` in think_stream) ensures only one active Popen per Brain at a time. The lock must wrap the entire Popen lifecycle, not just the `popen()` call.

### Pitfall 5: BrokenPipeError on client disconnect not caught
**What goes wrong:** Browser tab closes mid-stream → `self.wfile.write()` raises `BrokenPipeError`. Uncaught, this propagates and leaves the brain thread running undetected.
**How to avoid:** Wrap each `wfile.write/flush` in `except (BrokenPipeError, ConnectionResetError): break`. Optionally signal the brain thread via a `threading.Event` to abort early.

### Pitfall 6: Thinking blocks forwarded to the browser
**What goes wrong:** The `assistant` event contains a `thinking` content block before the `text` block. If forwarded as-is, the browser receives raw internal reasoning as a "text_delta" event and displays it to Pietro.
**How to avoid:** Filter in `think_stream()`: `if block.get("type") == "text"` — only emit text blocks; skip `thinking` blocks.

### Pitfall 7: session_id race when lock is removed from global scope
**What goes wrong:** `brain.session_id` is read at the start of `think()` (for `--resume`) and written at the end. Two concurrent turns on the same Brain could read a stale session_id.
**How to avoid:** Per-Brain lock wraps the entire `think_stream()` call. Since only one thread ever accesses a given Brain at a time, `session_id` is owned by that thread.

---

## Code Examples

### think_stream() — verified event parsing

```python
# brain.py — verified against empirical stream-json output 2026-06-05
def _build_stream_cmd(self, user_text: str) -> list[str]:
    cmd = self._build_cmd(user_text)
    idx = cmd.index("--output-format")
    cmd[idx + 1] = "stream-json"
    cmd.insert(idx + 2, "--verbose")   # REQUIRED: stream-json refuses without --verbose [VERIFIED]
    return cmd

def think_stream(self, user_text: str):
    """Generator: yields ActivityEvent dicts; updates self.session_id on result."""
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
                for block in (obj.get("message") or {}).get("content", []):
                    bt = block.get("type", "")
                    if bt == "thinking":
                        continue   # skip internal reasoning [VERIFIED: appears before text block]
                    elif bt == "text":
                        text = block.get("text", "")
                        if text:
                            yield {"type": "text", "text": text}   # event type is "text" (matches the plans/tests)
                    elif bt == "tool_use":
                        yield {"type": "tool_use", "name": block.get("name"),
                               "input": block.get("input", {})}  # [ASSUMED: not verified in this run]
            elif t == "tool_result":  # [ASSUMED: not verified in this run]
                for block in obj.get("content", []):
                    if block.get("type") == "image":
                        yield {"type": "screenshot",
                               "data": block.get("source", {}).get("data", "")}
            elif t == "result":
                final_text = (obj.get("result") or "").strip()
                if obj.get("session_id"):
                    self.session_id = obj["session_id"]   # [VERIFIED: confirmed in empirical run]
                yield {"type": "result", "text": final_text or "Okay."}
            # Skip: type == "system", "rate_limit_event" — no user-facing content [VERIFIED]
    finally:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    if proc.returncode != 0 and not final_text:
        stderr = proc.stderr.read()
        if any(w in stderr.lower() for w in ("network", "connect", "timeout", "offline", "fetch failed")):
            raise BrainOffline(stderr.strip())
        yield {"type": "error", "text": stderr[:200] or "Something went wrong."}
```

### SSE endpoint skeleton

```python
# server.py — GET /api/stream/<job_id>
_DONE = object()

def _sse_stream(self, job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        self._send(404, b'{"error":"not found"}')
        return
    # SSE headers — NEVER use _send here
    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream")
    self.send_header("Cache-Control", "no-cache")
    self.send_header("Connection", "keep-alive")
    self.end_headers()
    while True:
        try:
            event = job.q.get(timeout=25)
        except queue.Empty:
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
```

### Origin check (SEC-01)

```python
# server.py — add to top of do_POST and do_GET
_ALLOWED_ORIGINS = frozenset({"http://127.0.0.1:8765", "http://localhost:8765"})

# In do_POST and do_GET, before routing:
origin = self.headers.get("Origin", "")
if origin and origin not in _ALLOWED_ORIGINS:
    self._send(403, b'{"error":"forbidden"}')
    return
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact on Phase 1 |
|--------------|------------------|--------------|-------------------|
| `subprocess.run` (blocking) | `subprocess.Popen` (streaming) | Phase 1 | Enables line-by-line NDJSON parsing |
| Global `_brain` + `_brain_lock` | `SessionStore` dict with per-session Brain | Phase 1 | Eliminates 600s lock contention; fixes MCP pipe race |
| `/api/ask` (blocking, returns when done) | `/api/turn` (returns job_id) + `/api/stream/<id>` (SSE) | Phase 1 | UI unblocks; browser sees progress events |
| No Origin check | `Origin` header check on all POST/GET endpoints | Phase 1 | Closes DNS-rebinding/CSRF vector (SEC-01) |

**`--output-format json` → `stream-json`:** The only change to the CLI flags is the format flag and adding `--verbose`. All other flags (`--resume`, `--mcp-config`, `--strict-mcp-config`, `--allowedTools`, `--system-prompt`) are unchanged.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `claude` CLI | `brain.think_stream()` | Yes | 2.1.150 | None — required |
| Python 3.9.6 | All backend | Yes | 3.9.6 | None — required |
| Python stdlib: `queue`, `threading`, `uuid`, `subprocess`, `json` | server.py + brain.py | Yes (stdlib) | — | None needed |
| `mcp_config.json` | Computer-use turns | Yes (exists) | — | Gracefully skipped if absent |

**stream-json + --verbose confirmed working on this machine at claude CLI 2.1.150.**

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `type: "tool_result"` with `content[].type == "image"` carries screenshot base64 for computer-use turns | Code Examples / think_stream() | Screenshots won't forward to browser; activity panel won't show them. Detect by running one actual computer-use turn and inspecting raw NDJSON. |
| A2 | `type: "assistant"`, `content[].type == "tool_use"` appears for tool invocations in computer-use turns | Code Examples / think_stream() | Tool step labels won't appear in activity panel. Same detection path as A1. |
| A3 | The per-Brain `threading.Lock` introduced in Phase 1 doesn't exist in current `brain.py` and must be added | Architecture Patterns | Without it, concurrent turns on same session corrupt session_id. Verify by reading brain.py (confirmed: current Brain has no lock; one must be added). |

---

## Open Questions (RESOLVED)

1. **Empirical verification of computer-use event shapes (A1, A2)** — RESOLVED: deferred to first-run debug logging. Plan 01-02 Task 2 adds a `JARVIS_STREAM_DEBUG` mode that dumps raw NDJSON lines so the `tool_use`/`tool_result` shapes are confirmed on the first real computer-use turn; parsing is defensive (`.get()` at every level) so unknown shapes degrade gracefully rather than crashing.
   - What we know: Simple text-only turns verified empirically
   - What's unclear: Exact field names for `tool_use` and `tool_result` content blocks in a real computer-use turn
   - Disposition: debug logging in Plan 01-02 + defensive parsing; no extra research pass needed

2. **SessionStore TTL / cleanup** — RESOLVED: skipped for Phase 1, deferred to Phase 2. Plan 01-03 threat model (T-01-05) accepts unbounded `_sessions`/`_jobs` growth as non-critical for a single user and defers TTL cleanup to Phase 2.
   - What we know: `_sessions` dict will grow one Brain per session_token forever
   - What's unclear: Whether TTL cleanup is needed for Phase 1 (single user, one session at a time)
   - Disposition: skip TTL in Phase 1; revisit in Phase 2

3. **TCP_NODELAY / Nagle buffering** — RESOLVED: set explicitly at startup. Plan 01-03 Task 1 adds `httpd.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)` in `main()` — safe regardless of `ThreadingHTTPServer` defaults.
   - What we know: PITFALLS.md recommends `socket.TCP_NODELAY` to defeat Nagle on SSE connections
   - What's unclear: Whether `ThreadingHTTPServer` already sets this, or if it must be set at server startup
   - Disposition: set it explicitly in Plan 01-03

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | None declared (standalone test scripts only per CONCERNS.md) |
| Config file | none |
| Quick run command | `python test_server_streaming.py` (to be created in Wave 0) |
| Full suite command | `python test_server_streaming.py && python selftest.py` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CORE-01 | POST /api/turn returns immediately (< 1s) even while brain runs | integration | `python test_server_streaming.py::test_turn_nonblocking` | No — Wave 0 |
| CORE-01 | UI thread not blocked: second request during active turn gets response | integration | `python test_server_streaming.py::test_concurrent_request_not_blocked` | No — Wave 0 |
| CORE-02 | GET /api/stream/<id> receives multiple data: events before "done" | integration | `python test_server_streaming.py::test_sse_events_incremental` | No — Wave 0 |
| CORE-02 | Events arrive with correct type fields (text, tool_use, result, done) | unit | `python test_brain_stream.py::test_event_types` | No — Wave 0 |
| CORE-03 | Two turns on same session_token queue (second starts only after first finishes) | integration | `python test_server_streaming.py::test_concurrent_turns_serialize` | No — Wave 0 |
| CORE-03 | Two turns on different session_tokens run in parallel (no cross-blocking) | integration | `python test_server_streaming.py::test_different_sessions_parallel` | No — Wave 0 |
| SEC-01 | POST /api/turn with foreign Origin returns 403 | unit | `python test_server_streaming.py::test_origin_check_post` | No — Wave 0 |
| SEC-01 | GET /api/stream/<id> with foreign Origin returns 403 | unit | `python test_server_streaming.py::test_origin_check_get` | No — Wave 0 |
| SEC-01 | POST with no Origin header passes through (same-origin curl) | unit | `python test_server_streaming.py::test_origin_check_no_header` | No — Wave 0 |

### How to Validate Each Success Criterion

**"UI doesn't freeze during a turn":**
- Automated: Start server; POST /api/turn with a mock slow brain (sleep 5s); immediately GET /api/health — must return 200 within 1s while turn is in flight.
- Manual: Open browser; start a computer-use turn; verify you can type in the input box and click "New Chat" while the spinner runs.

**"Text + tool-call step labels arrive as they happen":**
- Automated: Open SSE connection; send turn with mock brain that yields 3 events over 3 seconds; assert all 3 `data:` lines are received before the `event: done` line. Measure timing: first event must arrive < 500ms after first mock yield.
- Manual: DevTools → Network → select the `/api/stream/<id>` request → EventStream tab → watch events arrive in real time.

**"Cross-origin page gets 403":**
- Automated: Python `http.client` or `urllib` to POST to `/api/turn` with `Origin: http://evil.com` header — assert 403 response.
- Manual: Open Chrome DevTools console on any page; `fetch('http://127.0.0.1:8765/api/turn', {method:'POST', headers:{Origin:'http://evil.com'}, body:JSON.stringify({text:'hi'})})` — assert network error (blocked) or 403.

**"Two near-simultaneous turns serialize safely":**
- Automated: Fire two concurrent HTTP requests to /api/turn with same session_token; open both SSE streams; assert both complete with valid `result` events (no garbled JSON or error events).
- Manual: Open two browser tabs; start a turn in tab 1; immediately start a turn in tab 2 with same session — tab 2's turn starts only after tab 1 completes.

### Wave 0 Gaps

- [ ] `test_server_streaming.py` — integration tests for all requirements (use `threading.Thread` to run the server locally and `http.client` for requests)
- [ ] `test_brain_stream.py` — unit tests for `think_stream()` parsing using a mock subprocess that emits controlled NDJSON lines

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Localhost-only; no user accounts |
| V3 Session Management | Partial | session_token in request body (browser-generated UUID); no expiry needed for single-user |
| V4 Access Control | Yes | Origin header check — prevents cross-origin requests from triggering Mac control |
| V5 Input Validation | Yes | `text.strip()` already applied; add length cap in /api/turn (e.g., 10,000 chars) |
| V6 Cryptography | No | No secrets stored; session_token is not a security boundary |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| DNS rebinding — evil.com resolves to 127.0.0.1 | Spoofing | `Origin` header check (SEC-01); block non-whitelisted origins |
| CSRF — malicious page POSTs to /api/turn | Tampering | Same `Origin` check; no cookies, so standard CSRF tokens not needed |
| Long-string DoS via /api/turn | DoS | Add `len(text) > 10_000` guard in do_POST before spawning brain thread |
| Stale job_ids accumulating in _jobs dict | DoS (minor) | TTL not critical for Phase 1 (single user); add cleanup in Phase 2 |

---

## Sources

### Primary (HIGH confidence)

- `brain.py` — read directly (current `think()` implementation, `_build_cmd` signature, `COMPUTER_TOOLS` list, `BrainOffline` exception)
- `server.py` — read directly (current `_send` helper conflict, `_brain_lock` usage, existing endpoint structure)
- `claude --output-format stream-json --verbose` — **empirically run in this session 2026-06-05** (verified: requires `--verbose`; verified event schema for system/assistant/result types; verified `session_id` location in result event)
- `.planning/research/ARCHITECTURE.md` — prior research, design already done and finalized
- `.planning/research/PITFALLS.md` — prior research, SSE/lock/origin pitfalls
- `.planning/research/STACK.md` — prior research, stack constraints

### Secondary (MEDIUM confidence)

- `.planning/codebase/ARCHITECTURE.md` — existing system architecture
- `.planning/codebase/CONCERNS.md` — known bugs and tech debt

### Tertiary (LOW / ASSUMED)

- tool_use and tool_result event shapes for computer-use turns — [ASSUMED from ARCHITECTURE.md training-data notes; not empirically verified in this session]

---

## Metadata

**Confidence breakdown:**
- stream-json event schema (text turns): HIGH — empirically verified 2026-06-05
- stream-json event schema (tool_use / tool_result): MEDIUM — architecture docs, not verified
- SSE/Job-queue pattern: HIGH — stdlib docs + prior research
- Origin check implementation: HIGH — standard HTTP, documented in PITFALLS.md
- Per-session Brain / SessionStore: HIGH — direct read of server.py + CONCERNS.md

**Research date:** 2026-06-05
**Valid until:** 2026-07-05 (claude CLI version pinned at 2.1.150; stream-json schema could change on CLI update)
