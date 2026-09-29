"""
Xyrox — Voice Package (Phase 6)

Voice is a first-class subsystem:
  - TTS: text-to-speech via Windows SAPI5 (offline, zero cost)
  - Audio I/O: microphone recording + device enumeration
  - (Phase 6.2) STT: speech-to-text
  - (Phase 6.3) Speaker verification
  - (Phase 6.4) Full pipeline + wake word + API endpoint

Design rules:
- No downloads for TTS — Windows built-in voices.
- No fake successes — if audio is not available, we raise clearly.
- All voice ops must be testable in dry_run mode (no audio hardware).
- Nothing happens silently.
"""