# Technology Stack

**Analysis Date:** 2026-06-05

## Languages

**Primary:**
- Python 3.9.6 — all backend logic (`jarvis.py`, `brain.py`, `ears.py`, `mouth.py`, `computer.py`, `computer_use_server.py`, `local_brain.py`, `wake.py`, `server.py`, `memory_consolidate.py`, `hotkey.py`, `doctor.py`)

**Secondary:**
- JavaScript (ES2015+, no build step) — browser-side web UI (`web/app.js`)
- Bash — setup and Raycast launcher scripts (`install.sh`, `raycast/*.sh`)
- HTML/CSS — web UI markup (`web/index.html`, `web/style.css`)

## Runtime

**Environment:**
- Python 3.9.6, constrained by the project venv at `.venv/` (`pyvenv.cfg` pins `version = 3.9.6`)
- Python 3.9 compatibility is intentional: the official `mcp` SDK requires 3.10+, so `computer_use_server.py` uses a hand-written JSON-RPC 2.0 implementation over stdio instead
- macOS only — hard dependency on Apple-specific APIs and binaries (`say`, `screencapture`, `osascript`, Quartz, ApplicationServices, AppKit)

**Browser (web UI path):**
- Chrome required — `web/app.js` uses `window.webkitSpeechRecognition` (Chrome-only) for STT and `window.speechSynthesis` for TTS

**Package Manager:**
- pip (stdlib venv via `python3 -m venv .venv`)
- Lockfile: absent — `requirements.txt` uses `>=` bounds only (no pinned versions, no Poetry/PDM)

## Frameworks

**Core:**
- No web framework — `server.py` uses Python stdlib `http.server.ThreadingHTTPServer` directly

**Testing:**
- No test framework declared in `requirements.txt`; tests are standalone scripts:
  - `selftest.py`, `test_wake.py`, `test_computer_use.py`, `test_memory_consolidate.py`
  - `wake.py --selftest` runs its own inline test suite (pure `print`/assert logic)

**Build/Dev:**
- No build tools; source runs directly from the project root
- `install.sh` bootstraps the venv and optionally installs Ollama

## Key Dependencies

**Speech-to-Text (ears.py):**
- `mlx-whisper>=0.4.0` — Metal-accelerated Whisper for Apple Silicon; preferred backend; model repo pattern: `mlx-community/whisper-{size}-mlx`
- `faster-whisper>=1.0.0` — CPU fallback; uses `WhisperModel(device="cpu", compute_type="int8")`
- `sounddevice>=0.4.6` — microphone capture (16 kHz, mono, float32)
- `numpy>=1.24.0` — audio buffer manipulation
- `scipy>=1.10.0` — `.wav` read/write (used by faster-whisper path via temp file)

**Computer Use (computer.py):**
- `pyobjc-framework-Quartz>=10.0` — screenshots (CGDisplayMode), mouse events (CGEvents), keyboard events
- `pyobjc-framework-ApplicationServices>=10.0` — macOS Accessibility API (AXUIElement tree walking)
- `pyobjc-framework-Cocoa>=10.0` — `NSWorkspace.sharedWorkspace().frontmostApplication()`
- `pillow>=10.0` — downscale retina screenshots to logical-point resolution (`Image.LANCZOS`)

**Global Hotkey (hotkey.py):**
- `pynput>=1.7` — optional; listens for a global push-to-talk hotkey from any app

**Brain (brain.py):**
- `claude` CLI (Claude Code) — NOT a pip package; installed separately, authenticated against the user's Max plan subscription. Invoked via `subprocess.run()`. Located at `~/.local/bin/claude` or on `$PATH`.

**TTS:**
- macOS built-in `say` command — no pip package; invoked via `subprocess`

## Configuration

**Environment Variables (all optional — no `.env` file required, no API keys):**

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

**Configuration Files:**
- `mcp_config.json` — registers `computer_use_server.py` as an MCP stdio server for the `claude` CLI; presence of this file enables computer use in `brain.py`
- `persona.md` — editable system prompt; overrides the default `DEFAULT_PERSONA` in `brain.py` if present
- `memory/about_you.md` — long-term memory file appended by the `remember` MCP tool; read into the system prompt every session

**Build:**
- No build step; `install.sh` only creates the venv and installs `requirements.txt`

## Platform Requirements

**Development & Production (same machine):**
- macOS (tested on macOS 26 / Apple Silicon M1+)
- Python 3.9.6 (via Xcode Command Line Tools or pyenv)
- Claude Code CLI installed and authenticated with Max plan
- macOS permissions required: Screen Recording + Accessibility (for computer use)
- Microphone permission (for voice modes)

---

*Stack analysis: 2026-06-05*
