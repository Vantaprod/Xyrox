"""
Xyrox — Voice Pipeline (Phase 6.4)

End-to-end orchestration:

    1. (Optional) record a short clip from the mic
    2. STT: transcribe
    3. Wake word: check for the configured phrase
    4. Speaker verify (optional): confirm the speaker
    5. Agent: run the command through the conversational agent
    6. TTS: speak the reply (optional)

Every stage is optional and clearly recorded in the result so the
caller knows what happened. Nothing is fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from app.backend.voice.audio_io import record_wav, AudioIOError
from app.backend.voice.stt import transcribe, STTError
from app.backend.voice.speaker import verify as verify_speaker, SpeakerError
from app.backend.voice.tts import speak, TTSError
from app.backend.voice.wake_word import detect_wake, WakeMatch


@dataclass
class VoiceResult:
    transcript: str = ""
    wake_matched: bool = False
    wake_phrase: Optional[str] = None
    command: str = ""
    speaker_matched: Optional[bool] = None
    speaker_similarity: Optional[float] = None
    agent_response: str = ""
    spoke_reply: bool = False
    audio_path: Optional[str] = None
    errors: list[str] = field(default_factory=list)


def run_voice_command(
    audio_path: Optional[str] = None,
    record_seconds: float = 4.0,
    wake_phrases: Optional[list[str]] = None,
    require_wake_word: bool = True,
    speaker_profile: Optional[str] = None,
    speaker_threshold: float = 0.75,
    require_speaker_match: bool = False,
    agent_factory=None,
    dry_run: bool = False,
    speak_reply: bool = True,
) -> VoiceResult:
    """
    Run one voice command end-to-end.

    audio_path:      if given, use this WAV; else record from mic
    record_seconds:  mic recording length when audio_path is None
    wake_phrases:    override default wake phrases
    require_wake_word: if True and no wake word, stop after STT
    speaker_profile: name of enrolled profile to verify against
    require_speaker_match: if True and verification fails, stop
    agent_factory:   callable() -> agent with .chat(str) -> result-like
                     If None, a default agent is built lazily.
    dry_run:         skip mic, STT model, speaker model, and TTS
    speak_reply:     if True, TTS the reply

    Returns a VoiceResult. Never raises for user-level issues;
    those go into .errors.
    """
    result = VoiceResult()

    # ---- 1. Get audio ----
    if audio_path is None:
        if dry_run:
            result.errors.append("dry_run: no audio captured.")
            return result
        try:
            rec = record_wav(record_seconds)
            audio_path = rec["path"]
            result.audio_path = audio_path
        except AudioIOError as exc:
            result.errors.append(f"recording failed: {exc}")
            return result
    else:
        result.audio_path = audio_path

    # ---- 2. STT ----
    try:
        tr = transcribe(audio_path, dry_run=dry_run)
        result.transcript = tr.text
    except STTError as exc:
        result.errors.append(f"transcription failed: {exc}")
        return result

    if not result.transcript.strip():
        result.errors.append("no speech detected.")
        return result

    # ---- 3. Wake word ----
    wm: WakeMatch = detect_wake(result.transcript, wake_phrases)
    result.wake_matched = wm.matched
    result.wake_phrase = wm.wake_phrase
    result.command = wm.command or (result.transcript if not require_wake_word else "")

    if require_wake_word and not wm.matched:
        result.errors.append("wake word not present.")
        return result

    # If wake matched but no command followed, nothing to do
    if require_wake_word and not wm.command.strip():
        result.errors.append("wake word present but no command followed.")
        return result

    # ---- 4. Speaker verification (optional) ----
    if speaker_profile:
        try:
            vr = verify_speaker(
                speaker_profile, audio_path,
                threshold=speaker_threshold, dry_run=dry_run,
            )
            result.speaker_matched = vr.matched
            result.speaker_similarity = vr.similarity
            if require_speaker_match and not vr.matched:
                result.errors.append(
                    f"speaker verification failed "
                    f"(similarity={vr.similarity}, threshold={vr.threshold})"
                )
                return result
        except SpeakerError as exc:
            result.errors.append(f"speaker verification failed: {exc}")
            if require_speaker_match:
                return result

    # ---- 5. Agent ----
    command = result.command.strip()
    if not command:
        result.errors.append("empty command after wake word.")
        return result

    try:
        if agent_factory is None:
            # Lazy import to avoid the heavy agent import during tests
            from app.backend.agents.agent import Agent
            agent = Agent()
        else:
            agent = agent_factory()
        agent_result = agent.chat(command)
        result.agent_response = getattr(agent_result, "final_message", "") or ""
    except Exception as exc:
        result.errors.append(f"agent failed: {exc}")
        return result

    # ---- 6. TTS ----
    if speak_reply and result.agent_response:
        try:
            speak(result.agent_response, dry_run=dry_run)
            result.spoke_reply = True
        except TTSError as exc:
            result.errors.append(f"tts failed: {exc}")

    return result


def voice_result_to_dict(r: VoiceResult) -> dict:
    return asdict(r)