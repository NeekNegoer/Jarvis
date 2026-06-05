---
phase: 02-live-activity-ui
plan: "01"
subsystem: brain
tags: [tdd, streaming, screenshot, bug-fix]
dependency_graph:
  requires: []
  provides: [think_stream-screenshot-events]
  affects: [server.py SSE /api/stream consumers]
tech_stack:
  added: []
  patterns: [defensive-dual-path-image-extraction, user-event-tool-result-parsing]
key_files:
  created: []
  modified:
    - brain.py
    - test_brain_stream.py
decisions:
  - "Defensive dual-path for image data: inner.get('data') for MCP shape, inner.get('source',{}).get('data') for Anthropic convention"
  - "Guard every nested access with `or {}` / `or []` per threat T-02-01"
  - "FakePopenWith(lines) factory pattern lets per-test NDJSON sequences share the brain fixture"
metrics:
  duration: "~2 minutes"
  completed: "2026-06-05"
  tasks_completed: 2
  files_modified: 2
requirements: [UI-03]
---

# Phase 2 Plan 01: Fix think_stream screenshot emission from user events Summary

**One-liner:** Dead `elif t == "tool_result":` branch replaced with `elif t == "user":` defensive dual-path parser that emits `{"type":"screenshot","data":<b64>}` from inner image blocks.

## What Was Built

Fixed the known Phase 1 carry-forward bug: `think_stream` had a dead branch that listened for a top-level `tool_result` event the claude CLI never emits. Per `stream_debug_findings.md` §3, tool results arrive inside `user` events. The fix walks `message.content[]` for `tool_result` blocks and their inner `content[]` for `image` blocks, supporting both the MCP server shape (`inner.data`) and the Anthropic convention (`inner.source.data`).

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | TDD RED — Add 3 failing screenshot tests to test_brain_stream.py | 717306c |
| 2 | TDD GREEN — Replace dead tool_result branch with user-event handler in brain.py | fc4b3a5 |

## Image Field Path Confirmation

**From `computer_use_server.py` line 211** (`_screenshot_result()`):
```python
{"type": "image", "data": b64, "mimeType": "image/png"}
```
The MCP server uses `data` directly (no `source` wrapper). The implementation checks `inner.get("data")` first (MCP shape), then falls back to `inner.get("source", {}).get("data")` (Anthropic convention). Both paths are exercised by the new tests.

**Note for Plan 02-02:** Confirm the exact path fired on a REAL screenshot turn by running `JARVIS_STREAM_DEBUG=1` and asking Jarvis to take a screenshot, then inspecting `stream_debug.ndjson`. The MCP path (`inner.data`) is most likely given `computer_use_server.py`.

## Test Results

```
8 passed in 0.01s
```

- 5 original Phase 1 tests: all GREEN (no regression)
- 3 new screenshot tests: all GREEN
  - `test_screenshot_from_user_event_mcp_shape` — `inner.data` path
  - `test_screenshot_from_user_event_source_shape` — `inner.source.data` path
  - `test_user_text_result_no_screenshot` — no crash on text-only inner content

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None. The `user`-event parser was already within the localhost SSE channel scope (T-02-02 accepted). Defensive guards satisfy T-02-01 (DoS via malformed JSON).

## Self-Check: PASSED

- brain.py modified: exists
- test_brain_stream.py modified: exists
- Commit 717306c: exists
- Commit fc4b3a5: exists
- `pytest test_brain_stream.py`: 8 passed
