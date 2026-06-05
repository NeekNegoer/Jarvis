# Codebase Structure

**Analysis Date:** 2026-06-05

## Directory Layout

```
Jarvis/                         # Project root — all .py modules live here (flat)
├── jarvis.py                   # Primary entry point — PTT / hands-free / text / wake dispatch
├── brain.py                    # Cloud brain: shells out to `claude` CLI (Max plan)
├── local_brain.py              # Offline brain: Ollama HTTP fallback
├── ears.py                     # STT: mlx-whisper (Metal) or faster-whisper (CPU)
├── mouth.py                    # TTS: macOS `say` command, bilingual voices
├── computer.py                 # macOS primitives: screenshot, click, type, AppleScript
├── computer_use_server.py      # MCP stdio server wrapping computer.py for the claude CLI
├── server.py                   # Web UI backend: HTTP server on 127.0.0.1:8765
├── hotkey.py                   # Global push-to-talk via pynput (Right Option key)
├── wake.py                     # Wake-word detection ("Jarvis...") using fuzzy matching
├── memory_consolidate.py       # Session-end memory extraction → memory/about_you.md
├── doctor.py                   # Checks macOS permissions (mic, screen recording, accessibility)
├── selftest.py                 # End-to-end smoke tests (no mic needed)
├── test_computer_use.py        # Tests for computer.py / MCP server
├── test_memory_consolidate.py  # Unit tests for consolidation helpers
├── test_wake.py                # Unit tests for wake-word matching logic
├── mcp_config.json             # MCP server declaration for claude CLI
├── persona.md                  # Editable personality prompt (loaded by brain.py)
├── recipes.md                  # Prompt recipes / example commands for Jarvis
├── requirements.txt            # Python dependencies
├── install.sh                  # One-shot setup script
├── Jarvis.command              # macOS double-click launcher (opens terminal, runs jarvis.py)
├── doctor.py                   # Permission checker / diagnostic tool
├── PLAN.md                     # Project planning notes
├── CHECKPOINTS.md              # Build milestone log
├── README.md                   # User-facing documentation
├── TODO_TOMORROW.md            # Active task list
├── RESEARCH.md                 # Architecture decision notes
│
├── web/                        # Browser UI assets (served by server.py)
│   ├── index.html              # Single-page chat UI
│   ├── style.css               # Styles
│   ├── app.js                  # Web Speech API (STT + TTS), /api/ask calls
│   └── README.md               # Web UI notes
│
├── raycast/                    # Raycast script commands
│   ├── ask-jarvis.sh           # Quick text query from Raycast
│   ├── jarvis-ui.sh            # Start server.py + open Chrome to the UI
│   ├── stop-jarvis.sh          # Kill the server
│   └── talk-jarvis.sh          # Launch terminal voice mode from Raycast
│
├── memory/                     # Persistent memory across sessions
│   └── about_you.md            # Durable facts about Pietro (appended, never overwritten)
│
├── logs/                       # Runtime logs (gitignored)
│   ├── conversation-YYYY-MM-DD.log   # Per-day turn log (role / lang / text)
│   ├── jarvis-ui.log           # Web server stdout from Raycast launcher
│   ├── jarvis-voice.log        # Voice mode stdout from Raycast launcher
│   └── *.pid                   # PID files for server process management
│
├── .planning/                  # GSD planning artifacts
│   └── codebase/               # Codebase analysis documents (this directory)
│
├── .venv/                      # Python virtual environment (gitignored)
├── .env.example                # Example env vars (document only — actual .env not committed)
├── .gitignore                  # Excludes .venv, logs, .env, __pycache__
└── .git/                       # Git repository
```

---

## Directory Purposes

**Root `.py` modules (flat layout):**
- Purpose: All application Python lives directly in the project root — no `src/` subdirectory
- Naming: snake_case, descriptive single-word or compound names matching their role
- Key modules: `jarvis.py` (orchestration), `brain.py` (cloud AI), `ears.py` (STT), `mouth.py` (TTS), `computer.py` (macOS actions)

**`web/`:**
- Purpose: Static assets for the browser chat UI served by `server.py`
- Contains: `index.html`, `style.css`, `app.js`
- Speech: Browser handles both recognition (Web Speech API) and TTS — the backend only returns text
- No build step — plain HTML/CSS/JS, served as static files

**`raycast/`:**
- Purpose: Raycast script commands for hands-free macOS launcher integration
- Contains: Shell scripts that manage the server process, open Chrome, or invoke voice mode
- PID management: `stop-jarvis.sh` reads PID from `logs/jarvis-ui.pid`

**`memory/`:**
- Purpose: Durable long-term memory for Jarvis across sessions
- Contains: `about_you.md` — an append-only markdown list of facts
- Format: `- <fact>  _(learned YYYY-MM-DD)_` (consistent with `remember` MCP tool)
- Read at: every `Brain` instantiation via `brain.py:_load_memory()`
- Written by: `memory_consolidate.py` (session end) and `mcp__computer__remember` tool (mid-session)

**`logs/`:**
- Purpose: Runtime conversation logs and process management artifacts
- Gitignored: never committed
- Rotation: new log file per calendar day (`conversation-YYYY-MM-DD.log`)

**`.planning/codebase/`:**
- Purpose: GSD codebase analysis documents consumed by `/gsd-plan-phase` and `/gsd-execute-phase`
- Contains: ARCHITECTURE.md, STRUCTURE.md (and others generated by mapping runs)

---

## Key File Locations

**Entry Points:**
- `jarvis.py`: Primary CLI — PTT, hands-free, text mode, wake-word dispatch
- `server.py`: Web UI server (`python server.py`)
- `hotkey.py`: Global hotkey PTT (`python hotkey.py`)
- `wake.py`: Wake-word loop (called by `jarvis.py --wake`)
- `Jarvis.command`: macOS Finder double-click launcher

**Configuration:**
- `mcp_config.json`: MCP server declaration — points `claude` CLI to `computer_use_server.py`
- `persona.md`: Editable AI personality (falls back to `DEFAULT_PERSONA` in `brain.py`)
- `.env.example`: Documents supported environment variables (never read by code directly — users copy to `.env`)
- `requirements.txt`: Pinned Python dependencies

**Core Logic:**
- `brain.py`: `Brain.think()` — the single interface all callers use to invoke Claude
- `ears.py`: `listen()` / `listen_continuous()` — the single interface for audio capture
- `mouth.py`: `speak()` — the single interface for TTS
- `computer.py`: macOS automation primitives (used exclusively via MCP server in production)
- `computer_use_server.py`: MCP stdio server — the boundary between Claude and the OS

**Memory:**
- `memory/about_you.md`: Append-only durable facts file
- `memory_consolidate.py`: Session-end extraction logic

**Testing:**
- `selftest.py`: End-to-end smoke test (no mic required)
- `test_computer_use.py`: Computer automation tests
- `test_memory_consolidate.py`: Memory consolidation unit tests
- `test_wake.py`: Wake-word matching unit tests
- `doctor.py`: Permission / dependency diagnostic (not a test runner, but diagnostic)

---

## Naming Conventions

**Files:**
- snake_case, role-descriptive: `brain.py`, `local_brain.py`, `computer_use_server.py`
- Test files prefixed with `test_`: `test_wake.py`, `test_memory_consolidate.py`
- Shell scripts in `raycast/` are kebab-case: `ask-jarvis.sh`, `stop-jarvis.sh`

**Classes:**
- PascalCase: `Brain`, `LocalBrain`, `BrainOffline`, `PushToTalk`
- Named for their role, not their implementation: `Brain` not `ClaudeCLIWrapper`

**Functions:**
- snake_case, verb-first for actions: `listen()`, `speak()`, `transcribe_file()`
- Leading underscore for module-private helpers: `_log()`, `_clean()`, `_init_backend()`
- Boolean accessors named as predicates: `has_accessibility()`, `is_speaking()`, `available()`

**Constants:**
- SCREAMING_SNAKE_CASE: `SAMPLE_RATE`, `COMPUTER_TOOLS`, `GOODBYE_WORDS`, `MCP_CONFIG`

**Environment variables:**
- All prefixed with `JARVIS_`: `JARVIS_STT`, `JARVIS_WHISPER_MODEL`, `JARVIS_VOICE_EN`, `JARVIS_VOICE_PT`, `JARVIS_VOICE_RATE`, `JARVIS_SILENT`, `JARVIS_HOTKEY`, `JARVIS_WAKE_WORD`, `JARVIS_OLLAMA_MODEL`
- Non-prefixed for standard infra: `OLLAMA_HOST`

---

## Where to Add New Code

**New voice capability (new STT backend, new language):**
- Primary code: `ears.py` — add backend branch in `_init_backend()` and `_transcribe_locked()`
- Language tokens: add to `_PT_WORDS` / `_EN_WORDS` sets in `jarvis.py`

**New computer-use tool:**
- Primitive: `computer.py` — add the macOS automation function
- MCP exposure: `computer_use_server.py` — add entry to `TOOLS` dict
- Whitelist: `brain.py` `COMPUTER_TOOLS` list — add `"mcp__computer__<name>"`

**New Brain capability or prompt change:**
- System prompt: `persona.md` (runtime edit) or `brain.py:DEFAULT_PERSONA` (code change)
- Memory instructions: `brain.py:_system_prompt()`

**New entry point / interaction mode:**
- New `.py` file in project root
- Import from `ears`, `brain`, `mouth` as needed
- Follow the `Brain` + `BrainOffline` fallback pattern from `jarvis.py`

**New web UI feature:**
- Frontend: `web/app.js`, `web/index.html`, `web/style.css`
- New API endpoint: `server.py` `Handler.do_POST()` or `do_GET()`

**New Raycast command:**
- Shell script: `raycast/` directory, kebab-case name, `.sh` extension

**New persistent memory field:**
- `memory/about_you.md` is free-form markdown — no schema change needed
- Extraction logic: `memory_consolidate.py:EXTRACTION_PROMPT` if new categories needed

**Tests for new module:**
- New file: `test_<module_name>.py` in project root
- Follow patterns in `test_wake.py` (pure unit) or `test_memory_consolidate.py` (helpers + consolidate)

---

## Special Directories

**`.venv/`:**
- Purpose: Python 3.9 virtual environment
- Generated: Yes (by `install.sh` or `python -m venv .venv`)
- Committed: No (gitignored)

**`logs/`:**
- Purpose: Runtime conversation and process logs
- Generated: Yes (at runtime by `jarvis.py` and Raycast scripts)
- Committed: No (gitignored)

**`.planning/`:**
- Purpose: GSD planning artifacts
- Generated: By GSD plugin commands
- Committed: Yes (planning docs are version-controlled)

**`memory/`:**
- Purpose: Durable AI memory (about_you.md)
- Generated: Yes (appended at session end)
- Committed: User's choice — contains personal facts about Pietro

---

*Structure analysis: 2026-06-05*
