"""Admin commands. Only users in ADMIN_IDS can run these."""

from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import func, select

from bot.config import Settings
from bot.db.database import Database
from bot.db.models import Memory, Message as DbMessage, Summary, User
from bot.db.repository import Repository
from bot.logger import get_logger

logger = get_logger(__name__)


def _is_admin(message: Message, settings: Settings) -> bool:
    return bool(message.from_user and message.from_user.id in settings.admin_ids)


def build_admin_router(*, db: Database, settings: Settings) -> Router:
    router = Router(name="admin")

    @router.message(Command("ping"))
    async def on_ping(message: Message) -> None:
        if not _is_admin(message, settings):
            return
        await message.answer("pong")

    @router.message(Command("stats"))
    async def on_stats(message: Message) -> None:
        if not _is_admin(message, settings):
            return
        async with db.session() as session:
            users_count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
            msgs_count = (await session.execute(select(func.count()).select_from(DbMessage))).scalar_one()
            mem_count = (await session.execute(select(func.count()).select_from(Memory))).scalar_one()
            sum_count = (await session.execute(select(func.count()).select_from(Summary))).scalar_one()
            paused_global = await Repository(session).get_state("paused")

        await message.answer(
            "stats:\n"
            f"users: {users_count}\n"
            f"messages: {msgs_count}\n"
            f"memories: {mem_count}\n"
            f"summaries: {sum_count}\n"
            f"global_paused: {paused_global == '1'}\n"
            f"model: {settings.llm_model} via {settings.llm_base_url}"
        )

    @router.message(Command("pause"))
    async def on_pause(message: Message) -> None:
        if not _is_admin(message, settings):
            return
        async with db.session() as session:
            repo = Repository(session)
            await repo.set_state("paused", "1")
            await session.commit()
        await message.answer("paused. бот молчит везде до /resume.")

    @router.message(Command("resume"))
    async def on_resume(message: Message) -> None:
        if not _is_admin(message, settings):
            return
        async with db.session() as session:
            repo = Repository(session)
            await repo.set_state("paused", "0")
            await session.commit()
        await message.answer("resumed.")

    @router.message(Command("memory"))
    async def on_memory(message: Message, command: CommandObject) -> None:
        if not _is_admin(message, settings):
            return
        target_id = _parse_user_id(command.args) or (message.from_user.id if message.from_user else None)
        if target_id is None:
            await message.answer("usage: /memory [user_id]")
            return
        async with db.session() as session:
            repo = Repository(session)
            user = await repo.get_user(target_id)
            memories = await repo.list_memories(target_id, limit=50) if user else []
            summary = await repo.latest_summary(target_id) if user else None
        if user is None:
            await message.answer(f"no user {target_id}")
            return
        if not memories and summary is None:
            await message.answer(f"no memory for {user.display_name} ({target_id})")
            return
        chunks: list[str] = [f"memory for {user.display_name} ({target_id}):"]
        if summary:
            chunks.append("summary:\n" + summary.content[:1500])
        if memories:
            chunks.append("facts:")
            for m in memories[:30]:
                chunks.append(f"- [{m.kind} w={m.importance}] {m.content}")
        text = "\n".join(chunks)
        for piece in _split_for_telegram(text):
            await message.answer(piece)

    @router.message(Command("forget"))
    async def on_forget(message: Message, command: CommandObject) -> None:
        if not _is_admin(message, settings):
            return
        target_id = _parse_user_id(command.args)
        if target_id is None:
            await message.answer("usage: /forget <user_id>")
            return
        async with db.session() as session:
            repo = Repository(session)
            await repo.delete_user_memories(target_id)
            await repo.delete_user_summaries(target_id)
            await session.commit()
        await message.answer(f"wiped memory + summaries for user {target_id}")

    @router.message(Command("reset"))
    async def on_reset(message: Message, command: CommandObject) -> None:
        if not _is_admin(message, settings):
            return
        target_id = _parse_user_id(command.args)
        if target_id is None:
            await message.answer("usage: /reset <user_id>")
            return
        async with db.session() as session:
            repo = Repository(session)
            await repo.delete_user_messages(target_id)
            await repo.delete_user_memories(target_id)
            await repo.delete_user_summaries(target_id)
            await session.commit()
        await message.answer(f"reset everything for user {target_id}")

    @router.message(Command("block"))
    async def on_block(message: Message, command: CommandObject) -> None:
        if not _is_admin(message, settings):
            return
        target_id = _parse_user_id(command.args)
        if target_id is None:
            await message.answer("usage: /block <user_id>")
            return
        async with db.session() as session:
            repo = Repository(session)
            await repo.set_blocked(target_id, True)
            await session.commit()
        await message.answer(f"blocked user {target_id}")

    @router.message(Command("unblock"))
    async def on_unblock(message: Message, command: CommandObject) -> None:
        if not _is_admin(message, settings):
            return
        target_id = _parse_user_id(command.args)
        if target_id is None:
            await message.answer("usage: /unblock <user_id>")
            return
        async with db.session() as session:
            repo = Repository(session)
            await repo.set_blocked(target_id, False)
            await session.commit()
        await message.answer(f"unblocked user {target_id}")

    @router.message(Command("users"))
    async def on_users(message: Message) -> None:
        if not _is_admin(message, settings):
            return
        async with db.session() as session:
            repo = Repository(session)
            users = await repo.list_users(limit=20)
        if not users:
            await message.answer("no users yet")
            return
        lines = ["recent users:"]
        for u in users:
            tag = " [admin]" if u.is_admin else ""
            tag += " [blocked]" if u.is_blocked else ""
            tag += " [paused]" if u.paused else ""
            lines.append(f"- {u.id} {u.display_name}{tag}")
        await message.answer("\n".join(lines))

    @router.message(Command("broadcast"))
    async def on_broadcast(message: Message, command: CommandObject) -> None:
        if not _is_admin(message, settings):
            return
        text = (command.args or "").strip()
        if not text:
            await message.answer("usage: /broadcast <text>")
            return
        async with db.session() as session:
            repo = Repository(session)
            users = await repo.list_users(limit=10_000)
        targets = [u for u in users if not u.is_blocked]
        sent = 0
        failed = 0
        # Telegram's global cap is ~30 msg/s. Stay well under that.
        for u in targets:
            try:
                await message.bot.send_message(u.id, text, disable_web_page_preview=True)
                sent += 1
            except TelegramForbiddenError:
                failed += 1
                async with db.session() as session:
                    repo = Repository(session)
                    await repo.set_blocked(u.id, True)
                    await session.commit()
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 0.5)
                try:
                    await message.bot.send_message(u.id, text, disable_web_page_preview=True)
                    sent += 1
                except Exception:  # noqa: BLE001
                    failed += 1
            except Exception:  # noqa: BLE001
                logger.exception("broadcast failed for user=%s", u.id)
                failed += 1
            await asyncio.sleep(0.05)  # ~20 msg/s
        await message.answer(f"broadcast: sent={sent} failed={failed} total={len(targets)}")

    @router.message(Command("admin_help"))
    async def on_admin_help(message: Message) -> None:
        if not _is_admin(message, settings):
            return
        await message.answer(
            "admin commands:\n"
            "/ping\n"
            "/stats\n"
            "/pause | /resume — global pause\n"
            "/users — recent users\n"
            "/memory [user_id] — show memory\n"
            "/forget <user_id> — wipe memory only\n"
            "/reset <user_id> — wipe everything\n"
            "/block <user_id> | /unblock <user_id>\n"
            "/broadcast <text> — send to all unblocked users"
        )

    return router


def _parse_user_id(args: str | None) -> int | None:
    if not args:
        return None
    token = args.strip().split()[0]
    try:
        return int(token)
    except ValueError:
        return None


def _split_for_telegram(text: str, limit: int = 3500) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    buf: list[str] = []
    used = 0
    for line in text.split("\n"):
        if used + len(line) + 1 > limit and buf:
            parts.append("\n".join(buf))
            buf = []
            used = 0
        buf.append(line)
        used += len(line) + 1
    if buf:
        parts.append("\n".join(buf))
    return parts
