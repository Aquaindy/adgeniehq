import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError


def test_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "AdVanta AI"
    assert body["health"].endswith("/health")


def test_health_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "AdVanta AI"
    assert body["version"] == "0.0.1"


class _FakeRedis:
    def __init__(self, *, fail: bool):
        self._fail = fail

    def ping(self):
        if self._fail:
            raise RedisError("redis down")
        return True

    def close(self):
        pass


def test_ready_ok_when_deps_up(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.api.v1.health as health_mod

    monkeypatch.setattr(health_mod.Redis, "from_url", lambda *a, **k: _FakeRedis(fail=False))
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"postgres": "ok", "redis": "ok"}


def test_ready_returns_503_when_redis_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.api.v1.health as health_mod

    monkeypatch.setattr(health_mod.Redis, "from_url", lambda *a, **k: _FakeRedis(fail=True))
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["postgres"] == "ok"
    assert body["checks"]["redis"].startswith("error")
