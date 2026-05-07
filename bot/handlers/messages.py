"""Catch-all message handler that funnels real conversation through the
reply engine via the debounce queue."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from bot.config import Settings
from bot.db.database import Database
from bot.db.repository import Repository
from bot.logger import get_logger
from bot.reply.queue import MessageQueue, QueuedMessage

logger = get_logger(__name__)


def build_message_router(
    *,
    queue: MessageQueue,
    db: Database,
    settings: Settings,
) -> Router:
    router = Router(name="messages")

    @router.message(F.text & ~F.text.startswith("/"))
    async def on_text(message: Message) -> None:
        await _handle(message, queue=queue, db=db, settings=settings)

    @router.message(F.caption & ~F.caption.startswith("/"))
    async def on_caption(message: Message) -> None:
        await _handle(message, queue=queue, db=db, settings=settings, use_caption=True)

    return router


async def _handle(
    message: Message,
    *,
    queue: MessageQueue,
    db: Database,
    settings: Settings,
    use_caption: bool = False,
) -> None:
    if message.from_user is None or message.from_user.is_bot:
        return

    chat_type = message.chat.type
    is_dm = chat_type == ChatType.PRIVATE
    is_group = chat_type in {ChatType.GROUP, ChatType.SUPERGROUP}
    if not is_dm and not (settings.reply_in_groups and is_group):
        return

    text = message.caption if use_caption else message.text
    if not text:
        return

    # Upsert the user first so paused/blocked checks downstream are valid.
    async with db.session() as session:
        repo = Repository(session)
        await repo.upsert_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=message.from_user.language_code,
            is_admin=message.from_user.id in settings.admin_ids,
        )
        await session.commit()

    await queue.push(
        QueuedMessage(
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            message_id=message.message_id,
            text=text,
        )
    )
