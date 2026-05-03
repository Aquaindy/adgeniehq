"""M12 production-hardening tests: request-id middleware, rate limiter,
admin endpoints with superuser gate."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.security.rate_limit import RateLimitMiddleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_user(
    db: Session,
    *,
    email: str = "alice@example.com",
    is_superuser: bool = False,
) -> User:
    user = User(
        email=email,
        hashed_password=hash_password("correct-horse-9"),
        is_active=True,
        is_superuser=is_superuser,
    )
    db.add(user)
    db.commit()
    return user


def _seed_workspace_for(db: Session, user: User, *, name: str = "Acme") -> Workspace:
    workspace = Workspace(name=name, slug=f"acme-{user.email.split('@')[0]}")
    db.add(workspace)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role=Role.OWNER,
            status=MemberStatus.ACTIVE,
        )
    )
    db.commit()
    return workspace


def _login(client: TestClient, email: str) -> None:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-9"},
    ).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------------------
# Request-ID middleware
# ---------------------------------------------------------------------------


def test_request_id_minted_when_missing(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    rid = response.headers["X-Request-ID"]
    # UUIDv4 has 36 chars (with hyphens)
    assert len(rid) == 36 and rid.count("-") == 4


def test_request_id_echoed_when_provided(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health", headers={"X-Request-ID": "trace-abc-123"}
    )
    assert response.headers["X-Request-ID"] == "trace-abc-123"


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


def test_rate_limiter_disabled_in_tests(client: TestClient) -> None:
    """conftest.py sets RATE_LIMIT_DISABLED=1 so the suite can run hot."""
    assert settings.rate_limit_disabled is True


def test_rate_limit_rule_lookup() -> None:
    """The rule table picks the right bucket for path patterns."""
    from app.security.rate_limit import _match_rule

    assert _match_rule("/api/v1/auth/login").label == "auth"
    assert _match_rule("/api/v1/auth/register").label == "auth"
    assert _match_rule(
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000000/agents/run"
    ).label == "agents.run"
    assert _match_rule(
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000000/landing-pages/00000000-0000-0000-0000-000000000000/audit"
    ).label == "landing.audit"
    assert _match_rule(
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000000/billing/checkout-session"
    ).label == "billing.checkout"
    assert _match_rule(
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000000/campaigns/sync"
    ).label == "campaigns.sync"
    # Unmatched paths fall through to the default bucket
    assert _match_rule("/api/v1/workspaces").label == "default"


def test_rate_limit_middleware_returns_429_when_redis_says_exceeded(monkeypatch) -> None:
    """Directly exercise the middleware's exceeded path with a fake Redis."""

    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.routing import Route
    from starlette.responses import PlainTextResponse

    monkeypatch.setattr(settings, "rate_limit_disabled", False)

    class _FakePipe:
        def __init__(self):
            self.calls: list[tuple] = []

        def incr(self, key):
            self.calls.append(("incr", key))

        def expire(self, key, ttl):
            self.calls.append(("expire", key, ttl))

        def execute(self):
            return [9999, True]  # always over the limit

    class _FakeRedis:
        def pipeline(self):
            return _FakePipe()

    monkeypatch.setattr(
        "app.security.rate_limit._redis_client", lambda: _FakeRedis()
    )

    async def _ok(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    inner_app = Starlette(routes=[Route("/api/v1/auth/login", _ok, methods=["POST"])])
    inner_app.add_middleware(RateLimitMiddleware)

    test_client = TestClient(inner_app)
    response = test_client.post("/api/v1/auth/login")
    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "rate_limited"
    assert response.headers["Retry-After"] == "60"


def test_rate_limit_middleware_failopen_when_redis_unreachable(monkeypatch) -> None:
    """If Redis is down, requests pass through (logged) — never 5xx."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.routing import Route
    from starlette.responses import PlainTextResponse

    monkeypatch.setattr(settings, "rate_limit_disabled", False)
    monkeypatch.setattr("app.security.rate_limit._redis_client", lambda: None)

    async def _ok(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    inner_app = Starlette(routes=[Route("/api/v1/auth/login", _ok, methods=["POST"])])
    inner_app.add_middleware(RateLimitMiddleware)
    test_client = TestClient(inner_app)
    response = test_client.post("/api/v1/auth/login")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# is_superuser flag + admin endpoints
# ---------------------------------------------------------------------------


def test_me_returns_is_superuser_flag(client: TestClient, db_session: Session) -> None:
    user = _seed_user(db_session, email="alice@example.com", is_superuser=True)
    _login(client, "alice@example.com")
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["is_superuser"] is True
    assert body["id"] == str(user.id)


def test_admin_overview_requires_superuser(
    client: TestClient, db_session: Session
) -> None:
    _seed_user(db_session, email="regular@example.com", is_superuser=False)
    _login(client, "regular@example.com")
    response = client.get("/api/v1/admin/overview")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_admin_overview_returns_real_counts(
    client: TestClient, db_session: Session
) -> None:
    superuser = _seed_user(db_session, email="root@example.com", is_superuser=True)
    _seed_workspace_for(db_session, superuser, name="HQ")

    other = _seed_user(db_session, email="other@example.com", is_superuser=False)
    _seed_workspace_for(db_session, other, name="Other")

    _login(client, "root@example.com")
    response = client.get("/api/v1/admin/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["users_total"] == 2
    assert body["superusers_total"] == 1
    assert body["workspaces_total"] == 2
    assert body["paid_workspaces_total"] == 0


def test_admin_workspaces_list(client: TestClient, db_session: Session) -> None:
    superuser = _seed_user(db_session, email="root@example.com", is_superuser=True)
    _seed_workspace_for(db_session, superuser, name="HQ")
    _login(client, "root@example.com")
    response = client.get("/api/v1/admin/workspaces")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["name"] == "HQ"
    assert rows[0]["member_count"] == 1
    assert rows[0]["plan_code"] == "free"


def test_admin_users_list(client: TestClient, db_session: Session) -> None:
    superuser = _seed_user(db_session, email="root@example.com", is_superuser=True)
    _seed_user(db_session, email="user2@example.com")
    _seed_workspace_for(db_session, superuser, name="HQ")
    _login(client, "root@example.com")
    response = client.get("/api/v1/admin/users")
    assert response.status_code == 200
    rows = response.json()
    by_email = {r["email"]: r for r in rows}
    assert by_email["root@example.com"]["is_superuser"] is True
    assert by_email["root@example.com"]["workspace_count"] == 1
    assert by_email["user2@example.com"]["is_superuser"] is False
    assert by_email["user2@example.com"]["workspace_count"] == 0


def test_admin_endpoints_require_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/admin/overview")
    assert response.status_code == 401
