"""Crawl-based prospect discovery + bulk import.

Pins:
  * Discovery extracts external links from a competitor crawl, dedupes
    against existing prospects, and surfaces a relevance score
  * Discovery is idempotent — running twice doesn't duplicate
  * Bulk import accepts a list and reports per-row skipping
  * Workspace isolation
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.skills.website.fetch import FetchedPage


def _seed_workspace(
    db: Session, *, email: str, role: Role = Role.OWNER
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
            role=role,
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


def _make_page(url: str, html: str) -> FetchedPage:
    return FetchedPage(
        url=url,
        final_url=url,
        status_code=200,
        content_type="text/html",
        html=html,
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_discovery_extracts_external_links_with_relevance_score(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")

    pages = {
        "https://competitor.test/": _make_page(
            "https://competitor.test/",
            """<html><body>
            <a href="/about">About</a>
            <a href="https://news.example.com/article-1">A great article</a>
            <a href="https://news.example.com/article-2">Another link</a>
            <a href="https://partner.test/whitepaper">Partner whitepaper</a>
            </body></html>""",
        ),
        "https://competitor.test/about": _make_page(
            "https://competitor.test/about",
            """<html><body>
            <a href="https://news.example.com/article-3">Yet another</a>
            <a href="https://twitter.com/competitor">Follow us</a>
            </body></html>""",
        ),
    }

    def fake_fetch(url: str) -> FetchedPage:
        if url in pages:
            return pages[url]
        # Treat unknown URLs as 404 → discovery skill catches WebsiteFetchError.
        from app.skills.website.fetch import WebsiteFetchError

        raise WebsiteFetchError("not seeded", url=url)

    with patch(
        "app.skills.outreach.prospect_discovery.fetch_html",
        side_effect=fake_fetch,
    ):
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/backlink-prospects/discover",
            json={"competitor_url": "https://competitor.test/", "max_pages": 5},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["competitor_url"] == "https://competitor.test/"
    assert body["prospects_added"] >= 2  # news.example.com + partner.test
    assert body["prospects_skipped_duplicate"] == 0

    domains = {p["domain"] for p in body["prospects"]}
    # Twitter is on the skip list — must not surface as a prospect.
    assert "twitter.com" not in domains
    # Internal links are skipped.
    assert "competitor.test" not in domains
    # External links survive.
    assert "example.com" in domains  # news.example.com → registrable example.com
    assert "partner.test" in domains

    # Relevance score is populated and within bounds.
    for p in body["prospects"]:
        assert 0 <= p["relevance_score"] <= 100
    # The most-mentioned domain gets the highest score.
    by_domain = {p["domain"]: p for p in body["prospects"]}
    assert by_domain["example.com"]["relevance_score"] >= by_domain["partner.test"]["relevance_score"]


def test_discovery_is_idempotent(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")

    page = _make_page(
        "https://competitor.test/",
        '<html><a href="https://partner.test/">P</a></html>',
    )

    def fake_fetch(url: str) -> FetchedPage:
        return page

    with patch(
        "app.skills.outreach.prospect_discovery.fetch_html",
        side_effect=fake_fetch,
    ):
        first = client.post(
            f"/api/v1/workspaces/{ws.id}/backlink-prospects/discover",
            json={"competitor_url": "https://competitor.test/"},
        )
        second = client.post(
            f"/api/v1/workspaces/{ws.id}/backlink-prospects/discover",
            json={"competitor_url": "https://competitor.test/"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["prospects_added"] >= 1
    assert second.json()["prospects_added"] == 0
    assert second.json()["prospects_skipped_duplicate"] >= 1


def test_discovery_rejects_invalid_url(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects/discover",
        json={"competitor_url": "not a url"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_prospect"


def test_discovery_workspace_isolation(
    client: TestClient, db_session: Session
) -> None:
    _, ws_a = _seed_workspace(db_session, email="alice@example.com")
    _, ws_b = _seed_workspace(db_session, email="bob@example.com")

    page = _make_page(
        "https://x.test/",
        '<html><a href="https://shared-target.test/">Shared</a></html>',
    )
    with patch(
        "app.skills.outreach.prospect_discovery.fetch_html",
        return_value=page,
    ):
        _login(client, "alice@example.com")
        client.post(
            f"/api/v1/workspaces/{ws_a.id}/backlink-prospects/discover",
            json={"competitor_url": "https://x.test/"},
        )
        _login(client, "bob@example.com")
        bob_resp = client.post(
            f"/api/v1/workspaces/{ws_b.id}/backlink-prospects/discover",
            json={"competitor_url": "https://x.test/"},
        )

    # Bob's workspace had no pre-existing rows, so discovery still adds the
    # shared target — the rows are workspace-scoped.
    assert bob_resp.json()["prospects_added"] >= 1


# ---------------------------------------------------------------------------
# Bulk import
# ---------------------------------------------------------------------------


def test_bulk_import_creates_rows_and_reports_skipped(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com")
    _login(client, "alice@example.com")

    # Pre-create one so we can confirm dup detection.
    client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects",
        json={"domain": "preexisting.com"},
    )

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects/bulk",
        json={
            "items": [
                {"domain": "alpha.com", "contact_email": "EDITOR@alpha.com"},
                {"domain": "beta.org", "notes": "from CSV"},
                {"domain": "preexisting.com"},  # dup
                {"domain": "not a domain"},  # invalid
                {"domain": "alpha.com"},  # dup within batch
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    added_domains = {p["domain"] for p in body["added"]}
    assert added_domains == {"alpha.com", "beta.org"}
    assert "preexisting.com" in body["skipped_duplicate"]
    # Within-batch dup: also marked as a duplicate after first add.
    assert body["skipped_duplicate"].count("alpha.com") >= 1
    assert len(body["skipped_invalid"]) == 1
    assert "not a domain" in body["skipped_invalid"][0]["error"] or "invalid" in body["skipped_invalid"][0]["error"]
    # Email lowercased on add.
    alpha = next(p for p in body["added"] if p["domain"] == "alpha.com")
    assert alpha["contact_email"] == "editor@alpha.com"


def test_bulk_import_requires_marketer_or_higher(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(
        db_session, email="alice@example.com", role=Role.VIEWER
    )
    _login(client, "alice@example.com")
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/backlink-prospects/bulk",
        json={"items": [{"domain": "alpha.com"}]},
    )
    assert resp.status_code == 403
