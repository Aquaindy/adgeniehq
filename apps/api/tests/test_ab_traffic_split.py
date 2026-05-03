"""Public traffic-split: assign + convert + metric aggregation.

Pins the load-bearing behaviours of the public endpoints:
  * Sticky assignment — a visitor sees the same variant on every call
  * Workspace isolation — public endpoints don't leak past the test_id
  * Conversion needs a prior exposure
  * Metrics overlay computes from real exposure/conversion rows
  * CORS preflight succeeds (so the customer's site can hit us cross-origin)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.ab_test import AbTestStatus, AbTestVariant
from app.models.ab_test_event import AbTestConversion, AbTestExposure
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


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


def _login(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"}
    )
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


def _create_and_launch_test(
    client: TestClient, *, workspace_id, control_url="https://example.com/a", treatment_url="https://example.com/b"
):
    create = client.post(
        f"/api/v1/workspaces/{workspace_id}/ab-tests",
        json={
            "name": "Hero copy",
            "target": "landing_page",
            "objective": "conversion_rate",
            "variants": [
                {
                    "name": "control",
                    "is_control": True,
                    "traffic_share": 0.5,
                    "payload": {"url": control_url},
                },
                {
                    "name": "treatment",
                    "traffic_share": 0.5,
                    "payload": {"url": treatment_url},
                },
            ],
        },
    )
    assert create.status_code == 200, create.text
    test_id = create.json()["id"]
    launch = client.post(f"/api/v1/workspaces/{workspace_id}/ab-tests/{test_id}/launch")
    assert launch.status_code == 200, launch.text
    return test_id


# ---------------------------------------------------------------------------
# Sticky assignment
# ---------------------------------------------------------------------------


def test_assign_is_sticky_per_visitor(
    client: TestClient, db_session: Session
) -> None:
    """A visitor's first call decides the variant. Subsequent calls — even
    after many other visitors come through — return the same variant."""

    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    test_id = _create_and_launch_test(client, workspace_id=ws.id)

    # Strip auth — public endpoints don't require it.
    client.headers.pop("Authorization", None)

    first = client.post(
        f"/api/v1/public/ab-tests/{test_id}/assign",
        json={"visitor_id": "visitor-A"},
    )
    assert first.status_code == 200, first.text
    first_variant = first.json()["variant_id"]

    # Stir the pot with other visitors so the random pick has plenty of
    # opportunity to flip — sticky logic should still hold.
    for i in range(20):
        client.post(
            f"/api/v1/public/ab-tests/{test_id}/assign",
            json={"visitor_id": f"noise-{i}"},
        )

    second = client.post(
        f"/api/v1/public/ab-tests/{test_id}/assign",
        json={"visitor_id": "visitor-A"},
    )
    assert second.status_code == 200
    assert second.json()["variant_id"] == first_variant


def test_traffic_split_distributes_weighted(
    client: TestClient, db_session: Session
) -> None:
    """A 50/50 split should land in roughly equal buckets across many
    visitors. Loose bound to avoid flakiness."""

    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    test_id = _create_and_launch_test(client, workspace_id=ws.id)

    client.headers.pop("Authorization", None)

    counts: dict[str, int] = {}
    for i in range(200):
        resp = client.post(
            f"/api/v1/public/ab-tests/{test_id}/assign",
            json={"visitor_id": f"v-{i}"},
        )
        name = resp.json()["variant_name"]
        counts[name] = counts.get(name, 0) + 1
    assert sum(counts.values()) == 200
    # 50/50 with 200 trials — very loose bound.
    for name, count in counts.items():
        assert 60 <= count <= 140, f"variant {name} got {count} of 200 — distribution looks broken"


def test_assign_refuses_when_test_not_launched(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    create = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests",
        json={
            "name": "Not launched",
            "target": "landing_page",
            "objective": "conversion_rate",
            "variants": [
                {"name": "a", "traffic_share": 0.5, "payload": {"url": "https://example.com/a"}},
                {"name": "b", "traffic_share": 0.5, "payload": {"url": "https://example.com/b"}},
            ],
        },
    )
    test_id = create.json()["id"]

    client.headers.pop("Authorization", None)
    resp = client.post(
        f"/api/v1/public/ab-tests/{test_id}/assign",
        json={"visitor_id": "visitor-x"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ab_test_not_launched"


# ---------------------------------------------------------------------------
# Conversion + aggregation
# ---------------------------------------------------------------------------


def test_convert_requires_prior_assignment(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    test_id = _create_and_launch_test(client, workspace_id=ws.id)

    client.headers.pop("Authorization", None)
    resp = client.post(
        f"/api/v1/public/ab-tests/{test_id}/convert",
        json={"visitor_id": "ghost-visitor"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ab_test_unknown_visitor"


def test_metrics_aggregate_from_exposures_and_conversions(
    client: TestClient, db_session: Session
) -> None:
    """End-to-end: drive 12 visitors through assign, convert 4 of them, then
    GET the test and confirm visits/conversions/conversion_rate match."""

    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    test_id = _create_and_launch_test(client, workspace_id=ws.id)
    auth_headers = dict(client.headers)
    client.headers.pop("Authorization", None)

    visitor_variants: dict[str, str] = {}
    for i in range(12):
        vid = f"v-{i}"
        resp = client.post(
            f"/api/v1/public/ab-tests/{test_id}/assign",
            json={"visitor_id": vid},
        )
        visitor_variants[vid] = resp.json()["variant_id"]

    # Convert the first four.
    for vid in list(visitor_variants.keys())[:4]:
        conv = client.post(
            f"/api/v1/public/ab-tests/{test_id}/convert",
            json={"visitor_id": vid, "value_cents": 4900},
        )
        assert conv.status_code == 200

    # Re-auth and GET — service should hydrate variants with live aggregates.
    client.headers.update(auth_headers)
    detail = client.get(f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}")
    assert detail.status_code == 200
    body = detail.json()

    total_visits = sum(v["metrics"]["visits"] for v in body["variants"])
    total_conversions = sum(v["metrics"]["conversions"] for v in body["variants"])
    total_revenue = sum(v["metrics"]["revenue_cents"] for v in body["variants"])
    assert total_visits == 12
    assert total_conversions == 4
    assert total_revenue == 4 * 4900

    # Conversion rate ≈ conversions / visits per variant.
    for v in body["variants"]:
        m = v["metrics"]
        if m["visits"] > 0:
            expected = m["conversions"] / m["visits"]
            assert abs(m["conversion_rate"] - expected) < 1e-6


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


def test_cors_preflight_returns_permissive_headers(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    test_id = _create_and_launch_test(client, workspace_id=ws.id)

    client.headers.pop("Authorization", None)
    resp = client.options(
        f"/api/v1/public/ab-tests/{test_id}/assign",
        headers={
            "Origin": "https://customer-site.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 204
    assert resp.headers.get("access-control-allow-origin") == "*"
    assert "POST" in resp.headers.get("access-control-allow-methods", "")


def test_assign_response_carries_cors_header(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    test_id = _create_and_launch_test(client, workspace_id=ws.id)

    client.headers.pop("Authorization", None)
    resp = client.post(
        f"/api/v1/public/ab-tests/{test_id}/assign",
        json={"visitor_id": "v-x"},
        headers={"Origin": "https://customer-site.example"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"


# ---------------------------------------------------------------------------
# Static snippet — served at /static/advanta-ab.js
# ---------------------------------------------------------------------------


def test_static_snippet_is_reachable(client: TestClient) -> None:
    resp = client.get("/static/advanta-ab.js")
    assert resp.status_code == 200
    body = resp.text
    # Sanity: the snippet implements the assign+convert protocol we test above.
    assert "/api/v1/public/ab-tests/" in body
    assert "advantaConvert" in body
