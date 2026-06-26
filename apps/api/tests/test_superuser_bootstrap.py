from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.bootstrap import ensure_initial_superusers
from app.core.config import settings
from app.models.user import User


def _register(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "Founder"},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["access_token"]


def _with_superuser_emails(emails: list[str]):
    """Set settings.initial_superuser_emails, restoring afterwards."""

    class _Ctx:
        def __enter__(self):
            self._prev = settings.initial_superuser_emails
            settings.initial_superuser_emails = emails
            return self

        def __exit__(self, *exc):
            settings.initial_superuser_emails = self._prev
            return False

    return _Ctx()


def test_bootstrap_promotes_existing_user_case_insensitively(
    client: TestClient, db_session: Session
) -> None:
    _register(client, "founder@example.com")
    with _with_superuser_emails(["FOUNDER@Example.com"]):
        promoted = ensure_initial_superusers(db_session)
    assert promoted == ["founder@example.com"]
    user = db_session.query(User).filter(User.email == "founder@example.com").first()
    assert user is not None and user.is_superuser is True


def test_bootstrap_is_idempotent(client: TestClient, db_session: Session) -> None:
    _register(client, "founder2@example.com")
    with _with_superuser_emails(["founder2@example.com"]):
        first = ensure_initial_superusers(db_session)
        second = ensure_initial_superusers(db_session)
    assert first == ["founder2@example.com"]
    assert second == []  # already a superuser → no-op


def test_bootstrap_skips_unknown_email(db_session: Session) -> None:
    with _with_superuser_emails(["ghost@nowhere.io"]):
        promoted = ensure_initial_superusers(db_session)
    assert promoted == []


def test_bootstrap_empty_config_is_noop(db_session: Session) -> None:
    with _with_superuser_emails([]):
        assert ensure_initial_superusers(db_session) == []


def test_bootstrap_grants_admin_access(client: TestClient, db_session: Session) -> None:
    token = _register(client, "admin-founder@example.com")
    client.headers.update({"Authorization": f"Bearer {token}"})

    # Before promotion the /admin gate rejects the user.
    assert client.get("/api/v1/admin/overview").status_code == 403

    with _with_superuser_emails(["admin-founder@example.com"]):
        ensure_initial_superusers(db_session)

    # After promotion (committed) the same token now passes require_superuser.
    assert client.get("/api/v1/admin/overview").status_code == 200
