"""Token-counting helpers. Uses tiktoken when available, falls back to a
4-chars-per-token heuristic for non-OpenAI models / when tiktoken errors out."""

from __future__ import annotations

from functools import lru_cache

try:  # pragma: no cover - import guard
    import tiktoken
except Exception:  # pragma: no cover
    tiktoken = None  # type: ignore[assignment]


@lru_cache(maxsize=8)
def _encoder(model: str):
    if tiktoken is None:
        return None
    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    if not text:
        return 0
    enc = _encoder(model)
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    # Heuristic fallback: ~4 chars per token.
    return max(1, len(text) // 4)


def count_messages_tokens(messages: list[dict[str, str]], model: str = "gpt-4o-mini") -> int:
    total = 0
    for msg in messages:
        content = str(msg.get("content", ""))
        # Each message has overhead (role, separators) — approximate as +4.
        total += count_tokens(content, model) + 4
    return total
