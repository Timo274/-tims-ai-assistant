"""Knowledge base about the bot's owner.

A static questionnaire (~120 questions) covering identity, background,
preferences, work, friends, opinions. The owner answers it once and the
answers are stored in `bot_state` under the key `KNOWLEDGE_KEY`. The
reply context loads this blob and injects it into the system prompt as
"WHAT YOU KNOW ABOUT YOURSELF" so the bot can answer factual questions
the way the real owner would.

We deliberately keep this as one big text blob — no parsing per
question. The owner can paste freeform answers and the LLM will pick out
what's relevant for any given conversation.
"""

from bot.knowledge.questionnaire import (
    KNOWLEDGE_KEY,
    QUESTIONNAIRE,
    format_questions_for_user,
    get_user_knowledge,
    set_user_knowledge,
)

__all__ = [
    "KNOWLEDGE_KEY",
    "QUESTIONNAIRE",
    "format_questions_for_user",
    "get_user_knowledge",
    "set_user_knowledge",
]
