---
phase: 01-brain-unlock
plan: 04
subsystem: testing
tags: [integration, sse, checkpoint, human-verify, stream-json, web-ui]

requires:
  - phase: 01-brain-unlock
    provides: think_stream (01-02), SSE server (01-03), test scaffold (01-01)
provides:
  - Phase 1 integration gate passed (full suite + selftest green together)
  - Real-browser confirmation of non-freeze + message/step-level streaming
  - Verified/corrected claude stream-json event shapes (stream_debug_findings.md)
  - web/app.js migrated to the non-blocking /api/turn + /api/stream flow (gap closure)
affects: [02-live-activity-ui]

tech-stack:
  added: []
  patterns:
    - "Browser consumes turns via EventSource over /api/stream/<job_id>"
    - "Offline guarantee preserved client-side: streaming failure falls back to /api/ask"

key-files:
  created:
    - .planning/phases/01-brain-unlock/stream_debug_findings.md
  modified:
    - web/app.js
    - .gitignore

key-decisions:
  - "The claude CLI streams whole MESSAGES, not token deltas — incremental UX is per message/step, the finest granularity available"
  - "tool_use event shape CONFIRMED correct; tool_result/screenshot shape CORRECTED (arrives via `user` events) and recorded for Phase 2"
  - "SEC-01 cross-origin 403 verified by the automated test; the manual apple.com attempt was blocked one layer earlier by that site's CSP"
  - "Migrating web/app.js to the streaming flow was a required Phase 1 gap closure — the 4 original plans never wired the frontend"

patterns-established:
  - "stream_debug.ndjson is gitignored (may contain screen contents per threat T-01-21)"

requirements-completed: [CORE-01, CORE-02, CORE-03, SEC-01]

duration: ~session (interactive)
completed: 2026-06-05
---

# Phase 01 Plan 04: Integration Gate + Human Verification Summary

**Phase 1 verified end-to-end in a real Chrome browser: the UI no longer freezes during a turn, events stream per message/step over SSE, the cross-origin 403 holds, and the MEDIUM-confidence claude event shapes were confirmed (tool_use) or corrected (screenshot).**

## Performance

- **Completed:** 2026-06-05
- **Tasks:** 2 (automated full-suite gate + human-verify checkpoint)
- **Files modified:** web/app.js, .gitignore; created stream_debug_findings.md

## Accomplishments
- **Task 1 (automated gate):** full Phase 1 suite + selftest green together — `14 passed` (brain+server), `selftest.py 12 passed`, backward-compat import assertion OK (both `think` and `think_stream` present), stable across repeated and 3× concurrent runs.
- **Task 2 (human-verify, real browser):**
  - **CORE-01 non-freeze:** PASSED — during a Mac-control turn, typing and **New Chat** both respond; the browser never freezes.
  - **CORE-02 incremental:** OK at message/step granularity — confirmed via `stream_debug.ndjson` that the claude CLI emits whole messages (0 token deltas); tool-call steps + text arrive over time on multi-step turns.
  - **CORE-02 event shapes:** `tool_use` CONFIRMED correct; `tool_result`/screenshot CORRECTED — recorded in `stream_debug_findings.md`.
  - **SEC-01 403:** proven by `test_origin_check_post`; the manual cross-origin fetch from apple.com was blocked by that page's CSP one layer earlier (also blocked, different mechanism).

## Gap Closure (required to meet Phase 1 criteria)
The original 4 plans built brain.py + server.py + tests but never migrated the frontend, so the
browser still used the blocking `/api/ask` and **froze** during turns (criterion 1 failing).
Fixed in commit `ad42d7d`:
- `web/app.js` `send()` now POSTs `/api/turn` then reads `/api/stream/<job_id>` via `EventSource`,
  rendering text incrementally and surfacing tool steps as live labels.
- `newChat()` works mid-turn (aborts the stream, resets) — satisfies "open new chat while thinking".
- Offline guarantee preserved: a streaming turn that yields no answer falls back to `/api/ask` (→ Ollama).

## Files Created/Modified
- `web/app.js` — migrated to the streaming, non-blocking flow (gap closure)
- `.planning/phases/01-brain-unlock/stream_debug_findings.md` — verified/corrected event shapes
- `.gitignore` — ignore `stream_debug.ndjson` (may contain screen contents, threat T-01-21)

## Decisions Made
- Accept message/step-level streaming as satisfying criterion 2 — token-by-token is not offered by the `claude` CLI. Rich live visualization (activity panel, inline screenshots) is the explicit goal of **Phase 2 — Live Activity UI**.

## Deviations from Plan
- **Frontend migration (gap):** not in the original plan scope but required to make Phase 1's browser-level criteria true. Done as a focused, committed change.
- **VSCode terminal config** (`.vscode/settings.json`, commit `8aa59e8`): disabled auto-venv-activation that was interrupting the user's typing — incidental dev-environment fix.

## Issues Encountered
- A stale `server.py` instance held port 8765, causing one transient flaky test run earlier; resolved by freeing the port. The suite is otherwise stable.

## Next Phase Readiness
- **Phase 2 — Live Activity UI** is unblocked: streaming plumbing works; `stream_debug_findings.md` hands Phase 2 the verified `tool_use` shape and the exact `tool_result`/screenshot correction to implement (confirm the image base64 path on a real screenshot turn).
- Carry-forward: screenshot events not yet emitted by `think_stream` (corrected shape recorded); per-turn job leak when an SSE stream is never opened (minor; candidate for a TTL cleanup).

---
*Phase: 01-brain-unlock*
*Completed: 2026-06-05*
