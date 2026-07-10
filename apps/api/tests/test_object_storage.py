"""Object storage backend selection + R2 upload (boto3 mocked).

No network: the R2 path stubs the boto3 client. The default (no R2 config)
path exercises the real local-disk backend, mirroring how the image-upload and
image-generation features behave in dev/CI.
"""

import pytest

from app.core.config import settings
from app.services import object_storage


@pytest.fixture
def reset_r2():
    """Snapshot + restore R2 settings and the cached backend around a test."""
    keys = (
        "r2_account_id",
        "r2_access_key_id",
        "r2_secret_access_key",
        "r2_bucket",
        "r2_public_base_url",
        "r2_endpoint_url",
    )
    saved = {k: getattr(settings, k) for k in keys}
    object_storage.reset_backend()
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(settings, k, v)
        object_storage.reset_backend()


def _configure_r2() -> None:
    settings.r2_account_id = "acct123"
    settings.r2_access_key_id = "AKIAEXAMPLE"
    settings.r2_secret_access_key = "secret"
    settings.r2_bucket = "adgenie-images"
    settings.r2_public_base_url = "https://pub-xyz.r2.dev/"  # trailing slash on purpose
    settings.r2_endpoint_url = ""


def test_defaults_to_local_backend(reset_r2) -> None:
    for k in (
        "r2_account_id",
        "r2_access_key_id",
        "r2_secret_access_key",
        "r2_bucket",
        "r2_public_base_url",
        "r2_endpoint_url",
    ):
        setattr(settings, k, "")
    object_storage.reset_backend()

    assert not settings.r2_enabled
    backend = object_storage.build_backend()
    assert type(backend).__name__ == "LocalDiskBackend"

    url = object_storage.put_object(
        key="blog-images/ws1/abc.png", data=b"\x89PNG", content_type="image/png"
    )
    assert url == "/uploads/blog-images/ws1/abc.png"


def test_r2_enabled_when_fully_configured(reset_r2) -> None:
    _configure_r2()
    assert settings.r2_enabled
    assert settings.r2_endpoint == "https://acct123.r2.cloudflarestorage.com"
    assert type(object_storage.build_backend()).__name__ == "R2Backend"


def test_r2_endpoint_override(reset_r2) -> None:
    _configure_r2()
    settings.r2_endpoint_url = "https://custom.example.com/"
    assert settings.r2_endpoint == "https://custom.example.com"


def test_missing_any_field_disables_r2(reset_r2) -> None:
    _configure_r2()
    settings.r2_public_base_url = ""  # drop one required field
    assert not settings.r2_enabled
    assert type(object_storage.build_backend()).__name__ == "LocalDiskBackend"


def test_r2_put_uploads_and_returns_public_url(reset_r2) -> None:
    _configure_r2()
    object_storage.reset_backend()
    backend = object_storage.build_backend()

    captured: dict = {}

    class _FakeS3:
        def put_object(self, **kwargs):
            captured.update(kwargs)

    backend._client = _FakeS3()  # skip real boto3/network

    url = backend.put(
        key="blog-images/ws1/def.png", data=b"IMG", content_type="image/png"
    )
    # Public URL joins the base (trailing slash trimmed) and the key.
    assert url == "https://pub-xyz.r2.dev/blog-images/ws1/def.png"
    assert captured["Bucket"] == "adgenie-images"
    assert captured["Key"] == "blog-images/ws1/def.png"
    assert captured["Body"] == b"IMG"
    assert captured["ContentType"] == "image/png"
    assert "immutable" in captured["CacheControl"]


def test_r2_put_failure_raises_storage_error(reset_r2) -> None:
    _configure_r2()
    object_storage.reset_backend()
    backend = object_storage.build_backend()

    class _BoomS3:
        def put_object(self, **kwargs):
            raise RuntimeError("network down")

    backend._client = _BoomS3()

    with pytest.raises(object_storage.ObjectStorageError):
        backend.put(key="k/x.png", data=b"x", content_type="image/png")
