"""Xyrox — Speaker Verification Tests (Phase 6.3)"""

import numpy as np
import pytest

from app.backend.voice import speaker as sp
from app.backend.voice.speaker import (
    enroll, verify, list_profiles, delete_profile,
    SpeakerError, VerificationResult,
)


@pytest.fixture(autouse=True)
def isolated_profiles(tmp_path, monkeypatch):
    tmp = tmp_path / "profiles"
    monkeypatch.setattr(sp, "PROFILES_DIR", tmp)
    yield tmp


@pytest.fixture
def three_wavs(tmp_path):
    import soundfile as sf
    sr = 16000
    paths = []
    for i in range(3):
        p = tmp_path / f"s{i}.wav"
        t = np.linspace(0, 1.0, sr, endpoint=False)
        sig = (0.2 * np.sin(2 * np.pi * (200 + 50 * i) * t)).astype(np.float32)
        sf.write(str(p), sig, sr)
        paths.append(str(p))
    return paths


def test_enroll_dry_run_creates_profile(three_wavs):
    r = enroll("joseph", three_wavs, dry_run=True)
    assert r["profile"] == "joseph"
    assert r["samples"] == 3
    from pathlib import Path
    assert Path(r["path"]).exists()


def test_enroll_rejects_empty_profile(three_wavs):
    with pytest.raises(SpeakerError):
        enroll("", three_wavs, dry_run=True)


def test_enroll_rejects_too_few_samples(three_wavs):
    with pytest.raises(SpeakerError):
        enroll("joseph", three_wavs[:2], dry_run=True)


def test_verify_same_profile_matches(three_wavs):
    enroll("joseph", three_wavs, dry_run=True)
    result = verify("joseph", three_wavs[0], dry_run=True)
    assert isinstance(result, VerificationResult)
    assert 0.0 <= result.similarity <= 1.0


def test_verify_missing_profile_raises(three_wavs):
    with pytest.raises(SpeakerError):
        verify("nonexistent", three_wavs[0], dry_run=True)


def test_verify_rejects_bad_threshold(three_wavs):
    enroll("joseph", three_wavs, dry_run=True)
    with pytest.raises(SpeakerError):
        verify("joseph", three_wavs[0], threshold=1.5, dry_run=True)


def test_list_profiles_empty(isolated_profiles):
    assert list_profiles() == []


def test_list_profiles_after_enroll(three_wavs):
    enroll("joseph", three_wavs, dry_run=True)
    profiles = list_profiles()
    assert len(profiles) == 1
    assert profiles[0]["profile"] == "joseph"


def test_delete_profile(three_wavs):
    enroll("joseph", three_wavs, dry_run=True)
    assert delete_profile("joseph") is True
    assert list_profiles() == []


def test_delete_missing_profile(isolated_profiles):
    assert delete_profile("nobody") is False