# Stack Research

**Domain:** Localhost bilingual voice assistant — milestone 2 additions (PWA, SSE streaming, skill system, Google Classroom, echo cancel)
**Researched:** 2026-06-05
**Confidence:** HIGH (streaming/PWA/skill patterns), HIGH (Google package version pin), MEDIUM (Classroom OAuth scopes — training-data verified, not live-docs)

---

## Existing Stack (DO NOT DUPLICATE)

See `.planning/codebase/STACK.md` for the full v1 inventory (mlx-whisper, sounddevice, pyobjc, pynput, ThreadingHTTPServer, etc.). This file covers **only the net-new additions for milestone 2**.

---

## Recommended Stack — Milestone 2 Additions

### 1. PWA (Installable Chrome App)

| Asset | Version/Standard | Purpose | Why |
|-------|-----------------|---------|-----|
| `web/manifest.json` | W3C Web App Manifest | PWA identity, standalone display, icons | Built-in; zero deps; Chrome on localhost (127.0.0.1) grants secure context without HTTPS |
| `web/sw.js` | Service Workers API | Cache static assets; pass-through `/api/*` | Built-in; enables install prompt; explicit network-only for SSE prevents caching bugs |
| `web/icons/icon-192.png` + `icon-512.png` | PNG | Required icon sizes for Chrome install | Chrome requires both sizes; generate with any image tool |

**No new pip packages.** No new JS deps. Static files only.

Manifest minimum shape:
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

Service worker strategy: cache-first for static paths in a known allowlist; explicit `fetch(e.request)` pass-through for `/api/*` (never cache SSE streams or API responses).

---

### 2. Live Activity Streaming

| Component | Technology | Why |
|-----------|-----------|-----|
| Transport | SSE (`text/event-stream`) via stdlib `ThreadingHTTPServer` | WebSocket requires a third-party library (websockets, aiohttp); SSE is one-way server→browser which is all we need; works over plain HTTP on 127.0.0.1; survives browser reconnect natively |
| Python process model | `subprocess.Popen` reading stdout line-by-line (blocking loop in daemon thread) | asyncio subprocess requires Python 3.10+ event loop changes and complicates the existing sync codebase; Popen + daemon thread is simpler, 3.9-compatible, and already the pattern in `brain.py` |
| Event queue | `queue.Queue` (stdlib) | Thread-safe; no external dep; SSE handler blocks on `q.get(timeout=25)` for keepalive heartbeats |
| Job registry | `dict[str, Job]` + `threading.Lock` in server.py | Lightweight; per-turn job IDs decouple POST (create job) from GET (drain SSE) |
| Brain output format | `--output-format stream-json` (claude CLI flag) | Emits NDJSON line-by-line; parse defensively — extract `type`, `message.content`, `result`, `session_id`; discard unknown fields |

**No new pip packages.** All stdlib (`queue`, `threading`, `uuid`, `json`, `subprocess`).

---

### 3. Extensible Skill System

| Component | Approach | Why |
|-----------|---------|-----|
| Discovery | `skills/_loader.py` scans `skills/*/manifest.json` at startup | File-based; adding a skill = drop a folder; no registry, no database |
| MCP protocol | Hand-rolled JSON-RPC 2.0 over stdio (same as `computer_use_server.py`) | Official `mcp` SDK requires Python 3.10+; the existing pattern works and is already understood by the codebase |
| Config aggregation | Generates `skills/_generated_mcp_config.json` at startup | Brain passes a single `--mcp-config` path; gitignore the generated file |
| Skill isolation | Each skill is its own `skills/<id>/server.py` process | Crashes in one skill don't affect others; claude CLI manages MCP process lifecycle |

**No new pip packages** for the loader or skill framework itself.

---

### 4. Google Classroom Skill

This is the only new pip dependency group. **Constraint: Python 3.9.6 — pin to the last compatible versions.**

| Package | Pin | Why This Version |
|---------|-----|-----------------|
| `google-api-python-client` | `==2.197.0` | Latest; requires >=3.7 — 3.9 safe. Provides `build()` for Classroom REST API v1 |
| `google-auth-oauthlib` | `==1.3.1` | **Last release with `requires_python>=3.9`; version 1.4.0 dropped to >=3.10** |
| `google-auth-httplib2` | `==0.3.1` | **Last release with `requires_python>=3.9`; version 0.4.0 dropped to >=3.10** |
| `google-auth` | `==2.49.2` | **Last release with `requires_python>=3.8` (supports 3.9); version 2.50.0+ requires >=3.10** |

**Install command (for `skills/google-classroom/requirements.txt`):**
```
google-api-python-client==2.197.0
google-auth-oauthlib==1.3.1
google-auth-httplib2==0.3.1
google-auth==2.49.2
```

```bash
# from project root:
pip install -r skills/google-classroom/requirements.txt
```

#### OAuth Setup

- **Client type:** Desktop app (previously "Other") in GCP Console. Download `credentials.json` → place at `skills/google-classroom/credentials.json` (gitignored).
- **Auth flow:** `InstalledAppFlow.from_client_secrets_file()` from `google-auth-oauthlib`. Opens browser once; saves `token.json` (gitignored). `auth.py` refreshes automatically on expiry.
- **Token storage:** `skills/google-classroom/token.json` — gitignore both `credentials.json` and `token.json`.

#### Minimal Read-Only Scopes

```python
SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
]
```

| Scope | Grants Access To |
|-------|-----------------|
| `classroom.courses.readonly` | `courses.list` — all enrolled courses |
| `classroom.coursework.me.readonly` | `courses.courseWork.list` — Pietro's assignments per course |
| `classroom.announcements.readonly` | `courses.announcements.list` — announcements per course |

**Confidence on scopes: MEDIUM** — matches Google Classroom API v1 documentation from training data (August 2025 cutoff); verify against https://developers.google.com/classroom/reference/rest/v1/courses/list before setup.

If submission status (turned in / graded) is needed later, add `classroom.student-submissions.me.readonly`.

---

### 5. Echo Cancellation

No new packages needed. Two-layer approach:

| Layer | Mechanism | Why |
|-------|----------|-----|
| Browser (`web/app.js`) | `getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })` | Chrome's built-in AEC; effective for the web UI path; zero deps |
| Native `ears.py` | Suppress mic capture while TTS is playing (gate the `sounddevice` recording loop on a `_tts_active` threading.Event) | The simplest robust fix; avoids complex DSP; no new packages; works with existing `sounddevice` stream |

**Do NOT** add `webrtcvad`, `pyaudio`, or any DSP library for echo cancellation — they add C extension deps that may not install without admin or conflict with the existing `mlx-whisper` / `sounddevice` stack. The gating approach is sufficient for a personal tool.

---

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| SSE (`text/event-stream`) | WebSocket (`websockets` pip package) | Requires external dep; bidirectional is overkill — brain → browser is one-way; SSE reconnects automatically |
| `subprocess.Popen` + daemon thread | `asyncio` subprocess | `asyncio` subprocess in Python 3.9 has subtle event-loop-sharing issues with `ThreadingHTTPServer`; Popen + thread matches the existing sync architecture |
| Hand-rolled JSON-RPC MCP | Official `mcp` SDK | Requires Python 3.10+; already excluded |
| `google-auth-oauthlib==1.3.1` | 1.4.0 (latest) | 1.4.0 requires Python 3.10+ — breaks the venv |
| `google-auth==2.49.2` | 2.53.0 (latest) | 2.50.0+ requires Python 3.10+ — breaks the venv |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `google-auth >= 2.50.0` | Requires Python >=3.10; will refuse to install on 3.9 | `google-auth==2.49.2` |
| `google-auth-oauthlib >= 1.4.0` | Requires Python >=3.10 | `google-auth-oauthlib==1.3.1` |
| `google-auth-httplib2 >= 0.4.0` | Requires Python >=3.10 | `google-auth-httplib2==0.3.1` |
| `websockets` pip package | External dep for a one-way stream | SSE is stdlib-sufficient |
| `asyncio`-based streaming in server.py | Mixing asyncio event loop with `ThreadingHTTPServer` is fragile in 3.9 | `queue.Queue` + daemon thread |
| `webrtcvad` / `pyaudio` for echo cancel | C extensions; install complexity; not needed for gating approach | `threading.Event` gate on `sounddevice` recording |
| Official `mcp` SDK | Python 3.10+ only | Hand-rolled JSON-RPC 2.0 stdio (already working in codebase) |
| Any JS build step (webpack, vite, etc.) | Breaks the "no build" constraint; adds complexity | Vanilla ES2015+ modules in `web/*.js` |
| Computer-use screen-scraping for Classroom | Brittle; requires screen visible; slow | Classroom REST API v1 |

---

## Version Compatibility

| Package | Version | Python Constraint | Status |
|---------|---------|-------------------|--------|
| `google-api-python-client` | 2.197.0 | >=3.7 | Safe on 3.9 |
| `google-auth-oauthlib` | 1.3.1 | >=3.9 | Safe — last 3.9-compat release |
| `google-auth-httplib2` | 0.3.1 | >=3.9 | Safe — last 3.9-compat release |
| `google-auth` | 2.49.2 | >=3.8 | Safe on 3.9 — last pre-3.10-only release |
| All v1 deps (mlx-whisper, sounddevice, pyobjc, etc.) | Unchanged | As in codebase STACK.md | No conflict |

---

## Sources

- PyPI JSON API (`pypi.org/pypi/<pkg>/json`) — live-verified 2026-06-05 for all four google packages; `requires_python` field checked for every release in the 2.x/1.x range
- Chrome secure-context exception for 127.0.0.1 — Chrome developer docs; grants service worker + PWA install over plain HTTP on localhost (HIGH confidence)
- W3C Web App Manifest spec — `display: standalone`, icon size requirements (HIGH confidence)
- Google Classroom API v1 OAuth scopes — training data (August 2025); verify at https://developers.google.com/classroom/reference/rest before first run (MEDIUM confidence)
- `computer_use_server.py` existing JSON-RPC 2.0 pattern — live codebase (HIGH confidence; already proven working)
- Python stdlib docs — `queue.Queue`, `threading`, `subprocess.Popen`, `http.server.ThreadingHTTPServer` all 3.9-stable (HIGH confidence)

---

*Stack research for: Jarvis milestone 2 (PWA + SSE streaming + skill system + Google Classroom + echo cancellation)*
*Researched: 2026-06-05*
