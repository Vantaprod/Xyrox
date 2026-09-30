"""
Xyrox — Voice API (Phase 6.4)

Endpoints:
    POST /api/v1/voice/transcribe     — WAV → text
    POST /api/v1/voice/enroll         — enroll a speaker profile
    GET  /api/v1/voice/profiles       — list enrolled profiles
    DELETE /api/v1/voice/profiles/{n} — delete a profile
    POST /api/v1/voice/command        — WAV → full pipeline (STT →
                                        verify → agent → TTS reply text)

All endpoints require authentication. Audio is provided as base64
so clients can send it over JSON. Files are written to a temp path,
processed, then deleted.
"""

import base64
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from app.backend.api.deps import get_current_user
from app.backend.models.models import User
from app.backend.schemas.voice import (
    VoiceTranscribeRequest,
    VoiceTranscribeResponse,
    VoiceEnrollRequest,
    VoiceEnrollResponse,
    VoiceCommandResponse,
    ProfileInfo,
)
from app.backend.voice.stt import transcribe, STTError
from app.backend.voice.speaker import (
    enroll, list_profiles, delete_profile, SpeakerError,
)
from app.backend.voice.pipeline import run_voice_command, voice_result_to_dict


router = APIRouter(prefix="/voice", tags=["voice"])


def _write_temp_wav(audio_base64: str) -> Path:
    """Decode base64 WAV into a temp file. Returns the path."""
    try:
        data = base64.b64decode(audio_base64, validate=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"audio_base64 is not valid base64: {exc}",
        )
    if len(data) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="audio too short.",
        )
    tmp = tempfile.NamedTemporaryFile(
        suffix=".wav", delete=False,
    )
    try:
        tmp.write(data)
        tmp.close()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"cannot write temp file: {exc}",
        )
    return Path(tmp.name)


# ============================================================
# TRANSCRIBE
# ============================================================
@router.post("/transcribe", response_model=VoiceTranscribeResponse)
def transcribe_endpoint(
    payload: VoiceTranscribeRequest,
    _user: User = Depends(get_current_user),
) -> VoiceTranscribeResponse:
    path = _write_temp_wav(payload.audio_base64)
    try:
        result = transcribe(str(path), language=payload.language)
    except STTError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    return VoiceTranscribeResponse(
        text=result.text,
        language=result.language,
        duration_seconds=result.duration_seconds,
        model=result.model,
    )


# ============================================================
# ENROLL
# ============================================================
@router.post("/enroll", response_model=VoiceEnrollResponse)
def enroll_endpoint(
    payload: VoiceEnrollRequest,
    _user: User = Depends(get_current_user),
) -> VoiceEnrollResponse:
    try:
        result = enroll(payload.profile, payload.sample_paths)
    except SpeakerError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return VoiceEnrollResponse(**result)


# ============================================================
# PROFILES
# ============================================================
@router.get("/profiles", response_model=list[ProfileInfo])
def list_profiles_endpoint(
    _user: User = Depends(get_current_user),
) -> list[ProfileInfo]:
    return [ProfileInfo(**p) for p in list_profiles()]


@router.delete("/profiles/{name}")
def delete_profile_endpoint(
    name: str,
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        removed = delete_profile(name)
    except SpeakerError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    return {"deleted": removed, "profile": name}


# ============================================================
# FULL VOICE COMMAND
# ============================================================
@router.post("/command", response_model=VoiceCommandResponse)
def voice_command_endpoint(
    payload: VoiceTranscribeRequest,
    _user: User = Depends(get_current_user),
) -> VoiceCommandResponse:
    path = _write_temp_wav(payload.audio_base64)
    try:
        result = run_voice_command(
            audio_path=str(path),
            require_wake_word=True,
            speak_reply=False,   # server has no speakers
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"voice pipeline failed: {exc}",
        )
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    return VoiceCommandResponse(
        transcript=result.transcript,
        wake_matched=result.wake_matched,
        wake_phrase=result.wake_phrase,
        command=result.command,
        speaker_matched=result.speaker_matched,
        speaker_similarity=result.speaker_similarity,
        agent_response=result.agent_response,
        spoke_reply=result.spoke_reply,
        errors=result.errors,
        timestamp=datetime.now(timezone.utc),
    )