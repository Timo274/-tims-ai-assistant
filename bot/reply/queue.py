"""Per-user debouncing message queue.

People often fire 3-4 short messages in a row. Replying to each one separately
feels robotic. The queue collects rapid-fire messages from the same user and
hands them off as a single batch once they pause typing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from bot.logger import get_logger

logger = get_logger(__name__)


@dataclass
class QueuedMessage:
    chat_id: int
    user_id: int
    message_id: int
    text: str
    # Set when this message arrived via Telegram Business (the bot is
    # connected to the owner's account and is replying on their behalf).
    # The reply must be sent through the same connection so it appears
    # to come from the owner, not from @<bot>.
    business_connection_id: str | None = None


@dataclass
class _Bucket:
    messages: list[QueuedMessage] = field(default_factory=list)
    flush_handle: asyncio.TimerHandle | None = None
    in_flight_task: asyncio.Task | None = None


Handler = Callable[[int, list[QueuedMessage]], Awaitable[None]]


class MessageQueue:
    """Async per-(chat,user) debounce queue."""

    def __init__(self, handler: Handler, debounce_seconds: float) -> None:
        self._handler = handler
        self._debounce = max(0.1, float(debounce_seconds))
        self._buckets: dict[tuple[int, int], _Bucket] = {}
        self._lock = asyncio.Lock()

    async def push(self, msg: QueuedMessage) -> None:
        key = (msg.chat_id, msg.user_id)
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket()
                self._buckets[key] = bucket
            bucket.messages.append(msg)
            if bucket.flush_handle is not None:
                bucket.flush_handle.cancel()
            loop = asyncio.get_running_loop()
            bucket.flush_handle = loop.call_later(self._debounce, self._schedule_flush, key)

    def _schedule_flush(self, key: tuple[int, int]) -> None:
        bucket = self._buckets.get(key)
        if bucket is None or not bucket.messages:
            return
        if bucket.in_flight_task is not None and not bucket.in_flight_task.done():
            # Already replying — re-arm a flush for any new messages that
            # arrived during generation.
            loop = asyncio.get_running_loop()
            bucket.flush_handle = loop.call_later(self._debounce, self._schedule_flush, key)
            return
        bucket.in_flight_task = asyncio.create_task(self._flush(key))

    async def _flush(self, key: tuple[int, int]) -> None:
        bucket = self._buckets.get(key)
        if bucket is None:
            return
        async with self._lock:
            messages = bucket.messages
            bucket.messages = []
            bucket.flush_handle = None
        if not messages:
            return
        try:
            await self._handler(key[0], messages)
        except Exception:  # noqa: BLE001
            logger.exception("reply handler failed for key=%s", key)
        finally:
            async with self._lock:
                bucket = self._buckets.get(key)
                if bucket is None:
                    return
                bucket.in_flight_task = None
                if bucket.messages:
                    # Messages arrived during reply — schedule another flush.
                    loop = asyncio.get_running_loop()
                    bucket.flush_handle = loop.call_later(self._debounce, self._schedule_flush, key)

    async def shutdown(self) -> None:
        """Cancel pending flushes and wait for in-flight handlers."""
        async with self._lock:
            tasks: list[asyncio.Task] = []
            for bucket in self._buckets.values():
                if bucket.flush_handle is not None:
                    bucket.flush_handle.cancel()
                    bucket.flush_handle = None
                if bucket.in_flight_task is not None and not bucket.in_flight_task.done():
                    tasks.append(bucket.in_flight_task)
        for task in tasks:
            try:
                await asyncio.wait_for(task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
