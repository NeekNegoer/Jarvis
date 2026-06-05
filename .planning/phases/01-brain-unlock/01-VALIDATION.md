---
phase: 1
slug: brain-unlock
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-05
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `01-RESEARCH.md` → Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` (Wave 0 installs into the 3.9 venv if missing) with plain-script fallback — matches the project's existing `python test_*.py` convention |
| **Config file** | none — Wave 0 adds tests only, no global config |
| **Quick run command** | `.venv/bin/python -m pytest test_server_streaming.py test_brain_stream.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest test_server_streaming.py test_brain_stream.py -q && .venv/bin/python selftest.py` |
| **Estimated runtime** | ~15–25 seconds (server spun up in-thread per test) |

---

## Sampling Rate

- **After every task commit:** Run the quick command.
- **After every plan wave:** Run the full suite command.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** ~25 seconds.

---

## Per-Requirement Verification Map

Task IDs are assigned during planning; each row below MUST map to at least one task's `<automated>` verify.

| Requirement | Behavior | Test Type | Automated Command | File (Wave 0) | Status |
|-------------|----------|-----------|-------------------|---------------|--------|
| CORE-01 | `POST /api/turn` returns immediately (<1s) while the brain runs | integration | `pytest test_server_streaming.py -k turn_nonblocking` | `test_server_streaming.py` ❌ W0 | ⬜ pending |
| CORE-01 | A second request (e.g. `/api/health`) during an active turn is not blocked | integration | `pytest test_server_streaming.py -k concurrent_request_not_blocked` | `test_server_streaming.py` ❌ W0 | ⬜ pending |
| CORE-02 | `GET /api/stream/<id>` receives multiple `data:` events before `done` | integration | `pytest test_server_streaming.py -k sse_events_incremental` | `test_server_streaming.py` ❌ W0 | ⬜ pending |
| CORE-02 | `think_stream()` emits typed events (`text`, `tool_use`, `result`, `done`) parsed from NDJSON | unit | `pytest test_brain_stream.py -k event_types` | `test_brain_stream.py` ❌ W0 | ⬜ pending |
| CORE-03 | Two turns on the same `session_token` serialize (2nd starts after 1st finishes) | integration | `pytest test_server_streaming.py -k concurrent_turns_serialize` | `test_server_streaming.py` ❌ W0 | ⬜ pending |
| CORE-03 | Two turns on different `session_token`s do not cross-block | integration | `pytest test_server_streaming.py -k different_sessions_parallel` | `test_server_streaming.py` ❌ W0 | ⬜ pending |
| SEC-01 | `POST /api/turn` with a foreign `Origin` returns 403 | unit | `pytest test_server_streaming.py -k origin_check_post` | `test_server_streaming.py` ❌ W0 | ⬜ pending |
| SEC-01 | `GET /api/stream/<id>` with a foreign `Origin` returns 403 | unit | `pytest test_server_streaming.py -k origin_check_get` | `test_server_streaming.py` ❌ W0 | ⬜ pending |
| SEC-01 | Same-origin / no-Origin request passes through | unit | `pytest test_server_streaming.py -k origin_check_no_header` | `test_server_streaming.py` ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `test_server_streaming.py` — integration tests (run the server in a `threading.Thread`; drive it with `http.client`/`urllib`; use a fast **mock brain** so no real `claude` call is needed).
- [ ] `test_brain_stream.py` — unit tests for `Brain.think_stream()` NDJSON parsing using a mock `subprocess` that emits controlled `stream-json --verbose` lines (including a `thinking` block that must be filtered, an `assistant` text block, and a `result` block).
- [ ] `pytest` available in `.venv` (install if missing — pure-Python, 3.9-compatible).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| UI genuinely doesn't freeze during a real computer-use turn | CORE-01 | Needs a real Mac-control turn + a human watching the browser | Open the UI, start "open Safari and …", then type in the input + click "new" while it runs — both respond. |
| Real `tool_use`/screenshot event shapes parse correctly | CORE-02 | The empirical schema check was a text turn; tool/screenshot blocks are MEDIUM confidence | First real computer-use turn: enable debug logging of raw NDJSON lines; confirm tool steps + inline screenshot render. |

---

## Validation Sign-Off

- [ ] All tasks have an `<automated>` verify or a Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without an automated verify
- [ ] Wave 0 covers all MISSING test files
- [ ] No watch-mode flags
- [ ] Feedback latency < 25s
- [ ] `nyquist_compliant: true` set in frontmatter once plans map every row to a task

**Approval:** pending
