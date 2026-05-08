"""Reply engine: takes a batch of incoming messages and produces+sends replies."""

from __future__ import annotations

import asyncio
import random

from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from bot.config import Settings
from bot.db.database import Database
from bot.db.repository import Repository
from bot.llm.client import LLMClient, LLMError
from bot.logger import get_logger
from bot.memory.manager import MemoryManager
from bot.middleware.prompt_protection import sanitize_user_text
from bot.personality.style import polish
from bot.reply.context import ContextBuilder
from bot.reply.queue import QueuedMessage
from bot.utils.timing import estimate_typing_delay, sleep_jitter

logger = get_logger(__name__)


class ReplyEngine:
    def __init__(
        self,
        *,
        bot: Bot,
        db: Database,
        llm: LLMClient,
        memory: MemoryManager,
        context_builder: ContextBuilder,
        settings: Settings,
    ) -> None:
        self._bot = bot
        self._db = db
        self._llm = llm
        self._memory = memory
        self._context = context_builder
        self._settings = settings

    async def handle_batch(self, chat_id: int, messages: list[QueuedMessage]) -> None:
        if not messages:
            return
        user_id = messages[0].user_id
        # All messages in a batch share the same (chat_id, user_id) and so
        # must share the same business connection (it's keyed off chat).
        business_connection_id = messages[0].business_connection_id
        # In business mode the chat is a 1:1 between owner and contact,
        # so a chat_id != user_id discrepancy doesn't mean "group".
        is_group_chat = (business_connection_id is None) and (chat_id != user_id)

        # Skip groups unless explicitly enabled.
        if is_group_chat and not self._settings.reply_in_groups:
            return

        # Load user + persistence state.
        async with self._db.session() as session:
            repo = Repository(session)
            user = await repo.get_user(user_id)
            if user is None or user.is_blocked:
                return
            if user.paused:
                return
            global_paused = await repo.get_state("paused")
            if global_paused == "1":
                return

        merged_text = self._merge_user_text([m.text for m in messages])
        sanitized_text = sanitize_user_text(merged_text)

        # Persist user message(s) before generating a reply.
        async with self._db.session() as session:
            repo = Repository(session)
            for m in messages:
                clean = sanitize_user_text(m.text)
                await repo.add_message(user_id=user.id, role="user", content=clean)
            await session.commit()

        # Build LLM context. We persisted the user message above, so
        # ContextBuilder.recent_messages() already includes the freshest user
        # turn — do NOT append it a second time or the model sees the message
        # twice and quality suffers.
        try:
            llm_messages, tone, memory_ids = await self._context.build(
                user=user,
                incoming_text=sanitized_text,
                is_group_chat=is_group_chat,
                current_batch_count=len(messages),
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to build context for user=%s", user.id)
            return

        # Variable, pre-typing pause so the bot doesn't reply microseconds
        # after the message arrives.
        await sleep_jitter(random.uniform(0.4, 1.4))

        try:
            await self._bot.send_chat_action(
                chat_id,
                ChatAction.TYPING,
                business_connection_id=business_connection_id,
            )
        except (TelegramForbiddenError, TelegramRetryAfter):
            return
        except Exception:  # noqa: BLE001
            pass

        try:
            raw = await self._llm.chat(llm_messages)
        except LLMError as exc:
            logger.error("LLM failed for user=%s: %s", user.id, exc)
            return

        reply = polish(raw, contact_id=user.id)
        if not reply:
            logger.info("empty reply for user=%s, skipping", user.id)
            return

        # Telegram caps single messages at 4096 chars; with LLM_MAX_TOKENS=400
        # we never come close, but truncate defensively anyway.
        if len(reply) > 4000:
            reply = reply[:4000].rstrip()

        delay = estimate_typing_delay(
            reply,
            per_char=self._settings.typing_delay_per_char,
            minimum=self._settings.typing_delay_min,
            maximum=self._settings.typing_delay_max,
        )
        await sleep_jitter(delay)

        try:
            await self._bot.send_message(
                chat_id,
                reply,
                disable_web_page_preview=True,
                business_connection_id=business_connection_id,
            )
        except TelegramForbiddenError:
            logger.info("user=%s blocked the bot", user.id)
            async with self._db.session() as session:
                repo = Repository(session)
                await repo.set_blocked(user.id, True)
                await session.commit()
            return
        except TelegramRetryAfter as exc:
            logger.warning("retry after %s seconds, dropping reply", exc.retry_after)
            return
        except Exception:  # noqa: BLE001
            logger.exception("failed to send reply to user=%s", user.id)
            return

        async with self._db.session() as session:
            repo = Repository(session)
            await repo.add_message(user_id=user.id, role="assistant", content=reply)
            await session.commit()
        await self._memory.mark_used(memory_ids)

        # Background tasks: extract memories + maybe summarise.
        asyncio.create_task(self._post_reply_jobs(user.id))

        logger.info(
            "replied user=%s tone=%s in_msgs=%d out_chars=%d mem=%d",
            user.id,
            tone.label,
            len(messages),
            len(reply),
            len(memory_ids),
        )

    async def _post_reply_jobs(self, user_id: int) -> None:
        try:
            async with self._db.session() as session:
                repo = Repository(session)
                recent = await repo.recent_messages(user_id, limit=8)
            await self._memory.extract_and_store(user_id=user_id, recent_messages=recent)
            await self._memory.maybe_summarise(user_id)
        except Exception:  # noqa: BLE001
            logger.exception("post-reply job failed for user=%s", user_id)

    @staticmethod
    def _merge_user_text(parts: list[str]) -> str:
        cleaned = [p.strip() for p in parts if p and p.strip()]
        return "\n".join(cleaned)
