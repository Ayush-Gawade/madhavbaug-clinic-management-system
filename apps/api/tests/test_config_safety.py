"""Production safety gate tests (PRD AC-012, Risk 8).

These are pure unit tests: ``model_validate`` validates only the supplied data
and never reads the repository ``.env`` or process environment.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_HARDENED = {
    "app_env": "production",
    "app_debug": False,
    "secret_key": "s" * 48,
    "media_signing_secret": "m" * 48,
    "bootstrap_admin_password": "bootstrap-password-123",
    "whatsapp_verify_token": "webhook-token-123",
    "whatsapp_app_secret": "app-secret-123",
    "whatsapp_webhook_require_signature": True,
    "webhook_allow_unsigned": False,
    "whatsapp_enforce_session_window": True,
    "backend_cors_origins": "https://clinic.example.com",
    "ai_enabled": False,
    "whatsapp_enabled": False,
}


def _prod(**overrides: object) -> Settings:
    data = {**_HARDENED, **overrides}
    return Settings.model_validate(data)


def test_hardened_production_config_is_accepted() -> None:
    settings = _prod()
    assert settings.app_env == "production"
    assert settings.is_production is True


def test_development_allows_placeholders() -> None:
    settings = Settings.model_validate({"app_env": "development"})
    assert settings.app_env == "development"
    assert settings.is_production is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"app_debug": True},
        {"secret_key": "insecure-development-secret-change-me-0000"},
        {"secret_key": "too-short"},
        {"media_signing_secret": "insecure-media-signing-secret-change-me"},
        {"bootstrap_admin_password": "change-me-admin-password"},
        {"whatsapp_verify_token": "verify-token"},
        {"whatsapp_app_secret": ""},
        {"whatsapp_app_secret": "", "whatsapp_enabled": False},
        {"whatsapp_webhook_require_signature": False},
        {"webhook_allow_unsigned": True},
        {"backend_cors_origins": "https://clinic.example.com,http://localhost:5173"},
        {"whatsapp_enabled": True, "whatsapp_app_secret": ""},
        {"whatsapp_enabled": True, "whatsapp_enforce_session_window": False},
        {"ai_enabled": True, "openai_api_key": ""},
        {"ai_enabled": True, "openai_api_key": "sk-test", "ai_processing_mode": "inline"},
    ],
)
def test_unsafe_production_config_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _prod(**overrides)


def test_production_whatsapp_requires_app_secret() -> None:
    settings = _prod(whatsapp_enabled=True, whatsapp_app_secret="app-secret-123")
    assert settings.whatsapp_enabled is True


def test_production_live_whatsapp_requires_session_window_enforcement() -> None:
    with pytest.raises(ValidationError):
        _prod(whatsapp_enabled=True, whatsapp_enforce_session_window=False)
    settings = _prod(whatsapp_enabled=True, whatsapp_enforce_session_window=True)
    assert settings.whatsapp_enforce_session_window is True


def test_production_requires_app_secret_even_when_disabled() -> None:
    with pytest.raises(ValidationError):
        _prod(whatsapp_enabled=False, whatsapp_app_secret="")


def test_production_ai_requires_api_key() -> None:
    settings = _prod(ai_enabled=True, openai_api_key="sk-test", ai_processing_mode="deferred")
    assert settings.ai_enabled is True
    assert settings.ai_processing_mode == "deferred"
