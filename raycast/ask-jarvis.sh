#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Ask Jarvis
# @raycast.mode fullOutput

# Optional parameters:
# @raycast.icon 🤖
# @raycast.packageName Jarvis
# @raycast.argument1 { "type": "text", "placeholder": "Ask Jarvis anything…" }

# Documentation:
# @raycast.description One-off question to Jarvis. Prints the reply and speaks it aloud (PT/EN auto-detected).
# @raycast.author Pietro
# @raycast.authorURL https://github.com/pietro

set -eu

PROJECT="/Users/pietrojustino/Documents/Jarvis"
PY="$PROJECT/.venv/bin/python"

cd "$PROJECT" || { echo "Cannot find Jarvis project at $PROJECT"; exit 1; }

# Raycast runs scripts in a NON-login shell, so make sure the `claude` CLI
# (Jarvis's Max-plan brain) is on PATH. brain.py also falls back to
# ~/.local/bin/claude, but this keeps things predictable.
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

if [ ! -x "$PY" ]; then
  echo "Jarvis venv Python not found at $PY — run install.sh first."
  exit 1
fi

# Run ONE text turn through the brain (not the interactive loop), print the reply,
# then speak it. The question arrives as $1 from the Raycast argument field.
"$PY" - "${1:-}" <<'PYEOF'
import sys, types

# We only need a one-shot TEXT turn. jarvis.py does `from ears import ...` at import
# time, and ears.py loads the Whisper model (and runs a warm-up) on import — far too
# heavy for a quick text question. Stub out `ears` BEFORE importing jarvis so we can
# still reuse jarvis._guess_language without paying for speech-to-text.
_ears = types.ModuleType("ears")
_ears.listen = _ears.listen_continuous = lambda *a, **k: ("", "en")
sys.modules.setdefault("ears", _ears)

question = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
if not question:
    print("No question provided.")
    sys.exit(0)

# Detect the language exactly the way the rest of Jarvis does.
try:
    from jarvis import _guess_language
except Exception:
    # Fallback mirror of jarvis._guess_language if the module shape ever changes.
    def _guess_language(text: str) -> str:
        t = text.lower()
        if any(c in t for c in "ãõçáéíóúâêôà"):
            return "pt"
        pt_words = (" você", " não", " está", "obrigad", " abra", " qual", " faça",
                    " bom dia", " olá", "tchau", " que horas", " meu ", " minha ")
        return "pt" if any(w in f" {t} " for w in pt_words) else "en"

from brain import Brain, BrainOffline
import mouth

lang = _guess_language(question)

try:
    # Pure chat only: a quick Raycast question must NOT autonomously control the Mac,
    # and this keeps the fast 90s chat timeout (no MCP/computer-use subprocess).
    reply = Brain(enable_computer_use=False).think(question)
except BrainOffline:
    # Cloud brain unreachable → try the offline Ollama brain, like jarvis.py does.
    reply = None
    try:
        from local_brain import LocalBrain
        lb = LocalBrain()
        if lb.available():
            reply = lb.think(question, language=lang)
    except Exception:
        pass
    if not reply:
        reply = ("I can't reach my brain right now." if lang == "en"
                 else "Não consigo acessar meu cérebro agora.")
except Exception as e:
    reply = f"Jarvis error: {e}"

# Show it in Raycast first…
print(reply)
sys.stdout.flush()

# …then say it out loud (blocks until the sentence finishes).
try:
    mouth.speak(reply, lang)
except Exception:
    pass
PYEOF
