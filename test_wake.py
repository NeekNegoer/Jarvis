"""
test_wake.py — unit tests for the wake-word matcher (no microphone needed).

Run with pytest:        .venv/bin/python -m pytest test_wake.py -q
Or as a plain script:   .venv/bin/python test_wake.py
"""

from __future__ import annotations

from wake import match_wake_word

# (text, expect_match, expect_command)  — command compared case-insensitively.
CASES = [
    # --- plain hits ---
    ("Jarvis, what time is it?",            True,  "what time is it"),
    ("jarvis open safari",                  True,  "open safari"),
    ("Jarvis.",                             True,  ""),
    ("Jarvis",                              True,  ""),
    # --- leading fillers are stripped ---
    ("Hey Jarvis, play some music",         True,  "play some music"),
    ("ok jarvis what's the weather",        True,  "what's the weather"),
    ("Ei Jarvis, que horas são?",           True,  "que horas são"),   # PT, accents kept
    # --- Whisper mishearings caught by the fuzzy ratio ---
    ("Jarvez, lock the screen",             True,  "lock the screen"),
    ("Jarbis open mail",                    True,  "open mail"),
    ("Járvis, abre o navegador",            True,  "abre o navegador"),
    ("Jervis what's up",                    True,  "what's up"),
    ("Harvis turn off the lights",          True,  "turn off the lights"),
    # --- Whisper mishearings caught by the explicit alias list ---
    ("Service, set a timer",                True,  "set a timer"),
    ("Travis, remind me at five",           True,  "remind me at five"),
    # --- split-token mishearing "jar vis" ---
    ("Jar vis, what's the date",            True,  "what's the date"),
    # --- no wake word → must NOT fire ---
    ("what time is it",                     False, ""),
    ("open safari please",                  False, ""),
    ("I love marvelous java drivers",       False, ""),  # near-miss words stay below 0.75
    ("is it raining",                       False, ""),
    ("",                                    False, ""),
    # --- wake word too deep in the sentence → must NOT fire (address Jarvis up front) ---
    ("please could you ask jarvis to help", False, ""),
]


def test_matcher():
    for text, want_match, want_cmd in CASES:
        got_match, got_cmd = match_wake_word(text)
        assert got_match == want_match, f"match mismatch for {text!r}: {got_match}"
        if want_match:
            assert got_cmd.lower() == want_cmd.lower(), \
                f"command mismatch for {text!r}: {got_cmd!r} != {want_cmd!r}"


def test_custom_wake_word():
    assert match_wake_word("computer open mail", wake_word="computer") == (True, "open mail")
    assert match_wake_word("jarvis open mail", wake_word="computer")[0] is False


def test_threshold_is_tunable():
    # A very loose threshold lets a far word through; a strict one rejects a real variant.
    assert match_wake_word("travis hello", threshold=0.99)[0] is True   # alias, not fuzzy
    assert match_wake_word("charvis hello", threshold=0.95)[0] is False  # fuzzy 0.77 < 0.95
    assert match_wake_word("charvis hello", threshold=0.75)[0] is True


if __name__ == "__main__":
    test_matcher()
    test_custom_wake_word()
    test_threshold_is_tunable()
    print(f"All {len(CASES)} matcher cases + custom-word + threshold tests passed.")
