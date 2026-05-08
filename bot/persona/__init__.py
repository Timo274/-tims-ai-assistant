"""Persona data: hard-coded per-contact policy + style fingerprints derived
from the user's real Telegram archive.

The archive itself is NOT stored in the repo. We only ship aggregate stats
per contact (length / language / emoji rate) and a small policy table
(which contacts may receive profanity / love-words). This lets the bot
adapt tone per contact without leaking any actual conversation content.
"""

from bot.persona.contact_policy import (
    CUTE_ALLOWED_USER_IDS,
    DISCLOSE_AI_USER_IDS,
    LOVE_ALLOWED_USER_IDS,
    PROFANITY_ALLOWED_USER_IDS,
    is_cute_allowed,
    is_disclose_ai,
    is_love_allowed,
    is_profanity_allowed,
)
from bot.persona.contact_styles import ContactStyle, lookup_style

__all__ = [
    "CUTE_ALLOWED_USER_IDS",
    "DISCLOSE_AI_USER_IDS",
    "LOVE_ALLOWED_USER_IDS",
    "PROFANITY_ALLOWED_USER_IDS",
    "ContactStyle",
    "is_cute_allowed",
    "is_disclose_ai",
    "is_love_allowed",
    "is_profanity_allowed",
    "lookup_style",
]
