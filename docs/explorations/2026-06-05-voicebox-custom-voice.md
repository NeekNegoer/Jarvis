# Exploration: "voicebox" — a custom trained voice for Jarvis

**Date:** 2026-06-05
**Author:** Claude (autonomous session, for Pietro's review)
**Goal (Pietro):** Give Jarvis its own voice by "training a voice model" (he calls the tool **voicebox**).
**Status:** Researched from prior knowledge only — **live web search was unavailable this session** (harness error), so the tool landscape and the exact identity of "voicebox" should be re-verified with Pietro. **No tools installed.** Needs Pietro's decisions before implementation.

---

## TL;DR / Recommendation

1. **"Training from scratch" is almost certainly infeasible here** — it needs a GPU, a curated dataset (hours of clean audio), Python 3.10+, and long training runs. Pietro's box is Apple Silicon, Python **3.9.6**, no sudo, no GPU-training setup.
2. **What *is* feasible and probably what he actually wants: zero-shot voice *cloning*** — pick a target voice, give the model a ~6-30s clean reference clip, and it speaks any text in that voice. No training run required.
3. **Best fit for a bilingual (pt-BR + English) local clone: XTTS v2** (via the maintained `coqui-tts` fork). Multilingual incl. pt + en, runs locally on CPU/MPS, supports Python 3.9. Keep macOS `say` as the instant fallback.
4. **Biggest catch is latency + the browser path:** neural TTS takes ~1-4 s/sentence on an M-series CPU/MPS (vs. instant `say`), and the **Chrome UI currently speaks via the browser's Web Speech API** — a custom voice there means generating audio server-side and streaming it to the browser (a real change, overlaps with Phase 2).
5. **Do not install autonomously** — XTTS + torch is a multi-GB install that could disturb the 3.9 venv. This doc is the plan; installation waits for Pietro.

---

## What "voicebox" likely means
Meta's **Voicebox** model is a research artifact with **no publicly usable weights**, so "voicebox" here most likely means *"a tool to give Jarvis a custom voice"* generically, or a specific app/repo Pietro found. **Please confirm the exact tool/repo.** The design below targets the *capability* (custom bilingual voice) and recommends concrete, available tools; swap in his specific "voicebox" if it differs.

## Options (from prior knowledge — re-verify availability/licenses)

| Tool | Custom voice via | pt-BR + EN | Apple Silicon / Py3.9 | Latency | Notes |
|------|------------------|-----------|------------------------|---------|-------|
| **XTTS v2** (`coqui-tts` fork) | zero-shot clone (~6 s ref) | ✅ both | ✅ CPU/MPS, Py3.9 ok | ~1-4 s/sentence | **Recommended.** Multilingual; model license is non-commercial — fine for personal use |
| **OpenVoice v2** (MyShell) | clone tone-color over a base TTS | ⚠️ base (MeloTTS) weak on pt-BR | ✅ | medium | Great cloning, but pt-BR coverage is the weak point |
| **F5-TTS** | zero-shot clone | ⚠️ growing | needs newer torch/Py | medium-high | Higher quality, heavier deps; Py3.9 questionable |
| **Piper** | pre-trained voices only (custom = training) | ✅ has pt-BR + en voices | ✅ very fast | very low | Best for a fast *existing* voice, not a custom clone |
| **MLX-audio / Kokoro** | pre-trained | ⚠️ limited pt | ✅ MLX-native, fast | very low | Apple-native + fast, but language/voice coverage limited |
| **macOS `say`** (current) | — | ✅ Luciana / Samantha | ✅ instant | instant | Current fallback; keep it |

**Recommendation:** **XTTS v2** for the custom clone (bilingual, local, Py3.9-friendly), with `say` as the always-available instant fallback. If latency proves too high for conversation, offer Piper (fast, pre-trained pt-BR/en) as a "fast voice" alternative.

## Constraints check
- **Python 3.9.6:** `coqui-tts` + `torch` support 3.9 on macOS arm64 → OK (verify on install). F5-TTS likely needs 3.10+ → riskier.
- **No sudo / TCC:** all pip-only into `.venv` → OK. (Big download ~2-3 GB incl. torch + model weights.)
- **Apple Silicon:** XTTS runs on CPU or MPS; M1+ handles short utterances in a few seconds.
- **Bilingual:** XTTS explicitly multilingual (pt + en) — must pass the detected `lang` per turn, same as `mouth.py`/`say` does today.
- **Cost:** fully local, **zero per-use cost** ✅ (consistent with constraint #1).

## Integration architecture (two voice paths today)
Jarvis speaks in **two** places — both need a decision:

1. **Python voice modes** (`jarvis.py`, `hotkey.py`, `wake.py` → `mouth.py` → macOS `say`).
   - Cleanest first target. Add a neural backend to `mouth.py`: synthesize a WAV with XTTS (passing `lang` + the reference clip), play via `afplay`, fall back to `say` on any error or when `JARVIS_VOICE_ENGINE=say`.
   - Env-var gated (matches existing convention): e.g. `JARVIS_VOICE_ENGINE=xtts|say`, `JARVIS_VOICE_REF=path/to/reference.wav`.
   - Keep `_clean()` markdown-stripping and barge-in (`stop()`) behavior.

2. **Browser UI** (`web/app.js` → Web Speech API `speechSynthesis`).
   - The browser can't run XTTS. A custom voice here requires **server-side TTS**: backend synthesizes audio and the page plays it (`<audio>`), instead of `speechSynthesis`.
   - Natural shape: a `POST /api/tts` (or fold audio into the existing SSE turn stream) that returns/streams the WAV; `app.js` plays it. This **overlaps with Phase 2** (Live Activity UI) and the streaming server we just built — worth sequencing together.

**Latency mitigation:** synthesize per sentence and play as they arrive (stream), pre-warm/keep the model loaded in a worker, and keep a low-latency fallback voice. A first pass can be "generate whole reply then play" and optimize later.

## Suggested phased plan (for approval)
- **Spike (low risk, ~1 session):** in a throwaway venv or a separate `requirements-tts.txt`, install `coqui-tts`, clone a chosen reference voice, synthesize one pt-BR and one English line, measure latency + quality on Pietro's M-series. Decide go/no-go before touching `mouth.py`.
- **Phase A — Python voice:** wire XTTS into `mouth.py` behind `JARVIS_VOICE_ENGINE`, with `say` fallback. Ships a custom voice for all terminal/voice modes.
- **Phase B — Browser voice:** add server-side TTS endpoint + `app.js` audio playback (sequence with Phase 2).

## Decisions needed from Pietro
1. **Which voice to clone?** His own voice (record ~30 s clean), a specific person/character, or a chosen sample. (Cloning a real person's voice = consent/ethics — assume his own or a licensed sample.)
2. **Confirm the tool** — is "voicebox" a specific repo, or shall we use **XTTS v2**?
3. **Latency tolerance** — is ~1-4 s before Jarvis speaks acceptable, or must it stay near-instant (then Piper / keep `say`)?
4. **Scope first** — Python voice modes only to start, or also the Chrome UI (bigger, overlaps Phase 2)?
5. **OK with a ~2-3 GB install** (torch + coqui-tts + weights) into the project, isolated from core deps?
