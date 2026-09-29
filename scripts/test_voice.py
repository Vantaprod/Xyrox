"""
Manual voice test — Phase 6.2 verification.

Records 3 seconds from the default microphone, transcribes it with
faster-whisper, and prints what was heard.

Run from project root:
    python scripts\\test_voice.py
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so `app` is importable
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from app.backend.voice.audio_io import record_wav
from app.backend.voice.stt import transcribe


def main() -> None:
    print()
    print("=" * 50)
    print("Recording 3 seconds... speak now.")
    print("Try saying: 'Xyrox create a task'")
    print("=" * 50)
    print()

    rec = record_wav(3.0)
    print("Saved:", rec["path"])
    print()

    print("Transcribing (may take 5-15s)...")
    result = transcribe(rec["path"])

    print()
    print("=" * 50)
    print("You said:", result.text)
    print("Language:", result.language)
    print("Duration:", result.duration_seconds, "seconds")
    print("Model:   ", result.model)
    print("=" * 50)
    print()


if __name__ == "__main__":
    main()