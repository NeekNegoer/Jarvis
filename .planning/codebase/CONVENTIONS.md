# Coding Conventions

**Analysis Date:** 2026-06-05

## Naming Patterns

**Files:**
- `snake_case.py`, one concept per file named after its sensory/cognitive role: `brain.py`, `mouth.py`, `ears.py`, `wake.py`, `computer.py`, `memory_consolidate.py`
- Test files: `test_<module>.py` or `selftest.py`

**Functions:**
- Public API: `snake_case` — `speak`, `listen`, `stop`, `match_wake_word`, `consolidate`, `parse_facts`, `dedupe`, `is_duplicate`
- Private helpers: leading underscore — `_clean`, `_log`, `_guess_language`, `_build_prompt`, `_load_persona`, `_normalize`, `_memory_lines`, `_iter_turns`, `_format_transcript`
- `if __name__ == "__main__":` blocks in every module serve as quick standalone demos or manual tests

**Variables:**
- Module-level constants: `UPPER_SNAKE_CASE` — `SAMPLE_RATE`, `MODEL_NAME`, `CHAT_TIMEOUT`, `MEMORY_FILE`, `VOICES`, `RATE`, `SILENT`, `GOODBYE_WORDS`, `MAX_FACTS`, `MAX_FACT_LEN`
- Local variables and parameters: `snake_case`

**Types/Classes:**
- `PascalCase` — `Brain`, `BrainOffline`, `LocalBrain`
- Custom exceptions inherit from `Exception` and carry a descriptive message: `class BrainOffline(Exception): """Raised when the Max-plan brain can't be reached..."""`

## Type Hints

**Pattern:** Full type hints on all public and private function signatures. Python 3.9 compatibility is achieved with:
```python
from __future__ import annotations  # always line 1 after the module docstring
```
This enables `str | None`, `list[str]`, `tuple[str, str]`, `bool | None` union syntax that would otherwise require Python 3.10+.

**Examples from source:**
```python
# brain.py
def __init__(self, enable_computer_use: bool | None = None, model: str | None = None):
def think(self, user_text: str) -> str:

# wake.py
def match_wake_word(text: str, wake_word: str | None = None, threshold: float | None = None, max_scan: int = 3) -> tuple[bool, str]:
def _normalize(text: str) -> str:
def _tokenize(text: str) -> list[tuple[str, str]]:

# memory_consolidate.py
def parse_facts(raw, *, max_facts: int = MAX_FACTS, max_len: int = MAX_FACT_LEN) -> list:
def is_duplicate(candidate: str, existing: list, *, overlap: float = 0.5) -> bool:
def consolidate(brain_or_transcript=None, *, think=None, memory_file=None, ...) -> list:
```

## Module Structure

Every `.py` file follows this layout:
1. Module docstring (`"""filename.py — one-line purpose. Run command.` + multi-paragraph body)
2. `from __future__ import annotations`
3. Standard library imports (alphabetical)
4. Third-party imports (blank line separator)
5. Local imports (blank line separator) — or lazy imports inside functions to break circular deps
6. Module-level constants (env-var config, file paths)
7. Private helpers
8. Public API / classes
9. `if __name__ == "__main__":` block

**Example docstring format:**
```python
"""
brain.py — Jarvis's brain, powered by your Claude Max plan (no API key).

Multi-paragraph explanation of design decisions, alternatives considered,
and usage notes...
"""
```

## Env-var Configuration Convention

All configuration is via environment variables prefixed with `JARVIS_`. They are resolved at module import time and assigned to named module-level constants.

**Pattern:**
```python
# String
MODEL_NAME = os.getenv("JARVIS_WHISPER_MODEL", "small")

# Integer
RATE = int(os.getenv("JARVIS_VOICE_RATE", "178"))

# Boolean — accept "1", "true", "yes"
SILENT = os.getenv("JARVIS_SILENT", "").strip() in ("1", "true", "yes")

# Float with try/except fallback
def _env_threshold() -> float:
    try:
        return float(os.getenv("JARVIS_WAKE_THRESHOLD", DEFAULT_THRESHOLD))
    except ValueError:
        return DEFAULT_THRESHOLD
```

**Env vars in the project:**
- `JARVIS_VOICE_PT` / `JARVIS_VOICE_EN` — TTS voice name (`mouth.py`)
- `JARVIS_VOICE_RATE` — words per minute (`mouth.py`)
- `JARVIS_SILENT` — suppress audio output (`mouth.py`)
- `JARVIS_WHISPER_MODEL` — Whisper model size (`ears.py`)
- `JARVIS_STT` — force backend "mlx" or "faster" (`ears.py`)
- `JARVIS_WAKE_WORD` — custom wake word (`wake.py`)
- `JARVIS_WAKE_THRESHOLD` — fuzzy match ratio 0..1 (`wake.py`)
- `JARVIS_WAKE_FOLLOWUP_SECS` — post-reply listening window (`wake.py`)

All env vars are documented in their module's docstring "Configuration" section.

## Persona/Recipes Markdown-as-Config Pattern

Markdown files serve as editable runtime configuration loaded fresh each session — no code changes required to alter behavior.

**`persona.md`** (`/Users/pietrojustino/Documents/Jarvis/persona.md`):
- Loaded by `brain.py`'s `_load_persona()` on every `Brain.__init__()` call
- If missing or empty, `brain.py` falls back to its hardcoded `DEFAULT_PERSONA` constant
- The file ends with `# Edit this file freely to change how Jarvis behaves — it's loaded fresh every session.`

**`recipes.md`** (`/Users/pietrojustino/Documents/Jarvis/recipes.md`):
- Not loaded by Python code; instead `persona.md` instructs the LLM to reference it
- Contains AppleScript snippets the brain runs via `run_applescript` tool
- New app support added by editing only this markdown file

**`memory/about_you.md`** (`/Users/pietrojustino/Documents/Jarvis/memory/about_you.md`):
- Runtime-written; appended by `memory_consolidate.py`'s `_append_facts()`
- Format: `- <fact>  _(learned YYYY-MM-DD)_` (markdown bullets with date stamps)
- Parsed by `_memory_lines()` which keeps only bullet lines (`-`, `*`, `•`) and skips headers/notes
- Injected into the system prompt by `brain.py`'s `_system_prompt()`

## Error Handling

**"Never crash on shutdown" pattern** — functions called at session end use bare `except Exception` to guarantee silent failure:
```python
# memory_consolidate.py — consolidate() wraps everything
def consolidate(...) -> list:
    try:
        ...
        return new_facts
    except Exception:
        # Memory consolidation must never break shutdown.
        return []

# jarvis.py — _log() is best-effort
def _log(role, lang, text):
    try:
        ...
    except Exception:
        pass
```

**Spoken-style fallback strings** — error messages are written for TTS output, not for developers:
```python
# brain.py
except subprocess.TimeoutExpired:
    return "Sorry, that took too long. Could you try again?"

return (data.get("result") or "").strip() or "Okay."
return proc.stdout.strip() or "I didn't get a reply."

# jarvis.py
reply = ("I can't reach my main brain and have no offline brain set up yet."
         if lang == "en" else
         "Não consigo acessar meu cérebro principal e ainda não tenho um offline.")
```

**Custom exception for network failure** — `BrainOffline` triggers a local-brain fallback in callers:
```python
# brain.py
class BrainOffline(Exception):
    """Raised when the Max-plan brain can't be reached (e.g. no network)."""

# jarvis.py / wake.py — caller pattern
try:
    reply = brain.think(you_said)
except BrainOffline:
    local = local or _maybe_local_brain()
    reply = local.think(...) if local else MISSED[lang]
```

**Specific exception types** for expected failures, bare `except Exception` only for shutdown-safe operations:
```python
except subprocess.TimeoutExpired:   # specific
except FileNotFoundError:           # specific
except (json.JSONDecodeError, ValueError):  # specific
except Exception:                   # only where silent failure is correct
```

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first)
2. Standard library (alphabetical): `import json`, `import os`, `import re`, `import subprocess`, `from pathlib import Path`
3. Third-party (blank line): `import numpy as np`, `import sounddevice as sd`
4. Local (blank line): `from brain import Brain, BrainOffline`, `from mouth import speak`

**Lazy imports to break circular dependencies:**
```python
# wake.py — jarvis imports wake, so wake imports jarvis lazily
def run_wake_loop(brain=None) -> None:
    import jarvis  # lazy: avoids wake<->jarvis import cycle at module load
    from ears import listen_continuous, _calibrate_noise
    from brain import Brain, BrainOffline
    from mouth import speak, is_speaking
```

**Inline imports for optional/heavy dependencies:**
```python
# ears.py — scipy only needed in the faster-whisper path
import tempfile
from scipy.io.wavfile import write as write_wav
```

## Comments

**Section dividers** in longer modules:
```python
# ----------------------------------------------------------------------------------
#  PURE WAKE-WORD MATCHING  (no audio, no I/O — fully unit-testable)
# ----------------------------------------------------------------------------------
```

**Inline comments for non-obvious constants:**
```python
SAMPLE_RATE = 16000  # Whisper expects 16kHz mono audio
CHAT_TIMEOUT = 90    # seconds, no tools
```

**Extended why-not comments** for design decisions:
```python
# WHY NOT openWakeWord?
# openWakeWord is excellent... We default to the Whisper-reuse approach above because...
```

**Docstrings** on all public functions, with parameter semantics and return value format:
```python
def match_wake_word(text, wake_word=None, threshold=None, max_scan=3) -> tuple[bool, str]:
    """Detect the wake word near the start of `text`, tolerating Whisper mishearings.

    Pure function — no audio, no globals beyond env defaults. Easy to unit-test.

    Returns (matched, command):
      • matched  — True if the wake word was found...
      • command  — everything AFTER the wake word...
    """
```

## Path Handling

Use `pathlib.Path` throughout. Module-relative paths via `HERE`:
```python
HERE = Path(__file__).parent
MEMORY_FILE = HERE / "memory" / "about_you.md"
MCP_CONFIG  = HERE / "mcp_config.json"
LOG_DIR     = HERE / "logs"
```

## Linting and Formatting

No linter config detected (no `.flake8`, `pyproject.toml`, `mypy.ini`, `.pylintrc`, `.ruff.toml`). Code follows PEP 8 conventions manually (4-space indentation, 100-ish line length). No formatter config (no `black`, `isort`, `ruff` config files).

---

*Convention analysis: 2026-06-05*
