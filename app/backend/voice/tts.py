"""
Xyrox — Text-to-Speech (Phase 6.1)

Real speech output using pyttsx3, which on Windows uses the built-in
SAPI5 voices (Microsoft David, Zira, etc.). No model download.
Works offline.

Design rules:
- Singleton engine per process (pyttsx3 has global state).
- Thread-safe for a single speaker (voice output is serialized).
- dry_run=True skips actual audio for tests.
- All errors surface explicitly; nothing is swallowed.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional


class TTSError(Exception):
    """Raised when TTS cannot initialize or speak."""
    pass


@dataclass
class VoiceInfo:
    id: str
    name: str
    languages: list[str]
    gender: Optional[str] = None


_lock = threading.Lock()
_engine = None
_initialized = False


# ============================================================
# INTERNAL
# ============================================================
def _ensure_engine(dry_run: bool):
    """
    Lazily create the pyttsx3 engine. Returns None in dry_run mode.
    Raises TTSError if pyttsx3 is not importable and not dry_run.
    """
    global _engine, _initialized
    if dry_run:
        return None
    if _initialized:
        return _engine
    try:
        import pyttsx3
    except Exception as exc:
        raise TTSError(
            f"pyttsx3 is not available: {exc}. "
            f"Install with: pip install pyttsx3"
        ) from exc
    try:
        _engine = pyttsx3.init()
    except Exception as exc:
        raise TTSError(f"pyttsx3.init() failed: {exc}") from exc
    _initialized = True
    return _engine


# ============================================================
# PUBLIC
# ============================================================
def list_voices(dry_run: bool = False) -> list[VoiceInfo]:
    """
    Return every installed TTS voice.

    In dry_run mode returns an empty list without touching hardware.
    """
    if dry_run:
        return []
    engine = _ensure_engine(dry_run=False)
    try:
        voices = engine.getProperty("voices") or []
    except Exception as exc:
        raise TTSError(f"Cannot list voices: {exc}") from exc

    result: list[VoiceInfo] = []
    for v in voices:
        result.append(VoiceInfo(
            id=str(getattr(v, "id", "")),
            name=str(getattr(v, "name", "")),
            languages=[str(x) for x in (getattr(v, "languages", []) or [])],
            gender=getattr(v, "gender", None),
        ))
    return result


def speak(
    text: str,
    rate: Optional[int] = None,
    volume: Optional[float] = None,
    voice_id: Optional[str] = None,
    block: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Speak the given text.

    text:     what to say. Must be non-empty, <= 5000 chars.
    rate:     words per minute (default: engine default, ~200).
              50-400 is sane.
    volume:   0.0 to 1.0.
    voice_id: an id from list_voices(). If given, uses that voice.
    block:    if True, return after speech completes.
              if False, returns immediately (background thread).
    dry_run:  if True, validate only; no audio.

    Returns a dict with {spoken: bool, text, voice_id, rate, volume}.
    Raises TTSError on any failure.
    """
    if not isinstance(text, str) or not text.strip():
        raise TTSError("text must be a non-empty string.")
    if len(text) > 5000:
        raise TTSError("text must be at most 5000 characters.")
    if rate is not None:
        if not isinstance(rate, int) or not (50 <= rate <= 400):
            raise TTSError("rate must be an integer between 50 and 400.")
    if volume is not None:
        if not isinstance(volume, (int, float)) or not (0.0 <= volume <= 1.0):
            raise TTSError("volume must be a number between 0.0 and 1.0.")
    if voice_id is not None and not isinstance(voice_id, str):
        raise TTSError("voice_id must be a string or None.")

    if dry_run:
        return {
            "spoken": True,
            "text": text,
            "voice_id": voice_id,
            "rate": rate,
            "volume": volume,
            "dry_run": True,
        }

    with _lock:
        engine = _ensure_engine(dry_run=False)
        try:
            if rate is not None:
                engine.setProperty("rate", int(rate))
            if volume is not None:
                engine.setProperty("volume", float(volume))
            if voice_id is not None:
                engine.setProperty("voice", voice_id)

            engine.say(text)
            if block:
                engine.runAndWait()
            else:
                # Non-blocking: spawn a thread that runs runAndWait.
                def _run():
                    try:
                        engine.runAndWait()
                    except Exception:
                        pass
                t = threading.Thread(target=_run, daemon=True)
                t.start()
        except Exception as exc:
            raise TTSError(f"speak() failed: {exc}") from exc

    return {
        "spoken": True,
        "text": text,
        "voice_id": voice_id,
        "rate": rate,
        "volume": volume,
        "dry_run": False,
    }


def stop() -> None:
    """Stop current speech (if any). Safe to call anytime."""
    global _engine
    if _engine is None:
        return
    try:
        _engine.stop()
    except Exception:
        pass