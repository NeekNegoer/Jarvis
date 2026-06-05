"""
hotkey.py — talk to Jarvis from ANYWHERE with a global hotkey (experimental).

Hold the hotkey (default: Right Option ⌥) → talk → release → Jarvis hears you, thinks,
and speaks back. No need to be in the terminal. This makes Jarvis feel always-on.

  python hotkey.py

Needs one extra macOS permission beyond the usual: **Input Monitoring** (so it can hear
the global hotkey), granted to the app you launch it from — System Settings → Privacy &
Security → Input Monitoring. (Plus Microphone, and Accessibility for computer control.)

This is intentionally separate from jarvis.py so the core voice loop stays simple and
rock-solid. Change the hotkey via JARVIS_HOTKEY (e.g. alt_r, cmd_r, f13).
"""

from __future__ import annotations

import os
import queue
import threading

import numpy as np
import sounddevice as sd
from pynput import keyboard

from ears import SAMPLE_RATE, _transcribe_array
from brain import Brain, BrainOffline
from mouth import speak, stop as stop_speaking

HOTKEY_NAME = os.getenv("JARVIS_HOTKEY", "alt_r")  # Right Option by default


def _resolve_key(name: str):
    try:
        return getattr(keyboard.Key, name)
    except AttributeError:
        return keyboard.KeyCode.from_char(name)


class PushToTalk:
    def __init__(self):
        self.brain = Brain()
        self.key = _resolve_key(HOTKEY_NAME)
        self.recording = False
        self.frames: "queue.Queue[np.ndarray]" = queue.Queue()
        self.stream: sd.InputStream | None = None
        self._busy = False

    def _on_audio(self, indata, *_):
        if self.recording:
            self.frames.put(indata.copy())

    def start(self):
        self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                     dtype="float32", callback=self._on_audio)
        self.stream.start()
        print(f"🎧 Jarvis hotkey ready. Hold {HOTKEY_NAME} and talk. Ctrl+C to quit.")
        with keyboard.Listener(on_press=self._press, on_release=self._release) as ls:
            ls.join()

    def _press(self, k):
        if k == self.key and not self.recording and not self._busy:
            stop_speaking()  # barge-in: hush mid-sentence if Jarvis is talking
            while not self.frames.empty():
                self.frames.get()
            self.recording = True
            print("🎙️  recording…")

    def _release(self, k):
        if k == self.key and self.recording:
            self.recording = False
            threading.Thread(target=self._handle_turn, daemon=True).start()

    def _handle_turn(self):
        self._busy = True
        try:
            chunks = []
            while not self.frames.empty():
                chunks.append(self.frames.get())
            if not chunks:
                return
            audio = np.concatenate(chunks).flatten()
            text, lang = _transcribe_array(audio)
            if not text:
                print("   (didn't catch that)")
                return
            print(f"🗣️  [{lang}] {text}")
            try:
                reply = self.brain.think(text)
            except BrainOffline:
                reply = ("My main brain is offline right now." if lang == "en"
                         else "Meu cérebro principal está offline agora.")
            print(f"🤖 {reply}")
            speak(reply, lang)
        finally:
            self._busy = False


if __name__ == "__main__":
    try:
        PushToTalk().start()
    except KeyboardInterrupt:
        print("\nbye")
