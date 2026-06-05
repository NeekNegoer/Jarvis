#!/usr/bin/env bash
#
# install.sh — set Jarvis up from scratch on a Mac. No admin/sudo needed.
#
#   bash install.sh            # set up Python deps + check everything
#   bash install.sh --ollama   # also install the offline brain (Ollama) + pull a model
#
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
VENV=".venv"

echo "🛠️  Setting up Jarvis..."

# 1) Virtualenv + Python deps -------------------------------------------------
if [ ! -d "$VENV" ]; then
  echo "→ creating virtualenv ($VENV)"
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
echo "→ installing Python packages (this can take a few minutes the first time)"
pip install --upgrade pip wheel >/dev/null
pip install -r requirements.txt

# 2) Brain check --------------------------------------------------------------
if command -v claude >/dev/null 2>&1; then
  echo "✅ Claude Code CLI found — your Max-plan brain is ready."
else
  echo "⚠️  Claude Code CLI not found. Install it and log in with your Max plan:"
  echo "     https://claude.com/claude-code   (then run \`claude\` once to log in)"
fi

# 3) Optional: offline brain (Ollama), installed WITHOUT brew or sudo ---------
if [ "$1" == "--ollama" ]; then
  echo "→ installing Ollama (offline brain) without admin..."
  TAG=$(curl -fsSL https://api.github.com/repos/ollama/ollama/releases/latest | sed -n 's/.*"tag_name": "\(.*\)".*/\1/p')
  URL="https://github.com/ollama/ollama/releases/download/${TAG}/ollama-darwin.tgz"
  TMP=$(mktemp -d)
  echo "   downloading ollama ${TAG}..."
  curl -fsSL "$URL" -o "$TMP/ollama.tgz"
  rm -rf "$HOME/.ollama-dist" && mkdir -p "$HOME/.ollama-dist"
  tar -xzf "$TMP/ollama.tgz" -C "$HOME/.ollama-dist"
  chmod +x "$HOME/.ollama-dist/ollama"
  xattr -dr com.apple.quarantine "$HOME/.ollama-dist" 2>/dev/null || true
  mkdir -p "$HOME/.local/bin"
  ln -sf "$HOME/.ollama-dist/ollama" "$HOME/.local/bin/ollama"
  rm -rf "$TMP"
  echo "   starting the Ollama server..."
  OLLAMA_HOST=127.0.0.1:11434 nohup "$HOME/.ollama-dist/ollama" serve >/tmp/ollama_serve.log 2>&1 &
  sleep 3
  MODEL="${JARVIS_OLLAMA_MODEL:-qwen2.5:7b}"
  echo "   pulling model $MODEL (a few GB; one time)..."
  OLLAMA_HOST=127.0.0.1:11434 "$HOME/.ollama-dist/ollama" pull "$MODEL"
  echo "✅ Offline brain ready ($MODEL)."
  echo "   (add ~/.local/bin to your PATH if 'ollama' isn't found in new shells)"
fi

# 4) Final check --------------------------------------------------------------
echo ""
echo "→ running the doctor to see what's left..."
python doctor.py || true

echo ""
echo "Done. Start Jarvis with:   source .venv/bin/activate && python jarvis.py"
