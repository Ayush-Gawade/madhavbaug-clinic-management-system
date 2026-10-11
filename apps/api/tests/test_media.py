"""Inbound media storage and signed-serving tests (require PostgreSQL)."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.messaging import WhatsAppMessage
from app.models.user import StaffRole
from app.services import media as media_service
from app.services import whatsapp as whatsapp_client

API = "/api/v1"
PASSWORD = "strong-password-123"


def _phone() -> str:
    suffix = uuid.uuid4().int % 10**8
    return f"9198{suffix:08d}"


async def _login(client, email: str) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def _headers(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _register(client, headers: dict[str, str], phone: str) -> dict:
    response = await client.post(
        f"{API}/patients",
        headers=headers,
        json={"full_name": "Media Test Patient", "phone_number": phone},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _media_webhook(*, from_phone: str, message_id: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1234567890",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": from_phone,
                                    "id": message_id,
                                    "timestamp": "1700000000",
                                    "type": "image",
                                    "image": {
                                        "id": "media-provider-1",
                                        "mime_type": "image/png",
                                        "caption": "BP report",
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


async def _post_webhook(client, payload: dict):
    return await client.post(
        f"{API}/whatsapp/webhook",
        content=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )


def test_media_token_round_trip() -> None:
    message_id = uuid.uuid4()
    token = media_service.sign_media_token(message_id)
    assert media_service.verify_media_token(message_id, token) is True
    # A token is bound to one message and cannot be replayed elsewhere.
    assert media_service.verify_media_token(uuid.uuid4(), token) is False
    assert media_service.verify_media_token(message_id, "garbage") is False
    assert media_service.verify_media_token(message_id, token + "tampered") is False


def test_media_token_expires() -> None:
    message_id = uuid.uuid4()
    expired = media_service.sign_media_token(message_id, ttl_seconds=-10)
    assert media_service.verify_media_token(message_id, expired) is False


def test_content_type_falls_back_for_unknown_types() -> None:
    assert media_service.content_type_for("image/png") == "image/png"
    assert media_service.content_type_for("application/pdf") == "application/pdf"
    assert media_service.content_type_for("application/x-weird") == "application/octet-stream"
    assert media_service.content_type_for(None) == "application/octet-stream"


@pytest.mark.integration
async def test_inbound_media_is_stored_and_served(
    client,
    staff_factory,
    unique_email,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "media_root", tmp_path)

    async def _download(_media_id: str):
        return b"\x89PNG\r\n\x1a\nfakepng", "image/png"

    monkeypatch.setattr(whatsapp_client, "download_media", _download)

    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    phone = _phone()
    patient = await _register(client, headers, phone)

    posted = await _post_webhook(
        client, _media_webhook(from_phone=phone, message_id="wamid.MEDIA1")
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["messages"] == 1

    convo = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    inbound = next(m for m in convo.json()["items"] if m["direction"] == "inbound")
    assert inbound["message_type"] == "image"
    assert inbound["media_mime_type"] == "image/png"
    assert inbound["media_url"] is not None

    # Bytes are fetched and persisted by the worker-side helper.
    async with session_factory() as session:
        message = await session.get(WhatsAppMessage, uuid.UUID(inbound["id"]))
        assert message is not None
        assert await media_service.store_inbound_media(message) is True
        # Idempotent: a second call does not re-download.
        assert await media_service.store_inbound_media(message) is True
    stored = media_service.stored_media_path(uuid.UUID(inbound["id"]), "image/png")
    assert stored.is_file()

    # The signed URL returned by the API serves the bytes without a bearer token.
    served = await client.get(inbound["media_url"])
    assert served.status_code == 200, served.text
    assert served.content == b"\x89PNG\r\n\x1a\nfakepng"
    assert served.headers["content-type"] == "image/png"

    # A forged token and a valid token for another message are both refused.
    assert (await client.get(f"{API}/media/{inbound['id']}?token=forged")).status_code == 403
    other = uuid.uuid4()
    other_token = media_service.sign_media_token(other)
    assert (await client.get(f"{API}/media/{other}?token={other_token}")).status_code == 404
    expired = media_service.sign_media_token(uuid.UUID(inbound["id"]), ttl_seconds=-10)
    assert (await client.get(f"{API}/media/{inbound['id']}?token={expired}")).status_code == 403


@pytest.mark.integration
async def test_media_endpoint_404_when_file_absent(
    client, staff_factory, unique_email, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "media_root", tmp_path)

    owner = unique_email
    await staff_factory(email=owner, role=StaffRole.OWNER)
    headers = _headers(await _login(client, owner))
    phone = _phone()
    patient = await _register(client, headers, phone)
    await _post_webhook(client, _media_webhook(from_phone=phone, message_id="wamid.MEDIA2"))

    convo = await client.get(f"{API}/patients/{patient['id']}/messages", headers=headers)
    inbound = next(m for m in convo.json()["items"] if m["direction"] == "inbound")

    # No bytes were stored, so a valid link still resolves to 404, not a leak.
    served = await client.get(inbound["media_url"])
    assert served.status_code == 404
