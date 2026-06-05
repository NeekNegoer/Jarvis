# External Integrations

**Analysis Date:** 2026-06-05

## AI / Brain

**Claude CLI (Max plan) — primary brain:**
- What it does: receives every user utterance; returns a spoken reply; can invoke MCP computer-use tools
- SDK/Client: NOT a pip package — the `claude` binary is invoked via `subprocess.run()` in `brain.py`
- Auth: Claude Code OAuth (Max plan subscription); no `ANTHROPIC_API_KEY` required; managed entirely by the `claude` CLI's own login state
- Invocation pattern in `brain.py`:
  ```python
  cmd = [self.claude, "-p", user_text, "--output-format", "json",
         "--system-prompt", self.persona, "--mcp-config", str(MCP_CONFIG),
         "--strict-mcp-config", "--allowedTools", *COMPUTER_TOOLS]
  subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
  ```
- Session continuity: `--resume <session_id>` flag; `session_id` is parsed from the JSON stdout and stored on the `Brain` instance across turns
- Timeouts: 90 s for plain chat (`CHAT_TIMEOUT`), 600 s for computer-use turns (`COMPUTER_TIMEOUT`)
- Whitelisted tools (only these; no unrestricted Bash): `mcp__computer__screenshot`, `mcp__computer__click`, `mcp__computer__type_text`, `mcp__computer__key`, `mcp__computer__list_ui_elements`, `mcp__computer__click_element`, `mcp__computer__open_app`, `mcp__computer__run_applescript`, `mcp__computer__remember`, and eight others — see `COMPUTER_TOOLS` list in `brain.py`
- Error signal: `BrainOffline` exception raised when stderr contains `network`/`connect`/`timeout`/`offline`/`fetch failed`

**Ollama local server — offline fallback brain:**
- What it does: answers conversational queries when the cloud brain is unreachable; no computer-use tools
- Client: pure Python stdlib (`urllib.request`) in `local_brain.py`
- Base URL: `http://127.0.0.1:11434` (overridable via `OLLAMA_HOST`)
- Default model: `qwen2.5:7b` (overridable via `JARVIS_OLLAMA_MODEL`)
- Endpoints used:
  - `GET /api/tags` — availability check (lists pulled models)
  - `POST /api/chat` — chat completion (`stream: false`, `temperature: 0.6`, `num_predict: 300`)
- Installation: optional; `bash install.sh --ollama` downloads the macOS binary to `~/.ollama-dist/ollama` and symlinks to `~/.local/bin/ollama`
- Fallback logic: `brain.py` raises `BrainOffline` → `jarvis.py`/`server.py` call `LocalBrain().available()` → if true, route to Ollama

## MCP Stdio Server

**computer_use_server.py — gives the claude CLI "hands and eyes":**
- Protocol: hand-written JSON-RPC 2.0 over stdio (one message per line)
- Reason for hand-written: official `mcp` Python SDK requires Python 3.10+; this venv is 3.9.6
- Registration: `mcp_config.json` at project root registers it under the server name `"computer"`:
  ```json
  { "mcpServers": { "computer": {
      "command": ".venv/bin/python",
      "args": ["computer_use_server.py"]
  }}}
  ```
- Invoked as: a subprocess of the `claude` CLI (spawned automatically when `--mcp-config` is passed)
- MCP protocol version: `2024-11-05` (negotiated at `initialize`)
- Tools exposed (15):
  - Vision: `screenshot`, `screen_info`
  - Mouse: `click`, `double_click`, `right_click`, `move_mouse`, `scroll`
  - Keyboard: `type_text`, `key`
  - UI tree: `list_ui_elements`, `click_element`
  - Apps: `open_app`, `frontmost_app`
  - Scripting: `run_applescript` (with destructive-action guard; requires `confirm=true` for deletes/sends/power commands)
  - Memory: `remember` (appends to `memory/about_you.md`)
- stdout is protocol-only; all logging goes to stderr with `[computer-mcp]` prefix

## macOS System Services

**say — text-to-speech (`mouth.py`):**
- Invoked via `subprocess.run(["say", "-r", str(RATE), "-v", voice, text])`
- Blocking mode (`block=True`): `subprocess.run()` — voice finishes before next turn
- Non-blocking mode: `subprocess.Popen()` — stored in `_current` for barge-in via `mouth.stop()`
- Default voices: `Luciana` (pt-BR), `Samantha` (en) — both override via `JARVIS_VOICE_PT`/`JARVIS_VOICE_EN`
- Default rate: 178 wpm (override via `JARVIS_VOICE_RATE`)

**screencapture — screenshots (`computer.py`):**
- Binary: `/usr/sbin/screencapture`
- Invocation: `screencapture -x -D 1 -t png <path>` (silent, main display only, PNG)
- Output: retina physical pixels; downscaled to logical points by Pillow so click coordinates match pixel coordinates in the image
- Temp path: `/tmp/jarvis_screen.png`
- Permission guard: `Quartz.CGPreflightScreenCaptureAccess()`

**osascript — AppleScript runner (`computer.py`):**
- Invocation: `subprocess.run(["osascript", "-e", script])`
- Safety guard: `_guarded_applescript()` in `computer_use_server.py` blocks destructive patterns (delete, send mail, rm, sudo, power commands) with regex on lowercased script unless `confirm=True` is passed by the brain

**open — app launcher (`computer.py`):**
- Invocation: `subprocess.run(["open", "-a", name])`
- 0.6 s sleep after open to let the app come to front

**Quartz CGEvents — mouse and keyboard (`computer.py`):**
- Framework: `pyobjc-framework-Quartz`
- Mouse: `CGEventCreateMouseEvent` + `CGEventPost(kCGHIDEventTap, ...)` for click/move/scroll
- Keyboard: `CGEventCreateKeyboardEvent` for named keys/combos; `CGEventKeyboardSetUnicodeString` for arbitrary Unicode text input
- Coordinates: logical points (not retina pixels); `(0,0)` is top-left of main display

**Accessibility API — UI element tree (`computer.py`):**
- Framework: `pyobjc-framework-ApplicationServices`
- Entry point: `AXUIElementCreateApplication(pid)` → walk with `AXUIElementCopyAttributeValue`
- Attributes queried: `kAXRoleAttribute`, `kAXTitleAttribute`, `kAXDescriptionAttribute`, `kAXPositionAttribute`, `kAXSizeAttribute`, `kAXChildrenAttribute`
- Clickable roles: `AXButton`, `AXTextField`, `AXLink`, `AXCheckBox`, `AXMenuItem`, and 9 others
- Permission guard: `AS.AXIsProcessTrusted()`

**NSWorkspace — frontmost app (`computer.py`):**
- Framework: `pyobjc-framework-Cocoa`
- API: `NSWorkspace.sharedWorkspace().frontmostApplication()` → returns `localizedName()` + `processIdentifier()`

## Local HTTP Server (web UI)

**server.py — `ThreadingHTTPServer` on `127.0.0.1:8765`:**
- Stdlib only (`http.server`, `json`, `threading`, `pathlib`)
- Binds to loopback only — never exposed to LAN
- Static file serving: `web/` directory (`index.html`, `app.js`, `style.css`)
- API endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Returns `{ok, accessibility, screen_recording}` |
| POST | `/api/ask` | `{text, control, lang}` → `{reply, source}` (source: `max`/`ollama`/`offline`/`error`) |
| POST | `/api/reset` | Clears `Brain.session_id` to start a fresh conversation |

- Computer-use toggle: `control` field in `/api/ask` payload enables MCP tools for that turn (only if `mcp_config.json` exists)
- Fallback chain in `_ask()`: Max brain → Ollama (if available) → static error message

## Browser Web Speech API (web UI only — `web/app.js`)

**Speech Recognition (STT):**
- API: `window.SpeechRecognition || window.webkitSpeechRecognition`
- Chrome-only; degrades gracefully to text input if unavailable
- Language: `pt-BR` or `en-US` based on user's language toggle (stored in `localStorage`)
- Mode: `continuous=false`, `interimResults=true` — restarts automatically in hands-free mode

**Speech Synthesis (TTS):**
- API: `window.speechSynthesis` + `SpeechSynthesisUtterance`
- Voice selection: prefers Google neural voices; falls back to any matching language voice
- Language auto-detected from reply text (Portuguese diacritics / keyword heuristic in `isPortuguese()`)
- Barge-in: `speechSynthesis.cancel()` on orb tap while speaking

**Persistence:**
- `localStorage` keys: `jv_lang` (`"en"`/`"pt"`), `jv_control` (`"0"`/`"1"`)

## Raycast Integration

**raycast/ shell scripts (optional):**
- `raycast/jarvis-ui.sh` — starts `server.py` in background and opens Chrome to `http://127.0.0.1:8765`
- `raycast/ask-jarvis.sh` — sends a typed query directly to `/api/ask`
- `raycast/talk-jarvis.sh` — launches voice mode
- `raycast/stop-jarvis.sh` — kills the server process

## Data Storage (local filesystem only)

**No external databases or cloud storage.**

| Path | Purpose | Written by |
|---|---|---|
| `memory/about_you.md` | Long-term user memory; injected into system prompt every session | `computer_use_server.py` `_remember()` tool + `memory_consolidate.py` |
| `logs/conversation-YYYY-MM-DD.log` | Per-day conversation transcript | `jarvis.py` `_log()` |
| `/tmp/jarvis_screen.png` | Last screenshot (overwritten each turn) | `computer.py` `screenshot()` |

## Authentication & Secrets

- No API keys, no `.env` file required
- Claude Max plan: authentication managed entirely by the `claude` CLI's own login session
- All other integrations (Ollama, macOS APIs, system commands) require no credentials

---

*Integration audit: 2026-06-05*
