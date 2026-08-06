from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine
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
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session
