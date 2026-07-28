from backend.app.core.config import get_settings
from backend.app.db.session import build_engine, build_session_factory
from backend.app.services.voice import VoiceService
from backend.app.core.operations import InMemoryMetrics


def main() -> int:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    with session_factory() as session:
        deleted = VoiceService(session, metrics=InMemoryMetrics()).cleanup(
            batch_size=settings.audio_cleanup_batch_size
        )
    engine.dispose()
    print(f"audio_cleanup_deleted={deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
