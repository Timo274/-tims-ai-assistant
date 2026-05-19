"""High-level data-access layer used by the rest of the bot."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import BotState, Memory, Message, RateLimitEvent, Summary, User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Repository:
    """All DB access is funnelled through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ----- users -----------------------------------------------------------
    async def upsert_user(
        self,
        *,
        user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
        is_admin: bool = False,
    ) -> User:
        user = await self.session.get(User, user_id)
        if user is None:
            user = User(
                id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=language_code,
                is_admin=is_admin,
            )
            self.session.add(user)
        else:
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.language_code = language_code
            user.last_seen_at = _utcnow()
            if is_admin and not user.is_admin:
                user.is_admin = True
        await self.session.flush()
        return user

    async def get_user(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def set_paused(self, user_id: int, paused: bool) -> None:
        user = await self.session.get(User, user_id)
        if user is not None:
            user.paused = paused

    async def set_blocked(self, user_id: int, blocked: bool) -> None:
        user = await self.session.get(User, user_id)
        if user is not None:
            user.is_blocked = blocked

    async def list_users(self, limit: int = 50) -> list[User]:
        stmt = select(User).order_by(User.last_seen_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    # ----- messages --------------------------------------------------------
    async def add_message(
        self,
        *,
        user_id: int,
        role: str,
        content: str,
        tokens: int = 0,
    ) -> Message:
        msg = Message(user_id=user_id, role=role, content=content, tokens=tokens)
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def recent_messages(self, user_id: int, limit: int = 20) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        rows.reverse()
        return rows

    async def messages_count(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(Message).where(Message.user_id == user_id)
        return int((await self.session.execute(stmt)).scalar_one())

    async def messages_older_than(self, user_id: int, cutoff: datetime) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.user_id == user_id, Message.created_at < cutoff)
            .order_by(Message.created_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete_messages_older_than(self, user_id: int, cutoff: datetime) -> int:
        stmt = delete(Message).where(Message.user_id == user_id, Message.created_at < cutoff)
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    async def delete_user_messages(self, user_id: int) -> None:
        await self.session.execute(delete(Message).where(Message.user_id == user_id))

    # ----- memories --------------------------------------------------------
    async def add_memory(
        self,
        *,
        user_id: int,
        kind: str,
        content: str,
        importance: int = 5,
    ) -> Memory:
        mem = Memory(user_id=user_id, kind=kind, content=content, importance=importance)
        self.session.add(mem)
        await self.session.flush()
        return mem

    async def add_memories(
        self,
        user_id: int,
        items: Iterable[dict[str, Any]],
    ) -> list[Memory]:
        created: list[Memory] = []
        existing = {m.content.strip().lower() for m in await self.list_memories(user_id, limit=500)}
        for item in items:
            content = str(item.get("content", "")).strip()
            if not content or content.lower() in existing:
                continue
            kind = str(item.get("kind", "fact")).strip() or "fact"
            importance = int(item.get("importance", 5) or 5)
            importance = max(1, min(10, importance))
            mem = Memory(user_id=user_id, kind=kind, content=content, importance=importance)
            self.session.add(mem)
            created.append(mem)
            existing.add(content.lower())
        if created:
            await self.session.flush()
        return created

    async def list_memories(self, user_id: int, limit: int = 100) -> list[Memory]:
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(Memory.importance.desc(), Memory.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def touch_memories(self, memory_ids: Iterable[int]) -> None:
        ids = list(memory_ids)
        if not ids:
            return
        now = _utcnow()
        for memory_id in ids:
            mem = await self.session.get(Memory, memory_id)
            if mem is not None:
                mem.last_used_at = now

    async def delete_user_memories(self, user_id: int) -> None:
        await self.session.execute(delete(Memory).where(Memory.user_id == user_id))

    # ----- summaries -------------------------------------------------------
    async def add_summary(self, *, user_id: int, content: str, covers_until: datetime) -> Summary:
        s = Summary(user_id=user_id, content=content, covers_until=covers_until)
        self.session.add(s)
        await self.session.flush()
        return s

    async def latest_summary(self, user_id: int) -> Summary | None:
        stmt = (
            select(Summary)
            .where(Summary.user_id == user_id)
            .order_by(Summary.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def all_summaries(self, user_id: int) -> list[Summary]:
        stmt = (
            select(Summary)
            .where(Summary.user_id == user_id)
            .order_by(Summary.created_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete_user_summaries(self, user_id: int) -> None:
        await self.session.execute(delete(Summary).where(Summary.user_id == user_id))

    # ----- rate limit ------------------------------------------------------
    async def add_rate_limit_event(self, user_id: int) -> None:
        self.session.add(RateLimitEvent(user_id=user_id))
        await self.session.flush()

    async def count_rate_limit_events(self, user_id: int, window_seconds: int) -> int:
        cutoff = _utcnow() - timedelta(seconds=window_seconds)
        stmt = (
            select(func.count())
            .select_from(RateLimitEvent)
            .where(
                RateLimitEvent.user_id == user_id,
                RateLimitEvent.created_at >= cutoff,
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def purge_old_rate_limit_events(self, retention_seconds: int = 3600) -> int:
        cutoff = _utcnow() - timedelta(seconds=retention_seconds)
        stmt = delete(RateLimitEvent).where(RateLimitEvent.created_at < cutoff)
        result = await self.session.execute(stmt)
        return int(result.rowcount or 0)

    # ----- bot state -------------------------------------------------------
    async def get_state(self, key: str) -> str | None:
        s = await self.session.get(BotState, key)
        return s.value if s else None

    async def set_state(self, key: str, value: str) -> None:
        s = await self.session.get(BotState, key)
        if s is None:
            self.session.add(BotState(key=key, value=value))
        else:
            s.value = value
            s.updated_at = _utcnow()
