"""
doctor.py — Jarvis's pre-flight check. Run it any time:  python doctor.py

It tells you, in plain language, exactly what's working and what still needs a tap
from you (the permission toggles only you can flip). Nothing here needs admin/sudo.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

GREEN, RED, YEL, DIM, BOLD, END = "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[1m", "\033[0m"
OK, NO, MEH = f"{GREEN}✅{END}", f"{RED}❌{END}", f"{YEL}⚠️ {END}"

problems: list[str] = []


def line(status, label, detail=""):
    print(f"  {status}  {label}" + (f"  {DIM}{detail}{END}" if detail else ""))


def check_python_deps():
    print(f"\n{BOLD}Python packages{END}")
    deps = {
        "sounddevice": "microphone recording",
        "numpy": "audio buffers",
        "scipy": "wav handling",
        "Quartz": "screenshots + mouse/keyboard",
        "ApplicationServices": "accessibility (find buttons)",
        "AppKit": "frontmost app",
        "PIL": "screenshot images",
    }
    for mod, why in deps.items():
        try:
            __import__(mod)
            line(OK, mod, why)
        except Exception as e:
            line(NO, mod, f"{why} — MISSING ({e})")
            problems.append(f"Install Python deps:  pip install -r requirements.txt  (missing {mod})")
    # STT backend
    try:
        import mlx_whisper  # noqa: F401
        line(OK, "mlx-whisper", "fast Metal speech-to-text (preferred)")
    except Exception:
        try:
            import faster_whisper  # noqa: F401
            line(MEH, "faster-whisper", "CPU speech-to-text (works, slower; mlx-whisper recommended)")
        except Exception:
            line(NO, "speech-to-text", "no STT backend — pip install mlx-whisper")
            problems.append("Install a speech backend:  pip install mlx-whisper")


def check_brain():
    print(f"\n{BOLD}Brain (Claude Max plan){END}")
    claude = shutil.which("claude")
    if not claude:
        line(NO, "claude CLI", "not found — install Claude Code and log in with your Max plan")
        problems.append("Install Claude Code (https://claude.com/claude-code) and run `claude` once to log in.")
        return
    line(OK, "claude CLI", claude)
    try:
        r = subprocess.run([claude, "-p", "reply with OK", "--output-format", "json"],
                           capture_output=True, text=True, timeout=60)
        import json
        ok = r.returncode == 0 and not json.loads(r.stdout or "{}").get("is_error")
        line(OK if ok else NO, "Max-plan login", "a live reply came back" if ok else "the CLI errored — run `claude` and check you're logged in")
        if not ok:
            problems.append("Log in to Claude Code: run `claude` interactively once.")
    except Exception as e:
        line(MEH, "Max-plan login", f"couldn't verify ({e}) — check your internet / login")


def check_voices():
    print(f"\n{BOLD}Voices (text-to-speech){END}")
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
        for v, lang in (("Luciana", "Brazilian Portuguese"), ("Daniel", "English")):
            line(OK if v in out else MEH, v, f"{lang} voice" + ("" if v in out else " — not installed; pick another in mouth.py"))
    except Exception as e:
        line(NO, "say", f"macOS text-to-speech unavailable ({e})")


def check_permissions():
    print(f"\n{BOLD}macOS permissions{END}  {DIM}(System Settings → Privacy & Security){END}")
    # Accessibility + Screen Recording
    try:
        import computer
        acc = computer.has_accessibility()
        scr = computer.has_screen_recording()
        line(OK if acc else NO, "Accessibility", "Jarvis can click & type" if acc else
             "needed to click/type — enable your terminal/IDE in Privacy & Security → Accessibility")
        line(OK if scr else NO, "Screen Recording", "Jarvis can see your screen" if scr else
             "needed for screenshots — enable in Privacy & Security → Screen & System Audio Recording, then RESTART the app")
        if not acc:
            problems.append("Grant Accessibility to the app you launch Jarvis from (Privacy & Security → Accessibility).")
        if not scr:
            problems.append("Grant Screen Recording, then fully quit & reopen the app (Privacy & Security → Screen & System Audio Recording).")
    except Exception as e:
        line(MEH, "Accessibility/Screen", f"couldn't check ({e})")
    # Microphone
    try:
        import AVFoundation
        st = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(AVFoundation.AVMediaTypeAudio)
        # 0 notDetermined, 1 restricted, 2 denied, 3 authorized
        if st == 3:
            line(OK, "Microphone", "Jarvis can hear you")
        elif st == 0:
            line(MEH, "Microphone", "not requested yet — it'll ask the first time you run Jarvis")
        else:
            line(NO, "Microphone", "denied — enable in Privacy & Security → Microphone")
            problems.append("Grant Microphone access (Privacy & Security → Microphone).")
    except Exception:
        line(MEH, "Microphone", "couldn't check; it'll prompt on first run")


def check_ollama():
    print(f"\n{BOLD}Offline brain (Ollama — optional){END}")
    if not shutil.which("ollama"):
        line(MEH, "ollama", "not installed (optional) — only needed for offline use")
        return
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        models = [l.split()[0] for l in r.stdout.strip().splitlines()[1:] if l.strip()]
        line(OK if models else MEH, "ollama", f"models: {', '.join(models)}" if models else "installed, no models pulled yet")
    except Exception as e:
        line(MEH, "ollama", f"installed but not running ({e})")


def main():
    print(f"{BOLD}🩺 Jarvis doctor{END} — checking your setup...")
    check_python_deps()
    check_brain()
    check_voices()
    check_permissions()
    check_ollama()

    print(f"\n{BOLD}{'='*50}{END}")
    if not problems:
        print(f"{GREEN}{BOLD}All systems go. Run:  python jarvis.py{END}\n")
        return 0
    print(f"{YEL}{BOLD}A few things need you (no admin needed):{END}")
    for i, p in enumerate(problems, 1):
        print(f"  {i}. {p}")
    print(f"\n{DIM}Tip: run  python computer.py request_permissions  to pop the system prompts.{END}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
