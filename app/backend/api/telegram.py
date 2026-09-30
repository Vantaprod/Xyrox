"""
Xyrox — Telegram API (Phase 7.1)

Endpoints:
    GET  /api/v1/telegram/status          — configuration status
    POST /api/v1/telegram/send            — queue (or send) a message
    GET  /api/v1/telegram/pending         — list pending drafts
    POST /api/v1/telegram/approve/{id}    — send a queued draft

Every endpoint requires authentication. Outbound messages are
queued by default and only sent after explicit approval.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.backend.api.deps import get_current_user
from app.backend.models.models import PendingOutbound, User
from app.backend.schemas.telegram import (
    TelegramStatusResponse,
    TelegramSendRequest,
    TelegramDraftResponse,
    TelegramApproveResponse,
)
from app.backend.integrations import telegram as tg
from app.backend.database.db import SessionLocal


router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get("/status", response_model=TelegramStatusResponse)
def status_endpoint(
    _user: User = Depends(get_current_user),
) -> TelegramStatusResponse:
    allowed_raw = (tg.settings.TELEGRAM_ALLOWED_CHAT_IDS or "").strip()
    allowed = []
    for p in allowed_raw.split(","):
        p = p.strip()
        if p.lstrip("-").isdigit():
            allowed.append(int(p))
    return TelegramStatusResponse(
        configured=tg.is_configured(),
        bot_token_present=bool((tg.settings.TELEGRAM_BOT_TOKEN or "").strip()),
        allowed_chat_ids=allowed,
        whitelist_enabled=bool(allowed),
    )


@router.post("/send", response_model=TelegramDraftResponse)
def send_endpoint(
    payload: TelegramSendRequest,
    _user: User = Depends(get_current_user),
) -> TelegramDraftResponse:
    if not tg.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram NOT CONFIGURED — set TELEGRAM_BOT_TOKEN in .env.",
        )
    if not tg.is_authorized(payload.chat_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"chat_id {payload.chat_id} is not in the whitelist.",
        )

    if not payload.require_approval:
        try:
            tg.send_message(payload.chat_id, payload.text)
        except tg.TelegramError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return TelegramDraftResponse(
            draft_id=0,
            chat_id=payload.chat_id,
            text=payload.text,
            status="sent",
            created_at=datetime.now(timezone.utc),
        )

    db = SessionLocal()
    try:
        row = PendingOutbound(
            channel="telegram",
            recipient=str(payload.chat_id),
            content=payload.text,
            status="pending",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return TelegramDraftResponse(
            draft_id=row.id,
            chat_id=payload.chat_id,
            text=payload.text,
            status=row.status,
            created_at=row.created_at,
        )
    finally:
        db.close()


@router.get("/pending", response_model=list[TelegramDraftResponse])
def list_pending(
    _user: User = Depends(get_current_user),
) -> list[TelegramDraftResponse]:
    db = SessionLocal()
    try:
        rows = (
            db.query(PendingOutbound)
            .filter_by(channel="telegram", status="pending")
            .order_by(PendingOutbound.created_at.desc())
            .all()
        )
        return [
            TelegramDraftResponse(
                draft_id=r.id,
                chat_id=int(r.recipient),
                text=r.content,
                status=r.status,
                created_at=r.created_at,
            )
            for r in rows
        ]
    finally:
        db.close()


@router.post("/approve/{draft_id}", response_model=TelegramApproveResponse)
def approve_endpoint(
    draft_id: int,
    _user: User = Depends(get_current_user),
) -> TelegramApproveResponse:
    db = SessionLocal()
    try:
        row = db.query(PendingOutbound).filter_by(id=draft_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Draft not found.")
        if row.channel != "telegram":
            raise HTTPException(status_code=400, detail="Not a Telegram draft.")
        if row.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Draft is not pending (status={row.status}).",
            )
        try:
            sent = tg.send_message(int(row.recipient), row.content)
            row.status = "sent"
            row.sent_at = datetime.now(timezone.utc)
            db.commit()
            return TelegramApproveResponse(
                draft_id=row.id,
                sent=True,
                telegram_message_id=sent.get("message_id"),
            )
        except tg.TelegramError as exc:
            row.status = "error"
            row.error = str(exc)
            db.commit()
            return TelegramApproveResponse(
                draft_id=row.id,
                sent=False,
                error=str(exc),
            )
    finally:
        db.close()