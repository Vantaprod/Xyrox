"""
Xyrox — Audio I/O Tests (Phase 6.1)

Tests device enumeration (safe on any machine) and WAV reading with a
synthetic file. Recording tests are SKIPPED if no microphone is present.
"""

import wave
import numpy as np
import pytest

from app.backend.voice.audio_io import (
    list_devices,
    list_input_devices,
    list_output_devices,
    has_microphone,
    record_wav,
    read_wav,
    AudioIOError,
)


# ============================================================
# ENUMERATION — safe everywhere
# ============================================================
def test_list_devices_returns_list():
    devices = list_devices()
    assert isinstance(devices, list)
    # Every device has an index and a name
    for d in devices:
        assert isinstance(d.index, int)
        assert isinstance(d.name, str)
        assert d.channels_in >= 0
        assert d.channels_out >= 0


def test_list_input_and_output_are_disjoint_categories():
    ins = list_input_devices()
    outs = list_output_devices()
    for d in ins:
        assert d.channels_in > 0
    for d in outs:
        assert d.channels_out > 0


def test_has_microphone_returns_bool():
    result = has_microphone()
    assert isinstance(result, bool)


# ============================================================
# WAV READ — synthetic file, always works
# ============================================================
def test_read_wav_synthetic(tmp_path):
    # Write a 0.5-second sine wave manually
    sr = 16000
    duration = 0.5
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    signal = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    path = tmp_path / "tone.wav"
    import soundfile as sf
    sf.write(str(path), signal, sr)

    result = read_wav(str(path))
    assert result["sample_rate"] == sr
    assert result["channels"] == 1
    assert isinstance(result["audio"], np.ndarray)
    assert result["audio"].shape[0] > 0


def test_read_wav_missing_file(tmp_path):
    with pytest.raises(AudioIOError):
        read_wav(str(tmp_path / "does_not_exist.wav"))


# ============================================================
# RECORDING — skip if no mic
# ============================================================
def test_record_wav_requires_microphone(tmp_path):
    if not has_microphone():
        pytest.skip("No microphone detected on this system.")
    out = tmp_path / "test_rec.wav"
    result = record_wav(seconds=1.0, output_path=str(out))
    assert out.exists()
    assert out.stat().st_size > 0
    assert result["seconds"] == 1.0
    assert result["sample_rate"] == 16000


def test_record_wav_rejects_bad_duration(tmp_path):
    with pytest.raises(AudioIOError):
        record_wav(seconds=0.5, output_path=str(tmp_path / "x.wav"))
    with pytest.raises(AudioIOError):
        record_wav(seconds=200.0, output_path=str(tmp_path / "x.wav"))


def test_record_wav_rejects_bad_sample_rate(tmp_path):
    with pytest.raises(AudioIOError):
        record_wav(seconds=1.0, sample_rate=100, output_path=str(tmp_path / "x.wav"))


def test_record_wav_rejects_bad_channels(tmp_path):
    with pytest.raises(AudioIOError):
        record_wav(seconds=1.0, channels=3, output_path=str(tmp_path / "x.wav"))