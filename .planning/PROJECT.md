# Jarvis

## What This Is

Jarvis is Pietro's personal, **bilingual (pt-BR / English) system-wide macOS voice assistant** —
a hands-free chief-of-staff that listens, thinks with Claude (on his Max plan, no API key),
talks back in the language he used, and can control his whole Mac. v1 is complete and working.
This milestone makes it a **genuinely great daily driver in Chrome**: a real app-like UI, an
**extensible skill system** (starting with Google Classroom, since Pietro is a student), and the
**robustness to trust it** for real tasks.

## Core Value

**Pietro can speak or type to Jarvis and have it reliably get real things done** — on his Mac and
in his student/daily life — in Portuguese or English, hands-free, without paying per use. If
everything else fails, that loop (understand → act → report, trustworthily) must work.

## Requirements

### Validated

<!-- Shipped in v1 and relied upon. Inferred from the codebase map (.planning/codebase/). -->

- ✓ Bilingual voice loop — listen → think → speak, auto-detects pt-BR vs English per turn — v1
- ✓ Max-plan brain via the `claude` CLI (no API key) with session continuity — v1
- ✓ System-wide computer use (screenshot / click / type / keys / Accessibility / AppleScript) via a hand-written JSON-RPC MCP server — v1
- ✓ Offline brain fallback (Ollama `qwen2.5:7b`) when the Max plan / internet is unreachable — v1
- ✓ Self-writing memory (`memory/about_you.md`) + session-end consolidation — v1
- ✓ Multiple entry modes — text, push-to-talk, hands-free, wake-word, global hotkey — v1
- ✓ Raycast commands (Open Jarvis, Talk, Ask, Stop) — v1
- ✓ Browser UI in Chrome — browser-native STT/TTS, `/api/ask` · `/api/health` · `/api/reset`, new-chat / source badges / barge-in — v1
- ✓ AppleScript recipes for Mail (draft-only) / Calendar / Notes / Reminders / Music / browser — v1
- ✓ UI stays responsive during long tasks — brain-lock removed; non-blocking `/api/turn` job-queue + `/api/stream` SSE + per-session serialization + cross-origin 403 (CORE-01/02/03, SEC-01) — Phase 1 (milestone 2)

### Active

<!-- Milestone 2 scope. Hypotheses until shipped. -->

**Chrome UI**
- [ ] Installable PWA — Jarvis opens in its own window with a dock icon (manifest, service worker, icons), no browser tabs/address bar
- [ ] Live activity view — during Mac-control turns, see what Jarvis is doing (steps / tool calls / screenshots) instead of just "working…"

**Extensible skills**
- [ ] A skill system the brain can discover and invoke (pluggable, self-contained skills)
- [ ] Google Classroom skill — Pietro can ask about classes, assignments, due dates, and announcements
- [ ] Reuse skills/capabilities from Pietro's other Claude Code projects (an importable skill bridge)

**Robustness & trust**
- [x] UI stays responsive during long tasks — brain-lock removed; non-freeze streaming server shipped — Phase 1
- [ ] Echo cancellation — hands-free / wake-word works without headphones (the mic ignores Jarvis's own voice)

### Out of Scope

- **Paid APIs / `ANTHROPIC_API_KEY`** — hard constraint: Max plan only, no per-use billing, no paid services.
- **Cloud hosting / multi-user / network exposure** — personal localhost-only tool; the security model assumes a single trusted user on `127.0.0.1`.
- **Auto-sending email or other destructive actions without confirmation** — safety: Jarvis drafts and asks first.
- **Mobile / iOS app** — desktop macOS is the focus.
- **Native menu-bar app + auto-start at login (LaunchAgents)** — deferred to a later milestone; Pietro prioritized UI / skills / robustness this round (Raycast + PWA cover "always available" for now).
- **Full automated test suite + CI** — deferred; valuable but not this milestone's spine.
- **General Mac "macros" and a research-and-save skill** — deferred; revisit after the skill system lands.

## Context

- **Codebase state:** v1 is complete and verified (see `.planning/codebase/` and `CHECKPOINTS.md`). The Chrome UI (`server.py` + `web/`) shipped most recently.
- **Machine:** MacBook Pro M1 Pro, 16GB, arm64, macOS 26.5. `brew` lives at `~/Documents/.brew` but fails under macOS Documents-folder TCC, so non-pip installs go to `~/.local` (e.g. Ollama at `~/.ollama-dist`).
- **Permissions:** Microphone, Screen Recording, and Accessibility are all granted (the web UI `/api/health` reports `accessibility` and `screen_recording` true).
- **Known issues to address this milestone** (from the codebase map's `CONCERNS.md`):
  - `server.py` holds the brain lock for the entire turn (up to 600s on computer-use), so the UI can't do anything else meanwhile → drives the "responsive during tasks" requirement.
  - Hands-free / wake-word can hear Jarvis's own TTS without headphones → drives echo cancellation.
  - The brain spawns a fresh `claude` CLI per turn, re-running project SessionStart hooks (~5s TTFT) — relevant to the live-activity / streaming work.
  - `/api/ask` has no CSRF/auth gating before it can trigger Mac control — relevant to safely exposing more power in the UI.
- **Open question for research/planning:** how the Google Classroom skill authenticates — Classroom REST API via Google OAuth (no paid key, but a setup flow) vs. driving `classroom.google.com` through existing computer-use. And exactly which "other Claude projects" / skills Pietro wants Jarvis to import.

## Constraints

- **Tech stack**: Python **3.9.6** venv — blocks the official `mcp` SDK (needs 3.10+), hence the hand-written JSON-RPC MCP server in `computer_use_server.py`. New code must stay 3.9-compatible.
- **Brain**: the `claude` CLI on Pietro's **Max plan** — no `ANTHROPIC_API_KEY`, no per-use cost.
- **No sudo/admin**: everything installs without elevation; `brew` under `~/Documents` fails TCC.
- **Security**: localhost-only (`127.0.0.1`); Mac-control must stay gated and confirm before destructive actions.
- **Offline**: must degrade gracefully to the Ollama brain.
- **Bilingual**: pt-BR and English parity across every new feature.
- **Working style**: Pietro values waking up to working software over being asked questions — choose sensible defaults and act autonomously.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Milestone 2 = Chrome UI (PWA + live activity) + extensible skills (Google Classroom first) + robustness (responsive + echo cancel) | Pietro's explicit choice during init questioning | — Pending |
| Map the existing codebase before planning (brownfield) | Substantial v1 codebase; avoid re-planning what exists | ✓ Good (`.planning/codebase/`, commit `092e58e`) |
| Config chosen on Pietro's behalf — YOLO, standard granularity, parallel, research on | Honors his autonomy preference over more config questions | — Pending |
| Defer menu-bar app, auto-start, and full test/CI to a later milestone | Not the spine of what Pietro asked for this round | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-05 — Phase 1 (Brain Unlock) complete*
