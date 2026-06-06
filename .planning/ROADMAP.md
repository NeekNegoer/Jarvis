# Roadmap: Jarvis Milestone 2

## Overview

Milestone 2 transforms Jarvis from a working v1 into a genuinely great daily driver: a live, streaming browser experience backed by an extensible skill system, installable as a PWA, and robust enough for hands-free use without headphones. The dependency chain is strict — the server must be unlocked first (brain lock removed, SSE added, CSRF gated) before the live activity UI, skills, and echo cancellation can follow. PWA is independent and can land at any point after Phase 1 stabilizes the API paths.

## Milestones

- 🚧 **Milestone 2 — Chrome PWA + Skills + Robustness** — Phases 1–5 (in progress)

## Phases

- [ ] **Phase 1: Brain Unlock** - Remove the blocking brain lock; add job-queue SSE and CSRF protection so the UI stays responsive
- [x] **Phase 2: Live Activity UI** - Surface every tool call, inline screenshot, elapsed timer, and error chip in a live activity panel (completed 2026-06-06)
- [ ] **Phase 3: Skill System + Google Classroom** - Ship the pluggable skill loader and the first real skill: Google Classroom
- [ ] **Phase 4: PWA** - Make Jarvis installable as a standalone Chrome app with a dock icon
- [ ] **Phase 5: Echo Cancellation** - Gate the mic during TTS so hands-free mode works without headphones

## Phase Details

### Phase 1: Brain Unlock
**Goal**: The server processes turns without freezing, streams incremental events to the browser, serializes concurrent turns safely, and rejects cross-origin requests
**Depends on**: Nothing (first phase — modifies existing server.py and brain.py)
**Requirements**: CORE-01, CORE-02, CORE-03, SEC-01
**Success Criteria** (what must be TRUE):
  1. Pietro sends a message and the browser does not freeze — he can click, type, or open new chat while Jarvis is thinking (even during a 600 s computer-use turn)
  2. Text updates and tool-call step labels arrive in the browser as they happen, not only after the turn completes
  3. A cross-origin page (not http://127.0.0.1:8765) cannot POST to /api/turn or /api/ask — the server returns 403
  4. Two near-simultaneous turns on the same session queue safely — the second starts after the first finishes, with no JSON-RPC corruption on the MCP pipe
**Plans**: 4 plans
Plans:
- [x] 01-01-PLAN.md — Wave 0 test scaffold (RED): test_brain_stream.py + test_server_streaming.py
- [x] 01-02-PLAN.md — brain.py: think_stream() + _build_stream_cmd(--verbose) + per-Brain lock
- [x] 01-03-PLAN.md — server.py: SessionStore, JobRegistry, /api/turn, /api/stream SSE, Origin check
- [x] 01-04-PLAN.md — integration suite + human checkpoint (live streaming, non-freeze, real tool shapes)

### Phase 2: Live Activity UI
**Goal**: During a Mac-control turn Pietro sees a live panel showing each step, inline screenshots, an elapsed timer, collapsible detail, and clear error display
**Depends on**: Phase 1
**Requirements**: UI-02, UI-03, UI-04
**Success Criteria** (what must be TRUE):
  1. Each tool call (screenshot, click, type, AppleScript) appears as a plain-language step card the moment it is invoked, without waiting for the turn to finish
  2. Screenshots Jarvis captures mid-turn appear inline in the activity panel as image thumbnails — no extra action needed from Pietro
  3. An elapsed timer ticks visibly while the turn runs; any step can be expanded to show raw detail or collapsed to a summary line
  4. When a turn fails, a red error chip with a short message appears instead of silence or a frozen spinner
**Plans**: 3 plans
Plans:
- [x] 02-01-PLAN.md — Fix think_stream to emit screenshot events from `user` tool_result blocks (+ test)
- [x] 02-02-PLAN.md — Activity panel in app.js: bilingual step cards, inline screenshots+lightbox, timer, collapse, error chip
- [x] 02-03-PLAN.md — Style the panel to match the dark/gold aesthetic + human-verify checkpoint
**UI hint**: yes

### Phase 3: Skill System + Google Classroom
**Goal**: Jarvis loads pluggable self-contained skills from a skills/ folder at startup and Pietro can query his Google Classroom for assignments, courses, and announcements
**Depends on**: Phase 1
**Requirements**: SKILL-01, SKILL-02, SKILL-03, CLASS-01, CLASS-02, CLASS-03
**Success Criteria** (what must be TRUE):
  1. Pietro drops a new skill folder (manifest + server.py) into skills/ and restarts — the brain discovers and can invoke its tools with no edits to core code
  2. Pietro asks "what assignments are due this week?" and Jarvis answers with accurate due dates sourced from his Google Classroom
  3. Pietro asks about his courses and recent announcements and Jarvis answers correctly from Google Classroom
  4. Pietro points a skill manifest at a server.py in another Claude Code project and Jarvis can invoke its tools (import bridge via absolute path)
**Plans**: TBD

### Phase 4: PWA
**Goal**: Jarvis installs as a Chrome Progressive Web App — its own standalone window with a dock icon, no address bar or browser tabs
**Depends on**: Phase 1
**Requirements**: UI-01
**Success Criteria** (what must be TRUE):
  1. Chrome's install prompt appears for Jarvis and Pietro can install it; the installed app opens in a standalone window with no browser chrome
  2. Jarvis appears as a named app in the macOS Dock with its own icon (192×192 and 512×512)
**Plans**: TBD
**UI hint**: yes

### Phase 5: Echo Cancellation
**Goal**: Hands-free and wake-word modes work without headphones — the Python mic ignores Jarvis's own TTS voice so there is no self-triggering
**Depends on**: Phase 1, Phase 2
**Requirements**: AUDIO-01
**Success Criteria** (what must be TRUE):
  1. Pietro runs Jarvis in hands-free mode without headphones — Jarvis's spoken reply does not re-trigger the wake word or queue a new turn
  2. If the TTS-end signal is never received (network drop, crash), the mic suppression gate reopens automatically after 10 seconds so Jarvis does not stay muted permanently
**Plans**: TBD

## Progress

**Execution Order:** 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Brain Unlock | 4/4 | Complete | 2026-06-05 |
| 2. Live Activity UI | 3/3 | Complete    | 2026-06-06 |
| 3. Skill System + Google Classroom | 0/TBD | Not started | - |
| 4. PWA | 0/TBD | Not started | - |
| 5. Echo Cancellation | 0/TBD | Not started | - |
