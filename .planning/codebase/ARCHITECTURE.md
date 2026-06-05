# Architecture

**Analysis Date:** 2026-06-05

## Pattern Overview

**Overall:** Event-driven pipeline with a shell-out brain and MCP computer-use sidecar.

**Key Characteristics:**
- Voice pipeline is three independent modules: EARS → BRAIN → MOUTH
- Brain has no internal Python conversation state; session continuity relies on the `claude` CLI's `--resume <session_id>` flag
- Computer control is a separate stdio MCP server process (`computer_use_server.py`) spawned by the `claude` CLI itself — Jarvis never calls `computer.py` directly for Claude-initiated actions
- Two brain tiers: cloud (Max-plan `claude` CLI) with automatic fallback to local Ollama
- Five independent entry points for different interaction modes (all share the same Brain/EARS/MOUTH modules)

---

## Layers

**EARS — Speech-to-Text (`ears.py`):**
- Purpose: Capture microphone audio, transcribe to text, detect language (pt/en)
- Location: `ears.py`
- Contains: Backend selection (mlx-whisper vs faster-whisper), VAD, push-to-talk and hands-free recording functions
- Depends on: `mlx_whisper` or `faster_whisper`, `sounddevice`, `numpy`
- Used by: `jarvis.py`, `hotkey.py`, `wake.py`
- Key functions: `listen() -> (str, str)`, `listen_continuous() -> (str, str)`, `transcribe_file()`
- Thread safety: `_stt_lock` serializes all transcriptions (MLX is not thread-safe)

**BRAIN — Claude Max-plan via CLI (`brain.py`):**
- Purpose: Send user text to Claude, receive spoken reply, maintain conversation continuity
- Location: `brain.py`
- Contains: `Brain` class, `BrainOffline` exception, persona/memory loading, `claude` CLI subprocess invocation
- Depends on: `claude` CLI on `$PATH` (or `~/.local/bin/claude`), `mcp_config.json` (optional)
- Used by: `jarvis.py`, `hotkey.py`, `server.py`, `wake.py`
- Session continuity: `Brain.session_id` is captured from the `--output-format json` response and passed as `--resume` on subsequent turns
- Computer use: when `mcp_config.json` exists, `--mcp-config`, `--strict-mcp-config`, and `--allowedTools` flags are added to whitelist only the `mcp__computer__*` tools

**BRAIN FALLBACK — Ollama (`local_brain.py`):**
- Purpose: Offline conversational fallback when cloud brain raises `BrainOffline`
- Location: `local_brain.py`
- Contains: `LocalBrain` class, `/api/chat` and `/api/tags` Ollama HTTP calls
- Depends on: Ollama running at `OLLAMA_HOST` (default `127.0.0.1:11434`), model `qwen2.5:7b`
- Used by: `jarvis.py`, `server.py`, `hotkey.py` (partially)
- Limitations: No computer-use tools; plain conversational only; per-instance history list (not CLI session)

**MOUTH — Text-to-Speech (`mouth.py`):**
- Purpose: Speak reply text aloud via macOS `say`; strip markdown before speaking
- Location: `mouth.py`
- Contains: `speak()`, `stop()`, `is_speaking()`, `_clean()` markdown stripper
- Depends on: macOS built-in `say` command
- Used by: `jarvis.py`, `hotkey.py`, `wake.py`
- Barge-in: `stop()` terminates the active `say` subprocess when a new utterance starts
- Voice selection: `JARVIS_VOICE_PT` (Luciana) / `JARVIS_VOICE_EN` (Samantha), env-overridable

**COMPUTER-USE MCP SIDECAR (`computer_use_server.py` + `computer.py`):**
- Purpose: Give the Claude brain hands and eyes — screenshot, click, type, AppleScript, Accessibility
- Location: `computer_use_server.py` (MCP stdio server), `computer.py` (macOS primitives)
- Contains: Hand-written JSON-RPC 2.0 / MCP stdio protocol (no SDK; Python 3.9 compat), tool definitions wrapping `computer.py`
- Spawned by: `claude` CLI when Brain calls `--mcp-config mcp_config.json`; Jarvis's Python process does NOT call it directly
- Tools exposed: `screenshot`, `screen_info`, `click`, `double_click`, `right_click`, `move_mouse`, `scroll`, `type_text`, `key`, `list_ui_elements`, `click_element`, `open_app`, `frontmost_app`, `run_applescript`, `remember`
- `remember` tool: writes facts to `memory/about_you.md`

**WEB UI SERVER (`server.py`):**
- Purpose: Browser-based UI at `http://127.0.0.1:8765`; speech recognition and TTS in the browser (Web Speech API)
- Location: `server.py`, static files in `web/`
- Contains: `ThreadingHTTPServer`, `Handler` (GET static files, POST `/api/ask`, POST `/api/reset`, GET `/api/health`)
- Depends on: Python stdlib only (`http.server`), same `Brain` and `LocalBrain` classes
- Serves: `web/index.html`, `web/style.css`, `web/app.js`
- Session reset: `POST /api/reset` clears `Brain.session_id` to start a fresh conversation

---

## Data Flow

**Standard terminal push-to-talk turn (one loop cycle in `jarvis.py`):**

1. `listen()` in `ears.py` — blocks on Enter key, records mic via `sounddevice`, transcribes with Whisper → returns `(text, lang)`
2. `_is_goodbye()` in `jarvis.py` — regex check; if matched, speak farewell and break loop
3. `Brain.think(text)` in `brain.py` — builds `claude -p <text> --output-format json --resume <session_id> --mcp-config ...` subprocess → blocks until reply
4. If `BrainOffline` raised → `LocalBrain.think(text)` via Ollama HTTP
5. `speak(reply, lang)` in `mouth.py` — strips markdown, runs `say -v <voice> -r 178 <text>` subprocess
6. Session appended: `session.append(("you", lang, text))` / `("jarvis", lang, reply)`
7. On exit (goodbye or Ctrl+C): `_consolidate_on_exit(session)` in daemon thread

**Hands-free turn (same loop, different listen fn):**
- Uses `listen_continuous()` instead of `listen()` — energy-based VAD, no Enter required
- Calibrates ambient noise at startup; captures speech until 800ms silence

**Wake-word turn (`wake.py → run_wake_loop()`):**
1. `listen_continuous()` captures ambient utterance
2. `match_wake_word()` fuzzy-matches against "jarvis" (SequenceMatcher + alias list)
3. If matched, strip wake word from text, route to `Brain.think()`
4. Speak reply; optional follow-up window without requiring wake word again

**Global hotkey turn (`hotkey.py → PushToTalk`):**
1. `pynput` keyboard listener monitors Right Option key (or `JARVIS_HOTKEY`)
2. Hold key → mic records to frame queue; release → `_handle_turn()` in daemon thread
3. `_transcribe_array(audio)` → `Brain.think(text)` → `speak(reply, lang)`

**Web UI turn (`server.py → POST /api/ask`):**
1. Browser sends `{"text": "...", "control": bool, "lang": "en"}` to `/api/ask`
2. `_ask()` invokes `Brain.think()` (with `computer_use` toggled by `control` flag)
3. Returns `{"reply": "...", "source": "max"|"ollama"|"offline"|"error"}`
4. Browser TTS (Web Speech API) speaks the reply

**Memory consolidation (end-of-session):**
1. `consolidate(session)` in `memory_consolidate.py` formats transcript
2. Sends to `claude` CLI (headless, no tools) with extraction prompt
3. Parses JSON fact list, dedupes against `memory/about_you.md`, appends survivors with date stamp

**MCP computer-use tool call (within a Brain turn):**
1. Claude's response requests a tool call (e.g., `mcp__computer__screenshot`)
2. `claude` CLI routes to `computer_use_server.py` via stdio MCP protocol
3. Server calls the corresponding `computer.py` function
4. Result (image bytes for screenshot, text for others) returned to Claude as tool result
5. Claude continues multi-step reasoning; final text reply returned to `Brain.think()`

---

## Key Abstractions

**`Brain` class (`brain.py`):**
- Purpose: Stateful wrapper around the `claude` CLI subprocess
- Pattern: `Brain.think(text) -> str` is the single call site for all callers
- Session continuity via `self.session_id` — persists turn-to-turn within one process lifetime
- `BrainOffline` exception is the fallback trigger

**`BrainOffline` exception (`brain.py`):**
- Purpose: Signals network/auth failure to callers without leaking subprocess details
- All callers (`jarvis.py`, `server.py`, `hotkey.py`) catch this and route to `LocalBrain`

**`LocalBrain` class (`local_brain.py`):**
- Purpose: Ollama chat via plain HTTP; per-instance history list
- No computer-use tools; purely conversational fallback

**MCP sidecar contract (`mcp_config.json`, `computer_use_server.py`):**
- `mcp_config.json` declares the sidecar: `{"mcpServers": {"computer": {"command": ".venv/bin/python", "args": ["computer_use_server.py"]}}}`
- `computer_use_server.py` implements JSON-RPC 2.0 over stdio (hand-written, no SDK)
- `COMPUTER_TOOLS` whitelist in `brain.py` restricts which MCP tools Claude may call

**Language detection (`jarvis.py` `_guess_language()` / `_speak_lang()`):**
- Used to pick TTS voice when Whisper's detected language is ambiguous for short replies
- Prefers reply text's own language (accented chars + word-list matching)

---

## Entry Points

**`jarvis.py` (primary):**
- Location: `jarvis.py`
- Triggers: `python jarvis.py` (PTT), `--hands-free` / `-c` (VAD), `--text` / `-t` (typed), `--wake` / `-w` (delegates to `wake.run_wake_loop()`)
- Responsibilities: Main conversation loop, language detection, goodbye detection, logging, memory consolidation on exit

**`server.py` (web UI):**
- Location: `server.py`
- Triggers: `python server.py`, Raycast `jarvis-ui.sh`
- Responsibilities: HTTP server on `127.0.0.1:8765`, static file serving for `web/`, `/api/ask`, `/api/reset`, `/api/health`

**`hotkey.py` (global PTT):**
- Location: `hotkey.py`
- Triggers: `python hotkey.py`
- Responsibilities: pynput keyboard listener, mic capture, one daemon thread per turn

**`wake.py` (wake-word loop):**
- Location: `wake.py`
- Triggers: `python jarvis.py --wake`
- Responsibilities: Continuous VAD listen, fuzzy wake-word matching, optional follow-up window

**`Jarvis.command` (macOS launcher):**
- Location: `Jarvis.command`
- Triggers: Double-click in Finder
- Responsibilities: Activates venv, runs `python jarvis.py`

---

## Error Handling

**Strategy:** Fail-soft with spoken-friendly error messages; never crash the loop on a single bad turn.

**Patterns:**
- `BrainOffline` exception routes to `LocalBrain`; if Ollama also unavailable, a hardcoded bilingual error string is spoken
- `brain.py` `think()`: catches `TimeoutExpired` and returns a friendly retry message
- `jarvis.py` `_log()`: wrapped in `try/except Exception: pass` — log failure never surfaces
- `jarvis.py` `_consolidate_on_exit()`: daemon thread with 25s timeout; never blocks shutdown
- `computer_use_server.py`: JSON-RPC errors returned as structured `{"error": ...}` responses; never crashes the server process
- `server.py` `_ask()`: broad `except Exception` returns `{"reply": "Something went wrong: ...", "source": "error"}` — never 500s the UI

---

## Cross-Cutting Concerns

**Language Routing:**
- Detected at EARS (Whisper returns language tag); propagated through the loop as `lang: str` ("pt" or "en")
- Brain persona instructs Claude to mirror the user's language
- MOUTH uses `lang` to select voice (Luciana/Samantha)
- `LocalBrain.think()` receives `language` param and appends an explicit "Reply ONLY in English/Portuguese" rule

**Memory:**
- Ephemeral (session): `session` list in `jarvis.py` collects `(role, lang, text)` tuples
- Durable (cross-session): `memory/about_you.md` — appended by `memory_consolidate.py` at session end and by the `remember` MCP tool mid-session
- Loaded into system prompt every Brain instantiation via `_load_memory()` in `brain.py`

**Persona:**
- `persona.md` — editable personality file loaded at Brain init; falls back to `DEFAULT_PERSONA` in `brain.py` if absent or empty

**Logging:**
- Conversation log: `logs/conversation-YYYY-MM-DD.log` — one line per turn, appended by `_log()` in `jarvis.py`
- MCP server log: `stderr` of `computer_use_server.py`
- Web UI logs: `logs/jarvis-ui.log`, `logs/jarvis-voice.log` (written by Raycast scripts)

**Permissions:**
- Microphone: required for all voice modes
- Screen Recording: required for `screenshot` MCP tool
- Accessibility: required for click/type/key MCP tools and `list_ui_elements`
- Input Monitoring: required for `hotkey.py` global PTT
- `doctor.py` checks and guides permission setup

---

*Architecture analysis: 2026-06-05*
