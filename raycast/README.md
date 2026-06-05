# Jarvis in Raycast

Raycast Script Commands so you can summon Jarvis with a keystroke — no Terminal windows.

## One-time setup (30 seconds)
1. Open **Raycast → Settings (⌘,) → Extensions → Script Commands**.
2. Click **Add Script Directory** and pick this folder:
   `/Users/pietrojustino/Documents/Jarvis/raycast`
3. The commands appear in Raycast. Give them hotkeys/aliases if you like.

## The commands
| Command | What it does | Needs |
|---|---|---|
| **Open Jarvis** ⭐ | Opens the **full Jarvis UI in Chrome** (starts the local server if needed). Talk *or* type, in a beautiful window with Chrome's neural voices. Best everyday way in. | Mic (only to talk) |
| **Talk to Jarvis** | Brings **Chrome** to the front and starts Jarvis **listening — just talk** (no keys, no Terminal). Runs in the background; Jarvis greets you so you know it's live. | Microphone |
| **Stop Jarvis** | Stops the listening session. | — |
| **Ask Jarvis** | Type a question into Raycast → Jarvis answers (printed + spoken). One-shot, pure chat — never touches the Mac. | — |

So your normal flow is: hit **Open Jarvis** and talk or type in the window. (Or **Talk to
Jarvis** for a hands-free background session — say *"goodbye"* / *"tchau"*, or run **Stop
Jarvis**, to end it.)

### About "Open Jarvis" (the UI)
- The UI lives at `http://127.0.0.1:8765` — localhost only, never exposed to your network.
- Speech in **and** out happen **inside Chrome**, so the mic prompt goes to **Chrome** (allow it
  once), and you get Google's natural voices for free. No headphone gymnastics — it's tap-to-talk.
- Toggles in the window: **language** (🇧🇷/🇺🇸), **Mac control** (off by default — flip it on to let
  Jarvis click/type/open apps), and **new** (top right) to start a fresh conversation.
- It quietly uses the **offline brain** if your Max plan/internet is down (a small badge tells you).

## Permissions (no admin)
- **Talk to Jarvis** listens through the mic. Because Raycast launches it, the first time you
  run it macOS asks to let **Raycast** use the **Microphone** — allow it. (If you'd rather not
  give Raycast mic access, run `python jarvis.py --hands-free` from a terminal instead; then the
  grant goes to the terminal.)
- For Jarvis to **control** the Mac (click/type), grant **Accessibility** too — `python doctor.py`
  walks you through it. **Ask Jarvis** needs nothing special.

## Notes
- "Talk to Jarvis" uses continuous (hands-free) listening. On a laptop with no headphones it can
  occasionally hear its own voice — if that happens, use headphones, or switch the command to
  wake-word mode by changing `--hands-free` to `--wake` in `talk-jarvis.sh` (then you say
  "Jarvis …" before each request).
- Change the voice without editing code: `export JARVIS_VOICE_EN="Samantha"` (or any installed
  voice; run `say -v '?'`). For Siri-quality voices, download one in System Settings →
  Accessibility → Spoken Content → Manage Voices, then set `JARVIS_VOICE_EN` to its name.
