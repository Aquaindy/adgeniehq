"""Tests for AI creative image generation on content drafts.

Image generation calls OpenAI, so these tests inject a fake OpenAI client via
`image_generation_service._resolve_openai_client` — no network, no key needed.
The 1x1 PNG below is a real, decodable image so the upload service accepts it.
"""

import base64

from fastapi.testclient import TestClient

from app.llm.client import ImageResult

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def _signup_and_workspace(client: TestClient, email: str = "img@example.com") -> str:
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "Im"},
    )
    client.headers.update({"Authorization": f"Bearer {register.json()['access_token']}"})
    return client.post("/api/v1/workspaces", json={"name": "Acme"}).json()["id"]


def _make_social_draft(client: TestClient, ws: str, platform: str = "linkedin") -> dict:
    return client.post(
        f"/api/v1/workspaces/{ws}/social/generate",
        json={"topic": "Attribution", "platforms": [platform]},
    ).json()["drafts"][0]


class _FakeGptImageClient:
    """Stands in for OpenAIClient — returns gpt-image-style bytes."""

    def __init__(self, *, size_seen: list | None = None):
        self._size_seen = size_seen

    def is_configured(self) -> bool:
        return True

    def generate_image(self, *, prompt, size="1024x1024", model=None, quality=None):
        if self._size_seen is not None:
            self._size_seen.append(size)
        return ImageResult(
            url="",
            model="gpt-image-2",
            prompt=prompt,
            image_bytes=_PNG_1X1,
            content_type="image/png",
        )


def test_generate_image_hosts_bytes_and_sets_image_url(
    client: TestClient, monkeypatch
) -> None:
    from app.services import image_generation_service as svc

    monkeypatch.setattr(svc, "_resolve_openai_client", lambda db, ws: _FakeGptImageClient())

    ws = _signup_and_workspace(client)
    draft = _make_social_draft(client, ws)
    assert draft["image_url"] is None

    resp = client.post(
        f"/api/v1/workspaces/{ws}/content-drafts/{draft['id']}/image"
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    # gpt-image bytes were hosted locally, not left as a provider URL.
    assert updated["image_url"].startswith(f"/uploads/blog-images/{ws}/")
    assert updated["image_url"].endswith(".png")
    assert updated["seo_metadata"]["image_model"] == "gpt-image-2"
    assert updated["seo_metadata"]["image_size"] == "1536x1024"  # linkedin → landscape


def test_generate_image_size_matches_platform(client: TestClient, monkeypatch) -> None:
    from app.services import image_generation_service as svc

    seen: list = []
    monkeypatch.setattr(
        svc, "_resolve_openai_client", lambda db, ws: _FakeGptImageClient(size_seen=seen)
    )

    ws = _signup_and_workspace(client)
    for platform, expected in [
        ("instagram", "1024x1024"),
        ("pinterest", "1024x1536"),
        ("tiktok", "1024x1536"),  # video cover → portrait
    ]:
        draft = _make_social_draft(client, ws, platform=platform)
        client.post(f"/api/v1/workspaces/{ws}/content-drafts/{draft['id']}/image")
    assert seen == ["1024x1024", "1024x1536", "1024x1536"]


def test_generate_image_records_usage_and_bills(client: TestClient, monkeypatch) -> None:
    from app.services import image_generation_service as svc

    monkeypatch.setattr(svc, "_resolve_openai_client", lambda db, ws: _FakeGptImageClient())

    ws = _signup_and_workspace(client)
    draft = _make_social_draft(client, ws)
    client.post(f"/api/v1/workspaces/{ws}/content-drafts/{draft['id']}/image")

    # The image_generation usage event was written (the new enum value round-trips).
    from app.models.usage_event import UsageEvent, UsageEventType

    from tests.conftest import TestSessionLocal  # type: ignore

    with TestSessionLocal() as db:
        rows = (
            db.query(UsageEvent)
            .filter(UsageEvent.event_type == UsageEventType.IMAGE_GENERATION)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].metadata_json["model"] == "gpt-image-2"


def test_generate_image_without_openai_key_is_400(client: TestClient, monkeypatch) -> None:
    """No OpenAI credential and no env key → honest 400, not a fake image."""

    from app.services import image_generation_service as svc

    monkeypatch.setattr(svc, "_resolve_openai_client", lambda db, ws: None)

    ws = _signup_and_workspace(client)
    draft = _make_social_draft(client, ws)
    resp = client.post(f"/api/v1/workspaces/{ws}/content-drafts/{draft['id']}/image")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "image_provider_not_configured"


def test_dalle_url_result_is_stored_directly(client: TestClient, monkeypatch) -> None:
    """A URL-returning model (dall-e) is stored as-is (no local hosting)."""

    from app.services import image_generation_service as svc

    class _FakeUrlClient:
        def is_configured(self):
            return True

        def generate_image(self, *, prompt, size="1024x1024", model=None, quality=None):
            return ImageResult(url="https://oai.example/x.png", model="dall-e-3", prompt=prompt)

    monkeypatch.setattr(svc, "_resolve_openai_client", lambda db, ws: _FakeUrlClient())

    ws = _signup_and_workspace(client)
    draft = _make_social_draft(client, ws)
    updated = client.post(
        f"/api/v1/workspaces/{ws}/content-drafts/{draft['id']}/image"
    ).json()
    assert updated["image_url"] == "https://oai.example/x.png"
