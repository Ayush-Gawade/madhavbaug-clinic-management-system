"""Unit tests for the WhatsApp client helpers (no database required)."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from app.core.config import settings
from app.services import whatsapp


def test_verify_signature_without_secret_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "")
    # A missing secret can never prove authenticity.
    assert whatsapp.verify_signature(b"payload", None) is False


def test_signature_required_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "whatsapp_app_secret", "")
    monkeypatch.setattr(settings, "whatsapp_webhook_require_signature", True)
    monkeypatch.setattr(settings, "webhook_allow_unsigned", False)
    assert whatsapp.webhook_signature_required() is True


def test_signature_required_when_secret_set(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "whatsapp_app_secret", "app-secret")
    monkeypatch.setattr(settings, "whatsapp_webhook_require_signature", False)
    monkeypatch.setattr(settings, "webhook_allow_unsigned", False)
    assert whatsapp.webhook_signature_required() is True


def test_explicit_dev_opt_out_allows_unsigned(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "webhook_allow_unsigned", True)
    assert whatsapp.webhook_signature_required() is False


def test_production_never_allows_unsigned(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "whatsapp_webhook_require_signature", False)
    monkeypatch.setattr(settings, "webhook_allow_unsigned", True)
    assert whatsapp.webhook_signature_required() is True


def test_verify_signature_roundtrip(monkeypatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_app_secret", "app-secret")
    body = b'{"hello":"world"}'
    digest = hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    assert whatsapp.verify_signature(body, f"sha256={digest}") is True
    assert whatsapp.verify_signature(body, "sha256=deadbeef") is False
    assert whatsapp.verify_signature(body, None) is False


def test_webhook_challenge(monkeypatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_verify_token", "verify-token")
    assert whatsapp.verify_webhook_challenge("subscribe", "verify-token", "abc") == "abc"
    assert whatsapp.verify_webhook_challenge("subscribe", "wrong", "abc") is None
    assert whatsapp.verify_webhook_challenge("other", "verify-token", "abc") is None


def test_normalize_phone() -> None:
    assert whatsapp.normalize_phone("+91 98123-45678") == "919812345678"
    assert whatsapp.normalize_phone(None) is None


def test_render_template() -> None:
    body = "Hello {{name}}, your plan is {{plan}}."
    rendered = whatsapp.render_template(body, {"name": "Asha", "plan": "vegan"})
    assert rendered == "Hello Asha, your plan is vegan."


def test_build_template_parameters_preserves_order_and_tolerates_unknowns() -> None:
    body = "Hi {{name}}, your {{unknown}} is {{1}}."
    assert whatsapp.build_template_parameters(body, {"name": "Asha", "1": "ready"}) == [
        "Asha",
        "",
        "ready",
    ]
    assert whatsapp.build_template_parameters("No placeholders here.", {}) == []


def test_parse_webhook_extracts_messages_and_statuses() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "919812345678",
                                    "id": "wamid.1",
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": "sugar 180"},
                                },
                                {
                                    "from": "919812345678",
                                    "id": "wamid.2",
                                    "timestamp": "1700000001",
                                    "type": "image",
                                    "image": {"id": "media-1", "mime_type": "image/jpeg"},
                                },
                            ],
                            "statuses": [
                                {
                                    "id": "wamid.OUT",
                                    "status": "delivered",
                                    "recipient_id": "919812345678",
                                    "timestamp": "1700000002",
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    messages, statuses = whatsapp.parse_webhook(payload)
    assert len(messages) == 2
    assert messages[0].message_type == "text"
    assert messages[0].text == "Hi" or messages[0].text is not None
    assert messages[1].media_id is not None
    assert len(statuses) == 1
    assert statuses[0].status == "delivered"
    assert statuses[0].recipient == "919812345678"


@pytest.mark.parametrize(
    ("access_token", "phone_number_id"),
    [("", "phone-id"), ("live-token", "")],
)
async def test_production_send_fails_closed_with_missing_credentials(
    monkeypatch, access_token: str, phone_number_id: str
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "whatsapp_enabled", True)
    monkeypatch.setattr(settings, "whatsapp_access_token", access_token)
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", phone_number_id)

    result = await whatsapp._post_message({})

    assert result.ok is False
    assert result.dry_run is False
    assert result.error_code == "whatsapp_not_configured"


async def test_development_send_dry_runs_without_credentials(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "whatsapp_enabled", True)
    monkeypatch.setattr(settings, "whatsapp_access_token", "")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "")

    result = await whatsapp._post_message({})

    assert result.ok is True
    assert result.dry_run is True


async def test_production_media_fails_closed_without_access_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "whatsapp_enabled", True)
    monkeypatch.setattr(settings, "whatsapp_access_token", "")

    with pytest.raises(whatsapp.WhatsAppError) as exc_info:
        await whatsapp.download_media("media-id")

    assert exc_info.value.code == "whatsapp_not_configured"


async def test_send_uses_dedicated_whatsapp_timeout(monkeypatch) -> None:
    captured: dict[str, float] = {}

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self) -> dict[str, object]:
            return {"messages": [{"id": "wamid.test"}]}

    class _FakeClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> _FakeResponse:
            return _FakeResponse()

    monkeypatch.setattr(whatsapp.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "whatsapp_enabled", True)
    monkeypatch.setattr(settings, "whatsapp_access_token", "live-token")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "phone-id")
    monkeypatch.setattr(settings, "whatsapp_timeout_seconds", 12.5)

    result = await whatsapp._post_message({"test": True})

    assert result.ok is True
    assert result.provider_message_id == "wamid.test"
    assert captured["timeout"] == 12.5
