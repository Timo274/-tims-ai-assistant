"""Timing helpers used by the typing simulator."""

from __future__ import annotations

import asyncio
import random


def estimate_typing_delay(
    text: str,
    *,
    per_char: float,
    minimum: float,
    maximum: float,
) -> float:
    """Return a human-ish typing delay for the given message length."""
    base = per_char * len(text)
    # Add small random jitter so two replies are never identical in timing.
    jitter = random.uniform(-0.25, 0.6)
    return max(minimum, min(maximum, base + jitter))


async def sleep_jitter(seconds: float) -> None:
    """Sleep with a small +/-15% jitter."""
    if seconds <= 0:
        return
    await asyncio.sleep(seconds * random.uniform(0.85, 1.15))
