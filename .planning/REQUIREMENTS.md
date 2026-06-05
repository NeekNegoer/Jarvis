# Jarvis — Requirements (Milestone 2)

Milestone 2 = a genuinely great Chrome experience + extensible skills + the robustness to trust
it daily. Derived from PROJECT.md (Active) and `.planning/research/`. REQ-ID = `[CATEGORY]-[NN]`.

> v1 capabilities are already shipped and tracked under **Validated** in `PROJECT.md` — this file
> scopes only the new milestone-2 work.

---

## Requirements — Milestone 2 (current scope)

### CORE — Responsive, streaming brain backbone
*(The unlock everything else depends on — see research build order.)*

- [ ] **CORE-01**: The UI stays responsive during long turns — Pietro sees progress and the interface never freezes while a computer-use turn (up to 600 s) runs.
- [ ] **CORE-02**: A turn streams incrementally to the browser — text and step updates arrive as they happen (Server-Sent Events), not only after the turn completes.
- [ ] **CORE-03**: Concurrent turns/sessions are handled safely — a single-writer guarantee ensures two `claude` processes never corrupt the shared computer-use MCP connection.

### UI — Chrome experience
- [ ] **UI-01**: Jarvis installs as a Chrome PWA — opens in its own standalone window with a dock icon, no browser tabs or address bar.
- [ ] **UI-02**: During a Mac-control turn, Pietro sees a live activity view — each step / tool call appears as it happens, in plain language, instead of just "working…".
- [ ] **UI-03**: Screenshots Jarvis takes mid-turn appear inline in the activity view.
- [ ] **UI-04**: Activity steps can be expanded/collapsed for detail and an elapsed timer shows the turn is progressing; errors surface as a clear chip rather than silence.

### SKILL — Extensible skill system
- [ ] **SKILL-01**: Jarvis loads self-contained skills from a `skills/` folder at startup, and the brain can discover and invoke them.
- [ ] **SKILL-02**: Pietro can add a new skill by dropping in a folder (manifest + tools) — no edits to core code.
- [ ] **SKILL-03**: Jarvis can use a skill that lives in one of Pietro's other Claude Code projects by pointing a skill manifest at its absolute path (import bridge).

### CLASS — Google Classroom skill
- [ ] **CLASS-01**: Pietro can ask what assignments are due (today / this week / overdue) and Jarvis answers from his Google Classroom.
- [ ] **CLASS-02**: Pietro can ask about his courses and recent announcements and Jarvis answers from Google Classroom.
- [ ] **CLASS-03**: A one-time, no-paid-key OAuth setup connects Jarvis to Google Classroom (read-only scopes), and Jarvis re-authenticates gracefully when the token expires.

### AUDIO — Echo cancellation
- [ ] **AUDIO-01**: Hands-free and wake-word modes work without headphones — the mic ignores Jarvis's own TTS (no self-triggering) via a speak-suppression gate.

### SEC — Localhost safety
- [ ] **SEC-01**: The local web server rejects cross-origin requests (Origin check) so a malicious web page can't trigger Jarvis or Mac control through the `127.0.0.1` API.

---

## Deferred (v2 — valuable, not this milestone)

- Persistent conversation history across sessions (UI) — not selected this round.
- In-UI settings panel (voice / persona / language / memory) — not selected this round.
- Additional skills: Mac "macros" (named multi-step automations) and research-and-save.
- Native menu-bar app + auto-start at login (LaunchAgents for server + Ollama).
- Full automated test suite + CI.
- Sentence-by-sentence streaming TTS (speak as the reply streams).

## Out of Scope (hard boundaries)

- **Paid APIs / `ANTHROPIC_API_KEY`** — Max plan only; no per-use billing.
- **Cloud hosting / multi-user / network exposure** — single-user, localhost-only.
- **Auto-sending email or auto-submitting assignments** — Jarvis drafts / opens; Pietro confirms.
- **Mobile / iOS app** — desktop macOS focus.

---

## Open inputs

- **SKILL-03**: confirm *which* of Pietro's other Claude Code projects/skills to wire in first.
- **CLASS-03**: re-verify current Google Classroom OAuth scope sensitivity + the 7-day unverified-token policy at implementation time (research flagged MEDIUM confidence).

---

## Traceability

*(Filled by the roadmap — maps each REQ-ID to the phase that delivers it.)*

| REQ-ID | Phase | Status |
|--------|-------|--------|
| CORE-01 | Phase 1 | pending |
| CORE-02 | Phase 1 | pending |
| CORE-03 | Phase 1 | pending |
| SEC-01 | Phase 1 | pending |
| UI-02 | Phase 2 | pending |
| UI-03 | Phase 2 | pending |
| UI-04 | Phase 2 | pending |
| SKILL-01 | Phase 3 | pending |
| SKILL-02 | Phase 3 | pending |
| SKILL-03 | Phase 3 | pending |
| CLASS-01 | Phase 3 | pending |
| CLASS-02 | Phase 3 | pending |
| CLASS-03 | Phase 3 | pending |
| UI-01 | Phase 4 | pending |
| AUDIO-01 | Phase 5 | pending |
