from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from backend.app.core.config import get_settings

router = APIRouter(tags=["system"])


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
                checks["migration"] = "ready" if revision == "0005_operations_observability" else "incompatible"
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
    }


@router.get("/internal/metrics")
def metrics(request: Request):
    if not request.app.state.settings.expose_development_metrics:
        return JSONResponse(status_code=404, content={"error": {"code": "resource_not_found", "message": "Resource not found."}})
    return request.app.state.metrics.snapshot()
