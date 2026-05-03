from fastapi.testclient import TestClient


def _signup_and_workspace(client: TestClient, email: str = "alice@example.com") -> tuple[str, str]:
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "Alice"},
    )
    token = register.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})

    workspace = client.post("/api/v1/workspaces", json={"name": "Acme Marketing"}).json()
    return token, workspace["id"]


def test_get_onboarding_creates_empty_profile(client: TestClient) -> None:
    _, workspace_id = _signup_and_workspace(client)
    response = client.get(f"/api/v1/workspaces/{workspace_id}/onboarding")
    assert response.status_code == 200
    body = response.json()
    assert body["business_name"] is None
    assert body["step_completed"] == 0
    assert body["completed_at"] is None


def test_post_onboarding_updates_partial(client: TestClient) -> None:
    _, workspace_id = _signup_and_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/onboarding",
        json={
            "business_name": "Acme",
            "website_url": "https://acme.example",
            "industry": "B2B SaaS",
            "step_completed": 1,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["business_name"] == "Acme"
    assert body["website_url"].startswith("https://acme.example")
    assert body["step_completed"] == 1


def test_generate_growth_dna_requires_required_fields(client: TestClient) -> None:
    _, workspace_id = _signup_and_workspace(client)
    response = client.post(f"/api/v1/workspaces/{workspace_id}/growth-dna/generate")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "onboarding_incomplete"


def test_full_wizard_then_generate_growth_dna(client: TestClient) -> None:
    _, workspace_id = _signup_and_workspace(client)

    # Fill all required + optional inputs
    client.post(
        f"/api/v1/workspaces/{workspace_id}/onboarding",
        json={
            "business_name": "Acme Marketing",
            "website_url": "https://acme.example",
            "industry": "B2B SaaS",
            "target_audience": "Series A founders running performance marketing in-house.",
            "offer_description": (
                "AdVanta is the AI growth command center that turns chaotic ad spend into "
                "measurable pipeline by deploying specialized agents across paid, SEO, and "
                "website conversion."
            ),
            "pain_points": "Ads waste, slow reporting, fragmented tooling.",
            "primary_conversion_goal": "Lead form submissions",
            "monthly_ad_budget_min_usd": 5000,
            "monthly_ad_budget_max_usd": 8000,
            "geographic_target": "United States, Canada",
            "current_ad_platforms": ["google_ads", "meta_ads", "linkedin_ads"],
            "landing_page_urls": ["https://acme.example/pricing"],
            "analytics_status": "configured",
            "competitors": [{"name": "RivalCo", "url": "https://rival.example"}],
            "brand_voice": "Confident, executive, calm.",
            "step_completed": 5,
            "mark_completed": True,
        },
    )

    onboarding = client.get(f"/api/v1/workspaces/{workspace_id}/onboarding").json()
    assert onboarding["completed_at"] is not None
    assert onboarding["step_completed"] == 5

    gen = client.post(f"/api/v1/workspaces/{workspace_id}/growth-dna/generate")
    assert gen.status_code == 201, gen.text
    dna = gen.json()

    assert 0 <= dna["funnel_readiness_score"] <= 100
    assert 0 <= dna["paid_ads_readiness_score"] <= 100
    assert dna["funnel_readiness_score"] >= 70  # all signals filled — should be high
    assert dna["paid_ads_readiness_score"] >= 80
    assert dna["engine_version"] == "deterministic-v1"

    assert dna["business_summary"].startswith("Acme Marketing")
    assert "Series A founders" in dna["icp_summary"]

    # Three platforms → roughly evenly split
    shares = [c["budget_share_pct"] for c in dna["recommended_first_campaigns"]]
    assert sum(shares) == 100
    assert len(dna["recommended_first_campaigns"]) == 3

    # 30-day plan has four weeks
    plan = dna["thirty_day_growth_plan"]
    assert [w["week"] for w in plan] == [1, 2, 3, 4]
    assert all(len(w["deliverables"]) >= 1 for w in plan)

    # GET endpoint returns the same record
    fetched = client.get(f"/api/v1/workspaces/{workspace_id}/growth-dna").json()
    assert fetched["id"] == dna["id"]


def test_get_growth_dna_404_when_not_generated(client: TestClient) -> None:
    _, workspace_id = _signup_and_workspace(client)
    response = client.get(f"/api/v1/workspaces/{workspace_id}/growth-dna")
    assert response.status_code == 404


def test_low_signal_profile_yields_low_funnel_score(client: TestClient) -> None:
    _, workspace_id = _signup_and_workspace(client)
    client.post(
        f"/api/v1/workspaces/{workspace_id}/onboarding",
        json={
            "business_name": "Bare",
            "website_url": "https://bare.example",
            "target_audience": "Small business owners.",
            "offer_description": "We help with marketing.",  # short → no clarity bonus
            "primary_conversion_goal": "Demo bookings",
        },
    )
    gen = client.post(f"/api/v1/workspaces/{workspace_id}/growth-dna/generate")
    assert gen.status_code == 201, gen.text
    dna = gen.json()
    assert dna["funnel_readiness_score"] < 50
    assert any("Offer description is short" in r for r in dna["website_conversion_risks"])
    assert any("Analytics" in r for r in dna["website_conversion_risks"])


def test_onboarding_endpoints_require_membership(client: TestClient) -> None:
    _, workspace_id = _signup_and_workspace(client, "alice@example.com")
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

    response = other.get(f"/api/v1/workspaces/{workspace_id}/onboarding")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "workspace_not_found"
