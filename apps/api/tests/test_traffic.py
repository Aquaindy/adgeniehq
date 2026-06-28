"""Integration tests for Traffic Genie (Phases 1, 4, 5, 6).

Exercises the real HTTP endpoints end-to-end against the test DB. The suite pins
a Null LLM (see conftest `_pin_null_llm`), so every agent here runs its
deterministic fallback — assertions target those deterministic outputs, never
LLM-generated prose.
"""

from fastapi.testclient import TestClient


def _signup_and_workspace(client: TestClient, email: str = "traffic@example.com") -> str:
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "Tess"},
    )
    token = register.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    workspace = client.post("/api/v1/workspaces", json={"name": "Acme"}).json()
    return workspace["id"]


# ---------------------------------------------------------------------------
# Catalog + campaigns + assets (Phase 1)
# ---------------------------------------------------------------------------


def test_traffic_catalog_lists_sources_categories_recipes(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    resp = client.get(f"/api/v1/workspaces/{ws}/traffic/catalog")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["categories"]) >= 8
    assert len(body["recipes"]) >= 1
    slugs = {s["slug"] for s in body["sources"]}
    assert {"google_ads", "solo_ads", "seo_content"}.issubset(slugs)


def test_traffic_campaign_create_and_generate_assets(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    created = client.post(
        f"/api/v1/workspaces/{ws}/traffic/campaigns",
        json={"source_slug": "solo_ads", "name": "Lead push", "offer_name": "Free checklist"},
    )
    assert created.status_code == 201
    campaign = created.json()
    assert campaign["status"] == "draft"
    assert campaign["assets"] == []
    cid = campaign["id"]

    # Generate assets (runs the deterministic traffic_assets agent).
    gen = client.post(
        f"/api/v1/workspaces/{ws}/traffic/campaigns/{cid}/generate-assets",
        json={"asset_types": None},
    )
    assert gen.status_code == 201
    assets = gen.json()
    assert len(assets) >= 1
    assert all(a["content"] for a in assets)

    # Assets now appear on the campaign detail.
    detail = client.get(f"/api/v1/workspaces/{ws}/traffic/campaigns/{cid}").json()
    assert len(detail["assets"]) == len(assets)


def test_traffic_campaign_unknown_source_rejected(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    resp = client.post(
        f"/api/v1/workspaces/{ws}/traffic/campaigns",
        json={"source_slug": "not_a_real_source", "name": "X"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unknown_traffic_source"


def test_traffic_recommendation(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    resp = client.post(
        f"/api/v1/workspaces/{ws}/traffic/recommend",
        json={"business_type": "B2B SaaS", "monthly_budget": 2000, "preference": "hybrid", "goal": "leads"},
    )
    assert resp.status_code == 200
    plan = resp.json()
    assert plan["primary_source"] and plan["primary_source"]["slug"]
    assert plan["why"]
    assert len(plan["launch_plan_7_day"]) >= 5


def test_utm_builder_normalizes_and_persists(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    resp = client.post(
        f"/api/v1/workspaces/{ws}/traffic/utm-links",
        json={
            "destination_url": "https://example.com/lp?ref=x",
            "source": "Vendor Name",
            "medium": "Paid Email",
            "campaign": "Lead Magnet Launch",
            "content": "swipe_a",
        },
    )
    assert resp.status_code == 201
    link = resp.json()
    assert link["source"] == "vendor_name"  # normalized
    assert "utm_source=vendor_name" in link["generated_url"]
    assert "utm_campaign=lead_magnet_launch" in link["generated_url"]
    assert "ref=x" in link["generated_url"]  # original query preserved

    listed = client.get(f"/api/v1/workspaces/{ws}/traffic/utm-links").json()
    assert len(listed) == 1


# ---------------------------------------------------------------------------
# Solo Ads (Phase 4)
# ---------------------------------------------------------------------------


def test_solo_ad_order_derives_economics(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    vendor = client.post(
        f"/api/v1/workspaces/{ws}/solo-ads/vendors", json={"name": "TopList Media"}
    ).json()
    order = client.post(
        f"/api/v1/workspaces/{ws}/solo-ads/orders",
        json={
            "vendor_id": vendor["id"],
            "clicks_delivered": 100,
            "cost_cents": 40000,
            "optins": 40,
            "sales": 6,
            "revenue_cents": 120000,
        },
    )
    assert order.status_code == 201
    o = order.json()
    assert o["cpc_cents"] == 400  # 40000 / 100
    assert o["cpl_cents"] == 1000  # 40000 / 40
    assert o["roas"] == 3.0  # 120000 / 40000
    assert o["optin_rate"] == 0.4
    assert o["quality_score"] is None  # not scored yet


def test_solo_ad_quality_guard_and_vendor_rollup(client: TestClient) -> None:
    """Scoring computes a 0-100 quality score, and the vendor's rolling quality
    is the average of its scored orders — without double-counting on re-score
    (regression test for the autoflush identity-map bug)."""
    ws = _signup_and_workspace(client)
    vendor = client.post(
        f"/api/v1/workspaces/{ws}/solo-ads/vendors", json={"name": "VendorX"}
    ).json()
    vid = vendor["id"]

    # Healthy order.
    o1 = client.post(
        f"/api/v1/workspaces/{ws}/solo-ads/orders",
        json={"vendor_id": vid, "clicks_delivered": 100, "unique_clicks": 100,
              "cost_cents": 40000, "optins": 40, "sales": 6, "revenue_cents": 120000},
    ).json()
    # Poor order.
    o2 = client.post(
        f"/api/v1/workspaces/{ws}/solo-ads/orders",
        json={"vendor_id": vid, "clicks_delivered": 500, "unique_clicks": 300,
              "cost_cents": 30000, "optins": 20, "sales": 0, "revenue_cents": 0},
    ).json()

    s1 = client.post(f"/api/v1/workspaces/{ws}/solo-ads/orders/{o1['id']}/quality-score").json()
    s2 = client.post(f"/api/v1/workspaces/{ws}/solo-ads/orders/{o2['id']}/quality-score").json()
    assert isinstance(s1["quality_score"], int) and 0 <= s1["quality_score"] <= 100
    assert s1["quality_score"] > s2["quality_score"]  # healthy beats poor
    assert s1["quality_verdict"] and s2["quality_flags"]  # poor order has flags

    expected = round((s1["quality_score"] + s2["quality_score"]) / 2)

    def vendor_quality() -> int:
        vendors = client.get(f"/api/v1/workspaces/{ws}/solo-ads/vendors").json()
        return next(v for v in vendors if v["id"] == vid)["quality_score"]

    assert vendor_quality() == expected
    # Re-scoring an order must NOT skew the vendor average (no double-count).
    client.post(f"/api/v1/workspaces/{ws}/solo-ads/orders/{o1['id']}/quality-score")
    assert vendor_quality() == expected


def test_solo_ads_playbook(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    resp = client.post(
        f"/api/v1/workspaces/{ws}/solo-ads/playbook",
        json={"offer_name": "Free SEO Checklist", "goal": "build list", "vendor_name": "VendorX"},
    )
    assert resp.status_code == 200
    pb = resp.json()
    assert len(pb["subject_lines"]) == 10
    assert len(pb["email_swipes"]) == 3
    assert len(pb["vendor_screening_checklist"]) == 10
    assert pb["compliance_notes"]


# ---------------------------------------------------------------------------
# Omnisend journeys (Phase 5)
# ---------------------------------------------------------------------------


def test_omnisend_journey_types_and_generate(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    types = client.get(f"/api/v1/workspaces/{ws}/omnisend/journey-types").json()
    assert len(types) == 13
    assert {"welcome", "solo_ads_nurture"}.issubset({t["slug"] for t in types})

    journey = client.post(
        f"/api/v1/workspaces/{ws}/omnisend/journeys/generate",
        json={"journey_type": "solo_ads_nurture", "channel": "email", "offer_name": "Checklist"},
    )
    assert journey.status_code == 200
    bp = journey.json()
    assert len(bp["email_sequence"]) >= 5
    assert bp["flow_name"] and bp["conversion_goal"]
    assert bp["implementation_notes"]


def test_omnisend_campaign_mapping(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    campaign = client.post(
        f"/api/v1/workspaces/{ws}/traffic/campaigns",
        json={"source_slug": "solo_ads", "name": "Q3 List Build"},
    ).json()
    mapping = client.post(
        f"/api/v1/workspaces/{ws}/omnisend/campaign-mapping",
        json={"traffic_campaign_id": campaign["id"], "vendor_name": "VendorX"},
    )
    assert mapping.status_code == 200
    m = mapping.json()
    assert m["segment_name"] == "Solo Ads - VendorX - Q3 List Build"
    assert m["tag"] == "solo_ads_vendorx_q3_list_build"
    assert m["recommended_journey_type"] == "solo_ads_nurture"

    # Mapping is persisted on the campaign.
    detail = client.get(f"/api/v1/workspaces/{ws}/traffic/campaigns/{campaign['id']}").json()
    assert detail["omnisend_segment"] == m["segment_name"]


# ---------------------------------------------------------------------------
# Analytics + optimization (Phase 6)
# ---------------------------------------------------------------------------


def test_traffic_analytics_overview_and_optimize(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    # No data yet.
    empty = client.get(f"/api/v1/workspaces/{ws}/traffic/analytics/overview").json()
    assert empty["has_data"] is False

    # Log a profitable source and a losing source.
    client.post(
        f"/api/v1/workspaces/{ws}/traffic/metrics",
        json={"source_slug": "solo_ads", "clicks": 200, "leads": 70, "sales": 10,
              "cost_cents": 20000, "revenue_cents": 80000},
    )
    client.post(
        f"/api/v1/workspaces/{ws}/traffic/metrics",
        json={"source_slug": "tiktok_ads", "clicks": 500, "leads": 20, "sales": 0,
              "cost_cents": 30000, "revenue_cents": 0},
    )

    overview = client.get(f"/api/v1/workspaces/{ws}/traffic/analytics/overview").json()
    assert overview["has_data"] is True
    assert overview["totals"]["cost_cents"] == 50000
    assert overview["totals"]["revenue_cents"] == 80000
    by_slug = {s["source_slug"]: s for s in overview["sources"]}
    assert by_slug["solo_ads"]["roas"] == 4.0
    assert by_slug["solo_ads"]["profit_cents"] == 60000
    assert by_slug["tiktok_ads"]["profit_cents"] == -30000
    # Profitable source sorts first.
    assert overview["sources"][0]["source_slug"] == "solo_ads"

    # Optimizer surfaces prioritized actions and persists recommendations.
    opt = client.post(f"/api/v1/workspaces/{ws}/traffic/analytics/optimize")
    assert opt.status_code == 200
    actions = opt.json()["next_best_actions"]
    titles = {a["title"] for a in actions}
    assert any("Scale" in t for t in titles)
    assert any("Fix or pause" in t for t in titles)

    recs = client.get(f"/api/v1/workspaces/{ws}/recommendations").json()
    assert any(r["platform"] == "traffic" for r in recs)
