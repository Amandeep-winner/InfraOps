"""Database session and SQLite WAL engine management."""

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from infraops.common.config import get_settings
from infraops.server.models import Base

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine(db_url: str | None = None) -> Engine:
    """Create or return existing SQLAlchemy engine configured with SQLite WAL."""
    global _engine, _session_factory
    if _engine is not None and db_url is None:
        return _engine

    url = db_url or get_settings().db_url

    # Ensure SQLite parent directory exists
    if url.startswith("sqlite:///"):
        db_path = url.replace("sqlite:///", "")
        if db_path != ":memory:":
            Path(db_path).resolve().parent.mkdir(parents=True, exist_ok=True)

    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 30}

    engine = create_engine(url, connect_args=connect_args, echo=False)

    # Enable WAL mode and busy timeout on SQLite connections
    if url.startswith("sqlite") and not url.endswith(":memory:"):

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    _engine = engine
    _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine


def init_db(engine: Engine | None = None) -> None:
    """Create all database tables."""
    eng = engine or get_engine()
    Base.metadata.create_all(bind=eng)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    db = _session_factory()
    try:
        yield db
    finally:
        db.close()


def reset_db_engine() -> None:
    """Reset cached database engine and sessionmaker (for test isolation)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
