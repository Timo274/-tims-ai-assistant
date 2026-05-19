"""Defends against prompt-injection attempts.

Two layers:
  1. `sanitize_user_text` — neutralises in-message instructions that try to
     override the system prompt (jailbreak / "ignore previous", etc).
  2. `PromptProtectionMiddleware` — drops oversized messages before they ever
     reach the LLM.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from bot.logger import get_logger

logger = get_logger(__name__)

_MAX_MESSAGE_CHARS = 4000

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (?:all )?(?:previous|above|prior) (?:instructions|messages|prompts?)",
        r"disregard (?:all )?(?:previous|above|prior)",
        r"забудь (?:все|предыдущ|вс[её])",
        r"забудь (?:все|попередн|свої) інструкції",
        r"system prompt",
        r"system:?\s*you are",
        r"you are now (?:a|an) ",
        r"act as (?:a|an) ",
        r"jailbreak",
        r"developer mode",
        r"reveal (?:your )?(?:system )?prompt",
        r"покажи (?:свой )?(?:системный )?промпт",
        r"show (?:your )?(?:system )?prompt",
    )
)


def sanitize_user_text(text: str) -> str:
    """Defang obvious prompt-injection attempts so they can't override the
    system prompt. We don't reject the message — we just transform it so the
    model treats it as ordinary user content."""
    if not text:
        return ""
    cleaned = text
    if len(cleaned) > _MAX_MESSAGE_CHARS:
        cleaned = cleaned[:_MAX_MESSAGE_CHARS] + " […]"
    # Strip role-style markers users sometimes paste in.
    cleaned = re.sub(r"^\s*(system|assistant|user)\s*[:>]\s*", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub("[…]", cleaned)
    return cleaned.strip()


class PromptProtectionMiddleware(BaseMiddleware):
    """Drops obviously hostile / oversized payloads before any LLM call."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            text = event.text or event.caption or ""
            if len(text) > _MAX_MESSAGE_CHARS * 2:
                logger.warning(
                    "dropping oversize message: chat=%s len=%d",
                    event.chat.id,
                    len(text),
                )
                return  # silently drop
        return await handler(event, data)
