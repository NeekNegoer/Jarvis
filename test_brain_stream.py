"""
test_brain_stream.py — TDD RED scaffold for Brain.think_stream() (Phase 1, Plan 01).

These tests target Brain.think_stream() and Brain._build_stream_cmd() which DO NOT
exist yet. Running this file produces RED failures naming those missing symbols.
Plans 01-02 and 01-03 will make this suite GREEN.

Python 3.9 compatible (no match, no X|Y unions, no str.removeprefix).
"""

from __future__ import annotations

import io
import json
import threading

import pytest

# ---------------------------------------------------------------------------
# Controlled NDJSON sequence that a fake claude process would emit.
# Reflects the empirically verified stream-json --verbose schema (2026-06-05).
# Line ordering matters: system init → thinking block → text block → tool_use → result.
# ---------------------------------------------------------------------------
FAKE_LINES = [
    # 1. system/init event — must be skipped entirely (not user-facing)
    json.dumps({
        "type": "system",
        "subtype": "init",
        "session_id": "sess-old",
    }) + "\n",

    # 2. assistant event with a thinking block — must be filtered (never surfaced)
    json.dumps({
        "type": "assistant",
        "message": {
            "content": [{"type": "thinking", "thinking": "reasoning"}],
        },
    }) + "\n",

    # 3. assistant event with the actual text reply
    json.dumps({
        "type": "assistant",
        "message": {
            "content": [{"type": "text", "text": "Hi Pietro!"}],
        },
    }) + "\n",

    # 4. assistant event with a tool_use block (MEDIUM confidence shape)
    json.dumps({
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "mcp__computer__screenshot",
                    "input": {},
                }
            ],
        },
    }) + "\n",

    # 5. result event — final text + session_id (VERIFIED: empirical run 2026-06-05)
    json.dumps({
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Hi Pietro!",
        "session_id": "sess-123",
        "stop_reason": "end_turn",
    }) + "\n",
]


class FakePopen:
    """Mimics subprocess.Popen for unit tests.

    stdout is an iterator over NDJSON line strings (each ending "\\n"),
    stderr is io.StringIO(""), returncode is 0, wait() and kill() are no-ops.

    Approach: Brain.__init__ is stubbed via monkeypatch so no real `claude`
    binary is required. FakePopen is set via monkeypatch on brain.subprocess.Popen
    so no real subprocess is spawned.
    """

    def __init__(self, cmd, **kwargs):  # accepts all Popen kwargs (text=True, etc.)
        self.stdout = iter(list(FAKE_LINES))  # copy to allow re-use across tests
        self.stderr = io.StringIO("")
        self.returncode = 0

    def wait(self, timeout=None):  # noqa: D401
        """No-op — process is already "done"."""

    def kill(self):
        """No-op."""


def FakePopenWith(lines):
    """Return a Popen-compatible class that replays the given lines list.

    Usage: monkeypatch.setattr(brain_module.subprocess, "Popen", FakePopenWith(my_lines))
    """
    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            self.stdout = iter(list(lines))
            self.stderr = io.StringIO("")
            self.returncode = 0

        def wait(self, timeout=None):
            pass

        def kill(self):
            pass

    return _FakePopen


# ---------------------------------------------------------------------------
# NDJSON lines for screenshot (user-event) tests.
# Reflects stream_debug_findings.md §3: tool results arrive as `user` events
# whose message.content[] holds tool_result blocks with inner content[].
# ---------------------------------------------------------------------------

# MCP shape: computer_use_server.py _screenshot_result() returns
#   {"type": "image", "data": "<b64>", "mimeType": "image/png"}
# (line 211 of computer_use_server.py — `data` field, no `source` wrapper).
USER_SCREENSHOT_LINE = json.dumps({
    "type": "user",
    "message": {
        "content": [
            {
                "type": "tool_result",
                "content": [
                    {"type": "image", "data": "AAAA", "mimeType": "image/png"},
                ],
            }
        ]
    },
}) + "\n"

# Anthropic convention shape: image wrapped in source.data (defensive dual-path).
USER_SOURCE_SCREENSHOT_LINE = json.dumps({
    "type": "user",
    "message": {
        "content": [
            {
                "type": "tool_result",
                "content": [
                    {"type": "image", "source": {"type": "base64", "data": "BBBB"}},
                ],
            }
        ]
    },
}) + "\n"

# A user/tool_result whose inner content has only text — must yield NO screenshot event.
USER_TEXT_RESULT_LINE = json.dumps({
    "type": "user",
    "message": {
        "content": [
            {
                "type": "tool_result",
                "content": [
                    {"type": "text", "text": "Tool completed successfully"},
                ],
            }
        ]
    },
}) + "\n"

_RESULT_LINE = json.dumps({
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": "Done.",
    "session_id": "sess-screenshot",
    "stop_reason": "end_turn",
}) + "\n"

_SYSTEM_LINE = json.dumps({
    "type": "system",
    "subtype": "init",
    "session_id": "sess-old",
}) + "\n"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def brain(monkeypatch):
    """Construct a Brain with no real claude binary and no computer use.

    Strategy: monkeypatch brain.shutil.which to return '/usr/bin/true'
    (exists on macOS/Linux) so Brain.__init__ passes the binary-existence check
    without requiring a real `claude` installation in the test environment.
    """
    import brain as brain_module

    # Stub the binary discovery so __init__ succeeds without a real claude CLI.
    monkeypatch.setattr(brain_module.shutil, "which", lambda _name: "/usr/bin/true")

    from brain import Brain

    return Brain(enable_computer_use=False)


# ---------------------------------------------------------------------------
# Tests — each maps to a row in 01-VALIDATION.md (CORE-02 unit section).
# All will fail RED until Brain.think_stream / _build_stream_cmd are implemented.
# ---------------------------------------------------------------------------


def test_event_types(monkeypatch, brain):
    """think_stream yields typed events in order: text, tool_use, result, done.

    VALIDATION.md CORE-02: Events arrive with correct type fields.
    """
    import brain as brain_module

    monkeypatch.setattr(brain_module.subprocess, "Popen", FakePopen)

    events = list(brain.think_stream("hi"))
    types = [e["type"] for e in events]

    # Expected sequence after filtering system/thinking events
    assert types == ["text", "tool_use", "result", "done"], (
        "Expected event types ['text', 'tool_use', 'result', 'done'], got: " + str(types)
    )

    text_event = next(e for e in events if e["type"] == "text")
    assert text_event["text"] == "Hi Pietro!"

    tool_event = next(e for e in events if e["type"] == "tool_use")
    assert tool_event["name"] == "mcp__computer__screenshot"


def test_thinking_block_filtered(monkeypatch, brain):
    """Internal 'thinking' blocks must NEVER surface as yielded events.

    VALIDATION.md CORE-02: think_stream() filters thinking blocks.
    Pitfall 6 from 01-RESEARCH.md: thinking block forwarded to browser.
    """
    import brain as brain_module

    monkeypatch.setattr(brain_module.subprocess, "Popen", FakePopen)

    events = list(brain.think_stream("hi"))

    for event in events:
        assert event.get("text") != "reasoning", (
            "Thinking block leaked into event stream as text='reasoning'"
        )
        assert event.get("type") != "thinking", (
            "Thinking block leaked as a top-level event type='thinking'"
        )


def test_session_id_captured(monkeypatch, brain):
    """After consuming the stream, brain.session_id must equal the result session_id.

    VALIDATION.md CORE-02: result event updates brain.session_id for resume.
    Verified: session_id location in the result event confirmed empirically 2026-06-05.
    """
    import brain as brain_module

    monkeypatch.setattr(brain_module.subprocess, "Popen", FakePopen)

    # Exhaust the generator — session_id must be set as a side-effect.
    list(brain.think_stream("hi"))

    assert brain.session_id == "sess-123", (
        "brain.session_id not updated from result event; got: " + repr(brain.session_id)
    )


def test_build_stream_cmd_requires_verbose(brain):
    """_build_stream_cmd must include stream-json, --verbose, and --output-format.

    CRITICAL finding from 01-RESEARCH.md: stream-json refuses to run without --verbose.
    Error: 'When using --print, --output-format=stream-json requires --verbose'
    """
    cmd = brain._build_stream_cmd("hi")

    assert "--output-format" in cmd, "_build_stream_cmd missing --output-format flag"
    assert "stream-json" in cmd, "_build_stream_cmd must set output format to stream-json"
    assert "--verbose" in cmd, (
        "_build_stream_cmd missing --verbose (REQUIRED: stream-json refuses without it)"
    )


def test_has_per_brain_lock(brain):
    """Brain must expose self._lock (threading.Lock) for single-writer serialization.

    Per 01-RESEARCH.md Assumption A3: current brain.py has no per-Brain lock.
    Plan 01-02 adds it. This test enforces its presence.
    Pitfall 4: concurrent claude processes fighting over MCP stdio pipe.
    """
    assert hasattr(brain, "_lock"), "Brain must have a _lock attribute"
    # Verify it behaves like a lock (has acquire/release/context manager protocol).
    lock = brain._lock
    assert hasattr(lock, "acquire"), "brain._lock must be a threading.Lock-compatible object"
    assert hasattr(lock, "release"), "brain._lock must be a threading.Lock-compatible object"


# ---------------------------------------------------------------------------
# Screenshot / user-event tests (Phase 2, Plan 01).
# Verify that think_stream emits {"type":"screenshot","data":<b64>} from the
# `user` event that wraps tool_result blocks (stream_debug_findings.md §3).
# ---------------------------------------------------------------------------


def test_screenshot_from_user_event_mcp_shape(monkeypatch, brain):
    """think_stream emits screenshot event from `user` tool_result with MCP image shape.

    computer_use_server.py returns {"type":"image","data":"<b64>","mimeType":"image/png"}.
    The claude CLI wraps it inside a `user` event message.content[].tool_result.content[].
    think_stream must read inner.get("data") and yield {"type":"screenshot","data":"AAAA"}.
    """
    import brain as brain_module

    lines = [_SYSTEM_LINE, USER_SCREENSHOT_LINE, _RESULT_LINE]
    monkeypatch.setattr(brain_module.subprocess, "Popen", FakePopenWith(lines))

    events = list(brain.think_stream("take a screenshot"))
    screenshot_events = [e for e in events if e["type"] == "screenshot"]

    assert len(screenshot_events) == 1, (
        "Expected exactly 1 screenshot event from MCP-shape user event, got: "
        + str(screenshot_events)
    )
    assert screenshot_events[0]["data"] == "AAAA", (
        "Expected data='AAAA', got: " + repr(screenshot_events[0].get("data"))
    )


def test_screenshot_from_user_event_source_shape(monkeypatch, brain):
    """think_stream emits screenshot event from `user` tool_result with Anthropic image shape.

    Anthropic convention wraps base64 as {"type":"image","source":{"type":"base64","data":"BBBB"}}.
    Defensive dual-path: inner.get("source",{}).get("data") fallback must fire here.
    """
    import brain as brain_module

    lines = [_SYSTEM_LINE, USER_SOURCE_SCREENSHOT_LINE, _RESULT_LINE]
    monkeypatch.setattr(brain_module.subprocess, "Popen", FakePopenWith(lines))

    events = list(brain.think_stream("take a screenshot"))
    screenshot_events = [e for e in events if e["type"] == "screenshot"]

    assert len(screenshot_events) == 1, (
        "Expected exactly 1 screenshot event from Anthropic-shape user event, got: "
        + str(screenshot_events)
    )
    assert screenshot_events[0]["data"] == "BBBB", (
        "Expected data='BBBB', got: " + repr(screenshot_events[0].get("data"))
    )


def test_user_text_result_no_screenshot(monkeypatch, brain):
    """think_stream yields NO screenshot event when user tool_result contains only text.

    A `user` event whose inner content[] has only text blocks must not crash or
    emit spurious screenshot events. Confirms the defensive guard on inner block type.
    """
    import brain as brain_module

    lines = [_SYSTEM_LINE, USER_TEXT_RESULT_LINE, _RESULT_LINE]
    monkeypatch.setattr(brain_module.subprocess, "Popen", FakePopenWith(lines))

    events = list(brain.think_stream("do something"))
    screenshot_events = [e for e in events if e["type"] == "screenshot"]

    assert len(screenshot_events) == 0, (
        "Expected no screenshot events from text-only tool_result, got: "
        + str(screenshot_events)
    )
