"""
Xyrox — Voice Pipeline Tests (Phase 6.4)

Uses dry_run mode + synthetic WAVs. No mic, no model, no TTS.
Real-agent tests are handled in the integration suite.
"""

import numpy as np
import pytest

from app.backend.voice.pipeline import run_voice_command, VoiceResult


@pytest.fixture
def silent_wav(tmp_path):
    import soundfile as sf
    p = tmp_path / "silent.wav"
    sr = 16000
    sf.write(str(p), np.zeros(sr, dtype=np.float32), sr)
    return str(p)


# ============================================================
# DRY RUN
# ============================================================
def test_dry_run_no_audio_returns_error():
    r = run_voice_command(dry_run=True)
    assert isinstance(r, VoiceResult)
    assert "dry_run" in r.errors[0]


def test_pipeline_dry_run_transcribe(silent_wav):
    r = run_voice_command(audio_path=silent_wav, dry_run=True)
    # Dry-run STT returns a synthetic string containing "[dry run]"
    assert "[dry run]" in r.transcript


# ============================================================
# WAKE WORD GATE
# ============================================================
def test_no_wake_word_stops_pipeline(silent_wav, monkeypatch):
    # Force STT to return a transcript WITHOUT the wake word
    import app.backend.voice.pipeline as p
    monkeypatch.setattr(
        p, "transcribe",
        lambda *a, **k: type("R", (), {
            "text": "just a normal sentence",
            "language": "en",
            "duration_seconds": 1.0,
            "model": "tiny.en",
        })(),
    )
    r = run_voice_command(
        audio_path=silent_wav, dry_run=True, require_wake_word=True,
    )
    assert not r.wake_matched
    assert "wake word" in " ".join(r.errors).lower()


def test_wake_word_present_passes_gate(silent_wav, monkeypatch):
    import app.backend.voice.pipeline as p
    monkeypatch.setattr(
        p, "transcribe",
        lambda *a, **k: type("R", (), {
            "text": "hey xyrox what is the time",
            "language": "en",
            "duration_seconds": 1.0,
            "model": "tiny.en",
        })(),
    )

    class FakeAgent:
        def chat(self, msg):
            return type("A", (), {"final_message": f"echo: {msg}"})()

    r = run_voice_command(
        audio_path=silent_wav,
        dry_run=True,
        require_wake_word=True,
        agent_factory=lambda: FakeAgent(),
        speak_reply=False,
    )
    assert r.wake_matched is True
    assert r.command == "what is the time"
    assert "echo: what is the time" in r.agent_response


# ============================================================
# SPeaker verification flow
# ============================================================
def test_speaker_verification_skips_when_no_profile(silent_wav, monkeypatch):
    import app.backend.voice.pipeline as p
    monkeypatch.setattr(
        p, "transcribe",
        lambda *a, **k: type("R", (), {
            "text": "hey xyrox hello",
            "language": "en",
            "duration_seconds": 1.0,
            "model": "tiny.en",
        })(),
    )

    class FakeAgent:
        def chat(self, msg):
            return type("A", (), {"final_message": "ok"})()

    r = run_voice_command(
        audio_path=silent_wav, dry_run=True,
        agent_factory=lambda: FakeAgent(),
        speak_reply=False,
    )
    # No profile → no speaker check
    assert r.speaker_matched is None
    assert r.agent_response == "ok"