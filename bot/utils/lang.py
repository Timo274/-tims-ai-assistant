"""Tiny language detector used to decide reply language for new chats.

We only care about three buckets:
    - "ru"  Russian (default)
    - "uk"  Ukrainian (cyrillic + uk-only letters OR distinctive uk words)
    - "en"  English / latin

For anything we can't classify cheaply we return None and the prompt's
default-Russian rule wins. This is a heuristic — it is fine for first-
contact decisions ("recruiter writes in ukrainian → reply in ukrainian")
but not a real language detector. If a Russian-leaning text happens to
contain a single uk-only letter we'll classify as Ukrainian, which is
the conservative choice (we'd rather mirror up than lecture in Russian).
"""

from __future__ import annotations

import re

_UK_ONLY = set("іїєґІЇЄҐ")
_CYR_RE = re.compile(r"[а-яёА-ЯЁіїєґІЇЄҐ]")
_LAT_RE = re.compile(r"[A-Za-z]")

# Very small list of high-signal Ukrainian-only word stems. Russian-Ukrainian
# pairs are intentionally excluded (e.g. "як" vs "как" would mis-fire).
# These survive normal Cyrillic-letter spelling but never appear in modern
# Russian — they're enough to flip a short message to UK without reaching
# for a real detector library.
_UK_WORDS: tuple[str, ...] = (
    r"дякую",
    r"будь\s+ласка",
    r"немає",
    r"замість",
    r"вибачте",
    r"щось",
    r"щодо",
    r"щодня",
    r"завжди",
    r"тільки",
    r"трохи",
    r"взагалі",
    r"насправді",
    r"чомусь",
    r"досить",
)
_UK_WORD_RE = re.compile(r"\b(" + "|".join(_UK_WORDS) + r")\b", re.IGNORECASE)


def detect_language(text: str) -> str | None:
    if not text:
        return None
    cyr = sum(1 for c in text if _CYR_RE.match(c))
    lat = sum(1 for c in text if _LAT_RE.match(c))
    total = cyr + lat
    if total == 0:
        return None
    cyr_share = cyr / total
    if cyr_share >= 0.5:
        if any(c in _UK_ONLY for c in text):
            return "uk"
        if _UK_WORD_RE.search(text):
            return "uk"
        return "ru"
    if lat / total >= 0.5:
        return "en"
    return None
