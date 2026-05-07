"""Light post-processing of model output to nudge it closer to the persona.

We do NOT rewrite the model's output — we just lightly polish: trim, strip
markdown artefacts, occasionally lowercase the first letter, remove obvious
chatbot tics. Keep this conservative, the model does the heavy lifting via
the system prompt.
"""

from __future__ import annotations

import random
import re

_BANNED_PHRASES = (
    "as an ai language model",
    "as an ai",
    "as a language model",
    "i am an ai",
    "i'm an ai",
    "я искусственный интеллект",
    "я языковая модель",
    "я просто бот",
    "я бот",
    "я нейросеть",
    "let me know if",
    "feel free to",
    "i hope this helps",
    "is there anything else",
    "хочешь чтобы я",
    "если у тебя есть еще вопросы",
)

_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_MD_ITALIC_RE = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])")
_MD_HEADER_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_BULLET_RE = re.compile(r"^[\s]*[-*•]\s+", re.MULTILINE)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def polish(text: str) -> str:
    """Lightly clean the LLM output before sending to Telegram."""
    if not text:
        return ""

    out = text.strip()

    # Strip code fences but keep inner content.
    if out.startswith("```") and out.endswith("```"):
        out = out.strip("`").strip()
        if out.lower().startswith(("json", "python", "txt")):
            out = out.split("\n", 1)[-1]

    # Drop bot-style framing.
    lowered = out.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lowered:
            # Try to drop the sentence containing it.
            sentences = re.split(r"(?<=[\.\!\?])\s+", out)
            sentences = [s for s in sentences if phrase not in s.lower()]
            out = " ".join(sentences).strip()
            lowered = out.lower()

    # Remove markdown decoration that doesn't render in Telegram plain text.
    out = _MD_BOLD_RE.sub(r"\1", out)
    out = _MD_ITALIC_RE.sub(r"\1", out)
    out = _MD_HEADER_RE.sub("", out)
    out = _MD_BULLET_RE.sub("", out)
    out = _MULTI_BLANK_RE.sub("\n\n", out)

    # Occasionally make it more lowercase-y to match the vibe.
    if out and out[0].isalpha() and out[0].isupper() and random.random() < 0.7:
        # Don't lowercase obvious proper nouns (very rough heuristic).
        if out.split()[0].lower() not in {"i", "ok", "ngl", "lol"}:
            out = out[0].lower() + out[1:]

    return out.strip()


def split_into_messages(text: str, max_parts: int = 3) -> list[str]:
    """Occasionally split a longer reply into 2-3 messages, like a real human typing."""
    text = text.strip()
    if not text:
        return []
    if len(text) < 70 or "\n" not in text and text.count(". ") < 1:
        return [text]
    if random.random() > 0.35:  # most replies stay as one message
        return [text]

    # Prefer splitting on blank lines, then sentence boundaries.
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(parts) < 2:
        sentences = [s.strip() for s in re.split(r"(?<=[\.\!\?])\s+", text) if s.strip()]
        if len(sentences) < 2:
            return [text]
        # Group sentences into 2 or 3 chunks.
        target = min(max_parts, max(2, len(sentences) // 2))
        chunk_size = max(1, len(sentences) // target)
        parts = []
        for i in range(0, len(sentences), chunk_size):
            parts.append(" ".join(sentences[i : i + chunk_size]))

    return parts[:max_parts]
