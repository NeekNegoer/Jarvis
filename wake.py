"""
wake.py — OPTIONAL wake-word mode for Jarvis ("just say 'Jarvis ...'").

Run it with:  python jarvis.py --wake

How it works (and why it's built this way):
  • It reuses the EXISTING mlx-whisper pipeline in ears.py — no new model dependency.
    We sit in a low-power loop on `ears.listen_continuous`, which uses cheap energy-based
    voice-activity detection (VAD): it BLOCKS on the microphone until you actually speak,
    so it is I/O-bound, not a CPU busy-loop. Each captured utterance is transcribed once.
  • Every transcription goes through `ears._transcribe_array`, which holds the module-wide
    `_stt_lock`. MLX/Metal is NOT thread-safe, so this serialization is mandatory; we never
    spawn our own STT thread — we just call the locked path, same as push-to-talk mode.
  • Whisper mishears "Jarvis" constantly (jarvez, jarbis, "service", "travis", "járvis"…),
    so detection is a FUZZY matcher (`match_wake_word`) — pure logic, unit-testable with no
    microphone. It strips the wake word and hands the remainder to the brain as a turn.
  • The mic would otherwise hear Jarvis's own voice. `mouth.speak(..., block=True)` blocks
    the whole loop while we talk, so we can't capture our own TTS; we also drain a beat after
    speaking and re-open a fresh input stream each cycle (stale buffer discarded). Headphones
    are still recommended.

Configuration (all optional, via environment variables):
  JARVIS_WAKE_WORD            wake word to listen for          (default: "jarvis")
  JARVIS_WAKE_THRESHOLD       fuzzy match ratio 0..1           (default: 0.75)
  JARVIS_WAKE_FOLLOWUP_SECS   seconds to keep listening for a follow-up WITHOUT the
                              wake word after a reply; 0 disables it   (default: 0)

A note on a dedicated wake-word library (openWakeWord): see the module docstring section
"WHY NOT openWakeWord?" at the bottom of this file.
"""

from __future__ import annotations

import os
import re
import time
import unicodedata
from difflib import SequenceMatcher

# ----------------------------------------------------------------------------------
#  PURE WAKE-WORD MATCHING  (no audio, no I/O — fully unit-testable)
# ----------------------------------------------------------------------------------

DEFAULT_WAKE_WORD = "jarvis"
DEFAULT_THRESHOLD = 0.75

# Filler words people put BEFORE the wake word ("hey Jarvis", "ok Jarvis", "ei Jarvis").
# These are skipped so the command is whatever follows the wake word.
_FILLERS = {
    "hey", "hi", "hello", "ok", "okay", "yo",        # English
    "ei", "oi", "ola", "o", "e", "psiu",             # Portuguese (accents already stripped)
}

# Known Whisper MISHEARINGS of "Jarvis" whose spelling is too far from "jarvis" for the
# fuzzy ratio to catch (service≈0.46, travis≈0.67, jarvez≈0.67). Curated, deliberately
# conservative — every entry below is something Whisper has actually emitted for "Jarvis".
# Close spelling variants (jarbis, jervis, harvis, jarvus, jarvi…) are caught by the fuzzy
# ratio instead, so they don't need to be listed here.
_JARVIS_ALIASES = {
    "jarvis", "jarvez", "jarves", "travis", "service", "jervais", "jarviz",
    "jarvie", "jarby", "darby", "jervis", "jarvix", "jarbiz",
}


def _normalize(text: str) -> str:
    """Lowercase, strip accents (járvis→jarvis), drop punctuation, collapse whitespace."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(text: str) -> list[tuple[str, str]]:
    """Split on whitespace into (original_token, normalized_token) pairs.

    Original tokens are kept so the returned command preserves accents/casing (which the
    brain uses to detect Brazilian Portuguese vs English). Tokens that normalize to nothing
    (e.g. a stray "—") are dropped, keeping original↔normalized aligned one-to-one.
    """
    pairs = []
    for raw in text.split():
        norm = _normalize(raw)
        if norm:
            pairs.append((raw, norm.split()[0]))  # collapse the rare "a/b"→"a b" split
    return pairs


def _aliases_for(wake_word: str) -> set[str]:
    if wake_word == DEFAULT_WAKE_WORD:
        return _JARVIS_ALIASES
    # Custom wake word: we have no curated mishearing list, so rely on the literal word
    # plus the fuzzy ratio below.
    return {wake_word}


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _is_wake_token(token: str, wake_word: str, aliases: set[str], threshold: float) -> bool:
    return (
        token == wake_word
        or token in aliases
        or _ratio(token, wake_word) >= threshold
    )


def match_wake_word(
    text: str,
    wake_word: str | None = None,
    threshold: float | None = None,
    max_scan: int = 3,
) -> tuple[bool, str]:
    """Detect the wake word near the start of `text`, tolerating Whisper mishearings.

    Pure function — no audio, no globals beyond env defaults. Easy to unit-test.

    Returns (matched, command):
      • matched  — True if the wake word (or a known/fuzzy variant) was found in the first
                   `max_scan` words (after skipping leading fillers like "hey"/"ei").
      • command  — everything AFTER the wake word, in the ORIGINAL casing/accents. It is ""
                   when the user said only the wake word (e.g. just "Jarvis"); the caller
                   should then prompt and listen again for the actual command.
    """
    wake_word = _normalize(wake_word if wake_word is not None else _env_wake_word()) \
        or DEFAULT_WAKE_WORD
    if threshold is None:
        threshold = _env_threshold()
    aliases = _aliases_for(wake_word)

    pairs = _tokenize(text)
    if not pairs:
        return False, ""
    norms = [n for _, n in pairs]

    # Skip a few leading filler words ("hey", "ok", "ei", "o"...).
    i = 0
    while i < len(norms) and i < max_scan and norms[i] in _FILLERS:
        i += 1

    limit = min(len(norms), i + max_scan)
    while i < limit:
        # Single-token match: "jarvis ...".
        if _is_wake_token(norms[i], wake_word, aliases, threshold):
            return True, _join_command(pairs[i + 1:])
        # Split-token match: Whisper sometimes writes "jar vis" / "jar this" / "char vis".
        if i + 1 < len(norms):
            joined = norms[i] + norms[i + 1]
            if _is_wake_token(joined, wake_word, aliases, threshold):
                return True, _join_command(pairs[i + 2:])
        i += 1

    return False, ""


def _join_command(pairs: list[tuple[str, str]]) -> str:
    """Re-join the trailing ORIGINAL tokens and tidy leading punctuation/separators."""
    command = " ".join(raw for raw, _ in pairs)
    return command.strip(" ,.;:!?-–—…").strip()


# ----------------------------------------------------------------------------------
#  ENV CONFIG HELPERS
# ----------------------------------------------------------------------------------

def _env_wake_word() -> str:
    return (os.getenv("JARVIS_WAKE_WORD") or DEFAULT_WAKE_WORD).strip().lower() or DEFAULT_WAKE_WORD


def _env_threshold() -> float:
    try:
        return float(os.getenv("JARVIS_WAKE_THRESHOLD", DEFAULT_THRESHOLD))
    except ValueError:
        return DEFAULT_THRESHOLD


def _env_followup_secs() -> float:
    try:
        return max(0.0, float(os.getenv("JARVIS_WAKE_FOLLOWUP_SECS", "0")))
    except ValueError:
        return 0.0


# ----------------------------------------------------------------------------------
#  THE WAKE LOOP  (audio + brain + mouth — the runtime side)
# ----------------------------------------------------------------------------------

# Acknowledgements when the user says ONLY the wake word, per language.
_ACK = {"en": "Yes?", "pt": "Pois não?"}
# Recalibrate the ambient-noise threshold every N idle (no-speech) cycles, so the loop
# adapts to the room without paying the ~0.6s calibration cost on every iteration.
_RECALIBRATE_EVERY = 12
# Each listen window before we loop again and (occasionally) recalibrate. Kept short so
# Ctrl+C is responsive and so a long silence doesn't hold one stream open forever.
_WATCH_SECONDS = 20


def run_wake_loop(brain=None) -> None:
    """Run Jarvis in wake-word mode until a goodbye phrase or Ctrl+C.

    Reuses jarvis.py's helpers (logging, language guess, goodbye words, local-brain
    fallback) so behaviour stays identical to the other modes. Imported lazily to avoid a
    circular import (jarvis imports wake).
    """
    import jarvis  # lazy: avoids wake<->jarvis import cycle at module load
    from ears import listen_continuous, _calibrate_noise
    from brain import Brain, BrainOffline
    from mouth import speak, is_speaking

    wake_word = _env_wake_word()
    followup = _env_followup_secs()
    brain = brain or Brain()
    get_local = _local_getter(jarvis)  # memoized ONCE → probe Ollama at most once per session
    session = []  # (role, lang, text) turns, for end-of-session memory consolidation

    print("\n========================================")
    print(f"  JARVIS wake-word mode. Say '{wake_word.capitalize()} ...' to talk to me.")
    print("  Say 'goodbye' / 'tchau' (after the wake word) or press Ctrl+C to exit.")
    print("  Headphones recommended so I don't hear my own voice.")
    print("========================================")
    speak(jarvis.GREETING["en"], "en")

    # Calibrate the room ONCE up front; refresh occasionally during idle cycles.
    threshold = _calibrate_noise()
    idle_cycles = 0

    try:
        while True:
            # ---- 1. Watch for the wake word (low-power, VAD-gated) -------------------
            heard, lang = listen_continuous(
                silence_ms=700, max_seconds=_WATCH_SECONDS, threshold=threshold
            )
            if not heard:
                idle_cycles += 1
                if idle_cycles >= _RECALIBRATE_EVERY:
                    threshold = _calibrate_noise()
                    idle_cycles = 0
                time.sleep(0.05)  # tiny yield; keeps CPU/battery cool between windows
                continue
            idle_cycles = 0

            matched, command = match_wake_word(heard, wake_word=wake_word)
            if not matched:
                # Heard speech, but it wasn't addressed to Jarvis — ignore it silently.
                continue

            print(f"\n👂 Wake word detected in: {heard!r}")

            # ---- 2. Get the command (same utterance, or a follow-up turn) -----------
            if not command:
                speak(_ACK.get(lang, _ACK["en"]), lang)
                _drain_after_speaking()
                command, lang = listen_continuous(
                    silence_ms=800, max_seconds=20, threshold=threshold
                )
                if not command:
                    continue

            # ---- 3. Process the turn (one full conversation, then back to watching) --
            keep_going = _handle_turn(command, lang, brain, jarvis, speak,
                                      BrainOffline, get_local, session)
            if not keep_going:
                break

            # ---- 4. Optional hands-free follow-up window (no wake word needed) -------
            while keep_going and followup > 0:
                _drain_after_speaking()
                command, lang = listen_continuous(
                    silence_ms=800, max_seconds=int(followup) or 1, threshold=threshold
                )
                if not command:
                    break  # silence → go back to watching for the wake word
                if match_wake_word(command, wake_word=wake_word)[0]:
                    # They re-addressed me; strip the wake word and treat as a fresh command.
                    _m, command = match_wake_word(command, wake_word=wake_word)
                    if not command:
                        continue
                keep_going = _handle_turn(command, lang, brain, jarvis, speak,
                                          BrainOffline, get_local, session)
            if not keep_going:
                break  # a goodbye during the follow-up window must exit too
    finally:
        jarvis._consolidate_on_exit(session)  # wake mode learns like the other modes


def _handle_turn(text, lang, brain, jarvis, speak, BrainOffline, get_local, session) -> bool:
    """Run one user turn through brain→mouth. Returns False if the user said goodbye.
    Appends the turn to `session` so wake mode consolidates memory like the other modes."""
    print(f"🗣️  You [{lang}]: {text}")
    jarvis._log("you", lang, text)
    session.append(("you", lang, text))

    if jarvis._is_goodbye(text):
        speak(jarvis.BYE.get(lang, jarvis.BYE["en"]), lang)
        return False

    try:
        reply = brain.think(text)
    except BrainOffline:
        local = get_local()
        if local:
            print("   (cloud brain offline — using local Ollama brain)")
            reply = local.think(text, language=lang)
        else:
            reply = ("I can't reach my main brain and have no offline brain set up yet."
                     if lang == "en" else
                     "Não consigo acessar meu cérebro principal e ainda não tenho um offline.")

    print(f"🤖 Jarvis: {reply}")
    jarvis._log("jarvis", lang, reply)
    session.append(("jarvis", lang, reply))
    speak(reply, jarvis._speak_lang(reply, lang))  # reply language; blocking so mic can't catch our TTS
    return True


def _local_getter(jarvis):
    """Memoize the optional local brain so we probe Ollama at most once."""
    cache = {"lb": None, "tried": False}

    def get():
        if not cache["tried"]:
            cache["lb"] = jarvis._maybe_local_brain()
            cache["tried"] = True
        return cache["lb"]

    return get


def _drain_after_speaking() -> None:
    """Let the mic settle after TTS so the tail of our own voice isn't captured."""
    from mouth import is_speaking
    while is_speaking():           # defensive: speak() is blocking, so normally a no-op
        time.sleep(0.05)
    time.sleep(0.25)               # discard the acoustic tail before re-opening the mic


# ----------------------------------------------------------------------------------
#  SELF-TEST  (python wake.py --selftest)  — runs the pure matcher, no mic needed
# ----------------------------------------------------------------------------------

# (input_text, expect_match, expect_command). Command compared case-insensitively.
_TEST_CASES = [
    # plain hits
    ("Jarvis, what time is it?",            True,  "what time is it"),
    ("jarvis open safari",                  True,  "open safari"),
    ("Jarvis.",                             True,  ""),               # wake word only
    ("Jarvis",                              True,  ""),
    # leading fillers
    ("Hey Jarvis, play some music",         True,  "play some music"),
    ("ok jarvis what's the weather",        True,  "what's the weather"),
    ("Ei Jarvis, que horas são?",           True,  "que horas são"),  # PT, accents kept
    # Whisper mishearings (fuzzy)
    ("Jarvez, lock the screen",             True,  "lock the screen"),
    ("Jarbis open mail",                    True,  "open mail"),
    ("Járvis, abre o navegador",            True,  "abre o navegador"),
    ("Jervis what's up",                    True,  "what's up"),
    ("Harvis turn off the lights",          True,  "turn off the lights"),
    # Whisper mishearings (explicit alias list — too far for fuzzy)
    ("Service, set a timer",                True,  "set a timer"),
    ("Travis, remind me at five",           True,  "remind me at five"),
    # split-token mishearing
    ("Jar vis, what's the date",            True,  "what's the date"),
    # no wake word → ignored
    ("what time is it",                     False, ""),
    ("open safari please",                  False, ""),
    ("I love marvelous java drivers",       False, ""),   # near-miss words must NOT fire
    ("",                                    False, ""),
    ("is it raining",                       False, ""),   # 'is' ratio 0.5 < 0.75
    # wake word too deep in the sentence → ignored (must address Jarvis up front)
    ("please could you ask jarvis to help", False, ""),
]


def _run_selftest() -> int:
    failures = 0
    for text, want_match, want_cmd in _TEST_CASES:
        got_match, got_cmd = match_wake_word(text)
        ok = (got_match == want_match) and (
            not want_match or got_cmd.lower() == want_cmd.lower()
        )
        flag = "ok  " if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"  [{flag}] {text!r:48s} -> match={got_match} cmd={got_cmd!r}")
    print(f"\n{len(_TEST_CASES) - failures}/{len(_TEST_CASES)} passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv[1:]:
        raise SystemExit(_run_selftest())
    run_wake_loop()


# ----------------------------------------------------------------------------------
#  WHY NOT openWakeWord?
#  ------------------------------------------------------------------------------
#  openWakeWord is excellent and ships a pretrained "hey jarvis" model, and it IS
#  pip-installable on Python 3.9 / arm64:
#       pip install openwakeword onnxruntime
#  It runs a tiny melspectrogram + DNN per 80ms frame (far cheaper than Whisper) so
#  it's the right tool if you want *truly* always-on detection on battery.
#
#  We default to the Whisper-reuse approach above because, for THIS project, it:
#    • adds ZERO new dependencies (reuses ears.py exactly), and downloads no new model;
#    • makes the wake word fully configurable via JARVIS_WAKE_WORD (openWakeWord only
#      detects the specific phrases it was trained on, and its bundled model is the
#      English "hey jarvis", not a bare bilingual "Jarvis");
#    • already gives us the transcript we need for the command in the same breath.
#  The cost is higher idle CPU than openWakeWord. If battery life becomes the priority,
#  swap step 1 of run_wake_loop() for an openWakeWord detector and keep everything else.
# ----------------------------------------------------------------------------------
