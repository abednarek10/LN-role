"""SQLAlchemy engine, session factory, and FastAPI dependency."""
from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def make_engine(url: str = DATABASE_URL) -> Engine:
    """Build an engine for ``url`` (SQLite gets thread-safety + FK pragmas)."""
    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    eng = create_engine(url, echo=False, future=True, connect_args=connect_args)
    if is_sqlite:

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return eng


engine: Engine = make_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session and closing it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all(bind: Engine | None = None) -> None:
    """Create all tables. Idempotent — safe to call on every boot."""
    from . import models  # noqa: F401  (populate metadata)

    Base.metadata.create_all(bind=bind or engine)


def drop_all(bind: Engine | None = None) -> None:
    from . import models  # noqa: F401

    Base.metadata.drop_all(bind=bind or engine)
