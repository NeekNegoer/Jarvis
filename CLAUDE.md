<!-- GSD:project-start source:PROJECT.md -->
## Project

**Jarvis**

Jarvis is Pietro's personal, **bilingual (pt-BR / English) system-wide macOS voice assistant** —
a hands-free chief-of-staff that listens, thinks with Claude (on his Max plan, no API key),
talks back in the language he used, and can control his whole Mac. v1 is complete and working.
This milestone makes it a **genuinely great daily driver in Chrome**: a real app-like UI, an
**extensible skill system** (starting with Google Classroom, since Pietro is a student), and the
**robustness to trust it** for real tasks.

**Core Value:** **Pietro can speak or type to Jarvis and have it reliably get real things done** — on his Mac and
in his student/daily life — in Portuguese or English, hands-free, without paying per use. If
everything else fails, that loop (understand → act → report, trustworthily) must work.

### Constraints

- **Tech stack**: Python **3.9.6** venv — blocks the official `mcp` SDK (needs 3.10+), hence the hand-written JSON-RPC MCP server in `computer_use_server.py`. New code must stay 3.9-compatible.
- **Brain**: the `claude` CLI on Pietro's **Max plan** — no `ANTHROPIC_API_KEY`, no per-use cost.
- **No sudo/admin**: everything installs without elevation; `brew` under `~/Documents` fails TCC.
- **Security**: localhost-only (`127.0.0.1`); Mac-control must stay gated and confirm before destructive actions.
- **Offline**: must degrade gracefully to the Ollama brain.
- **Bilingual**: pt-BR and English parity across every new feature.
- **Working style**: Pietro values waking up to working software over being asked questions — choose sensible defaults and act autonomously.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.9.6 — all backend logic (`jarvis.py`, `brain.py`, `ears.py`, `mouth.py`, `computer.py`, `computer_use_server.py`, `local_brain.py`, `wake.py`, `server.py`, `memory_consolidate.py`, `hotkey.py`, `doctor.py`)
- JavaScript (ES2015+, no build step) — browser-side web UI (`web/app.js`)
- Bash — setup and Raycast launcher scripts (`install.sh`, `raycast/*.sh`)
- HTML/CSS — web UI markup (`web/index.html`, `web/style.css`)
## Runtime
- Python 3.9.6, constrained by the project venv at `.venv/` (`pyvenv.cfg` pins `version = 3.9.6`)
- Python 3.9 compatibility is intentional: the official `mcp` SDK requires 3.10+, so `computer_use_server.py` uses a hand-written JSON-RPC 2.0 implementation over stdio instead
- macOS only — hard dependency on Apple-specific APIs and binaries (`say`, `screencapture`, `osascript`, Quartz, ApplicationServices, AppKit)
- Chrome required — `web/app.js` uses `window.webkitSpeechRecognition` (Chrome-only) for STT and `window.speechSynthesis` for TTS
- pip (stdlib venv via `python3 -m venv .venv`)
- Lockfile: absent — `requirements.txt` uses `>=` bounds only (no pinned versions, no Poetry/PDM)
## Frameworks
- No web framework — `server.py` uses Python stdlib `http.server.ThreadingHTTPServer` directly
- No test framework declared in `requirements.txt`; tests are standalone scripts:
- No build tools; source runs directly from the project root
- `install.sh` bootstraps the venv and optionally installs Ollama
## Key Dependencies
- `mlx-whisper>=0.4.0` — Metal-accelerated Whisper for Apple Silicon; preferred backend; model repo pattern: `mlx-community/whisper-{size}-mlx`
- `faster-whisper>=1.0.0` — CPU fallback; uses `WhisperModel(device="cpu", compute_type="int8")`
- `sounddevice>=0.4.6` — microphone capture (16 kHz, mono, float32)
- `numpy>=1.24.0` — audio buffer manipulation
- `scipy>=1.10.0` — `.wav` read/write (used by faster-whisper path via temp file)
- `pyobjc-framework-Quartz>=10.0` — screenshots (CGDisplayMode), mouse events (CGEvents), keyboard events
- `pyobjc-framework-ApplicationServices>=10.0` — macOS Accessibility API (AXUIElement tree walking)
- `pyobjc-framework-Cocoa>=10.0` — `NSWorkspace.sharedWorkspace().frontmostApplication()`
- `pillow>=10.0` — downscale retina screenshots to logical-point resolution (`Image.LANCZOS`)
- `pynput>=1.7` — optional; listens for a global push-to-talk hotkey from any app
- `claude` CLI (Claude Code) — NOT a pip package; installed separately, authenticated against the user's Max plan subscription. Invoked via `subprocess.run()`. Located at `~/.local/bin/claude` or on `$PATH`.
- macOS built-in `say` command — no pip package; invoked via `subprocess`
## Configuration
| Variable | Default | Purpose |
|---|---|---|
| `JARVIS_WHISPER_MODEL` | `small` | Whisper model size: `tiny`, `base`, `small`, `medium` |
| `JARVIS_STT` | auto | Force backend: `mlx` or `faster` |
| `JARVIS_OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model for offline brain |
| `JARVIS_VOICE_PT` | `Luciana` | macOS `say` voice for Brazilian Portuguese |
| `JARVIS_VOICE_EN` | `Samantha` | macOS `say` voice for English |
| `JARVIS_VOICE_RATE` | `178` | Speech rate in words per minute |
| `JARVIS_SILENT` | (unset) | Set `1`/`true`/`yes` to suppress audio (text only) |
| `JARVIS_WAKE_WORD` | `jarvis` | Wake word for `--wake` mode |
| `JARVIS_WAKE_THRESHOLD` | `0.75` | Fuzzy match ratio for wake-word detection |
| `JARVIS_WAKE_FOLLOWUP_SECS` | `0` | Seconds to stay in hands-free after a reply |
| `OLLAMA_HOST` | `127.0.0.1:11434` | Ollama server address |
- `mcp_config.json` — registers `computer_use_server.py` as an MCP stdio server for the `claude` CLI; presence of this file enables computer use in `brain.py`
- `persona.md` — editable system prompt; overrides the default `DEFAULT_PERSONA` in `brain.py` if present
- `memory/about_you.md` — long-term memory file appended by the `remember` MCP tool; read into the system prompt every session
- No build step; `install.sh` only creates the venv and installs `requirements.txt`
## Platform Requirements
- macOS (tested on macOS 26 / Apple Silicon M1+)
- Python 3.9.6 (via Xcode Command Line Tools or pyenv)
- Claude Code CLI installed and authenticated with Max plan
- macOS permissions required: Screen Recording + Accessibility (for computer use)
- Microphone permission (for voice modes)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- `snake_case.py`, one concept per file named after its sensory/cognitive role: `brain.py`, `mouth.py`, `ears.py`, `wake.py`, `computer.py`, `memory_consolidate.py`
- Test files: `test_<module>.py` or `selftest.py`
- Public API: `snake_case` — `speak`, `listen`, `stop`, `match_wake_word`, `consolidate`, `parse_facts`, `dedupe`, `is_duplicate`
- Private helpers: leading underscore — `_clean`, `_log`, `_guess_language`, `_build_prompt`, `_load_persona`, `_normalize`, `_memory_lines`, `_iter_turns`, `_format_transcript`
- `if __name__ == "__main__":` blocks in every module serve as quick standalone demos or manual tests
- Module-level constants: `UPPER_SNAKE_CASE` — `SAMPLE_RATE`, `MODEL_NAME`, `CHAT_TIMEOUT`, `MEMORY_FILE`, `VOICES`, `RATE`, `SILENT`, `GOODBYE_WORDS`, `MAX_FACTS`, `MAX_FACT_LEN`
- Local variables and parameters: `snake_case`
- `PascalCase` — `Brain`, `BrainOffline`, `LocalBrain`
- Custom exceptions inherit from `Exception` and carry a descriptive message: `class BrainOffline(Exception): """Raised when the Max-plan brain can't be reached..."""`
## Type Hints
## Module Structure
## Env-var Configuration Convention
- `JARVIS_VOICE_PT` / `JARVIS_VOICE_EN` — TTS voice name (`mouth.py`)
- `JARVIS_VOICE_RATE` — words per minute (`mouth.py`)
- `JARVIS_SILENT` — suppress audio output (`mouth.py`)
- `JARVIS_WHISPER_MODEL` — Whisper model size (`ears.py`)
- `JARVIS_STT` — force backend "mlx" or "faster" (`ears.py`)
- `JARVIS_WAKE_WORD` — custom wake word (`wake.py`)
- `JARVIS_WAKE_THRESHOLD` — fuzzy match ratio 0..1 (`wake.py`)
- `JARVIS_WAKE_FOLLOWUP_SECS` — post-reply listening window (`wake.py`)
## Persona/Recipes Markdown-as-Config Pattern
- Loaded by `brain.py`'s `_load_persona()` on every `Brain.__init__()` call
- If missing or empty, `brain.py` falls back to its hardcoded `DEFAULT_PERSONA` constant
- The file ends with `# Edit this file freely to change how Jarvis behaves — it's loaded fresh every session.`
- Not loaded by Python code; instead `persona.md` instructs the LLM to reference it
- Contains AppleScript snippets the brain runs via `run_applescript` tool
- New app support added by editing only this markdown file
- Runtime-written; appended by `memory_consolidate.py`'s `_append_facts()`
- Format: `- <fact>  _(learned YYYY-MM-DD)_` (markdown bullets with date stamps)
- Parsed by `_memory_lines()` which keeps only bullet lines (`-`, `*`, `•`) and skips headers/notes
- Injected into the system prompt by `brain.py`'s `_system_prompt()`
## Error Handling
## Import Organization
## Comments
## Path Handling
## Linting and Formatting
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Voice pipeline is three independent modules: EARS → BRAIN → MOUTH
- Brain has no internal Python conversation state; session continuity relies on the `claude` CLI's `--resume <session_id>` flag
- Computer control is a separate stdio MCP server process (`computer_use_server.py`) spawned by the `claude` CLI itself — Jarvis never calls `computer.py` directly for Claude-initiated actions
- Two brain tiers: cloud (Max-plan `claude` CLI) with automatic fallback to local Ollama
- Five independent entry points for different interaction modes (all share the same Brain/EARS/MOUTH modules)
## Layers
- Purpose: Capture microphone audio, transcribe to text, detect language (pt/en)
- Location: `ears.py`
- Contains: Backend selection (mlx-whisper vs faster-whisper), VAD, push-to-talk and hands-free recording functions
- Depends on: `mlx_whisper` or `faster_whisper`, `sounddevice`, `numpy`
- Used by: `jarvis.py`, `hotkey.py`, `wake.py`
- Key functions: `listen() -> (str, str)`, `listen_continuous() -> (str, str)`, `transcribe_file()`
- Thread safety: `_stt_lock` serializes all transcriptions (MLX is not thread-safe)
- Purpose: Send user text to Claude, receive spoken reply, maintain conversation continuity
- Location: `brain.py`
- Contains: `Brain` class, `BrainOffline` exception, persona/memory loading, `claude` CLI subprocess invocation
- Depends on: `claude` CLI on `$PATH` (or `~/.local/bin/claude`), `mcp_config.json` (optional)
- Used by: `jarvis.py`, `hotkey.py`, `server.py`, `wake.py`
- Session continuity: `Brain.session_id` is captured from the `--output-format json` response and passed as `--resume` on subsequent turns
- Computer use: when `mcp_config.json` exists, `--mcp-config`, `--strict-mcp-config`, and `--allowedTools` flags are added to whitelist only the `mcp__computer__*` tools
- Purpose: Offline conversational fallback when cloud brain raises `BrainOffline`
- Location: `local_brain.py`
- Contains: `LocalBrain` class, `/api/chat` and `/api/tags` Ollama HTTP calls
- Depends on: Ollama running at `OLLAMA_HOST` (default `127.0.0.1:11434`), model `qwen2.5:7b`
- Used by: `jarvis.py`, `server.py`, `hotkey.py` (partially)
- Limitations: No computer-use tools; plain conversational only; per-instance history list (not CLI session)
- Purpose: Speak reply text aloud via macOS `say`; strip markdown before speaking
- Location: `mouth.py`
- Contains: `speak()`, `stop()`, `is_speaking()`, `_clean()` markdown stripper
- Depends on: macOS built-in `say` command
- Used by: `jarvis.py`, `hotkey.py`, `wake.py`
- Barge-in: `stop()` terminates the active `say` subprocess when a new utterance starts
- Voice selection: `JARVIS_VOICE_PT` (Luciana) / `JARVIS_VOICE_EN` (Samantha), env-overridable
- Purpose: Give the Claude brain hands and eyes — screenshot, click, type, AppleScript, Accessibility
- Location: `computer_use_server.py` (MCP stdio server), `computer.py` (macOS primitives)
- Contains: Hand-written JSON-RPC 2.0 / MCP stdio protocol (no SDK; Python 3.9 compat), tool definitions wrapping `computer.py`
- Spawned by: `claude` CLI when Brain calls `--mcp-config mcp_config.json`; Jarvis's Python process does NOT call it directly
- Tools exposed: `screenshot`, `screen_info`, `click`, `double_click`, `right_click`, `move_mouse`, `scroll`, `type_text`, `key`, `list_ui_elements`, `click_element`, `open_app`, `frontmost_app`, `run_applescript`, `remember`
- `remember` tool: writes facts to `memory/about_you.md`
- Purpose: Browser-based UI at `http://127.0.0.1:8765`; speech recognition and TTS in the browser (Web Speech API)
- Location: `server.py`, static files in `web/`
- Contains: `ThreadingHTTPServer`, `Handler` (GET static files, POST `/api/ask`, POST `/api/reset`, GET `/api/health`)
- Depends on: Python stdlib only (`http.server`), same `Brain` and `LocalBrain` classes
- Serves: `web/index.html`, `web/style.css`, `web/app.js`
- Session reset: `POST /api/reset` clears `Brain.session_id` to start a fresh conversation
## Data Flow
- Uses `listen_continuous()` instead of `listen()` — energy-based VAD, no Enter required
- Calibrates ambient noise at startup; captures speech until 800ms silence
## Key Abstractions
- Purpose: Stateful wrapper around the `claude` CLI subprocess
- Pattern: `Brain.think(text) -> str` is the single call site for all callers
- Session continuity via `self.session_id` — persists turn-to-turn within one process lifetime
- `BrainOffline` exception is the fallback trigger
- Purpose: Signals network/auth failure to callers without leaking subprocess details
- All callers (`jarvis.py`, `server.py`, `hotkey.py`) catch this and route to `LocalBrain`
- Purpose: Ollama chat via plain HTTP; per-instance history list
- No computer-use tools; purely conversational fallback
- `mcp_config.json` declares the sidecar: `{"mcpServers": {"computer": {"command": ".venv/bin/python", "args": ["computer_use_server.py"]}}}`
- `computer_use_server.py` implements JSON-RPC 2.0 over stdio (hand-written, no SDK)
- `COMPUTER_TOOLS` whitelist in `brain.py` restricts which MCP tools Claude may call
- Used to pick TTS voice when Whisper's detected language is ambiguous for short replies
- Prefers reply text's own language (accented chars + word-list matching)
## Entry Points
- Location: `jarvis.py`
- Triggers: `python jarvis.py` (PTT), `--hands-free` / `-c` (VAD), `--text` / `-t` (typed), `--wake` / `-w` (delegates to `wake.run_wake_loop()`)
- Responsibilities: Main conversation loop, language detection, goodbye detection, logging, memory consolidation on exit
- Location: `server.py`
- Triggers: `python server.py`, Raycast `jarvis-ui.sh`
- Responsibilities: HTTP server on `127.0.0.1:8765`, static file serving for `web/`, `/api/ask`, `/api/reset`, `/api/health`
- Location: `hotkey.py`
- Triggers: `python hotkey.py`
- Responsibilities: pynput keyboard listener, mic capture, one daemon thread per turn
- Location: `wake.py`
- Triggers: `python jarvis.py --wake`
- Responsibilities: Continuous VAD listen, fuzzy wake-word matching, optional follow-up window
- Location: `Jarvis.command`
- Triggers: Double-click in Finder
- Responsibilities: Activates venv, runs `python jarvis.py`
## Error Handling
- `BrainOffline` exception routes to `LocalBrain`; if Ollama also unavailable, a hardcoded bilingual error string is spoken
- `brain.py` `think()`: catches `TimeoutExpired` and returns a friendly retry message
- `jarvis.py` `_log()`: wrapped in `try/except Exception: pass` — log failure never surfaces
- `jarvis.py` `_consolidate_on_exit()`: daemon thread with 25s timeout; never blocks shutdown
- `computer_use_server.py`: JSON-RPC errors returned as structured `{"error": ...}` responses; never crashes the server process
- `server.py` `_ask()`: broad `except Exception` returns `{"reply": "Something went wrong: ...", "source": "error"}` — never 500s the UI
## Cross-Cutting Concerns
- Detected at EARS (Whisper returns language tag); propagated through the loop as `lang: str` ("pt" or "en")
- Brain persona instructs Claude to mirror the user's language
- MOUTH uses `lang` to select voice (Luciana/Samantha)
- `LocalBrain.think()` receives `language` param and appends an explicit "Reply ONLY in English/Portuguese" rule
- Ephemeral (session): `session` list in `jarvis.py` collects `(role, lang, text)` tuples
- Durable (cross-session): `memory/about_you.md` — appended by `memory_consolidate.py` at session end and by the `remember` MCP tool mid-session
- Loaded into system prompt every Brain instantiation via `_load_memory()` in `brain.py`
- `persona.md` — editable personality file loaded at Brain init; falls back to `DEFAULT_PERSONA` in `brain.py` if absent or empty
- Conversation log: `logs/conversation-YYYY-MM-DD.log` — one line per turn, appended by `_log()` in `jarvis.py`
- MCP server log: `stderr` of `computer_use_server.py`
- Web UI logs: `logs/jarvis-ui.log`, `logs/jarvis-voice.log` (written by Raycast scripts)
- Microphone: required for all voice modes
- Screen Recording: required for `screenshot` MCP tool
- Accessibility: required for click/type/key MCP tools and `list_ui_elements`
- Input Monitoring: required for `hotkey.py` global PTT
- `doctor.py` checks and guides permission setup
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
