"""Production config guard tests (app.core.config.validate_production_settings).

The guard fails the app's startup when a production deploy would ship an
insecure default (public dev signing key, debug on, missing/invalid encryption
key, or wildcard CORS with credentials). Pure-function tests — no boot needed.
"""

from cryptography.fernet import Fernet

from app.core.config import settings, validate_production_settings

_GOOD_KEY = Fernet.generate_key().decode()
_GOOD_SECRET = "x" * 48


def _prod(**overrides):
    base = {
        "app_env": "production",
        "app_debug": False,
        "app_secret_key": _GOOD_SECRET,
        "encryption_key": _GOOD_KEY,
        "cors_origins": ["https://app.advantaai.com"],
    }
    base.update(overrides)
    return settings.model_copy(update=base)


def test_non_production_never_blocks() -> None:
    # Even with every insecure default, a dev/staging env returns no problems.
    s = settings.model_copy(
        update={
            "app_env": "development",
            "app_debug": True,
            "app_secret_key": "dev-secret-change-me",
            "encryption_key": "",
            "cors_origins": ["*"],
        }
    )
    assert validate_production_settings(s) == []


def test_clean_production_config_passes() -> None:
    assert validate_production_settings(_prod()) == []


def test_default_secret_key_is_rejected() -> None:
    problems = validate_production_settings(_prod(app_secret_key="dev-secret-change-me"))
    assert any("APP_SECRET_KEY" in p for p in problems)


def test_short_secret_key_is_rejected() -> None:
    problems = validate_production_settings(_prod(app_secret_key="too-short"))
    assert any("APP_SECRET_KEY" in p for p in problems)


def test_debug_on_is_rejected() -> None:
    problems = validate_production_settings(_prod(app_debug=True))
    assert any("APP_DEBUG" in p for p in problems)


def test_missing_encryption_key_is_rejected() -> None:
    problems = validate_production_settings(_prod(encryption_key=""))
    assert any("ENCRYPTION_KEY" in p for p in problems)


def test_invalid_encryption_key_is_rejected() -> None:
    problems = validate_production_settings(_prod(encryption_key="not-a-fernet-key"))
    assert any("ENCRYPTION_KEY" in p for p in problems)


def test_wildcard_cors_is_rejected() -> None:
    problems = validate_production_settings(_prod(cors_origins=["*"]))
    assert any("CORS_ORIGINS" in p for p in problems)


def test_multiple_problems_all_reported() -> None:
    problems = validate_production_settings(
        _prod(
            app_secret_key="dev-secret-change-me",
            app_debug=True,
            encryption_key="",
            cors_origins=["*"],
        )
    )
    assert len(problems) >= 4
