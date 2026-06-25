from contextlib import contextmanager

from fastapi.testclient import TestClient

import app.llm.client as llm_client
from app.llm.client import LlmClient, LlmCompletion


@contextmanager
def _force_no_llm():
    """Pin the LLM singleton to NullClient so generation stays deterministic."""
    prev = llm_client._INSTANCE
    llm_client._INSTANCE = llm_client.NullClient()
    try:
        yield
    finally:
        llm_client._INSTANCE = prev


@contextmanager
def _force_llm(response_text: str, *, model: str = "fake-model"):
    """Pin a fake LLM that returns `response_text` for the strategy call."""

    class _FakeClient(LlmClient):
        provider_id = "fake"

        def is_configured(self) -> bool:
            return True

        def complete_metered(self, *, db, workspace_id, messages, max_tokens=800,
                              temperature=0.4, purpose=None) -> LlmCompletion:
            return LlmCompletion(text=response_text, model=model)

    prev = llm_client._INSTANCE
    llm_client._INSTANCE = _FakeClient()
    try:
        yield
    finally:
        llm_client._INSTANCE = prev


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

    with _force_no_llm():
        gen = client.post(f"/api/v1/workspaces/{workspace_id}/growth-dna/generate")
    assert gen.status_code == 201, gen.text
    dna = gen.json()

    assert 0 <= dna["funnel_readiness_score"] <= 100
    assert 0 <= dna["paid_ads_readiness_score"] <= 100
    assert dna["funnel_readiness_score"] >= 70  # all signals filled — should be high
    assert dna["paid_ads_readiness_score"] >= 80
    assert dna["engine_version"] == "deterministic-v2"

    assert dna["business_summary"].startswith("Acme Marketing")
    assert "Series A founders" in dna["icp_summary"]

    # Three platforms → roughly evenly split
    shares = [c["budget_share_pct"] for c in dna["recommended_first_campaigns"]]
    assert sum(shares) == 100
    assert len(dna["recommended_first_campaigns"]) == 3
    # Objective is concise per-platform, not the whole pasted goal blob.
    for c in dna["recommended_first_campaigns"]:
        assert len(c["objective"]) <= 121
    objectives = [c["objective"] for c in dna["recommended_first_campaigns"]]
    assert len(set(objectives)) == len(objectives)  # distinct per platform

    # 30-day plan has four weeks
    plan = dna["thirty_day_growth_plan"]
    assert [w["week"] for w in plan] == [1, 2, 3, 4]
    assert all(len(w["deliverables"]) >= 1 for w in plan)

    # Comprehensive marketing strategy is present (deterministic backbone).
    ms = dna["marketing_strategy"]
    assert ms["source"] == "deterministic"
    channel_names = {c["channel"] for c in ms["channels"]}
    assert "Email Marketing & Lifecycle" in channel_names
    assert "Organic Social Media" in channel_names
    assert "Search Engine Optimization (SEO)" in channel_names
    assert {c["category"] for c in ms["channels"]} >= {"paid", "owned", "earned", "foundation"}
    assert sum(p["allocation_pct"] for p in ms["content_pillars"]) == 100
    assert len(ms["platform_strategy"]) >= 3
    assert len(ms["email_strategy"]["flows"]) >= 2

    # GET endpoint returns the same record
    fetched = client.get(f"/api/v1/workspaces/{workspace_id}/growth-dna").json()
    assert fetched["id"] == dna["id"]


def test_fast_client_cross_provider_selection(monkeypatch) -> None:
    from app.core.config import settings
    from app.llm.client import AnthropicClient, OpenAIClient
    from app.services.growth_dna_service import _fast_client_or

    base = AnthropicClient(api_key="ak", model="claude-sonnet-4-6")

    # gpt-* fast model + OpenAI key → OpenAI client pinned to that model,
    # even though the main provider is Anthropic.
    monkeypatch.setattr(settings, "llm_fast_model", "gpt-5.4-mini")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    fast = _fast_client_or(base)
    assert isinstance(fast, OpenAIClient)
    assert fast.model == "gpt-5.4-mini"

    # gpt-* fast model but NO OpenAI key → graceful fallback to the main client.
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert _fast_client_or(base) is base

    # claude-* fast model → Anthropic client with that model.
    monkeypatch.setattr(settings, "llm_fast_model", "claude-haiku-4-5")
    monkeypatch.setattr(settings, "anthropic_api_key", "ak2")
    fast2 = _fast_client_or(base)
    assert isinstance(fast2, AnthropicClient)
    assert fast2.model == "claude-haiku-4-5"

    # Unset → original client unchanged.
    monkeypatch.setattr(settings, "llm_fast_model", "")
    assert _fast_client_or(base) is base


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
    with _force_no_llm():
        gen = client.post(f"/api/v1/workspaces/{workspace_id}/growth-dna/generate")
    assert gen.status_code == 201, gen.text
    dna = gen.json()
    assert dna["funnel_readiness_score"] < 50
    assert any("Offer description is short" in r for r in dna["website_conversion_risks"])
    assert any("Analytics" in r for r in dna["website_conversion_risks"])


def test_growth_dna_uses_llm_when_configured(client: TestClient) -> None:
    import json

    _, workspace_id = _signup_and_workspace(client, "carol@example.com")
    client.post(
        f"/api/v1/workspaces/{workspace_id}/onboarding",
        json={
            "business_name": "Acme Marketing",
            "website_url": "https://acme.example",
            "industry": "B2B SaaS",
            "target_audience": "Series A founders running performance marketing.",
            "offer_description": (
                "AdVanta turns chaotic ad spend into measurable pipeline with specialized AI agents "
                "across paid, SEO, and website conversion."
            ),
            "primary_conversion_goal": "Lead form submissions",
            "current_ad_platforms": ["google_ads", "meta_ads"],
            "step_completed": 5,
            "mark_completed": True,
        },
    )

    ai_payload = json.dumps(
        {
            "overview": {"thesis": "AI tailored thesis.", "priorities": ["Paid Search", "Email Marketing & Lifecycle"]},
            "channels": [
                {"channel": "Paid Search", "summary": "AI summary for paid search.",
                 "tactics": ["AI tactic 1", "AI tactic 2"], "kpis": ["CPA", "ROAS"]}
            ],
            "content_pillars": [
                {"name": "Education", "allocation_pct": 50, "description": "Teach.", "example_hooks": ["Hook A", "Hook B"]},
                {"name": "Proof", "allocation_pct": 50, "description": "Show.", "example_hooks": ["Hook C", "Hook D"]},
            ],
            "platform_strategy": [{"platform": "LinkedIn", "cadence": "3×/week", "focus": "B2B", "best_for": "B2B"}],
            "email_strategy": {
                "summary": "AI email summary.", "newsletter_cadence": "Weekly",
                "flows": [{"name": "Welcome", "trigger": "signup", "goal": "activate"}],
                "kpis": ["Open rate"],
            },
            "content_calendar": [
                {"day": 1, "channel": "LinkedIn", "format": "Post", "pillar": "Education",
                 "hook": "AI generated hook", "caption_direction": "Lead with the outcome."}
            ],
        }
    )

    with _force_llm(ai_payload):
        gen = client.post(f"/api/v1/workspaces/{workspace_id}/growth-dna/generate")
        assert gen.status_code == 201, gen.text
        # The generate response is the deterministic profile, returned instantly;
        # the AI tailoring runs as a background task (which TestClient executes
        # during the request), so the saved record is upgraded by the time we GET.
        assert gen.json()["marketing_strategy"]["enrichment"] == "pending"
        dna = client.get(f"/api/v1/workspaces/{workspace_id}/growth-dna").json()

    ms = dna["marketing_strategy"]
    assert ms["source"] == "ai"
    assert ms["enrichment"] == "enriched"
    assert dna["engine_version"].startswith("ai-")
    assert ms["overview"]["thesis"] == "AI tailored thesis."
    # AI calendar flows through (deterministic baseline is empty).
    assert any(e["hook"] == "AI generated hook" for e in ms["content_calendar"])
    # AI narrative overlays onto the matching baseline channel; full channel set is preserved.
    paid_search = next(c for c in ms["channels"] if c["channel"] == "Paid Search")
    assert paid_search["summary"] == "AI summary for paid search."
    assert len(ms["channels"]) >= 10


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
