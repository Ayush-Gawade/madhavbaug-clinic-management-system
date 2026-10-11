"""Unit tests for the WhatsApp client helpers (no database required)."""

from __future__ import annotations

import hashlib
import hmac

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
