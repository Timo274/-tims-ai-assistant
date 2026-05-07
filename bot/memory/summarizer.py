"""Compresses old conversation history into a long-term summary."""

from __future__ import annotations

from datetime import datetime, timezone

from bot.config import Settings
from bot.db.models import Message, Summary
from bot.llm.client import LLMClient, LLMError
from bot.llm.prompts import SUMMARY_PROMPT
from bot.logger import get_logger

logger = get_logger(__name__)


class ConversationSummarizer:
    def __init__(self, llm: LLMClient, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings

    async def summarise(
        self,
        messages: list[Message],
        previous_summary: Summary | None,
    ) -> tuple[str, datetime] | None:
        """Return (summary_text, covers_until) or None if nothing to summarise."""
        if not messages:
            return None

        convo = self._format(messages)
        prompt = SUMMARY_PROMPT.format(
            previous_summary=(previous_summary.content if previous_summary else "(none)"),
            conversation=convo,
        )
        try:
            text = await self._llm.chat(
                [
                    {"role": "system", "content": "You produce calm, factual summaries."},
                    {"role": "user", "content": prompt},
                ],
                model=self._settings.llm_summary_model,
                temperature=0.3,
                max_tokens=400,
            )
        except LLMError as exc:
            logger.warning("summary generation failed: %s", exc)
            return None

        text = text.strip()
        if not text:
            return None

        covers_until = max((m.created_at for m in messages), default=datetime.now(timezone.utc))
        if covers_until.tzinfo is None:
            covers_until = covers_until.replace(tzinfo=timezone.utc)
        return text, covers_until

    @staticmethod
    def _format(messages: list[Message]) -> str:
        lines: list[str] = []
        for m in messages:
            who = "user" if m.role == "user" else "you"
            content = m.content.strip().replace("\n", " ")
            if len(content) > 800:
                content = content[:797] + "..."
            lines.append(f"[{who}] {content}")
        return "\n".join(lines)
