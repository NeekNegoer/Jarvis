# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-05)

**Core value:** Pietro can speak or type to Jarvis and have it reliably get real things done — on his Mac and in his student/daily life — in Portuguese or English, hands-free, without paying per use.
**Current focus:** Phase 1 — Brain Unlock

## Current Position

Phase: 1 of 5 (Brain Unlock)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-06-05 — Roadmap created; milestone 2 phases derived and written

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: —
- Trend: —

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Milestone 2 scope locked: Chrome PWA + live activity UI + extensible skills (Google Classroom first) + robustness (responsive brain + echo cancel)
- YOLO mode, standard granularity, parallelization enabled — research ran before planning
- Google Auth packages pinned for Python 3.9: google-auth==2.49.2, google-auth-oauthlib==1.3.1, google-auth-httplib2==0.3.1, google-api-python-client==2.197.0
- Echo cancellation uses threading.Event gate in ears.py/wake.py — NOT browser getUserMedia({echoCancellation:true}) which does not reach sounddevice
- Service worker must pass /api/* straight through — never cache SSE streams

### Pending Todos

None yet.

### Blockers/Concerns

- SKILL-03: confirm which of Pietro's other Claude Code projects/skills to wire in first (open input)
- CLASS-03: re-verify Google Classroom OAuth scope sensitivity + 7-day unverified-token policy before implementation (MEDIUM confidence from research)
- Phase 1: claude CLI stream-json intermediate event field names are MEDIUM confidence — parse defensively and log raw lines in debug mode on first run
