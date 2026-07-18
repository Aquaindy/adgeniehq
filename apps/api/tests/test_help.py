"""Help / Knowledge-Base API + ElevenLabs narration.

Covers: topic listing/detail, auth requirement, the "unavailable" audio state
when the platform ElevenLabs key is unset, and generate-on-first-play caching
(synthesized once, served from cache after) with the HTTP + storage stubbed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.integrations import elevenlabs


def _login(client: TestClient, email: str = "helpuser@example.com") -> None:
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "Help"},
    )
    client.headers.update({"Authorization": f"Bearer {reg.json()['access_token']}"})


def test_list_and_get_topics(client: TestClient) -> None:
    _login(client)
    listing = client.get("/api/v1/help/topics")
    assert listing.status_code == 200
    topics = listing.json()
    ids = {t["id"] for t in topics}
    assert {"getting-started", "campaigns", "billing"} <= ids

    detail = client.get("/api/v1/help/topics/billing")
    assert detail.status_code == 200
    body = detail.json()
    assert body["title"].startswith("Billing")
    assert "PayPal" in body["body_markdown"]


def test_get_unknown_topic_404(client: TestClient) -> None:
    _login(client)
    resp = client.get("/api/v1/help/topics/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "help_topic_not_found"


def test_help_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/help/topics")
    assert resp.status_code == 401


def test_audio_unavailable_without_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No platform key configured → the Audio tab degrades to "coming soon".
    monkeypatch.setattr(settings, "elevenlabs_api_key", "", raising=False)
    monkeypatch.setattr(settings, "elevenlabs_default_voice_id", "", raising=False)
    _login(client)
    resp = client.get("/api/v1/help/topics/campaigns/audio")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unavailable"


def test_audio_generates_and_caches(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Configure a platform key + voice, and stub the network + storage.
    monkeypatch.setattr(settings, "elevenlabs_api_key", "test-key", raising=False)
    monkeypatch.setattr(settings, "elevenlabs_default_voice_id", "voice-x", raising=False)

    calls = {"synth": 0}

    def _fake_synth(text, *, voice_id=None, model=None):
        calls["synth"] += 1
        return elevenlabs.AudioResult(audio_bytes=b"ID3-fake-mp3", content_type="audio/mpeg")

    monkeypatch.setattr(elevenlabs, "synthesize", _fake_synth)
    monkeypatch.setattr(
        "app.services.object_storage.put_object",
        lambda **kw: "https://cdn.example/help-audio/campaigns.mp3",
    )

    _login(client)

    # First POST kicks off generation; with workers off it runs inline and
    # completes, so the response is already "ready".
    started = client.post("/api/v1/help/topics/campaigns/audio")
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["status"] == "ready"
    assert body["url"] == "https://cdn.example/help-audio/campaigns.mp3"
    assert calls["synth"] == 1

    # A subsequent GET is served from cache — no second synthesis.
    again = client.get("/api/v1/help/topics/campaigns/audio")
    assert again.status_code == 200
    assert again.json()["status"] == "ready"
    assert calls["synth"] == 1

    # And a second POST also reuses the cached asset.
    reposted = client.post("/api/v1/help/topics/campaigns/audio")
    assert reposted.json()["status"] == "ready"
    assert calls["synth"] == 1
