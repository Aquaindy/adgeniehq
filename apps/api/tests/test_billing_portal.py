"""Manage/cancel billing flow (PayPal).

PayPal has no per-customer hosted portal, so "Manage billing" appears for any
active PayPal subscription and resolves to the buyer's PayPal autopay list
(stored on the row at activation, with a constant fallback).
"""

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations import paypal_billing
from app.models.billing_subscription import (
    BillingSubscription,
    SubscriptionSource,
    SubscriptionStatus,
)


def _owner_workspace(client: TestClient, email: str = "owner@example.com") -> str:
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "Owner"},
    )
    client.headers.update({"Authorization": f"Bearer {reg.json()['access_token']}"})
    return client.post("/api/v1/workspaces", json={"name": "Acme"}).json()["id"]


def _add_paypal_sub(db: Session, workspace_id: str, *, management_url=None) -> None:
    db.add(
        BillingSubscription(
            workspace_id=UUID(workspace_id),
            plan_code="starter",
            source=SubscriptionSource.PAYPAL,
            status=SubscriptionStatus.ACTIVE,
            external_subscription_id="I-ABC123",
            management_url=management_url,
        )
    )
    db.commit()


def test_manage_button_shows_for_active_sub(
    client: TestClient, db_session: Session
) -> None:
    workspace_id = _owner_workspace(client)
    _add_paypal_sub(db_session, workspace_id, management_url=None)

    status = client.get(f"/api/v1/workspaces/{workspace_id}/billing/status").json()
    assert status["has_billing_customer"] is True
    assert status["subscription_status"] == "active"


def test_portal_falls_back_to_autopay_url(
    client: TestClient, db_session: Session
) -> None:
    """With no stored URL, the portal returns PayPal's autopay list."""
    workspace_id = _owner_workspace(client)
    _add_paypal_sub(db_session, workspace_id, management_url=None)

    resp = client.post(f"/api/v1/workspaces/{workspace_id}/billing/portal-session")
    assert resp.status_code == 201, resp.text
    assert resp.json()["url"] == paypal_billing.PAYPAL_AUTOPAY_URL


def test_portal_uses_stored_url_when_present(
    client: TestClient, db_session: Session
) -> None:
    workspace_id = _owner_workspace(client)
    _add_paypal_sub(
        db_session, workspace_id, management_url="https://www.paypal.com/myaccount/autopay/"
    )

    resp = client.post(f"/api/v1/workspaces/{workspace_id}/billing/portal-session")
    assert resp.status_code == 201
    assert resp.json()["url"] == "https://www.paypal.com/myaccount/autopay/"


def test_portal_503_without_subscription(
    client: TestClient, db_session: Session
) -> None:
    workspace_id = _owner_workspace(client)
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/billing/portal-session")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "billing_not_configured"
