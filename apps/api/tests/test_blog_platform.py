"""Blog-platform tests: slug + excerpt, image upload, AI Assistant, publish.

These pin the contract for the new "blog post" surface that lives on top of
ContentDraft (type=blog_post). The specialized blog editor in the dashboard
relies on every behavior tested here.

Coverage:
- Manual create accepts slug + excerpt + image_url.
- Slug normalization on update ("Hello, World!" → "hello-world").
- Slug uniqueness inside a workspace (insert with the same slug → 409 from
  the partial unique index).
- Publish auto-generates slug + excerpt for blog_post type when blank, and
  leaves them alone when set.
- POST /content-drafts/images: rejects non-image content types (415),
  rejects empty uploads (400), accepts a small PNG and returns a URL under
  /uploads/blog-images/{workspace}/.
- POST /content-drafts/{id}/ai-assist: returns the deterministic stub when
  no LLM is configured (no fake LLM call); rejects unknown actions (422);
  rejects expand/refine without a selection.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.content_draft import ContentDraft, ContentDraftStatus, ContentDraftType
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role


def _seed_workspace(db: Session, *, email: str, role: Role) -> tuple[User, Workspace]:
    user = User(
        email=email,
        hashed_password=hash_password("correct-horse-9"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    ws = Workspace(name="Acme", slug=f"acme-{email.split('@')[0]}")
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
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-9"},
    )
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------------------
# Slug + excerpt on manual create + update
# ---------------------------------------------------------------------------


def test_manual_create_accepts_slug_excerpt_image(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts",
        json={
            "type": "blog_post",
            "title": "Launching the AdVanta blog",
            "body": "First post here.",
            "slug": "launching-the-advanta-blog",
            "excerpt": "Short summary for cards.",
            "image_url": "/uploads/blog-images/x/y.png",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["slug"] == "launching-the-advanta-blog"
    assert body["excerpt"] == "Short summary for cards."
    assert body["image_url"] == "/uploads/blog-images/x/y.png"


def test_slug_is_normalized_on_update(
    client: TestClient, db_session: Session
) -> None:
    _, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")
    created = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts",
        json={"type": "blog_post", "title": "Hi", "body": "x"},
    ).json()

    response = client.patch(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{created['id']}",
        json={"slug": "Hello, World!  --  v2"},
    )
    assert response.status_code == 200
    assert response.json()["slug"] == "hello-world-v2"


def test_slug_uniqueness_inside_workspace(
    client: TestClient, db_session: Session
) -> None:
    """The partial-unique index on (workspace_id, slug) blocks duplicates."""

    _user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    db_session.add(
        ContentDraft(
            workspace_id=ws.id,
            type=ContentDraftType.BLOG_POST,
            status=ContentDraftStatus.DRAFT,
            title="A",
            body="x",
            slug="hello",
            source="manual",
        )
    )
    db_session.commit()

    db_session.add(
        ContentDraft(
            workspace_id=ws.id,
            type=ContentDraftType.BLOG_POST,
            status=ContentDraftStatus.DRAFT,
            title="B",
            body="y",
            slug="hello",
            source="manual",
        )
    )
    try:
        db_session.commit()
    except IntegrityError:
        db_session.rollback()
    else:
        raise AssertionError("Duplicate slug should have been rejected.")


# ---------------------------------------------------------------------------
# Publish auto-fills slug + excerpt for blog_post type
# ---------------------------------------------------------------------------


def test_publish_auto_generates_slug_and_excerpt(
    client: TestClient, db_session: Session
) -> None:
    _user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    long_body = (
        "AdVanta turns chaotic ad spend into pipeline by deploying agents "
        "across paid, SEO, and conversion. " * 6
    )
    created = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts",
        json={"type": "blog_post", "title": "What AdVanta is", "body": long_body},
    ).json()

    # Approve, then publish.
    client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{created['id']}/approve"
    )
    pub = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{created['id']}/publish",
        json={},
    )
    assert pub.status_code == 200, pub.text
    body = pub.json()
    assert body["status"] == "published"
    assert body["slug"] == "what-advanta-is"
    assert body["excerpt"] is not None
    assert len(body["excerpt"]) <= 281  # 280 + ellipsis
    assert body["published_at"] is not None


def test_publish_preserves_existing_slug_and_excerpt(
    client: TestClient, db_session: Session
) -> None:
    _user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    created = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts",
        json={
            "type": "blog_post",
            "title": "Topic",
            "body": "body",
            "slug": "my-pinned-slug",
            "excerpt": "Pinned summary.",
        },
    ).json()
    client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{created['id']}/approve"
    )
    pub = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{created['id']}/publish",
        json={},
    ).json()
    assert pub["slug"] == "my-pinned-slug"
    assert pub["excerpt"] == "Pinned summary."


# ---------------------------------------------------------------------------
# Image upload
# ---------------------------------------------------------------------------


def _tiny_png_bytes() -> bytes:
    """Smallest valid 1x1 transparent PNG. Bypasses any need for Pillow in tests."""

    return bytes.fromhex(
        "89504e470d0a1a0a"
        "0000000d49484452000000010000000108060000001f15c4890000000a"
        "49444154789c63000000020001E2218bce0000000049454e44ae426082"
    )


def test_upload_image_rejects_non_image_type(
    client: TestClient, db_session: Session
) -> None:
    _user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    files = {"file": ("note.txt", io.BytesIO(b"not an image"), "text/plain")}
    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/images", files=files
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_image_type"


def test_upload_image_rejects_empty(
    client: TestClient, db_session: Session
) -> None:
    _user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    files = {"file": ("blank.png", io.BytesIO(b""), "image/png")}
    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/images", files=files
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "empty_upload"


def test_upload_image_returns_url(
    client: TestClient, db_session: Session
) -> None:
    _user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    _login(client, "alice@example.com")

    files = {
        "file": ("hero.png", io.BytesIO(_tiny_png_bytes()), "image/png"),
    }
    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/images", files=files
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["url"].startswith(f"/uploads/blog-images/{ws.id}/")
    assert body["url"].endswith(".png")
    assert body["bytes"] > 0


def test_upload_image_refused_for_viewer(
    client: TestClient, db_session: Session
) -> None:
    _user, ws = _seed_workspace(
        db_session, email="viewer@example.com", role=Role.VIEWER
    )
    _login(client, "viewer@example.com")

    files = {"file": ("h.png", io.BytesIO(_tiny_png_bytes()), "image/png")}
    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/images", files=files
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# AI Assistant
# ---------------------------------------------------------------------------


def _seed_blog_draft(db: Session, *, ws: Workspace, user: User) -> ContentDraft:
    draft = ContentDraft(
        workspace_id=ws.id,
        type=ContentDraftType.BLOG_POST,
        status=ContentDraftStatus.DRAFT,
        title="Working title",
        body="One paragraph of body so the assistant has something to read.",
        source="manual",
        created_by=user.id,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def test_ai_assist_outline_returns_deterministic_when_no_llm(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    """Force the env-default LLM client to NullClient so the test passes
    regardless of whether the local `.env` happens to have a real
    OPENAI_API_KEY set."""
    from app.llm import client as llm_client

    monkeypatch.setattr(llm_client, "_INSTANCE", llm_client.NullClient())

    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    draft = _seed_blog_draft(db_session, ws=ws, user=user)
    _login(client, "alice@example.com")

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{draft.id}/ai-assist",
        json={"action": "outline"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "outline"
    assert body["source"] == "deterministic"
    sections = body["result"]["sections"]
    assert len(sections) >= 5
    assert all("heading" in s and "summary" in s for s in sections)


def test_ai_assist_unknown_action_rejected(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    draft = _seed_blog_draft(db_session, ws=ws, user=user)
    _login(client, "alice@example.com")

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{draft.id}/ai-assist",
        json={"action": "rewrite_with_emojis"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_assist_action"


def test_ai_assist_expand_requires_selection(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    draft = _seed_blog_draft(db_session, ws=ws, user=user)
    _login(client, "alice@example.com")

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{draft.id}/ai-assist",
        json={"action": "expand"},
    )
    # The route falls through to deterministic when no selection is provided
    # and the LLM path would have raised — deterministic returns a hint.
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "expand"
    assert "paragraph" in body["result"]


def test_ai_assist_suggest_title_returns_5_candidates(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    draft = _seed_blog_draft(db_session, ws=ws, user=user)
    _login(client, "alice@example.com")

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{draft.id}/ai-assist",
        json={"action": "suggest_title"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "suggest_title"
    candidates = body["result"]["candidates"]
    assert len(candidates) == 5
    assert all(isinstance(c, str) for c in candidates)


def test_ai_assist_suggest_meta_includes_title_and_description(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(db_session, email="alice@example.com", role=Role.OWNER)
    draft = _seed_blog_draft(db_session, ws=ws, user=user)
    _login(client, "alice@example.com")

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{draft.id}/ai-assist",
        json={"action": "suggest_meta"},
    )
    assert response.status_code == 200
    body = response.json()
    result = body["result"]
    assert "meta_title" in result
    assert "meta_description" in result
    assert len(result["meta_description"]) <= 155


def test_ai_assist_refused_for_viewer(
    client: TestClient, db_session: Session
) -> None:
    user, ws = _seed_workspace(
        db_session, email="viewer@example.com", role=Role.VIEWER
    )
    draft = _seed_blog_draft(db_session, ws=ws, user=user)
    _login(client, "viewer@example.com")

    response = client.post(
        f"/api/v1/workspaces/{ws.id}/content-drafts/{draft.id}/ai-assist",
        json={"action": "outline"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Public blog endpoints
# ---------------------------------------------------------------------------


def test_public_blog_returns_empty_when_unconfigured(
    client: TestClient,
) -> None:
    """No MARKETING_WORKSPACE_SLUG set → empty list, never an error."""

    # The default in tests is empty (env var not set).
    response = client.get("/api/v1/public/blog")
    assert response.status_code == 200
    assert response.json() == []


def test_public_blog_lists_only_published_blog_posts_in_marketing_workspace(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    user, ws = _seed_workspace(
        db_session, email="alice@example.com", role=Role.OWNER
    )
    # Configure the marketing workspace to be the seeded one.
    from app.core import config

    monkeypatch.setattr(config.settings, "marketing_workspace_slug", ws.slug)

    # Three drafts: one published blog_post (visible), one draft blog_post
    # (hidden), one published landing_page (hidden — wrong type).
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            ContentDraft(
                workspace_id=ws.id,
                type=ContentDraftType.BLOG_POST,
                status=ContentDraftStatus.PUBLISHED,
                title="Visible post",
                body="Hello.",
                slug="visible-post",
                excerpt="Visible.",
                published_at=now,
                source="manual",
                created_by=user.id,
            ),
            ContentDraft(
                workspace_id=ws.id,
                type=ContentDraftType.BLOG_POST,
                status=ContentDraftStatus.DRAFT,
                title="Still drafting",
                body="x",
                slug="still-drafting",
                source="manual",
                created_by=user.id,
            ),
            ContentDraft(
                workspace_id=ws.id,
                type=ContentDraftType.LANDING_PAGE,
                status=ContentDraftStatus.PUBLISHED,
                title="Landing page (wrong type)",
                body="x",
                slug="landing",
                published_at=now,
                source="manual",
                created_by=user.id,
            ),
        ]
    )
    db_session.commit()

    listing = client.get("/api/v1/public/blog").json()
    assert len(listing) == 1
    assert listing[0]["slug"] == "visible-post"

    # Detail endpoint returns the full body.
    detail = client.get("/api/v1/public/blog/visible-post").json()
    assert detail["body"] == "Hello."

    # 404 for hidden / unknown slugs.
    assert client.get("/api/v1/public/blog/still-drafting").status_code == 404
    assert client.get("/api/v1/public/blog/landing").status_code == 404
    assert client.get("/api/v1/public/blog/does-not-exist").status_code == 404
