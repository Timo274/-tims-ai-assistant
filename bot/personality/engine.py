"""Personality engine: detects the other person's tone and exposes config
for the prompt builder. Keeps the persona deterministic but adaptive."""

from __future__ import annotations

import re
from dataclasses import dataclass


_RECRUITER_HINTS = (
    "recruiter",
    "hr ",
    "internship",
    "стажир",
    "стажування",
    "вакансі",
    "вакансия",
    "интернш",
    "офер",
    "offer",
    "recruit",
    "linkedin",
    "ваш резюме",
    "ваше cv",
    "позици",
    "interview",
    "интервью",
    "співбесід",
    "собеседован",
    "salary",
    "ставка",
    "compens",
    "candidate",
    "applicat",
)

_FORMAL_MARKERS = (
    "good afternoon",
    "good morning",
    "dear ",
    "regards",
    "sincerely",
    "уважаем",
    "доброго дня",
    "доброго ранку",
    "добрый день",
    "доброе утро",
    "вітаю",
    "прошу повідомити",
    "позвольте",
    "будь ласка, повідомте",
    "хотів би уточнити",
    "хотел бы уточнить",
)

_CASUAL_MARKERS = (
    "ахах",
    "лол",
    "хах",
    "💀",
    "😭",
    "ну ",
    "че ",
    "чо ",
    "хз ",
    "капец",
    "ща ",
    "ето ",
    "lol",
    "lmao",
    "kek",
    "омг",
    "norm",
    "норм",
    "база",
    "вайб",
    "лооол",
)


@dataclass
class ToneProfile:
    label: str  # "recruiter" | "formal" | "casual" | "neutral"
    hint: str   # short instruction injected into the system prompt

    @classmethod
    def from_label(cls, label: str) -> "ToneProfile":
        return _TONE_PRESETS.get(label, _TONE_PRESETS["neutral"])


_TONE_PRESETS: dict[str, ToneProfile] = {
    "recruiter": ToneProfile(
        label="recruiter",
        hint=(
            "this looks like a recruiter / professional contact. dial UP the seriousness: "
            "fewer emojis, near-zero slang, mostly proper sentences, but still you — "
            "real, opinionated, a bit dry. one short paragraph max, no walls of text."
        ),
    ),
    "formal": ToneProfile(
        label="formal",
        hint=(
            "they're being polite/formal. mirror it a bit but stay yourself. "
            "no emojis, very mild slang, complete sentences. don't go full corporate."
        ),
    ),
    "casual": ToneProfile(
        label="casual",
        hint=(
            "they're casual / chaotic. you can lean into the slang, lowercase, "
            "irony, emojis (sparingly), short replies. match their energy."
        ),
    ),
    "neutral": ToneProfile(
        label="neutral",
        hint=(
            "tone is neutral. default mode: mostly lowercase, short-medium, "
            "casual but not chaotic, slight irony, occasional emoji."
        ),
    ),
}


_NON_WORD_RE = re.compile(r"[^\w\sа-яёіїєґА-ЯЁІЇЄҐ]")


class PersonalityEngine:
    """Stateless tone classifier. Cheap heuristic — no LLM call."""

    def detect_tone(self, recent_user_text: str) -> ToneProfile:
        if not recent_user_text:
            return _TONE_PRESETS["neutral"]
        lowered = recent_user_text.lower()

        if any(marker in lowered for marker in _RECRUITER_HINTS):
            return _TONE_PRESETS["recruiter"]

        formal_score = sum(1 for m in _FORMAL_MARKERS if m in lowered)
        casual_score = sum(1 for m in _CASUAL_MARKERS if m in lowered)

        # Capitalisation / punctuation density nudges the score.
        words = lowered.split()
        if words:
            cap_ratio = sum(1 for w in recent_user_text.split() if w[:1].isupper()) / max(1, len(words))
            if cap_ratio > 0.5:
                formal_score += 1
            if recent_user_text.count("!") + recent_user_text.count("?") > 4:
                casual_score += 1

        if formal_score >= 2 and formal_score > casual_score:
            return _TONE_PRESETS["formal"]
        if casual_score >= 2 and casual_score > formal_score:
            return _TONE_PRESETS["casual"]
        return _TONE_PRESETS["neutral"]
