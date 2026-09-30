"""Xyrox — Telegram API Schemas (Phase 7.1)"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class TelegramStatusResponse(BaseModel):
    configured: bool
    bot_token_present: bool
    allowed_chat_ids: list[int]
    whitelist_enabled: bool


class TelegramSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_id: int = Field(...)
    text: str = Field(min_length=1, max_length=4000)
    require_approval: bool = True


class TelegramDraftResponse(BaseModel):
    draft_id: int
    chat_id: int
    text: str
    status: str          # pending | sent | cancelled | error
    created_at: datetime


class TelegramApproveResponse(BaseModel):
    draft_id: int
    sent: bool
    telegram_message_id: Optional[int] = None
    error: Optional[str] = None