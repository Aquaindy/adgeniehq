"""Per-request correlation ID middleware.

- Reuses an inbound `X-Request-ID` header when present, otherwise mints a UUIDv4.
- Binds the ID to structlog's contextvars so every log line in the request
  scope carries `request_id`.
- Echoes the ID back to the client in the response header for log correlation."""

from __future__ import annotations

from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(HEADER) or str(uuid4())
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        try:
            response = await call_next(request)
        finally:
            # Don't leak per-request context across worker boundaries
            structlog.contextvars.unbind_contextvars("request_id", "method", "path")

        response.headers[HEADER] = request_id
        return response
