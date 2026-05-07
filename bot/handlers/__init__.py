"""aiogram handlers."""

from bot.handlers.admin import build_admin_router
from bot.handlers.messages import build_message_router
from bot.handlers.start import build_start_router

__all__ = ["build_admin_router", "build_message_router", "build_start_router"]
