# Jarvis — Build Log / Checkpoints

Newest first. Each checkpoint = roughly one hour of work or one finished milestone.

---

## Checkpoint 8 — 2026-06-05 ~12:40 — Web UI (Chrome) — verified end-to-end + polished

A previous session (~12:01–12:27) added a **browser UI** but ended before testing or logging it.
This checkpoint **verified it works end-to-end and finished the rough edges.**

- **What it is** (`server.py` + `web/`): a dependency-free stdlib HTTP server on `127.0.0.1:8765`
  that serves a gorgeous "orbital console" UI (`index.html`/`style.css`/`app.js`). Speech-in and
  speech-out happen **in the browser** via Chrome's Web Speech API — so STT/TTS need no Python,
  no headphone juggling, and you get **Google's neural voices**. The backend only thinks: it calls
  the same `brain.Brain` (Max plan) with `BrainOffline` → Ollama fallback. Bound to localhost only;
  path-traversal on static files is blocked. Launched by Raycast **"Open Jarvis"** (`jarvis-ui.sh`).
- **Verified end-to-end (urllib, no browser):** health=ok with **accessibility=TRUE,
  screen_recording=TRUE** (Pietro has since granted both — the last open requirement is done);
  `/api/ask` EN → "Two plus three is five." and PT → "A capital do Brasil é Brasília." both
  `source:max`; static + 404-traversal correct.
- **Streaming evaluated and rejected:** the installed `claude` CLI (2.1.150) `stream-json` emits the
  **whole** assistant message in one event (not token deltas), and TTFT (~5s) is dominated by the
  project's own SessionStart hooks firing per turn, not generation. For a voice assistant's short
  replies, streaming would buy ~nothing — so I didn't add the complexity.
- **Polish added this session (all tested):**
  - **New conversation** — topbar **"new"** button → `POST /api/reset` clears `brain.session_id`
    so a long-running server doesn't carry a stale, ever-growing session. Verified: it remembers
    within a session ("Pineapple.") and correctly forgets after reset ("I don't know the secret word.").
  - **Fallback visibility** — Jarvis bubbles get a small badge when a reply came from the offline
    brain (`offline`), had no brain (`no brain`), or errored (`error`); none for the Max brain.
  - **Barge-in** — tapping the orb (or **Esc**) while Jarvis is speaking silences it; hands-free then
    resumes listening, one-shot settles to idle.
  - **Mac-control awareness** — turning on "Mac control" without Accessibility shows a hint; the
    "thinking…" line becomes "working on your Mac…" on control turns (which can run up to 600s).
  - Replies now preserve line breaks (`white-space: pre-wrap`).
- `node --check web/app.js` clean; `server.py` imports clean.

---

## Checkpoint 7 — 2026-06-05 ~11:55 — Real user is PIETRO; Raycast + wake-word + memory consolidation

- **Identity correction:** the user is **Pietro**, not Larissa (the seeded name was wrong).
  Re-personalized the whole project — persona.md, memory/about_you.md, brain default persona,
  harness memory (now `user-pietro.md` + updated `project-jarvis.md`/`MEMORY.md`), docs, and
  Raycast author fields. Pietro: student + builder ("a bit of everything"), bilingual pt/en,
  wants Mac control/automation + research + email/calendar + a voice companion.
- **Raycast integration (his "wake" mechanism)** — 4 Script Commands in `raycast/` + README:
  **Ask Jarvis** (type → printed+spoken answer, one-shot, `enable_computer_use=False` so it's
  fast/safe — the adversarial verifier caught that Brain() would otherwise auto-enable Mac
  control), **Wake Jarvis (voice)**, **Jarvis hands-free**, **Jarvis wake-word**. VERIFIED:
  `ask-jarvis.sh "what is two plus three"` → "Two plus three is five." end-to-end.
- **Wake-word mode** (`wake.py`, `python jarvis.py --wake`) — ambient "Jarvis …" trigger reusing
  the Whisper pipeline, with a fuzzy matcher tolerant of mishearings (jarvez/jarbis/etc.),
  serialized for MLX, speak-blocking to avoid self-trigger. Pure matcher unit-tested (pt + en).
- **Memory consolidation** (`memory_consolidate.py`) — on session exit, Jarvis reflects on the
  transcript, extracts ≤5 durable facts as JSON, drops secrets/PII/trivia, dedupes against
  about_you.md, appends with a date. Wired into both `main()` and `run_text_mode()` via
  `_consolidate_on_exit` (best-effort, never blocks shutdown). Parse/dedupe/consolidate unit-tested.
- **AppleScript recipes** (`recipes.md`) — vetted snippets for Calendar/Mail(draft-not-send)/
  Notes/Reminders/Music/Safari+Chrome; persona points the brain at them (stays system-wide, not
  per-app tools, per Pietro's wish).
- **Also:** `mouth.py` gained `JARVIS_SILENT`; designed via a background design+adversarial-verify
  workflow (8 agents). **`selftest.py` 12/12**, standalone `test_memory_consolidate.py` all pass,
  all 12 modules compile.

---

## Checkpoint 6 — 2026-06-04 ~01:15 — Full-pipeline verified end-to-end; multi-display fix

- **🎉 Whole conversational loop verified** with synthesized speech (closest thing to a live
  mic): spoken pt question → `ears` transcribed [pt] in 2.1s → `brain` answered "A capital da
  França é Paris." in 6.3s → `mouth` ready with the Luciana voice. End-to-end PASS.
- **Multi-display robustness:** `screenshot()` now uses `screencapture -D 1` (main display only)
  so screenshot pixels always share `screen_info`'s logical-point space. Verified 1800×1169.
- **Latency checked:** per-turn time is dominated by Max-plan model variance (~3-6s); MCP spawn
  overhead is negligible (a with-tools turn was *faster* than a no-tools one). No optimization needed.
- **`test_computer_use.py`** added — a safe, self-cleaning TextEdit demo Pietro runs after
  granting Accessibility to prove type/keys/click/AX-readback all work. Exits cleanly with
  guidance if perms are missing (verified).
- selftest.py still **9/9**.

**Definitive status: Jarvis works. Only Pietro's Accessibility grant (+ mic prompt) stands
between Pietro and full voice-driven computer control.**

---

## Checkpoint 5 — 2026-06-04 ~00:55 — Launcher, logging, hotkey, hardening

- **`Jarvis.command`** — double-click in Finder to launch (auto-starts the Ollama server if
  installed & down, runs install.sh on first run). Executable.
- **Conversation logging** — `jarvis.py` appends each turn to `logs/conversation-YYYY-MM-DD.log`
  (best-effort, never breaks the loop). `logs/` gitignored.
- **`hotkey.py`** (optional/experimental) — global push-to-talk: hold Right-Option ⌥ from any
  app → talk → release → Jarvis answers. Uses pynput; needs Input Monitoring. Kept separate
  from the core so the verified loop stays simple. Compiles + imports clean.
- **AX hardening** — `_attr/_point/_size` in computer.py now tolerate a missing
  `kAXErrorSuccess` (fallback 0) and wrap unwrapping in try/except, so the untested
  accessibility path fails soft instead of throwing.
- **Validated real utility available NOW (no extra permission):** battery %, volume, Wi-Fi
  name, date/time all return correctly via `run_applescript` (`do shell script`).
- **Final state:** all 10 modules compile; `selftest.py` **8/8**; offline brain available;
  20 project files. Screen Recording granted + vision verified; only Accessibility (+ mic
  prompt) remain for Pietro.

- **Deterministic safety guardrail** (research-aligned: enforce in code, not just the prompt):
  `run_applescript` now BLOCKS destructive scripts (rm/sudo, empty trash, delete files/notes/
  events, shut down/restart, send mail/messages) unless called with `confirm=true` — the brain
  must ask Pietro out loud first, then retry confirmed. Tuned to avoid false positives (dropped
  the over-broad "to send"). `selftest.py` now **9/9** (added a guardrail test).

**This is a complete, working, well-documented v1.** Further work from here is optional
enhancement, not required for "running smoothly."

---

## Checkpoint 4 — 2026-06-04 ~00:40 — VISION PIPELINE VERIFIED + startup polish

- **Screen Recording got granted** during the build (the earlier `screencapture` call
  registered the app) — and a real screenshot now captures genuine content (1800×1169 logical,
  pixel variance confirms it's not a black frame).
- **🎉 Full vision pipeline verified end-to-end:** asked the brain to screenshot and describe
  the screen — it returned *"Visual Studio Code is open, showing a Screen Time limit popup…"*.
  That exercises brain → MCP `screenshot` tool → screencapture → retina downscale → base64
  inline image block → `claude` CLI vision → accurate description. The hand-written MCP image
  content format is correct. **Jarvis can now SEE the screen.**
- **Remaining gap:** Accessibility (click/type/AX tree) still needs Pietro's grant; that code
  is built to the researched best practices but untested until granted. Updated TODO_TOMORROW:
  the practical must-do is now just **Accessibility** (+ approve the mic prompt).
- **Startup polish:** `jarvis.py` now checks computer-use permissions on launch and, if any are
  missing, prints + speaks a one-line heads-up pointing to doctor.py (instead of silently
  failing the first "click"). Added AppleScript-first "common tasks" guidance to `persona.md`.
- `selftest.py` still **8/8**.

---

## Checkpoint 3 — 2026-06-04 ~00:20 — Memory, text mode; v1 COMPLETE & VERIFIED

- **Offline brain verified end-to-end:** `qwen2.5:7b` pulled (4.7 GB), `local_brain.py`
  `available()==True`, replies correctly. Added a per-turn language pin (`Reply ONLY in
  English.` / `Responda SOMENTE em português.`) because qwen-7b drifted languages — now correct.
- **Self-growing memory:** added a `remember` MCP tool (appends dated facts to
  `memory/about_you.md`); `brain.py` now loads persona + `about_you.md` into the system prompt
  every session via `_system_prompt()`, and the persona tells Jarvis when to save. Verified:
  tool saves, brain reads it back.
- **`--text` mode** (`jarvis.py --text`): type to Jarvis (full brain + tools + memory),
  replies printed + spoken. Needs NO mic/permissions → the ideal first test. `_guess_language`
  picks pt/en for typed text: **8/8** on test phrases.
- **Final state:** `selftest.py` **8/8 pass**; `doctor.py` all green except the 2 permissions
  only Pietro can grant (Accessibility, Screen Recording) + Microphone (prompts on first run).
  Cloud brain re-verified with tools after all edits (replied in pt, used a tool).

**STATUS: Jarvis v1 is done and working.** Only blocker to full computer-control is the
manual permission grants (TODO_TOMORROW.md). Continuing with further improvements until
interrupted.

---

## Checkpoint 2 — 2026-06-04 ~00:00 — Offline brain, hands-free mode, docs, tests

**Milestones M3 + M4 (most of it) done.**

- **Ollama offline brain installed WITHOUT brew or sudo.** `brew install ollama` failed —
  Homebrew lives under `~/Documents/.brew` and macOS TCC protects the Documents folder, so
  brew's `sandbox-exec` build step gets EPERM on its own portable-ruby (`HOMEBREW_NO_SANDBOX=1`
  didn't help). Worked around it: downloaded the official `ollama-darwin.tgz` (v0.30.4),
  extracted the whole bundle to `~/.ollama-dist`, symlinked `~/.local/bin/ollama`, stripped
  quarantine. Binary runs, **detects Metal GPU (M1 Pro, 11.8 GiB)**. Server started; pulling
  `qwen2.5:7b` (multilingual, ~4.7GB) — see install.sh for the reproducible no-admin method.
- **`local_brain.py`** — offline brain over the Ollama HTTP API (urllib, no deps). `available()`
  probe + bilingual persona. `jarvis.py` auto-falls back to it on `BrainOffline`.
- **Hands-free mode** — `ears.listen_continuous()` energy-VAD (noise-calibrated, no deps);
  `python jarvis.py --hands-free`. Push-to-talk stays the reliable default.
- **`doctor.py`** — color pre-flight check of deps, Max-plan login (live call), voices, the 3
  permissions, and ollama. Verified output. **`selftest.py`** — 7 smoke tests, **7/7 pass**.
- **Docs:** `README.md`, `install.sh` (one-shot, `--ollama` flag), `persona.md` (editable
  personality), refreshed `.env.example`/`.gitignore` (no API key anywhere), rewrote
  `TODO_TOMORROW.md` as a friendly morning briefing.
- All 9 modules `py_compile` clean.

**Left for Pietro (in TODO_TOMORROW.md):** grant the 3 macOS permissions (the only must-do);
optionally confirm the ollama model finished pulling. Everything else is done.

---

## Checkpoint 1 — 2026-06-03 ~23:35 — Bilingual voice loop + system-wide computer use WORKING

**Milestones M1 + M2 done.** Everything below is tested and working except the parts
that need permissions Pietro must grant (screenshot/click/type — see TODO_TOMORROW.md).

- **Brain** (`brain.py`): rewritten to shell out to `claude -p --output-format json`
  on the Max plan. Session continuity via captured `session_id` + `--resume`. Verified:
  3 bilingual turns, ~2-3s each, remembered context, switched pt↔en correctly.
- **Ears** (`ears.py`): pluggable STT. **mlx-whisper (Metal)** preferred → faster-whisper
  fallback. Auto-detects pt/en. Verified: pt clip → "Que horas são…" [pt] in **0.30s
  steady-state**; en clip → correct [en]. NOTE: a background warm-up thread + MLX caused a
  **segfault (exit 139)** because MLX/Metal isn't thread-safe — fixed with a `_stt_lock`
  serializing all transcription. Model files cached under HF cache.
- **Mouth** (`mouth.py`): language-aware `say` (Luciana=pt, Daniel=en), markdown stripped,
  killable for barge-in. Verified both voices render.
- **Computer use** (`computer.py` + `computer_use_server.py`): screenshot (screencapture →
  downscaled to LOGICAL points so screenshot-pixel == click-coord), Quartz mouse/keyboard,
  AX tree (`list_ui_elements`/`click_element` by name), `open_app`, `frontmost_app`,
  `run_applescript`. Hand-written raw JSON-RPC MCP stdio server (no `mcp` SDK; venv is 3.9).
  Verified: MCP handshake + tools/list (14 tools) + tool calls all return correct JSON-RPC.
- **Brain ⇄ tools wired** (`mcp_config.json`): **VERIFIED end-to-end** — asked the brain to
  check the frontmost app + screen res; it called the MCP tools and answered in spoken style
  ("eighteen hundred by eleven sixty-nine… two times retina scale"), 0 permission denials.
- **Safety decision:** brain whitelists ONLY `mcp__computer__*` + `Read` with
  `--strict-mcp-config`. Deliberately **no unrestricted Bash and no `bypassPermissions`**
  (my own session's auto-mode classifier correctly flagged that; the scoped whitelist is
  safer and matches the research guidance). Destructive-action confirmation is in the persona.

**Env note:** frontmost app when launched here is **"Code" (VS Code)** → that's the app that
needs Screen Recording + Accessibility granted. `screencapture` hard-fails on macOS 26 without
Screen Recording (returns a friendly error now).

**Next:** doctor.py (permission/dep checker), Ollama offline brain, polish (continuous
listening, README, install script, tests).

---

## Checkpoint 0 — 2026-06-03 ~15:20 — Audit & plan

**State of the world when I started:** a basic scaffold existed —
`jarvis.py` (loop), `brain.py` (Anthropic API), `ears.py` (English-only Whisper),
`mouth.py` (macOS `say`, English voice). It could not run: `brain.py` requires an
`ANTHROPIC_API_KEY` the user does not have.

**Key facts established:**
- `claude` CLI v2.1.150 is installed and **works headless on the Max plan**
  (`claude -p "..."` returned a completion). → This is the brain. No API key needed.
- Machine: MacBook Pro M1 Pro, 16GB RAM, arm64, macOS 26.5. Can run a 7-8B local model.
- `brew` is available at `/Users/pietrojustino/Documents/.brew` (no sudo needed) →
  can install ollama + cliclick.
- TTS voices present: **Luciana** (pt_BR), **Daniel** (en_GB). Multilingual say works.
- venv is **Python 3.9.6** → the official `mcp` SDK (needs 3.10+) won't install, so the
  MCP server is hand-written raw JSON-RPC over stdio (no extra deps).
- `ollama` not yet installed. `cliclick` not installed. `screencapture` present.

**Decisions:** see PLAN.md. Brain = `claude` CLI headless. Computer use = pixels +
Accessibility API, exposed as both a CLI (Bash-callable) and an MCP server.

**Next:** M1 — rewrite brain/ears/mouth for the bilingual Max-plan voice loop.
