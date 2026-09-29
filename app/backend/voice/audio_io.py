"""
Xyrox — Audio I/O (Phase 6.1)

Microphone enumeration and recording. Uses sounddevice (PortAudio
bindings) for capture and soundfile for WAV writing.

Design rules:
- Enumerate real devices; do not guess.
- Recording is explicit (no hidden background capture).
- Recordings are written to data/voice/recordings/ by default.
- If no microphone is present, functions raise clearly.
- Tests can skip if no audio hardware is available.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf


class AudioIOError(Exception):
    """Raised when audio I/O fails."""
    pass


DEFAULT_SAMPLE_RATE = 16000  # 16 kHz — ideal for STT
DEFAULT_CHANNELS = 1
RECORDINGS_DIR = Path("data") / "voice" / "recordings"


@dataclass
class AudioDevice:
    index: int
    name: str
    channels_in: int
    channels_out: int
    default_sample_rate: float
    is_default_input: bool = False
    is_default_output: bool = False


# ============================================================
# ENUMERATION
# ============================================================
def list_devices() -> list[AudioDevice]:
    """
    Return every audio device as an AudioDevice.
    Raises AudioIOError if the audio subsystem cannot be queried.
    """
    try:
        raw = sd.query_devices()
        apis = sd.query_hostapis()
    except Exception as exc:
        raise AudioIOError(f"Cannot query audio devices: {exc}") from exc

    default_in = None
    default_out = None
    try:
        default_in, default_out = sd.default.device
    except Exception:
        pass

    devices: list[AudioDevice] = []
    for i, d in enumerate(raw):
        devices.append(AudioDevice(
            index=i,
            name=str(d.get("name", f"device_{i}")),
            channels_in=int(d.get("max_input_channels", 0)),
            channels_out=int(d.get("max_output_channels", 0)),
            default_sample_rate=float(d.get("default_samplerate", 0.0)),
            is_default_input=(i == default_in),
            is_default_output=(i == default_out),
        ))
    return devices


def list_input_devices() -> list[AudioDevice]:
    """Only devices with at least one input channel."""
    return [d for d in list_devices() if d.channels_in > 0]


def list_output_devices() -> list[AudioDevice]:
    """Only devices with at least one output channel."""
    return [d for d in list_devices() if d.channels_out > 0]


def has_microphone() -> bool:
    """True if any input device exists."""
    try:
        return len(list_input_devices()) > 0
    except AudioIOError:
        return False


# ============================================================
# RECORDING
# ============================================================
def record_wav(
    seconds: float,
    output_path: Optional[str] = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    device: Optional[int] = None,
) -> dict:
    """
    Record `seconds` of audio from the microphone to a WAV file.

    seconds:     1.0 to 120.0
    output_path: if None, writes to data/voice/recordings/rec_<timestamp>.wav
    sample_rate: 8000–48000 (default 16000 — best for STT)
    channels:    1 or 2
    device:      input device index; None uses system default

    Returns: {"path": ..., "seconds": ..., "sample_rate": ..., "channels": ...}
    Raises AudioIOError on any failure.
    """
    if not isinstance(seconds, (int, float)) or not (1.0 <= seconds <= 120.0):
        raise AudioIOError("seconds must be between 1.0 and 120.0.")
    if not isinstance(sample_rate, int) or not (8000 <= sample_rate <= 48000):
        raise AudioIOError("sample_rate must be an integer between 8000 and 48000.")
    if channels not in (1, 2):
        raise AudioIOError("channels must be 1 or 2.")

    if not has_microphone():
        raise AudioIOError("No microphone detected on this system.")

    if output_path is None:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = RECORDINGS_DIR / f"rec_{ts}.wav"
    else:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

    try:
        frames = int(seconds * sample_rate)
        audio = sd.rec(
            frames,
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            device=device,
        )
        sd.wait()
    except Exception as exc:
        raise AudioIOError(f"Recording failed: {exc}") from exc

    # Convert to a 1-D array for mono output clarity, but keep shape
    if audio.ndim == 2 and channels == 1:
        audio = audio[:, 0]

    try:
        sf.write(str(out), audio, sample_rate, subtype="PCM_16")
    except Exception as exc:
        raise AudioIOError(f"Cannot write WAV file: {exc}") from exc

    return {
        "path": str(out.resolve()),
        "seconds": float(seconds),
        "sample_rate": sample_rate,
        "channels": channels,
    }


# ============================================================
# WAV READ (used by STT in Phase 6.2)
# ============================================================
def read_wav(path: str) -> dict:
    """
    Read a WAV file into a numpy array.
    Returns {"audio": np.ndarray, "sample_rate": int, "channels": int}.
    """
    p = Path(path)
    if not p.exists():
        raise AudioIOError(f"File not found: {path}")
    try:
        data, sr = sf.read(str(p), always_2d=False)
    except Exception as exc:
        raise AudioIOError(f"Cannot read WAV: {exc}") from exc

    channels = 1 if data.ndim == 1 else data.shape[1]
    return {
        "audio": np.asarray(data, dtype=np.float32),
        "sample_rate": int(sr),
        "channels": int(channels),
    }