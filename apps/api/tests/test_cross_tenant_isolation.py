"""Cross-tenant isolation + RBAC-denial coverage across the workspace-scoped
surface. These are the core multi-tenant security boundaries:

  * a user who is NOT a member of a workspace gets 404 on its resources
    (non-existence, no info leak) — verified across many routers, not just one;
  * a member with an insufficient role gets 403 on owner/admin-only mutations.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


def _register(client: TestClient, email: str) -> tuple[str, str]:
    """Register a fresh user (own client cookies), return (token, workspace_id)."""
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "U"},
    )
    token = reg.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    ws = client.post("/api/v1/workspaces", json={"name": "WS"}).json()
    return token, ws["id"]


# ---------------------------------------------------------------------------
# Cross-tenant: a non-member cannot read another workspace's resources.
# ---------------------------------------------------------------------------

_SCOPED_GET_ROUTES = [
    "campaigns",
    "recommendations",
    "autopilot",
    "integrations",
    "reports",
    "billing/status",
    "agents/runs",
]


def _seed_foreign_workspace(db: Session) -> str:
    """A workspace owned by someone else that the test's caller is NOT in."""
    bob = User(
        email="bob@example.com",
        hashed_password=hash_password("correct-horse-9"),
        is_active=True,
    )
    db.add(bob)
    db.flush()
    ws = Workspace(name="Bob WS", slug="bob-ws")
    db.add(ws)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=ws.id, user_id=bob.id, role=Role.OWNER, status=MemberStatus.ACTIVE
        )
    )
    db.commit()
    return str(ws.id)


@pytest.mark.parametrize("suffix", _SCOPED_GET_ROUTES)
def test_non_member_cannot_read_other_workspace(
    client: TestClient, db_session: Session, suffix: str
) -> None:
    # Alice authenticates; Bob's workspace exists but Alice isn't a member.
    _register(client, "alice@example.com")
    ws_b = _seed_foreign_workspace(db_session)

    resp = client.get(f"/api/v1/workspaces/{ws_b}/{suffix}")
    assert resp.status_code == 404, f"{suffix} leaked cross-tenant: {resp.status_code}"


# ---------------------------------------------------------------------------
# RBAC: a Viewer member cannot perform owner/admin-only mutations.
# ---------------------------------------------------------------------------


def _seed_viewer_in_workspace(db: Session, workspace_id: str) -> None:
    viewer = User(
        email="viewer@example.com",
        hashed_password=hash_password("correct-horse-9"),
        is_active=True,
    )
    db.add(viewer)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=workspace_id,
            user_id=viewer.id,
            role=Role.VIEWER,
            status=MemberStatus.ACTIVE,
        )
    )
    db.commit()


def _login(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"}
    )
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})


def test_viewer_cannot_change_autopilot_config(client: TestClient, db_session: Session) -> None:
    _, ws = _register(client, "owner-a@example.com")
    _seed_viewer_in_workspace(db_session, ws)
    _login(client, "viewer@example.com")

    resp = client.patch(f"/api/v1/workspaces/{ws}/autopilot", json={"mode": "off"})
    assert resp.status_code == 403


def test_viewer_cannot_start_checkout(client: TestClient, db_session: Session) -> None:
    _, ws = _register(client, "owner-b@example.com")
    _seed_viewer_in_workspace(db_session, ws)
    _login(client, "viewer@example.com")

    resp = client.post(
        f"/api/v1/workspaces/{ws}/billing/checkout-session", json={"plan_code": "starter"}
    )
    assert resp.status_code == 403


def test_viewer_cannot_invite_members(client: TestClient, db_session: Session) -> None:
    _, ws = _register(client, "owner-c@example.com")
    _seed_viewer_in_workspace(db_session, ws)
    _login(client, "viewer@example.com")

    resp = client.post(
        f"/api/v1/workspaces/{ws}/members/invite",
        json={"email": "new@example.com", "role": "marketer"},
    )
    assert resp.status_code == 403
