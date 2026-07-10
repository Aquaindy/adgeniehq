"""Integration tests for the Social studio.

The suite pins a Null LLM (conftest `_pin_null_llm`), so the SocialContent
agent runs its deterministic fallback here. Assertions target that
deterministic output and the persistence/billing wiring around it — never
LLM-generated prose.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.skills.content.social import (
    SocialContentRequest,
    _enforce_char_limit,
    _hashtag_block_length,
    _slug_tag,
    generate_social_content,
    normalize_hashtags,
)
from app.social.catalog import get_platform, list_platforms


def _signup_and_workspace(client: TestClient, email: str = "social@example.com") -> str:
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "Sol"},
    )
    token = register.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    workspace = client.post("/api/v1/workspaces", json={"name": "Acme"}).json()
    return workspace["id"]


def _seed_workspace(db: Session, *, email: str, role: Role) -> tuple[User, Workspace]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
    db.add(user)
    db.flush()
    ws = Workspace(name="Acme", slug=f"acme-{email.split('@')[0]}")
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
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-9"},
    )
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_platform_catalog_lists_posts_and_video(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    resp = client.get(f"/api/v1/workspaces/{ws}/social/platforms")
    assert resp.status_code == 200
    body = resp.json()

    slugs = {p["slug"] for p in body}
    assert {"facebook", "x", "instagram", "pinterest", "linkedin"}.issubset(slugs)
    assert {"tiktok", "instagram_reels", "youtube_shorts"}.issubset(slugs)

    by_slug = {p["slug"]: p for p in body}
    assert by_slug["x"]["hard_char_limit"] == 280
    assert by_slug["x"]["draft_type"] == "social_post"
    assert by_slug["tiktok"]["draft_type"] == "short_video_script"
    assert by_slug["tiktok"]["aspect_ratio"] == "9:16"
    assert by_slug["tiktok"]["duration_max_seconds"] == 60


def test_platform_catalog_format_filter(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    videos = client.get(
        f"/api/v1/workspaces/{ws}/social/platforms?format=video_script"
    ).json()
    assert {p["slug"] for p in videos} == {"tiktok", "instagram_reels", "youtube_shorts"}
    assert all(p["format"] == "video_script" for p in videos)

    posts = client.get(f"/api/v1/workspaces/{ws}/social/platforms?format=post").json()
    assert all(p["format"] == "post" for p in posts)
    assert "linkedin" in {p["slug"] for p in posts}


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def test_generate_pack_creates_one_draft_per_platform(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    resp = client.post(
        f"/api/v1/workspaces/{ws}/social/generate",
        json={
            "topic": "First-touch attribution misleads B2B teams",
            "platforms": ["linkedin", "x", "tiktok"],
            "keywords": ["attribution", "b2b marketing"],
            "call_to_action": "Follow for weekly teardowns",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["topic"] == "First-touch attribution misleads B2B teams"

    drafts = body["drafts"]
    assert len(drafts) == 3
    assert {d["platform"] for d in drafts} == {"linkedin", "x", "tiktok"}

    by_platform = {d["platform"]: d for d in drafts}
    assert by_platform["linkedin"]["type"] == "social_post"
    assert by_platform["x"]["type"] == "social_post"
    assert by_platform["tiktok"]["type"] == "short_video_script"

    for draft in drafts:
        # Never auto-published, and always traceable to the run that made it.
        assert draft["status"] == "draft"
        assert draft["agent_run_id"] is not None
        assert draft["source"] == "agent"
        # NullClient is pinned, so this must be the deterministic path.
        assert draft["model_used"] is None
        assert draft["body"]
        assert draft["hashtags"], f"{draft['platform']} produced no hashtags"
        assert draft["keywords"]


def test_generate_pack_respects_x_character_limit(client: TestClient) -> None:
    """X counts hashtags inside its 280. The stored body plus its hashtag block
    must fit, or the operator can't actually post what we generated."""

    ws = _signup_and_workspace(client)
    drafts = client.post(
        f"/api/v1/workspaces/{ws}/social/generate",
        json={
            "topic": "A" * 400,  # far past the limit on its own
            "platforms": ["x"],
            "keywords": ["attribution"],
        },
    ).json()["drafts"]

    draft = drafts[0]
    hashtag_block = len(" ".join(draft["hashtags"])) + 1 if draft["hashtags"] else 0
    assert len(draft["body"]) + hashtag_block <= 280

    meta = draft["seo_metadata"]
    assert meta["character_limit"] == 280
    assert meta["composed_character_count"] == len(draft["body"]) + hashtag_block
    assert meta["composed_character_count"] <= 280


def test_generate_pack_video_draft_carries_structured_script(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    drafts = client.post(
        f"/api/v1/workspaces/{ws}/social/generate",
        json={"topic": "Why your CPA spiked", "platforms": ["youtube_shorts"]},
    ).json()["drafts"]

    draft = drafts[0]
    assert draft["type"] == "short_video_script"
    script = draft["seo_metadata"]["script"]
    assert script["hook"]
    assert script["cta"]
    assert len(script["beats"]) >= 3
    assert all(beat["narration"] for beat in script["beats"])
    assert script["aspect_ratio"] == "9:16"
    # The rendered body is what a creator shoots from.
    assert "HOOK" in draft["body"]
    assert "CTA:" in draft["body"]


def test_generate_pack_rejects_unknown_platform(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    resp = client.post(
        f"/api/v1/workspaces/{ws}/social/generate",
        json={"topic": "Anything", "platforms": ["myspace"]},
    )
    # A caller error, not a 500 from a failed agent run. This also pins the
    # exception-handler fix: a validator that raises ValueError leaves the
    # exception object in `ctx`, which used to make JSONResponse blow up.
    assert resp.status_code == 422
    assert "myspace" in resp.text
    assert resp.json()["error"]["code"] == "validation_error"


def test_validator_value_errors_serialize_as_422_not_500(client: TestClient) -> None:
    """Regression: `ctx["error"]` holds a raw ValueError, and `input` can hold
    arbitrary objects. Both must be stringified or the 422 handler 500s.

    Uses the onboarding budget validator, which predates the social feature and
    hit this same path."""

    ws = _signup_and_workspace(client)
    resp = client.post(
        f"/api/v1/workspaces/{ws}/onboarding",
        json={"monthly_ad_budget_min_usd": 5000, "monthly_ad_budget_max_usd": 100},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["error"]["code"] == "validation_error"
    assert "monthly_ad_budget_min_usd" in resp.text


# ---------------------------------------------------------------------------
# Generate from a web link
# ---------------------------------------------------------------------------


def _stub_article(monkeypatch, *, title: str, text: str, final_url: str | None = None):
    """Replace the network fetch so tests never hit the wire (and the SSRF
    guard doesn't reject test hosts). Patches the source module, which the
    service imports at call time."""

    from app.skills.website import extract as web_extract

    def _fake(url: str, *, max_chars: int = 8000):
        return web_extract.ExtractedArticle(
            url=url, final_url=final_url or url, title=title, text=text
        )

    monkeypatch.setattr(web_extract, "fetch_and_extract", _fake)


def test_generate_pack_from_source_url_repurposes_content(
    client: TestClient, monkeypatch
) -> None:
    _stub_article(
        monkeypatch,
        title="Cookieless Attribution in 2026",
        text=(
            "Marketers relying on last-click are flying blind as third-party "
            "cookies disappear. Server-side tagging plus modeled conversions "
            "restore the signal. Teams that migrate early see lower CPA."
        ),
    )
    ws = _signup_and_workspace(client)
    body = client.post(
        f"/api/v1/workspaces/{ws}/social/generate",
        json={"source_url": "https://blog.example/attribution", "platforms": ["linkedin", "x"]},
    ).json()

    # Topic was derived from the page title.
    assert body["topic"] == "Cookieless Attribution in 2026"
    drafts = body["drafts"]
    assert len(drafts) == 2
    for draft in drafts:
        assert draft["seo_metadata"]["source_url"] == "https://blog.example/attribution"
        # Deterministic path (NullClient) surfaces the source excerpt.
        assert "last-click" in draft["body"] or "cookies" in draft["body"]


def test_generate_pack_topic_overrides_derived_title(
    client: TestClient, monkeypatch
) -> None:
    """Both topic and source_url supplied → the explicit topic wins as the
    label, while the source still grounds the content."""

    _stub_article(monkeypatch, title="Some Page Title", text="A lengthy article body about server-side tagging and conversions.")
    ws = _signup_and_workspace(client)
    body = client.post(
        f"/api/v1/workspaces/{ws}/social/generate",
        json={
            "topic": "Angle this for CFOs",
            "source_url": "https://blog.example/x",
            "platforms": ["linkedin"],
        },
    ).json()
    assert body["topic"] == "Angle this for CFOs"
    assert body["drafts"][0]["seo_metadata"]["source_url"] == "https://blog.example/x"


def test_generate_pack_requires_topic_or_source(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    resp = client.post(
        f"/api/v1/workspaces/{ws}/social/generate",
        json={"platforms": ["x"]},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_generate_pack_unreachable_source_url_is_400_not_500(
    client: TestClient, monkeypatch
) -> None:
    """A blocked/unreachable URL is the caller's problem, surfaced cleanly —
    not a 500. The SSRF guard raises WebsiteFetchError, which the service maps
    to a content-generation error."""

    from app.skills.website import extract as web_extract
    from app.skills.website.fetch import WebsiteFetchError

    def _boom(url: str, *, max_chars: int = 8000):
        raise WebsiteFetchError("Could not reach host", url=url)

    monkeypatch.setattr(web_extract, "fetch_and_extract", _boom)

    ws = _signup_and_workspace(client)
    resp = client.post(
        f"/api/v1/workspaces/{ws}/social/generate",
        json={"source_url": "https://blocked.example", "platforms": ["x"]},
    )
    assert resp.status_code == 400, resp.text
    assert resp.status_code != 500


def test_generate_pack_dedupes_platforms(client: TestClient) -> None:
    """Duplicates must collapse before billing — one credit, one draft."""

    ws = _signup_and_workspace(client)
    drafts = client.post(
        f"/api/v1/workspaces/{ws}/social/generate",
        json={"topic": "Attribution", "platforms": ["x", "x", "X"]},
    ).json()["drafts"]
    assert len(drafts) == 1
    assert drafts[0]["platform"] == "x"


def test_generate_pack_refused_for_viewer(client: TestClient, db_session: Session) -> None:
    """Viewers can read the catalog but can't spend credits."""

    _user, ws = _seed_workspace(db_session, email="viewer-social@example.com", role=Role.VIEWER)
    _login(client, "viewer-social@example.com")

    # Reading the catalog is fine.
    assert client.get(f"/api/v1/workspaces/{ws.id}/social/platforms").status_code == 200

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/social/generate",
        json={"topic": "Attribution", "platforms": ["x"]},
    )
    assert resp.status_code == 403


def test_social_drafts_appear_in_content_draft_list(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    client.post(
        f"/api/v1/workspaces/{ws}/social/generate",
        json={"topic": "Attribution", "platforms": ["linkedin", "tiktok"]},
    )

    listed = client.get(f"/api/v1/workspaces/{ws}/content-drafts").json()
    assert len(listed) == 2
    assert {d["platform"] for d in listed} == {"linkedin", "tiktok"}

    # The new enum value round-trips through the ?type= filter.
    scripts = client.get(
        f"/api/v1/workspaces/{ws}/content-drafts?type=short_video_script"
    ).json()
    assert len(scripts) == 1
    assert scripts[0]["platform"] == "tiktok"


def test_social_draft_hashtags_are_editable(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    draft = client.post(
        f"/api/v1/workspaces/{ws}/social/generate",
        json={"topic": "Attribution", "platforms": ["linkedin"]},
    ).json()["drafts"][0]

    updated = client.patch(
        f"/api/v1/workspaces/{ws}/content-drafts/{draft['id']}",
        json={"hashtags": ["#b2b", "#growth"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["hashtags"] == ["#b2b", "#growth"]


# ---------------------------------------------------------------------------
# Skill-level units (no DB, no LLM)
# ---------------------------------------------------------------------------


def test_hashtags_dedupe_case_insensitively_and_respect_platform_cap() -> None:
    ig = get_platform("instagram")
    tags = normalize_hashtags(["#Growth", "growth", "b2b marketing", "#SaaS!!"], platform=ig)
    assert tags == ["#Growth", "#b2bmarketing", "#SaaS"]

    x = get_platform("x")
    assert len(normalize_hashtags(["a", "b", "c", "d"], platform=x)) == 2
    assert len(normalize_hashtags(["a", "b"], platform=get_platform("threads"))) == 1

    # A tag derived from a long topic is unusable and would eat X's 280 budget.
    assert normalize_hashtags(["A" * 400, "ok"], platform=x) == ["#ok"]


def test_slug_tag_preserves_acronyms() -> None:
    # str.title() would mangle "CPA" into "Cpa".
    assert _slug_tag("cpa") == "cpa"
    assert _slug_tag("paid ads") == "PaidAds"
    assert _slug_tag("Why your CPA spiked") == "WhyYourCPASpiked"


def test_enforce_char_limit_reserves_room_for_hashtags() -> None:
    x = get_platform("x")
    body = " ".join(["word"] * 200)
    tags = ["#attribution", "#b2b"]
    reserved = _hashtag_block_length(tags)
    assert reserved == len(" ".join(tags)) + 1

    trimmed = _enforce_char_limit(body, platform=x, reserved=reserved)
    assert len(trimmed) + reserved <= 280
    # Trims on a word boundary rather than mid-token.
    assert not trimmed.endswith("wor")

    assert _hashtag_block_length([]) == 0
    # Video platforms have no ceiling; the body passes through untouched.
    assert _enforce_char_limit(body, platform=get_platform("tiktok")) == body


def test_deterministic_fallback_is_grammatical_with_default_audience() -> None:
    payload = generate_social_content(
        request=SocialContentRequest(
            platform=get_platform("youtube_shorts"), topic="CPA spikes"
        ),
        profile=None,
    )
    assert payload.source == "deterministic"
    assert payload.model_used is None
    hook = payload.script["hook"]
    assert "most your" not in hook
    assert "your audience keep" not in hook


def test_every_catalog_platform_generates_a_draft() -> None:
    """Guards the parametric generator: adding a platform to the catalog must
    not require touching the skill."""

    for platform in list_platforms():
        payload = generate_social_content(
            request=SocialContentRequest(platform=platform, topic="Attribution"),
            profile=None,
        )
        assert payload.body, f"{platform.slug} produced an empty body"
        assert payload.title
        if platform.is_video:
            assert payload.script is not None
        else:
            assert payload.script is None
            if platform.hard_char_limit:
                composed = len(payload.body) + _hashtag_block_length(payload.hashtags)
                assert composed <= platform.hard_char_limit


# ---------------------------------------------------------------------------
# Article extraction (pure, fetch mocked)
# ---------------------------------------------------------------------------


def test_fetch_and_extract_pulls_title_and_strips_noise(monkeypatch) -> None:
    from app.skills.website import extract as web_extract
    from app.skills.website.fetch import FetchedPage

    html = """
    <html><head><title>Fallback Title</title></head>
    <body>
      <nav>Home About</nav>
      <script>var x = 'tracking junk';</script>
      <style>.a{color:red}</style>
      <article>
        <h1>The Real Headline</h1>
        <p>First substantive paragraph about server-side attribution and CPA.</p>
        <p>Second paragraph with more detail.</p>
      </article>
    </body></html>
    """
    monkeypatch.setattr(
        web_extract,
        "fetch_html",
        lambda url: FetchedPage(
            url=url, final_url=url, status_code=200, content_type="text/html", html=html
        ),
    )

    art = web_extract.fetch_and_extract("https://ex.example/post")
    assert art.title == "The Real Headline"  # H1 wins over <title>
    assert "tracking junk" not in art.text  # <script> stripped
    assert "color:red" not in art.text  # <style> stripped
    assert "server-side attribution" in art.text


def test_fetch_and_extract_empty_page_raises(monkeypatch) -> None:
    from app.skills.website import extract as web_extract
    from app.skills.website.extract import ArticleExtractionError
    from app.skills.website.fetch import FetchedPage

    monkeypatch.setattr(
        web_extract,
        "fetch_html",
        lambda url: FetchedPage(
            url=url, final_url=url, status_code=200, content_type="text/html",
            html="<html><body><script>x=1</script></body></html>",
        ),
    )
    import pytest

    with pytest.raises(ArticleExtractionError):
        web_extract.fetch_and_extract("https://ex.example/empty")


def test_source_lead_skips_nav_crumbs() -> None:
    from app.skills.content.social import _source_lead

    text = "Home\nMenu\n\nThis is the first genuinely substantive paragraph of the piece."
    lead = _source_lead(text, max_chars=600)
    assert lead.startswith("This is the first genuinely substantive")
    assert "Home" not in lead
