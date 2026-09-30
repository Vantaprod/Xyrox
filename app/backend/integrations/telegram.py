"""
Xyrox — Telegram Bot Client (Phase 7.1)

Minimal HTTP wrapper over the official Telegram Bot API.
No third-party library needed — we use httpx (already installed).

Design rules:
- If TELEGRAM_BOT_TOKEN is missing -> every method raises
  TelegramNotConfigured, which the tools translate to a clear
  "NOT CONFIGURED" response. Never fake success.
- Whitelist enforcement: only chat IDs listed in
  TELEGRAM_ALLOWED_CHAT_IDS are accepted by the poller.
- Outbound sends are done by the poller or by the API layer,
  not directly by the AI tools (which queue for approval).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from app.backend.config import settings


class TelegramError(Exception):
    """Base class for Telegram integration errors."""
    pass


class TelegramNotConfigured(TelegramError):
    """Raised when TELEGRAM_BOT_TOKEN is missing or invalid."""
    pass


API_BASE = "https://api.telegram.org"


@dataclass
class TelegramMessage:
    update_id: int
    chat_id: int
    from_id: Optional[int]
    from_name: Optional[str]
    text: Optional[str]
    voice_file_id: Optional[str]
    is_voice: bool
    date: Optional[int]


def _token() -> str:
    t = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not t:
        raise TelegramNotConfigured(
            "TELEGRAM_BOT_TOKEN is not set. Add it to .env and restart."
        )
    return t


def _allowed_ids() -> set:
    raw = (settings.TELEGRAM_ALLOWED_CHAT_IDS or "").strip()
    if not raw:
        return set()
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


def is_configured() -> bool:
    return bool((settings.TELEGRAM_BOT_TOKEN or "").strip())


def is_authorized(chat_id: int) -> bool:
    """A chat_id is authorized if the whitelist is empty (dev mode) or contains it."""
    allowed = _allowed_ids()
    if not allowed:
        return True
    return chat_id in allowed


# ============================================================
# LOW-LEVEL API CALLS
# ============================================================
def _post(method: str, payload: dict, timeout: float = 30.0) -> dict:
    url = f"{API_BASE}/bot{_token()}/{method}"
    try:
        r = httpx.post(url, json=payload, timeout=timeout)
    except Exception as exc:
        raise TelegramError(f"HTTP error calling {method}: {exc}") from exc
    if r.status_code >= 400:
        raise TelegramError(
            f"Telegram API error {r.status_code} on {method}: {r.text[:300]}"
        )
    try:
        data = r.json()
    except Exception as exc:
        raise TelegramError(f"Invalid JSON from {method}: {exc}") from exc
    if not data.get("ok"):
        raise TelegramError(
            f"Telegram API returned ok=false on {method}: {data}"
        )
    return data.get("result")


# ============================================================
# OUTBOUND
# ============================================================
def send_message(chat_id: int, text: str) -> dict:
    """Send a text message. Returns the Telegram message object."""
    if not isinstance(chat_id, int):
        raise TelegramError("chat_id must be an integer.")
    if not isinstance(text, str) or not text.strip():
        raise TelegramError("text must be a non-empty string.")
    if len(text) > 4000:
        text = text[:4000] + "..."
    return _post("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    })


def send_voice(chat_id: int, ogg_opus_path: str, caption: Optional[str] = None) -> dict:
    """Send a voice message from a .ogg (Opus) file."""
    if not isinstance(chat_id, int):
        raise TelegramError("chat_id must be an integer.")
    token = _token()
    url = f"{API_BASE}/bot{token}/sendVoice"
    try:
        with open(ogg_opus_path, "rb") as fh:
            files = {"voice": fh}
            data = {"chat_id": str(chat_id)}
            if caption:
                data["caption"] = caption[:1000]
            r = httpx.post(url, data=data, files=files, timeout=60.0)
    except FileNotFoundError as exc:
        raise TelegramError(f"Voice file not found: {ogg_opus_path}") from exc
    except Exception as exc:
        raise TelegramError(f"send_voice HTTP error: {exc}") from exc
    if r.status_code >= 400:
        raise TelegramError(
            f"Telegram API error {r.status_code} on sendVoice: {r.text[:300]}"
        )
    return r.json().get("result", {})


# ============================================================
# INBOUND — long-polling updates
# ============================================================
def get_updates(offset: int = 0, timeout: int = 25) -> list:
    """
    Fetch new updates using long-polling.
    offset: last update_id + 1 (to acknowledge previous).
    Returns a list of parsed messages.
    """
    raw = _post("getUpdates", {
        "offset": offset,
        "timeout": timeout,
        "allowed_updates": ["message"],
    })
    return [_parse_update(u) for u in raw]


def _parse_update(u: dict) -> TelegramMessage:
    msg = u.get("message", {}) or {}
    chat = msg.get("chat", {}) or {}
    sender = msg.get("from", {}) or {}
    voice = msg.get("voice")
    return TelegramMessage(
        update_id=int(u.get("update_id", 0)),
        chat_id=int(chat.get("id", 0)),
        from_id=int(sender.get("id", 0)) or None,
        from_name=(
            (sender.get("first_name") or "") + " " + (sender.get("last_name") or "")
        ).strip() or None,
        text=msg.get("text"),
        voice_file_id=(voice or {}).get("file_id") if voice else None,
        is_voice=bool(voice),
        date=msg.get("date"),
    )


def download_voice(file_id: str, dest_path: str) -> str:
    """Download a voice message (as .oga) to dest_path. Returns the path."""
    token = _token()
    # Get file path
    r = httpx.get(
        f"{API_BASE}/bot{token}/getFile",
        params={"file_id": file_id},
        timeout=30.0,
    )
    if r.status_code >= 400 or not r.json().get("ok"):
        raise TelegramError(f"getFile failed: {r.text[:200]}")
    file_path = r.json()["result"]["file_path"]
    # Download content
    url = f"{API_BASE}/file/bot{token}/{file_path}"
    try:
        with httpx.stream("GET", url, timeout=60.0) as resp:
            if resp.status_code >= 400:
                raise TelegramError(f"Download failed: {resp.status_code}")
            with open(dest_path, "wb") as out:
                for chunk in resp.iter_bytes():
                    out.write(chunk)
    except TelegramError:
        raise
    except Exception as exc:
        raise TelegramError(f"Download error: {exc}") from exc
    return dest_path