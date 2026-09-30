"""
Xyrox — Telegram Tools (Phase 7.1)

Tools the AI can call to interact with Telegram.
Every send is queued for user approval by default (Master Command §25).
"""

from typing import Optional

from app.backend.config import settings
from app.backend.database.db import SessionLocal
from app.backend.models.models import PendingOutbound
from app.backend.integrations import telegram as tg
from app.backend.tools.base import Tool, ToolValidationError
from app.backend.tools.registry import ToolRegistry


# ============================================================
# TOOL FUNCTIONS
# ============================================================
def send_telegram_message(
    chat_id: int,
    text: str,
    require_approval: bool = True,
    **extra,
) -> dict:
    if extra:
        raise ToolValidationError(
            f"send_telegram_message got unexpected args: {sorted(extra)}"
        )
    if not tg.is_configured():
        raise ToolValidationError(
            "Telegram is NOT CONFIGURED. Add TELEGRAM_BOT_TOKEN to .env."
        )
    if not isinstance(chat_id, int):
        raise ToolValidationError("chat_id must be an integer.")
    if not isinstance(text, str) or not text.strip():
        raise ToolValidationError("text must be a non-empty string.")
    if not tg.is_authorized(chat_id):
        raise ToolValidationError(
            f"chat_id {chat_id} is not in the whitelist."
        )

    if not require_approval:
        try:
            sent = tg.send_message(chat_id, text)
            return {
                "sent": True,
                "chat_id": chat_id,
                "message_id": sent.get("message_id"),
            }
        except tg.TelegramError as exc:
            raise ToolValidationError(f"Telegram send failed: {exc}") from exc

    # Queue for approval
    db = SessionLocal()
    try:
        row = PendingOutbound(
            channel="telegram",
            recipient=str(chat_id),
            content=text,
            status="pending",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "queued": True,
            "draft_id": row.id,
            "chat_id": chat_id,
            "text": text,
            "status": row.status,
            "note": (
                "Awaiting user approval at "
                "POST /api/v1/telegram/approve/{draft_id}."
            ),
        }
    finally:
        db.close()


def read_telegram_updates(offset: int = 0, timeout: int = 5, **extra) -> dict:
    if extra:
        raise ToolValidationError("read_telegram_updates got unexpected args.")
    if not tg.is_configured():
        raise ToolValidationError("Telegram is NOT CONFIGURED.")
    try:
        messages = tg.get_updates(offset=offset, timeout=timeout)
    except tg.TelegramError as exc:
        raise ToolValidationError(f"Telegram read failed: {exc}") from exc
    return {
        "count": len(messages),
        "messages": [
            {
                "update_id": m.update_id,
                "chat_id": m.chat_id,
                "from": m.from_name,
                "text": m.text,
                "is_voice": m.is_voice,
                "date": m.date,
            }
            for m in messages
        ],
    }


# ============================================================
# REGISTRATION
# ============================================================
def register_telegram_tools(registry: ToolRegistry) -> None:
    registry.register(Tool(
        name="send_telegram_message",
        description=(
            "Send a Telegram message to a chat. Requires approval by "
            "default — this queues the message for user confirmation "
            "rather than sending immediately. Use only when the user "
            "asks you to message someone on Telegram. Pass the numeric "
            "chat_id. If require_approval is True (default), the message "
            "is queued and the user confirms via the API."
        ),
        parameters={
            "type": "object",
            "properties": {
                "chat_id": {
                    "type": "integer",
                    "description": "Numeric Telegram chat ID.",
                },
                "text": {
                    "type": "string",
                    "description": "Message body, up to 4000 chars.",
                },
                "require_approval": {"type": "boolean"},
            },
            "required": ["chat_id", "text"],
        },
        func=send_telegram_message,
    ))

    registry.register(Tool(
        name="read_telegram_updates",
        description=(
            "Fetch recent Telegram messages sent to Xyrox. Use when the "
            "user asks what people said, or to check for new messages."
        ),
        parameters={
            "type": "object",
            "properties": {
                "offset": {"type": "integer"},
                "timeout": {"type": "integer"},
            },
            "required": [],
        },
        func=read_telegram_updates,
    ))