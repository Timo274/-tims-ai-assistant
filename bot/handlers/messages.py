"""Catch-all message handler that funnels real conversation through the
reply engine via the debounce queue.

The same handlers are wired on TWO event observers:
  * `router.message`           — normal DM / group bot messaging.
  * `router.business_message`  — Telegram Business mode where the bot
    is connected to the owner's premium account and replies on their
    behalf in their own private chats. In that mode the reply must be
    sent back with the matching `business_connection_id` so it appears
    to come from the owner, not from @<bot>.
"""

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
    _register_content_handlers(router.message, queue=queue, db=db, settings=settings)
    _register_content_handlers(
        router.business_message, queue=queue, db=db, settings=settings
    )

    # Log when the owner enables/disables Telegram Business connection so
    # that we have a clear breadcrumb in production logs.
    @router.business_connection()
    async def on_business_connection(connection) -> None:  # type: ignore[no-untyped-def]
        is_enabled = bool(getattr(connection, "is_enabled", False))
        user = getattr(connection, "user", None)
        user_id = getattr(user, "id", None) if user else None
        logger.info(
            "business connection %s | id=%s owner=%s can_reply=%s",
            "enabled" if is_enabled else "disabled",
            getattr(connection, "id", None),
            user_id,
            getattr(connection, "can_reply", None),
        )

    return router


def _register_content_handlers(
    observer,
    *,
    queue: MessageQueue,
    db: Database,
    settings: Settings,
) -> None:
    @observer(F.text & ~F.text.startswith("/"))
    async def on_text(message: Message) -> None:
        await _handle(message, queue=queue, db=db, settings=settings)

    @observer(F.caption & ~F.caption.startswith("/"))
    async def on_caption(message: Message) -> None:
        await _handle(message, queue=queue, db=db, settings=settings, use_caption=True)

    # Stickers, voice notes, and bare media (photo / video / animation /
    # video_note / audio / document) all get a synthesized text
    # representation so the LLM can react like a real person would (e.g.
    # "хах жесть" —> sticker pack name).
    @observer(F.sticker)
    async def on_sticker(message: Message) -> None:
        s = message.sticker
        emoji = (s.emoji if s and s.emoji else "").strip()
        pack = (s.set_name if s and s.set_name else "").strip()
        bits = ["[sticker]"]
        if emoji:
            bits.append(emoji)
        if pack:
            bits.append(f"({pack})")
        await _handle(
            message, queue=queue, db=db, settings=settings, override_text=" ".join(bits)
        )

    @observer(F.voice)
    async def on_voice(message: Message) -> None:
        await _handle(
            message, queue=queue, db=db, settings=settings, override_text="[voice message]"
        )

    @observer(F.video_note)
    async def on_video_note(message: Message) -> None:
        await _handle(
            message,
            queue=queue,
            db=db,
            settings=settings,
            override_text="[video circle]",
        )

    @observer(F.photo)
    async def on_photo_no_caption(message: Message) -> None:
        if message.caption:
            return  # already handled by on_caption
        await _handle(
            message, queue=queue, db=db, settings=settings, override_text="[photo]"
        )

    @observer(F.video)
    async def on_video_no_caption(message: Message) -> None:
        if message.caption:
            return
        await _handle(
            message, queue=queue, db=db, settings=settings, override_text="[video]"
        )

    @observer(F.animation)
    async def on_animation(message: Message) -> None:
        if message.caption:
            return
        await _handle(
            message, queue=queue, db=db, settings=settings, override_text="[gif]"
        )


async def _handle(
    message: Message,
    *,
    queue: MessageQueue,
    db: Database,
    settings: Settings,
    use_caption: bool = False,
    override_text: str | None = None,
) -> None:
    if message.from_user is None or message.from_user.is_bot:
        return

    business_connection_id = getattr(message, "business_connection_id", None)
    is_business = business_connection_id is not None

    # In Telegram Business mode the bot also receives the OWNER's own
    # outgoing messages (when the owner replies manually to someone in
    # their own chats). We must never auto-reply to those — otherwise the
    # bot would generate replies to its own owner's typing. Heuristic:
    # any admin user (the owner is in admin_ids) is treated as the
    # account holder.
    if is_business and message.from_user.id in settings.admin_ids:
        return

    chat_type = message.chat.type
    is_dm = chat_type == ChatType.PRIVATE
    is_group = chat_type in {ChatType.GROUP, ChatType.SUPERGROUP}
    if not is_dm and not (settings.reply_in_groups and is_group):
        return

    if override_text is not None:
        text = override_text
    elif use_caption:
        text = message.caption
    else:
        text = message.text
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
            business_connection_id=business_connection_id,
        )
    )
