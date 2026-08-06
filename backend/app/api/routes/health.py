from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import inspect, text

from backend.app.core.config import get_settings

router = APIRouter(tags=["system"])

REQUIRED_AUTH_SCHEMA = {
    "learners": {"user_account_id"},
    "refresh_tokens": {"family_id", "parent_token_id"},
}


def authentication_schema_is_compatible(connection) -> bool:
    inspector = inspect(connection)
    try:
        return all(
            required.issubset({column["name"] for column in inspector.get_columns(table)})
            for table, required in REQUIRED_AUTH_SCHEMA.items()
        )
    except Exception:
        return False


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        service=settings.app_name,
        version=settings.app_version,
    )


@router.get("/health/live")
def live(request: Request):
    return {"status": "alive", "service": request.app.state.settings.app_name}


@router.get("/health/ready")
def ready(request: Request):
    settings = request.app.state.settings
    checks = {
        "database": "unavailable",
        "migration": "unavailable",
        "authentication": "unavailable",
        "providers": "configured" if settings.providers_ready() else "unavailable",
    }
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            try:
                revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                checks["migration"] = (
                    "ready"
                    if revision == "0009_commercial_subscriptions" and authentication_schema_is_compatible(connection)
                    else "incompatible"
                )
            except Exception:
                if settings.environment != "production" and settings.auto_create_tables:
                    checks["migration"] = "development_metadata"
        checks["database"] = "ready"
    except Exception:
        pass
    try:
        keys = settings.signing_keys()
        if all(len(value) >= 32 for value in keys.values()):
            checks["authentication"] = "ready"
    except (ValueError, TypeError):
        pass
    ready_state = (
        checks["database"] == "ready"
        and checks["authentication"] == "ready"
        and checks["providers"] == "configured"
        and checks["migration"] in {"ready", "development_metadata"}
    )
    if settings.environment == "production":
        redis_ready = not settings.redis_required
        if request.app.state.redis is not None:
            try:
                redis_ready = bool(request.app.state.redis.ping())
            except Exception:
                redis_ready = False
        storage_ready = False
        if request.app.state.object_storage is not None:
            try:
                storage_ready = request.app.state.object_storage.healthcheck()
            except Exception:
                storage_ready = False
        worker_ready = not settings.worker_enabled
        if settings.worker_enabled and request.app.state.redis is not None:
            try:
                worker_ready = bool(request.app.state.redis.get(settings.worker_heartbeat_key))
            except Exception:
                worker_ready = False
        checks.update({
            "redis": "ready" if redis_ready else "unavailable",
            "object_storage": "ready" if storage_ready else "unavailable",
            "openai": "configured" if (settings.llm_provider != "openai" or settings.openai_api_key) else "unavailable",
            "payment": "configured" if (not settings.razorpay_enabled or settings.razorpay_webhook_secret) else "unavailable",
            "worker": "ready" if (not settings.worker_enabled or getattr(request.app.state, "worker_healthy", False)) else "unavailable",
        })
        ready_state = ready_state and all(
            value in {"ready", "configured"}
            for key, value in checks.items()
            if key in {"redis", "object_storage", "openai", "payment", "worker"}
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready_state else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if ready_state else "not_ready", "checks": checks},
    )


@router.get("/health/version")
def version(request: Request):
    settings = request.app.state.settings
    return {
        "application_version": settings.app_version,
        "build_identifier": settings.build_identifier,
        "environment": settings.environment,
        "api_version": "v1",
        "dependencies": {"python": "3.12+", "database_schema": "0009_commercial_subscriptions"},
    }


@router.get("/internal/metrics")
def metrics(request: Request):
    if not request.app.state.settings.expose_development_metrics:
        return JSONResponse(status_code=404, content={"error": {"code": "resource_not_found", "message": "Resource not found."}})
    return request.app.state.metrics.snapshot()
