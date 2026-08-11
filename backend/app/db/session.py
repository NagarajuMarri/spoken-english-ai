from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def build_engine(
    database_url: str,
    *,
    pool_size: int = 5,
    pool_timeout_seconds: int = 10,
    connect_timeout_seconds: int = 10,
) -> Engine:
    connect_args: dict[str, object] = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    if database_url.startswith("postgresql"):
        connect_args = {"connect_timeout": connect_timeout_seconds, "options": "-c statement_timeout=30000"}
        return create_engine(
            database_url, connect_args=connect_args, pool_pre_ping=True,
            pool_size=pool_size, max_overflow=pool_size, pool_timeout=pool_timeout_seconds, pool_recycle=1800,
        )
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=5000")
            finally:
                cursor.close()
    return engine


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session
