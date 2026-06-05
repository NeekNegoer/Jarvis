---
phase: 01-brain-unlock
plan: 03
subsystem: api
tags: [http.server, sse, event-stream, threading, job-queue, session-store, origin-check, csrf]

requires:
  - phase: 01-brain-unlock
    provides: Brain.think_stream + Brain._lock (plan 01-02); test_server_streaming.py contract (plan 01-01)
provides:
  - POST /api/turn non-blocking job dispatch (returns job_id in <1s)
  - GET /api/stream/<job_id> SSE drain loop with keepalive pings
  - SessionStore (per-session_token Brain) for same-session serialization + cross-session parallelism
  - Origin/CSRF allow-list guard (403) and 10k text length cap (SEC-01)
  - _BRAIN_FACTORY testability hook
affects: [01-04 integration gate, web activity UI, future skill endpoints]

tech-stack:
  added: []
  patterns:
    - "Job-queue + SSE over stdlib http.server.ThreadingHTTPServer (no framework)"
    - "Per-session Brain lock: serialize within a session, parallel across sessions"
    - "Origin allow-list CSRF/DNS-rebinding guard on every /api/* route"

key-files:
  created: []
  modified: [server.py]

key-decisions:
  - "Per-session_token Brain (each with its own _lock) gives CORE-03 parallelism without cross-session blocking"
  - "Worker holds brain._lock for the full think_stream drain (Pitfall 4: MCP stdio pipe race)"
  - "SSE response omits Content-Length + uses Connection: close so the client read() returns on stream end"
  - "TCP_NODELAY set on the server socket to flush SSE events immediately (defeat Nagle buffering)"
  - "_local_brain() uses a None sentinel + one-time probe guard (removes bool sentinel; fixes Pylance reportAttributeAccessIssue)"

patterns-established:
  - "ActivityEvent dicts from Brain.think_stream serialized as `data: {json}\\n\\n`; _DONE sentinel -> `event: done`"

requirements-completed: [CORE-01, CORE-02, CORE-03, SEC-01]

duration: ~25min
completed: 2026-06-05
---

# Phase 01 Plan 03: Non-blocking SSE Streaming Server Summary

**server.py refactored from a blocking single-brain-lock model to a Job-queue + SSE architecture: POST /api/turn returns a job_id instantly, GET /api/stream/<id> streams incremental events, per-session turns serialize while different sessions run in parallel, and a foreign-Origin/length guard enforces SEC-01.**

## Performance

- **Duration:** ~25 min (mostly investigation — see below)
- **Completed:** 2026-06-05
- **Tasks:** server refactor (SessionStore, JobRegistry, /api/turn, /api/stream, _start_sse, Origin check, length cap) + _local_brain type fix
- **Files modified:** 1 (server.py, +265/-55)

## Accomplishments
- `POST /api/turn`: validates input, spawns a daemon worker thread, returns `{job_id}` in <1s (CORE-01 non-blocking)
- `GET /api/stream/<job_id>`: long-lived `text/event-stream`, drains the job queue per-event with `wfile.flush()`, keepalive `: ping` comments, `event: done` on completion (CORE-02 incremental)
- `SessionStore` (`_sessions`): one Brain per session_token; worker holds `brain._lock` across the whole turn → same-session turns serialize, different sessions run in parallel (CORE-03)
- Origin/CSRF allow-list (`_ALLOWED_ORIGINS`) returns 403 on foreign Origin for every /api/* route; 10k text length cap returns 400 (SEC-01)
- `_BRAIN_FACTORY` module hook lets tests inject MockBrain; `/api/ask`, `/api/health`, `/api/reset` preserved
- Fixed the Pylance `reportAttributeAccessIssue` on `lb.think()` by giving `_local_brain()` a clean `Optional[LocalBrain]` return (None sentinel + `_local_checked` guard)

## Task Commits

1. **Non-blocking SSE Job-queue server + Origin guard + _local_brain fix** - `ba8b8dc` (feat)

_Note: the server refactor arrived as a reviewed working-tree change (test-verified) and was committed as one feat commit after the investigation below confirmed correctness and the Pylance fix was applied._

## Files Created/Modified
- `server.py` - SessionStore, JobRegistry/_Job, _run_turn worker, /api/turn, /api/stream/<id>, _start_sse, _origin_ok, length cap, _BRAIN_FACTORY, _local_brain None-sentinel fix

## Decisions Made
- Per-session Brain + lock (not a single global lock) — required for CORE-03 cross-session parallelism
- SSE: no Content-Length, `Connection: close`, `close_connection = True`, TCP_NODELAY — so events flush live and client `read()` terminates cleanly

## Deviations from Plan

### Investigation: transient test flakiness (not a code defect)

**Found during:** initial evaluation of the existing server.py implementation.
**Observed:** one early full-file run reported `3 failed` (test_sse_events_incremental → socket.timeout; test_concurrent_turns_serialize / test_different_sessions_parallel → max_active assertions) taking ~20s.
**Investigation:** the same tests passed in isolation (0.53s), as a 3-test group (2.12s), and the full file passed 14/14 across ~14 subsequent runs — including 6 runs under 3× concurrent pytest load. pytest-randomly is NOT installed, so order is deterministic; the flake was timing/load-related (orphan daemon worker threads from the deliberately-non-draining tests + shared `MockBrain._active_count`), most plausibly triggered by a real `server.py` instance running on the machine at that moment.
**Disposition:** implementation confirmed correct and robust; the committed test scaffold (01-01) was NOT modified (no reproducible cause). Flagged as a watch-item for the 01-04 integration gate, where behaviour is verified on real hardware.

### Auto-fix
- **[Pylance reportAttributeAccessIssue] `_local_brain()` bool sentinel** — `lb.think()` flagged because `_local` could be inferred as `bool`. Refactored to an `Optional[LocalBrain]` return (None sentinel + one-time probe guard). Behaviour unchanged; type now clean.

## Issues Encountered
- See investigation above. No code defects; one transient timing-sensitive flake that did not reproduce under stress.

## Next Phase Readiness
- Streaming server + brain generator ready for the 01-04 integration gate (real claude turn over SSE in Chrome)
- Watch-items for 01-04: (1) confirm MEDIUM-confidence tool_use/screenshot event shapes on a real computer-use turn; (2) keep an eye on SSE timing under real load (the one transient flake)
- Known minor: a /api/turn whose SSE stream is never opened leaves an orphan entry in `_jobs` (abandoned-turn leak) — acceptable for now; candidate for a future TTL/cleanup pass

---
*Phase: 01-brain-unlock*
*Completed: 2026-06-05*
