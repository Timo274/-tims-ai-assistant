"""High-level orchestration of memory: extracts on the fly, retrieves
relevant snippets at reply time, and triggers long-term summarisation when
history grows too large."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from bot.config import Settings
from bot.db.database import Database
from bot.db.models import Memory, Message, Summary
from bot.db.repository import Repository
from bot.llm.client import LLMClient
from bot.logger import get_logger
from bot.memory.extractor import MemoryExtractor
from bot.memory.summarizer import ConversationSummarizer

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[\wа-яёіїєґА-ЯЁІЇЄҐ]+", re.UNICODE)


def _tokenise(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) >= 3}


class MemoryManager:
    """Owns all memory side effects."""

    def __init__(self, db: Database, llm: LLMClient, settings: Settings) -> None:
        self._db = db
        self._llm = llm
        self._settings = settings
        self._extractor = MemoryExtractor(llm, settings)
        self._summarizer = ConversationSummarizer(llm, settings)

    # ----- retrieve --------------------------------------------------------
    async def retrieve(
        self,
        *,
        user_id: int,
        focus_text: str,
        top_k: int | None = None,
    ) -> tuple[list[Memory], Summary | None]:
        """Pick the top-k most relevant memories + the latest summary."""
        top_k = top_k or self._settings.memory_top_k
        async with self._db.session() as session:
            repo = Repository(session)
            all_memories = await repo.list_memories(user_id, limit=200)
            summary = await repo.latest_summary(user_id)

        if not all_memories:
            return [], summary

        focus_tokens = _tokenise(focus_text)

        def score(m: Memory) -> float:
            mem_tokens = _tokenise(m.content)
            overlap = len(focus_tokens & mem_tokens)
            base = m.importance / 2.0
            return base + overlap * 1.5 + (1.5 if m.kind == "name" else 0.0)

        ranked = sorted(all_memories, key=score, reverse=True)
        return ranked[:top_k], summary

    async def mark_used(self, memory_ids: list[int]) -> None:
        if not memory_ids:
            return
        async with self._db.session() as session:
            repo = Repository(session)
            await repo.touch_memories(memory_ids)
            await session.commit()

    # ----- extract ---------------------------------------------------------
    async def extract_and_store(self, *, user_id: int, recent_messages: list[Message]) -> int:
        """Run after a reply. Extracts new memories from the recent exchange."""
        if len(recent_messages) < 2:
            return 0
        items = await self._extractor.extract(recent_messages)
        if not items:
            return 0
        async with self._db.session() as session:
            repo = Repository(session)
            created = await repo.add_memories(user_id, items)
            await session.commit()
        if created:
            logger.info("user=%s stored %d new memories", user_id, len(created))
        return len(created)

    # ----- summarise -------------------------------------------------------
    async def maybe_summarise(self, user_id: int) -> Summary | None:
        """If history is too long, fold the oldest half into a summary."""
        threshold = self._settings.summarise_after_messages
        keep_recent = self._settings.context_recent_messages

        async with self._db.session() as session:
            repo = Repository(session)
            total = await repo.messages_count(user_id)
            if total < threshold:
                return None

            # The cutoff is: keep the last `keep_recent` messages verbatim,
            # summarise everything older.
            recent = await repo.recent_messages(user_id, limit=keep_recent)
            if not recent:
                return None
            oldest_recent = min(m.created_at for m in recent)
            cutoff = oldest_recent
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=timezone.utc)

            old_messages = await repo.messages_older_than(user_id, cutoff)
            if not old_messages:
                return None
            previous = await repo.latest_summary(user_id)

        result = await self._summarizer.summarise(old_messages, previous)
        if result is None:
            return None
        text, covers_until = result

        async with self._db.session() as session:
            repo = Repository(session)
            summary = await repo.add_summary(
                user_id=user_id,
                content=text,
                covers_until=covers_until,
            )
            # Drop the now-summarised raw messages to keep storage bounded.
            # Use `cutoff` (the boundary between old and recent) rather than
            # `covers_until` (== max old message timestamp). The repo deletes
            # with strict `<`, so passing `covers_until` would leave the
            # newest already-summarised row behind every cycle and re-feed
            # it into the next summary.
            await repo.delete_messages_older_than(user_id, cutoff)
            await session.commit()
        logger.info(
            "user=%s summarised %d old messages into %d-char summary",
            user_id,
            len(old_messages),
            len(text),
        )
        return summary
