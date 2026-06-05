#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Open Jarvis
# @raycast.mode silent

# Optional parameters:
# @raycast.icon 🟠
# @raycast.packageName Jarvis

# Documentation:
# @raycast.description Open the Jarvis UI in Chrome (starts the local server if needed). Talk or type.
# @raycast.author Pietro
# @raycast.authorURL https://github.com/pietro

set -u

PROJECT="/Users/pietrojustino/Documents/Jarvis"
PY="$PROJECT/.venv/bin/python"
URL="http://127.0.0.1:8765"
LOG="$PROJECT/logs/jarvis-ui.log"
PIDFILE="$PROJECT/logs/jarvis-ui.pid"
mkdir -p "$PROJECT/logs"

export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
cd "$PROJECT" || { echo "Can't find Jarvis at $PROJECT"; exit 1; }
if [ ! -x "$PY" ]; then echo "Jarvis venv not found — run install.sh first."; exit 1; fi

# Start the server only if it isn't already answering.
if ! curl -fsS "$URL/api/health" >/dev/null 2>&1; then
  nohup "$PY" server.py --no-open >"$LOG" 2>&1 &
  echo $! > "$PIDFILE"
  disown 2>/dev/null || true
  for _ in $(seq 1 20); do curl -fsS "$URL/api/health" >/dev/null 2>&1 && break; sleep 0.4; done
fi

open -a "Google Chrome" "$URL"
echo "🟠 Jarvis is open in Chrome — talk or type."
