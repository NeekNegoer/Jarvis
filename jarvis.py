"""
jarvis.py — your Jarvis. Run it:  python jarvis.py

The loop:
  1. ears   — listen to what you say (in Portuguese or English)
  2. brain  — Claude (your Max plan) figures out a reply, using computer tools if asked
  3. mouth  — Jarvis says it back, in the language you spoke
Repeat until you say "goodbye" / "tchau" (or press Ctrl+C).

If the Max-plan brain can't be reached (no internet), Jarvis falls back to the local
Ollama brain when it's available, so it keeps working offline.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from ears import listen, listen_continuous
from brain import Brain, BrainOffline
from mouth import speak

LOG_DIR = Path(__file__).parent / "logs"


def _log(role: str, lang: str, text: str) -> None:
    """Append a turn to today's conversation log. Best-effort; never breaks the loop."""
    try:
        LOG_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d")
        with open(LOG_DIR / f"conversation-{stamp}.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} [{lang}] {role}: {text}\n")
    except Exception:
        pass

# Words that end the session, in both languages.
GOODBYE_WORDS = ("goodbye", "bye jarvis", "shut down", "go to sleep",
                 "tchau", "até logo", "desligar", "vai dormir", "bye", "adeus")

GREETING = {"en": "Jarvis online. How can I help?",
            "pt": "Jarvis online. Como posso ajudar?"}
BYE = {"en": "Goodbye. Talk soon.", "pt": "Tchau. Até logo."}
MISSED = {"en": "Sorry, I didn't catch that.", "pt": "Desculpa, não entendi."}


def _is_goodbye(text: str) -> bool:
    """True only if the utterance IS a goodbye — not merely contains one. Prevents
    accidental exits like 'don't shut down the server' or 'a story to help me go to sleep'."""
    import re
    norm = re.sub(r"[^\w\s]", "", text.lower()).strip()
    if not norm:
        return False
    if norm in GOODBYE_WORDS:                       # exact short utterance
        return True
    # For very short utterances, allow a leading filler ("ok goodbye", "tá tchau").
    if len(norm.split()) <= 3:
        return any(re.search(rf"\b{re.escape(w)}\b", norm) for w in GOODBYE_WORDS)
    return False


# High-signal Portuguese tokens that are rare/absent in English (used for whole-word match).
_PT_WORDS = {
    "você", "voce", "não", "nao", "está", "esta", "sim", "claro", "certo", "obrigada",
    "obrigado", "oi", "olá", "ola", "tchau", "abra", "abrir", "qual", "quais", "faça",
    "faca", "fazer", "que", "uma", "um", "meu", "minha", "seu", "sua", "hoje", "agora",
    "porque", "quero", "preciso", "também", "tambem", "para", "como", "quando", "onde",
    "quem", "isso", "aqui", "muito", "horas", "bom", "dia", "noite", "tarde", "por",
    "favor", "coisa", "ele", "ela", "nós", "nos", "são", "sao",
}


# Common English function words — a positive "this is English" signal for voice selection.
_EN_WORDS = {
    "the", "is", "are", "you", "what", "how", "i", "to", "of", "and", "it", "that",
    "this", "your", "ok", "okay", "yes", "no", "sure", "done", "here", "time", "now",
    "open", "the", "a", "an", "on", "for", "with", "can", "will", "got", "let", "me",
}


def _guess_language(text: str) -> str:
    """Cheap pt/en guess. Used to pick the speaking voice; prefer guessing from the text
    that will actually be SPOKEN (the reply), which carries Portuguese accents."""
    t = text.lower()
    if any(c in t for c in "ãõçáéíóúâêôàü"):
        return "pt"
    words = set(__import__("re").findall(r"[a-zà-ú]+", t))
    return "pt" if len(words & _PT_WORDS) >= 1 else "en"


def _speak_lang(reply: str, fallback: str = "en") -> str:
    """Pick the TTS voice language for `reply`. Prefer the reply's own language (it carries
    accents), but when the reply has no clear pt OR en signal (e.g. a short 'Pronto.'), use
    the known input language instead of blindly defaulting to English."""
    t = reply.lower()
    if any(c in t for c in "ãõçáéíóúâêôàü"):
        return "pt"
    words = set(__import__("re").findall(r"[a-zà-ú]+", t))
    if words & _PT_WORDS:
        return "pt"
    if words & _EN_WORDS:
        return "en"
    return fallback


def run_text_mode():
    """Type to Jarvis instead of speaking. Replies are printed and spoken. Great for
    testing the brain + tools + memory before granting mic/screen permissions."""
    brain = Brain()
    session = []  # (role, lang, text) turns, for end-of-session memory consolidation
    print("\n💬 Jarvis text mode. Type a message (Portuguese or English).")
    print("   Replies are printed and spoken. Ctrl+C or 'goodbye'/'tchau' to exit.\n")
    try:
        while True:
            try:
                you_said = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not you_said:
                continue
            lang = _guess_language(you_said)
            session.append(("you", lang, you_said))
            if _is_goodbye(you_said):
                print("jarvis>", BYE.get(lang, BYE["en"]))
                speak(BYE.get(lang, BYE["en"]), lang)
                return
            _log("you", lang, you_said)
            try:
                reply = brain.think(you_said)
            except BrainOffline:
                lb = _maybe_local_brain()
                reply = lb.think(you_said, language=lang) if lb else MISSED[lang]
            print("jarvis>", reply, "\n")
            _log("jarvis", lang, reply)
            session.append(("jarvis", lang, reply))
            speak(reply, _speak_lang(reply, lang))  # reply language, fallback to input
    finally:
        _consolidate_on_exit(session)


def _computer_use_status():
    """('ready' | 'partial' | 'off', message). Tells if Jarvis can control the Mac yet."""
    try:
        import computer
        acc, scr = computer.has_accessibility(), computer.has_screen_recording()
    except Exception:
        return "off", ""
    if acc and scr:
        return "ready", ""
    missing = []
    if not scr:
        missing.append("Screen Recording")
    if not acc:
        missing.append("Accessibility")
    return "partial", (f"Heads up: I can't see or control the screen yet — {', '.join(missing)} "
                       f"permission is missing. Run python doctor.py to fix it.")


def _maybe_local_brain():
    """Return a local Ollama brain if available, else None."""
    try:
        from local_brain import LocalBrain
        lb = LocalBrain()
        if lb.available():
            return lb
    except Exception:
        pass
    return None


def _consolidate_on_exit(session):
    """At session end, let Jarvis reflect and save durable facts about Pietro.
    Runs in a daemon thread with a hard time budget so it can NEVER hang shutdown
    (the underlying brain call could otherwise take up to ~90s). The memory file is
    written in one atomic block, so abandoning a slow thread can't corrupt it."""
    if not session:
        return
    import threading
    result = {}

    def _work():
        try:
            from memory_consolidate import consolidate
            result["saved"] = consolidate(session)
        except Exception:
            pass

    print("   🧠 saving what I learned…", flush=True)
    t = threading.Thread(target=_work, daemon=True)
    t.start()
    t.join(timeout=25)  # give up (but let it finish in the background) past this
    saved = result.get("saved")
    if saved:
        n = len(saved)
        print(f"   🧠 (remembered {n} new thing{'s' if n != 1 else ''} about you)")


def main(hands_free: bool = False):
    brain = Brain()
    local = None  # lazily created only if the cloud brain fails
    session = []  # (role, lang, text) turns, for end-of-session memory consolidation
    listen_fn = listen_continuous if hands_free else listen
    print("\n========================================")
    print("  JARVIS is online. Say 'goodbye' / 'tchau' to exit.")
    if hands_free:
        print("  Hands-free mode: just start talking (headphones recommended).")
    else:
        print("  Push-to-talk: Enter to start, Enter to send.")
    print("========================================")
    speak(GREETING["en"], "en")

    status, msg = _computer_use_status()
    if status == "partial":
        print(f"⚠️  {msg}")
        speak(msg, "en")

    try:
        while True:
            you_said, lang = listen_fn()

            if not you_said:
                print("   (didn't catch that)")
                continue

            print(f"\n🗣️  You [{lang}]: {you_said}")
            _log("you", lang, you_said)
            session.append(("you", lang, you_said))

            if _is_goodbye(you_said):
                speak(BYE.get(lang, BYE["en"]), lang)
                break

            try:
                reply = brain.think(you_said)
            except BrainOffline:
                local = local or _maybe_local_brain()
                if local:
                    print("   (cloud brain offline — using local Ollama brain)")
                    reply = local.think(you_said, language=lang)
                else:
                    reply = ("I can't reach my main brain and have no offline brain set up yet."
                             if lang == "en" else
                             "Não consigo acessar meu cérebro principal e ainda não tenho um offline.")

            print(f"🤖 Jarvis: {reply}")
            _log("jarvis", lang, reply)
            session.append(("jarvis", lang, reply))
            speak(reply, _speak_lang(reply, lang))  # reply language, fallback to input
    finally:
        _consolidate_on_exit(session)


if __name__ == "__main__":
    args = sys.argv[1:]
    try:
        if any(a in ("--text", "-t") for a in args):
            run_text_mode()
        elif any(a in ("--wake", "-w") for a in args):
            from wake import run_wake_loop
            run_wake_loop()
        else:
            hands_free = any(a in ("--hands-free", "-c", "--continuous") for a in args)
            main(hands_free=hands_free)
    except KeyboardInterrupt:
        print("\nJarvis shutting down.")
