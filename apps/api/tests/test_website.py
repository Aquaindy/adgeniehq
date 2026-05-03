from unittest.mock import patch

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.landing_page import LandingPage
from app.models.onboarding_profile import OnboardingProfile
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.skills.conversion import (
    check_above_fold,
    check_copy_clarity,
    check_cta_analysis,
    check_form_friction,
    check_trust_signals,
)
from app.skills.conversion.page_speed import PageSpeedResult


# ---------------------------------------------------------------------------
# Skill unit tests
# ---------------------------------------------------------------------------


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_cta_analysis_clear_primary() -> None:
    finding = check_cta_analysis(
        _soup('<a class="btn" href="#">Get started free</a><button>Talk to sales</button>')
    )
    assert finding["cta_count"] == 2
    assert finding["primary_clarity"] == "clear"
    assert finding["severity"] in ("ok", "low")
    assert finding["score"] >= 60


def test_cta_analysis_vague_primary() -> None:
    finding = check_cta_analysis(
        _soup('<a class="btn" href="#">Learn more</a>')
    )
    assert finding["primary_clarity"] == "vague"
    assert finding["severity"] == "medium"


def test_cta_analysis_no_cta_high_severity() -> None:
    finding = check_cta_analysis(_soup("<p>just text</p>"))
    assert finding["cta_count"] == 0
    assert finding["severity"] == "high"


def test_above_fold_strong_value_prop() -> None:
    html = """
    <h1>Grow pipeline 3x without hiring more reps</h1>
    <p>AdVanta saves marketers 12 hours a week by automating ad ops across Meta and Google.</p>
    """
    finding = check_above_fold(_soup(html))
    assert finding["severity"] == "ok"
    assert finding["benefit_signals"] >= 1
    assert finding["score"] >= 60


def test_above_fold_no_h1_high_severity() -> None:
    finding = check_above_fold(_soup("<div>nothing</div>"))
    assert finding["severity"] == "high"
    assert finding["score"] == 0


def test_trust_signals_zero_is_high() -> None:
    finding = check_trust_signals(_soup("<p>plain page</p>"))
    assert finding["severity"] == "high"


def test_trust_signals_multi_signals_ok() -> None:
    html = """
    <section class='logo-cloud'><img alt='Acme'></section>
    <blockquote>Best growth tool we've used.</blockquote>
    <p>Trusted by 4.7/5 customers on G2.</p>
    """
    finding = check_trust_signals(_soup(html))
    assert finding["severity"] == "ok"
    assert finding["signal_count"] >= 3


def test_form_friction_three_fields_is_ok() -> None:
    html = "<form><input name='email'><input name='name'><textarea name='note'></textarea></form>"
    finding = check_form_friction(_soup(html))
    assert finding["severity"] == "ok"
    assert finding["max_fields"] == 3


def test_form_friction_huge_form_high() -> None:
    fields = "".join(f"<input name='f{i}'>" for i in range(11))
    finding = check_form_friction(_soup(f"<form>{fields}</form>"))
    assert finding["severity"] == "high"
    assert finding["max_fields"] == 11


def test_form_friction_no_forms_is_ok() -> None:
    finding = check_form_friction(_soup("<p>no form here</p>"))
    assert finding["severity"] == "ok"
    assert finding["form_count"] == 0


def test_copy_clarity_short_pages_flagged() -> None:
    finding = check_copy_clarity(_soup("<p>tiny</p>"))
    assert finding["severity"] == "medium"


def test_copy_clarity_brisk_copy_is_ok() -> None:
    paragraph = "AdVanta turns chaotic ad spend into measurable pipeline. " * 20
    finding = check_copy_clarity(_soup(f"<p>{paragraph}</p>"))
    assert finding["word_count"] >= 80
    # Should not flag as medium for sentence length
    assert finding["severity"] in ("ok", "low")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_workspace(db: Session, *, email: str = "alice@example.com") -> tuple[User, Workspace]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
    db.add(user)
    db.flush()
    workspace = Workspace(name="Acme", slug=f"acme-{email.split('@')[0]}")
    db.add(workspace)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id, user_id=user.id, role=Role.OWNER, status=MemberStatus.ACTIVE
        )
    )
    db.commit()
    return user, workspace


def _login(client: TestClient, email: str) -> None:
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"}
    ).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------------------
# CRUD + auto-import
# ---------------------------------------------------------------------------


def test_create_and_list_landing_page(client: TestClient, db_session: Session) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")

    create = client.post(
        f"/api/v1/workspaces/{workspace.id}/landing-pages",
        json={"url": "https://acme.example/pricing", "label": "Pricing"},
    )
    assert create.status_code == 201
    body = create.json()
    assert body["url"].rstrip("/") == "https://acme.example/pricing"
    assert body["source"] == "manual"

    listing = client.get(f"/api/v1/workspaces/{workspace.id}/landing-pages").json()
    assert len(listing) == 1
    assert listing[0]["label"] == "Pricing"


def test_duplicate_landing_page_returns_409(client: TestClient, db_session: Session) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    payload = {"url": "https://acme.example/pricing"}
    client.post(f"/api/v1/workspaces/{workspace.id}/landing-pages", json=payload)
    second = client.post(f"/api/v1/workspaces/{workspace.id}/landing-pages", json=payload)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_landing_page"


def test_import_from_onboarding_creates_rows(client: TestClient, db_session: Session) -> None:
    _, workspace = _seed_workspace(db_session)
    db_session.add(
        OnboardingProfile(
            workspace_id=workspace.id,
            website_url="https://acme.example",
            landing_page_urls=[
                "https://acme.example/pricing",
                "https://acme.example/demo",
            ],
        )
    )
    db_session.commit()

    _login(client, "alice@example.com")
    response = client.post(f"/api/v1/workspaces/{workspace.id}/landing-pages/import")
    assert response.status_code == 201
    assert response.json()["created"] == 2

    listing = client.get(f"/api/v1/workspaces/{workspace.id}/landing-pages").json()
    assert {lp["url"] for lp in listing} == {
        "https://acme.example/pricing",
        "https://acme.example/demo",
    }
    assert all(lp["source"] == "onboarding" for lp in listing)


def test_delete_landing_page(client: TestClient, db_session: Session) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    create = client.post(
        f"/api/v1/workspaces/{workspace.id}/landing-pages",
        json={"url": "https://acme.example/x"},
    ).json()
    response = client.delete(
        f"/api/v1/workspaces/{workspace.id}/landing-pages/{create['id']}"
    )
    assert response.status_code == 204
    assert client.get(f"/api/v1/workspaces/{workspace.id}/landing-pages").json() == []


# ---------------------------------------------------------------------------
# Audit agent end-to-end with mocked fetch + PSI
# ---------------------------------------------------------------------------


HEALTHY_HTML = """
<!doctype html>
<html>
  <head>
    <title>Acme — Grow pipeline 3x</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
  </head>
  <body>
    <h1>Grow pipeline 3x without hiring more reps</h1>
    <p>AdVanta saves marketers 12 hours a week by automating ad ops across Meta and Google.</p>
    <a class="btn primary" href="#">Get started free</a>
    <a class="btn secondary" href="#">Book a demo</a>
    <section class="logo-cloud">
      <img alt="Acme">
      <img alt="Beta">
    </section>
    <blockquote>Best growth tool we've used. Rated 4.7/5 on G2.</blockquote>
    <form>
      <input name="email" type="email">
      <input name="name" type="text">
    </form>
    <p>AdVanta turns chaotic ad spend into measurable pipeline by deploying specialized agents.</p>
  </body>
</html>
"""

WEAK_HTML = """
<!doctype html>
<html>
  <head><title>x</title></head>
  <body>
    <p>welcome</p>
    <a href="#">Learn more</a>
    <form>
      <input><input><input><input><input><input><input><input><input><input>
    </form>
  </body>
</html>
"""


def _patch_psi(score: float | None = 0.92):
    return patch(
        "app.agents.landing_page_audit.fetch_page_speed",
        return_value=PageSpeedResult(
            url="https://acme.example/pricing",
            strategy="mobile",
            performance=score,
            accessibility=0.95,
            best_practices=0.9,
            seo=0.95,
            raw={"lighthouseResult": {"categories": {}}},
        ),
    )


def _patch_fetch(html: str):
    from app.skills.website.fetch import FetchedPage

    page = FetchedPage(
        url="https://acme.example/pricing",
        final_url="https://acme.example/pricing",
        status_code=200,
        content_type="text/html",
        html=html,
    )
    return patch("app.agents.landing_page_audit.fetch_html", return_value=page)


def test_audit_endpoint_runs_agent_and_persists_summary(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    lp = client.post(
        f"/api/v1/workspaces/{workspace.id}/landing-pages",
        json={"url": "https://acme.example/pricing"},
    ).json()

    with _patch_fetch(HEALTHY_HTML), _patch_psi(0.92):
        response = client.post(
            f"/api/v1/workspaces/{workspace.id}/landing-pages/{lp['id']}/audit"
        )
    assert response.status_code == 201
    detail = response.json()
    assert detail["status"] == "succeeded"
    op = detail["output_payload"]
    assert op["scores"]["mobile_ux"] == 100
    assert op["scores"]["page_speed"] == 92
    # Healthy page should score well on conversion composite
    assert op["scores"]["conversion"] >= 60

    fetched = client.get(
        f"/api/v1/workspaces/{workspace.id}/landing-pages/{lp['id']}"
    ).json()
    assert fetched["last_audited_at"] is not None
    assert fetched["last_audit_summary"]["scores"]["conversion"] >= 60


def test_audit_agent_emits_findings_for_weak_page(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    lp = client.post(
        f"/api/v1/workspaces/{workspace.id}/landing-pages",
        json={"url": "https://acme.example/pricing"},
    ).json()

    with _patch_fetch(WEAK_HTML), _patch_psi(0.30):
        response = client.post(
            f"/api/v1/workspaces/{workspace.id}/landing-pages/{lp['id']}/audit"
        )
    detail = response.json()
    types = {r["recommendation_type"] for r in detail["recommendations"]}
    assert any(t.startswith("conversion.above_fold") for t in types)
    assert any(t.startswith("conversion.cta_analysis") for t in types)
    assert any(t.startswith("conversion.form_friction") for t in types)
    assert any(t.startswith("conversion.trust_signals") for t in types)
    assert "conversion.page_speed.high" in types
    assert detail["output_payload"]["scores"]["page_speed"] == 30


def test_audit_when_fetch_fails_emits_unreachable_recommendation(
    client: TestClient, db_session: Session
) -> None:
    from app.skills.website.fetch import WebsiteFetchError

    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    lp = client.post(
        f"/api/v1/workspaces/{workspace.id}/landing-pages",
        json={"url": "https://acme.example/pricing"},
    ).json()

    def raise_fetch(*args, **kwargs):
        raise WebsiteFetchError("boom", url="https://acme.example/pricing")

    with patch("app.agents.landing_page_audit.fetch_html", side_effect=raise_fetch):
        response = client.post(
            f"/api/v1/workspaces/{workspace.id}/landing-pages/{lp['id']}/audit"
        )
    detail = response.json()
    assert detail["status"] == "succeeded"
    assert detail["output_payload"]["reason"] == "fetch_failed"
    types = {r["recommendation_type"] for r in detail["recommendations"]}
    assert "website.unreachable" in types


def test_audit_endpoint_404_for_other_workspace(
    client: TestClient, db_session: Session
) -> None:
    _, workspace_a = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    lp = client.post(
        f"/api/v1/workspaces/{workspace_a.id}/landing-pages",
        json={"url": "https://acme.example/x"},
    ).json()

    other = TestClient(client.app)
    other.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "correct-horse-9"},
    )
    bob_token = other.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "correct-horse-9"},
    ).json()["access_token"]
    other.headers.update({"Authorization": f"Bearer {bob_token}"})
    bob_ws = other.post("/api/v1/workspaces", json={"name": "Bob's"}).json()["id"]

    response = other.post(
        f"/api/v1/workspaces/{bob_ws}/landing-pages/{lp['id']}/audit"
    )
    assert response.status_code == 404
