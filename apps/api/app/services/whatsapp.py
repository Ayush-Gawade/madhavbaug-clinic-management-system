"""WhatsApp Cloud API wrapper: webhook verification, parsing, send and media.

When ``whatsapp_enabled`` is false or no access token is configured the send
paths operate in a deterministic dry-run mode (synthetic ids, no network) so
local development and tests do not require Meta credentials.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import settings

_MAX_TEXT_LENGTH = 4096


class WhatsAppError(Exception):
    """Transport or provider failure while talking to the WhatsApp API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SendResult:
    """Outcome of an outbound send attempt."""

    __slots__ = ("dry_run", "error_code", "error_message", "ok", "provider_message_id")

    def __init__(
        self,
        *,
        ok: bool,
        provider_message_id: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        dry_run: bool = False,
    ) -> None:
        self.ok = ok
        self.provider_message_id = provider_message_id
        self.error_code = error_code
        self.error_message = error_message
        self.dry_run = dry_run


class MessageEvent:
    """A parsed inbound message from a webhook payload."""

    def __init__(
        self,
        *,
        provider_message_id: str,
        from_phone: str,
        message_type: str,
        text: str | None = None,
        media_id: str | None = None,
        media_mime_type: str | None = None,
        media_caption: str | None = None,
        timestamp: datetime | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.provider_message_id = provider_message_id
        self.from_phone = from_phone
        self.message_type = message_type
        self.text = text
        self.media_id = media_id
        self.media_mime_type = media_mime_type
        self.media_caption = media_caption
        self.timestamp = timestamp
        self.raw = raw or {}


class StatusEvent:
    """A parsed delivery-status update from a webhook payload."""

    def __init__(
        self,
        *,
        provider_message_id: str,
        status: str,
        recipient: str | None,
        timestamp: datetime | None,
        error_code: str | None = None,
        error_message: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.provider_message_id = provider_message_id
        self.status = status
        self.recipient = recipient
        self.timestamp = timestamp
        self.error_code = error_code
        self.error_message = error_message
        self.raw = raw or {}


def normalize_phone(value: str | None) -> str | None:
    """Keep digits only; used for tolerant patient matching."""
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits or None


def verify_webhook_challenge(
    mode: str | None, token: str | None, challenge: str | None
) -> str | None:
    """Return the challenge string when the GET verification matches."""
    if mode == "subscribe" and token == settings.whatsapp_verify_token and challenge:
        return challenge
    return None


def webhook_signature_required() -> bool:
    """Whether an inbound webhook must carry a valid signature to be processed.

    Signatures are enforced by default. The only way to accept an unsigned
    payload is the explicit, non-production ``WEBHOOK_ALLOW_UNSIGNED`` opt-out,
    which the production validator refuses. Production therefore always
    requires a verifiable signature (fail closed).
    """
    if settings.app_env == "production":
        return True
    if settings.webhook_allow_unsigned:
        return False
    return settings.whatsapp_webhook_require_signature or bool(settings.whatsapp_app_secret)


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Validate the ``X-Hub-Signature-256`` HMAC header against the app secret.

    Returns ``True`` only when authenticity is actually proven. A missing app
    secret can never verify a payload (fail closed).
    """
    secret = settings.whatsapp_app_secret
    if not secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (ValueError, OSError, OverflowError):
        return None


_WA_TYPE_MAP = {
    "text": "text",
    "image": "image",
    "document": "document",
    "audio": "audio",
    "video": "video",
    "interactive": "interactive",
    "button": "interactive",
    "template": "template",
}


def parse_webhook(payload: dict[str, Any]) -> tuple[list[MessageEvent], list[StatusEvent]]:
    """Normalize a raw webhook envelope into message and status events."""
    messages: list[MessageEvent] = []
    statuses: list[StatusEvent] = []

    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}

            for item in value.get("messages", []) or []:
                wa_type = item.get("type", "unsupported")
                text = media_id = media_mime = media_caption = None
                if wa_type == "text":
                    text = (item.get("text") or {}).get("body")
                elif wa_type in {"image", "document", "audio", "video"}:
                    media = item.get(wa_type) or {}
                    media_id = media.get("id")
                    media_mime = media.get("mime_type")
                    media_caption = media.get("caption")
                elif wa_type == "interactive":
                    interactive = item.get("interactive") or {}
                    button = interactive.get("button_reply") or {}
                    listing = interactive.get("list_reply") or {}
                    text = button.get("title") or listing.get("title")

                messages.append(
                    MessageEvent(
                        provider_message_id=item.get("id", ""),
                        from_phone=normalize_phone(item.get("from")) or "",
                        message_type=_WA_TYPE_MAP.get(wa_type, "unsupported"),
                        text=text,
                        media_id=media_id,
                        media_mime_type=media_mime,
                        media_caption=media_caption,
                        timestamp=_parse_timestamp(item.get("timestamp")),
                        raw=item,
                    )
                )

            for item in value.get("statuses", []) or []:
                errors = item.get("errors") or []
                first = errors[0] if errors else {}
                statuses.append(
                    StatusEvent(
                        provider_message_id=item.get("id", ""),
                        status=item.get("status", ""),
                        recipient=normalize_phone(item.get("recipient_id")),
                        timestamp=_parse_timestamp(item.get("timestamp")),
                        error_code=str(first["code"]) if first.get("code") else None,
                        error_message=first.get("title"),
                        raw=item,
                    )
                )

    return messages, statuses


def _graph_url(path: str) -> str:
    base = settings.whatsapp_graph_base_url.rstrip("/")
    return f"{base}/{settings.whatsapp_api_version}/{path.lstrip('/')}"


async def _post_message(payload: dict[str, Any]) -> SendResult:
    if not settings.whatsapp_enabled or not settings.whatsapp_access_token:
        return SendResult(ok=True, provider_message_id=f"local-{uuid.uuid4().hex}", dry_run=True)

    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.openai_timeout_seconds) as client:
            response = await client.post(
                _graph_url(f"{settings.whatsapp_phone_number_id}/messages"),
                json=payload,
                headers=headers,
            )
    except httpx.HTTPError as exc:  # pragma: no cover - network dependent
        return SendResult(ok=False, error_code="transport_error", error_message=str(exc))

    if response.status_code >= 400:
        return SendResult(
            ok=False, error_code=str(response.status_code), error_message=response.text[:500]
        )
    data = response.json()
    provider_id = (data.get("messages") or [{}])[0].get("id")
    return SendResult(ok=True, provider_message_id=provider_id)


async def send_text_message(to_phone: str, body: str) -> SendResult:
    """Send a plain text message (allowed inside the session window only)."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalize_phone(to_phone) or to_phone,
        "type": "text",
        "text": {"preview_url": False, "body": body[:_MAX_TEXT_LENGTH]},
    }
    return await _post_message(payload)


async def send_template_message(
    to_phone: str,
    template_name: str,
    language: str = "en",
    body_parameters: list[str] | None = None,
) -> SendResult:
    """Send an approved WhatsApp template message."""
    components = []
    if body_parameters:
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": value} for value in body_parameters],
            }
        )
    payload = {
        "messaging_product": "whatsapp",
        "to": normalize_phone(to_phone) or to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": components,
        },
    }
    return await _post_message(payload)


async def download_media(media_id: str) -> tuple[bytes, str | None]:
    """Fetch media bytes for an inbound media id (two-step Graph call)."""
    if not settings.whatsapp_enabled or not settings.whatsapp_access_token:
        return b"", None
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    try:
        async with httpx.AsyncClient(timeout=settings.openai_timeout_seconds) as client:
            meta = await client.get(_graph_url(media_id), headers=headers)
            meta.raise_for_status()
            info = meta.json()
            media = await client.get(info["url"], headers=headers)
            media.raise_for_status()
            return media.content, info.get("mime_type")
    except httpx.HTTPError as exc:  # pragma: no cover - network dependent
        raise WhatsAppError("media_error", str(exc)) from exc


def render_template(body: str, context: dict[str, str]) -> str:
    """Fill ``{{placeholder}}`` tokens in an approved template body."""

    def _replace(match: re.Match[str]) -> str:
        return context.get(match.group(1).strip(), "")

    return re.sub(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", _replace, body)
