from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.skills.website.fetch import FetchedPage


def _signup_and_workspace(client: TestClient, email: str = "alice@example.com") -> str:
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "Alice"},
    )
    token = register.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    workspace = client.post("/api/v1/workspaces", json={"name": "Acme"}).json()
    return workspace["id"]


def _complete_onboarding(client: TestClient, workspace_id: str, **overrides) -> None:
    body = {
        "business_name": "Acme",
        "website_url": "https://acme.example",
        "industry": "B2B SaaS",
        "target_audience": "Series A founders",
        "offer_description": (
            "AdVanta is the AI growth command center that turns chaotic ad spend "
            "into measurable pipeline by deploying specialized agents across paid "
            "media, SEO, and website conversion."
        ),
        "pain_points": "Ads waste, slow reporting.",
        "primary_conversion_goal": "Lead form submissions",
        "monthly_ad_budget_min_usd": 5000,
        "monthly_ad_budget_max_usd": 5000,
        "geographic_target": "US, Canada",
        "current_ad_platforms": ["google_ads", "meta_ads"],
        "landing_page_urls": ["https://acme.example/pricing"],
        "analytics_status": "configured",
        "competitors": [{"name": "RivalCo", "url": "https://rival.example"}],
        "brand_voice": "Confident, executive, calm.",
        "step_completed": 5,
        "mark_completed": True,
    }
    body.update(overrides)
    client.post(f"/api/v1/workspaces/{workspace_id}/onboarding", json=body)


# ---------------------------------------------------------------------------
# Catalog + runs listings
# ---------------------------------------------------------------------------


def test_list_agents_returns_catalog_with_no_runs(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    response = client.get(f"/api/v1/workspaces/{workspace_id}/agents")
    assert response.status_code == 200
    catalog = response.json()
    assert {entry["type"] for entry in catalog} == {
        "website_audit",
        "onboarding_insight",
        "paid_ads",
        "seo_audit",
        "landing_page_audit",
        "content_writer",
        "market_intelligence",
        "icp_persona",
        "creative_strategy",
        "campaign_builder",
        "tracking_attribution",
        "master_orchestrator",
    }
    assert all(entry["last_run"] is None for entry in catalog)


def test_unknown_agent_type_returns_404(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={"agent_type": "made_up_agent"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_agent"


# ---------------------------------------------------------------------------
# OnboardingInsightAgent
# ---------------------------------------------------------------------------


def test_onboarding_insight_skips_when_onboarding_incomplete(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={"agent_type": "onboarding_insight"},
    )
    assert response.status_code == 201
    detail = response.json()
    assert detail["status"] == "succeeded"
    assert detail["output_payload"]["skipped"] is True
    assert detail["output_payload"]["reason"] == "onboarding_incomplete"
    assert detail["recommendations"] == []
    assert detail["tasks"][0]["status"] == "skipped"


def test_onboarding_insight_emits_recommendations_for_gaps(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    _complete_onboarding(
        client,
        workspace_id,
        brand_voice=None,  # gap
        competitors=[],  # gap (empty list)
        analytics_status="partial",  # gap
    )

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={"agent_type": "onboarding_insight"},
    )
    assert response.status_code == 201
    detail = response.json()
    assert detail["status"] == "succeeded"

    types = {r["recommendation_type"] for r in detail["recommendations"]}
    assert "onboarding.gap.brand_voice" in types
    assert "onboarding.gap.competitors" in types
    assert "onboarding.gap.analytics_status" in types

    # Recommendations are persisted on the workspace
    listed = client.get(f"/api/v1/workspaces/{workspace_id}/recommendations").json()
    assert len(listed) == len(detail["recommendations"])
    assert all(r["status"] == "open" for r in listed)


# ---------------------------------------------------------------------------
# WebsiteAuditAgent (mocked HTTP fetch)
# ---------------------------------------------------------------------------


def test_website_audit_skipped_when_no_url(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={"agent_type": "website_audit"},
    )
    assert response.status_code == 201
    detail = response.json()
    assert detail["output_payload"]["reason"] == "no_website_url"
    assert detail["tasks"][0]["status"] == "skipped"


def test_website_audit_runs_skills_against_fetched_html(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    _complete_onboarding(client, workspace_id)

    html = """
    <!doctype html>
    <html>
      <head>
        <title>Acme — Pipeline From Paid, SEO, And Conversion</title>
        <meta name='description' content='AdVanta AI is the growth command center for SaaS marketers, deploying AI skill agents across paid, SEO, and conversion to remove busywork.'>
        <meta name='viewport' content='width=device-width, initial-scale=1'>
      </head>
      <body>
        <h1>Turn ad chaos into intelligent growth</h1>
      </body>
    </html>
    """

    fetched = FetchedPage(
        url="https://acme.example",
        final_url="https://acme.example",
        status_code=200,
        content_type="text/html",
        html=html,
    )

    with patch("app.agents.website_audit.fetch_html", return_value=fetched):
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/agents/run",
            json={"agent_type": "website_audit"},
        )

    assert response.status_code == 201
    detail = response.json()
    assert detail["status"] == "succeeded"
    assert detail["output_payload"]["url"] == "https://acme.example"
    assert detail["output_payload"]["severity_counts"]["high"] == 0
    # 1 fetch task + 5 skill tasks
    assert len(detail["tasks"]) == 6
    skill_names = [t["skill_name"] for t in detail["tasks"]]
    assert "website.title" in skill_names
    assert "website.meta_description" in skill_names

    # Skill outputs persisted
    assert len(detail["skill_outputs"]) == 5
    output_types = {o["output_type"] for o in detail["skill_outputs"]}
    assert output_types == {"website_finding"}

    # No high-severity recommendations for a healthy page (likely zero recs)
    high_recs = [r for r in detail["recommendations"] if r["risk_level"] == "high"]
    assert high_recs == []


def test_website_audit_handles_unreachable_url(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    _complete_onboarding(client, workspace_id)

    def raise_http_error(*args, **kwargs):
        raise httpx.ConnectError("could not connect")

    with patch("app.skills.website.fetch.httpx.get", side_effect=raise_http_error):
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/agents/run",
            json={"agent_type": "website_audit"},
        )

    assert response.status_code == 201
    detail = response.json()
    assert detail["status"] == "succeeded"  # the agent itself succeeded — the fetch task failed
    assert detail["output_payload"]["reason"] == "fetch_failed"
    assert detail["tasks"][0]["status"] == "failed"
    assert any(r["recommendation_type"] == "website_unreachable" for r in detail["recommendations"])


def test_run_detail_404_in_other_workspace(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client, "alice@example.com")
    _complete_onboarding(client, workspace_id)
    detail_resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={"agent_type": "onboarding_insight"},
    ).json()
    run_id = detail_resp["id"]

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

    response = other.get(f"/api/v1/workspaces/{bob_ws}/agents/runs/{run_id}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Market Intelligence + ICP/Persona + Master Orchestrator
# ---------------------------------------------------------------------------


def test_market_intelligence_skips_when_onboarding_incomplete(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={"agent_type": "market_intelligence"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["output_payload"]["skipped"] is True
    assert any(
        r["recommendation_type"] == "market_intel.onboarding_incomplete"
        for r in body["recommendations"]
    )


def test_market_intelligence_emits_competitor_inventory(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    _complete_onboarding(client, workspace_id)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={"agent_type": "market_intelligence"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "succeeded"
    out = body["output_payload"]
    assert out["competitor_count"] == 1
    # Without an LLM key the matrix should be deterministic.
    assert out["matrix_source"] in ("deterministic", "llm")


def test_icp_persona_skips_when_onboarding_incomplete(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={"agent_type": "icp_persona"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["output_payload"]["skipped"] is True


def test_icp_persona_generates_personas(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    _complete_onboarding(client, workspace_id)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={"agent_type": "icp_persona"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["output_payload"]["persona_count"] >= 1


def test_master_orchestrator_delegates_to_subagents(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    _complete_onboarding(client, workspace_id)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={
            "agent_type": "master_orchestrator",
            "input_payload": {"goal": "research"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "succeeded"
    out = body["output_payload"]
    assert out["plan_source"] == "goal:research"
    assert "market_intelligence" in out["plan"]
    assert "icp_persona" in out["plan"]
    assert len(out["sub_runs"]) == 2

    # Each sub-run should be visible in the runs listing.
    runs = client.get(f"/api/v1/workspaces/{workspace_id}/agents/runs").json()
    types = {r["agent_type"] for r in runs}
    assert {"master_orchestrator", "market_intelligence", "icp_persona"}.issubset(types)


# ---------------------------------------------------------------------------
# Creative Strategy + Campaign Builder + Tracking
# ---------------------------------------------------------------------------


def test_creative_strategy_persists_variants(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    _complete_onboarding(client, workspace_id)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={
            "agent_type": "creative_strategy",
            "input_payload": {"creative_type": "search_ad"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    out = body["output_payload"]
    assert out["creative_type"] == "search_ad"
    assert out["variant_count"] >= 1
    assert any(
        r["recommendation_type"] == "creative_strategy.variants_generated"
        for r in body["recommendations"]
    )


def test_campaign_builder_emits_blueprint(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    _complete_onboarding(client, workspace_id)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={
            "agent_type": "campaign_builder",
            "input_payload": {
                "objective": "lead_gen",
                "platform": "google_ads",
                "budget_cents": 200_000,
                "audience_size": "balanced",
            },
        },
    )
    assert response.status_code == 201
    body = response.json()
    out = body["output_payload"]
    assert out["objective"] == "lead_gen"
    assert out["platform"] == "google_ads"
    assert out["ad_group_count"] >= 2

    rec = next(
        r for r in body["recommendations"]
        if r["recommendation_type"] == "campaign_builder.blueprint"
    )
    assert rec["risk_level"] == "high"  # spend gates must be approved
    assert "blueprint" in rec["metadata"]


def test_tracking_attribution_scores_workspace(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    _complete_onboarding(client, workspace_id)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/agents/run",
        json={"agent_type": "tracking_attribution"},
    )
    assert response.status_code == 201
    body = response.json()
    out = body["output_payload"]
    assert "score" in out
    assert 0 <= out["score"] <= 100
    # No connected accounts in a fresh test workspace, so we expect a
    # missing-GA4 recommendation.
    assert any(
        r["recommendation_type"] == "tracking.missing_ga4"
        for r in body["recommendations"]
    )
