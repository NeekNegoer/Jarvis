#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Talk to Jarvis
# @raycast.mode silent

# Optional parameters:
# @raycast.icon 🎙️
# @raycast.packageName Jarvis

# Documentation:
# @raycast.description Brings Chrome to the front and starts Jarvis listening — just talk, no keys, no Terminal window.
# @raycast.author Pietro
# @raycast.authorURL https://github.com/pietro

set -u

PROJECT="/Users/pietrojustino/Documents/Jarvis"
PY="$PROJECT/.venv/bin/python"
PIDFILE="$PROJECT/logs/jarvis.pid"
LOG="$PROJECT/logs/jarvis-voice.log"
mkdir -p "$PROJECT/logs"

# Bring Chrome to the front (launch it if it isn't open) — that's your workspace.
open -a "Google Chrome" 2>/dev/null || true

# If a Jarvis voice session is already running, stop it first so we don't stack two.
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
  kill "$(cat "$PIDFILE")" 2>/dev/null || true
  sleep 1
fi

export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
cd "$PROJECT" || { echo "Can't find Jarvis at $PROJECT"; exit 1; }
if [ ! -x "$PY" ]; then echo "Jarvis venv not found — run install.sh first."; exit 1; fi

# Talk-only: hands-free (continuous listening), running detached in the background so no
# Terminal window appears. Jarvis speaks a short greeting so you know it's listening.
nohup "$PY" jarvis.py --hands-free >"$LOG" 2>&1 &
echo $! > "$PIDFILE"
disown 2>/dev/null || true

echo "🎙️ Jarvis is listening — just talk. Say 'goodbye'/'tchau' or run 'Stop Jarvis' to stop."
