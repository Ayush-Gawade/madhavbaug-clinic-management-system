"""Inbound media storage and signed, expiring URLs (PRD 11.4).

WhatsApp media ids are short-lived, so inbound bytes are downloaded and stored
under ``media_root`` when a message arrives. Staff open media through a
short-lived HMAC-signed URL, so files are never publicly enumerable and a leaked
link expires on its own.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.models.messaging import WhatsAppMessage
from app.services import whatsapp as whatsapp_client

logger = get_logger(__name__)

# A provider mime type maps to a file extension so the served response carries a
# useful type without guessing. Anything unknown is stored as raw bytes.
_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/amr": ".amr",
    "audio/aac": ".aac",
    "video/mp4": ".mp4",
    "video/3gpp": ".3gp",
}

_EXTENSION_TO_MIME = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".pdf": "application/pdf",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".amr": "audio/amr",
    ".aac": "audio/aac",
    ".mp4": "video/mp4",
    ".3gp": "video/3gpp",
    ".bin": "application/octet-stream",
}


def _extension(mime_type: str | None) -> str:
    if not mime_type:
        return ".bin"
    return _EXTENSIONS.get(mime_type.split(";")[0].strip().lower(), ".bin")


def stored_media_path(message_id: uuid.UUID, mime_type: str | None) -> Path:
    """Deterministic on-disk path for a stored message's media."""
    return settings.media_root / "inbound" / f"{message_id}{_extension(mime_type)}"


def content_type_for(mime_type: str | None) -> str:
    """The response content type to use for stored media."""
    if not mime_type:
        return "application/octet-stream"
    normalized = mime_type.split(";")[0].strip().lower()
    if normalized in _EXTENSIONS or normalized in {"application/octet-stream"}:
        return normalized
    return _EXTENSION_TO_MIME.get(_extension(normalized), "application/octet-stream")


async def store_inbound_media(message: WhatsAppMessage) -> bool:
    """Download and persist an inbound message's media; best-effort and idempotent.

    Returns whether the bytes are now on disk. Dry-run mode and download failures
    return ``False`` without raising so a webhook is never failed by media issues.
    """
    if not message.media_reference or not message.media_mime_type:
        return False
    path = stored_media_path(message.id, message.media_mime_type)
    if path.is_file():
        return True
    try:
        data, _ = await whatsapp_client.download_media(message.media_reference)
    except whatsapp_client.WhatsAppError as exc:
        logger.warning("media_download_failed", message_id=str(message.id), error=str(exc))
        return False
    if not data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    logger.info("media_stored", message_id=str(message.id), bytes=len(data))
    return True


def _signature(message_id: uuid.UUID, expires: int) -> str:
    payload = f"{message_id}.{expires}".encode()
    digest = hmac.new(settings.media_signing_secret.encode(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def sign_media_token(message_id: uuid.UUID, *, ttl_seconds: int | None = None) -> str:
    """Build an ``<expiry>.<signature>`` token that authorizes one media fetch."""
    ttl = ttl_seconds if ttl_seconds is not None else settings.media_url_ttl_seconds
    expires = int(datetime.now(UTC).timestamp()) + ttl
    return f"{expires}.{_signature(message_id, expires)}"


def verify_media_token(message_id: uuid.UUID, token: str) -> bool:
    """Whether a token is authentic, for this message and unexpired."""
    try:
        expires_str, signature = token.split(".", 1)
        expires = int(expires_str)
    except (AttributeError, ValueError):
        return False
    if not hmac.compare_digest(_signature(message_id, expires), signature):
        return False
    return datetime.now(UTC).timestamp() <= expires


def media_url(message_id: uuid.UUID) -> str:
    """A same-origin, signed URL the web client can render directly."""
    prefix = settings.api_v1_prefix.rstrip("/")
    return f"{prefix}/media/{message_id}?token={sign_media_token(message_id)}"
