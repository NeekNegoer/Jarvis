"""
ears.py — Jarvis's ears (bilingual, Metal-accelerated).

Records your voice and turns it into text locally — free, private, offline after the
first model download. It auto-detects whether you spoke **Brazilian Portuguese or
English** each turn so the rest of Jarvis replies and speaks in the right language.

Two transcription backends, picked automatically:
  • mlx-whisper   — Apple-Silicon/Metal accelerated. ~7× faster than CPU. Preferred.
  • faster-whisper — CPU fallback (works everywhere, slower on M1).
Force one with JARVIS_STT=mlx|faster. Pick model size with JARVIS_WHISPER_MODEL.

Recording is push-to-talk: press Enter to start, Enter again to stop.
"""

from __future__ import annotations

import os
import queue
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000  # Whisper expects 16kHz mono audio
SUPPORTED = {"pt", "en"}  # other detected languages are coerced to the nearest of these

# "small" is the sweet spot on an M1 Pro: good Portuguese accuracy, still fast.
# tiny/base = lower latency; medium = better pt-BR at a latency cost.
MODEL_NAME = os.getenv("JARVIS_WHISPER_MODEL", "small")
_BACKEND_PREF = os.getenv("JARVIS_STT", "").lower()  # "", "mlx", or "faster"


def _coerce_lang(lang: str | None) -> str:
    return lang if lang in SUPPORTED else "en"


# --- Backend selection ------------------------------------------------------------
_backend = None        # "mlx" or "faster"
_mlx_repo = None
_fw_model = None


def _init_backend():
    global _backend, _mlx_repo, _fw_model
    want_faster = _BACKEND_PREF == "faster"
    if not want_faster:
        try:
            import mlx_whisper  # noqa: F401
            _mlx_repo = f"mlx-community/whisper-{MODEL_NAME}-mlx"
            _backend = "mlx"
            print(f"🧠 Speech backend: mlx-whisper ({_mlx_repo}) — Metal accelerated.")
            return
        except Exception as e:
            if _BACKEND_PREF == "mlx":
                raise
            print(f"   (mlx-whisper unavailable: {e}; falling back to faster-whisper)")
    from faster_whisper import WhisperModel
    print(f"🧠 Speech backend: faster-whisper ({MODEL_NAME}) — CPU.")
    _fw_model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")


# MLX/Metal is not thread-safe; serialize every transcription so the background
# warm-up can never run concurrently with a real turn (that segfaults).
_stt_lock = threading.Lock()


def _transcribe_array(audio: np.ndarray) -> tuple[str, str]:
    if audio.size < SAMPLE_RATE // 2:  # < ~0.5s, probably nothing
        return "", "en"
    with _stt_lock:
        return _transcribe_locked(audio)


def _transcribe_locked(audio: np.ndarray) -> tuple[str, str]:
    if _backend == "mlx":
        import mlx_whisper
        r = mlx_whisper.transcribe(
            audio, path_or_hf_repo=_mlx_repo, language=None,
            no_speech_threshold=0.6,  # cut hallucinated filler on silence
        )
        return r["text"].strip(), _coerce_lang(r.get("language"))
    # faster-whisper path: it reads files, so hand it the array via a temp wav.
    import tempfile
    from scipy.io.wavfile import write as write_wav
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
        write_wav(f.name, SAMPLE_RATE, np.int16(np.clip(audio, -1, 1) * 32767))
        segments, info = _fw_model.transcribe(
            f.name, language=None, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        text = " ".join(seg.text for seg in segments).strip()
    return text, _coerce_lang(info.language)


_init_backend()


def _warm_up():
    """Run one transcription on silence so the first real turn isn't slow."""
    try:
        _transcribe_array(np.zeros(SAMPLE_RATE, dtype="float32"))
    except Exception:
        pass


threading.Thread(target=_warm_up, daemon=True).start()
print("✅ Ears ready.")


def _record_until_enter() -> np.ndarray:
    """Record from the mic until Enter is pressed. Returns float32 samples."""
    frames: "queue.Queue[np.ndarray]" = queue.Queue()

    def callback(indata, _frames, _time, _status):
        frames.put(indata.copy())

    stop = threading.Event()
    threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                        callback=callback):
        while not stop.is_set():
            sd.sleep(50)

    chunks = []
    while not frames.empty():
        chunks.append(frames.get())
    if not chunks:
        return np.zeros(0, dtype="float32")
    return np.concatenate(chunks, axis=0).flatten()


def listen() -> tuple[str, str]:
    """Record one spoken turn. Returns (text, language) where language is 'pt' or 'en'."""
    print("\n🎙️  Press Enter, speak, then press Enter again to send...")
    input()
    print("   recording... (press Enter to stop)")
    audio = _record_until_enter()
    return _transcribe_array(audio)


def _calibrate_noise(seconds: float = 0.6) -> float:
    """Sample ambient noise to set a speech threshold. Returns an RMS threshold."""
    rec = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    ambient = float(np.sqrt(np.mean(rec.astype(np.float64) ** 2)) + 1e-6)
    # Speech must be clearly above ambient; floor keeps it sane in dead-silent rooms.
    return max(ambient * 3.5, 0.012)


def listen_continuous(silence_ms: int = 800, max_seconds: int = 30,
                      threshold: float | None = None) -> tuple[str, str]:
    """Hands-free: wait for speech, record until you pause, then transcribe.

    Energy-based voice-activity detection — no extra dependencies. Returns (text, lang).
    Best with headphones so the mic doesn't hear Jarvis's own voice.
    """
    if threshold is None:
        threshold = _calibrate_noise()
    frame = int(SAMPLE_RATE * 0.03)  # 30ms frames
    silence_frames_needed = int(silence_ms / 30)
    max_frames = int(max_seconds / 0.03)

    collected: list[np.ndarray] = []
    started = False
    silent_run = 0

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                        blocksize=frame) as stream:
        for _ in range(max_frames):
            block, _ = stream.read(frame)
            block = block.flatten()
            rms = float(np.sqrt(np.mean(block.astype(np.float64) ** 2)) + 1e-9)
            loud = rms > threshold
            if loud:
                if not started:
                    started = True
                silent_run = 0
                collected.append(block)
            elif started:
                collected.append(block)
                silent_run += 1
                if silent_run >= silence_frames_needed:
                    break  # the user paused → end of turn

    if not collected:
        return "", "en"
    return _transcribe_array(np.concatenate(collected))


def transcribe_file(path: str) -> tuple[str, str]:
    """Transcribe an existing 16kHz wav file (used by tests). Returns (text, language)."""
    from scipy.io.wavfile import read as read_wav
    _sr, data = read_wav(path)
    audio = data.astype(np.float32) / 32768.0 if data.dtype == np.int16 else data.astype(np.float32)
    return _transcribe_array(audio)


if __name__ == "__main__":
    said, lang = listen()
    print(f"\n[{lang}] You said: {said!r}")
