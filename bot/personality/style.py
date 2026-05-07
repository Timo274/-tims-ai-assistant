"""Light post-processing of model output to nudge it closer to the persona.

We do NOT rewrite the model's output — we just lightly polish: trim, strip
markdown artefacts, occasionally lowercase the first letter, remove obvious
chatbot tics. Keep this conservative, the model does the heavy lifting via
the system prompt.
"""

from __future__ import annotations

import re

_CASE_OPENERS = {
    "i", "yes", "yeah", "yep", "no", "nope", "ok", "okay", "sure", "maybe",
    "just", "so", "well", "hmm", "да", "нет", "ну", "норм", "мб", "та",
    "ага", "бля", "короче", "ща", "типа",
}

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

    # Lower-case the first letter ONLY when it's a common short sentence
    # opener like "I", "Yes", "Ok". For anything else we leave the case alone
    # so we don't mangle proper nouns ("Bitcoin", "Apple", "AP", "PP" etc).
    if out and out[0].isalpha() and out[0].isupper():
        first_word = out.split(maxsplit=1)[0].rstrip(".,!?;:")
        if first_word.lower() in _CASE_OPENERS:
            out = out[0].lower() + out[1:]

    return out.strip()
