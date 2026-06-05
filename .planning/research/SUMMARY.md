# Project Research Summary — Jarvis Milestone 2

**Project:** Jarvis Milestone 2 | **Domain:** Bilingual macOS voice assistant — Chrome PWA + SSE streaming + extensible skills + Google Classroom + echo cancellation | **Researched:** 2026-06-05 | **Confidence:** HIGH overall; MEDIUM on the `claude` CLI stream-json event schema and Google OAuth scope classification

---

## Executive Summary

Milestone 2 is a brownfield robustness and extension layer on a complete v1 codebase. The two hardest problems are the **brain-lock refactor** (`server.py` holds `_brain_lock` for the entire turn — up to 600 s on computer-use — and must be replaced by a per-session Brain + job-queue architecture before any streaming UI can work) and **Google OAuth on Python 3.9** (the latest `google-auth` family dropped 3.9 support at versions 2.50.0 / 1.4.0 / 0.4.0; three packages must be pinned to last 3.9-compatible releases, live-verified via the PyPI JSON API on 2026-06-05). Every other feature is low-risk with well-established stdlib patterns.

The recommended approach is strict dependency order: unlock the server first (job registry + SSE endpoint), wire the streaming brain, then build the browser activity panel. Skills and PWA are independent tracks that can proceed in parallel with streaming and merge cleanly at the end. Google Classroom is the only new external dependency and sits entirely inside the skill system, so its risk is isolated. Echo cancellation requires no new packages — the correct fix is a `threading.Event` gate on the Python mic; browser `echoCancellation: true` does NOT reach the `sounddevice` capture path.

The project-level constraint shaping every decision: Python 3.9.6 venv, no asyncio event-loop sharing with `ThreadingHTTPServer`, no official `mcp` SDK (requires 3.10+), no paid APIs, no HTTPS required (Chrome grants secure context to `127.0.0.1`). All patterns are stdlib-only except the four pinned Google packages.

---

## Recommended Build Order

Derived from ARCHITECTURE.md dependency table:

| # | Step | Depends On |
|---|------|-----------|
| 1 | **Job registry + SessionStore** in `server.py` | Nothing — existing `server.py` only |
| 2 | **`POST /api/turn` + `GET /api/stream/<id>` SSE** | Step 1 |
| 3 | **`Brain.think_stream()`** (NDJSON → typed ActivityEvents) | Step 2 |
| 4 | **Browser SSE client + activity panel** | Steps 2+3 |
| 5 | **`skills/_loader.py` + manifest schema** | Nothing — parallel track |
| 6 | **Brain skill integration** (`load_skills()` at init) | Steps 3+5 |
| 7 | **Google Classroom skill** (manifest + server.py + auth.py) | Step 5 (loader contract stable) |
| 8 | **PWA manifest + icons** | Nothing — static files only |
| 9 | **Service worker** | Step 8 (manifest stable) + Step 2 (API paths stable) |
| 10 | **Echo cancellation** (`/api/tts_start`, `/api/tts_end` + Event gate) | Steps 1+4 (SSE infra + app.js posting) |

**Hard dependency chain:** SSE (step 2) must precede inline screenshots (step 4); skill loader (step 5) must precede the Classroom skill (step 7).

---

## The "Do NOT" List

| Do NOT | Why It Fails | Do This Instead |
|--------|-------------|----------------|
| Drop the brain lock without a single-writer queue | Two concurrent `claude` processes share one `computer_use_server.py` stdio pipe → garbled JSON-RPC, silent computer-use failures | Per-session Brain with own lock, OR single-writer job queue (one `claude` process active at a time) |
| Cache `/api/*` in the service worker | Caches stale API responses; SSE streams intercepted by the SW never reach the server | Explicit static-paths allowlist; unconditional network pass-through for anything under `/api/` |
| Rely on `getUserMedia({ echoCancellation: true })` for the native mic | Browser AEC only applies to the browser's capture stream; Python `sounddevice` reads CoreAudio independently with no coordination | `threading.Event` gate on `ears.py`/`wake.py`, toggled via `/api/tts_start` and `/api/tts_end` |
| Auto-submit assignments through Jarvis | Unrecoverable if wrong; academic-integrity risk | Jarvis opens the assignment URL; Pietro submits manually |

---

## Google Auth Version Pins (Python 3.9 — non-negotiable)

```
google-api-python-client==2.197.0   # latest; >=3.7 safe
google-auth-oauthlib==1.3.1          # LAST 3.9-compat; 1.4.0 requires 3.10+
google-auth-httplib2==0.3.1          # LAST 3.9-compat; 0.4.0 requires 3.10+
google-auth==2.49.2                  # LAST 3.9-compat; 2.50.0+ requires 3.10+
```

**OAuth 7-day refresh-token risk:** Classroom read-only scopes are classified as "sensitive" by Google. Unverified apps in Testing status cannot hold permanent refresh tokens — `token.json` becomes invalid after 7 days with `401 invalid_grant`. Mitigation: catch `google.auth.exceptions.RefreshError`, delete `token.json`, re-trigger the local browser auth flow. Document the weekly re-auth expectation. Store `credentials.json` and `token.json` in `~/.config/jarvis/` — NOT in the project directory; add both to `.gitignore` before the files exist.

---

## Suggested Phases (5 total)

**Phase 1 — Brain Unlock:** Job registry + SessionStore + `POST /api/turn` + `GET /api/stream/<id>` + `Brain.think_stream()` + Origin CSRF check. No dependencies. Unlocks everything else.

**Phase 2 — Live Activity UI:** Browser SSE client, activity panel, tool-call badges, elapsed timer, collapsible steps, inline screenshots, error chips. Depends on Phase 1 SSE being stable. Inline screenshots are the highest-impact differentiator — build in this phase, not deferred.

**Phase 3 — Skill System + Google Classroom:** `skills/_loader.py`, Brain integration, Classroom manifest/server/auth. Parallel to Phases 1–2; placed here to isolate the only external-service dependency. Pin package versions and run `pip install` in the 3.9 venv as the very first step.

**Phase 4 — PWA:** `web/manifest.json` + icons + `web/sw.js` (~30 lines, hand-written — no Workbox). Parallel; SW allowlist finalized after Phase 1 stabilizes API paths. Validate with DevTools → Application → Manifest → Installability before shipping.

**Phase 5 — Echo Cancellation + Polish:** `/api/tts_start` + `/api/tts_end` + `threading.Event` gate in `ears.py`/`wake.py`, 10 s timeout fallback, SW cache-version bump. Depends on SSE infra (Phase 1) and app.js (Phase 2).

---

## Research Flags

**Needs targeted validation before implementation:**
- **Phase 3 (Google OAuth):** Verify current Classroom scope sensitivity classifications at `https://developers.google.com/classroom/reference/rest` — determines whether the 7-day expiry applies. Verify `requires_python` at pip install time.
- **Phase 1 (stream-json schema):** the `claude` CLI intermediate NDJSON event field names are MEDIUM confidence. Parse defensively; log raw lines in debug mode on first run; adjust field paths before finalizing the ActivityEvent contract.

**Standard patterns (no additional research needed):**
- **Phase 4 (PWA):** the W3C manifest + SW spec is fully defined; Chrome's localhost secure-context exception is documented.
- **Phase 1 SSE patterns:** stdlib `queue.Queue` + `text/event-stream` is a standard, well-specified pattern.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Google package versions live-verified via the PyPI JSON API; all stdlib patterns are 3.9-stable |
| Features | HIGH | Maps directly to the Active requirements in PROJECT.md; dependency chain fully traced |
| Architecture | HIGH/MEDIUM | SSE/queue/skill-loader HIGH; `claude` CLI stream-json intermediate shape MEDIUM |
| Pitfalls | HIGH/MEDIUM | `server.py` + CONCERNS.md read directly (HIGH); Google 7-day token policy from training data (MEDIUM — re-verify before OAuth) |

**Overall: HIGH.** One open input: confirm with Pietro which specific other Claude Code projects/skills to import via the skill bridge before the Phase 3 roadmap items are finalized.

---
*Sources: `.planning/research/STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md`. Synthesized 2026-06-05.*
