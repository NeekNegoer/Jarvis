"""
mouth.py — Jarvis's voice (bilingual).

Speaks text aloud with macOS's built-in `say` command — free, no setup, offline.
It picks the voice by language: **Luciana** for Brazilian Portuguese, **Samantha** for
English. It also strips markdown/symbols so nothing weird gets read out loud, and can
be interrupted (so Jarvis can stop talking when you start talking — "barge-in").

Want a much nicer (Siri-quality) voice? Download one in
System Settings → Accessibility → Spoken Content → System Voice → Manage Voices…
(look for "(Premium)" or the Siri voices), then set JARVIS_VOICE_EN / JARVIS_VOICE_PT
to its exact name (run `say -v '?'` to see installed voices). No code change needed.
"""

from __future__ import annotations

import os
import re
import subprocess

# Voice per language — override without editing code via env vars.
VOICES = {
    "pt": os.getenv("JARVIS_VOICE_PT", "Luciana"),     # Brazilian Portuguese
    "en": os.getenv("JARVIS_VOICE_EN", "Samantha"),    # English (nicer than Daniel)
}
DEFAULT_VOICE = VOICES["en"]
RATE = int(os.getenv("JARVIS_VOICE_RATE", "178"))  # words per minute (a touch calmer than 190)
# Set JARVIS_SILENT=1 to suppress audio (text still flows) — handy for testing or quiet rooms.
SILENT = os.getenv("JARVIS_SILENT", "").strip() in ("1", "true", "yes")

_current: subprocess.Popen | None = None  # the active `say` process, for barge-in


def _clean(text: str) -> str:
    """Strip markdown and symbols that shouldn't be read aloud."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)   # code fences
    text = re.sub(r"`([^`]*)`", r"\1", text)                  # inline code
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)            # bold
    text = re.sub(r"\*([^*]*)\*", r"\1", text)                # italics
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)    # headings
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)  # bullets
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)      # [text](url) -> text
    text = re.sub(r"https?://\S+", "", text)                  # bare urls
    return re.sub(r"\s+", " ", text).strip()


def speak(text: str, language: str = "en", block: bool = True) -> None:
    """Say `text` aloud in the given language ('pt' or 'en')."""
    text = _clean(text)
    if not text or SILENT:
        return
    stop()  # never talk over ourselves
    voice = VOICES.get(language, DEFAULT_VOICE)
    cmd = ["say", "-r", str(RATE), "-v", voice, text]

    global _current
    if block:
        subprocess.run(cmd)
        _current = None
    else:
        _current = subprocess.Popen(cmd)


def stop() -> None:
    """Stop Jarvis mid-sentence (used for barge-in when the user starts talking)."""
    global _current
    if _current and _current.poll() is None:
        _current.terminate()
    _current = None


def is_speaking() -> bool:
    return _current is not None and _current.poll() is None


if __name__ == "__main__":
    speak("Hello Pietro, I am Jarvis. Your assistant is online.", "en")
    speak("Olá Pietro, eu sou o Jarvis. Seu assistente está online.", "pt")
