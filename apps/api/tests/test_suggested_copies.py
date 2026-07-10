from fastapi.testclient import TestClient


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
            "AdGenieHQ is the AI growth command center that turns chaotic ad spend "
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


def _generate_growth_dna(client: TestClient, workspace_id: str) -> None:
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/growth-dna/generate")
    assert resp.status_code == 201, resp.text


def _ready_workspace(client: TestClient, email: str = "alice@example.com") -> str:
    workspace_id = _signup_and_workspace(client, email)
    _complete_onboarding(client, workspace_id)
    _generate_growth_dna(client, workspace_id)
    return workspace_id


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def test_generate_creates_copies_across_sections(client: TestClient) -> None:
    workspace_id = _ready_workspace(client)
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies/generate", json={}
    )
    assert resp.status_code == 201, resp.text
    detail = resp.json()
    assert detail["status"] == "succeeded"
    out = detail["output_payload"]
    assert out["product_name"] == "Acme"
    assert out["source"] == "deterministic"  # NullClient in tests
    assert out["copy_count"] >= 8

    by_type = out["by_type"]
    for expected in ("keywords", "ad_copy", "landing_page", "email", "social_post", "meta_tags"):
        assert expected in by_type, f"missing {expected} in {by_type}"

    # Persisted + listable
    listed = client.get(f"/api/v1/workspaces/{workspace_id}/suggested-copies").json()
    assert len(listed) == out["copy_count"]
    assert all(c["product_name"] == "Acme" for c in listed)
    assert all(c["title"] and c["body"] for c in listed)


def test_generate_respects_explicit_product_name(client: TestClient) -> None:
    workspace_id = _ready_workspace(client)
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies/generate",
        json={"product_name": "Widget Pro"},
    )
    assert resp.status_code == 201
    assert resp.json()["output_payload"]["product_name"] == "Widget Pro"
    listed = client.get(f"/api/v1/workspaces/{workspace_id}/suggested-copies").json()
    assert listed and all(c["product_name"] == "Widget Pro" for c in listed)


def test_generate_skips_without_growth_dna(client: TestClient) -> None:
    workspace_id = _signup_and_workspace(client)
    _complete_onboarding(client, workspace_id)  # but no growth DNA generated
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies/generate", json={}
    )
    assert resp.status_code == 201
    detail = resp.json()
    assert detail["status"] == "succeeded"
    assert detail["output_payload"]["skipped"] is True
    assert detail["output_payload"]["reason"] == "no_growth_dna"
    listed = client.get(f"/api/v1/workspaces/{workspace_id}/suggested-copies").json()
    assert listed == []


def test_list_filters_by_copy_type(client: TestClient) -> None:
    workspace_id = _ready_workspace(client)
    client.post(f"/api/v1/workspaces/{workspace_id}/suggested-copies/generate", json={})
    kw = client.get(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies",
        params={"copy_type": "keywords"},
    ).json()
    assert len(kw) == 1
    assert kw[0]["copy_type"] == "keywords"


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------


def test_download_single_txt_and_docx(client: TestClient) -> None:
    workspace_id = _ready_workspace(client)
    client.post(f"/api/v1/workspaces/{workspace_id}/suggested-copies/generate", json={})
    copy = client.get(f"/api/v1/workspaces/{workspace_id}/suggested-copies").json()[0]
    copy_id = copy["id"]

    txt = client.get(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies/{copy_id}/download",
        params={"format": "txt"},
    )
    assert txt.status_code == 200
    assert txt.headers["content-type"].startswith("text/plain")
    assert "attachment;" in txt.headers["content-disposition"]
    assert copy["title"] in txt.content.decode("utf-8")

    docx = client.get(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies/{copy_id}/download",
        params={"format": "docx"},
    )
    assert docx.status_code == 200
    assert "wordprocessingml" in docx.headers["content-type"]
    # A .docx is a zip archive — verify the magic bytes.
    assert docx.content[:2] == b"PK"


def test_download_bundle_docx(client: TestClient) -> None:
    workspace_id = _ready_workspace(client)
    client.post(f"/api/v1/workspaces/{workspace_id}/suggested-copies/generate", json={})
    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies/download",
        params={"format": "docx"},
    )
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"


def test_download_bundle_empty_is_404(client: TestClient) -> None:
    workspace_id = _ready_workspace(client)
    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies/download",
        params={"format": "docx"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "no_suggested_copies"


def test_download_unsupported_format(client: TestClient) -> None:
    workspace_id = _ready_workspace(client)
    client.post(f"/api/v1/workspaces/{workspace_id}/suggested-copies/generate", json={})
    copy_id = client.get(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies"
    ).json()[0]["id"]
    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies/{copy_id}/download",
        params={"format": "pdf"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unsupported_format"


# ---------------------------------------------------------------------------
# Delete + isolation
# ---------------------------------------------------------------------------


def test_delete_suggested_copy(client: TestClient) -> None:
    workspace_id = _ready_workspace(client)
    client.post(f"/api/v1/workspaces/{workspace_id}/suggested-copies/generate", json={})
    copy_id = client.get(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies"
    ).json()[0]["id"]

    resp = client.delete(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies/{copy_id}"
    )
    assert resp.status_code == 204
    assert (
        client.get(
            f"/api/v1/workspaces/{workspace_id}/suggested-copies/{copy_id}"
        ).status_code
        == 404
    )


def test_suggested_copies_workspace_isolation(client: TestClient) -> None:
    workspace_id = _ready_workspace(client, "alice@example.com")
    client.post(f"/api/v1/workspaces/{workspace_id}/suggested-copies/generate", json={})
    copy_id = client.get(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies"
    ).json()[0]["id"]

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

    # Bob cannot read Alice's copy from his own workspace scope.
    assert (
        other.get(f"/api/v1/workspaces/{bob_ws}/suggested-copies/{copy_id}").status_code
        == 404
    )
    # And Bob is not a member of Alice's workspace at all — the membership
    # guard hides the workspace entirely (404, not 403).
    assert (
        other.get(
            f"/api/v1/workspaces/{workspace_id}/suggested-copies/{copy_id}"
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# Organic social (Growth DNA content strategy)
# ---------------------------------------------------------------------------


def test_organic_social_copies_are_platform_native(client: TestClient) -> None:
    """Each content pillar yields a platform-native artifact, not a generic
    'post hooks' blob. Platforms come from the Growth DNA's own strategy."""

    from app.social.catalog import get_platform

    workspace_id = _ready_workspace(client)  # onboarding is B2B SaaS
    client.post(f"/api/v1/workspaces/{workspace_id}/suggested-copies/generate", json={})

    listed = client.get(f"/api/v1/workspaces/{workspace_id}/suggested-copies").json()
    social = [c for c in listed if c["copy_type"] in ("social_post", "short_video_script")]
    assert social, "no organic social copies generated"

    for copy in social:
        platform = get_platform(copy["platform"])
        assert platform is not None, f"unknown platform {copy['platform']!r}"
        assert copy["hashtags"], f"{copy['platform']} produced no hashtags"
        assert len(copy["hashtags"]) <= platform.hashtag_range[1]
        assert copy["section"].startswith("Organic social —")
        if platform.hard_char_limit:
            composed = len(copy["body"]) + len(" ".join(copy["hashtags"])) + 1
            assert composed <= platform.hard_char_limit, f"{copy['platform']} over limit"

    # A B2B strategy recommends LinkedIn + X, so pillars rotate across them.
    assert {c["platform"] for c in social} == {"linkedin", "x"}


def test_ecommerce_growth_dna_yields_short_video_scripts(client: TestClient) -> None:
    """An ecommerce strategy recommends TikTok/Instagram, so the pillars must
    produce Reels/Shorts scripts — not just text posts."""

    workspace_id = _signup_and_workspace(client, email="shop@example.com")
    _complete_onboarding(
        client,
        workspace_id,
        industry="Ecommerce",
        target_audience="Shoppers who buy skincare online",
        offer_description="An online store selling skincare and beauty products.",
    )
    _generate_growth_dna(client, workspace_id)

    out = client.post(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies/generate", json={}
    ).json()["output_payload"]
    assert "short_video_script" in out["by_type"], out["by_type"]

    listed = client.get(f"/api/v1/workspaces/{workspace_id}/suggested-copies").json()
    scripts = [c for c in listed if c["copy_type"] == "short_video_script"]
    assert scripts
    for script in scripts:
        assert script["platform"] in ("tiktok", "instagram_reels", "youtube_shorts")
        assert "HOOK" in script["body"]
        assert "CTA:" in script["body"]
        assert script["hashtags"]


def test_non_social_copies_have_no_platform_or_hashtags(client: TestClient) -> None:
    workspace_id = _ready_workspace(client)
    client.post(f"/api/v1/workspaces/{workspace_id}/suggested-copies/generate", json={})

    listed = client.get(f"/api/v1/workspaces/{workspace_id}/suggested-copies").json()
    others = [c for c in listed if c["copy_type"] in ("keywords", "email", "meta_tags")]
    assert others
    assert all(c["platform"] is None and c["hashtags"] is None for c in others)


def test_growth_dna_platform_names_map_onto_the_catalog() -> None:
    """Growth DNA names platforms for humans ("X / Twitter"); the catalog keys
    on slugs. Unmapped names (long-form YouTube) are skipped, not guessed at."""

    from types import SimpleNamespace

    from app.skills.content.copy_studio import _recommended_social_platforms

    dna = SimpleNamespace(
        marketing_strategy={
            "platform_strategy": [
                {"platform": "LinkedIn"},
                {"platform": "X / Twitter"},
                {"platform": "YouTube"},  # long-form: no catalog entry
                {"platform": "TikTok"},
            ]
        }
    )
    assert [p.slug for p in _recommended_social_platforms(dna)] == [
        "linkedin",
        "x",
        "tiktok",
    ]

    # Nothing mappable → fall back rather than emit no social content at all.
    empty = SimpleNamespace(marketing_strategy={"platform_strategy": [{"platform": "YouTube"}]})
    assert [p.slug for p in _recommended_social_platforms(empty)] == ["linkedin"]

    assert _recommended_social_platforms(SimpleNamespace(marketing_strategy={}))


def test_txt_export_includes_platform_and_hashtags(client: TestClient) -> None:
    """A post exported without its hashtags is an incomplete post."""

    workspace_id = _ready_workspace(client)
    client.post(f"/api/v1/workspaces/{workspace_id}/suggested-copies/generate", json={})

    listed = client.get(f"/api/v1/workspaces/{workspace_id}/suggested-copies").json()
    social = next(c for c in listed if c["copy_type"] == "social_post")

    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/suggested-copies/{social['id']}/download",
        params={"format": "txt"},
    )
    assert resp.status_code == 200, resp.text
    text = resp.content.decode("utf-8")
    assert f"Platform: {social['platform']}" in text
    for tag in social["hashtags"]:
        assert tag in text
