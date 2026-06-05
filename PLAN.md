# Jarvis — Master Plan

> A personal, system-wide, bilingual (pt-BR / English) voice assistant for macOS,
> powered by your **Claude Max plan** (no API key) with the ability to control your
> whole computer (screenshots, clicking, typing, app control), plus an optional
> **offline brain** via Ollama.

This document is the source of truth for what Jarvis is and where it's going.
`CHECKPOINTS.md` is the running log of what got done each work session.
`TODO_TOMORROW.md` is the short list of things that need *you* (the human) — mostly
one-time permission grants that need your hands on System Settings.

---

## The core idea

```
        ┌─────────┐      ┌──────────┐      ┌──────────┐
 you ─▶ │  EARS   │ ─▶   │  BRAIN   │ ─▶   │  MOUTH   │ ─▶ you
 (mic)  │ Whisper │      │ Claude   │      │ macOS    │  (speakers)
        │ pt+en   │      │ Max plan │      │  say     │
        └─────────┘      └────┬─────┘      └──────────┘
                              │ uses tools
                         ┌────▼─────────┐
                         │ COMPUTER USE │  screenshot · click · type ·
                         │ (whole Mac)  │  keys · accessibility tree · open app
                         └──────────────┘
```

- **Ears** (`ears.py`): local `faster-whisper`, multilingual, auto-detects whether
  you spoke Portuguese or English and returns both the text and the language.
- **Brain** (`brain.py`): shells out to the `claude` CLI in headless mode
  (`claude -p ... --output-format json`). This uses your **Max plan
  subscription**, so **no `ANTHROPIC_API_KEY` is needed**. Conversation continuity
  is kept via the returned `session_id` + `--resume`.
- **Mouth** (`mouth.py`): macOS `say`, picks the voice by language
  (Luciana for pt-BR, Daniel for English), strips markdown so nothing weird gets
  read aloud.
- **Computer use** (`computer.py` + `computer_use_server.py`): lets the brain
  control the entire Mac — not one app, the whole system. Exposed two ways for
  robustness: a plain CLI (`python computer.py screenshot`) that Claude can call
  via its Bash tool, and an MCP server so screenshots come back inline as images.
- **Local brain** (`local_brain.py`, optional): Ollama running a small model for
  offline / no-network use.

## Why the `claude` CLI instead of the Anthropic API

The user has a **Claude Max plan but no API key and no plan to get one**. The
`claude` CLI authenticates with the Max subscription, and its headless `-p` mode
returns completions the same way an API call would — including tool use, MCP, and
file reading. So the brain is "Claude Code, scripted." Bonus: we get a
full agent (tool use, vision on screenshots) for free.

## Design principles

1. **Whole-system, not per-app.** One computer-use layer that works in any app via
   screen pixels + the macOS Accessibility API. No per-app integrations.
2. **No API key, ever.** Everything routes through the Max plan or runs locally.
3. **Bilingual by default.** Detect the spoken language each turn; reply and speak
   in that language.
4. **Safe by default.** Destructive/irreversible actions get a spoken confirmation
   first. (See computer-use guardrails.)
5. **Degrade gracefully.** If the network/Max plan is unavailable, fall back to the
   local Ollama brain. If accessibility isn't granted yet, still do everything that
   doesn't need it and say what's blocked.
6. **One file per concern.** Swapping Whisper for something else, or `say` for
   ElevenLabs, should touch exactly one file.

## Roadmap / milestones

- [x] M0 — Audit existing scaffold, confirm Max-plan brain works headless.
- [ ] M1 — Bilingual voice loop on the Max plan (brain/ears/mouth rewrite).
- [ ] M2 — System-wide computer use wired into the brain.
- [ ] M3 — Ollama offline brain.
- [ ] M4 — Polish: continuous listening, guardrails, README, install script, tests.

See `CHECKPOINTS.md` for detailed progress.
