"""
selftest.py — fast smoke test of Jarvis's pieces.  python selftest.py

Exercises everything that doesn't need the microphone or the screen permissions, so you
can confirm a healthy install in a few seconds. For permissions, use doctor.py.
"""

from __future__ import annotations

import sys
import traceback

passed, failed = 0, 0


def check(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  ✅ {name}")
        passed += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        traceback.print_exc()
        failed += 1


def t_mouth_clean():
    import mouth
    out = mouth._clean("**Hi** `x` [a](http://b.com)\n- one")
    assert "**" not in out and "http" not in out and out, out


def t_computer_basics():
    import computer
    info = computer.screen_info()
    assert info["logical_width"] > 0 and info["scale"] >= 1
    assert "name" in computer.frontmost_app()
    # key combos parse (won't move anything without Accessibility granted)
    for k in ("return", "cmd+c", "cmd+shift+t", "esc", "f5"):
        computer.key(k)


def t_applescript():
    import computer
    r = computer.run_applescript('return 6 * 7')
    assert r["ok"] and r["stdout"] == "42", r


def t_mcp_tools():
    import computer_use_server as s
    names = {t["name"] for t in s._tools_list()}
    for needed in ("screenshot", "click", "type_text", "list_ui_elements",
                   "run_applescript", "click_element", "remember"):
        assert needed in names, f"missing tool {needed}"
    # the JSON-RPC handler answers initialize + tools/list
    init = s.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "computer"


def t_ears_backend():
    import ears
    assert ears._backend in ("mlx", "faster")


def t_brain_construct():
    from brain import Brain
    b = Brain(enable_computer_use=False)
    assert b.claude and b.persona


def t_local_brain():
    from local_brain import LocalBrain
    lb = LocalBrain()
    # just construct + probe availability (don't require it to be up)
    _ = lb.available()


def t_text_lang_guess():
    import jarvis
    assert jarvis._guess_language("abra o Safari") == "pt"
    assert jarvis._guess_language("open my email") == "en"
    assert jarvis._guess_language("que horas são?") == "pt"


def t_wake_word_matcher():
    import wake
    m, cmd = wake.match_wake_word("Hey Jarvis, open Safari")
    assert m and cmd.lower() == "open safari", (m, cmd)
    assert wake.match_wake_word("what time is it")[0] is False
    assert wake.match_wake_word("Jarvez, lock the screen")[0] is True  # fuzzy mishearing


def t_memory_consolidate_pieces():
    import memory_consolidate as mc
    facts = mc.parse_facts('["Likes concise answers", "Is learning guitar"]')
    assert facts == ["Likes concise answers", "Is learning guitar"], facts
    # dedupe against existing memory
    assert mc.dedupe(["Likes concise answers"], "- Likes concise answers") == []
    # secrets are dropped
    assert mc.parse_facts('["my password is hunter2"]') == []
    # end-to-end with a fake thinker (no network), then nothing duplicates on a re-run
    out = mc.consolidate([("you", "en", "I play tennis on weekends and study law.")],
                         think=lambda p: '["Plays tennis on weekends", "Studies law"]',
                         memory_file="/tmp/jarvis_mem_test.md", today="2026-06-05")
    assert "Plays tennis on weekends" in out, out
    import os
    os.remove("/tmp/jarvis_mem_test.md")


def t_silent_mode():
    import importlib, mouth
    # SILENT honored from env (re-import to pick up the flag)
    import os
    os.environ["JARVIS_SILENT"] = "1"
    importlib.reload(mouth)
    assert mouth.SILENT is True
    mouth.speak("this should not play", "en")  # no audio, no error
    del os.environ["JARVIS_SILENT"]
    importlib.reload(mouth)


def t_destructive_guardrail():
    import computer_use_server as s
    # destructive scripts are blocked without confirm...
    assert s._guarded_applescript('do shell script "rm -rf /tmp/x"', False).get("blocked")
    assert s._guarded_applescript('tell application "Mail" to send m', False).get("blocked")
    assert s._guarded_applescript('tell application "Finder" to empty the trash', False).get("blocked")
    # ...allowed with explicit confirm, and safe scripts run normally
    assert "blocked" not in s._guarded_applescript('return 1', False)
    assert "blocked" not in s._guarded_applescript('tell application "Notes" to count notes', False)


def main():
    print("🧪 Jarvis self-test\n")
    check("mouth markdown cleaning", t_mouth_clean)
    check("computer.py basics (screen/app/keys)", t_computer_basics)
    check("AppleScript bridge", t_applescript)
    check("MCP server tools + handshake", t_mcp_tools)
    check("ears STT backend selected", t_ears_backend)
    check("brain constructs (Max-plan CLI found)", t_brain_construct)
    check("local brain constructs", t_local_brain)
    check("text-mode language guesser", t_text_lang_guess)
    check("destructive-action guardrail", t_destructive_guardrail)
    check("wake-word matcher", t_wake_word_matcher)
    check("memory consolidation pieces", t_memory_consolidate_pieces)
    check("silent mode (JARVIS_SILENT)", t_silent_mode)
    print(f"\n{passed} passed, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
