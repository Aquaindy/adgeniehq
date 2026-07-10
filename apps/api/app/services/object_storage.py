"""Pluggable object storage for images.

Two backends behind one `put_object(key, data, content_type) -> public_url`:

  * `R2Backend` — Cloudflare R2 (S3-compatible via boto3). Durable; used
    whenever R2 is fully configured (see `settings.r2_enabled`).
  * `LocalDiskBackend` — writes under `uploads/` and returns a `/uploads/...`
    relative URL served by the FastAPI static mount. Fine for local dev;
    EPHEMERAL on hosts like Render (files vanish on redeploy).

The active backend is chosen once from config and cached. `key` is the full
object path (e.g. `blog-images/<workspace>/<file>.png`); the same key is used
for both the R2 object and the local file, so switching backends doesn't move
existing references — new writes just land in the new place.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.core.exceptions import AdGenieError
from app.core.logging import get_logger

log = get_logger(__name__)

# One year, immutable — filenames are random and unguessable, so an object at a
# given key never changes.
_CACHE_CONTROL = "public, max-age=31536000, immutable"


class ObjectStorageError(AdGenieError):
    status_code = 502
    code = "object_storage_error"


class StorageBackend(Protocol):
    def put(self, *, key: str, data: bytes, content_type: str) -> str: ...


class LocalDiskBackend:
    """Writes to the local uploads dir; returns a relative `/uploads/...` URL."""

    def __init__(self, *, root: Path, url_prefix: str) -> None:
        self._root = root
        self._url_prefix = url_prefix.rstrip("/")

    def put(self, *, key: str, data: bytes, content_type: str) -> str:
        target = self._root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"{self._url_prefix}/{key}"


class R2Backend:
    """Uploads to Cloudflare R2 (S3 API) and returns a public URL.

    The boto3 client is built lazily and reused (it holds a connection pool)."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        public_base_url: str,
    ) -> None:
        self._endpoint = endpoint
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._bucket = bucket
        self._public_base_url = public_base_url.rstrip("/")
        self._client = None
        self._client_lock = threading.Lock()

    def _get_client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    try:
                        import boto3
                        from botocore.config import Config
                    except ImportError as exc:  # pragma: no cover
                        raise ObjectStorageError(
                            "boto3 is required for R2 storage but is not installed."
                        ) from exc
                    self._client = boto3.client(
                        "s3",
                        endpoint_url=self._endpoint,
                        aws_access_key_id=self._access_key_id,
                        aws_secret_access_key=self._secret_access_key,
                        # R2 ignores region but the SDK requires one.
                        region_name="auto",
                        config=Config(
                            signature_version="s3v4",
                            retries={"max_attempts": 3, "mode": "standard"},
                        ),
                    )
        return self._client

    def put(self, *, key: str, data: bytes, content_type: str) -> str:
        client = self._get_client()
        try:
            client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                CacheControl=_CACHE_CONTROL,
            )
        except Exception as exc:  # noqa: BLE001 — boto/botocore raise many types
            log.error("object_storage.r2_put_failed", key=key, error=str(exc))
            raise ObjectStorageError(f"Failed to upload image to R2: {exc}") from exc
        return f"{self._public_base_url}/{key}"


# ---------------------------------------------------------------------------
# Backend selection (cached)
# ---------------------------------------------------------------------------

_backend: StorageBackend | None = None
_lock = threading.Lock()


def build_backend() -> StorageBackend:
    """Construct the backend from current settings. Exposed (uncached) for
    tests; app code should call `get_backend()`."""

    if settings.r2_enabled:
        return R2Backend(
            endpoint=settings.r2_endpoint,
            access_key_id=settings.r2_access_key_id,
            secret_access_key=settings.r2_secret_access_key,
            bucket=settings.r2_bucket,
            public_base_url=settings.r2_public_base_url,
        )
    from app.services.image_upload_service import uploads_root

    return LocalDiskBackend(root=uploads_root(), url_prefix="/uploads")


def get_backend() -> StorageBackend:
    global _backend
    if _backend is None:
        with _lock:
            if _backend is None:
                _backend = build_backend()
    return _backend


def reset_backend() -> None:
    """Drop the cached backend so the next call rebuilds from settings. For
    tests that flip R2 config on/off."""
    global _backend
    with _lock:
        _backend = None


def put_object(*, key: str, data: bytes, content_type: str) -> str:
    """Store bytes at `key` and return the public URL to serve them from."""
    return get_backend().put(key=key, data=data, content_type=content_type)
