#!/bin/bash
# Jarvis.command — double-click this in Finder to start Jarvis (opens in Terminal).
#
# Pass a mode by editing the last line, or just run from a terminal:
#   ./Jarvis.command            # push-to-talk voice
#   ./Jarvis.command --text     # type instead of talk
#   ./Jarvis.command --hands-free
#
# Note: if you launch via double-click, the app that needs the macOS permissions is
# *Terminal* (grant Microphone/Accessibility to Terminal in System Settings).

cd "$(dirname "$0")" || exit 1

# Best-effort: start the offline Ollama brain in the background if it's installed but down.
OLLAMA="$HOME/.ollama-dist/ollama"
if [ -x "$OLLAMA" ]; then
  if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    echo "Starting offline brain (Ollama)…"
    OLLAMA_HOST=127.0.0.1:11434 nohup "$OLLAMA" serve >/tmp/ollama_serve.log 2>&1 &
    sleep 2
  fi
fi

if [ ! -d ".venv" ]; then
  echo "First run: setting up. This takes a few minutes…"
  bash install.sh
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec python jarvis.py "$@"
