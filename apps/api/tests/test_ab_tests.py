"""Tests for the A/B test runner.

Covers:
  * Variant validation (>= 2 variants, unique names, traffic share sum)
  * Landing-page tests launch without provider writes
  * Ad-target tests launch by calling provider.create_campaign per variant
  * Provider failure on every variant surfaces as 502; partial-launch keeps
    the test in READY so the user can retry the failed variants
  * Workspace isolation
  * Winner declaration moves test to COMPLETED with timestamps
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations.meta_ads import MetaAdsProvider
from app.models.ab_test import AbTest, AbTestStatus, AbTestVariant
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.oauth_token import OAuthToken
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from datetime import datetime, timezone
from app.security.encryption import encrypt
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


def _seed_workspace(
    db: Session, *, email: str, role: Role
) -> tuple[User, Workspace]:
    user = User(
        email=email, hashed_password=hash_password("correct-horse-9"), is_active=True
    )
    db.add(user)
    db.flush()
    ws = Workspace(name="Test", slug=f"test-{email.split('@')[0]}")
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


def _seed_meta_account(db: Session, *, workspace: Workspace, user: User) -> None:
    account = ConnectedAccount(
        workspace_id=workspace.id,
        provider="meta_ads",
        provider_account_id="ext-id",
        display_name="Test acct",
        status=ConnectionStatus.CONNECTED,
        connected_by=user.id,
        connected_at=datetime.now(timezone.utc),
    )
    db.add(account)
    db.flush()
    db.add(
        OAuthToken(
            connected_account_id=account.id,
            encrypted_access_token=encrypt("real-access-token"),
            encrypted_refresh_token=None,
        )
    )
    db.commit()


def _login(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"}
    )
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


@pytest.fixture(autouse=True)
def _meta_creds():
    keys = {"META_APP_ID": "test-app", "META_APP_SECRET": "test-secret"}
    saved = {k: os.environ.get(k) for k in keys}
    os.environ.update(keys)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _landing_test_payload(name="Hero copy v1 vs v2") -> dict:
    return {
        "name": name,
        "hypothesis": "Specific value props beat generic ones.",
        "target": "landing_page",
        "objective": "conversion_rate",
        "variants": [
            {
                "name": "control",
                "is_control": True,
                "traffic_share": 0.5,
                "payload": {"url": "https://example.com/a", "copy": "v1"},
            },
            {
                "name": "treatment",
                "traffic_share": 0.5,
                "payload": {"url": "https://example.com/b", "copy": "v2"},
            },
        ],
    }


def _ad_test_payload() -> dict:
    return {
        "name": "Headline test",
        "target": "ad",
        "objective": "click_through_rate",
        "provider": "meta_ads",
        "external_account_id": "act_42",
        "variants": [
            {
                "name": "headline_a",
                "traffic_share": 0.5,
                "payload": {
                    "name": "Test — A",
                    "objective": "OUTCOME_LEADS",
                    "daily_budget_cents": 5000,
                },
            },
            {
                "name": "headline_b",
                "traffic_share": 0.5,
                "payload": {
                    "name": "Test — B",
                    "objective": "OUTCOME_LEADS",
                    "daily_budget_cents": 5000,
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_create_test_requires_two_variants(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    payload = _landing_test_payload()
    payload["variants"] = payload["variants"][:1]
    response = client.post(f"/api/v1/workspaces/{ws.id}/ab-tests", json=payload)
    # pydantic enforces min_length=2 → 422
    assert response.status_code == 422


def test_create_test_rejects_traffic_share_not_summing_to_one(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    payload = _landing_test_payload()
    payload["variants"][0]["traffic_share"] = 0.7
    payload["variants"][1]["traffic_share"] = 0.7
    response = client.post(f"/api/v1/workspaces/{ws.id}/ab-tests", json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_ab_test"


def test_ad_target_requires_provider_and_account(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    payload = _ad_test_payload()
    payload["external_account_id"] = None
    response = client.post(f"/api/v1/workspaces/{ws.id}/ab-tests", json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_ab_test"


# ---------------------------------------------------------------------------
# Landing-page launch
# ---------------------------------------------------------------------------


def test_landing_page_test_launches_without_provider_calls(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    create = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests", json=_landing_test_payload()
    )
    assert create.status_code == 200, create.text
    test_id = create.json()["id"]
    assert create.json()["status"] == "ready"

    launch = client.post(f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/launch")
    assert launch.status_code == 200, launch.text
    body = launch.json()
    assert body["status"] == "launched"
    assert body["started_at"] is not None
    for variant in body["variants"]:
        assert variant["launched_at"] is not None


# ---------------------------------------------------------------------------
# Ad-target launch
# ---------------------------------------------------------------------------


def test_ad_target_launch_calls_create_campaign_per_variant(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_meta_account(db_session, workspace=ws, user=user)
    _login(client, "alice@example.com")

    create = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests", json=_ad_test_payload()
    )
    test_id = create.json()["id"]

    call_count = {"n": 0}

    def fake_create(*, access_token, external_account_id, payload):
        call_count["n"] += 1
        return {
            "ok": True,
            "external_id": f"camp-{call_count['n']}",
            "external_account_id": external_account_id,
            "result": {"id": f"camp-{call_count['n']}"},
        }

    with patch.object(MetaAdsProvider, "create_campaign", side_effect=fake_create):
        launch = client.post(
            f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/launch"
        )
    assert launch.status_code == 200, launch.text
    assert launch.json()["status"] == "launched"
    assert call_count["n"] == 2
    ids = sorted(v["external_id"] for v in launch.json()["variants"])
    assert ids == ["camp-1", "camp-2"]


def test_ad_target_launch_partial_failure_keeps_status_ready(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_meta_account(db_session, workspace=ws, user=user)
    _login(client, "alice@example.com")

    create = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests", json=_ad_test_payload()
    )
    test_id = create.json()["id"]

    from app.integrations.base import ProviderError

    calls = {"n": 0}

    def flaky(*, access_token, external_account_id, payload):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "ok": True,
                "external_id": "camp-1",
                "external_account_id": external_account_id,
                "result": {"id": "camp-1"},
            }
        raise ProviderError("Meta said no.")

    with patch.object(MetaAdsProvider, "create_campaign", side_effect=flaky):
        launch = client.post(
            f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/launch"
        )
    assert launch.status_code == 200, launch.text
    body = launch.json()
    # First variant launched, second didn't — status stays READY for retry.
    assert body["status"] == "ready"
    launched = [v for v in body["variants"] if v["external_id"]]
    assert len(launched) == 1


def test_ad_target_full_failure_returns_502(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _seed_meta_account(db_session, workspace=ws, user=user)
    _login(client, "alice@example.com")

    create = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests", json=_ad_test_payload()
    )
    test_id = create.json()["id"]

    from app.integrations.base import ProviderError

    with patch.object(
        MetaAdsProvider, "create_campaign", side_effect=ProviderError("nope")
    ):
        launch = client.post(
            f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/launch"
        )
    assert launch.status_code == 502
    assert launch.json()["error"]["code"] == "ab_test_launch_failed"


def test_ad_target_launch_requires_admin(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(
        db_session, email="alice@example.com", role=Role.MARKETER
    )
    _seed_meta_account(db_session, workspace=ws, user=user)
    _login(client, "alice@example.com")

    create = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests", json=_ad_test_payload()
    )
    test_id = create.json()["id"]
    launch = client.post(f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/launch")
    assert launch.status_code == 403


# ---------------------------------------------------------------------------
# Metrics + winner
# ---------------------------------------------------------------------------


def test_record_metrics_and_declare_winner(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    create = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests", json=_landing_test_payload()
    )
    test_id = create.json()["id"]
    variant_a = create.json()["variants"][0]["id"]
    variant_b = create.json()["variants"][1]["id"]

    client.post(f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/launch")

    m1 = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/variants/{variant_a}/metrics",
        json={"metrics": {"visits": 1000, "conversions": 30}},
    )
    assert m1.status_code == 200
    m2 = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/variants/{variant_b}/metrics",
        json={"metrics": {"visits": 1000, "conversions": 48}},
    )
    assert m2.status_code == 200
    body = m2.json()
    metrics_by_id = {v["id"]: v["metrics"] for v in body["variants"]}
    assert metrics_by_id[variant_a]["conversions"] == 30
    assert metrics_by_id[variant_b]["conversions"] == 48

    winner = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/declare-winner",
        json={"variant_id": variant_b},
    )
    assert winner.status_code == 200, winner.text
    body = winner.json()
    assert body["status"] == "completed"
    assert body["winner_variant_id"] == variant_b
    assert body["ended_at"] is not None


def test_workspace_isolation(client: TestClient, db_session: Session) -> None:
    _, ws_a = _seed_workspace(
        db_session, email="alice@example.com", role=Role.OWNER
    )
    _, ws_b = _seed_workspace(db_session, email="bob@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    create = client.post(
        f"/api/v1/workspaces/{ws_a.id}/ab-tests", json=_landing_test_payload()
    )
    test_id = create.json()["id"]
    _login(client, "bob@example.com")
    fetch = client.get(f"/api/v1/workspaces/{ws_b.id}/ab-tests/{test_id}")
    assert fetch.status_code == 404


# ---------------------------------------------------------------------------
# Variant generation
# ---------------------------------------------------------------------------


def test_generate_variants_appends_to_draft_test(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    create = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests", json=_landing_test_payload()
    )
    assert create.status_code == 200
    test_id = create.json()["id"]

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/generate-variants?count=2"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # Started with 2 (control + treatment), generated 2 more → total 4
    assert len(body["variants"]) == 4
    # Generated variants are not the control
    new_variants = [v for v in body["variants"] if v["position"] >= 2]
    assert len(new_variants) == 2
    assert all(v["is_control"] is False for v in new_variants)


def test_generate_variants_refuses_when_test_launched(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    create = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests", json=_landing_test_payload()
    )
    test_id = create.json()["id"]
    # Force the test into LAUNCHED state directly so we don't depend on the
    # full launch path.
    test = db_session.query(AbTest).filter(AbTest.id == test_id).first()
    test.status = AbTestStatus.LAUNCHED
    db_session.commit()

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/generate-variants?count=1"
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ab_test_not_editable"


def test_generate_variants_preserves_traffic_share_invariant(
    client: TestClient, db_session: Session
) -> None:
    """Regression: variant generation used to hard-code traffic_share=0.10 on
    every new variant, breaking the sum-to-1.0 invariant. After generation,
    all variants must split traffic equally and sum to ~1.0 so the test
    can launch without manual rebalancing."""

    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    create = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests", json=_landing_test_payload()
    )
    test_id = create.json()["id"]

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/generate-variants?count=2"
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # 4 total variants, even split. Sum must be ~1.0 within tolerance.
    shares = [float(v["traffic_share"]) for v in body["variants"]]
    assert len(shares) == 4
    assert abs(sum(shares) - 1.0) < 0.01, (
        f"Traffic share sum drifted: {sum(shares)} (variants={shares})"
    )
    # Each share is approximately 1/N
    for s in shares:
        assert abs(s - 0.25) < 0.01

    # And the downstream launch path must not reject it.
    launch = client.post(f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/launch")
    assert launch.status_code == 200, launch.text
