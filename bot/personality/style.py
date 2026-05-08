"""Light post-processing of model output to nudge it closer to the persona.

We do NOT rewrite the model's output — we just lightly polish: trim, strip
markdown artefacts, occasionally lowercase the first letter, remove obvious
chatbot tics. Keep this conservative, the model does the heavy lifting via
the system prompt.

Three tone categories are policy-gated (off by default, lifted only for
whitelisted contacts in `bot.persona.contact_policy`):

    profanity   — мат
    love        — affectionate "люблю" / "целую" / "родная"
    cute        — pet-names "малыш" / "котик" / "зайка"

If the model leaks one of those into a reply for a non-whitelisted contact,
we drop the offending sentence (keeping the rest of the reply intact).
"""

from __future__ import annotations

import re

from bot.persona.contact_policy import (
    is_cute_allowed,
    is_love_allowed,
    is_profanity_allowed,
)

_CASE_OPENERS = {
    "i", "yes", "yeah", "yep", "no", "nope", "ok", "okay", "sure", "maybe",
    "just", "so", "well", "hmm", "да", "нет", "ну", "норм", "мб", "та",
    "ага", "бля", "короче", "ща", "типа",
}

# Phrases that immediately give away "this is a chatbot". We strip them
# rather than letting them ship to Telegram.
_BANNED_PHRASES: tuple[str, ...] = (
    "as an ai language model",
    "as an ai",
    "as a language model",
    "i am an ai",
    "i'm an ai",
    "я искусственный интеллект",
    "я языковая модель",
    "я бот",
    "я просто бот",
    "я нейросеть",
    "let me know if",
    "feel free to",
    "i hope this helps",
    "is there anything else",
    "хочешь чтобы я",
    "если у тебя есть еще вопросы",
)

# Tone-category tokens — banned by default, conditionally lifted per
# contact. We match Russian word stems with `\w*` so e.g. "ебать", "ебал",
# "ебанул", "ебанутый" all match a single "ебан\w*" stem.
_PROFANITY_TOKENS: tuple[str, ...] = (
    r"бля",
    r"бляд\w*",
    r"блят\w*",
    r"пиздец\w*",
    r"пизд\w*",
    r"ебат\w*",
    r"ёбат\w*",
    r"ебал\w*",
    r"ебан\w*",
    r"ёбан\w*",
    r"ебуч\w*",
    r"еба\w*",
    r"ебись",
    r"ахуе\w*",
    r"охуе\w*",
    r"охуит\w*",
    r"нахуй",
    r"нихуя",
    r"хуй",
    r"хуёв\w*",
    r"хуев\w*",
    r"хуя\w*",
    r"хуяч\w*",
    r"сука",
    r"сук",
    r"гандон\w*",
    r"мудак\w*",
    r"мудил\w*",
    r"пидор\w*",
    r"fuck",
    r"fucking",
    r"shit",
)

# Affectionate vocabulary. Picky list — generic "хороший / милый" isn't
# banned, only direct affection markers.
_LOVE_TOKENS: tuple[str, ...] = (
    r"люблю",
    r"любимая",
    r"любимый",
    r"любимое",
    r"люблю\s+тебя",
    r"целую",
    r"обнимаю",
    r"родна\w+",
    r"родне\w+",
    r"родно\w+",
    r"сладк\w+",
    r"i\s+love\s+you",
    r"miss\s+you",
)

# Cute / pet-name register.
_CUTE_TOKENS: tuple[str, ...] = (
    r"малыш\w*",
    r"котик\w*",
    r"зайк\w+",
    r"зайч\w+",
    r"зай",
    r"солныш\w+",
    r"солнышк\w+",
    r"пупс\w*",
    r"крошк\w+",
    r"лапочк\w+",
    r"сладеньк\w+",
)


def _compile(tokens: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(r"\b" + t + r"\b", re.IGNORECASE) for t in tokens)


_BANNED_RES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE)
    for p in _BANNED_PHRASES
)
_PROFANITY_RES = _compile(_PROFANITY_TOKENS)
_LOVE_RES = _compile(_LOVE_TOKENS)
_CUTE_RES = _compile(_CUTE_TOKENS)

_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_MD_ITALIC_RE = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])")
_MD_HEADER_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_BULLET_RE = re.compile(r"^[\s]*[-*•]\s+", re.MULTILINE)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def _strip_matching(text: str, pattern: re.Pattern[str]) -> str:
    """Drop sentences that contain `pattern`. If nothing is left, just
    erase the matching token rather than nuking the whole reply."""
    if not pattern.search(text):
        return text
    sentences = re.split(r"(?<=[\.\!\?])\s+", text)
    kept = [s for s in sentences if not pattern.search(s)]
    if kept:
        return " ".join(kept).strip()
    return pattern.sub("", text).strip()


def polish(text: str, *, contact_id: int | None = None) -> str:
    """Lightly clean the LLM output before sending to Telegram.

    `contact_id` is the recipient's Telegram user_id. When provided we
    consult the per-user policy and conditionally allow profanity / love /
    cute vocabulary that's banned by default.
    """
    if not text:
        return ""

    out = text.strip()

    if out.startswith("```") and out.endswith("```"):
        out = out.strip("`").strip()
        if out.lower().startswith(("json", "python", "txt")):
            out = out.split("\n", 1)[-1]

    for pattern in _BANNED_RES:
        out = _strip_matching(out, pattern)

    if not is_profanity_allowed(contact_id):
        for pattern in _PROFANITY_RES:
            out = _strip_matching(out, pattern)
    if not is_love_allowed(contact_id):
        for pattern in _LOVE_RES:
            out = _strip_matching(out, pattern)
    if not is_cute_allowed(contact_id):
        for pattern in _CUTE_RES:
            out = _strip_matching(out, pattern)

    out = _MD_BOLD_RE.sub(r"\1", out)
    out = _MD_ITALIC_RE.sub(r"\1", out)
    out = _MD_HEADER_RE.sub("", out)
    out = _MD_BULLET_RE.sub("", out)
    out = _MULTI_BLANK_RE.sub("\n\n", out)

    if out and out[0].isalpha() and out[0].isupper():
        first_word = out.split(maxsplit=1)[0].rstrip(".,!?;:")
        if first_word.lower() in _CASE_OPENERS:
            out = out[0].lower() + out[1:]

    return out.strip()
