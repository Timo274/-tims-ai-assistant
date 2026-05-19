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

import asyncio
import hashlib
from uuid import uuid4

from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from bot.config import Settings, get_settings
from bot.llm.client import LLMClient, LLMError
from bot.llm.prompts import INLINE_QUERY_PROMPT
from bot.logger import get_logger

logger = get_logger(__name__)

# Telegram drops the inline answer if the bot doesn't respond within
# roughly 10 seconds — after that the popup just stays empty for that
# specific query string and the user sees "nothing happens". We cap our
# end-to-end LLM call under that window so we always return *something*
# even if the model is slow / rate-limited.
_INLINE_TOTAL_TIMEOUT = 8.0

# Inline replies are short by design (1–3 sentences). Capping output
# tokens makes the model stream finish faster, which matters a lot under
# the tight Telegram window above.
_INLINE_MAX_TOKENS = 200

# Cache successful answers briefly so repeated identical queries from the
# same user don't re-hit the model. Errors / timeouts are NOT cached so
# the user can retry immediately.
_CACHE_SECONDS_OK = 30
_CACHE_SECONDS_ERROR = 0
_CACHE_SECONDS_EMPTY = 2


def _result_id(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8", errors="ignore")).hexdigest()[:32] or uuid4().hex


def build_inline_router(*, llm: LLMClient, settings: Settings | None = None) -> Router:
    router = Router(name="inline")
    cfg = settings or get_settings()

    @router.inline_query()
    async def on_inline(inline_query: InlineQuery) -> None:
        query = (inline_query.query or "").strip()
        if not query:
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=uuid4().hex,
                        title="напиши вопрос после @бота",
                        description="например: @timsAiAssistent_bot как обновить usdt в trust wallet",
                        input_message_content=InputTextMessageContent(
                            message_text="(пустой запрос)"
                        ),
                    )
                ],
                cache_time=_CACHE_SECONDS_EMPTY,
                is_personal=True,
            )
            return

        # Fast path: pin to the primary model only (skip fallback chain),
        # single attempt (no exponential-backoff retry loop), and a hard
        # asyncio timeout. Without this, the default chat() walks the
        # whole model chain with retries and can easily exceed Telegram's
        # ~10s inline-answer window → popup stays empty.
        try:
            answer = await asyncio.wait_for(
                llm.chat(
                    [
                        {"role": "system", "content": INLINE_QUERY_PROMPT},
                        {"role": "user", "content": query},
                    ],
                    model=cfg.llm_model,
                    max_tokens=_INLINE_MAX_TOKENS,
                    attempts=1,
                ),
                timeout=_INLINE_TOTAL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "inline LLM timed out after %.1fs (query=%r)",
                _INLINE_TOTAL_TIMEOUT,
                query[:80],
            )
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id=uuid4().hex,
                        title="модель не успела ответить",
                        description="попробуй ещё раз — иногда бесплатный лимит тормозит",
                        input_message_content=InputTextMessageContent(
                            message_text=f"(не успел ответить за {_INLINE_TOTAL_TIMEOUT:.0f}с, попробуй ещё раз)"
                        ),
                    )
                ],
                cache_time=_CACHE_SECONDS_ERROR,
                is_personal=True,
            )
            return
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
                cache_time=_CACHE_SECONDS_ERROR,
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
            cache_time=_CACHE_SECONDS_OK,
            is_personal=True,
        )

    return router
