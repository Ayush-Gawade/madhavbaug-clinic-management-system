"""Application configuration.

Settings are loaded from environment variables, falling back to ``.env`` files.
The repository root ``.env`` is read after any local ``.env`` so that a single
root file configures every service in the monorepo.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "staging", "production"]

# Insecure development placeholders. A production deployment must override each
# of these; the validator below refuses to boot otherwise (PRD AC-012, Risk 8).
_DEFAULT_SECRET_KEY = "insecure-development-secret-change-me-0000"
_DEFAULT_MEDIA_SIGNING_SECRET = "insecure-media-signing-secret-change-me"
_DEFAULT_BOOTSTRAP_ADMIN_PASSWORD = "change-me-admin-password"
_DEFAULT_WHATSAPP_VERIFY_TOKEN = "verify-token"
_INSECURE_CORS_HOSTS = ("localhost", "127.0.0.1")


class Settings(BaseSettings):
    """Typed, validated application settings."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env", "../../../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Application --------------------------------------------------------
    app_name: str = "Madhavbaug Clinic Management System"
    app_env: AppEnv = "development"
    app_debug: bool = False
    app_timezone: str = "Asia/Kolkata"
    api_v1_prefix: str = "/api/v1"
    public_base_url: str = "http://localhost:8000"
    backend_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # -- Security / auth ----------------------------------------------------
    secret_key: str = Field(default=_DEFAULT_SECRET_KEY, min_length=16)
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 60 * 24 * 14
    jwt_algorithm: str = "HS256"

    # -- Database -----------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "madhavbaug"
    postgres_password: str = "madhavbaug"
    postgres_db: str = "madhavbaug"
    database_url: str | None = None
    test_database_url: str | None = None

    # -- Redis / Celery -----------------------------------------------------
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_task_always_eager: bool = False

    # -- Local dev scheduler ------------------------------------------------
    # When Redis/Celery is unavailable (typical local Windows dev) a light
    # in-process loop can drive the follow-up pipeline. It is ignored in
    # production, where Celery Beat + workers own this work.
    local_scheduler_enabled: bool = False
    local_scheduler_interval_seconds: float = 30.0

    # -- Media --------------------------------------------------------------
    media_root: Path = Path("./data/media")
    media_signing_secret: str = Field(default=_DEFAULT_MEDIA_SIGNING_SECRET, min_length=16)
    media_url_ttl_seconds: int = 300

    # -- OpenAI -------------------------------------------------------------
    openai_api_key: str = ""
    # Point the client at any OpenAI-compatible gateway (e.g. OpenRouter,
    # Together, a local vLLM). Empty uses api.openai.com.
    openai_base_url: str | None = None
    openai_text_model: str = "gpt-4o"
    openai_vision_model: str = "gpt-4o"
    openai_timeout_seconds: float = 45.0
    openai_max_retries: int = 2
    ai_enabled: bool = True
    # "inline" analyses inbound messages inside the webhook request (simple, but
    # a slow provider delays the response); "deferred" enqueues a Celery task.
    # Production requires "deferred" when AI is enabled so webhooks never block.
    ai_processing_mode: Literal["inline", "deferred"] = "inline"

    # -- WhatsApp Cloud API -------------------------------------------------
    whatsapp_enabled: bool = False
    whatsapp_verify_token: str = _DEFAULT_WHATSAPP_VERIFY_TOKEN
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_app_secret: str = ""
    # Outbound Graph API calls use a dedicated timeout so a slow Meta API cannot
    # inherit the (much longer) AI provider timeout.
    whatsapp_timeout_seconds: float = Field(default=30.0, gt=0)
    # Fail-closed webhook verification (PRD AC-007). Signatures are required by
    # default; an unsigned payload is rejected with 403.
    whatsapp_webhook_require_signature: bool = True
    # Explicit, non-production-only opt-out used for local dry-runs and tests.
    # It is ignored in production and unsigned payloads are never persisted
    # unless this is deliberately enabled outside production.
    webhook_allow_unsigned: bool = False
    whatsapp_api_version: str = "v21.0"
    whatsapp_graph_base_url: str = "https://graph.facebook.com"
    # Meta only allows free-form (text) messages within 24 hours of the patient's
    # last inbound message. Business-initiated messages outside that window must
    # use an approved template; when enforcement is on, dispatch refuses to send
    # free-form text that Meta would reject (error 131047).
    whatsapp_session_window_hours: int = 24
    whatsapp_enforce_session_window: bool = False

    # -- Bootstrap admin ----------------------------------------------------
    bootstrap_admin_email: str = "admin@madhavbaug.in"
    bootstrap_admin_password: str = _DEFAULT_BOOTSTRAP_ADMIN_PASSWORD
    bootstrap_admin_name: str = "Clinic Owner"

    # -- Finance ------------------------------------------------------------
    # Clinic-approved profitability boundaries for the cost estimator (P0
    # placeholders until the clinic supplies real values, PRD FR-034/FR-037).
    finance_min_contribution_margin: float = 0.10
    finance_min_profit: float = 0.0
    finance_max_discount_default: float = 0.50

    @field_validator("database_url", "test_database_url", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Settings:
        """Refuse to start in production with unsafe or placeholder settings.

        This is a hard gate for AC-012 ("platform and data safeguards"): real
        patient data and live messaging must never run on development defaults
        or with a debug/observability configuration that leaks internals.
        """
        if self.app_env != "production":
            return self

        problems: list[str] = []
        if self.app_debug:
            problems.append("APP_DEBUG must be false")
        if self.secret_key == _DEFAULT_SECRET_KEY or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be a strong, unique value (>=32 chars)")
        if self.media_signing_secret == _DEFAULT_MEDIA_SIGNING_SECRET:
            problems.append("MEDIA_SIGNING_SECRET must be changed")
        if self.bootstrap_admin_password == _DEFAULT_BOOTSTRAP_ADMIN_PASSWORD:
            problems.append("BOOTSTRAP_ADMIN_PASSWORD must be changed")
        if self.whatsapp_verify_token == _DEFAULT_WHATSAPP_VERIFY_TOKEN:
            problems.append("WHATSAPP_VERIFY_TOKEN must be changed")
        # The webhook route is always mounted, so a production deployment must
        # always be able to verify signatures — even with WhatsApp disabled.
        if not self.whatsapp_app_secret:
            problems.append("WHATSAPP_APP_SECRET is required in production to verify webhooks")
        if not self.whatsapp_webhook_require_signature:
            problems.append("WHATSAPP_WEBHOOK_REQUIRE_SIGNATURE must be true in production")
        if self.webhook_allow_unsigned:
            problems.append("WEBHOOK_ALLOW_UNSIGNED must be false in production")
        if self.whatsapp_enabled and not self.whatsapp_enforce_session_window:
            problems.append(
                "WHATSAPP_ENFORCE_SESSION_WINDOW must be true in production so "
                "business-initiated messages outside the 24h window use a template"
            )
        if self.whatsapp_enabled and not self.whatsapp_access_token.strip():
            problems.append("WHATSAPP_ACCESS_TOKEN is required when WHATSAPP_ENABLED is true")
        if self.whatsapp_enabled and not self.whatsapp_phone_number_id.strip():
            problems.append("WHATSAPP_PHONE_NUMBER_ID is required when WHATSAPP_ENABLED is true")
        if self.ai_enabled and not self.openai_api_key:
            problems.append("OPENAI_API_KEY is required when AI_ENABLED is true")
        if self.ai_enabled and self.ai_processing_mode != "deferred":
            problems.append("AI_PROCESSING_MODE must be deferred in production")
        if not self.public_base_url.startswith("https://"):
            problems.append("PUBLIC_BASE_URL must use https in production")
        if any(host in self.public_base_url for host in _INSECURE_CORS_HOSTS):
            problems.append("PUBLIC_BASE_URL must not point to localhost in production")
        if any(host in self.backend_cors_origins for host in _INSECURE_CORS_HOSTS):
            problems.append("BACKEND_CORS_ORIGINS must not include localhost addresses")

        if problems:
            raise ValueError("unsafe production configuration: " + "; ".join(problems))
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def sqlalchemy_database_uri(self) -> str:
        """Async SQLAlchemy URI used by the application runtime."""
        if self.database_url:
            return self.database_url
        password = quote_plus(self.postgres_password)
        user = quote_plus(self.postgres_user)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()


settings = get_settings()
