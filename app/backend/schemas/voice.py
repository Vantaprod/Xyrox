"""Xyrox — Voice API Schemas (Phase 6.4)"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class VoiceTranscribeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audio_base64: str = Field(min_length=1)
    language: Optional[str] = None


class VoiceTranscribeResponse(BaseModel):
    text: str
    language: Optional[str]
    duration_seconds: float
    model: str


class VoiceEnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: str = Field(min_length=1, max_length=64)
    sample_paths: list[str] = Field(min_length=3, max_length=20)


class VoiceEnrollResponse(BaseModel):
    profile: str
    samples: int
    path: str
    created_at: str


class VoiceCommandResponse(BaseModel):
    transcript: str
    wake_matched: bool
    wake_phrase: Optional[str] = None
    command: str
    speaker_matched: Optional[bool] = None
    speaker_similarity: Optional[float] = None
    agent_response: str
    spoke_reply: bool
    errors: list[str]
    timestamp: datetime


class ProfileInfo(BaseModel):
    profile: str
    samples: int
    created_at: str
    path: str