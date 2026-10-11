"""Unit tests for password hashing and JWT issuance/validation."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_verify_password_handles_invalid_hash() -> None:
    assert verify_password("anything", "not-a-valid-hash") is False


def test_create_and_decode_access_token() -> None:
    token = create_token("user-123", token_type="access", extra_claims={"role": "owner"})
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"
    assert payload["role"] == "owner"
    assert "jti" in payload


def test_decode_rejects_wrong_token_type() -> None:
    token = create_token("user-123", token_type="refresh")
    with pytest.raises(TokenError):
        decode_token(token, expected_type="access")


def test_decode_rejects_expired_token() -> None:
    token = create_token("user-123", token_type="access", expires_delta=timedelta(seconds=-1))
    with pytest.raises(TokenError):
        decode_token(token, expected_type="access")


def test_decode_rejects_tampered_token() -> None:
    token = create_token("user-123", token_type="access")
    with pytest.raises(TokenError):
        decode_token(token + "tampered", expected_type="access")
