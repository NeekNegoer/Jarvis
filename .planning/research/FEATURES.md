# Feature Research

**Domain:** Bilingual personal voice assistant — PWA UI + agent trace + skill system + Google Classroom
**Researched:** 2026-06-05
**Confidence:** HIGH (PWA / PWA-install, skill patterns, Classroom API) | MEDIUM (agent trace UI conventions — based on observed Claude.ai / ChatGPT / Perplexity behavior, no live search available)

---

## Area 1 — Voice Assistant PWA UI

The goal: Jarvis opens in its own window from the Dock, no tab bar, no address bar. The current UI already has good bones (grain/aura aesthetic, orb, transcript, composer).

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| `manifest.json` with `display: standalone` | Without it Chrome won't offer "Add to Dock"; it's a tab forever | LOW | Needs `name`, `short_name`, `start_url`, `background_color`, `theme_color`, `icons` |
| App icons at 192 × 192 and 512 × 512 (PNG) | Chrome install requires both; missing = install fails silently | LOW | Generate from the orb SVG or a simple wordmark |
| Service worker (even a no-op shell) | Required for Chrome to mark the app "installable" | LOW | A pass-through SW that caches the shell HTML/JS/CSS is enough; no complex caching strategy needed |
| `theme_color` matching the UI background | Without it the standalone window titlebar looks wrong (white flash) | LOW | Use the dark bg color already in style.css |
| `viewport-fit=cover` | Already set in index.html — keeps layout correct in standalone window | DONE | Already shipped |
| Persistent state across installs | Users expect lang + control toggle to survive PWA reinstall | DONE | Already in `localStorage` |
| Keyboard shortcut to talk | Power users expect Cmd+Shift+J or similar — feels app-grade | MEDIUM | Add `keydown` listener for a global combo; document it in the hint area |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Custom install prompt (in-UI "Install Jarvis" button) | Browser's default "Add to Dock" banner is ugly and dismissible; an explicit in-app CTA converts | LOW | Listen for `beforeinstallprompt`, store it, show a chip in the top bar |
| Window remembers its own size / position | Real app feel — Chrome PWA standalone windows don't auto-restore position; a one-shot `localStorage` write on `resize`/`move` isn't possible from JS, but setting a sensible default `--window-width`/`height` in the manifest helps | LOW | Set `prefer_related_applications: false`; set `display_override: ["window-controls-overlay"]` for extra polish |
| `window-controls-overlay` display mode | Lets Jarvis paint all the way into the title bar, making the topbar feel native | MEDIUM | CSS env variables `titlebar-area-*`; graceful fallback to `standalone` if not supported |
| Offline "no brain" UI with clear message | PWA opens even when server.py is down; shows "Jarvis is offline — start the server" instead of a blank page | MEDIUM | SW serves cached shell; `/api/health` timeout triggers a UI banner |

### Anti-Features

| Feature | Why Requested | Why Avoid | Alternative |
|---------|---------------|-----------|-------------|
| Push notifications | "Remind me when Jarvis finishes" | Requires a push server (no paid API, no remote service); breaks the localhost-only model | Show a done banner in the UI when the tab re-focuses; use macOS `osascript` notification via the brain |
| Background sync / background fetch | Keep Jarvis running when the window is closed | SW background sync needs a remote endpoint; also not meaningful for a local voice assistant | Keep Raycast commands as the always-available entry point (already shipped in v1) |
| Multiple PWA windows / tabs | "Open two conversations" | Adds session-state complexity; the brain's session is a single `claude` CLI process | Use "New conversation" button to reset; one window is the mental model |

---

## Area 2 — Live Activity / Agent Trace View

The problem today: computer-use turns lock the UI for up to 600 s with only "working on your Mac…" visible. The fix is streaming intermediate events from the brain.

### Reference: How leading agent UIs handle this

- **Claude.ai**: streams token-by-token; tool calls appear as collapsible cards labeled "Using computer", "Reading file", etc.; screenshots show inline; inner thinking blocks are collapsed by default
- **ChatGPT (with tools)**: shows "Browsing…", "Running code…" banners; results append to the same message thread; no screenshots inline
- **Perplexity**: "Searching for X" with source chips appearing as they resolve; sources collapse after answer
- **Raycast AI**: mostly opaque — shows "Thinking…" spinner; no step breakdown
- **Cursor**: shows file reads/writes as diff events in real time; most granular trace of any product

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Streaming step labels during computer-use | "working…" for 60s feels broken; users need a heartbeat | MEDIUM | Requires SSE or WebSocket from server.py; server must emit step events as the `claude` CLI streams them |
| Tool-call badges ("screenshot", "click", "type", "read") | Shows what Jarvis is actually doing vs. a black box | MEDIUM | Parse the `claude` CLI's JSON stream; each tool call → emit an event |
| Elapsed timer on long turns | Shows Jarvis is alive, not hung | LOW | JS `Date.now()` delta from turn start; render as "12s…" next to status dot |
| Collapsible step list in transcript | Steps are details; the final answer is the star | MEDIUM | Show steps as an expandable `<details>` block inside the Jarvis bubble; collapsed by default |
| Auto-scroll to latest step, not just final reply | If user is watching, they want to see what's happening now | LOW | `scrollTop = scrollHeight` on each step append; same pattern as existing transcript |
| Error step (tool failed) | If a click missed, user needs to know; otherwise they think Jarvis succeeded | MEDIUM | Distinguish `tool_error` events visually (red chip) |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Inline screenshots from computer-use | The most powerful trust signal — user can see exactly what Jarvis saw | HIGH | `computer_use` tool returns base64 PNG on screenshot; SSE stream it as `data:image/png;base64,...`; render `<img>` thumbnail in the step list |
| "Jump to current step" button | If Pietro scrolled up in transcript during a long task, one click re-anchors | LOW | Fixed button that appears when `scrollTop < scrollHeight - 200`; hides when at bottom |
| Step summary at turn end | After 15 steps, collapse them into "Did 6 clicks, 2 screenshots, typed in 3 fields" | MEDIUM | Count event types on turn end, render summary sentence |
| Abort / interrupt button during computer-use | Kill a runaway task mid-flight without losing the session | HIGH | Requires server.py to kill the `claude` subprocess on a new `/api/stop` endpoint; brain must handle SIGTERM gracefully |

### Anti-Features

| Feature | Why Requested | Why Avoid | Alternative |
|---------|---------------|-----------|-------------|
| Full JSON dump of tool inputs/outputs | "I want to see everything" | Overwhelming for a voice assistant; this is a developer need not a daily-driver need | Provide a hidden debug mode (Cmd+D) that shows raw JSON only when deliberately toggled |
| Audio narration of each step ("now clicking Safari…") | "Keep me informed hands-free" | Interrupts conversation flow; annoying after the 2nd use | Let the orb pulse animation convey activity; narrate only the final result |
| Persistent step history across turns | "I want a full activity log" | Storage grows unboundedly; complicates UI | Keep steps only for the current turn; clear on next send |

### Implementation note

Server.py currently blocks the brain lock for the entire turn (`await subprocess`). To stream events it must switch to async subprocess with stdout line-by-line reading, emitting SSE. The `claude` CLI already streams JSON lines (tool calls + text deltas) — the server just needs to relay them. Python 3.9 supports `asyncio.create_subprocess_exec` + `StreamReader`, so no version upgrade is needed.

---

## Area 3 — Extensible Skill / Plugin System

A skill is a self-contained capability the brain can discover and invoke via natural language. The brain is the `claude` CLI with a system prompt — so skills are primarily prompt-injected context + optional Python helpers.

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Skills as files in a `skills/` directory | Discoverability: drop a file, it's available | LOW | Each skill is a directory: `skills/classroom/` with `manifest.json` (name, description, triggers) + `prompt.md` (system prompt fragment) + optional `helper.py` |
| Skill manifest with name + description | The brain's system prompt must include skill descriptions so it knows when to invoke them | LOW | `manifest.json`: `{ "id": "classroom", "name": "Google Classroom", "enabled": true, "description": "...", "triggers": ["assignment", "due date", "aula"] }` |
| Enable / disable per skill | Pietro may want to turn off a skill temporarily without deleting it | LOW | `"enabled": false` in manifest; server.py reads enabled skills on startup and injects only those |
| Skills injected into brain system prompt at startup | The brain must know skills exist; injection is the simplest integration | LOW | server.py concatenates enabled skills' `prompt.md` into the system prompt |
| Bilingual triggers | pt-BR and English must both invoke the skill reliably | LOW | List triggers in both languages in manifest; rely on Claude's multilingual understanding for the rest |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Skill-aware UI chips in the composer | Show enabled skills as small chips (e.g. "📚 Classroom") that highlight when a relevant query is detected | MEDIUM | Cosmetic; adds personality and reminds Pietro what Jarvis can do |
| Per-skill helper Python module | Some skills need real API calls (Classroom), not just prompts; each skill can ship a `helper.py` that the brain calls via MCP | HIGH | Requires adding skill-specific tool definitions to the MCP server; clean but complex |
| "List skills" voice command | Pietro can ask "what can you do?" and get a bilingual summary of enabled skills | LOW | A static response generated from the skills' descriptions; no extra code |
| Import from other Claude Code projects (skill bridge) | Reuse existing automation Pietro has built elsewhere | MEDIUM | A skill that reads another project's `CLAUDE.md` / scripts and exposes them as Jarvis commands; essentially a cross-project prompt bridge |
| Hot-enable without restart | Toggle a skill from the UI; server reloads only the system prompt portion | MEDIUM | Requires moving system prompt construction out of startup into a cached getter; `/api/skills` endpoint for list + toggle |

### Anti-Features

| Feature | Why Requested | Why Avoid | Alternative |
|---------|---------------|-----------|-------------|
| NPM / pip package-based plugins | "Like VS Code extensions" | Adds dependency management, security surface, and install friction; overkill for a personal tool | Plain directories + Python files are sufficient and git-trackable |
| Skill sandboxing / permissions model | "Skills shouldn't access each other" | Single-user, trusted-author (Pietro writes all skills); sandboxing adds complexity with zero real-world benefit | Code review (it's Pietro's own code); git history as audit trail |
| Skill marketplace / registry | "Discover community skills" | Breaks the localhost-only, no-paid-API model; also a security nightmare | Skills are just files; share them via git if needed |

---

## Area 4 — Google Classroom Skill

Pietro is a Brazilian student. He wants to ask Jarvis (in Portuguese or English) about his classes without opening a browser.

### Authentication path (critical prerequisite)

Two options:
- **Google Classroom REST API + OAuth 2.0**: Structured JSON data, reliable, works headlessly after one-time setup (create a Google Cloud project → OAuth consent screen → credentials.json → run auth flow once → token stored locally). No paid key. Requires ~20 min of one-time setup.
- **Computer-use scraping classroom.google.com**: Zero setup, but brittle (Google changes layout), slow (full browser session), breaks with MFA prompts, and can't handle all classroom states.

**Recommendation: OAuth 2.0 REST API.** Structured data is far superior for reliable voice answers. The one-time setup is a reasonable upfront cost.

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| List upcoming assignments with due dates | Core student need; "what's due?" is the #1 query | MEDIUM | `GET /courses/{courseId}/courseWork`; filter by `dueDate >= today`; sort ascending |
| Overdue assignments ("what did I miss?") | Critical for a student who might forget | MEDIUM | Same endpoint; filter `dueDate < today` and `submissionState != TURNED_IN` |
| Assignments due today | Most urgent query; Pietro wants a daily briefing | LOW | Filter on `dueDate == today` |
| Assignments due this week | Weekly planning | LOW | Filter on `dueDate <= 7 days out` |
| Course list ("what are my classes?") | Context for all other queries | LOW | `GET /courses`; cache locally (changes rarely) |
| Announcements ("any news from Prof X?") | Teachers post time-sensitive info | MEDIUM | `GET /courses/{courseId}/announcements`; show latest N |
| Bilingual responses | Pietro's primary interface is in Portuguese | DONE | Inherited from Jarvis's brain — Claude answers in the language Pietro asked |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Smart priority ordering | Overdue first → due today → due this week → future; never bury the urgent | LOW | Sort logic in helper.py before passing to brain |
| Natural language due-date queries | "O que vence semana que vem?" / "What's due next week?" without explicit class names | LOW | Pass full assignment list to Claude; it parses the natural language intent |
| Grade peek ("how am I doing in Calc?") | Motivating check-in; not always available but valuable when it is | MEDIUM | `GET /courses/{courseId}/courseWork/{cwId}/studentSubmissions`; grades are per-submission; only available if teacher has graded |
| Daily morning briefing skill | "Bom dia Jarvis" → auto-summary of today's classes, due today, and new announcements | MEDIUM | Combine course schedule (if available) + due-today + latest announcements into one prompt |
| "Class is starting" alert | Notify 5 min before a class starts (if schedule is in Classroom or Google Calendar) | HIGH | Requires a polling daemon or cron; deferred — needs more research |
| Cache with TTL | Classroom API has rate limits; don't hit it on every query | LOW | Cache results in a local JSON file with 15-min TTL; stale-while-revalidate pattern |

### Anti-Features

| Feature | Why Requested | Why Avoid | Alternative |
|---------|---------------|-----------|-------------|
| Submit assignments through Jarvis | "Do it all from voice" | Google Classroom's submission API requires exact file attachments; submitting incorrectly is worse than not submitting; also against spirit of academic integrity for written work | Jarvis opens the assignment URL in Chrome; Pietro submits manually |
| Auto-schedule reminders in macOS Reminders | "Add to my reminders automatically" | Creates duplicate reminders if run multiple times; Pietro may not want every assignment in Reminders | Pietro can say "remind me about this" and Jarvis uses the existing Reminders AppleScript on request |
| Posting announcements / comments | "Reply to the professor" | High-stakes action; wrong recipient or content is unrecoverable | Jarvis drafts the text; Pietro reviews and sends manually via the browser |
| Real-time push from Classroom | "Tell me the moment a new assignment is posted" | Requires a long-running webhook endpoint (needs public URL or tunneling); breaks localhost-only model | Pietro asks "any new assignments?" on demand; optional: a cron-based local poll every hour |

---

## Feature Dependencies

```
PWA Install
    └──requires──> manifest.json + service worker + icons

Live Activity View
    └──requires──> SSE streaming from server.py
                       └──requires──> async subprocess (already Python 3.9 compatible)
                       └──requires──> brain lock release (non-blocking turn)

Inline Screenshots
    └──requires──> Live Activity View (SSE stream)
    └──requires──> computer-use tool returning screenshots

Skill System (prompt injection)
    └──requires──> skills/ directory structure
    └──enhances──> Google Classroom Skill (provides the discovery mechanism)

Google Classroom Skill (API path)
    └──requires──> OAuth 2.0 one-time setup (credentials.json + token)
    └──requires──> Skill System (to be discovered)
    └──requires──> helper.py in skill dir (to call REST API)

Abort / Interrupt Button
    └──requires──> Live Activity View (SSE gives turn ID)
    └──requires──> /api/stop endpoint on server.py

Hot-enable skill without restart
    └──requires──> /api/skills endpoint
    └──enhances──> Skill UI chips in composer
```

### Dependency Notes

- **Live Activity requires SSE**: The current `fetch("/api/ask")` waits for the full response. Every live-activity feature depends on the server switching to SSE. This is the single biggest implementation dependency in milestone 2.
- **Inline screenshots require SSE**: Can't stream a base64 image in a synchronous JSON response; SSE (or WS) is the gate.
- **Classroom skill requires OAuth setup**: This is a one-time human step (Pietro must run an auth flow in a browser once). Plan for it as a documented setup task, not automated.
- **Skill system must land before Classroom skill**: Classroom is delivered as a skill, so the skill discovery mechanism must exist first.

---

## MVP Definition (Milestone 2 scope)

### Launch With (v2 — this milestone)

- [x] PWA manifest + SW + icons (table stakes, low complexity, high impact)
- [x] Live activity step labels via SSE (core UX improvement; unlocks trust in Mac-control)
- [x] Inline screenshots from computer-use (highest-impact differentiator)
- [x] Skill directory structure + prompt injection (foundation for everything else)
- [x] Google Classroom skill: due today/this week + overdue + announcements via OAuth
- [x] Echo cancellation (already in Active requirements from PROJECT.md)
- [x] UI stays responsive during long tasks (server.py async; already in Active requirements)

### Add After Validation (v2.x)

- [ ] Hot-enable skills from UI (`/api/skills` endpoint + chips) — trigger: Pietro asks "can I toggle skills without restarting?"
- [ ] Abort/interrupt button — trigger: Pietro gets stuck in a runaway computer-use turn
- [ ] Grade peek feature — trigger: grades are available in Pietro's Classroom courses
- [ ] Daily morning briefing — trigger: Pietro starts asking "what's my day look like?"
- [ ] Skill bridge from other Claude Code projects — trigger: Pietro identifies specific automations to import

### Future Consideration (v3+)

- [ ] `window-controls-overlay` PWA display mode — polish, not functionality
- [ ] Class-starts-in-5-min alerts (requires polling daemon + schedule data)
- [ ] Skill-aware UI chips in composer (cosmetic, nice-to-have)

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| PWA manifest + install | HIGH | LOW | P1 |
| SSE streaming (live activity) | HIGH | MEDIUM | P1 |
| Inline screenshots | HIGH | HIGH | P1 |
| Skill directory + prompt injection | HIGH | LOW | P1 |
| Google Classroom assignments + due dates | HIGH | MEDIUM | P1 |
| Echo cancellation | HIGH | MEDIUM | P1 |
| Async brain (non-blocking UI) | HIGH | HIGH | P1 |
| Collapsible step list UI | MEDIUM | LOW | P2 |
| Elapsed timer on turns | MEDIUM | LOW | P2 |
| Classroom grade peek | MEDIUM | MEDIUM | P2 |
| Hot-enable skills from UI | MEDIUM | MEDIUM | P2 |
| Abort/interrupt button | MEDIUM | HIGH | P2 |
| Classroom morning briefing | MEDIUM | LOW | P2 |
| `window-controls-overlay` | LOW | MEDIUM | P3 |
| Skill bridge (other Claude projects) | LOW | HIGH | P3 |
| Class-start alerts | LOW | HIGH | P3 |

---

## Sources

- Current Jarvis v1 codebase: `web/index.html`, `web/app.js`, `.planning/PROJECT.md`
- Claude.ai agent trace UI: observed behavior (tool call cards, screenshot inline, collapsible steps)
- Google Classroom REST API: https://developers.google.com/classroom/reference/rest — no paid key required, OAuth 2.0 only
- Chrome PWA installability criteria: https://web.dev/install-criteria/ — manifest + SW required
- Python 3.9 `asyncio.create_subprocess_exec`: standard library, no upgrade needed
- SSE in Flask/Python: `flask` `Response` with `text/event-stream` mimetype; works with Python 3.9

---
*Feature research for: Jarvis milestone 2 — PWA UI + live activity + skill system + Google Classroom*
*Researched: 2026-06-05*
