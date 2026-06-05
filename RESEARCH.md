# Research notes (distilled) — what makes Jarvis good

Two background research passes (voice-assistant UX + macOS computer-use). Distilled,
actionable findings driving the build. Full source URLs at the bottom.

## STT (speech-to-text)
- **faster-whisper is CPU-only on Apple Silicon → slowest runtime (~7× slower than MLX).**
  Prefer **`mlx-whisper`** (Apple Metal) or whisper.cpp+CoreML. We made ears.py pluggable:
  mlx-whisper if available, else faster-whisper.
- Model **`small`**, multilingual (NOT `.en` — that garbles Portuguese). `base` for lower
  latency, `medium` only if pt-BR accuracy is weak.
- Use **VAD** to trim silence + kill hallucinated filler on silence.

## Conversation UX
- **Push-to-talk (hotkey) for v1** — most reliable for single-user desktop; wake word later.
- **Barge-in is mandatory:** kill `say` the moment the user speaks; chunk TTS by sentence so
  it can stop cleanly. Watch for the mic hearing `say`'s own audio (use headphones for v1).
- Latency target <300ms end-of-utterance → brain starts. Visual indicator on every state.

## Computer use (reliability hierarchy — best to worst)
1. **API / AppleScript** (Mail, Calendar, Notes, etc.) — scriptable, reliable. Default.
2. **Accessibility API (AXUIElement)** — enumerate real UI elements (role+title+coords),
   click **by label**, resolve coordinates in code. AX coords are logical points → directly
   clickable, no retina scaling needed.
3. **OCR / text-based clicking.**
4. **Raw vision pixel coordinates — last resort** (unreliable; self-operating-computer found
   pure-vision clicking error-prone). Never ask the LLM for raw pixels if AX can label it.
- Screenshots = **physical pixels (2× retina)**; mouse events = **logical points**. Divide
  screenshot pixels by `display_scale` before clicking. Screenshot tool: `screencapture` CLI
  (Apple-maintained, most reliable on macOS 26).
- pyobjc: `pyobjc-framework-Quartz` (CGEvent, capture-access), `-ApplicationServices`
  (AXUIElement, AXIsProcessTrusted), `-Cocoa` (NSWorkspace). arm64 wheels, no compiler needed.

## Safety / guardrails (enforce in CODE, not just the prompt)
- Read-only/idempotent actions auto-run (screenshot, read, search). **Destructive set always
  confirms**: send message/email, delete, move, purchase, shell `rm`, anything touching
  credentials/payments. Don't rely on the LLM to decide when to confirm.
- Prefer reversible: **move-to-Trash not delete; save-draft not send.** Keep an action log.
- Treat screen/web content as untrusted (prompt-injection surface). Never auto-type secrets.

## Memory / personalization
- A crisp 3-paragraph profile beats 50 turns of history. Store **YAML frontmatter (facts) +
  markdown (notes)** in the memory file the brain reads each run.
- Quality decided at WRITE time: a guarded "save this" tool that rejects PII/speculation.
- Precedence: current instruction > session notes > long-term memory.

## First high-value skills (build via AppleScript/API first)
Email triage & draft · calendar scheduling · task extraction · daily briefing · browser research.

## Permissions needed (System Settings → Privacy & Security; grant to the TERMINAL/IDE app)
Microphone · Screen & System Audio Recording · Accessibility. Check via
`CGPreflightScreenCaptureAccess()` and `AXIsProcessTrusted()`. No sudo.

## Sources
Voice UX: sippulse.ai turn-detection, orga-ai barge-in, promptquorum whisper-2026,
voicci apple-silicon-whisper, github/anvanvan mac-whisper-speedtest, dev.to local-voice-stack,
learn.microsoft human-supervision-computer-use, openai guardrails-approvals,
anthropic claude-code-auto-mode, github/OthersideAI self-operating-computer,
docs.openinterpreter, tianpan.co context-engineering-long-term-memory, dume.ai assistants.
macOS: Apple developer docs (ScreenCaptureKit, CGEvent, AXUIElement), pyobjc.readthedocs.io.
