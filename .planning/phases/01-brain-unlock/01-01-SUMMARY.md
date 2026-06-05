---
phase: "01"
plan: "01"
subsystem: brain-unlock
tags: [tdd, red-scaffold, testing, brain, server, streaming]
dependency_graph:
  requires: []
  provides: [test_brain_stream.py, test_server_streaming.py]
  affects: [brain.py, server.py]
tech_stack:
  added: [pytest>=8.4.2]
  patterns: [FakePopen, MockBrain, live_server fixture, SSE reading helper]
key_files:
  created:
    - test_brain_stream.py
    - test_server_streaming.py
  modified: []
decisions:
  - "pytest installed into project venv (3.9-compatible, no build step conflict)"
  - "Brain fixture stubs shutil.which to return /usr/bin/true to bypass real claude binary check"
  - "FakePopen.stdout uses iter(list(FAKE_LINES)) so each test fixture gets a fresh iterator"
  - "MockBrain class-level _active_count/_max_active counters support serialize vs. parallel overlap tests"
  - "live_server uses ephemeral port 0 to avoid port conflicts; getattr+sentinel pattern handles absent _BRAIN_FACTORY"
metrics:
  duration_minutes: 11
  completed_date: "2026-06-05"
  tasks_completed: 2
  files_created: 2
---

# Phase 1 Plan 1: TDD RED Scaffold Summary

**One-liner:** Wave 0 RED test scaffold — pytest suite encoding Brain.think_stream NDJSON contract + server streaming/Origin/session-serialization contracts; all 12 target tests fail naming the unimplemented symbols.

---

## What Was Built

Two pytest test files that encode the full behavioral contract for Phase 1 before any implementation work begins.

### test_brain_stream.py (215 lines)

Unit tests for `Brain.think_stream()` and `Brain._build_stream_cmd()` driven by a `FakePopen` mock that emits controlled NDJSON lines matching the empirically verified `claude --output-format stream-json --verbose` schema.

| Test | VALIDATION.md Row | Failure Reason (RED) |
|------|-------------------|----------------------|
| test_event_types | CORE-02 unit | `AttributeError: Brain has no 'think_stream'` |
| test_thinking_block_filtered | CORE-02 unit | `AttributeError: Brain has no 'think_stream'` |
| test_session_id_captured | CORE-02 unit | `AttributeError: Brain has no 'think_stream'` |
| test_build_stream_cmd_requires_verbose | CORE-02 unit | `AttributeError: Brain has no '_build_stream_cmd'` |
| test_has_per_brain_lock | CORE-02 unit | `AssertionError: Brain must have a _lock attribute` |

### test_server_streaming.py (472 lines)

Integration tests spinning up `server.Handler` on an ephemeral port via `live_server` fixture with `MockBrain` injected through `server._BRAIN_FACTORY`.

| Test | VALIDATION.md Row | Failure Reason (RED) |
|------|-------------------|----------------------|
| test_turn_nonblocking | CORE-01 | `/api/turn` → 404 (not routed yet) |
| test_concurrent_request_not_blocked | CORE-01 | `/api/turn` → 404 (PASSES: health returns in time, not 403) |
| test_sse_events_incremental | CORE-02 | `/api/turn` → 404, no job_id |
| test_origin_check_post | SEC-01 | `/api/turn` with evil origin → 404, not 403 |
| test_origin_check_get | SEC-01 | `/api/stream/anyid` with evil origin → 404, not 403 |
| test_origin_check_no_header | SEC-01 | PASSES: 404 != 403 (acceptable in RED state) |
| test_length_cap | SEC-01 | `/api/turn` → 404, not 400 |
| test_concurrent_turns_serialize | CORE-03 | `/api/turn` → 404 for both turns |
| test_different_sessions_parallel | CORE-03 | `/api/turn` → 404 for both turns |

**RED result summary:** 12 failed, 2 passed (both passes are design-correct: health reachability and no-origin-passthrough hold true even before Phase 1 implementation).

---

## Decisions Made

1. **pytest installed into project venv** — `pip install pytest` into `.venv` (pure Python, 3.9-compatible, no admin required). No `pytest.ini` or `conftest.py` added — standalone test files match the project convention.

2. **Brain fixture stubs `shutil.which` via monkeypatch** — Returns `/usr/bin/true` (exists on macOS) so `Brain.__init__` passes the binary-existence guard without a real `claude` CLI in the test environment. Documented with a comment in the fixture.

3. **FakePopen copies FAKE_LINES per instance** — `iter(list(FAKE_LINES))` ensures each test fixture gets a fresh iterator even if Brain is shared. Prevents iterator-exhaustion cross-test contamination.

4. **MockBrain class-level concurrency counters** — `_active_count` / `_max_active` with `_counter_lock` support both `test_concurrent_turns_serialize` (asserts max_active <= 1) and `test_different_sessions_parallel` (asserts max_active >= 2). `reset_counters()` is called per test.

5. **Ephemeral port 0 + sentinel pattern** — `ThreadingHTTPServer(("127.0.0.1", 0), ...)` avoids port conflicts. `_sentinel = object()` detects absent `_BRAIN_FACTORY` vs. intentionally-set `None` for clean teardown.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Issue] pytest not present in venv**
- **Found during:** Task 1 setup
- **Issue:** `.venv/bin/python -m pytest --version` returned "No module named pytest"
- **Fix:** Ran `.venv/bin/pip install pytest` before writing test files
- **Files modified:** .venv (no repo file; dependency install only)
- **Commit:** N/A (not a code change)

None of the test logic required deviation from the plan specification.

---

## Known Stubs

None — these are test-only files. No production stubs exist.

---

## Threat Flags

None — test files create no new network endpoints or auth paths.

---

## Self-Check: PASSED

Files created:
- FOUND: /Users/pietrojustino/Documents/Jarvis/test_brain_stream.py (215 lines)
- FOUND: /Users/pietrojustino/Documents/Jarvis/test_server_streaming.py (472 lines)

Commits:
- FOUND: a7b4a0b — test(01-01): add failing unit tests for Brain.think_stream (TDD RED)
- FOUND: 08bac3a — test(01-01): add failing integration tests for server streaming API (TDD RED)

RED verification: 12 failed, 2 passed — confirmed expected outcome.
