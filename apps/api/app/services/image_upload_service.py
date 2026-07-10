"""Local-disk image upload service.

Saves multipart-uploaded images under `apps/api/uploads/blog-images/{workspace}/`
and returns a relative URL the frontend can use directly. The directory is
mounted on FastAPI as `/uploads/...` (see main.py).

We deliberately reject anything that isn't an image we want to render in a
browser (JPEG, PNG, WebP, GIF) to avoid the upload directory becoming a
backdoor for arbitrary files.

For production scale we'd swap the filesystem writer for an S3 / R2 / GCS
backend behind the same `save_image` interface. The route + frontend
contract stay the same.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Final
from uuid import UUID

from fastapi import UploadFile

from app.core.exceptions import AdGenieError


_MAX_BYTES: Final = 5 * 1024 * 1024  # 5 MB

# (mime, [allowed extensions]). Browsers send `image/jpeg` for both .jpg and
# .jpeg; we always normalize to `.jpg`.
_ALLOWED_TYPES: Final = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

# Directory paths: physical disk + the URL prefix the static mount serves on.
_UPLOADS_ROOT: Final = (
    Path(__file__).resolve().parent.parent.parent / "uploads"
)
_BLOG_IMAGES_SUBDIR: Final = "blog-images"
_PUBLIC_URL_PREFIX: Final = "/uploads/blog-images"


class ImageTooLargeError(AdGenieError):
    status_code = 413
    code = "image_too_large"


class UnsupportedImageTypeError(AdGenieError):
    status_code = 415
    code = "unsupported_image_type"


class EmptyUploadError(AdGenieError):
    status_code = 400
    code = "empty_upload"


def uploads_root() -> Path:
    """Exposed so main.py can mount the directory if it exists."""
    return _UPLOADS_ROOT


def save_image(*, workspace_id: UUID, upload: UploadFile) -> dict:
    """Validate + write the upload to disk. Returns `{url, bytes,
    content_type, filename}` for the route layer to surface.

    Caller is responsible for making sure the actor is workspace-authorized
    BEFORE this is invoked — the service has no concept of identity."""

    content_type = (upload.content_type or "").lower()
    if content_type not in _ALLOWED_TYPES:
        raise UnsupportedImageTypeError(
            "Allowed types: " + ", ".join(sorted(_ALLOWED_TYPES.keys()))
        )

    # Read fully so we can both size-check and write atomically. 5 MB cap is
    # small enough that the cost of a buffer is fine; for larger uploads
    # we'd switch to streamed chunked writes.
    data = upload.file.read()
    if not data:
        raise EmptyUploadError("Upload is empty.")
    if len(data) > _MAX_BYTES:
        raise ImageTooLargeError(
            f"Max image size is {_MAX_BYTES // 1024 // 1024} MB; "
            f"got {len(data) // 1024} KB."
        )

    return _write_bytes(workspace_id=workspace_id, data=data, content_type=content_type)


def save_image_bytes(
    *, workspace_id: UUID, data: bytes, content_type: str = "image/png"
) -> dict:
    """Persist already-in-memory image bytes (e.g. an AI-generated image the
    provider returned as base64). Same validation, storage layout, and return
    shape as `save_image`. Caller must have authorized the actor first.

    NOTE: like `save_image`, this writes to the local `uploads/` directory. On
    an ephemeral-filesystem host (Render), these files do not survive a
    redeploy — swap `_write_bytes` for an object-store backend for durability."""

    content_type = (content_type or "").lower()
    if content_type not in _ALLOWED_TYPES:
        raise UnsupportedImageTypeError(
            "Allowed types: " + ", ".join(sorted(_ALLOWED_TYPES.keys()))
        )
    if not data:
        raise EmptyUploadError("Image is empty.")
    if len(data) > _MAX_BYTES:
        raise ImageTooLargeError(
            f"Max image size is {_MAX_BYTES // 1024 // 1024} MB; "
            f"got {len(data) // 1024} KB."
        )
    return _write_bytes(workspace_id=workspace_id, data=data, content_type=content_type)


def _write_bytes(*, workspace_id: UUID, data: bytes, content_type: str) -> dict:
    workspace_dir = _UPLOADS_ROOT / _BLOG_IMAGES_SUBDIR / str(workspace_id)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    ext = _ALLOWED_TYPES[content_type]
    # 16 hex chars of randomness; unguessable, easy to debug.
    filename = f"{secrets.token_hex(8)}.{ext}"
    target = workspace_dir / filename
    target.write_bytes(data)

    return {
        "url": f"{_PUBLIC_URL_PREFIX}/{workspace_id}/{filename}",
        "bytes": len(data),
        "content_type": content_type,
        "filename": filename,
    }
