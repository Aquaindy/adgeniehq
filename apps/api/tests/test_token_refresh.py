"""Token refresh on the execution + sync paths.

A long-lived workspace's access tokens roll over every 30-60 minutes for most
providers. Without auto-refresh, the next outbound write fails with a
provider 401 and the user is left wondering why. These tests pin the refresh
behaviour so it stays correct as we add more provider write methods."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations.base import (
    ProviderError,
    ProviderTokens,
)
from app.integrations.meta_ads import MetaAdsProvider
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.oauth_token import OAuthToken
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.encryption import decrypt, encrypt
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.services import integration_service


def _seed_workspace(
    db: Session, *, email: str
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
            role=Role.OWNER,
            status=MemberStatus.ACTIVE,
        )
    )
    db.commit()
    return user, ws


def _seed_account_with_token(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    expires_at: datetime | None,
    refresh_token: str | None = "real-refresh-token",
    access_token: str = "real-access-token",
    provider: str = "meta_ads",
) -> ConnectedAccount:
    account = ConnectedAccount(
        workspace_id=workspace.id,
        provider=provider,
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
            encrypted_access_token=encrypt(access_token),
            encrypted_refresh_token=encrypt(refresh_token) if refresh_token else None,
            expires_at=expires_at,
        )
    )
    db.commit()
    db.refresh(account)
    return account


@pytest.fixture(autouse=True)
def _meta_creds():
    keys = {"META_APP_ID": "test", "META_APP_SECRET": "test"}
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


# ---------------------------------------------------------------------------
# Direct unit tests on get_fresh_access_token
# ---------------------------------------------------------------------------


def test_fresh_token_returns_as_is_without_refresh(db_session: Session) -> None:
    """Token with > buffer remaining should be returned without calling refresh."""

    user, ws = _seed_workspace(db_session, email="alice@example.com")
    account = _seed_account_with_token(
        db_session,
        workspace=ws,
        user=user,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    with patch.object(
        MetaAdsProvider,
        "refresh_access_token",
        side_effect=AssertionError("must not be called"),
    ):
        token = integration_service.get_fresh_access_token(
            db_session, account=account
        )
    assert token == "real-access-token"


def test_token_without_expiry_returns_as_is(db_session: Session) -> None:
    """Some providers (long-lived LinkedIn, GA4 server tokens) ship without an
    expiry. We hand the existing token back rather than guessing."""

    user, ws = _seed_workspace(db_session, email="alice@example.com")
    account = _seed_account_with_token(
        db_session, workspace=ws, user=user, expires_at=None
    )
    with patch.object(
        MetaAdsProvider,
        "refresh_access_token",
        side_effect=AssertionError("must not be called"),
    ):
        token = integration_service.get_fresh_access_token(
            db_session, account=account
        )
    assert token == "real-access-token"


def test_expired_token_triggers_refresh_and_persists_new_value(
    db_session: Session,
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com")
    expired = datetime.now(timezone.utc) - timedelta(minutes=5)
    account = _seed_account_with_token(
        db_session, workspace=ws, user=user, expires_at=expired
    )

    new_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    fake_refresh_result = ProviderTokens(
        access_token="rotated-access-token",
        refresh_token="rotated-refresh-token",
        expires_at=new_expiry,
        scopes=None,
    )

    with patch.object(
        MetaAdsProvider, "refresh_access_token", return_value=fake_refresh_result
    ) as refresh_mock:
        token = integration_service.get_fresh_access_token(
            db_session, account=account
        )

    refresh_mock.assert_called_once()
    assert token == "rotated-access-token"

    # Persisted fields are encrypted; decrypt to confirm.
    db_session.refresh(account.token)
    assert decrypt(account.token.encrypted_access_token) == "rotated-access-token"
    assert (
        decrypt(account.token.encrypted_refresh_token) == "rotated-refresh-token"
    )
    # Allow tiny clock drift between the test and the model's commit timestamp.
    persisted = account.token.expires_at
    assert persisted is not None
    assert abs((persisted - new_expiry).total_seconds()) < 5


def test_refresh_omitting_new_refresh_token_keeps_old_one(
    db_session: Session,
) -> None:
    """Google omits refresh_token on subsequent refreshes; we must keep the
    original one rather than nulling it out."""

    user, ws = _seed_workspace(db_session, email="alice@example.com")
    account = _seed_account_with_token(
        db_session,
        workspace=ws,
        user=user,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    fake_refresh_result = ProviderTokens(
        access_token="rotated-access",
        refresh_token=None,  # provider didn't issue a new one
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=None,
    )
    with patch.object(
        MetaAdsProvider, "refresh_access_token", return_value=fake_refresh_result
    ):
        integration_service.get_fresh_access_token(db_session, account=account)

    db_session.refresh(account.token)
    assert decrypt(account.token.encrypted_access_token) == "rotated-access"
    assert (
        decrypt(account.token.encrypted_refresh_token) == "real-refresh-token"
    )


def test_refresh_failure_marks_account_error_and_raises_401(
    db_session: Session,
) -> None:
    """If the provider rejects the refresh (revoked, deleted app, etc.) we
    must surface a 401 so the UI prompts the user to reconnect, not a 502
    that looks like a transient error."""

    user, ws = _seed_workspace(db_session, email="alice@example.com")
    account = _seed_account_with_token(
        db_session,
        workspace=ws,
        user=user,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    with patch.object(
        MetaAdsProvider,
        "refresh_access_token",
        side_effect=ProviderError("invalid_grant"),
    ):
        with pytest.raises(integration_service.TokenRefreshFailedError) as exc:
            integration_service.get_fresh_access_token(
                db_session, account=account
            )
    assert exc.value.status_code == 401

    db_session.refresh(account)
    assert account.status == ConnectionStatus.ERROR
    assert "Token refresh failed" in (account.last_error or "")


def test_account_with_no_refresh_token_falls_back_to_existing_access_token(
    db_session: Session,
) -> None:
    """If we never received a refresh token, refresh isn't an option. Hand
    back what we have so the provider call can fail clearly if needed."""

    user, ws = _seed_workspace(db_session, email="alice@example.com")
    account = _seed_account_with_token(
        db_session,
        workspace=ws,
        user=user,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        refresh_token=None,
    )
    with patch.object(
        MetaAdsProvider,
        "refresh_access_token",
        side_effect=AssertionError("must not be called when no refresh token"),
    ):
        token = integration_service.get_fresh_access_token(
            db_session, account=account
        )
    assert token == "real-access-token"


# ---------------------------------------------------------------------------
# End-to-end: an /execute call refreshes then dispatches with the fresh token.
# ---------------------------------------------------------------------------


def test_execute_endpoint_refreshes_expired_token_before_dispatch(
    client: TestClient, db_session: Session
) -> None:
    """The new token must be the one passed to the provider write."""

    from app.models.agent_run import AgentRun, AgentRunStatus
    from app.models.approval import Approval, ApprovalStatus
    from app.models.recommendation import (
        Recommendation,
        RecommendationStatus,
        RiskLevel,
    )

    user, ws = _seed_workspace(db_session, email="alice@example.com")
    account = _seed_account_with_token(
        db_session,
        workspace=ws,
        user=user,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )

    # Seed an actionable recommendation pointed at the connected meta_ads account.
    run = AgentRun(
        workspace_id=ws.id,
        agent_type="paid_ads",
        status=AgentRunStatus.SUCCEEDED,
    )
    db_session.add(run)
    db_session.flush()
    rec = Recommendation(
        workspace_id=ws.id,
        agent_run_id=run.id,
        title="Pause campaign",
        summary="—",
        recommendation_type="campaign.pause",
        risk_level=RiskLevel.LOW,
        expected_impact="—",
        suggested_action="—",
        status=RecommendationStatus.OPEN,
        platform="meta_ads",
        metadata_json={
            "provider": "meta_ads",
            "action": "campaign.pause",
            "external_id": "100",
            "external_account_id": "act_42",
            "payload": {},
        },
    )
    db_session.add(rec)
    db_session.flush()
    db_session.add(
        Approval(
            workspace_id=ws.id,
            recommendation_id=rec.id,
            action_type=rec.recommendation_type,
            risk_level=rec.risk_level,
            status=ApprovalStatus.PENDING,
        )
    )
    db_session.commit()

    fake_refresh_result = ProviderTokens(
        access_token="freshly-rotated-token",
        refresh_token=None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=None,
    )
    captured: dict = {}

    def fake_pause(*, access_token, external_account_id, external_id):
        captured["access_token"] = access_token
        return {
            "ok": True,
            "prior_state": {"status": "ACTIVE"},
            "result": {"id": external_id},
        }

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correct-horse-9"},
    )
    client.headers.update(
        {"Authorization": f"Bearer {resp.json()['access_token']}"}
    )

    with patch.object(
        MetaAdsProvider,
        "refresh_access_token",
        return_value=fake_refresh_result,
    ), patch.object(MetaAdsProvider, "pause_campaign", side_effect=fake_pause):
        approve = client.post(
            f"/api/v1/workspaces/{ws.id}/recommendations/{rec.id}/approve"
        )
    assert approve.status_code == 200, approve.text
    # Provider must have received the post-refresh token, not the stale one.
    assert captured["access_token"] == "freshly-rotated-token"
