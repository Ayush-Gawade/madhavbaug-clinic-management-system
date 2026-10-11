"""Defensive HTTP response header tests (no database required)."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def _get(path: str):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path)


async def test_security_headers_are_present() -> None:
    response = await _get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Permissions-Policy" in response.headers


async def test_hsts_is_not_sent_outside_production() -> None:
    response = await _get("/health")
    assert "Strict-Transport-Security" not in response.headers
