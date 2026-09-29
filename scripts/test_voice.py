"""
Manual voice test — Phase 6.2 verification.

Records 3 seconds from the default microphone, transcribes it with
faster-whisper, and prints what was heard.

Run:
    python scripts\test_voice.py
"""

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

    print("Transcribing (this may take 5-15s on first run)...")
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