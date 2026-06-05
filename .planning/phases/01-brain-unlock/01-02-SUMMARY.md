---
phase: 01-brain-unlock
plan: 02
subsystem: brain
tags: [claude-cli, stream-json, ndjson, subprocess, threading, generator]

requires:
  - phase: 01-brain-unlock
    provides: test_brain_stream.py RED contract (plan 01-01)
provides:
  - Brain.think_stream() generator yielding typed ActivityEvents from claude stream-json NDJSON
  - Brain._build_stream_cmd() with mandatory --verbose flag
  - Per-Brain threading.Lock (Brain._lock) for server single-writer serialization
affects: [01-03 server streaming, 01-04 integration gate, web activity UI]

tech-stack:
  added: []
  patterns:
    - "Generator-based incremental event streaming over subprocess.Popen stdout (line-by-line NDJSON)"
    - "Defensive parsing of MEDIUM-confidence tool_use/screenshot event shapes"

key-files:
  created: []
  modified: [brain.py]

key-decisions:
  - "stream-json mode injects --verbose unconditionally (claude refuses stream-json without it)"
  - "thinking blocks filtered out; only text/tool_use/screenshot/result/done/error events surface"
  - "session_id captured from the result event into self.session_id for next-turn --resume"
  - "think() sync path left byte-for-byte unchanged (backward compatibility)"

patterns-established:
  - "ActivityEvent dict shapes: text/tool_use/screenshot/result/done/error — consumed by server SSE"

requirements-completed: [CORE-02]

duration: ~10min
completed: 2026-06-05
---

# Phase 01 Plan 02: Brain Streaming Generator Summary

**Brain.think_stream() — a generator that runs the claude CLI in stream-json mode and yields typed ActivityEvents (text, tool_use, screenshot, result) line-by-line, capturing session_id for resume.**

## Performance

- **Duration:** ~10 min
- **Completed:** 2026-06-05
- **Tasks:** 2 (build stream command + streaming generator)
- **Files modified:** 1 (brain.py, +96 lines)

## Accomplishments
- `think_stream(user_text)` generator: subprocess.Popen on claude `--output-format stream-json --verbose`, parses NDJSON per line, yields typed events as each segment completes
- `_build_stream_cmd()`: derives the streaming command from `_build_cmd`, swapping output format to stream-json and inserting the mandatory `--verbose` flag
- `self._lock = threading.Lock()` added per Brain instance for the server worker's single-writer serialization
- thinking blocks filtered; `session_id` captured from the result event into `self.session_id`; `BrainOffline` raised on network-style stderr
- Existing `Brain.think()` synchronous path preserved unchanged

## Task Commits

1. **think_stream + _build_stream_cmd + _lock** - `15cec12` (feat)

_Note: this plan's implementation arrived as a single reviewed working-tree change (test-verified) and was committed as one feat commit after confirming it satisfies the 01-01 contract. Provenance confirmed with user before committing._

## Files Created/Modified
- `brain.py` - Added think_stream() generator, _build_stream_cmd(), self._lock; think() untouched

## Decisions Made
- `--verbose` is non-optional for stream-json (empirically verified — claude errors otherwise)
- MEDIUM-confidence tool_use/screenshot block shapes parsed defensively; flagged in-code for confirmation on a real computer-use turn (deferred to plan 01-04)

## Deviations from Plan
None — implementation matches plan 01-02 must_haves; verified against test_brain_stream.py.

## Issues Encountered
None.

## Next Phase Readiness
- `Brain.think_stream` + `Brain._lock` ready for plan 01-03 (server worker drains the generator under the lock)
- tool_use/screenshot event shapes remain MEDIUM confidence until confirmed on a real turn in plan 01-04

---
*Phase: 01-brain-unlock*
*Completed: 2026-06-05*
