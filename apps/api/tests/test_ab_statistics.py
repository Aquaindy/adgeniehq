"""A/B statistics + min-sample-size guard.

Pins:
  * Two-proportion z-test produces sane p-values for known cases
  * Wald CIs cover the conversion rate
  * declare_winner refuses when underpowered
  * declare_winner refuses when result not significant
  * `force=True` overrides both guards
  * Statistics block is attached to landing-page test responses
  * required_sample_size produces a reasonable number for typical inputs
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.services import ab_statistics


# ---------------------------------------------------------------------------
# Pure-function tests (no DB)
# ---------------------------------------------------------------------------


def test_z_test_strong_signal_is_significant() -> None:
    """5% vs 10% over 1000 visitors per variant — should be highly significant."""

    stats = ab_statistics.compute_test_statistics(
        variants=[
            {"id": uuid4(), "name": "control", "is_control": True, "visits": 1000, "conversions": 50},
            {"id": uuid4(), "name": "treatment", "is_control": False, "visits": 1000, "conversions": 100},
        ],
    )
    assert stats.p_value is not None
    assert stats.p_value < 0.001
    assert stats.significant is True
    assert stats.underpowered is False
    assert stats.relative_lift is not None
    assert stats.relative_lift > 0.9  # ~100% relative lift
    assert stats.winner_variant_id is not None


def test_z_test_no_signal_is_not_significant() -> None:
    stats = ab_statistics.compute_test_statistics(
        variants=[
            {"id": uuid4(), "name": "control", "is_control": True, "visits": 1000, "conversions": 50},
            {"id": uuid4(), "name": "treatment", "is_control": False, "visits": 1000, "conversions": 52},
        ],
    )
    assert stats.p_value is not None
    assert stats.p_value > 0.5
    assert stats.significant is False
    assert stats.winner_variant_id is None


def test_underpowered_when_below_threshold() -> None:
    """Tiny samples can't be significant even if rates differ — must be flagged."""

    stats = ab_statistics.compute_test_statistics(
        variants=[
            {"id": uuid4(), "name": "control", "is_control": True, "visits": 20, "conversions": 1},
            {"id": uuid4(), "name": "treatment", "is_control": False, "visits": 20, "conversions": 5},
        ],
        min_sample_per_variant=100,
    )
    assert stats.underpowered is True
    assert stats.significant is False  # underpowered overrides p-value
    assert stats.winner_variant_id is None


def test_confidence_intervals_contain_observed_rate() -> None:
    stats = ab_statistics.compute_test_statistics(
        variants=[
            {"id": uuid4(), "name": "control", "is_control": True, "visits": 500, "conversions": 50},
            {"id": uuid4(), "name": "treatment", "is_control": False, "visits": 500, "conversions": 70},
        ],
    )
    for vs in stats.variants:
        assert vs.ci_low <= vs.conversion_rate <= vs.ci_high
        assert 0.0 <= vs.ci_low <= 1.0
        assert 0.0 <= vs.ci_high <= 1.0


def test_required_sample_size_for_typical_inputs() -> None:
    # Detecting a 20% relative lift on a 5% baseline — should require
    # several thousand visitors per variant. We just sanity-check the
    # output is in a reasonable range, not the exact value.
    n = ab_statistics.required_sample_size(
        baseline_rate=0.05, minimum_detectable_effect=0.20
    )
    assert 4_000 <= n <= 30_000


# ---------------------------------------------------------------------------
# Integration: declare-winner guard
# ---------------------------------------------------------------------------


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


def _seed_landing_test_with_metrics(
    client: TestClient, *, ws_id, control_visits, control_conv, treatment_visits, treatment_conv
) -> tuple[str, str, str]:
    """Create + launch a landing-page test, then drive the public exposure
    + conversion endpoints to populate real metrics. Returns
    (test_id, control_variant_id, treatment_variant_id)."""

    create = client.post(
        f"/api/v1/workspaces/{ws_id}/ab-tests",
        json={
            "name": "T",
            "target": "landing_page",
            "objective": "conversion_rate",
            "variants": [
                {
                    "name": "control",
                    "is_control": True,
                    "traffic_share": 0.5,
                    "payload": {"url": "https://example.com/a"},
                },
                {
                    "name": "treatment",
                    "is_control": False,
                    "traffic_share": 0.5,
                    "payload": {"url": "https://example.com/b"},
                },
            ],
        },
    )
    assert create.status_code == 200, create.text
    body = create.json()
    test_id = body["id"]
    variants_by_name = {v["name"]: v["id"] for v in body["variants"]}
    control_id = variants_by_name["control"]
    treatment_id = variants_by_name["treatment"]

    launch = client.post(f"/api/v1/workspaces/{ws_id}/ab-tests/{test_id}/launch")
    assert launch.status_code == 200, launch.text

    # The public traffic-split endpoint sticky-assigns visitors. To pin known
    # counts per variant we hit the underlying service directly via the API
    # but that requires the splitter to actually deliver visitors to specific
    # variants. Easiest: insert exposure + conversion rows directly through
    # the DB session. We import here so the fixture-bound session is the one
    # used.
    from datetime import datetime, timezone
    from uuid import UUID as _UUID

    from app.models.ab_test_event import AbTestConversion, AbTestExposure
    from app.db.session import SessionLocal as _SessionLocal

    with _SessionLocal() as db:
        for i in range(control_visits):
            db.add(AbTestExposure(
                workspace_id=ws_id if isinstance(ws_id, _UUID) else _UUID(ws_id),
                ab_test_id=_UUID(test_id),
                ab_test_variant_id=_UUID(control_id),
                visitor_id=f"c-{i}",
            ))
        for i in range(treatment_visits):
            db.add(AbTestExposure(
                workspace_id=ws_id if isinstance(ws_id, _UUID) else _UUID(ws_id),
                ab_test_id=_UUID(test_id),
                ab_test_variant_id=_UUID(treatment_id),
                visitor_id=f"t-{i}",
            ))
        for i in range(control_conv):
            db.add(AbTestConversion(
                workspace_id=ws_id if isinstance(ws_id, _UUID) else _UUID(ws_id),
                ab_test_id=_UUID(test_id),
                ab_test_variant_id=_UUID(control_id),
                visitor_id=f"c-{i}",
                occurred_at=datetime.now(timezone.utc),
            ))
        for i in range(treatment_conv):
            db.add(AbTestConversion(
                workspace_id=ws_id if isinstance(ws_id, _UUID) else _UUID(ws_id),
                ab_test_id=_UUID(test_id),
                ab_test_variant_id=_UUID(treatment_id),
                visitor_id=f"t-{i}",
                occurred_at=datetime.now(timezone.utc),
            ))
        db.commit()

    return test_id, control_id, treatment_id


def test_get_test_attaches_statistics_block(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    test_id, control_id, treatment_id = _seed_landing_test_with_metrics(
        client, ws_id=ws.id, control_visits=500, control_conv=25,
        treatment_visits=500, treatment_conv=60,
    )

    resp = client.get(f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    stats = body.get("statistics")
    assert stats is not None
    assert stats["p_value"] is not None
    assert stats["p_value"] < 0.001
    assert stats["significant"] is True
    assert stats["underpowered"] is False
    assert stats["min_sample_per_variant"] == ab_statistics.DEFAULT_MIN_SAMPLE_PER_VARIANT
    assert stats["suggested_winner_variant_id"] == treatment_id


def test_declare_winner_refuses_when_underpowered(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    test_id, _, treatment_id = _seed_landing_test_with_metrics(
        client, ws_id=ws.id, control_visits=20, control_conv=2,
        treatment_visits=20, treatment_conv=4,
    )

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/declare-winner",
        json={"variant_id": treatment_id},
    )
    assert resp.status_code == 409
    assert "underpowered" in resp.json()["error"]["message"].lower()


def test_declare_winner_refuses_when_not_significant(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    test_id, _, treatment_id = _seed_landing_test_with_metrics(
        client, ws_id=ws.id, control_visits=500, control_conv=50,
        treatment_visits=500, treatment_conv=52,
    )

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/declare-winner",
        json={"variant_id": treatment_id},
    )
    assert resp.status_code == 409
    assert "significant" in resp.json()["error"]["message"].lower()


def test_force_overrides_underpowered_guard(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    test_id, _, treatment_id = _seed_landing_test_with_metrics(
        client, ws_id=ws.id, control_visits=10, control_conv=1,
        treatment_visits=10, treatment_conv=3,
    )

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/declare-winner",
        json={"variant_id": treatment_id, "force": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["winner_variant_id"] == treatment_id


def test_declare_winner_succeeds_when_significant_and_powered(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    test_id, _, treatment_id = _seed_landing_test_with_metrics(
        client, ws_id=ws.id, control_visits=1000, control_conv=50,
        treatment_visits=1000, treatment_conv=100,
    )

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/ab-tests/{test_id}/declare-winner",
        json={"variant_id": treatment_id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "completed"
    assert resp.json()["winner_variant_id"] == treatment_id
