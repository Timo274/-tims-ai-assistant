"""Logs every incoming Telegram update at DEBUG level."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from bot.logger import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            user = event.from_user
            user_id = user.id if user else "?"
            text = (event.text or event.caption or "").replace("\n", " ")
            if len(text) > 200:
                text = text[:197] + "..."
            logger.info(
                "msg chat=%s user=%s len=%d text=%r",
                event.chat.id,
                user_id,
                len(event.text or event.caption or ""),
                text,
            )
        return await handler(event, data)
