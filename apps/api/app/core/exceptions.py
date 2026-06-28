from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

log = get_logger(__name__)


class AdGenieError(Exception):
    """Base error for AdGenieHQ business logic. Subclass for domain-specific errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "adgeniehq_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


# Backwards-compatibility alias. The codebase was renamed AdVanta -> AdGenieHQ;
# modules that still import the old name (e.g. deployed code that predates the
# rename) resolve to the same class. Safe to remove once every importer uses
# AdGenieError.
AdVantaError = AdGenieError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AdGenieError)
    async def handle_adgeniehq_error(_: Request, exc: AdGenieError) -> JSONResponse:
        log.warning("adgeniehq.error", code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": exc.detail}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("adgeniehq.unhandled", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": "internal_error", "message": "Internal server error."}},
        )
