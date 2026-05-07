"""Async SQLAlchemy engine + session factory."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bot.config import Settings, get_settings
from bot.db.models import Base
from bot.logger import get_logger

logger = get_logger(__name__)


class Database:
    """Wraps the async engine and session maker."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        if settings.is_sqlite and settings.sqlite_path is not None:
            settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

        connect_args: dict[str, object] = {}
        if settings.is_sqlite:
            connect_args["timeout"] = 30

        self._engine: AsyncEngine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False, class_=AsyncSession)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    def session(self) -> AsyncSession:
        return self._sessionmaker()

    async def init_models(self) -> None:
        """Create tables if missing. Safe to call repeatedly."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        if self._settings.is_sqlite and self._settings.sqlite_path is not None:
            logger.info("SQLite ready at %s", self._settings.sqlite_path)
        else:
            logger.info("Database ready (%s)", self._settings.database_url.split("@")[-1])

    async def dispose(self) -> None:
        await self._engine.dispose()


_db: Database | None = None


def get_database() -> Database:
    """Return the process-wide Database instance."""
    global _db
    if _db is None:
        _db = Database(get_settings())
    return _db


def reset_database_for_tests(path: Path | None = None) -> None:
    """Test helper. Not used at runtime."""
    global _db
    _db = None
