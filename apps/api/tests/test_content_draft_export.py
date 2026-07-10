"""Download content drafts (social pack) as .txt / .docx.

Exercises the real HTTP endpoints against deterministic drafts (NullClient
pinned by conftest). The .docx image-embed path is unit-tested directly with a
tiny PNG served from the local upload store.
"""

import base64
import io
import zipfile

from fastapi.testclient import TestClient

_DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# A valid 8x8 RGB PNG (python-docx's parser rejects a 1x1). Real image so the
# .docx embed path is genuinely exercised.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAEUlEQVR4nGOw02/BihiGlgQAeaE8QWOCgWUAAAAASUVORK5CYII="
)


def _signup_and_workspace(client: TestClient, email: str = "export@example.com") -> str:
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-9", "full_name": "Ex"},
    )
    client.headers.update({"Authorization": f"Bearer {reg.json()['access_token']}"})
    return client.post("/api/v1/workspaces", json={"name": "Acme"}).json()["id"]


def _make_pack(client: TestClient, ws: str, platforms=("linkedin", "x", "tiktok")) -> list:
    return client.post(
        f"/api/v1/workspaces/{ws}/social/generate",
        json={"topic": "Attribution", "platforms": list(platforms)},
    ).json()["drafts"]


# ---------------------------------------------------------------------------
# Single-draft download
# ---------------------------------------------------------------------------


def test_download_single_txt(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    draft = _make_pack(client, ws, platforms=("linkedin",))[0]

    resp = client.get(
        f"/api/v1/workspaces/{ws}/content-drafts/{draft['id']}/download?format=txt"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "attachment;" in resp.headers["content-disposition"]
    text = resp.content.decode("utf-8")
    assert draft["title"] in text
    for tag in draft["hashtags"]:
        assert tag in text


def test_download_single_docx(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    draft = _make_pack(client, ws, platforms=("linkedin",))[0]

    resp = client.get(
        f"/api/v1/workspaces/{ws}/content-drafts/{draft['id']}/download?format=docx"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(_DOCX_MEDIA)
    # A .docx is a zip; confirm it's a well-formed archive with the doc part.
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert "word/document.xml" in zf.namelist()


def test_download_unsupported_format_is_400(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    draft = _make_pack(client, ws, platforms=("linkedin",))[0]
    resp = client.get(
        f"/api/v1/workspaces/{ws}/content-drafts/{draft['id']}/download?format=pdf"
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Bundle download
# ---------------------------------------------------------------------------


def test_download_bundle_by_ids_txt(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    drafts = _make_pack(client, ws)
    ids = ",".join(d["id"] for d in drafts)

    resp = client.get(
        f"/api/v1/workspaces/{ws}/content-drafts/download?format=txt&ids={ids}"
    )
    assert resp.status_code == 200
    text = resp.content.decode("utf-8")
    # Each platform's section appears in the one file, in request order. Keyed
    # on the platform label (titles can repeat across platforms for one topic).
    assert text.index("LinkedIn") < text.index("X (Twitter)") < text.index("TikTok")
    assert text.count("-" * 60) == len(drafts) - 1  # one separator between sections


def test_download_bundle_docx_is_valid_archive(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    drafts = _make_pack(client, ws)
    ids = ",".join(d["id"] for d in drafts)
    resp = client.get(
        f"/api/v1/workspaces/{ws}/content-drafts/download?format=docx&ids={ids}"
    )
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert "word/document.xml" in zf.namelist()


def test_bundle_download_route_not_shadowed_by_draft_id(client: TestClient) -> None:
    """The literal `/download` path must resolve to the bundle route, not be
    parsed as a draft-id UUID."""
    ws = _signup_and_workspace(client)
    _make_pack(client, ws, platforms=("linkedin",))
    # No ids → falls back to all drafts in the workspace.
    resp = client.get(f"/api/v1/workspaces/{ws}/content-drafts/download?format=txt")
    assert resp.status_code == 200


def test_bundle_empty_is_404(client: TestClient) -> None:
    ws = _signup_and_workspace(client)
    # Random id that isn't in the workspace → nothing to export.
    resp = client.get(
        f"/api/v1/workspaces/{ws}/content-drafts/download"
        "?format=txt&ids=00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404


def test_bundle_ids_are_workspace_scoped(client: TestClient) -> None:
    """A draft id from another workspace is silently excluded, not leaked."""
    ws_a = _signup_and_workspace(client, email="a-export@example.com")
    draft_a = _make_pack(client, ws_a, platforms=("linkedin",))[0]

    ws_b = _signup_and_workspace(client, email="b-export@example.com")
    resp = client.get(
        f"/api/v1/workspaces/{ws_b}/content-drafts/download?format=txt&ids={draft_a['id']}"
    )
    # draft_a belongs to ws_a, so from ws_b's scope there's nothing to export.
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Image embedding (unit)
# ---------------------------------------------------------------------------


def test_docx_embeds_local_image(client: TestClient, db_session) -> None:
    from app.services import content_draft_export_service as export
    from app.services.image_upload_service import save_image_bytes

    ws = _signup_and_workspace(client)
    draft_json = _make_pack(client, ws, platforms=("linkedin",))[0]

    # Host a real image and point the draft at it.
    from uuid import UUID

    from app.models.content_draft import ContentDraft

    saved = save_image_bytes(
        workspace_id=UUID(ws), data=_PNG, content_type="image/png"
    )

    row = db_session.get(ContentDraft, UUID(draft_json["id"]))
    row.image_url = saved["url"]
    db_session.commit()

    data = export.render_docx(row)
    zf = zipfile.ZipFile(io.BytesIO(data))
    # An embedded picture lands under word/media/.
    assert any(n.startswith("word/media/") for n in zf.namelist())


def test_docx_skips_bad_image_url_gracefully(client: TestClient, db_session) -> None:
    """A path-traversal / non-existent local image is skipped, not fatal."""
    from uuid import UUID

    from app.models.content_draft import ContentDraft
    from app.services import content_draft_export_service as export

    ws = _signup_and_workspace(client)
    draft_json = _make_pack(client, ws, platforms=("linkedin",))[0]
    row = db_session.get(ContentDraft, UUID(draft_json["id"]))
    row.image_url = "/uploads/../../etc/passwd"
    db_session.commit()

    # Should still render a valid doc, just without an image.
    data = export.render_docx(row)
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert "word/document.xml" in zf.namelist()
    assert not any(n.startswith("word/media/") for n in zf.namelist())
