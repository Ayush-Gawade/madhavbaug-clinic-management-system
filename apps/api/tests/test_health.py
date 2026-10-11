"""Liveness endpoint tests (no database required)."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def test_liveness() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert "X-Request-ID" in response.headers


class _HealthyRedis:
    async def ping(self) -> bool:
        return True


class _DownRedis:
    async def ping(self) -> bool:
        raise ConnectionError("redis down")


class _BrokenSession:
    async def execute(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("database down")


async def test_readiness_is_ok_when_dependencies_healthy(client, monkeypatch) -> None:
    from app.api.v1.endpoints import health as health_module

    monkeypatch.setattr(health_module, "get_redis", lambda: _HealthyRedis())
    response = await client.get("/health/ready")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["components"] == {"database": "ok", "redis": "ok"}


async def test_readiness_is_503_when_redis_down(client, monkeypatch) -> None:
    from app.api.v1.endpoints import health as health_module

    monkeypatch.setattr(health_module, "get_redis", lambda: _DownRedis())
    response = await client.get("/health/ready")
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"]["database"] == "ok"
    assert body["components"]["redis"].startswith("error")


async def test_readiness_is_503_when_database_down(monkeypatch) -> None:
    from app.api.v1.endpoints import health as health_module
    from app.db.session import get_db

    monkeypatch.setattr(health_module, "get_redis", lambda: _HealthyRedis())

    app = create_app()

    async def override_get_db():
        yield _BrokenSession()

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        response = await http_client.get("/health/ready")
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"]["database"].startswith("error")
