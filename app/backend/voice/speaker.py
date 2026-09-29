"""
Xyrox — Speaker Verification (Phase 6.3)

Enrolls a user's voice from N samples, stores the centroid embedding,
and verifies future recordings against it.

Design rules (Master Command §8):
- Speaker verification is NOT biometric-grade security.
- Confidence is reported; uncertainty is surfaced, not hidden.
- Enrolled profiles are stored per-user as .npz files.
- Dry-run mode for tests without model download.
- Threshold is configurable; default is conservative.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np


class SpeakerError(Exception):
    """Raised when speaker verification fails."""
    pass


@dataclass
class VerificationResult:
    matched: bool
    similarity: float
    threshold: float
    confidence: str          # high | medium | low
    profile: str


# ============================================================
# CONFIG
# ============================================================
PROFILES_DIR = Path("data") / "voice" / "speaker_profiles"
DEFAULT_THRESHOLD = 0.75          # cosine similarity
MIN_ENROLLMENT_SAMPLES = 3
MAX_ENROLLMENT_SAMPLES = 20

# In-process embedder cache (resemblyzer loads a PyTorch model)
_encoder = None
_encoder_loaded = False


# ============================================================
# INTERNAL
# ============================================================
def _ensure_encoder(dry_run: bool):
    global _encoder, _encoder_loaded
    if dry_run:
        return None
    if _encoder_loaded:
        return _encoder
    try:
        from resemblyzer import VoiceEncoder
    except Exception as exc:
        raise SpeakerError(
            f"resemblyzer is not installed: {exc}. "
            f"Run: pip install resemblyzer"
        ) from exc
    try:
        _encoder = VoiceEncoder()
    except Exception as exc:
        raise SpeakerError(f"Failed to load VoiceEncoder: {exc}") from exc
    _encoder_loaded = True
    return _encoder


def _embed_wav(path: str, dry_run: bool) -> np.ndarray:
    """Return a 256-d speaker embedding for a WAV file."""
    if dry_run:
        # Deterministic synthetic embedding for tests
        rng = np.random.default_rng(seed=hash(path) & 0xFFFFFFFF)
        v = rng.standard_normal(256).astype(np.float32)
        return v / np.linalg.norm(v)

    try:
        from resemblyzer import preprocess_wav
    except Exception as exc:
        raise SpeakerError(f"resemblyzer preprocess_wav failed: {exc}") from exc

    p = Path(path)
    if not p.exists():
        raise SpeakerError(f"Audio file not found: {path}")

    try:
        wav = preprocess_wav(str(p))
    except Exception as exc:
        raise SpeakerError(f"Audio preprocessing failed: {exc}") from exc

    if wav is None or len(wav) < 1600:  # less than 0.1s at 16kHz
        raise SpeakerError("Audio too short for speaker embedding.")

    encoder = _ensure_encoder(dry_run=False)
    try:
        emb = encoder.embed_utterance(wav)
    except Exception as exc:
        raise SpeakerError(f"Embedding failed: {exc}") from exc

    if emb is None or emb.shape[0] == 0:
        raise SpeakerError("Encoder returned an empty embedding.")

    return emb.astype(np.float32)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _profile_path(profile: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in profile)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return PROFILES_DIR / f"{safe}.npz"


def _confidence_from_similarity(sim: float, threshold: float) -> str:
    """
    Map similarity to a confidence level.
    Honest semantics: we describe how clearly above/below the
    threshold the score is, not pretend it is a probability.
    """
    if sim >= threshold + 0.10:
        return "high"
    if sim >= threshold:
        return "medium"
    if sim >= threshold - 0.10:
        return "low"
    return "low"


# ============================================================
# PUBLIC
# ============================================================
def enroll(
    profile: str,
    sample_paths: list[str],
    dry_run: bool = False,
) -> dict:
    """
    Enroll a voice profile from N WAV samples.

    profile:       name of the profile (e.g. "joseph")
    sample_paths:  3 to 20 paths to WAV files, each 3+ seconds
    dry_run:       skip model; store synthetic embeddings for tests

    Returns {"profile": str, "samples": int, "path": str,
             "created_at": str}.
    Raises SpeakerError on any failure.
    """
    if not isinstance(profile, str) or not profile.strip():
        raise SpeakerError("profile must be a non-empty string.")
    if not isinstance(sample_paths, list):
        raise SpeakerError("sample_paths must be a list.")
    if len(sample_paths) < MIN_ENROLLMENT_SAMPLES:
        raise SpeakerError(
            f"at least {MIN_ENROLLMENT_SAMPLES} samples required, "
            f"got {len(sample_paths)}."
        )
    if len(sample_paths) > MAX_ENROLLMENT_SAMPLES:
        raise SpeakerError(
            f"at most {MAX_ENROLLMENT_SAMPLES} samples allowed."
        )
    for p in sample_paths:
        if not isinstance(p, str):
            raise SpeakerError("every sample path must be a string.")

    embeddings: list[np.ndarray] = []
    for p in sample_paths:
        emb = _embed_wav(p, dry_run=dry_run)
        embeddings.append(emb)

    stacked = np.stack(embeddings, axis=0)
    centroid = np.mean(stacked, axis=0)
    # Normalize
    norm = np.linalg.norm(centroid)
    if norm == 0:
        raise SpeakerError("Centroid embedding is zero-length.")
    centroid = centroid / norm

    path = _profile_path(profile)
    np.savez(
        str(path),
        centroid=centroid,
        samples_count=len(sample_paths),
        created_at=datetime.now(timezone.utc).isoformat(),
        profile_name=profile,
    )

    return {
        "profile": profile,
        "samples": len(sample_paths),
        "path": str(path.resolve()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def verify(
    profile: str,
    audio_path: str,
    threshold: float = DEFAULT_THRESHOLD,
    dry_run: bool = False,
) -> VerificationResult:
    """
    Verify whether the given WAV matches the enrolled profile.

    Returns a VerificationResult. Never raises on mismatch — only
    on system errors (missing profile, bad audio, encoder failure).
    """
    if not isinstance(profile, str) or not profile.strip():
        raise SpeakerError("profile must be a non-empty string.")
    if not isinstance(audio_path, str) or not audio_path.strip():
        raise SpeakerError("audio_path must be a non-empty string.")
    if not (0.0 <= threshold <= 1.0):
        raise SpeakerError("threshold must be between 0.0 and 1.0.")

    path = _profile_path(profile)
    if not path.exists():
        raise SpeakerError(
            f"No enrolled profile named '{profile}'. "
            f"Enroll first with enroll()."
        )

    try:
        data = np.load(str(path), allow_pickle=False)
        centroid = data["centroid"]
    except Exception as exc:
        raise SpeakerError(f"Cannot load profile: {exc}") from exc

    emb = _embed_wav(audio_path, dry_run=dry_run)
    sim = _cosine(centroid, emb)
    matched = sim >= threshold
    conf = _confidence_from_similarity(sim, threshold)

    return VerificationResult(
        matched=matched,
        similarity=round(sim, 4),
        threshold=threshold,
        confidence=conf,
        profile=profile,
    )


def list_profiles() -> list[dict]:
    """Return every enrolled profile's metadata (no embeddings)."""
    if not PROFILES_DIR.exists():
        return []
    out: list[dict] = []
    for f in PROFILES_DIR.glob("*.npz"):
        try:
            data = np.load(str(f), allow_pickle=False)
            out.append({
                "profile": str(data.get("profile_name", f.stem)),
                "samples": int(data.get("samples_count", 0)),
                "created_at": str(data.get("created_at", "")),
                "path": str(f.resolve()),
            })
        except Exception:
            continue
    return out


def delete_profile(profile: str) -> bool:
    """Delete an enrolled profile. Returns True if it existed."""
    path = _profile_path(profile)
    if path.exists():
        try:
            path.unlink()
            return True
        except Exception as exc:
            raise SpeakerError(f"Cannot delete profile: {exc}") from exc
    return False