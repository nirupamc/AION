"""Database engine, session factory, and Base for SQLAlchemy 2 models."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None


def _ensure_sqlite_directory(url: str) -> None:
    """Create the parent directory for a SQLite file URL if it does not exist.

    No-ops for in-memory or non-SQLite URLs. Never creates a directory for
    production Postgres URLs.
    """
    if not url.startswith("sqlite:///"):
        return
    raw = url.removeprefix("sqlite:///")
    file_part = raw.split("?", 1)[0]
    if file_part in ("", ":memory:"):
        return
    # Handle sqlite:////absolute or sqlite:///C:/... — file_part is already absolute
    from pathlib import Path

    db_file = Path(file_part)
    # Only create directories for file-based SQLite DBs
    if db_file.suffix or "/" in file_part or "\\" in file_part:
        db_file.parent.mkdir(parents=True, exist_ok=True)


def _build_engine() -> Engine:
    url = settings.database_url
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        _ensure_sqlite_directory(url)
    engine = create_engine(url, future=True, connect_args=connect_args)
    log.info("database_engine_initialized url=%s", url)
    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a session and ensures cleanup."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_engine_for_tests() -> None:
    """Drop the cached engine/session so tests can point at a different URL."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
