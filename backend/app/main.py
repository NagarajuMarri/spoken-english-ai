from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes.conversations import router as conversations_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.learners import router as learners_router
from backend.app.api.routes.learning import router as learning_router
from backend.app.api.routes.voice import router as voice_router
from backend.app.api.routes.auth import router as auth_router
from backend.app.api.routes.ai import router as ai_router
from backend.app.api.routes.tutors import router as tutors_router
from backend.app.api.routes.intelligent_learning import router as intelligent_learning_router
from backend.app.api.routes.commercial import router as commercial_router
from backend.app.core.security import InMemoryLoginThrottler
from backend.app.core.operations import InMemoryMetrics, InMemoryRateLimiter, request_context_middleware
from backend.app.core.config import get_settings
from backend.app.core.errors import install_error_handlers
from backend.app.db.base import Base
from backend.app.db.session import build_engine, build_session_factory
from backend.app.intelligent_learning import IntelligentLearningEngine
from backend.app.commercial.models import CommercialConfig
from backend.app.commercial.payments import RazorpayBoundary
from backend.app.commercial.service import CommercialService
import backend.app.models  # noqa: F401


def create_app(settings=None) -> FastAPI:
    settings = settings or get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )
    engine = build_engine(settings.database_url)
    application.state.engine = engine
    application.state.settings = settings
    application.state.login_throttler = InMemoryLoginThrottler(settings.login_attempt_limit)
    application.state.metrics = InMemoryMetrics()
    application.state.rate_limiter = InMemoryRateLimiter()
    application.state.session_factory = build_session_factory(engine)
    application.state.learning_engine = IntelligentLearningEngine()
    commercial_config = CommercialConfig(
        settings.commercial_monthly_price_inr,
        settings.commercial_yearly_price_inr,
        settings.commercial_trial_days,
        settings.commercial_free_daily_conversations,
        settings.commercial_free_daily_voice_minutes,
        settings.commercial_free_daily_grammar_checks,
        settings.commercial_free_daily_pronunciation_checks,
        settings.commercial_premium_fair_use_daily_requests,
        settings.commercial_premium_voice_minutes,
        settings.commercial_monthly_ai_cost_limit_usd,
        settings.commercial_advertisements_enabled,
        settings.commercial_premium_tutors_enabled,
    )
    application.state.commercial_service = CommercialService(
        commercial_config,
        RazorpayBoundary(settings.razorpay_webhook_secret or None),
    )
    if settings.auto_create_tables:
        Base.metadata.create_all(engine)
    install_error_handlers(application)
    application.middleware("http")(request_context_middleware)
    application.include_router(health_router)
    application.include_router(learners_router)
    application.include_router(conversations_router)
    application.include_router(learning_router)
    application.include_router(voice_router)
    application.include_router(auth_router)
    application.include_router(ai_router)
    application.include_router(tutors_router)
    application.include_router(intelligent_learning_router)
    application.include_router(commercial_router)
    frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend.is_dir():
        application.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")
        application.mount("/tutors", StaticFiles(directory=frontend / "tutors"), name="tutors")

        @application.get("/", include_in_schema=False)
        def learner_experience():
            return FileResponse(frontend / "index.html")

    return application


app = create_app()
