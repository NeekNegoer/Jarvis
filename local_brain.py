"""
local_brain.py — Jarvis's offline brain (Ollama).

A fallback for when the Max-plan brain can't be reached (no internet). It talks to a
local Ollama model over HTTP — fully offline, private, free. It's conversational only
(no computer-control tools); for that you need the cloud brain.

Setup (no admin needed): install Ollama and pull a model — see install.sh / TODO_TOMORROW.md.
Pick the model with JARVIS_OLLAMA_MODEL (default: qwen2.5:7b — good in Portuguese & English).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "127.0.0.1:11434")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = "http://" + OLLAMA_HOST
MODEL = os.getenv("JARVIS_OLLAMA_MODEL", "qwen2.5:7b")

SYSTEM = """You are Jarvis, Pietro's personal voice assistant, running offline right now.
Reply in the SAME language Pietro used — Brazilian Portuguese or English. Your replies are
spoken aloud, so keep them short (1-3 sentences), plain and conversational: no markdown,
no bullet points, no code, no emojis. Be warm, witty and genuinely helpful. You currently
have no internet and cannot control the computer; if asked for those, say so briefly."""


def _get(path: str, timeout: float = 3.0):
    req = urllib.request.Request(OLLAMA_HOST + path)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post(path: str, payload: dict, timeout: float = 120.0):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(OLLAMA_HOST + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


class LocalBrain:
    def __init__(self, model: str | None = None):
        self.model = model or MODEL
        self.history: list[dict] = []

    def available(self) -> bool:
        """True if the Ollama server is up and our model is pulled."""
        try:
            tags = _get("/api/tags")
        except (urllib.error.URLError, OSError, ValueError):
            return False
        names = [m.get("name", "") for m in tags.get("models", [])]
        # match "qwen2.5:7b" against "qwen2.5:7b" or "qwen2.5:7b-instruct-q4_K_M" etc.
        base = self.model.split(":")[0]
        return any(n == self.model or n.startswith(base) for n in names)

    def think(self, user_text: str, language: str = "en") -> str:
        self.history.append({"role": "user", "content": user_text})
        # Smaller local models drift between languages; pin it explicitly each turn.
        lang_rule = ("Reply ONLY in English." if language == "en"
                     else "Responda SOMENTE em português do Brasil.")
        messages = ([{"role": "system", "content": SYSTEM + "\n\n" + lang_rule}]
                    + self.history)
        try:
            resp = _post("/api/chat", {
                "model": self.model, "messages": messages, "stream": False,
                "options": {"temperature": 0.6, "num_predict": 300},
            })
        except Exception:
            return ("My offline brain isn't responding." if language == "en"
                    else "Meu cérebro offline não está respondendo.")
        reply = (resp.get("message") or {}).get("content", "").strip()
        self.history.append({"role": "assistant", "content": reply})
        return reply or ("Okay." if language == "en" else "Certo.")


if __name__ == "__main__":
    lb = LocalBrain()
    print("available:", lb.available(), "| model:", lb.model)
    if lb.available():
        print("EN:", lb.think("Say hello in 4 words.", "en"))
        print("PT:", lb.think("Diga olá em quatro palavras.", "pt"))
