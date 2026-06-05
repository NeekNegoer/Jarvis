"""
brain.py — Jarvis's brain, powered by your Claude Max plan (no API key).

Instead of calling the Anthropic API (which needs a paid API key), this shells out
to the `claude` command-line tool in headless mode. That tool is already logged in
with your **Max plan subscription**, so every reply is "free" under your plan and
needs no ANTHROPIC_API_KEY.

Bonus: because the brain is the full Claude Code agent, it can use tools — including
the system-wide computer-use tools in `computer_use_server.py`. That's what lets
Jarvis actually click, type, and read your screen, not just chat.

Conversation memory across a session is kept by capturing the `session_id` the CLI
returns and passing `--resume` on every following turn.
"""

from __future__ import annotations  # allow `str | None` hints on Python 3.9

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

HERE = Path(__file__).parent
MCP_CONFIG = HERE / "mcp_config.json"        # written by setup; enables computer use
PERSONA_FILE = HERE / "persona.md"           # editable personality (optional)
MEMORY_FILE = HERE / "memory" / "about_you.md"  # what Jarvis remembers about Pietro

# How long to wait for a single reply. Plain chat is fast; a computer-use task
# (open an app, click around, read the screen) can take a while, so be generous.
CHAT_TIMEOUT = 90          # seconds, no tools
COMPUTER_TIMEOUT = 600     # seconds, when computer use is on

# The tools the brain may use without prompting (headless can't show a prompt).
# We whitelist ONLY the computer-use MCP tools (+ read-only file access) — deliberately
# NOT unrestricted Bash. That keeps Jarvis scoped to controlling the Mac through the
# vetted tools, not arbitrary shell commands. (Safety guidance: scope the tools.)
COMPUTER_TOOLS = [
    "mcp__computer__screenshot",
    "mcp__computer__screen_info",
    "mcp__computer__click",
    "mcp__computer__double_click",
    "mcp__computer__right_click",
    "mcp__computer__move_mouse",
    "mcp__computer__scroll",
    "mcp__computer__type_text",
    "mcp__computer__key",
    "mcp__computer__list_ui_elements",
    "mcp__computer__click_element",
    "mcp__computer__open_app",
    "mcp__computer__frontmost_app",
    "mcp__computer__run_applescript",
    "mcp__computer__remember",
    "Read",
]

DEFAULT_PERSONA = """You are Jarvis, Pietro's personal AI assistant. You speak out loud,
so your replies are read by a text-to-speech voice.

LANGUAGE: Pietro is Brazilian and bilingual. ALWAYS reply in the SAME language he
just used — Brazilian Portuguese if he spoke Portuguese, English if he spoke English.
Match his language naturally; never mix them in one reply.

VOICE STYLE (your words are spoken aloud, so):
- Keep replies short and conversational — usually 1 to 3 sentences.
- No markdown, no bullet points, no code blocks, no emojis, no URLs. Plain spoken words only.
- Say numbers, dates and times the way a person would say them.
- If a task has many steps, say the gist out loud and just do it; don't read out a list.

PERSONALITY: warm, witty, calm and genuinely capable — a great chief-of-staff, not a
robotic FAQ bot. Be proactive. Remember what you learn about Pietro.

COMPUTER CONTROL: You can control this whole Mac with your tools (take a screenshot to
see the screen, click, type, press keys, open apps, read on-screen UI elements). When he
asks you to DO something on the computer, actually do it with the tools, then tell him
out loud in one short sentence what you did. Take a screenshot first to see the current
state before acting. Find buttons/fields by taking a screenshot and/or listing UI elements.

SAFETY: Before anything destructive or hard to undo — deleting files, sending an email or
message, making a purchase, posting publicly — say what you're about to do and ask him to
confirm out loud first. Everyday safe actions (opening apps, navigating, reading, taking
notes) you can just do."""


class BrainOffline(Exception):
    """Raised when the Max-plan brain can't be reached (e.g. no network)."""


def _load_persona() -> str:
    if PERSONA_FILE.exists():
        text = PERSONA_FILE.read_text().strip()
        if text:
            return text
    return DEFAULT_PERSONA


def _load_memory() -> str:
    if MEMORY_FILE.exists():
        return MEMORY_FILE.read_text().strip()
    return ""


def _system_prompt() -> str:
    """Persona + what Jarvis has learned about Pietro, refreshed every session."""
    parts = [_load_persona()]
    memory = _load_memory()
    if memory:
        parts.append("What you remember about Pietro:\n" + memory)
    parts.append(
        "If he tells you something worth remembering long-term (a preference, a fact about "
        "him, how he likes things done), save it with the `remember` tool. Don't save "
        "secrets, passwords, or one-off trivia.")
    return "\n\n".join(parts)


class Brain:
    def __init__(self, enable_computer_use: bool | None = None, model: str | None = None):
        self.claude = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
        if not Path(self.claude).exists():
            raise RuntimeError(
                "The `claude` CLI was not found. Install Claude Code and log in with "
                "your Max plan first (https://claude.com/claude-code)."
            )
        self.model = model
        self.session_id: str | None = None
        self.persona = _system_prompt()

        # Computer use turns on automatically if the MCP config exists, unless told otherwise.
        if enable_computer_use is None:
            enable_computer_use = MCP_CONFIG.exists()
        self.computer_use = enable_computer_use

        # Per-Brain lock: used by the server worker to guarantee single-writer access per session
        # (protects the MCP stdio pipe and self.session_id from concurrent turns).
        self._lock = threading.Lock()

    def _build_cmd(self, user_text: str) -> list[str]:
        cmd = [self.claude, "-p", user_text, "--output-format", "json",
               "--system-prompt", self.persona]
        if self.model:
            cmd += ["--model", self.model]
        if self.session_id:
            cmd += ["--resume", self.session_id]
        if self.computer_use and MCP_CONFIG.exists():
            # Whitelist only our computer tools; --strict-mcp-config ignores any other
            # MCP servers configured on the machine. No bypassPermissions, no Bash.
            cmd += ["--mcp-config", str(MCP_CONFIG), "--strict-mcp-config",
                    "--allowedTools", *COMPUTER_TOOLS]
        return cmd

    def _build_stream_cmd(self, user_text: str) -> list:
        """Like _build_cmd but sets --output-format stream-json + --verbose (REQUIRED).

        CRITICAL: stream-json refuses to run without --verbose.
        Error: 'When using --print, --output-format=stream-json requires --verbose'
        [VERIFIED: empirical run 2026-06-05]
        """
        cmd = self._build_cmd(user_text)
        idx = cmd.index("--output-format")
        cmd[idx + 1] = "stream-json"
        cmd.insert(idx + 2, "--verbose")  # REQUIRED — stream-json refuses without it
        return cmd

    # NOTE: tool_use/screenshot block shapes below are MEDIUM confidence (not verified on a real
    # computer-use turn). Run one turn with JARVIS_STREAM_DEBUG=1 and inspect stream_debug.ndjson
    # to confirm field names (per RESEARCH Open Question 1).
    def think_stream(self, user_text: str):
        """Generator: yields ActivityEvent dicts; updates self.session_id on result.

        Yields, in order (thinking blocks are filtered):
          {"type":"text","text": str}
          {"type":"tool_use","name": str, "input": dict}   # MEDIUM confidence shape
          {"type":"screenshot","data": str}                 # MEDIUM confidence shape
          {"type":"result","text": str}
          {"type":"done"}
          {"type":"error","text": str}  # only on non-zero exit without a result
        Raises BrainOffline on network-style failures.
        """
        cmd = self._build_stream_cmd(user_text)
        timeout = COMPUTER_TIMEOUT if self.computer_use else CHAT_TIMEOUT  # noqa: F841 (future use)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        final_text = ""
        try:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                # Opt-in raw-line debug trace to confirm MEDIUM-confidence event shapes.
                if os.environ.get("JARVIS_STREAM_DEBUG"):
                    try:
                        with open(HERE / "stream_debug.ndjson", "a", encoding="utf-8") as _dbg:
                            _dbg.write(line + "\n")
                    except Exception:
                        pass
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = obj.get("type", "")
                if t == "assistant":
                    for block in (obj.get("message") or {}).get("content", []):
                        bt = block.get("type", "")
                        if bt == "thinking":
                            continue  # skip internal reasoning [VERIFIED: appears before text block]
                        elif bt == "text":
                            text = block.get("text", "")
                            if text:
                                yield {"type": "text", "text": text}
                        elif bt == "tool_use":
                            # [ASSUMED: field names not verified on a real computer-use turn]
                            yield {
                                "type": "tool_use",
                                "name": block.get("name"),
                                "input": block.get("input", {}),
                            }
                elif t == "user":
                    # Tool results arrive as `user` events (stream_debug_findings.md §3).
                    # message.content[] holds tool_result blocks; inner content[] holds
                    # image blocks.  Defensive: tolerate missing/non-list at each level.
                    # Dual-path for image data:
                    #   MCP shape   (computer_use_server.py line 211): inner["data"]
                    #   Anthropic shape (convention):                   inner["source"]["data"]
                    for block in (obj.get("message") or {}).get("content", []):
                        if block.get("type") != "tool_result":
                            continue
                        for inner in (block.get("content") or []):
                            if inner.get("type") != "image":
                                continue
                            data = (
                                inner.get("data")
                                or (inner.get("source") or {}).get("data")
                                or ""
                            )
                            if data:
                                yield {"type": "screenshot", "data": data}
                elif t == "result":
                    final_text = (obj.get("result") or "").strip()
                    if obj.get("session_id"):
                        self.session_id = obj["session_id"]  # [VERIFIED: empirical run 2026-06-05]
                    yield {"type": "result", "text": final_text or "Okay."}
                # skip type in {"system", "rate_limit_event"} — no user-facing content [VERIFIED]
        finally:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if proc.returncode != 0 and not final_text:
            stderr = proc.stderr.read()
            if any(w in stderr.lower()
                   for w in ("network", "connect", "timeout", "offline", "fetch failed")):
                raise BrainOffline(stderr.strip())
            yield {"type": "error", "text": stderr[:200] or "Something went wrong."}
        yield {"type": "done"}

    def think(self, user_text: str) -> str:
        """Send what the user said to Claude (Max plan) and return the spoken reply."""
        cmd = self._build_cmd(user_text)
        timeout = COMPUTER_TIMEOUT if self.computer_use else CHAT_TIMEOUT
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return "Sorry, that took too long. Could you try again?"
        except FileNotFoundError:
            raise RuntimeError("Could not run the `claude` CLI.")

        if proc.returncode != 0:
            stderr = (proc.stderr or "").lower()
            if any(w in stderr for w in ("network", "connect", "timeout", "offline", "fetch failed")):
                raise BrainOffline(proc.stderr.strip())
            # Fall back to whatever was printed.
            return (proc.stdout or proc.stderr or "Something went wrong.").strip()[:500]

        try:
            data = json.loads(proc.stdout)
        except (json.JSONDecodeError, ValueError):
            return proc.stdout.strip() or "I didn't get a reply."

        # Keep the conversation going next turn.
        if data.get("session_id"):
            self.session_id = data["session_id"]

        if data.get("is_error"):
            raise BrainOffline(str(data.get("result") or data.get("api_error_status")))

        return (data.get("result") or "").strip() or "Okay."


if __name__ == "__main__":
    # Quick standalone test: python brain.py
    b = Brain(enable_computer_use=False)
    print("Brain (no tools) ready. Type to chat, Ctrl+C to quit.\n")
    try:
        while True:
            msg = input("you> ")
            print("jarvis>", b.think(msg), "\n")
    except (KeyboardInterrupt, EOFError):
        print("\nbye")
