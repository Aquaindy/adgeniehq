"""Ad-structure builder: user-built ad groups, ads, creatives under a campaign."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.ad import Ad
from app.models.ad_group import AdGroup, AdGroupStatus, AdObjectSource
from app.models.campaign import Campaign, CampaignStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


def _seed(db: Session, *, email: str, role: Role = Role.OWNER) -> tuple[User, Workspace]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
    db.add(user)
    db.flush()
    ws = Workspace(name="Test", slug=f"test-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role, status=MemberStatus.ACTIVE))
    db.commit()
    return user, ws


def _campaign(db: Session, *, ws: Workspace) -> Campaign:
    c = Campaign(
        workspace_id=ws.id,
        provider="meta_ads",
        external_id="100",
        external_account_id="act_42",
        name="Camp",
        status=CampaignStatus.ACTIVE,
        daily_budget_cents=4000,
        currency="USD",
        last_synced_at=datetime.now(timezone.utc),
        raw_payload={},
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _login(client: TestClient, email: str) -> None:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"})
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})


def test_build_ad_group_creative_and_ad(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    c = _campaign(db_session, ws=ws)
    _login(client, "o@example.com")

    # Ad group with targeting + budget.
    ag = client.post(
        f"/api/v1/workspaces/{ws.id}/campaigns/{c.id}/ad-groups",
        json={
            "name": "US · 25-44 · Founders",
            "daily_budget_cents": 3000,
            "targeting": {"locations": ["US"], "age_min": 25, "age_max": 44, "interests": ["SaaS"]},
        },
    )
    assert ag.status_code == 201, ag.text
    ag_body = ag.json()
    assert ag_body["source"] == "advanta_draft"
    assert ag_body["external_id"] is None
    assert ag_body["status"] == "paused"
    assert ag_body["targeting"]["age_min"] == 25

    # User-created creative.
    cr = client.post(
        f"/api/v1/workspaces/{ws.id}/creatives",
        json={"type": "single_image", "headline": "Stop guessing", "primary_text": "Score it first", "cta": "Try free"},
    )
    assert cr.status_code == 201, cr.text
    assert cr.json()["source"] == "user_uploaded"

    # Ad linking the creative under the ad group.
    ad = client.post(
        f"/api/v1/workspaces/{ws.id}/ad-groups/{ag_body['id']}/ads",
        json={"name": "Ad 1", "landing_page_url": "https://x.example", "creative_id": cr.json()["id"]},
    )
    assert ad.status_code == 201, ad.text
    assert ad.json()["creative_id"] == cr.json()["id"]
    assert ad.json()["source"] == "advanta_draft"

    # It shows up in the read list filtered by campaign.
    listed = client.get(f"/api/v1/workspaces/{ws.id}/ad-groups?campaign_id={c.id}").json()
    assert len(listed) == 1


def test_builder_requires_marketer(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="a@example.com", role=Role.ANALYST)
    c = _campaign(db_session, ws=ws)
    _login(client, "a@example.com")
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/campaigns/{c.id}/ad-groups",
        json={"name": "x", "targeting": {}},
    )
    assert resp.status_code == 403


def test_synced_ad_group_is_read_only(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    c = _campaign(db_session, ws=ws)
    synced = AdGroup(
        workspace_id=ws.id,
        campaign_id=c.id,
        external_id="ext-1",
        source=AdObjectSource.PLATFORM_SYNCED,
        name="Synced",
        status=AdGroupStatus.ACTIVE,
        last_synced_at=datetime.now(timezone.utc),
    )
    db_session.add(synced)
    db_session.commit()

    _login(client, "o@example.com")
    resp = client.patch(
        f"/api/v1/workspaces/{ws.id}/ad-groups/{synced.id}", json={"name": "Hacked"}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "not_editable"


def test_delete_ad_group_cascades_ads(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    c = _campaign(db_session, ws=ws)
    _login(client, "o@example.com")
    ag = client.post(
        f"/api/v1/workspaces/{ws.id}/campaigns/{c.id}/ad-groups",
        json={"name": "G", "targeting": {}},
    ).json()
    client.post(
        f"/api/v1/workspaces/{ws.id}/ad-groups/{ag['id']}/ads", json={"name": "Ad"}
    )
    assert db_session.query(Ad).count() == 1

    deleted = client.delete(f"/api/v1/workspaces/{ws.id}/ad-groups/{ag['id']}")
    assert deleted.status_code == 204
    assert db_session.query(AdGroup).count() == 0
    assert db_session.query(Ad).count() == 0  # cascade


def test_campaign_not_found_on_create(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _login(client, "o@example.com")
    import uuid

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/campaigns/{uuid.uuid4()}/ad-groups",
        json={"name": "G", "targeting": {}},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "campaign_not_found"


def test_workspace_isolation(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    c = _campaign(db_session, ws=ws)
    _seed(db_session, email="evil@example.com")
    _login(client, "evil@example.com")
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/campaigns/{c.id}/ad-groups",
        json={"name": "G", "targeting": {}},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "workspace_not_found"
