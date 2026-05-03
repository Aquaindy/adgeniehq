"""Redis-backed IP rate limiter.

Cheap fixed-window counters keyed by `(prefix, ip)`. Buckets are tuned per
endpoint group:

- auth (login/register/password-reset): 30 req / minute / IP
- agent runs (expensive): 30 req / minute / IP
- billing checkout: 10 req / minute / IP
- everything else: 600 req / minute / IP

When `RATE_LIMIT_DISABLED=1` the middleware is a no-op (used in tests). On
Redis errors we fail-open with a warning."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from redis import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern[str]
    limit: int
    window_seconds: int
    label: str


RULES: tuple[Rule, ...] = (
    Rule(re.compile(r"/auth/(login|register|password-reset)"), 30, 60, "auth"),
    Rule(re.compile(r"/agents/run$"), 30, 60, "agents.run"),
    Rule(re.compile(r"/landing-pages/[^/]+/audit$"), 30, 60, "landing.audit"),
    Rule(re.compile(r"/billing/checkout-session$"), 10, 60, "billing.checkout"),
    Rule(re.compile(r"/billing/portal-session$"), 10, 60, "billing.portal"),
    Rule(re.compile(r"/campaigns/sync$"), 20, 60, "campaigns.sync"),
    Rule(re.compile(r"/seo/sync$"), 20, 60, "seo.sync"),
    Rule(re.compile(r"/integrations/[^/]+/(sync|disconnect)$"), 20, 60, "integrations.sync"),
)

DEFAULT_RULE = Rule(re.compile(r".*"), 600, 60, "default")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _match_rule(path: str) -> Rule:
    for rule in RULES:
        if rule.pattern.search(path):
            return rule
    return DEFAULT_RULE


def _redis_client() -> Redis | None:
    try:
        return Redis.from_url(settings.redis_url, socket_connect_timeout=1)
    except RedisError:
        return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if settings.rate_limit_disabled:
            return await call_next(request)

        # Always allow OPTIONS (CORS preflight) and health probes
        if request.method == "OPTIONS" or request.url.path.startswith(
            f"{settings.api_v1_prefix}/health"
        ):
            return await call_next(request)

        rule = _match_rule(request.url.path)
        ip = _client_ip(request)

        bucket = f"rl:{rule.label}:{ip}:{int(time.time() // rule.window_seconds)}"
        client = _redis_client()
        if client is None:
            log.warning("rate_limit.redis_unreachable", path=request.url.path)
            return await call_next(request)

        try:
            pipe = client.pipeline()
            pipe.incr(bucket)
            pipe.expire(bucket, rule.window_seconds + 5)
            count, _ = pipe.execute()
        except RedisError as exc:
            log.warning("rate_limit.failed_open", error=str(exc))
            return await call_next(request)

        if count > rule.limit:
            log.info(
                "rate_limit.exceeded",
                rule=rule.label,
                ip=ip,
                count=count,
                limit=rule.limit,
                path=request.url.path,
            )
            retry_after = rule.window_seconds
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": (
                            f"Too many requests in the last {rule.window_seconds}s "
                            f"({count} > {rule.limit})."
                        ),
                    }
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(rule.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rule.limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, rule.limit - int(count)))
        return response
