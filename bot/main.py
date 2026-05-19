"""Bot entrypoint: wires aiogram, db, llm, queue, handlers, middleware."""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from bot.config import Settings, get_settings
from bot.db.database import Database, get_database
from bot.db.repository import Repository
from bot.handlers import (
    build_admin_router,
    build_inline_router,
    build_message_router,
    build_start_router,
)
from bot.llm.client import LLMClient, get_llm_client
from bot.logger import configure_logging, get_logger
from bot.memory.manager import MemoryManager
from bot.middleware import (
    PromptProtectionMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
)
from bot.personality.engine import PersonalityEngine
from bot.reply.context import ContextBuilder
from bot.reply.engine import ReplyEngine
from bot.reply.queue import MessageQueue


async def _main() -> None:
    settings: Settings = get_settings()
    configure_logging(settings.log_level, settings.log_dir_path)
    logger = get_logger("bot.main")
    logger.info(
        "starting tims-ai-assistant | model=%s | base=%s",
        settings.llm_model,
        settings.llm_base_url,
    )

    db: Database = get_database()
    await db.init_models()

    llm: LLMClient = get_llm_client()
    personality = PersonalityEngine()
    memory = MemoryManager(db, llm, settings)
    context_builder = ContextBuilder(db, memory, personality, settings)

    # Default to plain text. We don't format replies with HTML/Markdown, and
    # any stray '<', '>' or '&' in LLM output would otherwise crash Telegram's
    # parser and silently drop replies.
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=None),
    )
    me = await bot.get_me()
    logger.info("authenticated as @%s (id=%s)", me.username, me.id)

    reply_engine = ReplyEngine(
        bot=bot,
        db=db,
        llm=llm,
        memory=memory,
        context_builder=context_builder,
        settings=settings,
    )
    queue = MessageQueue(reply_engine.handle_batch, settings.reply_debounce_seconds)

    # Initialise global pause state if needed.
    async with db.session() as session:
        repo = Repository(session)
        if settings.start_paused and (await repo.get_state("paused")) != "1":
            await repo.set_state("paused", "1")
        await session.commit()

    dp = Dispatcher()
    # Order matters: protection first, then rate-limit, then logging.
    # All three middlewares operate on Message events specifically, so they
    # must be attached at the message router level (dp.update would deliver
    # raw Update objects and our isinstance(Message) checks would no-op).
    #
    # IMPORTANT: dp.message and dp.business_message are *independent*
    # observers in aiogram v3 — they do NOT share middleware. We register
    # the same chain on both so Telegram-Business contacts get the same
    # rate-limit / prompt-protection / logging treatment as DM contacts.
    # Forgetting business_message would mean unlimited LLM calls per
    # contact in business mode (no throttle).
    for observer in (dp.message, dp.business_message):
        observer.middleware(PromptProtectionMiddleware())
        observer.middleware(RateLimitMiddleware(db, settings))
        observer.middleware(RequestLoggingMiddleware())

    dp.include_router(build_admin_router(db=db, settings=settings))
    dp.include_router(build_start_router())
    dp.include_router(build_inline_router(llm=llm, settings=settings))
    dp.include_router(build_message_router(queue=queue, db=db, settings=settings))

    stop_event = asyncio.Event()

    def _request_stop(*_args: Any) -> None:
        if not stop_event.is_set():
            logger.info("shutdown signal received")
            stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows: fall back to default handler.
            signal.signal(sig, _request_stop)

    polling_task = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    )

    try:
        await stop_event.wait()
    finally:
        logger.info("stopping...")
        await dp.stop_polling()
        polling_task.cancel()
        try:
            await polling_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        await queue.shutdown()
        await bot.session.close()
        await db.dispose()
        logger.info("bye")


def run() -> None:
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    run()
