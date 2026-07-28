from fastapi import FastAPI

from backend.app.api.routes.conversations import router as conversations_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.learners import router as learners_router
from backend.app.api.routes.learning import router as learning_router
from backend.app.api.routes.voice import router as voice_router
from backend.app.core.config import get_settings
from backend.app.core.errors import install_error_handlers
from backend.app.db.base import Base
from backend.app.db.session import build_engine, build_session_factory
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
    application.state.session_factory = build_session_factory(engine)
    if settings.auto_create_tables:
        Base.metadata.create_all(engine)
    install_error_handlers(application)
    application.include_router(health_router)
    application.include_router(learners_router)
    application.include_router(conversations_router)
    application.include_router(learning_router)
    application.include_router(voice_router)
    return application


app = create_app()
