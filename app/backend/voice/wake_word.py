"""
Xyrox — Wake Word Detection (Phase 6.4)

Simple text-based wake-word matching. We deliberately chose NOT to
use a neural wake-word engine (Porcupine, OpenWakeWord) to avoid
extra downloads and model training.

How it works:
- The pipeline records short clips (1-2 seconds) on a loop.
- Each clip is transcribed by STT.
- If the transcript STARTS WITH the configured wake phrase,
  the wake word fires and the remainder becomes the command.

This is honest: the wake word is a text match, not a magic always-on
listener. It has a small latency and a small false-positive rate.

Design rules:
- Configurable phrase (default: "hey xyrox").
- Case-insensitive, punctuation-tolerant.
- Strips the wake phrase from the returned command.
- Returns None when no wake word present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


DEFAULT_WAKE_PHRASES = [
    "hey xyrox",
    "hi xyrox",
    "ok xyrox",
    "okay xyrox",
    "xyrox",
]


@dataclass
class WakeMatch:
    matched: bool
    wake_phrase: Optional[str]
    command: str


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    if not isinstance(text, str):
        return ""
    t = text.lower().strip()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def detect_wake(
    transcript: str,
    wake_phrases: Optional[list[str]] = None,
) -> WakeMatch:
    """
    Check whether `transcript` begins with a wake phrase.

    Returns a WakeMatch. If matched is True, command contains the
    text AFTER the wake phrase (may be empty). If matched is False,
    command contains the full normalized transcript for context.
    """
    if not isinstance(transcript, str):
        raise TypeError("transcript must be a string.")

    if wake_phrases is None:
        phrases = DEFAULT_WAKE_PHRASES
    else:
        if not isinstance(wake_phrases, list) or not wake_phrases:
            raise ValueError("wake_phrases must be a non-empty list if provided.")
        phrases = wake_phrases

    normalized = _normalize(transcript)
    if not normalized:
        return WakeMatch(matched=False, wake_phrase=None, command="")

    # Try longest phrases first to avoid partial matches
    sorted_phrases = sorted(
        [_normalize(p) for p in phrases],
        key=len,
        reverse=True,
    )
    for phrase in sorted_phrases:
        if not phrase:
            continue
        if normalized == phrase:
            return WakeMatch(matched=True, wake_phrase=phrase, command="")
        if normalized.startswith(phrase + " "):
            remainder = normalized[len(phrase):].strip()
            return WakeMatch(
                matched=True, wake_phrase=phrase, command=remainder,
            )
    return WakeMatch(matched=False, wake_phrase=None, command=normalized)