"""Ad-hierarchy endpoint tests.

Goals:
- Empty workspace returns empty arrays from each list endpoint.
- Lists honour the `campaign_id` / `ad_group_id` / `type` / `source` filters.
- get_one 404s in a different workspace.
- PATCH /creatives mutates only whitelisted fields, audit-logs the diff,
  and refuses for analyst-or-lower roles.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.ad import Ad, AdStatus
from app.models.ad_group import AdGroup, AdGroupStatus
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign, CampaignStatus
from app.models.creative import Creative, CreativeSource, CreativeType
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


def _seed_workspace(db: Session, *, email: str, role: Role) -> tuple[User, Workspace]:
    user = User(
        email=email,
        hashed_password=hash_password("correct-horse-9"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    ws = Workspace(name="Acme", slug=f"acme-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=ws.id,
            user_id=user.id,
            role=role,
            status=MemberStatus.ACTIVE,
        )
    )
    db.commit()
    return user, ws


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-9"},
    )
    token = response.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


def _seed_campaign(db: Session, *, workspace: Workspace) -> Campaign:
    campaign = Campaign(
        workspace_id=workspace.id,
        provider="meta_ads",
        external_id="ext-cmp-1",
        name="Test campaign",
        status=CampaignStatus.ACTIVE,
        last_synced_at=datetime.now(timezone.utc),
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def test_empty_workspace_returns_empty_arrays(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    for path in ("ad-groups", "ads", "creatives"):
        response = client.get(f"/api/v1/workspaces/{ws.id}/{path}")
        assert response.status_code == 200
        assert response.json() == []


def test_creatives_filters_by_type_and_source(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    db_session.add_all(
        [
            Creative(
                workspace_id=ws.id,
                type=CreativeType.SEARCH_AD,
                source=CreativeSource.AI_GENERATED,
                headline="A",
            ),
            Creative(
                workspace_id=ws.id,
                type=CreativeType.SEARCH_AD,
                source=CreativeSource.PLATFORM_SYNCED,
                headline="B",
            ),
            Creative(
                workspace_id=ws.id,
                type=CreativeType.SINGLE_IMAGE,
                source=CreativeSource.AI_GENERATED,
                headline="C",
            ),
        ]
    )
    db_session.commit()
    _login(client, "alice@example.com")

    all_resp = client.get(f"/api/v1/workspaces/{ws.id}/creatives").json()
    assert len(all_resp) == 3

    search_only = client.get(
        f"/api/v1/workspaces/{ws.id}/creatives?type=search_ad"
    ).json()
    assert len(search_only) == 2

    ai_only = client.get(
        f"/api/v1/workspaces/{ws.id}/creatives?source=ai_generated"
    ).json()
    assert len(ai_only) == 2


def test_ads_filters_by_ad_group_id(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    campaign = _seed_campaign(db_session, workspace=ws)

    group_a = AdGroup(
        workspace_id=ws.id,
        campaign_id=campaign.id,
        external_id="grp-a",
        name="Group A",
        status=AdGroupStatus.ACTIVE,
        last_synced_at=datetime.now(timezone.utc),
    )
    group_b = AdGroup(
        workspace_id=ws.id,
        campaign_id=campaign.id,
        external_id="grp-b",
        name="Group B",
        status=AdGroupStatus.ACTIVE,
        last_synced_at=datetime.now(timezone.utc),
    )
    db_session.add_all([group_a, group_b])
    db_session.flush()

    db_session.add_all(
        [
            Ad(
                workspace_id=ws.id,
                campaign_id=campaign.id,
                ad_group_id=group_a.id,
                external_id="ad-a1",
                name="Ad A1",
                status=AdStatus.ACTIVE,
                last_synced_at=datetime.now(timezone.utc),
            ),
            Ad(
                workspace_id=ws.id,
                campaign_id=campaign.id,
                ad_group_id=group_b.id,
                external_id="ad-b1",
                name="Ad B1",
                status=AdStatus.ACTIVE,
                last_synced_at=datetime.now(timezone.utc),
            ),
        ]
    )
    db_session.commit()
    _login(client, "alice@example.com")

    all_ads = client.get(f"/api/v1/workspaces/{ws.id}/ads").json()
    assert len(all_ads) == 2

    only_b = client.get(
        f"/api/v1/workspaces/{ws.id}/ads?ad_group_id={group_b.id}"
    ).json()
    assert len(only_b) == 1
    assert only_b[0]["name"] == "Ad B1"


def test_get_creative_404_in_other_workspace(
    client: TestClient, db_session: Session
) -> None:
    user_a, ws_a = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    creative = Creative(
        workspace_id=ws_a.id,
        type=CreativeType.SEARCH_AD,
        source=CreativeSource.AI_GENERATED,
        headline="A",
    )
    db_session.add(creative)
    db_session.commit()

    _user_b, ws_b = _seed_workspace(db_session, email="bob@example.com", role=Role.OWNER)
    _login(client, "bob@example.com")

    response = client.get(
        f"/api/v1/workspaces/{ws_b.id}/creatives/{creative.id}"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "creative_not_found"


def test_patch_creative_logs_diff_and_only_touches_whitelisted_fields(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    creative = Creative(
        workspace_id=ws.id,
        type=CreativeType.SEARCH_AD,
        source=CreativeSource.AI_GENERATED,
        headline="Old headline",
        description="Old description",
    )
    db_session.add(creative)
    db_session.commit()

    _login(client, "alice@example.com")
    response = client.patch(
        f"/api/v1/workspaces/{ws.id}/creatives/{creative.id}",
        json={
            "headline": "New headline",
            "description": "New description",
            # Attempt to mutate immutable fields — should be ignored by schema.
            "type": "video",
            "source": "platform_synced",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["headline"] == "New headline"
    assert body["description"] == "New description"
    # Immutable fields preserved
    assert body["type"] == "search_ad"
    assert body["source"] == "ai_generated"

    # Audit row records the diff.
    audits = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.workspace_id == ws.id,
            AuditLog.action == "creative.updated",
        )
        .all()
    )
    assert len(audits) == 1
    changes = audits[0].metadata_json["changes"]
    assert "headline" in changes
    assert changes["headline"]["from"] == "Old headline"
    assert changes["headline"]["to"] == "New headline"


def test_patch_creative_refuses_for_viewer(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(
        db_session, email="viewer@example.com", role=Role.VIEWER
    )
    creative = Creative(
        workspace_id=ws.id,
        type=CreativeType.SEARCH_AD,
        source=CreativeSource.AI_GENERATED,
        headline="Old",
    )
    db_session.add(creative)
    db_session.commit()

    _login(client, "viewer@example.com")
    response = client.patch(
        f"/api/v1/workspaces/{ws.id}/creatives/{creative.id}",
        json={"headline": "Hijacked"},
    )
    assert response.status_code == 403
