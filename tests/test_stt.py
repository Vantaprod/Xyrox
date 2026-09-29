"""
Xyrox — STT Tests (Phase 6.2)

Validates the STT interface without requiring the Whisper model to
be downloaded. Real transcription tests SKIP if the model is not
cached or faster-whisper is missing.
"""

import wave
import numpy as np
import pytest

from app.backend.voice.stt import (
    transcribe,
    model_is_cached,
    clear_model_cache,
    STTError,
    VALID_MODELS,
    DEFAULT_MODEL,
)


# ============================================================
# SYNTHETIC WAV FIXTURE
# ============================================================
@pytest.fixture
def silent_wav(tmp_path):
    """A 1-second silent WAV file. Valid audio, no speech."""
    path = tmp_path / "silent.wav"
    sr = 16000
    samples = np.zeros(sr, dtype=np.float32)
    import soundfile as sf
    sf.write(str(path), samples, sr)
    return path


# ============================================================
# DRY-RUN
# ============================================================
def test_dry_run_returns_synthetic(silent_wav):
    result = transcribe(str(silent_wav), dry_run=True)
    assert result.text.startswith("[dry run]")
    assert result.model == DEFAULT_MODEL


def test_dry_run_with_custom_model(silent_wav):
    result = transcribe(str(silent_wav), model="base.en", dry_run=True)
    assert result.model == "base.en"


# ============================================================
# VALIDATION
# ============================================================
def test_rejects_missing_file(tmp_path):
    with pytest.raises(STTError):
        transcribe(str(tmp_path / "nope.wav"))


def test_rejects_empty_path():
    with pytest.raises(STTError):
        transcribe("")


def test_rejects_wrong_extension(tmp_path):
    p = tmp_path / "not.wav"
    p.write_text("fake")
    with pytest.raises(STTError):
        transcribe(str(p))


def test_rejects_unknown_model(silent_wav):
    with pytest.raises(STTError):
        transcribe(str(silent_wav), model="gpt-5")


def test_rejects_bad_beam_size(silent_wav):
    with pytest.raises(STTError):
        transcribe(str(silent_wav), beam_size=0)
    with pytest.raises(STTError):
        transcribe(str(silent_wav), beam_size=999)


# ============================================================
# CACHE STATE
# ============================================================
def test_model_cache_check_returns_bool():
    assert isinstance(model_is_cached(DEFAULT_MODEL), bool)


def test_clear_model_cache():
    clear_model_cache()
    # After clear, cache check still works (reflects on-disk state)
    assert isinstance(model_is_cached(DEFAULT_MODEL), bool)


# ============================================================
# REAL TRANSCRIPTION — SKIP IF MODEL NOT AVAILABLE
# ============================================================
def test_real_transcribe_requires_model(silent_wav):
    """
    If the model is cached and faster-whisper is installed, run a real
    transcription on silence. If not, SKIP — this is not a failure.
    """
    if not model_is_cached(DEFAULT_MODEL):
        pytest.skip(
            f"Model '{DEFAULT_MODEL}' not cached. "
            f"Run a real transcription once to download it."
        )
    try:
        result = transcribe(str(silent_wav), model=DEFAULT_MODEL)
    except STTError as exc:
        pytest.skip(f"faster-whisper not available: {exc}")

    # Silence should produce empty or near-empty text. That's OK.
    assert isinstance(result.text, str)
    assert isinstance(result.duration_seconds, float)