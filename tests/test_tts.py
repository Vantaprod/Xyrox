"""
Xyrox — TTS Tests (Phase 6.1)

Validates the TTS interface without requiring real audio hardware
(dry_run mode). One optional test attempts a real pyttsx3 init and
SKIPS if unavailable — so the suite never fails due to missing audio.
"""

import pytest

from app.backend.voice.tts import (
    speak,
    list_voices,
    TTSError,
)


# ============================================================
# DRY-RUN — always testable, no audio
# ============================================================
def test_speak_dry_run_valid():
    r = speak("Hello world.", dry_run=True)
    assert r["spoken"] is True
    assert r["dry_run"] is True
    assert r["text"] == "Hello world."


def test_speak_rejects_empty():
    with pytest.raises(TTSError):
        speak("", dry_run=True)


def test_speak_rejects_whitespace():
    with pytest.raises(TTSError):
        speak("   ", dry_run=True)


def test_speak_rejects_too_long():
    with pytest.raises(TTSError):
        speak("x" * 5001, dry_run=True)


def test_speak_rejects_bad_rate():
    with pytest.raises(TTSError):
        speak("hi", rate=10, dry_run=True)
    with pytest.raises(TTSError):
        speak("hi", rate=1000, dry_run=True)


def test_speak_rejects_bad_volume():
    with pytest.raises(TTSError):
        speak("hi", volume=1.5, dry_run=True)
    with pytest.raises(TTSError):
        speak("hi", volume=-0.1, dry_run=True)


def test_speak_rejects_bad_voice_id():
    with pytest.raises(TTSError):
        speak("hi", voice_id=123, dry_run=True)  # type: ignore


def test_speak_accepts_optional_params():
    r = speak(
        "Test message.",
        rate=180,
        volume=0.8,
        voice_id="fake-id",
        dry_run=True,
    )
    assert r["spoken"] is True
    assert r["rate"] == 180
    assert r["volume"] == 0.8
    assert r["voice_id"] == "fake-id"


def test_list_voices_dry_run():
    voices = list_voices(dry_run=True)
    assert voices == []


# ============================================================
# REAL PYTTSX3 — SKIP IF UNAVAILABLE
# ============================================================
def test_real_tts_initializes():
    """Attempt a real pyttsx3 init. Skips if the library is missing."""
    try:
        voices = list_voices(dry_run=False)
    except TTSError as exc:
        pytest.skip(f"pyttsx3 not available: {exc}")
    # If we got here, pyttsx3 works. Voices should be non-empty on Windows.
    assert isinstance(voices, list)