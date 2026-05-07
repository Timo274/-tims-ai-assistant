"""Extracts durable facts from a conversation snippet using the LLM."""

from __future__ import annotations

from typing import Any

from bot.config import Settings
from bot.db.models import Message
from bot.llm.client import LLMClient, LLMError
from bot.llm.prompts import MEMORY_EXTRACTION_PROMPT
from bot.logger import get_logger

logger = get_logger(__name__)

_VALID_KINDS = {"name", "fact", "preference", "relationship", "topic"}


class MemoryExtractor:
    def __init__(self, llm: LLMClient, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings

    async def extract(self, messages: list[Message]) -> list[dict[str, Any]]:
        if not messages:
            return []
        convo = self._format(messages)
        prompt = MEMORY_EXTRACTION_PROMPT.format(conversation=convo)
        try:
            data = await self._llm.chat_json(
                [
                    {"role": "system", "content": "You output strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model=self._settings.llm_summary_model,
                temperature=0.2,
            )
        except LLMError as exc:
            logger.warning("memory extraction failed: %s", exc)
            return []

        items: list[dict[str, Any]] = []
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict) and isinstance(data.get("memories"), list):
            raw_items = data["memories"]
        else:
            return []

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", "fact")).strip().lower()
            content = str(item.get("content", "")).strip()
            try:
                importance = int(item.get("importance", 5))
            except (TypeError, ValueError):
                importance = 5
            importance = max(1, min(10, importance))
            if not content or len(content) > 280:
                continue
            if kind not in _VALID_KINDS:
                kind = "fact"
            items.append({"kind": kind, "content": content, "importance": importance})
        return items

    @staticmethod
    def _format(messages: list[Message]) -> str:
        lines: list[str] = []
        for m in messages:
            who = "user" if m.role == "user" else "you"
            content = m.content.strip().replace("\n", " ")
            if len(content) > 600:
                content = content[:597] + "..."
            lines.append(f"[{who}] {content}")
        return "\n".join(lines)
