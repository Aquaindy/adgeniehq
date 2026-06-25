"""Autoresponder integrations: adapter parsing (mocked HTTP) + service/endpoint
wiring (patched network boundary). Fully hermetic — no real network calls."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations.autoresponders.base import (
    Audience,
    AutoresponderAccountInfo,
    AutoresponderAuthError,
    AutoresponderError,
    Contact,
    PushResult,
)
from app.integrations.autoresponders.custom import CustomWebhookAdapter
from app.integrations.autoresponders.getresponse import GetResponseAdapter
from app.integrations.autoresponders.omnisend import OmnisendAdapter
from app.models.autoresponder_connection import AutoresponderConnection
from app.models.connected_account import ConnectionStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.encryption import decrypt
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed(db: Session, *, email: str, role: Role = Role.ADMIN) -> tuple[User, Workspace]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
    db.add(user)
    db.flush()
    ws = Workspace(name="Test", slug=f"test-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=ws.id, user_id=user.id, role=role, status=MemberStatus.ACTIVE
        )
    )
    db.commit()
    return user, ws


def _login(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"}
    )
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})


class _FakeResp:
    def __init__(self, body, *, status_code: int = 200, text: str = "", content: bytes = b"{}"):
        self.status_code = status_code
        self._b = body
        self.text = text
        self.content = content

    def json(self):
        return self._b


# ---------------------------------------------------------------------------
# Adapter unit tests (pure, mocked HTTP)
# ---------------------------------------------------------------------------


def test_omnisend_verify_ok() -> None:
    with patch.object(httpx, "get", return_value=_FakeResp({"contacts": []})):
        info = OmnisendAdapter.verify(api_key="k", config={})
    assert isinstance(info, AutoresponderAccountInfo)


def test_omnisend_verify_bad_key_raises_auth() -> None:
    with patch.object(httpx, "get", return_value=_FakeResp({}, status_code=401)):
        with pytest.raises(AutoresponderAuthError):
            OmnisendAdapter.verify(api_key="bad", config={})


def test_omnisend_verify_without_key_raises() -> None:
    with pytest.raises(AutoresponderAuthError):
        OmnisendAdapter.verify(api_key=None, config={})


def test_omnisend_push_builds_tagged_identifier_body() -> None:
    captured: dict = {}

    def _fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _FakeResp({"contactID": "abc"}, status_code=200)

    contacts = [Contact(email="a@b.com", first_name="Ann", tags=["existing"])]
    with patch.object(httpx, "post", side_effect=_fake_post):
        result = OmnisendAdapter.push_contacts(
            api_key="k", config={}, audience_id="newsletter", contacts=contacts
        )
    assert result.succeeded == 1 and result.failed == 0
    body = captured["json"]
    assert body["identifiers"][0]["type"] == "email"
    assert body["identifiers"][0]["id"] == "a@b.com"
    assert "newsletter" in body["tags"] and "existing" in body["tags"]
    assert body["firstName"] == "Ann"


def test_omnisend_push_counts_failures() -> None:
    with patch.object(httpx, "post", return_value=_FakeResp({}, status_code=422, text="bad")):
        result = OmnisendAdapter.push_contacts(
            api_key="k", config={}, audience_id="x",
            contacts=[Contact(email="a@b.com"), Contact(email="c@d.com")],
        )
    assert result.succeeded == 0 and result.failed == 2
    assert len(result.errors) == 2


def test_omnisend_pull_parses_contacts() -> None:
    body = {"contacts": [{"email": "x@y.com", "firstName": "X", "tags": ["lead"]}]}
    with patch.object(httpx, "get", return_value=_FakeResp(body)):
        contacts = OmnisendAdapter.pull_contacts(
            api_key="k", config={}, audience_id="lead", limit=50
        )
    assert len(contacts) == 1
    assert contacts[0].email == "x@y.com"
    assert contacts[0].first_name == "X"
    assert contacts[0].tags == ["lead"]


def test_getresponse_list_audiences_parses_campaigns() -> None:
    body = [
        {"campaignId": "L1", "name": "Newsletter"},
        {"campaignId": "L2", "name": "Leads"},
        {"name": "no-id-skipped"},
    ]
    with patch.object(httpx, "get", return_value=_FakeResp(body)):
        auds = GetResponseAdapter.list_audiences(api_key="k", config={})
    assert [a.external_id for a in auds] == ["L1", "L2"]
    assert auds[0].name == "Newsletter"


def test_getresponse_push_requires_list() -> None:
    with pytest.raises(AutoresponderError):
        GetResponseAdapter.push_contacts(
            api_key="k", config={}, audience_id=None, contacts=[Contact(email="a@b.com")]
        )


def test_custom_push_sends_auth_header_and_body() -> None:
    captured: dict = {}

    def _fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        return _FakeResp({}, status_code=200)

    config = {"push_url": "https://hooks.example.com/c", "auth_scheme": "Bearer"}
    with patch.object(httpx, "post", side_effect=_fake_post):
        result = CustomWebhookAdapter.push_contacts(
            api_key="secret", config=config, audience_id="list-7",
            contacts=[Contact(email="a@b.com")],
        )
    assert result.succeeded == 1
    assert captured["url"] == "https://hooks.example.com/c"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["json"]["list"] == "list-7"


def test_custom_requires_valid_push_url() -> None:
    with pytest.raises(AutoresponderError):
        CustomWebhookAdapter.push_contacts(
            api_key=None, config={"push_url": "not-a-url"}, audience_id=None,
            contacts=[Contact(email="a@b.com")],
        )


# ---------------------------------------------------------------------------
# Catalog + connect/disconnect endpoints
# ---------------------------------------------------------------------------


def test_catalog_lists_providers(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _login(client, "o@example.com")
    resp = client.get(f"/api/v1/workspaces/{ws.id}/autoresponders/catalog")
    assert resp.status_code == 200
    providers = {p["provider"]: p for p in resp.json()}
    assert "omnisend" in providers and "getresponse" in providers and "custom" in providers
    # Omnisend ships first and is tag-based (freeform audience, no listing).
    assert providers["omnisend"]["freeform_audience"] is True
    assert providers["omnisend"]["supports_audience_listing"] is False
    assert providers["getresponse"]["supports_audience_listing"] is True
    assert providers["custom"]["requires_api_key"] is False


def test_connect_stores_encrypted_key(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _login(client, "o@example.com")
    info = AutoresponderAccountInfo(account_id=None, display_name="Omnisend store")
    with patch.object(OmnisendAdapter, "verify", return_value=info):
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/autoresponders/omnisend/connect",
            json={"api_key": "super-secret-key", "config": {}},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == ConnectionStatus.CONNECTED.value
    # Key is encrypted at rest, never returned in the response.
    assert "super-secret-key" not in resp.text
    row = (
        db_session.query(AutoresponderConnection)
        .filter(AutoresponderConnection.workspace_id == ws.id)
        .one()
    )
    assert row.encrypted_api_key and row.encrypted_api_key != "super-secret-key"
    assert decrypt(row.encrypted_api_key) == "super-secret-key"


def test_connect_bad_key_records_error(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _login(client, "o@example.com")
    with patch.object(
        OmnisendAdapter, "verify", side_effect=AutoresponderAuthError("nope")
    ):
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/autoresponders/omnisend/connect",
            json={"api_key": "bad", "config": {}},
        )
    assert resp.status_code == 401
    row = (
        db_session.query(AutoresponderConnection)
        .filter(AutoresponderConnection.workspace_id == ws.id)
        .one()
    )
    assert row.status == ConnectionStatus.ERROR
    assert row.encrypted_api_key is None  # bad key not persisted


def test_connect_requires_admin(client: TestClient, db_session: Session) -> None:
    _seed(db_session, email="m@example.com", role=Role.MARKETER)
    _login(client, "m@example.com")
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]
    info = AutoresponderAccountInfo(account_id=None, display_name="x")
    with patch.object(OmnisendAdapter, "verify", return_value=info):
        resp = client.post(
            f"/api/v1/workspaces/{ws_id}/autoresponders/omnisend/connect",
            json={"api_key": "k", "config": {}},
        )
    assert resp.status_code == 403


def test_custom_connect_validates_required_config(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _login(client, "o@example.com")
    # Missing required push_url for the custom connector.
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/autoresponders/custom/connect",
        json={"api_key": None, "config": {}},
    )
    assert resp.status_code == 422


def test_disconnect_clears_key(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _login(client, "o@example.com")
    info = AutoresponderAccountInfo(account_id=None, display_name="x")
    with patch.object(OmnisendAdapter, "verify", return_value=info):
        client.post(
            f"/api/v1/workspaces/{ws.id}/autoresponders/omnisend/connect",
            json={"api_key": "k", "config": {}},
        )
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/autoresponders/omnisend/disconnect"
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == ConnectionStatus.DISCONNECTED.value
    row = (
        db_session.query(AutoresponderConnection)
        .filter(AutoresponderConnection.workspace_id == ws.id)
        .one()
    )
    assert row.encrypted_api_key is None


def test_unknown_provider_404(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _login(client, "o@example.com")
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/autoresponders/nope/connect",
        json={"api_key": "k", "config": {}},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Audiences + contact sync (both directions)
# ---------------------------------------------------------------------------


def _connect_omnisend(client: TestClient, ws_id: str) -> None:
    info = AutoresponderAccountInfo(account_id=None, display_name="store")
    with patch.object(OmnisendAdapter, "verify", return_value=info):
        r = client.post(
            f"/api/v1/workspaces/{ws_id}/autoresponders/omnisend/connect",
            json={"api_key": "k", "config": {}},
        )
    assert r.status_code == 200, r.text


def test_audiences_endpoint_getresponse(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _login(client, "o@example.com")
    info = AutoresponderAccountInfo(account_id="1", display_name="acct")
    with patch.object(GetResponseAdapter, "verify", return_value=info):
        client.post(
            f"/api/v1/workspaces/{ws.id}/autoresponders/getresponse/connect",
            json={"api_key": "k", "config": {}},
        )
    auds = [Audience(external_id="L1", name="Newsletter")]
    with patch.object(GetResponseAdapter, "list_audiences", return_value=auds):
        resp = client.get(
            f"/api/v1/workspaces/{ws.id}/autoresponders/getresponse/audiences"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["supports_audience_listing"] is True
    assert data["audiences"][0]["external_id"] == "L1"


def test_push_contacts_records_sync(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _login(client, "o@example.com")
    _connect_omnisend(client, str(ws.id))

    result = PushResult(requested=2, succeeded=2, failed=0)
    with patch.object(OmnisendAdapter, "push_contacts", return_value=result):
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/autoresponders/omnisend/push",
            json={
                "audience_id": "leads",
                "source": "manual",
                "contacts": [
                    {"email": "a@b.com", "first_name": "Ann"},
                    {"email": "c@d.com"},
                ],
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["direction"] == "push"
    assert body["status"] == "succeeded"
    assert body["succeeded_count"] == 2

    activity = client.get(
        f"/api/v1/workspaces/{ws.id}/autoresponders/activity"
    ).json()
    assert len(activity) == 1
    assert activity[0]["audience_external_id"] == "leads"


def test_push_partial_outcome(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _login(client, "o@example.com")
    _connect_omnisend(client, str(ws.id))
    result = PushResult(requested=2, succeeded=1, failed=1, errors=["c@d.com: HTTP 422"])
    with patch.object(OmnisendAdapter, "push_contacts", return_value=result):
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/autoresponders/omnisend/push",
            json={"contacts": [{"email": "a@b.com"}, {"email": "c@d.com"}]},
        )
    assert resp.json()["status"] == "partial"


def test_pull_contacts_returns_and_logs(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _login(client, "o@example.com")
    _connect_omnisend(client, str(ws.id))
    pulled = [Contact(email="x@y.com", first_name="X"), Contact(email="z@w.com")]
    with patch.object(OmnisendAdapter, "pull_contacts", return_value=pulled):
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/autoresponders/omnisend/pull",
            json={"audience_id": "leads", "limit": 50},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["contacts"]) == 2
    assert body["contacts"][0]["email"] == "x@y.com"
    assert body["sync"]["direction"] == "pull"
    assert body["sync"]["succeeded_count"] == 2


def test_push_before_connect_409(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _login(client, "o@example.com")
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/autoresponders/omnisend/push",
        json={"contacts": [{"email": "a@b.com"}]},
    )
    assert resp.status_code == 409


def test_push_requires_marketer(client: TestClient, db_session: Session) -> None:
    _seed(db_session, email="a@example.com", role=Role.ANALYST)
    _login(client, "a@example.com")
    ws_id = client.get("/api/v1/workspaces").json()[0]["id"]
    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/autoresponders/omnisend/push",
        json={"contacts": [{"email": "a@b.com"}]},
    )
    assert resp.status_code == 403


def test_autoresponder_isolation(client: TestClient, db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _seed(db_session, email="evil@example.com")
    _login(client, "evil@example.com")
    resp = client.get(f"/api/v1/workspaces/{ws.id}/autoresponders")
    assert resp.status_code == 404
