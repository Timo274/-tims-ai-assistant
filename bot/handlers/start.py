"""/start and /help — kept intentionally minimal so the bot doesn't sound
like a scripted FAQ assistant."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.logger import get_logger

logger = get_logger(__name__)


def build_start_router() -> Router:
    router = Router(name="start")

    @router.message(Command("start"))
    async def on_start(message: Message) -> None:
        # Don't sound like a "Welcome to FooBot v1.0!" template.
        await message.answer("ну хай")

    @router.message(Command("help"))
    async def on_help(message: Message) -> None:
        await message.answer("просто пиши мне как обычному человеку, я отвечу")

    @router.message(F.text == "/about")
    async def on_about(message: Message) -> None:
        await message.answer("личный чат, без подробностей")

    return router
