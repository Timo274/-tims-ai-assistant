"""Builds the message list passed to the LLM."""

from __future__ import annotations

from bot.config import Settings
from bot.db.database import Database
from bot.db.models import User
from bot.db.repository import Repository
from bot.llm.prompts import build_system_prompt
from bot.memory.manager import MemoryManager
from bot.personality.engine import PersonalityEngine, ToneProfile


class ContextBuilder:
    def __init__(
        self,
        db: Database,
        memory: MemoryManager,
        personality: PersonalityEngine,
        settings: Settings,
    ) -> None:
        self._db = db
        self._memory = memory
        self._personality = personality
        self._settings = settings

    async def build(
        self,
        *,
        user: User,
        incoming_text: str,
        is_group_chat: bool,
    ) -> tuple[list[dict[str, str]], ToneProfile, list[int]]:
        """Return (messages, tone, used_memory_ids)."""
        tone = self._personality.detect_tone(incoming_text)

        memories, summary = await self._memory.retrieve(
            user_id=user.id,
            focus_text=incoming_text,
        )
        memory_lines = [f"({m.kind}, w={m.importance}) {m.content}" for m in memories]
        memory_ids = [m.id for m in memories]

        async with self._db.session() as session:
            repo = Repository(session)
            recent = await repo.recent_messages(
                user_id=user.id,
                limit=self._settings.context_recent_messages,
            )

        system_prompt = build_system_prompt(
            persona_name=self._settings.bot_persona_name,
            user_display_name=user.display_name,
            is_group_chat=is_group_chat,
            detected_tone=tone.hint,
            long_term_summary=summary.content if summary else None,
            relevant_memories=memory_lines,
        )

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for m in recent:
            if m.role not in {"user", "assistant"}:
                continue
            messages.append({"role": m.role, "content": m.content})
        # The current incoming text is appended by the caller (queue may have
        # batched several user messages — caller decides how to merge them).

        return messages, tone, memory_ids
