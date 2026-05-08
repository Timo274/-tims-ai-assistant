"""Inline-mode handler: when someone types `@<bot_username> <query>` in
any chat, Telegram sends us an InlineQuery and we return one or more
`InlineQueryResultArticle`s. Picking a result causes the *user* to send
the article's text into the chat.

This is intentionally separate from the autopilot persona — when the bot
is invoked inline it acts as a regular chatbot assistant, not as Tim. We
keep the wording neutral, mirror the language of the query, and keep
answers short.
"""

from __future__ import annotations

import hashlib
from uuid import uuid4

from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from bot.llm.client import LLMClient, LLMError
from bot.llm.prompts import INLINE_QUERY_PROMPT
from bot.logger import get_logger

logger = get_logger(__name__)

# Telegram caches inline results by (query, chat_type, etc.) for this many
# seconds — set short so retried queries don't return stale answers.
_CACHE_SECONDS = 5


def _result_id(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8", errors="ignore")).hexdigest()[:32] or uuid4().hex


def build_inline_router(*, llm: LLMClient) -> Router:
    router = Router(name="inline")

    @router.inline_query()
    async def on_inline(inline_query: InlineQuery) -> None:
        query = (inline_query.query or "").strip()
        if not query:
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=uuid4().hex,
                        title="напиши вопрос после @bot",
                        description="например: @timsAiAssistent_bot как обновить usdt в trust wallet",
                        input_message_content=InputTextMessageContent(
                            message_text="(пустой запрос)"
                        ),
                    )
                ],
                cache_time=_CACHE_SECONDS,
                is_personal=True,
            )
            return

        try:
            answer = await llm.chat(
                [
                    {"role": "system", "content": INLINE_QUERY_PROMPT},
                    {"role": "user", "content": query},
                ],
                max_tokens=300,
            )
        except LLMError as exc:
            logger.error("inline LLM failed: %s", exc)
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=uuid4().hex,
                        title="не получилось дотянуться до модели",
                        description=str(exc)[:140],
                        input_message_content=InputTextMessageContent(
                            message_text=f"(модель недоступна: {exc})"
                        ),
                    )
                ],
                cache_time=_CACHE_SECONDS,
                is_personal=True,
            )
            return

        answer = (answer or "").strip()
        if not answer:
            answer = "не нашёл нормального ответа"

        # Single result: short preview as title (Telegram caps at ~64 chars
        # for the title, ~256 for description) + full text in the message.
        title = answer.split("\n", 1)[0][:64].strip() or "ответ"
        description = answer[:256].strip()

        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id=_result_id(query),
                    title=title,
                    description=description,
                    input_message_content=InputTextMessageContent(
                        message_text=answer,
                        disable_web_page_preview=True,
                    ),
                )
            ],
            cache_time=_CACHE_SECONDS,
            is_personal=True,
        )

    return router
