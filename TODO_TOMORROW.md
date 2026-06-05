# Good morning, Pietro ☀️

I worked through the night. **Jarvis is built and working** — bilingual voice, the Claude
Max-plan brain, full system-wide computer control, and an offline brain. Everything that
didn't need *you* is done and tested.

Here's the short list that needs your hands (none need a password/admin). Should take ~2 min.

---

## ✅ What's already working (no action needed)
- Talks & listens in **Portuguese and English**, auto-detecting which you spoke.
- Brain runs on your **Max plan** — no API key, nothing to pay per use.
- Fast local speech recognition (mlx-whisper, Metal) — ~0.3s per phrase.
- Can control the whole Mac (screenshot, click, type, keys, open apps, AppleScript) —
  *once you grant the permissions below.*
- Offline brain (Ollama + qwen2.5:7b) auto-used if the internet/Max plan is down.

## 🔴 Step 1 — Grant the permissions (the only must-do)  ⬜
Open a terminal in this folder and run:
```bash
source .venv/bin/activate
python doctor.py
```
It prints a checklist. For each ❌, flip the toggle in **System Settings → Privacy &
Security**. Grant them to **the app you launch Jarvis from** (your terminal, or VS Code):

1. **Accessibility** — so it can click & type. *(still needed)*
2. **Microphone** — so it can hear you. *(will prompt automatically on first voice run)*
3. **Screen & System Audio Recording** — so it can see your screen. **✅ This already got
   granted during the build and I verified a real screenshot works** — but `doctor.py` is the
   source of truth, so just confirm it's still ✅. *(If you ever flip it, quit & reopen the app.)*

So in practice the one thing left for you is **Accessibility** (plus approving the mic prompt).
Shortcut to pop the system prompts: `python computer.py request_permissions`

**After you grant Accessibility, prove it works** with a safe self-cleaning demo (opens a
throwaway TextEdit doc, types, reads it back, closes without saving — never touches your files):
```bash
python test_computer_use.py
```
If every line is ✅, Jarvis can fully control your Mac.

## 🟡 Step 2 — Try it  ⬜
**Quickest first test (needs no permissions at all):** type to it.
```bash
python jarvis.py --text         # type in Portuguese or English; it replies & speaks
```
Then the voice modes:
```bash
python jarvis.py                # push-to-talk: Enter to start/stop talking
python jarvis.py --hands-free   # just talk (use headphones so it doesn't hear itself)
```
Say something simple first ("what time is it?" / "que horas são?"), then try a computer
task ("abra o Safari" / "open Notes and write a reminder").

## 🟢 Optional things I set up but couldn't fully finish without you
- **Offline brain (Ollama):** I installed it without admin to `~/.ollama-dist` and linked it
  at `~/.local/bin/ollama`, started the server, and pulled `qwen2.5:7b`.
  - If `python doctor.py` shows ollama with no model, just run:
    `~/.local/bin/ollama serve &` then `~/.local/bin/ollama pull qwen2.5:7b`
  - The server must be running for offline mode. Want it to auto-start at login? That's a
    one-liner LaunchAgent — say the word and I'll add it (left out to avoid surprising you).
  - I added `~/.local/bin` to PATH for Jarvis, but if `ollama` isn't found in *new* terminals,
    add `export PATH="$HOME/.local/bin:$PATH"` to your `~/.zshrc`.

## 🖥️ New: the browser UI (the nicest way to use Jarvis)  ⬜
There's now a **window** for Jarvis — talk *or* type in Chrome, with Google's natural neural
voices, no headphone fuss. Try it:
```bash
python server.py        # opens http://127.0.0.1:8765 in your browser
```
Tap the orb to talk (mic prompt goes to Chrome — allow it once), or just type. Toggles for
🇧🇷/🇺🇸 language, **Mac control** (off by default — flip on to let it click/type), and **new**
(top-right) to start fresh. If the Max plan/internet is down it falls back to the offline
brain and shows a small badge. From Raycast it's the **Open Jarvis** command.

## 🪄 Summon Jarvis from Raycast  ⬜
Add the `raycast/` folder as a Script Directory in **Raycast → Settings → Extensions →
Script Commands → Add Script Directory** → pick `/Users/pietrojustino/Documents/Jarvis/raycast`.
You'll get: **Open Jarvis** (the browser UI — best everyday way), **Talk to Jarvis** (hands-free),
**Ask Jarvis** (type a question, hear the answer — no permissions needed), and **Stop Jarvis**.
Full notes in `raycast/README.md`. (The voice ones open Terminal/Chrome, so the first run asks
to let Raycast control them — that's the only extra prompt.)

## ✅ Recently added (already done — just use them)
- **Email / calendar / notes / reminders / music / browser** — reliable AppleScript recipes
  in `recipes.md` that the brain uses (first use per app triggers a one-time Automation prompt).
- **Wake word** — `python jarvis.py --wake`, say "Jarvis …". Configurable via `JARVIS_WAKE_WORD`.
- **Memory that writes itself** — Jarvis saves durable facts about you to `memory/about_you.md`
  during chats and reflects at the end of each session to add more.
- **Silent mode** — `JARVIS_SILENT=1` to mute the voice (text still works).

## 💡 Ideas for next (my suggestions — your call)
1. **A menu-bar app** so Jarvis is always visible/one-click (Raycast + the new browser UI cover
   most of this now — a menu-bar toggle that opens the UI would be the cherry on top).
2. **Wake word without headphones** — add acoustic echo cancellation so the mic ignores
   Jarvis's own voice (today: use headphones, or it listens after it finishes speaking).
3. **Deeper skills** — multi-step flows like "triage my inbox and draft replies".

---
*Full build log in `CHECKPOINTS.md`. Architecture in `PLAN.md`. Research behind the choices
in `RESEARCH.md`. If anything's broken, `python doctor.py` is the first stop.*
