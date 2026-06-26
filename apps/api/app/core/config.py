from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3].parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="AdVanta", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    app_secret_key: str = Field(default="dev-secret-change-me", alias="APP_SECRET_KEY")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")

    database_url: str = Field(
        default="postgresql+psycopg://advanta:advanta@localhost:5432/advanta_ai",
        alias="DATABASE_URL",
    )
    test_database_url: str | None = Field(default=None, alias="TEST_DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"],
        alias="CORS_ORIGINS",
    )

    jwt_access_token_expire_minutes: int = Field(default=30, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    jwt_refresh_token_expire_days: int = Field(default=30, alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS")

    encryption_key: str = Field(default="", alias="ENCRYPTION_KEY")

    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")
    backend_url: str = Field(default="http://localhost:8000", alias="BACKEND_URL")

    # Slug of the workspace whose published blog_post drafts are served on
    # the public marketing site at /blog. When empty, the public blog returns
    # an empty list (honest empty state, no fabricated posts). Customers
    # using AdVanta to write their own blog publish to their own CMS via
    # the existing publish_webhook flow — this only controls advantaai.com/blog.
    marketing_workspace_slug: str = Field(
        default="", alias="MARKETING_WORKSPACE_SLUG"
    )

    # Founding super-admins. Comma-separated (or JSON list) of emails promoted
    # to is_superuser=True on API startup — grants /admin access + bypasses all
    # plan limits. Additive + idempotent: it never demotes, and re-promotes on
    # every boot so a restored DB keeps its admins. Match is case-insensitive;
    # the user must already have registered.
    initial_superuser_emails: list[str] = Field(
        default=[], alias="INITIAL_SUPERUSER_EMAILS"
    )

    # Production hardening (M12)
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    rate_limit_disabled: bool = Field(default=False, alias="RATE_LIMIT_DISABLED")

    # LLM (used by content/outreach generation skills).
    #
    # `LLM_PROVIDER` selects the env-default. Workspaces can override per-call
    # by adding their own credential under Settings → API keys. Supported
    # providers: "openai", "anthropic", "google_ai".
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    # Per-provider models — only the one matching `llm_provider` is used at
    # the env level, but all are read so a workspace BYOK credential of any
    # provider can pick up the right default model.
    llm_model: str = Field(default="gpt-5.4-mini", alias="LLM_MODEL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", alias="OPENAI_BASE_URL"
    )
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-4-6", alias="ANTHROPIC_MODEL")
    google_ai_api_key: str = Field(default="", alias="GOOGLE_AI_API_KEY")
    google_ai_model: str = Field(default="gemini-1.5-flash", alias="GOOGLE_AI_MODEL")
    # Optional faster/cheaper model used ONLY for large background generations
    # (the Growth DNA marketing strategy). Must match the active provider's
    # naming (e.g. claude-haiku-4-5 for anthropic, gpt-5.4-mini for openai).
    # Empty = use the provider's normal model.
    llm_fast_model: str = Field(default="", alias="LLM_FAST_MODEL")
    # Per-request HTTP timeout (seconds) for LLM provider calls. Larger
    # generations (e.g. the full Growth DNA marketing strategy) can legitimately
    # run longer than the old 60s default, so this is generous by default.
    llm_http_timeout_seconds: float = Field(
        default=120.0, alias="LLM_HTTP_TIMEOUT_SECONDS"
    )

    # Inbound email parsing — Postmark/Sendgrid/Mailgun-style webhooks.
    # When `inbound_email_domain` is set, outreach emails go out with a
    # Reply-To of `reply+<token>@<domain>`. Set up a parse rule in your inbound
    # provider that POSTs to /api/v1/inbound/email with X-Inbound-Secret =
    # `inbound_email_secret`.
    inbound_email_domain: str = Field(default="", alias="INBOUND_EMAIL_DOMAIN")
    inbound_email_secret: str = Field(default="", alias="INBOUND_EMAIL_SECRET")

    # Outreach send throttle — per-workspace cap on actual SMTP sends per
    # rolling minute. Stops a misconfigured loop from spam-flagging the
    # sending domain.
    outreach_send_per_minute: int = Field(default=10, alias="OUTREACH_SEND_PER_MINUTE")
    # Days to wait before auto-drafting a follow-up if no reply received.
    outreach_followup_after_days: int = Field(default=3, alias="OUTREACH_FOLLOWUP_AFTER_DAYS")
    # Public unsubscribe URL we append to outreach bodies. When empty we
    # append a "reply STOP to unsubscribe" line instead.
    unsubscribe_url: str = Field(default="", alias="UNSUBSCRIBE_URL")

    # Provider webhook shared secrets. Each ad platform that supports outbound
    # notifications (status changes, account flags, billing alerts) signs
    # payloads with HMAC-SHA256 of the raw body using one of these secrets.
    # Set per platform; the route that receives the call selects the matching
    # secret. If empty for a given provider, the route returns 503 — we don't
    # silently accept unsigned traffic.
    google_ads_webhook_secret: str = Field(
        default="", alias="GOOGLE_ADS_WEBHOOK_SECRET"
    )
    meta_ads_webhook_secret: str = Field(
        default="", alias="META_ADS_WEBHOOK_SECRET"
    )
    linkedin_ads_webhook_secret: str = Field(
        default="", alias="LINKEDIN_ADS_WEBHOOK_SECRET"
    )

    # Google OAuth *for end-user login* (not the ad/analytics integrations).
    # We use a separate OAuth client for login so the consent screen + scopes
    # stay narrow ("identify yourself") rather than the broader ad-data
    # scopes the integrations request.
    google_login_client_id: str = Field(default="", alias="GOOGLE_LOGIN_CLIENT_ID")
    google_login_client_secret: str = Field(
        default="", alias="GOOGLE_LOGIN_CLIENT_SECRET"
    )
    # Where Google redirects after consent. Must be an absolute URL pointing
    # to /api/v1/auth/google/callback on this backend.
    google_login_redirect_uri: str = Field(
        default="", alias="GOOGLE_LOGIN_REDIRECT_URI"
    )

    # Background workers — Celery + Redis. Off by default so tests + dev stay
    # sync and fast. Flip on per environment to dispatch slow tasks
    # (landing-page audits, LLM calls, ad-test launches) to the worker pool.
    workers_enabled: bool = Field(default=False, alias="WORKERS_ENABLED")
    celery_broker_url: str = Field(default="", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="", alias="CELERY_RESULT_BACKEND")

    @field_validator("database_url", "test_database_url", mode="before")
    @classmethod
    def _force_psycopg_driver(cls, value: object) -> object:
        """Pin the SQLAlchemy URL to the psycopg (v3) driver.

        Managed hosts (Render, Heroku, Railway) hand out a *bare*
        ``postgresql://…`` (or the legacy ``postgres://…``) connection string
        with no driver. SQLAlchemy then defaults to the ``psycopg2`` dialect,
        which this project does NOT install — we ship ``psycopg`` v3. Without
        this, the auto-wired ``DATABASE_URL`` blows up with
        ``ModuleNotFoundError: No module named 'psycopg2'`` (e.g. the
        ``alembic upgrade head`` pre-deploy step). Rewriting the scheme here
        means the connection string works untouched, app engine + migrations
        alike.
        """
        if not isinstance(value, str) or not value:
            return value
        for prefix in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                import json

                return json.loads(stripped)
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    @field_validator("initial_superuser_emails", mode="before")
    @classmethod
    def _split_superuser_emails(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                import json

                return json.loads(stripped)
            return [e.strip() for e in stripped.split(",") if e.strip()]
        return value


def validate_production_settings(s: "Settings") -> list[str]:
    """Return a list of fatal misconfigurations for a *production* deploy.

    Pure function (no side effects) so it can be unit-tested without booting
    the app. Returns an empty list for non-production environments or when the
    config is safe. The app refuses to start (in ``main.lifespan``) when this
    returns anything, so a forgotten env var can never silently ship an
    insecure default (e.g. the public dev signing key)."""
    if (s.app_env or "").lower() != "production":
        return []

    problems: list[str] = []

    if s.app_secret_key in ("", "dev-secret-change-me") or len(s.app_secret_key) < 32:
        problems.append(
            "APP_SECRET_KEY must be a strong, random value of at least 32 "
            "characters in production (it signs every JWT and OAuth state token)."
        )
    if s.app_debug:
        problems.append("APP_DEBUG must be false in production (it leaks verbose errors).")

    key = (s.encryption_key or "").strip()
    if not key:
        problems.append("ENCRYPTION_KEY must be set in production (it encrypts OAuth tokens at rest).")
    else:
        try:
            from cryptography.fernet import Fernet

            Fernet(key.encode("utf-8"))
        except Exception:
            problems.append(
                "ENCRYPTION_KEY is not a valid Fernet key. Generate one with "
                "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`."
            )

    if "*" in s.cors_origins:
        problems.append(
            "CORS_ORIGINS must not include '*' in production because credentials are allowed."
        )

    return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
