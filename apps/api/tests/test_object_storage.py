"""Object storage backend selection + S3 upload (boto3 mocked).

No network: the S3 path stubs the boto3 client. The default (no S3 config)
path exercises the real local-disk backend, mirroring how the image-upload and
image-generation features behave in dev/CI.
"""

import pytest

from app.core.config import settings
from app.services import object_storage

_FIELDS = (
    "s3_access_key_id",
    "s3_secret_access_key",
    "s3_bucket",
    "s3_endpoint_url",
    "s3_prefix",
    "s3_public_url",
)


@pytest.fixture
def reset_s3():
    """Snapshot + restore S3 settings and the cached backend around a test."""
    saved = {k: getattr(settings, k) for k in _FIELDS}
    object_storage.reset_backend()
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(settings, k, v)
        object_storage.reset_backend()


def _configure_s3(*, prefix: str = "", public_url: str = "") -> None:
    settings.s3_access_key_id = "AKIAEXAMPLE"
    settings.s3_secret_access_key = "secret"
    settings.s3_bucket = "adgenie-images"
    settings.s3_endpoint_url = "https://acct123.r2.cloudflarestorage.com/"
    settings.s3_prefix = prefix
    settings.s3_public_url = public_url


def test_defaults_to_local_backend(reset_s3) -> None:
    for k in _FIELDS:
        setattr(settings, k, "")
    object_storage.reset_backend()

    assert not settings.s3_enabled
    assert type(object_storage.build_backend()).__name__ == "LocalDiskBackend"

    url = object_storage.put_object(
        key="blog-images/ws1/abc.png", data=b"\x89PNG", content_type="image/png"
    )
    assert url == "/uploads/blog-images/ws1/abc.png"


def test_s3_enabled_without_public_url(reset_s3) -> None:
    """The 5-var convention (no public URL) is valid; the endpoint is trimmed
    of its trailing slash and the public base derives to {endpoint}/{bucket}."""
    _configure_s3()
    assert settings.s3_enabled
    assert settings.s3_endpoint == "https://acct123.r2.cloudflarestorage.com"
    assert (
        settings.s3_public_base
        == "https://acct123.r2.cloudflarestorage.com/adgenie-images"
    )
    assert type(object_storage.build_backend()).__name__ == "S3Backend"


def test_explicit_public_url_wins(reset_s3) -> None:
    _configure_s3(public_url="https://cdn.adgeniehq.com/")
    assert settings.s3_public_base == "https://cdn.adgeniehq.com"


def test_missing_endpoint_disables_s3(reset_s3) -> None:
    _configure_s3()
    settings.s3_endpoint_url = ""
    assert not settings.s3_enabled
    assert type(object_storage.build_backend()).__name__ == "LocalDiskBackend"


def test_s3_put_applies_prefix_and_returns_public_url(reset_s3) -> None:
    _configure_s3(prefix="adgeniehq", public_url="https://cdn.adgeniehq.com")
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
    # S3_PREFIX namespaces the object key AND the URL.
    assert captured["Key"] == "adgeniehq/blog-images/ws1/def.png"
    assert url == "https://cdn.adgeniehq.com/adgeniehq/blog-images/ws1/def.png"
    assert captured["Bucket"] == "adgenie-images"
    assert captured["Body"] == b"IMG"
    assert captured["ContentType"] == "image/png"
    assert "immutable" in captured["CacheControl"]


def test_s3_put_without_prefix(reset_s3) -> None:
    _configure_s3(public_url="https://cdn.adgeniehq.com")
    object_storage.reset_backend()
    backend = object_storage.build_backend()

    captured: dict = {}
    backend._client = type("F", (), {"put_object": lambda self, **kw: captured.update(kw)})()

    url = backend.put(key="blog-images/ws1/x.png", data=b"x", content_type="image/png")
    assert captured["Key"] == "blog-images/ws1/x.png"
    assert url == "https://cdn.adgeniehq.com/blog-images/ws1/x.png"


def test_s3_put_failure_raises_storage_error(reset_s3) -> None:
    _configure_s3()
    object_storage.reset_backend()
    backend = object_storage.build_backend()

    class _BoomS3:
        def put_object(self, **kwargs):
            raise RuntimeError("network down")

    backend._client = _BoomS3()

    with pytest.raises(object_storage.ObjectStorageError):
        backend.put(key="k/x.png", data=b"x", content_type="image/png")


def test_r2_prefixed_env_names_still_load(reset_s3, monkeypatch) -> None:
    """Back-compat: the older R2_* env names map onto the same settings via
    AliasChoices, so anything shipped earlier keeps working."""
    from app.core.config import Settings

    for k in ("S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_BUCKET", "S3_ENDPOINT_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "r2key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "r2secret")
    monkeypatch.setenv("R2_BUCKET", "r2bucket")
    monkeypatch.setenv("R2_ENDPOINT_URL", "https://r2.example.com")

    s = Settings(_env_file=None)
    assert s.s3_access_key_id == "r2key"
    assert s.s3_secret_access_key == "r2secret"
    assert s.s3_bucket == "r2bucket"
    assert s.s3_endpoint_url == "https://r2.example.com"
    assert s.s3_enabled
