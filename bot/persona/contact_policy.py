"""Hard-coded allow-lists for tone categories that are off by default.

Profanity, love-words, and cute-pet-names are disabled in the default
persona. They get re-enabled per Telegram user_id below — the user
manually whitelisted these contacts in the spec ("мат можно только юзеру
955745087, любовные/милые только юзеру 1120864152"). The data also backs
this up: in the archive `Рома Армор` (955745087) sees ~9.6% of messages
contain profanity (the user's max), while `жинка` (1120864152) is the
top-volume contact and the only one with consistent affectionate
language. Every other contact gets the clean default.

Adding a new ID here is the entire knob — no env var, no admin command.
We intentionally don't expose this through the LLM to avoid prompt
injection lifting the bans.
"""

from __future__ import annotations

# Profanity ("бля", "пиздец", "ебать", "ахуеть", etc.) is allowed only here.
PROFANITY_ALLOWED_USER_IDS: frozenset[int] = frozenset({
    955745087,   # Рома Армор — historical 9.6% profanity rate
})

# Love / affection words ("люблю", "целую", "родная", "обнимаю") only here.
LOVE_ALLOWED_USER_IDS: frozenset[int] = frozenset({
    1120864152,  # жинка
})

# Cute / pet-name register ("малыш", "котик", "зайка", "солнышко") only here.
CUTE_ALLOWED_USER_IDS: frozenset[int] = frozenset({
    1120864152,  # жинка
})

# Contacts who explicitly opted into knowing this is a bot. Empty by default
# — variant B from the spec means "only disclose when asked", not "always
# announce". Adding an ID here would make the bot prefix replies with a
# disclosure even when not asked, which we currently don't want for anyone.
DISCLOSE_AI_USER_IDS: frozenset[int] = frozenset()


# Hard never-reply list. The bot must not produce ANY reply (no text, no
# typing indicator, no LLM call) for messages from these contacts. Used
# for relatives / accounts the owner explicitly wants to stay out of —
# e.g. the owner's mother. Distinct from the dynamic /block command,
# which can be flipped at runtime: this list is checked even before the
# DB lookup so it's tamper-proof from prompt injection or DB writes.
NEVER_REPLY_USER_IDS: frozenset[int] = frozenset({
    689177445,   # owner-designated do-not-autoreply contact
})


# Known named contacts: Telegram user_id -> short label injected into
# the system prompt so the LLM knows who it's talking to. Keep these
# minimal — they should be at most a couple of words ("Соня (девушка)",
# "Рома (лучший друг)"). Anything richer belongs in /set_knowledge.
CONTACT_NAMES: dict[int, str] = {
    1120864152: "Соня (девушка, отношения 10+ месяцев)",
    955745087: "Рома (лучший друг, дружат 2+ года)",
}


def is_profanity_allowed(user_id: int | None) -> bool:
    return user_id is not None and user_id in PROFANITY_ALLOWED_USER_IDS


def is_love_allowed(user_id: int | None) -> bool:
    return user_id is not None and user_id in LOVE_ALLOWED_USER_IDS


def is_cute_allowed(user_id: int | None) -> bool:
    return user_id is not None and user_id in CUTE_ALLOWED_USER_IDS


def is_disclose_ai(user_id: int | None) -> bool:
    return user_id is not None and user_id in DISCLOSE_AI_USER_IDS


def is_never_reply(user_id: int | None) -> bool:
    return user_id is not None and user_id in NEVER_REPLY_USER_IDS


def get_contact_name(user_id: int | None) -> str | None:
    if user_id is None:
        return None
    return CONTACT_NAMES.get(user_id)
