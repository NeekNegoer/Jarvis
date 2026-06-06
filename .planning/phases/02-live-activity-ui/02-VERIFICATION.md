---
status: passed
phase: 02-live-activity-ui
verified: 2026-06-06
verifier: inline (orchestrator) + human visual sign-off
requirements_verified: [UI-02, UI-03, UI-04]
automated_tests: "17 passed (test_brain_stream + test_server_streaming) at last run; selftest 12 passed"
human_approved: true
---

# Phase 2: Live Activity UI — Verification

**Goal:** During a Mac-control turn Pietro sees a live panel showing each step, inline
screenshots, an elapsed timer, collapsible detail, and clear error display.

**Verdict: PASSED** — Pietro visually approved all four behaviors in a real Mac-control turn
("Aprovado!"), and the automated suite was green at the last run.

## Success Criteria (goal-backward)

### UI-02 — Live step cards in plain language — ✅ PASSED
- `web/app.js` `addStepCard()` renders one card per `tool_use` event the moment it arrives, with a
  bilingual plain-language label from `stepLabel()` (15-tool map, pt-BR/EN). Verified live: cards
  appeared one-by-one during "abra o Safari e tire um print" (🚀 Abriu Safari, 📸 Tirou um print).

### UI-03 — Inline screenshots — ✅ PASSED
- Backend (02-01): `brain.py think_stream` now emits `{type:"screenshot",data}` from `user`
  tool_result image blocks (the dead `tool_result` branch was the bug). 3 new unit tests cover it.
- Frontend (02-02): `addShot()` renders a `data:image/png;base64` thumbnail inline; clicking opens a
  lightbox (`ensureLightbox()`), Esc/click closes. Verified live by Pietro.

### UI-04 — Timer + collapse/expand + error chip — ✅ PASSED
- Elapsed `mm:ss` timer (`fmtElapsed` + setInterval, single-start guard) ticks during the turn and
  stops on done. Each step card toggles `.expanded` to reveal raw tool `input` (JSON in a `<pre>`,
  rendered via `textContent` — XSS-safe). `addErrorChip()` shows a red chip on `error` events.
  All verified live by Pietro.

## Requirement Traceability
| Req | Where delivered | Status |
|-----|-----------------|--------|
| UI-02 | app.js addStepCard/stepLabel (02-02); CSS (02-03) | ✅ |
| UI-03 | brain.py screenshot emission (02-01); app.js addShot/lightbox (02-02); CSS (02-03) | ✅ |
| UI-04 | app.js timer/expand/error chip (02-02); CSS (02-03) | ✅ |

## Notes / carry-forward
- The live screenshot/tool-shape path was confirmed end-to-end by Pietro's real Mac-control turn
  (resolves the MEDIUM-confidence item from Phase 1's stream_debug_findings.md).
- Tooling note: VSCode's debugger "Select debugger" popup intercepts `node` commands in the
  integrated terminal; `.vscode/settings.json` now disables auto-attach. Final bookkeeping/commits
  for this phase were run from an external terminal as a workaround.

## Automated Evidence (last green run)
```
.venv/bin/python -m pytest test_brain_stream.py test_server_streaming.py -q  →  17 passed
.venv/bin/python selftest.py                                                 →  12 passed, 0 failed
```
