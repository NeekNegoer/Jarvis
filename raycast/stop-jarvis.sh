#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Stop Jarvis
# @raycast.mode silent

# Optional parameters:
# @raycast.icon 🛑
# @raycast.packageName Jarvis

# Documentation:
# @raycast.description Stop the background Jarvis voice session.
# @raycast.author Pietro
# @raycast.authorURL https://github.com/pietro

set -u

PROJECT="/Users/pietrojustino/Documents/Jarvis"
PIDFILE="$PROJECT/logs/jarvis.pid"
stopped=0

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" 2>/dev/null)"
  if [ -n "$PID" ] && kill "$PID" 2>/dev/null; then stopped=1; fi
  rm -f "$PIDFILE"
fi

# Fallback: catch any stray hands-free/wake session.
if pkill -f "jarvis.py --hands-free" 2>/dev/null; then stopped=1; fi
if pkill -f "jarvis.py --wake" 2>/dev/null; then stopped=1; fi
pkill -x say 2>/dev/null || true   # cut off any in-progress speech

if [ "$stopped" -eq 1 ]; then echo "🛑 Jarvis stopped."; else echo "Jarvis wasn't running."; fi
