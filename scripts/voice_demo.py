"""Manual voice demo — Phase 6.4 end-to-end test."""

import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.backend.voice.pipeline import run_voice_command


def main():
    print()
    print("=" * 60)
    print("Recording 4 seconds. Speak clearly.")
    print("Try: 'Hey Xyrox, create a task to call Promise'")
    print("=" * 60)
    print()

    result = run_voice_command(record_seconds=4.0, speak_reply=True)

    print()
    print("-" * 60)
    print("Transcript:       ", result.transcript or "(none)")
    print("Wake word matched:", result.wake_matched)
    print("Wake phrase:      ", result.wake_phrase)
    print("Command:          ", result.command or "(none)")
    print("Agent response:   ", result.agent_response or "(none)")
    print("Spoke reply:      ", result.spoke_reply)
    print("Errors:           ", result.errors if result.errors else "none")
    print("-" * 60)
    print()


if __name__ == "__main__":
    main()