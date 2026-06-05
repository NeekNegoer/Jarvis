# Jarvis 🤖🎙️

Your personal, **bilingual** (🇧🇷 Português / 🇺🇸 English) voice assistant for the Mac —
powered by your **Claude Max plan** (no API key), able to **control your whole computer**
by voice, with an optional **offline brain** for when you have no internet.

Talk to it. It listens in Portuguese or English, thinks with Claude, and talks back in the
same language. Ask it to *do* things — open apps, click buttons, type, read your screen,
script Mail/Calendar/Notes — and it actually does them.

---

## Quick start

```bash
# 1. Set up (one time). No admin/sudo needed.
bash install.sh            # add --ollama to also set up the offline brain

# 2. Check what's ready and what needs a tap from you:
source .venv/bin/activate
python doctor.py

# 3. Talk (or type):
python server.py           # ⭐ the browser UI — opens Chrome; talk OR type, neural voices
python jarvis.py            # voice, push-to-talk (Terminal)
python jarvis.py --text     # type instead of talk (works before granting any permissions)
python jarvis.py --hands-free   # just talk, no key presses (headphones recommended)
python jarvis.py --wake         # ambient: just say "Jarvis ..." (headphones recommended)
python hotkey.py                # talk from ANYWHERE: hold Right-Option ⌥ (needs Input Monitoring)
```

> **Easiest way in:** `python server.py` opens `http://127.0.0.1:8765` where you can talk
> *or* type. Speech in and out run **inside Chrome** (Google's neural voices, no headphone
> fuss; the mic prompt goes to Chrome). Toggles for language, Mac control, and **new** chat.
> From Raycast it's the **"Open Jarvis"** command.

Push-to-talk (Terminal): press **Enter** to start talking, **Enter** again to send. Say
**“goodbye”** or **“tchau”** to exit. That's it.

> New here? Start with `python jarvis.py --text` — it exercises the brain, computer tools
> and memory by typing, so you can confirm everything works *before* touching permissions.

### Summon it from Raycast 🪄
Jarvis ships **Raycast** commands — **Open Jarvis** (the browser UI), **Talk to Jarvis**
(hands-free), **Ask Jarvis** (type → spoken answer), and **Stop Jarvis**. Add the
[`raycast/`](raycast/) folder as a Script Directory in Raycast settings — see
[raycast/README.md](raycast/README.md). **Open Jarvis** is the everyday way in.

## What it needs from you (one time, no admin)

Three macOS permission toggles in **System Settings → Privacy & Security**. `doctor.py`
tells you exactly which are still missing. Grant them to **the app you launch Jarvis from**
(your terminal, or VS Code):

| Permission | Why | Where |
|---|---|---|
| 🎙️ Microphone | so Jarvis can hear you | Privacy & Security → Microphone |
| 📸 Screen & System Audio Recording | so Jarvis can see your screen | …→ Screen Recording *(restart the app after)* |
| ♿ Accessibility | so Jarvis can click & type for you | …→ Accessibility |

> Tip: `python computer.py request_permissions` pops the system prompts for you.

## How it works

```
  you ──▶  EARS  ──▶  BRAIN  ──▶  MOUTH  ──▶ you
 (mic)   Whisper    Claude Max     say
         pt + en     plan        pt / en
                       │ uses tools
                  COMPUTER USE (whole Mac)
        screenshot · click · type · keys · accessibility · open app · AppleScript
```

- **Brain** — shells out to the `claude` CLI on your **Max plan**, so there's **no API key**
  and nothing extra to pay. It's the full Claude agent, so it can use tools and see screenshots.
- **Ears** — local Whisper (`mlx-whisper`, Metal-accelerated on Apple Silicon), auto-detects
  Portuguese vs English each turn. Private, offline, free.
- **Mouth** — macOS `say`: **Luciana** for Portuguese, **Daniel** for English.
- **Computer use** — controls any app via screen + the macOS Accessibility API, exposed to the
  brain as MCP tools. It prefers reliable methods (AppleScript, named UI elements) over guessing
  pixels, and asks before anything destructive.
- **Offline brain** — optional local Ollama model (`qwen2.5:7b`) used automatically if the Max
  plan can't be reached.

## The files

| File | Role |
|---|---|
| `jarvis.py` | the main loop: listen → think → speak |
| `ears.py` | speech-to-text (bilingual, Metal-accelerated, with CPU fallback) |
| `brain.py` | the Claude Max-plan brain (via the `claude` CLI) |
| `mouth.py` | text-to-speech, voice chosen by language |
| `computer.py` | system-wide control: screenshot, click, type, keys, accessibility, AppleScript |
| `computer_use_server.py` | exposes `computer.py` to the brain as MCP tools (inline screenshots) |
| `mcp_config.json` | tells the brain where the computer-use tools live |
| `local_brain.py` | the offline Ollama brain |
| `server.py` + `web/` | the browser UI (localhost; talk/type in Chrome with neural voices) |
| `wake.py` | wake-word mode ("Jarvis …") + the fuzzy wake-word matcher |
| `memory_consolidate.py` | at session end, reflects and saves durable facts about you |
| `recipes.md` | reliable AppleScript recipes (mail, calendar, notes, music, browser…) |
| `raycast/` | Raycast Script Commands to summon Jarvis (see `raycast/README.md`) |
| `hotkey.py` | *(optional)* global push-to-talk — talk to Jarvis from any app |
| `Jarvis.command` | double-click in Finder to launch (auto-starts the offline brain) |
| `doctor.py` | checks deps + permissions and tells you what's left |
| `selftest.py` | fast smoke test of all the pieces (no mic/permissions needed) |
| `test_computer_use.py` | safe end-to-end proof that Jarvis can control the Mac (after granting Accessibility) |
| `install.sh` | one-shot setup (no admin) |
| `persona.md` | *(optional)* edit to change Jarvis's personality |
| `PLAN.md` · `RESEARCH.md` · `CHECKPOINTS.md` · `TODO_TOMORROW.md` | the project's brain on paper |

## Customizing

- **Personality / rules:** create `persona.md` (overrides the built-in one in `brain.py`).
- **Voices:** edit `VOICES` in `mouth.py` (`say -v '?'` lists all installed voices).
- **Speech model size/speed:** `JARVIS_WHISPER_MODEL=base|small|medium` (default `small`).
- **Offline model:** `JARVIS_OLLAMA_MODEL=qwen2.5:7b` (or any model you've pulled).
- **Wake word:** `JARVIS_WAKE_WORD=jarvis`, `JARVIS_WAKE_THRESHOLD=0.75` (fuzzy match).
- **Silence/audio off:** `JARVIS_SILENT=1` (text still flows; nothing is spoken).
- **Memory:** Jarvis saves durable facts about you to `memory/about_you.md` during and at the
  end of a session — edit that file anytime to add/remove what it knows.

## Troubleshooting

- **“No reply / it hangs.”** Run `python doctor.py` — usually it's the Max-plan login
  (`claude` once interactively) or a missing permission.
- **“It can't see my screen / click.”** Screen Recording + Accessibility aren't granted yet,
  *or* you didn't restart the app after granting Screen Recording.
- **Portuguese comes out garbled.** Make sure the model isn't an English-only `.en` one
  (we use multilingual `small`); try `JARVIS_WHISPER_MODEL=medium` for tougher audio.

---

*Built to grow. See `PLAN.md` for where it's headed.*
