from fastapi import APIRouter, Depends, Response, status
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.health import ComponentHealth, HealthResponse

router = APIRouter()


@router.get("", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness — is the process up. Cheap, no dependency probes."""
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        env=settings.app_env,
        version="0.0.1",
    )


@router.get("/ready")
def health_ready(response: Response, db: Session = Depends(get_db)) -> dict:
    """Readiness — probes Postgres AND Redis and returns **503** if either is
    down, so a load balancer / Render health check pulls a brownout instance
    out of rotation instead of routing traffic to it."""
    checks: dict[str, str] = {}
    healthy = True

    try:
        db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except SQLAlchemyError as exc:
        checks["postgres"] = f"error:{exc.__class__.__name__}"
        healthy = False

    client = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
    try:
        client.ping()
        checks["redis"] = "ok"
    except RedisError as exc:
        checks["redis"] = f"error:{exc.__class__.__name__}"
        healthy = False
    finally:
        try:
            client.close()
        except Exception:  # pragma: no cover — defensive
            pass

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", "checks": checks}


@router.get("/db", response_model=ComponentHealth)
def health_db(db: Session = Depends(get_db)) -> ComponentHealth:
    try:
        db.execute(text("SELECT 1"))
        return ComponentHealth(component="postgres", status="ok")
    except SQLAlchemyError as exc:
        return ComponentHealth(
            component="postgres",
            status="error",
            detail=str(exc.__class__.__name__),
        )


@router.get("/redis", response_model=ComponentHealth)
def health_redis() -> ComponentHealth:
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
    try:
        client.ping()
        return ComponentHealth(component="redis", status="ok")
    except RedisError as exc:
        return ComponentHealth(
            component="redis",
            status="error",
            detail=str(exc.__class__.__name__),
        )
    finally:
        try:
            client.close()
        except Exception:
            pass


__all__ = ["router", "status"]
