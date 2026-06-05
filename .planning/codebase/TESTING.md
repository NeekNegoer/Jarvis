# Testing Patterns

**Analysis Date:** 2026-06-05

## Test Infrastructure

**Runner:** No pytest config exists. No `pytest.ini`, `pyproject.toml`, `setup.cfg`, `tox.ini`, or `conftest.py` was found. Pytest is usable (`python -m pytest`) but is not configured.

**CI/CD:** None. No GitHub Actions, no CI config of any kind.

**Coverage requirements:** None configured.

**Assertion style:** Plain `assert` with inline messages — no assertion library.

## Run Commands

```bash
# Smoke test (12 checks, no permissions needed) — primary test for install verification
python selftest.py

# Wake-word unit tests (pure, no microphone) — two modes:
python -m pytest test_wake.py -q
python test_wake.py                        # also works as a script

# Memory consolidation unit tests (pure, no network) — two modes:
python -m pytest test_memory_consolidate.py -q
python test_memory_consolidate.py          # also works as a script

# Manual Mac-control integration test (REQUIRES Accessibility + Screen Recording)
python test_computer_use.py

# Pre-flight check (not tests — verifies the install and permissions)
python doctor.py
```

## Test Files

### `selftest.py` — Smoke Test (12 checks)

**Location:** `/Users/pietrojustino/Documents/Jarvis/selftest.py`

**Run as:** `python selftest.py` (standalone script only — NOT pytest-compatible)

**Design:** A custom `check(name, fn)` harness with global `passed`/`failed` counters. Each check is a `t_*` function that raises on failure. Covers everything that runs without the microphone or macOS permissions.

**Checks:**
| Name | What it tests |
|---|---|
| `t_mouth_clean` | `mouth._clean()` strips markdown/URLs from text |
| `t_computer_basics` | `computer.screen_info()`, `computer.frontmost_app()`, `computer.key()` |
| `t_applescript` | `computer.run_applescript('return 6 * 7')` returns `"42"` |
| `t_mcp_tools` | `computer_use_server._tools_list()` has required tools; JSON-RPC `initialize` handshake |
| `t_ears_backend` | `ears._backend` is `"mlx"` or `"faster"` |
| `t_brain_construct` | `Brain(enable_computer_use=False)` finds claude CLI and loads persona |
| `t_local_brain` | `LocalBrain()` constructs and `.available()` doesn't raise |
| `t_text_lang_guess` | `jarvis._guess_language()` correctly returns `"pt"` / `"en"` |
| `t_destructive_guardrail` | `computer_use_server._guarded_applescript()` blocks `rm -rf`, `send`, `empty trash` |
| `t_wake_word_matcher` | `wake.match_wake_word()` basic match, fuzzy miss-hearing, non-match |
| `t_memory_consolidate_pieces` | `mc.parse_facts()`, `mc.dedupe()`, secret filtering, end-to-end with fake thinker |
| `t_silent_mode` | `JARVIS_SILENT=1` + `importlib.reload(mouth)` → `mouth.SILENT is True`, no audio |

### `test_wake.py` — Wake-word Unit Tests

**Location:** `/Users/pietrojustino/Documents/Jarvis/test_wake.py`

**Run as:** `python -m pytest test_wake.py -q` or `python test_wake.py`

**Functions:** `test_matcher`, `test_custom_wake_word`, `test_threshold_is_tunable`

**Pattern:** Table-driven. A module-level `CASES` list of `(text, want_match, want_cmd)` tuples drives `test_matcher`. All inputs are pure strings — no audio, no network, no I/O.

```python
CASES = [
    ("Hey Jarvis, play some music",    True,  "play some music"),
    ("Jarvez, lock the screen",        True,  "lock the screen"),  # fuzzy mishearing
    ("Service, set a timer",           True,  "set a timer"),      # alias
    ("what time is it",                False, ""),
    ("I love marvelous java drivers",  False, ""),  # near-miss must NOT fire
]

def test_matcher():
    for text, want_match, want_cmd in CASES:
        got_match, got_cmd = match_wake_word(text)
        assert got_match == want_match, f"match mismatch for {text!r}: {got_match}"
        if want_match:
            assert got_cmd.lower() == want_cmd.lower(), ...
```

**Script mode runner** (when run as `python test_wake.py`):
```python
if __name__ == "__main__":
    test_matcher()
    test_custom_wake_word()
    test_threshold_is_tunable()
    print(f"All {len(CASES)} matcher cases + custom-word + threshold tests passed.")
```

### `test_memory_consolidate.py` — Memory Consolidation Unit Tests

**Location:** `/Users/pietrojustino/Documents/Jarvis/test_memory_consolidate.py`

**Run as:** `python -m pytest test_memory_consolidate.py -q` or `python test_memory_consolidate.py`

**Scope:** ~20 test functions organized in sections: `parse`, `dedupe`, `transcript shapes`, `end-to-end with fake brain`

**Key patterns:**

**Fake thinker (dependency injection for no-network tests):**
```python
# Lambda replaces the real Brain; consolidate() accepts it via `think=` parameter
fake = lambda prompt: '["Plays tennis on weekends", "Studies law"]'
saved = mc.consolidate(turns, think=fake, memory_file="/tmp/jarvis_mem_test.md", today="2026-06-05")
```

**pytest `tmp_path` fixture for file I/O:**
```python
def test_consolidate_end_to_end(tmp_path):
    mem = tmp_path / "about_you.md"
    mem.write_text(EXISTING, encoding="utf-8")
    ...
    contents = mem.read_text(encoding="utf-8")
    assert "- Has a dog named Rex.  _(learned 2026-06-05)_" in contents
```

**Script mode self-runner** — handles `tmp_path` manually when run without pytest:
```python
if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        if "tmp_path" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
            with tempfile.TemporaryDirectory() as d:
                fn(Path(d))
        else:
            fn()
```

**Error-resilience test:**
```python
def test_consolidate_never_raises(tmp_path):
    def boom(prompt):
        raise RuntimeError("brain exploded")
    assert mc.consolidate(turns, think=boom, memory_file=mem) == []
```

### `test_computer_use.py` — Manual Mac-control Integration Test

**Location:** `/Users/pietrojustino/Documents/Jarvis/test_computer_use.py`

**Run as:** `python test_computer_use.py` (script only — NOT pytest-compatible, NOT in CI)

**Requires:** Accessibility permission + Screen Recording permission. Exits early with a message if missing (`python doctor.py` first).

**Design:** Opens a real TextEdit scratch document, types a sentence, reads it back via AppleScript, exercises key combos, takes a screenshot, checks UI elements, then closes without saving. Self-cleaning — never touches real files.

**Output format:** `✅` / `❌` per capability printed to stdout. Returns exit code 0 on full pass.

## What IS and IS NOT Tested

### Tested (automated)
- All pure logic functions: `match_wake_word`, `parse_facts`, `dedupe`, `is_duplicate`, `_clean`, `_guess_language`, `_is_goodbye`, `_worth_consolidating`, `_format_transcript`, `_iter_turns`, `_memory_lines`
- Module import and construction: `Brain(enable_computer_use=False)`, `LocalBrain()`
- MCP server tool registration and JSON-RPC handshake
- AppleScript bridge with safe scripts (`return 6 * 7`)
- Destructive-action guardrail (`_guarded_applescript`)
- Env-var config via `importlib.reload` pattern
- JSON parsing robustness (fenced, buried, `{"facts": [...]}`, list-of-objects, garbage)
- Secret/PII filtering in `parse_facts`
- Memory deduplication (exact, substring, keyword overlap)
- End-to-end `consolidate()` with fake thinker and real file I/O

### NOT Tested (automated)
- Audio recording or live transcription (requires microphone)
- Real LLM brain calls (requires live `claude` CLI + network + Max plan login)
- End-to-end voice conversation loop
- Mac GUI control (only in manual `test_computer_use.py`)
- `listen()` / `listen_continuous()` / `transcribe_file()` paths
- `run_wake_loop()` (the audio loop itself)
- `mouth.speak()` audio output (tested only for no-exception in silent mode)
- TTS voice selection
- Memory file append (only partially covered in `selftest.py` via `/tmp/`)

## Mocking Strategy

**No mock library used.** The project avoids mocking by designing pure functions that accept their dependencies as arguments:

```python
# consolidate() accepts `think=` so tests pass a lambda instead of a Brain
def consolidate(brain_or_transcript=None, *, think=None, ...) -> list:
    thinker = think or _default_thinker()
```

```python
# selftest.py tests env-var behavior with importlib.reload instead of mocking os.environ
import os
os.environ["JARVIS_SILENT"] = "1"
importlib.reload(mouth)
assert mouth.SILENT is True
del os.environ["JARVIS_SILENT"]
importlib.reload(mouth)
```

## Test Data / Fixtures

**No fixtures directory.** Test data is inline in each test file.

**Module-level constants** for shared data in `test_memory_consolidate.py`:
```python
EXISTING = """# What Jarvis knows about you
- Name: Pietro
- Location: Brazil
- Goal: building my own AI assistant ("Jarvis") and growing it over time
- Prefers temperatures in Celsius.  _(learned 2026-06-01)_
"""
```

**Temp files** handled via pytest `tmp_path` fixture or `tempfile.TemporaryDirectory` (script mode).

## Coverage Gaps (Priority)

**High:**
- `ears.py` listen/transcription paths — no automated tests at all
- `local_brain.py` actual `.think()` call — only `.available()` is tested
- `brain.py` `.think()` output parsing (JSON path, error path) — tested indirectly through selftest construction only

**Medium:**
- `mouth.speak()` with real audio
- `jarvis.py` `run_text_mode()` and `main()` loops
- `wake.py` `run_wake_loop()` — only the pure `match_wake_word` is tested
- `computer.py` `type_text()`, `click()`, `screenshot()` — only in manual test

**Low:**
- `hotkey.py` — not tested at all
- `server.py` — not tested at all
- `computer_use_server.py` JSON-RPC beyond `initialize` + `tools/list`

---

*Testing analysis: 2026-06-05*
