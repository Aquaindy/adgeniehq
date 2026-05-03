from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1 import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.request_id import RequestIdMiddleware
from app.security.rate_limit import RateLimitMiddleware

configure_logging()
log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Sentry — env-driven. No-op when SENTRY_DSN isn't set.
# ---------------------------------------------------------------------------

if settings.sentry_dsn:
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            release="advanta-api@0.0.1",
            traces_sample_rate=0.1 if settings.app_env == "production" else 0.0,
            send_default_pii=False,
        )
        log.info("sentry.initialized", env=settings.app_env)
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("sentry.init_failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("api.startup", env=settings.app_env, debug=settings.app_debug)
    yield
    log.info("api.shutdown")


app = FastAPI(
    title=settings.app_name,
    version="0.0.1",
    debug=settings.app_debug,
    lifespan=lifespan,
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url=f"{settings.api_v1_prefix}/docs",
    redoc_url=f"{settings.api_v1_prefix}/redoc",
    description=(
        "AdVanta AI — Growth Command Center API. Multi-tenant SaaS that runs "
        "AI Skill Agents over real ad accounts, analytics, and websites. "
        "All routes are JWT-authenticated and workspace-scoped."
    ),
    contact={"name": "AdVanta AI", "url": "https://advantaai.com"},
)

# Order matters: outermost first. CORS sees outbound responses last; rate
# limiter is below CORS so OPTIONS preflights aren't counted; request ID is
# innermost so the limiter's responses also include the correlation header.
_PUBLIC_PATH_PREFIX = f"{settings.api_v1_prefix}/public/"
_PUBLIC_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "600",
}


class PublicCorsMiddleware(BaseHTTPMiddleware):
    """`/api/v1/public/*` is the only set of routes meant for unauthenticated,
    cross-origin traffic from a customer's landing page. The strict
    CORSMiddleware below would otherwise reject those preflights with 400; we
    short-circuit them here before they get there."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(_PUBLIC_PATH_PREFIX):
            if request.method == "OPTIONS":
                return Response(status_code=204, headers=_PUBLIC_CORS_HEADERS)
            response = await call_next(request)
            for k, v in _PUBLIC_CORS_HEADERS.items():
                response.headers.setdefault(k, v)
            return response
        return await call_next(request)


# Order: outermost first; a request travels left-to-right.
# RequestId → RateLimit → PublicCors → CORSMiddleware → app
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
)
app.add_middleware(PublicCorsMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIdMiddleware)

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.api_v1_prefix)

# Static assets — currently the public A/B traffic-split snippet.
# Customers paste a <script src="…/static/advanta-ab.js"> into their site.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# User uploads — blog cover images and inline images attached to drafts.
# The directory is created on first upload by image_upload_service.
from app.services.image_upload_service import uploads_root as _uploads_root  # noqa: E402

_UPLOADS_DIR = _uploads_root()
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "version": "0.0.1",
        "docs": f"{settings.api_v1_prefix}/docs",
        "health": f"{settings.api_v1_prefix}/health",
    }
