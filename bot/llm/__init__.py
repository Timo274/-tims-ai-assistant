"""LLM client + prompt library."""

from bot.llm.client import LLMClient, get_llm_client
from bot.llm.prompts import (
    MEMORY_EXTRACTION_PROMPT,
    PERSONA_BASE,
    STYLE_RULES,
    SUMMARY_PROMPT,
    build_system_prompt,
)

__all__ = [
    "LLMClient",
    "MEMORY_EXTRACTION_PROMPT",
    "PERSONA_BASE",
    "STYLE_RULES",
    "SUMMARY_PROMPT",
    "build_system_prompt",
    "get_llm_client",
]
