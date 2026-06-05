---
phase: 02-live-activity-ui
plan: 02
subsystem: web-ui
tags: [activity-panel, streaming, bilingual, screenshots, timer, accessibility]
dependency_graph:
  requires: [02-01]
  provides: [activity-panel-dom, step-cards, screenshot-thumbnails, lightbox, elapsed-timer, error-chip]
  affects: [web/app.js]
tech_stack:
  added: []
  patterns: [vanilla-ES2015, createElement-only, textContent-XSS-guard, closure-timers]
key_files:
  created: []
  modified: [web/app.js]
decisions:
  - "timerId declared at module-level (not local to send()) so newChat() can clear it"
  - "elTranscript.innerHTML='' replaced with removeChild loop to satisfy innerHTML==0 acceptance gate"
  - "Timer started with if(!timerId) guard on BOTH tool_use and screenshot branches (first one wins)"
  - "lightbox singleton created lazily on first thumbnail click; reused for all screenshots in the turn"
metrics:
  duration_minutes: 5
  completed_date: "2026-06-05"
  tasks_completed: 3
  files_modified: 1
requirements_satisfied: [UI-02, UI-03, UI-04]
---

# Phase 02 Plan 02: Live Activity Panel Summary

One-liner: Persistent bilingual step-cards, inline screenshot thumbnails with lightbox, ticking elapsed timer, collapse/expand detail, and red error chip — all additive on top of existing text+TTS flow, with zero innerHTML.

## What Was Built

### Task 1 — Bilingual step labels + activity panel + step cards (UI-02)
Commit: `e9678dc`

Four new helpers added to `web/app.js` after `markSource`:

- `toolKey(name)` — strips `mcp__computer__` prefix
- `stepLabel(name, input, lang)` — returns `{icon, text}` from a 16-entry bilingual MAP; all text values built with string concatenation (never innerHTML); default fallback `{icon:"🔧", text: key}`
- `ensureActivityPanel(bubble)` — lazily creates `<section class="activity">` containing `<div class="activity-head"><span class="activity-timer">0:00</span></div>`, inserted before `.body`
- `addStepCard(panel, ev)` — renders `<div class="step">` with `<span class="step-icon">`, `<span class="step-label">` (textContent), `<pre class="step-detail">` (JSON.stringify via textContent)

`tool_use` branch now calls `ensureActivityPanel` + `addStepCard` instead of only updating `elHint`.

**Deviation (Rule 2):** `elTranscript.innerHTML = ""` in `newChat()` (pre-existing) was replaced with a `while/removeChild` loop to satisfy the `grep innerHTML == 0` acceptance gate.

### Task 2 — Inline screenshots + lightbox (UI-03)
Commit: `cc355c1`

- `addShot(panel, b64)` — creates `<div class="shot"><img loading="lazy">` with `src = "data:image/png;base64," + b64`; clicking the thumbnail opens a singleton `<div class="lightbox">` appended to `document.body`
- `ensureLightbox()` — lazily creates the lightbox singleton; sets `img.alt` and click-to-close handler
- Escape key handler now first closes the lightbox if open, then falls through to existing speech/hands-free logic
- Module-level `let lightbox = null;` added alongside `let es = null;`

`screenshot` branch now calls `addShot(panel, ev.data)` (guarded with `if (ev.data)`).

### Task 3 — Elapsed timer + collapse/expand + error chip (UI-04)
Commit: `e4bd0b8`

- `fmtElapsed(ms)` → `"m:ss"` string using padStart
- `addErrorChip(bubble, msg)` → creates `<div class="activity-error">` with `textContent = "⚠️ " + msg`; inserted after `.activity` panel if present, else before `.body`
- Module-level `let timerId = null;` guards against multiple intervals
- Timer starts with `if (!timerId) { timerId = setInterval(..., 1000); }` on the FIRST tool_use or screenshot event in a turn
- `finish()` clears interval, nulls `timerId`, writes final elapsed to `.activity-timer`
- `fallbackToAsk()`, `catch` block, and `newChat()` all guard-clear the timer with `if (timerId) { clearInterval(timerId); timerId = null; }`
- `addStepCard` gains `role="button"`, `tabindex="0"`, `title`, `onclick` toggle `"expanded"`, `onkeydown` (Enter/Space) toggle
- `error` branch calls `addErrorChip(ph, ev.text)` before the existing fallback-text logic

## PINNED CSS Class Names (for Plan 02-03)

| Class | Element | Notes |
|-------|---------|-------|
| `.activity` | `<section>` | container inside Jarvis bubble, before `.body` |
| `.activity-head` | `<div>` | top row of activity panel |
| `.activity-timer` | `<span>` | elapsed mm:ss display |
| `.step` | `<div>` | one row per tool_use; has `.expanded` modifier |
| `.step-icon` | `<span>` | emoji icon |
| `.step-label` | `<span>` | plain-language bilingual label text |
| `.step-detail` | `<pre>` | JSON detail; hidden by default, shown when `.step.expanded` |
| `.step.expanded` | modifier | added/removed by click/Enter/Space |
| `.shot` | `<div>` | screenshot thumbnail wrapper |
| `.shot img` | `<img>` | thumbnail |
| `.lightbox` | `<div>` | singleton fullscreen overlay on `document.body` |
| `.lightbox.open` | modifier | added to show, removed to hide |
| `.activity-error` | `<div>` | red error chip with "⚠️ " prefix |

## Bilingual Label Map (PINNED)

| Key | Icon | PT | EN |
|-----|------|----|----|
| screenshot | 📸 | Tirou um print | Took a screenshot |
| screen_info | 📐 | Mediu a tela | Measured the screen |
| click | 🖱️ | Clicou | Clicked |
| double_click | 🖱️ | Clique duplo | Double-clicked |
| right_click | 🖱️ | Clique direito | Right-clicked |
| move_mouse | 🖱️ | Moveu o mouse | Moved the mouse |
| scroll | 🖱️ | Rolou a tela | Scrolled |
| type_text | ⌨️ | Digitou "..." | Typed "..." |
| key | ⌨️ | Tecla \<k> | Pressed \<k> |
| open_app | 🚀 | Abriu \<app> | Opened \<app> |
| frontmost_app | 👀 | Viu o app ativo | Checked active app |
| list_ui_elements | 👀 | Leu a tela | Read the screen |
| click_element | 🖱️ | Clicou em \<el> | Clicked \<el> |
| run_applescript | 📜 | Rodou um AppleScript | Ran AppleScript |
| remember | 🧠 | Memorizou | Remembered |
| ToolSearch | 🔎 | Procurou ferramenta | Searched tools |
| (unknown) | 🔧 | toolKey(name) | toolKey(name) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - XSS acceptance gate] Replaced elTranscript.innerHTML = "" with removeChild loop**
- Found during: Task 1 verification
- Issue: Pre-existing `elTranscript.innerHTML = ""` in `newChat()` caused `grep -c innerHTML` to return 1, failing the hard acceptance gate
- Fix: Replaced with `while (elTranscript.firstChild) elTranscript.removeChild(elTranscript.firstChild);`
- Files modified: `web/app.js`
- Commit: `e9678dc`

## Verification Results

- `node --check web/app.js` — PASSED (all three tasks)
- `grep -c "innerHTML" web/app.js` — 0 (XSS gate PASSED)
- `grep -c "function stepLabel" web/app.js` — 1
- `grep -c "function ensureActivityPanel" web/app.js` — 1
- `grep -c "function addStepCard" web/app.js` — 1
- `grep -c "function addShot" web/app.js` — 1
- `grep -c "function fmtElapsed" web/app.js` — 1
- `grep -c "function addErrorChip" web/app.js` — 1
- `grep -c "setInterval" web/app.js` — 2 (tool_use + screenshot branches)
- `grep -c "clearInterval" web/app.js` — 4 (finish, fallbackToAsk, catch, newChat)
- Bilingual: "Took a screenshot" == 1, "Tirou um print" == 1

## Known Stubs

None. All event branches are fully wired. CSS styling deferred to Plan 02-03 (by design — classes are pinned, not stub-empty).

## Self-Check: PASSED
