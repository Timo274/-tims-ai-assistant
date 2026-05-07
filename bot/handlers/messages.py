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

    # Stickers, voice notes, and bare media (photo / video / animation /
    # video_note / audio / document) all get a synthesized text
    # representation so the LLM can react like a real person would (e.g.
    # "хах жесть" —> sticker pack name).
    @router.message(F.sticker)
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

    @router.message(F.voice)
    async def on_voice(message: Message) -> None:
        await _handle(
            message, queue=queue, db=db, settings=settings, override_text="[voice message]"
        )

    @router.message(F.video_note)
    async def on_video_note(message: Message) -> None:
        await _handle(
            message,
            queue=queue,
            db=db,
            settings=settings,
            override_text="[video circle]",
        )

    @router.message(F.photo)
    async def on_photo_no_caption(message: Message) -> None:
        if message.caption:
            return  # already handled by on_caption
        await _handle(
            message, queue=queue, db=db, settings=settings, override_text="[photo]"
        )

    @router.message(F.video)
    async def on_video_no_caption(message: Message) -> None:
        if message.caption:
            return
        await _handle(
            message, queue=queue, db=db, settings=settings, override_text="[video]"
        )

    @router.message(F.animation)
    async def on_animation(message: Message) -> None:
        if message.caption:
            return
        await _handle(
            message, queue=queue, db=db, settings=settings, override_text="[gif]"
        )

    return router


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
        )
    )
