"""Signed serving of stored inbound WhatsApp media.

Access is granted by a short-lived HMAC token rather than a bearer header, because
an ``<img>``/``<audio>`` element cannot send an Authorization header. A missing,
forged or expired token is refused before any filesystem access.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import DbSession
from app.core.errors import NotFoundError, PermissionDeniedError
from app.models.messaging import WhatsAppMessage
from app.services import media as media_service

router = APIRouter(tags=["media"])


@router.get("/media/{message_id}", summary="Fetch inbound media by signed URL")
async def get_message_media(
    message_id: uuid.UUID,
    db: DbSession,
    token: str = Query(..., description="Signed, expiring media token."),
) -> FileResponse:
    if not media_service.verify_media_token(message_id, token):
        raise PermissionDeniedError("This media link is invalid or has expired.")
    message = await db.get(WhatsAppMessage, message_id)
    if message is None or not message.media_mime_type:
        raise NotFoundError("Media not found.")
    path = media_service.stored_media_path(message.id, message.media_mime_type)
    if not path.is_file():
        raise NotFoundError("Media not found.")
    return FileResponse(path, media_type=media_service.content_type_for(message.media_mime_type))
