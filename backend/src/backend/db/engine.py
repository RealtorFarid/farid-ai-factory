"""Database engine and sessions.

Synchronous SQLAlchemy, deliberately (ADR D-021). The async ORM costs more to
own than it saves here: queries are small and indexed, FastAPI runs plain `def`
handlers in a worker thread, PydanticAI runs sync tools off the event loop, and
the few async callers offload explicitly via :func:`in_thread`. One engineer can
hold this in their head; async sessions, greenlet context and lazy-load
surprises are a tax paid forever for latency that is not the bottleneck.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import anyio.to_thread
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.runtime.logger import get_logger

__all__ = ["Database", "in_thread"]

log = get_logger(__name__)


async def in_thread[T](fn: Callable[..., T], *args: Any) -> T:
    """Run a blocking repository call from async code without stalling the loop."""
    return await anyio.to_thread.run_sync(fn, *args)


class Database:
    """Owns the engine and hands out sessions."""

    def __init__(self, url: str, *, echo: bool = False, pool_size: int = 5) -> None:
        self._engine: Engine = create_engine(
            url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=pool_size * 2,
            pool_pre_ping=True,  # survives Postgres restarts and idle timeouts
            future=True,
        )
        self._session_factory = sessionmaker(
            bind=self._engine, expire_on_commit=False, class_=Session
        )

    @property
    def engine(self) -> Engine:
        return self._engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        """A session with commit-on-success, rollback-on-error."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def check(self) -> bool:
        """Cheap liveness probe for the readiness endpoint."""
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            log.warning("db.unreachable", error=str(exc))
            return False
        return True

    def dispose(self) -> None:
        self._engine.dispose()
