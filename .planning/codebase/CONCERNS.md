# Codebase Concerns

**Analysis Date:** 2026-06-05

---

## Tech Debt

**Hand-written MCP server (Python 3.9 constraint):**
- Issue: The venv is Python 3.9.6; the official `mcp` SDK requires 3.10+. `computer_use_server.py` is a hand-rolled JSON-RPC 2.0 stdio server (~290 lines) that reimplements protocol framing, tool dispatch, and error handling from scratch.
- Files: `computer_use_server.py`, `mcp_config.json`
- Impact: Any MCP protocol update or new capability (e.g., resource subscriptions, progress notifications) requires manual implementation. Protocol edge-cases (batch requests, partial reads, malformed UTF-8 in large payloads) are unhandled — the server reads one `stdin` line at a time with `sys.stdin`, which is fragile if a tool result emits a newline mid-stream.
- Fix approach: Upgrade the venv to Python 3.10+ (no other blocker exists) and replace `computer_use_server.py` with the official SDK. The `mcp_config.json` spawn command can stay unchanged.

**Subprocess-per-turn brain architecture:**
- Issue: `brain.py` spawns a fresh `claude` CLI process for every single turn via `subprocess.run`. The CLI re-evaluates the project's `SessionStart` hooks on every invocation.
- Files: `brain.py` (`think()` method, lines 148–178)
- Impact: Adds 1–5 s of latency per turn (per CHECKPOINTS.md checkpoint 8: "TTFT ~5s is dominated by the project's own SessionStart hooks firing per turn"). This is the dominant latency source and is architectural — it cannot be tuned away without changing the invocation model.
- Fix approach: Investigate the `claude` CLI's `--resume` flag to see if hooks are skipped on resumed sessions; or move to the Anthropic API directly once an API key is available; or strip SessionStart hooks from the project that fires Jarvis.

**No automated test suite; ad-hoc test scripts only:**
- Issue: Tests live as standalone scripts (`selftest.py`, `test_memory_consolidate.py`, `test_computer_use.py`, `test_wake.py`) with no shared runner, no CI, and no coverage measurement. There is no `pytest` configuration.
- Files: `selftest.py`, `test_memory_consolidate.py`, `test_computer_use.py`, `test_wake.py`
- Impact: Regressions in core modules (ears, brain, mouth, computer) can go undetected. The selftest is a smoke test only — it compiles modules but does not exercise runtime paths. No test covers the MCP server protocol, the web server endpoints, or the memory-consolidation brain call.
- Fix approach: Adopt `pytest`, convert the standalone scripts to test modules, add httpx-based tests for `server.py` endpoints, and add a mock-subprocess fixture for `brain.py`.

**Ollama server must be started manually:**
- Issue: The offline brain (`local_brain.py`) requires `ollama serve` to be running. There is no LaunchAgent, no auto-start in `Jarvis.command`, and no health-check retry loop.
- Files: `local_brain.py`, `Jarvis.command`, `TODO_TOMORROW.md`
- Impact: If Jarvis falls back to the offline brain and Ollama is not running, `LocalBrain.available()` returns `False` and the user gets a "no brain" response instead of an offline reply.
- Fix approach: Add a LaunchAgent plist (`com.jarvis.ollama.plist`) that starts `ollama serve` at login, or add an auto-start guard in `local_brain.available()` / `Jarvis.command`.

---

## Known Bugs / Historical Issues

**MLX/Metal segfault on concurrent transcription (fixed, fragile):**
- Symptoms: Process exits with code 139 (SIGSEGV) when MLX Metal operations run concurrently.
- Files: `ears.py` (lines 63–72, `_stt_lock`), `wake.py` (references `ears._transcribe_array`)
- Trigger: Any code path that starts a background thread and calls into `mlx_whisper.transcribe` outside the lock, or upgrades to a new version of `mlx-whisper` that changes its threading behavior.
- Workaround: All transcription is serialized through `_stt_lock` in `ears.py`. The warm-up thread (line 107) runs under the lock too, but if `_init_backend()` is ever called more than once (e.g., after a reload) a second warm-up thread could race. No regression test guards this.

**faster-whisper uses a temp file with `delete=True`:**
- Symptoms: On some OS/Python combinations, `NamedTemporaryFile(delete=True)` deletes the file before `faster-whisper` finishes reading it (Windows-style behavior can appear on macOS if the file handle is closed before the subprocess reads it).
- Files: `ears.py` (lines 84–91, `_transcribe_locked`)
- Trigger: faster-whisper fallback path. The file is opened, written, then the context manager closes it while `_fw_model.transcribe` still has the path string. On macOS this works today but is non-portable.
- Fix approach: Use `delete=False` and `os.unlink` in a `finally` block.

**Brain returns raw error text on non-network CLI failure:**
- Symptoms: If `claude` CLI returns a non-zero exit code for reasons OTHER than network errors (e.g., model error, malformed `--system-prompt`), `brain.think()` returns the truncated `proc.stdout or proc.stderr` string (up to 500 chars) as the spoken reply. The user hears raw error text.
- Files: `brain.py` (lines 159–164)
- Trigger: Any `claude` CLI error that does not contain "network", "connect", "timeout", "offline", or "fetch failed" in stderr.
- Fix approach: Raise a dedicated exception or return a user-friendly fallback string instead of raw stderr.

**`_is_goodbye` regex is import-at-call-time:**
- Issue: `import re` inside `_is_goodbye()` in `jarvis.py` (line 51) means every goodbye check re-executes the import statement.
- Files: `jarvis.py` (line 51)
- Impact: Negligible performance, but signals missing module-level import discipline.

---

## Security Considerations

**`memory/about_you.md` contains personal data (PII):**
- Risk: The file stores personal facts about Pietro (name, location, habits, preferences) appended by Jarvis automatically over time. It is not encrypted, and any process with filesystem read access can read it. If the repo is ever accidentally pushed public, this file is exposed.
- Files: `memory/about_you.md`, `computer_use_server.py` (`_remember` handler, lines 181–188), `memory_consolidate.py`
- Current mitigation: The `.gitignore` must exclude `memory/about_you.md`; verify this is the case before any `git push`. The `remember` tool docstring says "NOT secrets or one-off trivia" but nothing prevents the model from writing sensitive content.
- Recommendations: Add `memory/about_you.md` to `.gitignore` explicitly if not already there. Consider encrypting at rest with macOS Keychain, or at minimum document the privacy surface.

**AppleScript destructive-action guard is regex-based (bypassable):**
- Risk: The `_DESTRUCTIVE` pattern list in `computer_use_server.py` (lines 153–167) blocks irreversible actions unless `confirm=True`. Because it matches lowercased script text with regexes, a sufficiently creative prompt could craft an AppleScript that passes the patterns while still being destructive (e.g., using variables, `do shell script`, multi-step obfuscation).
- Files: `computer_use_server.py` (lines 153–178)
- Current mitigation: The `_DESTRUCTIVE` list covers the most common attack surfaces (rm, sudo, empty trash, delete, send mail/messages, shutdown/restart). The safety constraint is defense-in-depth; the model's own persona also instructs it to confirm destructive actions.
- Recommendations: Treat the guard as a last-resort net, not a security boundary. For a higher bar, enumerate an allowlist of safe AppleScript tell-targets rather than a denylist.

**Static file serving: path traversal is blocked correctly:**
- Risk: Serving arbitrary files from `web/` could allow `../` traversal to read other files.
- Files: `server.py` (lines 106–110, `do_GET`)
- Current mitigation: `(WEB / rel).resolve()` is checked against `WEB.resolve()` with `str(f).startswith(...)`. This is correct for resolved absolute paths on macOS (no symlink ambiguity if `WEB` itself is not a symlink). The server binds `127.0.0.1` only.
- Recommendations: No immediate action needed. Note that if `WEB` ever becomes a symlink the `resolve()` check still works because both sides are resolved; this is safe.

**`run_applescript` receives untrusted model output:**
- Risk: The brain constructs and executes arbitrary AppleScript based on Claude's output. Although the destructive-action guard exists, Claude (or a prompt injection via screen content) could generate AppleScript that performs actions not covered by the guard.
- Files: `computer.py` (`run_applescript`, line 261), `computer_use_server.py` (`run_applescript` tool handler)
- Current mitigation: `--strict-mcp-config` limits the brain to the whitelisted tools only; `bypassPermissions` is not set; the destructive guard blocks the worst patterns.
- Recommendations: Log all AppleScript invocations to a durable audit log (currently only stderr of the MCP server). Consider a per-session confirmation toggle for `run_applescript` even on non-destructive scripts.

**No CSRF protection on `/api/ask` and `/api/reset`:**
- Risk: Any page loaded in the same browser can POST to `http://127.0.0.1:8765/api/ask` and trigger Jarvis actions. Since the server binds localhost only, the attack surface is limited to the local machine.
- Files: `server.py` (lines 112–136, `do_POST`)
- Current mitigation: Localhost-only binding significantly reduces risk. There is no authentication token.
- Recommendations: Add an `Origin` header check (allow only `http://127.0.0.1:8765`), or generate a random token at startup and require it in POST bodies.

---

## Performance Bottlenecks

**SessionStart hooks dominate per-turn latency:**
- Problem: Each turn spawns a new `claude` CLI process which re-fires the project's Claude Code `SessionStart` hooks. CHECKPOINTS.md documents TTFT of ~5 s dominated by this overhead, not model generation time.
- Files: `brain.py` (`_build_cmd`, `think`), `mcp_config.json`
- Cause: `claude -p` in non-interactive mode still runs hooks configured in the active project.
- Improvement path: Identify and disable or remove SessionStart hooks from the project that launches Jarvis; or run Jarvis from a directory with no Claude Code project configured.

**MLX warm-up serializes with the first real transcription:**
- Problem: The background warm-up thread (line 107 of `ears.py`) holds `_stt_lock`. If a user speaks before the warm-up finishes, the real transcription blocks until the silence array is fully processed.
- Files: `ears.py` (lines 99–107)
- Cause: The warm-up and real transcription share the same lock with no priority mechanism.
- Improvement path: Use a `threading.Event` to signal warm-up completion; the main loop can wait on it before accepting the first input rather than competing with the warm-up thread.

**Screenshot is captured at full retina resolution and then downscaled in Python:**
- Problem: `screencapture` dumps a 3600×2338 (retina) PNG; `computer.py` opens it with Pillow, resizes to 1800×1169, and saves it again on every call.
- Files: `computer.py` (`screenshot`, lines 107–136)
- Cause: `screencapture` has no native logical-resolution output option for the exact target size.
- Improvement path: Acceptable at current scale; if screenshot frequency increases (e.g., for streaming vision), consider caching the scale factor and writing directly to a lower-res target.

**Local brain unbounded history list:**
- Problem: `LocalBrain.history` grows without limit for long sessions; every turn sends the entire history to Ollama, increasing latency and memory usage as the session grows.
- Files: `local_brain.py` (lines 48, 62, 76)
- Cause: No sliding-window or summarization step.
- Improvement path: Truncate to the last N turns (e.g., 10) before building the messages list.

---

## Fragile Areas

**`ears.py` module-level side effects on import:**
- Files: `ears.py` (lines 96, 107–108)
- Why fragile: Importing `ears` immediately calls `_init_backend()` (downloads or loads the Whisper model) and starts a background daemon thread for warm-up. Any test, script, or server that imports `ears` incurs the full model-load cost. A failed model download raises on import, which crashes the importer.
- Safe modification: Guard `_init_backend()` and the warm-up thread behind a `if __name__ != "__main__" and not os.getenv("JARVIS_NO_INIT")` flag, or lazy-initialize on the first `listen()` call.
- Test coverage: No unit test covers the import path with a missing model.

**`computer.py` imports Quartz and AppKit at module level:**
- Files: `computer.py` (lines 43–45)
- Why fragile: Any test or utility that imports `computer` will fail on non-macOS systems or in a venv missing `pyobjc`. `selftest.py` works around this by using `py_compile` only.
- Safe modification: Guard system imports with a `sys.platform == "darwin"` check and provide stub implementations for non-Mac environments (useful for CI on Linux runners).

**`mcp_config.json` hard-codes absolute paths:**
- Files: `mcp_config.json`
- Why fragile: The `command` field is `/Users/pietrojustino/Documents/Jarvis/.venv/bin/python` and `args` points to the absolute script path. Moving the project directory breaks the MCP server spawn.
- Safe modification: Generate `mcp_config.json` from `install.sh` using `$(pwd)` / `$(python -c "import sys; print(sys.executable)")` so paths are always current.

**`brain.py` session_id persists across errors:**
- Files: `brain.py` (`think` method, line 172)
- Why fragile: `self.session_id` is updated only on success. If a turn fails mid-stream (timeout, non-zero exit with partial output), the old `session_id` is reused on the next `--resume`, which may produce unexpected context. There is no mechanism to detect a stale or invalidated session_id.
- Safe modification: On `BrainOffline` or unrecognized error, consider clearing `session_id` so the next turn starts a fresh session rather than resuming a potentially broken one.

**`server.py` shares a single `Brain` instance across threads:**
- Files: `server.py` (lines 29–30, 40–45, 61–68)
- Why fragile: `ThreadingHTTPServer` can serve concurrent requests. `_brain_lock` protects the `_get_brain()` lazy-init, and `brain.think()` is called inside the lock in `_ask()`. This means concurrent `/api/ask` requests serialize at the brain level (acceptable), but the lock is also held for the full ~5 s duration of a `brain.think()` call. A second browser tab sending a request during a long computer-use turn (up to 600 s) will block indefinitely, potentially timing out the HTTP connection.
- Safe modification: Use a request queue or separate Brain instances per logical session; or surface a "busy" 503 response when the lock is held.

---

## Scaling Limits

**Max plan rate limits:**
- Current capacity: Unlimited conversational use under the Max plan subscription; no API key, no per-token cost.
- Limit: If Anthropic imposes session or request rate limits on the CLI tool, `brain.think()` will fail with an error string that may not match the "offline" keyword list in `brain.py` line 161.
- Scaling path: Add explicit detection of rate-limit error strings; implement exponential backoff in `think()`.

**Ollama model fits in unified memory:**
- Current capacity: qwen2.5:7b runs on M1 Pro 16 GB (11.8 GiB VRAM). Larger models may not fit.
- Limit: Loading a 13B+ model would exhaust VRAM and fall back to CPU, making it unusably slow for voice interaction.
- Scaling path: Use quantized models (Q4_K_M); switch model via `JARVIS_OLLAMA_MODEL`.

---

## Dependencies at Risk

**`pyobjc` (Quartz, AppKit, ApplicationServices):**
- Risk: `pyobjc` bindings track macOS SDK changes. A major macOS version bump can break Quartz CGEvent APIs (e.g., CGEventCreateMouseEvent signatures), Accessibility APIs, or Workspace calls. macOS 26 is a new enough version that any untested API change here could silently break computer control.
- Impact: `computer.py` — the entire mouse, keyboard, AX tree, and screenshot pipeline.
- Migration plan: Pin `pyobjc` to a tested version in `requirements.txt`; run `test_computer_use.py` after each macOS update.

**`mlx-whisper` (MLX framework, Metal):**
- Risk: MLX is actively developed by Apple; breaking API changes are possible. The thread-safety constraint is undocumented and discovered empirically (CHECKPOINTS.md checkpoint 1).
- Impact: `ears.py` — transcription will segfault if MLX introduces new background threads or changes the thread model.
- Migration plan: Watch MLX release notes; pin `mlx-whisper` version; keep the `_stt_lock` even if future versions claim thread safety until independently verified.

**`claude` CLI (version 2.1.150):**
- Risk: The brain depends on the CLI's `--output-format json`, `--resume`, `--mcp-config`, `--strict-mcp-config`, and `--allowedTools` flags. Any of these could change in a future CLI release.
- Impact: `brain.py` — JSON parsing (`data.get("result")`, `data.get("session_id")`) will break silently if the output schema changes; MCP integration breaks if flag names change.
- Migration plan: Pin the CLI version (`npm pin` or document required version); add a version check in `doctor.py`.

---

## Missing Critical Features

**No microphone permission check before recording:**
- Problem: `ears.listen()` calls `sd.InputStream` without first verifying that the microphone permission is granted. On first run, macOS shows a system dialog; if denied, `sounddevice` raises an error that propagates uncaught through `jarvis.py`.
- Files: `ears.py` (lines 134–140), `doctor.py`
- Blocks: First-run experience for new users; silent failure in hands-free mode.

**No input sanitization on `/api/ask` text field:**
- Problem: `server.py` passes `data.get("text")` directly to `brain.think()` with only a `.strip()`. There is no length limit, no character filtering, and no rate limiting.
- Files: `server.py` (lines 131–135)
- Blocks: Protects against accidental but not malicious misuse; a local attacker could send very long strings that inflate context or exceed the CLI timeout.

**Wake-word mode has no self-trigger suppression for the web UI:**
- Problem: `wake.py` suppresses self-triggering only when using `mouth.speak(..., block=True)` in the terminal modes. The web UI (`server.py`) uses Chrome's TTS in the browser; the Python microphone remains open and will transcribe Jarvis's own browser voice if the wake-word loop is running concurrently.
- Files: `wake.py`, `server.py`
- Blocks: Concurrent use of wake-word mode and the browser UI.

---

## Test Coverage Gaps

**MCP server protocol (computer_use_server.py):**
- What's not tested: JSON-RPC framing, tool dispatch, error paths, the `remember` handler, the `_guarded_applescript` regex patterns.
- Files: `computer_use_server.py`
- Risk: A protocol regression breaks all computer-use features silently.
- Priority: High

**`server.py` HTTP endpoints:**
- What's not tested: `/api/ask`, `/api/reset`, `/api/health`, static file serving, path traversal guard, concurrent request behavior.
- Files: `server.py`
- Risk: A change to the request parsing or brain integration breaks the web UI with no automated signal.
- Priority: High

**`brain.py` subprocess integration:**
- What's not tested: `BrainOffline` detection logic, session_id capture, timeout handling, non-zero exit code handling.
- Files: `brain.py`
- Risk: Error-handling regressions go unnoticed until Pietro encounters them.
- Priority: Medium

**`ears.py` faster-whisper fallback path:**
- What's not tested: The CPU fallback (`faster-whisper`) code path, including the temp-file write/read cycle.
- Files: `ears.py` (lines 83–93)
- Risk: The fallback silently breaks if `scipy` or `faster-whisper` behavior changes.
- Priority: Medium

---

*Concerns audit: 2026-06-05*
