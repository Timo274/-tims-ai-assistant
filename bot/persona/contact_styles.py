"""Per-contact style fingerprints loaded from a static JSON.

The JSON (`contact_styles.json`) was generated from the user's Telegram
archive — for each contact we kept a small set of frequency stats that
describe how the user *historically* writes to them:

  - typical message length (median/mean characters)
  - language mix (% Cyrillic / % Ukrainian-specific letters / % Latin)
  - lowercase rate
  - emoji rate
  - profanity / love word rates (informational — actual policy lives in
    `contact_policy.py`)

At reply time we look up the contact (by Telegram user_id) and inject a
short "your historical style with this person" hint into the system
prompt. For unknown contacts we just don't add the block.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_STYLES_PATH = Path(__file__).parent / "contact_styles.json"


@dataclass(frozen=True)
class ContactStyle:
    contact_id: int
    n_out: int
    n_in: int
    median_len: int
    mean_len: float
    pct_emoji: float
    pct_lowercase: float
    pct_cyrillic: float
    pct_ukrainian: float
    pct_latin: float
    pct_profanity: float
    pct_love: float

    @property
    def dominant_language(self) -> str:
        """One-of {"ru", "uk", "en", "mixed"} based on Cyrillic vs Latin
        share. Ukrainian-specific letters bump Russian → Ukrainian."""
        if self.pct_cyrillic >= 70:
            if self.pct_ukrainian >= 8:
                return "uk"
            return "ru"
        if self.pct_latin >= 50:
            return "en"
        return "mixed"

    @property
    def length_bucket(self) -> str:
        """Coarse bucket for prompt: short / medium / long."""
        if self.median_len <= 12:
            return "short"
        if self.median_len <= 30:
            return "medium"
        return "long"


@lru_cache(maxsize=1)
def _load() -> dict[int, ContactStyle]:
    if not _STYLES_PATH.exists():
        return {}
    with _STYLES_PATH.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    out: dict[int, ContactStyle] = {}
    for c in raw.get("contacts", []):
        cid = int(c["contact_id"])
        out[cid] = ContactStyle(
            contact_id=cid,
            n_out=int(c.get("n_out", 0)),
            n_in=int(c.get("n_in", 0)),
            median_len=int(c.get("med", 0)),
            mean_len=float(c.get("mean", 0.0)),
            pct_emoji=float(c.get("emoji", 0.0)),
            pct_lowercase=float(c.get("lower", 0.0)),
            pct_cyrillic=float(c.get("cyr", 0.0)),
            pct_ukrainian=float(c.get("uk", 0.0)),
            pct_latin=float(c.get("lat", 0.0)),
            pct_profanity=float(c.get("prof", 0.0)),
            pct_love=float(c.get("love", 0.0)),
        )
    return out


def lookup_style(contact_id: int | None) -> ContactStyle | None:
    if contact_id is None:
        return None
    return _load().get(contact_id)
