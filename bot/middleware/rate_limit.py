"""Sliding-window rate limiter backed by the database."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser

from bot.config import Settings
from bot.db.database import Database
from bot.db.repository import Repository
from bot.logger import get_logger

logger = get_logger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, db: Database, settings: Settings) -> None:
        self._db = db
        self._settings = settings
        self._purge_lock = asyncio.Lock()
        self._purge_counter = 0

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user: TgUser | None = data.get("event_from_user")
        if from_user is None or from_user.is_bot:
            return await handler(event, data)

        async with self._db.session() as session:
            repo = Repository(session)
            count = await repo.count_rate_limit_events(
                from_user.id, self._settings.rate_limit_window_seconds
            )
            if count >= self._settings.rate_limit_messages:
                logger.warning(
                    "rate-limit hit for user=%s (%d/%d in %ss)",
                    from_user.id,
                    count,
                    self._settings.rate_limit_messages,
                    self._settings.rate_limit_window_seconds,
                )
                return  # silently drop — never tell users they're being rate-limited
            await repo.add_rate_limit_event(from_user.id)
            await session.commit()

        # Periodic purge of old events.
        self._purge_counter += 1
        if self._purge_counter >= 50:
            self._purge_counter = 0
            asyncio.create_task(self._purge_old())

        return await handler(event, data)

    async def _purge_old(self) -> None:
        if self._purge_lock.locked():
            return
        async with self._purge_lock:
            try:
                async with self._db.session() as session:
                    repo = Repository(session)
                    await repo.purge_old_rate_limit_events(retention_seconds=3600)
                    await session.commit()
            except Exception:  # noqa: BLE001
                logger.exception("rate-limit purge failed")
