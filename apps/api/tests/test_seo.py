from datetime import date, datetime, timezone
from unittest.mock import patch

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations.google_search_console import (
    GSCKeywordRow,
    GSCSearchAnalyticsResult,
)
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.keyword import Keyword
from app.models.oauth_token import OAuthToken
from app.models.onboarding_profile import OnboardingProfile
from app.models.seo_project import SeoProject
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.encryption import encrypt
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.services.seo_service import opportunity_score
from app.skills.seo import (
    check_canonical,
    check_faq_schema,
    check_open_graph,
    check_structured_data,
    discover_sitemap,
)


# ---------------------------------------------------------------------------
# SEO skill unit tests
# ---------------------------------------------------------------------------


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_canonical_missing_is_medium() -> None:
    finding = check_canonical(_soup("<html></html>"), page_url="https://x.com/")
    assert finding["severity"] == "medium"


def test_canonical_present_and_matching_is_ok() -> None:
    finding = check_canonical(
        _soup('<link rel="canonical" href="https://x.com/">'), page_url="https://x.com/"
    )
    assert finding["severity"] == "ok"


def test_structured_data_missing_is_medium() -> None:
    finding = check_structured_data(_soup("<html></html>"))
    assert finding["severity"] == "medium"
    assert finding["block_count"] == 0


def test_structured_data_recognizes_jsonld_types() -> None:
    html = """
    <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"Organization","name":"Acme"}
    </script>
    """
    finding = check_structured_data(_soup(html))
    assert finding["severity"] == "ok"
    assert "Organization" in finding["types"]


def test_structured_data_invalid_json_flagged() -> None:
    html = '<script type="application/ld+json">{not valid json</script>'
    finding = check_structured_data(_soup(html))
    assert finding["severity"] == "medium"
    assert finding["invalid_block_count"] == 1


def test_open_graph_missing_is_medium() -> None:
    finding = check_open_graph(_soup("<html></html>"))
    assert finding["severity"] == "medium"


def test_open_graph_complete_is_ok() -> None:
    html = """
    <meta property='og:title' content='X'>
    <meta property='og:description' content='Y'>
    <meta property='og:url' content='https://x.com/'>
    <meta property='og:image' content='https://x.com/i.png'>
    """
    finding = check_open_graph(_soup(html))
    assert finding["severity"] == "ok"


def test_faq_schema_recognized() -> None:
    html = """
    <script type='application/ld+json'>
      {"@context":"https://schema.org","@type":"FAQPage","mainEntity":[]}
    </script>
    """
    finding = check_faq_schema(_soup(html))
    assert finding["present"] is True
    assert finding["severity"] == "ok"


def test_faq_schema_absent() -> None:
    finding = check_faq_schema(_soup("<html></html>"))
    assert finding["present"] is False
    assert finding["severity"] == "low"


# ---------------------------------------------------------------------------
# Sitemap discovery (mocked HTTP)
# ---------------------------------------------------------------------------


class _StubResp:
    def __init__(self, status_code: int, *, text: str = "", content: bytes = b""):
        self.status_code = status_code
        self.text = text
        self.content = content


def test_sitemap_discovered_via_robots() -> None:
    robots = "User-agent: *\nAllow: /\nSitemap: https://example.com/sitemap.xml\n"
    sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/</loc></url>
  <url><loc>https://example.com/pricing</loc></url>
</urlset>
"""

    def _fake(url, **_):
        if url.endswith("/robots.txt"):
            return _StubResp(200, text=robots)
        if url.endswith("/sitemap.xml"):
            return _StubResp(200, content=sitemap)
        return _StubResp(404)

    with patch("app.skills.seo.sitemap.httpx.get", side_effect=_fake):
        result = discover_sitemap("https://example.com")

    assert result.discovered_via_robots is True
    assert result.sitemap_url_found == "https://example.com/sitemap.xml"
    assert "https://example.com/" in result.page_urls
    assert "https://example.com/pricing" in result.page_urls


def test_sitemap_falls_back_to_sitemap_xml() -> None:
    sitemap = b"""<?xml version='1.0' encoding='UTF-8'?>
<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
  <url><loc>https://x.com/a</loc></url>
</urlset>
"""

    def _fake(url, **_):
        if url.endswith("/robots.txt"):
            return _StubResp(404)
        if url.endswith("/sitemap.xml"):
            return _StubResp(200, content=sitemap)
        return _StubResp(404)

    with patch("app.skills.seo.sitemap.httpx.get", side_effect=_fake):
        result = discover_sitemap("https://x.com")
    assert result.sitemap_url_found.endswith("/sitemap.xml")
    assert result.page_urls == ["https://x.com/a"]


def test_sitemap_no_sitemap_records_error() -> None:
    def _fake(url, **_):
        return _StubResp(404)

    with patch("app.skills.seo.sitemap.httpx.get", side_effect=_fake):
        result = discover_sitemap("https://nosite.example")
    assert result.sitemap_url_found is None
    assert result.error and "No sitemap" in result.error
    assert result.page_urls == []


# ---------------------------------------------------------------------------
# Opportunity scoring
# ---------------------------------------------------------------------------


def test_opportunity_score_high_for_rank_10_high_impressions_low_ctr() -> None:
    score = opportunity_score(position=10, impressions=2000, ctr=0.005)
    assert score >= 50


def test_opportunity_score_low_for_top_rank_well_optimized() -> None:
    score = opportunity_score(position=1, impressions=2000, ctr=0.30)
    assert score < 25


def test_opportunity_score_zero_for_zero_impressions() -> None:
    assert opportunity_score(position=10, impressions=0, ctr=0.0) == 0


# ---------------------------------------------------------------------------
# Helpers (signup + GSC connection)
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


def _seed_gsc_connection(db: Session, *, workspace: Workspace, user: User) -> ConnectedAccount:
    account = ConnectedAccount(
        workspace_id=workspace.id,
        provider="google_search_console",
        provider_account_id="user-123",
        display_name="Test User",
        status=ConnectionStatus.CONNECTED,
        connected_by=user.id,
        connected_at=datetime.now(timezone.utc),
    )
    db.add(account)
    db.flush()
    db.add(
        OAuthToken(
            connected_account_id=account.id,
            encrypted_access_token=encrypt("ya29.real"),
            encrypted_refresh_token=None,
        )
    )
    db.commit()
    return account


def _login(client: TestClient, email: str) -> None:
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"}
    ).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------------------
# /seo/project + auto-create
# ---------------------------------------------------------------------------


def test_seo_project_auto_created_with_onboarding_url(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    db_session.add(
        OnboardingProfile(workspace_id=workspace.id, website_url="https://acme.example")
    )
    db_session.commit()

    _login(client, "alice@example.com")
    response = client.get(f"/api/v1/workspaces/{workspace.id}/seo/project")
    assert response.status_code == 200
    body = response.json()
    assert body["site_url"] == "https://acme.example"


# ---------------------------------------------------------------------------
# Search Console sync (mocked)
# ---------------------------------------------------------------------------


def test_seo_sync_409_when_gsc_not_connected(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    db_session.add(
        OnboardingProfile(workspace_id=workspace.id, website_url="https://acme.example")
    )
    db_session.commit()
    _login(client, "alice@example.com")
    response = client.post(f"/api/v1/workspaces/{workspace.id}/seo/sync")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "search_console_not_connected"


def test_seo_sync_persists_keywords_with_opportunity_scores(
    client: TestClient, db_session: Session
) -> None:
    user, workspace = _seed_workspace(db_session)
    db_session.add(
        OnboardingProfile(workspace_id=workspace.id, website_url="https://acme.example")
    )
    db_session.commit()
    _seed_gsc_connection(db_session, workspace=workspace, user=user)

    sites = [
        {"siteUrl": "https://acme.example/", "permissionLevel": "siteOwner"},
        {"siteUrl": "https://other.example/", "permissionLevel": "siteUser"},
    ]
    fake_result = GSCSearchAnalyticsResult(
        site_url="https://acme.example/",
        period_start=date(2026, 3, 28),
        period_end=date(2026, 4, 25),
        rows=[
            GSCKeywordRow(
                query="ai growth command center",
                clicks=12,
                impressions=2400,
                ctr=12 / 2400,
                position=8.4,
                top_page="https://acme.example/",
            ),
            GSCKeywordRow(
                query="advanta ai",
                clicks=80,
                impressions=120,
                ctr=80 / 120,
                position=1.2,
                top_page="https://acme.example/",
            ),
        ],
    )

    _login(client, "alice@example.com")
    with patch(
        "app.integrations.google_search_console.GoogleSearchConsoleProvider.list_sites",
        return_value=sites,
    ), patch(
        "app.integrations.google_search_console.GoogleSearchConsoleProvider.fetch_search_analytics",
        return_value=fake_result,
    ):
        response = client.post(f"/api/v1/workspaces/{workspace.id}/seo/sync")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["site_url"] == "https://acme.example/"
    assert body["keywords_upserted"] == 2

    keywords = client.get(f"/api/v1/workspaces/{workspace.id}/seo/keywords").json()
    by_query = {k["query"]: k for k in keywords}

    assert by_query["ai growth command center"]["impressions"] == 2400
    assert by_query["ai growth command center"]["opportunity_score"] >= 50
    # The well-ranked branded query should score lower
    assert (
        by_query["advanta ai"]["opportunity_score"]
        < by_query["ai growth command center"]["opportunity_score"]
    )


# ---------------------------------------------------------------------------
# SEOAuditAgent
# ---------------------------------------------------------------------------


def test_seo_audit_agent_no_site_url_returns_recommendation(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    _login(client, "alice@example.com")
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/agents/run",
        json={"agent_type": "seo_audit"},
    )
    assert response.status_code == 201
    detail = response.json()
    assert detail["output_payload"]["reason"] == "no_website_url"
    types = {r["recommendation_type"] for r in detail["recommendations"]}
    assert "seo.no_site" in types


def test_seo_audit_agent_with_real_site_emits_findings(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    db_session.add(
        OnboardingProfile(workspace_id=workspace.id, website_url="https://acme.example")
    )
    db_session.commit()

    sitemap_xml = b"""<?xml version='1.0' encoding='UTF-8'?>
<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
  <url><loc>https://acme.example/pricing</loc></url>
  <url><loc>https://acme.example/about</loc></url>
</urlset>
"""

    def _sitemap_fake(url, **_):
        if url.endswith("/robots.txt"):
            return _StubResp(404)
        if url.endswith("/sitemap.xml"):
            return _StubResp(200, content=sitemap_xml)
        return _StubResp(404)

    # All crawled pages return the same skeletal HTML — missing meta description,
    # missing canonical, no structured data, and missing OG tags. Title + h1 OK.
    page_html = """
    <!doctype html>
    <html>
      <head><title>Acme — Growth platform that wins</title></head>
      <body><h1>Turn ad chaos into intelligent growth</h1></body>
    </html>
    """

    from app.skills.website.fetch import FetchedPage

    def _page_fetch(url):
        return FetchedPage(
            url=url, final_url=url, status_code=200, content_type="text/html", html=page_html
        )

    _login(client, "alice@example.com")
    with patch("app.skills.seo.sitemap.httpx.get", side_effect=_sitemap_fake), patch(
        "app.agents.seo_audit.fetch_html", side_effect=_page_fetch
    ):
        response = client.post(
            f"/api/v1/workspaces/{workspace.id}/agents/run",
            json={"agent_type": "seo_audit"},
        )
    assert response.status_code == 201
    detail = response.json()
    types = {r["recommendation_type"] for r in detail["recommendations"]}
    # Sitemap is found; we should have site-wide aggregate recs for missing meta/canonical/SD/OG/FAQ
    assert "seo.meta_description_missing_site_wide" in types
    assert "seo.canonical_missing_site_wide" in types
    assert "geo.structured_data_missing" in types
    assert "geo.faq_schema_missing" in types
    # The crawl summary made it back to the SeoProject
    project = db_session.query(SeoProject).filter_by(workspace_id=workspace.id).one()
    assert project.crawl_summary is not None
    assert project.crawl_summary["pages_crawled"] >= 1
    assert project.crawl_summary["meta_missing_count"] >= 1


def test_seo_audit_agent_no_sitemap_recommends_creating_one(
    client: TestClient, db_session: Session
) -> None:
    _, workspace = _seed_workspace(db_session)
    db_session.add(
        OnboardingProfile(workspace_id=workspace.id, website_url="https://acme.example")
    )
    db_session.commit()

    def _fake_404(url, **_):
        return _StubResp(404)

    page_html = """<!doctype html><html><head><title>x</title></head><body><h1>x</h1></body></html>"""
    from app.skills.website.fetch import FetchedPage

    def _page_fetch(url):
        return FetchedPage(
            url=url, final_url=url, status_code=200, content_type="text/html", html=page_html
        )

    _login(client, "alice@example.com")
    with patch("app.skills.seo.sitemap.httpx.get", side_effect=_fake_404), patch(
        "app.agents.seo_audit.fetch_html", side_effect=_page_fetch
    ):
        response = client.post(
            f"/api/v1/workspaces/{workspace.id}/agents/run",
            json={"agent_type": "seo_audit"},
        )
    assert response.status_code == 201
    types = {r["recommendation_type"] for r in response.json()["recommendations"]}
    assert "seo.sitemap_missing" in types
