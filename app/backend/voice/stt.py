"""
Xyrox — Speech-to-Text (Phase 6.2)

Transcribes WAV files and raw audio to text using faster-whisper
(CPU-optimized CTranslate2 backend) with automatic download of the
Whisper model on first use.

Design rules:
- Model is downloaded once and cached in ~/.cache/huggingface/
- If the download fails, the error is explicit and retryable.
- Dry-run mode for tests without model download.
- All transcription is offline after the initial model download.
- Speaker verification is NOT here (Phase 6.3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class STTError(Exception):
    """Raised when speech-to-text fails."""
    pass


@dataclass
class TranscriptionResult:
    text: str
    language: Optional[str]
    duration_seconds: float
    model: str


# ============================================================
# CONFIG
# ============================================================
DEFAULT_MODEL = "tiny.en"           # ~75 MB, fast, English-focused
FALLBACK_MODEL = "base.en"          # ~140 MB, better accuracy
VALID_MODELS = {
    "tiny.en", "tiny",
    "base.en", "base",
    "small.en", "small",
    "medium.en", "medium",
    "large-v3", "large",
}

# In-process cache so the model loads only once per program run.
_model_cache: dict[str, object] = {}


# ============================================================
# INTERNAL
# ============================================================
def _ensure_model(model_name: str):
    """Load and cache a WhisperModel. Raises STTError on failure."""
    if model_name in _model_cache:
        return _model_cache[model_name]

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise STTError(
            "faster-whisper is not installed. "
            "Run: pip install faster-whisper"
        ) from exc

    try:
        # device="cpu", compute_type="int8" — best for CPU-only machines.
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
    except Exception as exc:
        raise STTError(
            f"Failed to load Whisper model '{model_name}': {exc}. "
            f"If this is a download error, retry — the download resumes."
        ) from exc

    _model_cache[model_name] = model
    return model


# ============================================================
# PUBLIC
# ============================================================
def transcribe(
    audio_path: str,
    model: str = DEFAULT_MODEL,
    language: Optional[str] = None,
    beam_size: int = 1,
    vad_filter: bool = True,
    dry_run: bool = False,
) -> TranscriptionResult:
    """
    Transcribe a WAV file to text.

    audio_path: path to a .wav file
    model:      whisper model id (default "tiny.en")
    language:   ISO code (e.g. "en") or None for auto-detect
    beam_size:  1 = fastest, 5 = more accurate
    vad_filter: True = skip silence (better for voice commands)
    dry_run:    return a synthetic result without loading the model

    Raises STTError on any failure.
    """
    if not isinstance(audio_path, str) or not audio_path.strip():
        raise STTError("audio_path must be a non-empty string.")
    p = Path(audio_path)
    if not p.exists():
        raise STTError(f"Audio file not found: {audio_path}")
    if p.suffix.lower() != ".wav":
        raise STTError(f"Only .wav files supported, got {p.suffix!r}.")
    if model not in VALID_MODELS:
        raise STTError(
            f"model must be one of {sorted(VALID_MODELS)}, got {model!r}."
        )
    if not isinstance(beam_size, int) or not (1 <= beam_size <= 10):
        raise STTError("beam_size must be an integer between 1 and 10.")

    if dry_run:
        return TranscriptionResult(
            text="[dry run] this is a synthetic transcription",
            language=language or "en",
            duration_seconds=0.0,
            model=model,
        )

    whisper = _ensure_model(model)

    try:
        segments, info = whisper.transcribe(
            str(p),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
        )
        # segments is a generator; iterate to get text
        text_parts: list[str] = []
        for seg in segments:
            if seg.text:
                text_parts.append(seg.text.strip())
        text = " ".join(text_parts).strip()

        duration = float(getattr(info, "duration", 0.0) or 0.0)
        detected_lang = getattr(info, "language", None) or language

        return TranscriptionResult(
            text=text,
            language=detected_lang,
            duration_seconds=duration,
            model=model,
        )
    except Exception as exc:
        raise STTError(f"Transcription failed: {exc}") from exc


def model_is_cached(model: str = DEFAULT_MODEL) -> bool:
    """
    True if the model is already downloaded and cached locally.
    Checks the HuggingFace cache directory.
    """
    if model in _model_cache:
        return True
    home = Path(os.path.expanduser("~"))
    cache = home / ".cache" / "huggingface" / "hub"
    if not cache.exists():
        return False
    # The folder is: models--Systran--faster-whisper-<model>
    prefix = f"models--Systran--faster-whisper-{model}"
    for entry in cache.iterdir():
        if entry.is_dir() and entry.name == prefix:
            return True
    return False


def clear_model_cache() -> None:
    """Clear the in-process model cache (does NOT delete files on disk)."""
    _model_cache.clear()