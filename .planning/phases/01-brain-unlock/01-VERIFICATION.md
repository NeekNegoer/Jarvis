---
status: passed
phase: 01-brain-unlock
verified: 2026-06-05
verifier: inline (orchestrator, with live human checkpoint)
requirements_verified: [CORE-01, CORE-02, CORE-03, SEC-01]
must_haves_met: 4/4 success criteria
automated_tests: "14 passed (test_brain_stream + test_server_streaming); selftest 12 passed"
---

# Phase 1: Brain Unlock — Verification

**Goal:** The server processes turns without freezing, streams incremental events to the
browser, serializes concurrent turns safely, and rejects cross-origin requests.

**Verdict: PASSED** — all four success criteria are true, with two honest notes carried to Phase 2.

## Success Criteria (goal-backward)

### 1. Browser does not freeze during a turn (CORE-01) — ✅ PASSED
- **Automated:** `test_turn_nonblocking` (POST /api/turn returns <1s while the brain runs),
  `test_concurrent_request_not_blocked` (GET /api/health <1s while a turn is in flight).
- **Human (real Chrome):** during a Mac-control turn ("abra o Safari…"), typing and **New Chat**
  both respond immediately. Confirmed by Pietro: "teste 1: passou".
- **Enabler:** required a gap-closure — `web/app.js` was migrated from the blocking `/api/ask`
  to `/api/turn` + `/api/stream` (commit `ad42d7d`); `newChat()` now aborts the stream mid-turn.

### 2. Incremental text + tool-call step labels arrive as they happen (CORE-02) — ✅ PASSED (note)
- **Automated:** `test_sse_events_incremental` (≥2 `data:` events + `event: done` over SSE).
- **Human + evidence:** `stream_debug.ndjson` from a real turn shows tool steps then text arriving
  in sequence over the turn (ToolSearch → run_applescript → text → result).
- **Note (granularity):** the `claude` CLI emits whole **messages**, not token deltas (0 delta
  events observed). So incremental UX is per message/step — the finest granularity the CLI offers.
  A single-message reply renders at once. Pietro accepted this; rich live visualization is the
  explicit scope of **Phase 2 — Live Activity UI**.

### 3. Cross-origin page cannot POST to /api/turn or /api/ask — 403 (SEC-01) — ✅ PASSED
- **Automated:** `test_origin_check_post` (403 on foreign Origin POST), `test_origin_check_get`
  (403 on foreign Origin GET /api/stream), `test_origin_check_no_header` (same-origin passes),
  `test_length_cap` (400 over 10k chars).
- **Manual:** the apple.com console fetch was blocked by that site's CSP one layer before reaching
  the server — also blocked, different mechanism. Our 403 is proven by the automated test.

### 4. Same-session turns serialize; different sessions run in parallel (CORE-03) — ✅ PASSED
- **Automated:** `test_concurrent_turns_serialize` (same session_token → max_active ≤ 1, no MCP
  pipe corruption), `test_different_sessions_parallel` (different tokens → max_active ≥ 2).
- **Mechanism:** per-session `Brain` in `SessionStore`; the worker holds `brain._lock` across the
  whole `think_stream` drain.

## Requirement Traceability
| Req | Where delivered | Status |
|-----|-----------------|--------|
| CORE-01 | server.py /api/turn non-blocking worker; app.js non-freeze | ✅ |
| CORE-02 | brain.py think_stream; server.py /api/stream SSE; app.js EventSource | ✅ (message-level) |
| CORE-03 | server.py SessionStore + per-Brain lock | ✅ |
| SEC-01 | server.py Origin allow-list (403) + 10k length cap | ✅ |

## Carry-forward to Phase 2 (not Phase 1 regressions)
1. `think_stream` does not yet emit `screenshot` events — the `tool_result`/image shape was
   corrected in `stream_debug_findings.md`; Phase 2 (which renders screenshots) implements it and
   confirms the image base64 path on a real `screenshot`-tool turn.
2. Minor: a `/api/turn` whose SSE stream is never opened leaves an orphan entry in `_jobs`
   (abandoned-turn leak) — candidate for a TTL/cleanup pass.

## Automated Evidence
```
.venv/bin/python -m pytest test_brain_stream.py test_server_streaming.py -q  →  14 passed
.venv/bin/python selftest.py                                                 →  12 passed, 0 failed
import assertion (Brain.think + Brain.think_stream present)                  →  OK
```
