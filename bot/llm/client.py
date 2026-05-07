"""Async OpenAI-compatible LLM client with retries."""

from __future__ import annotations

import json
from typing import Any

from openai import APIError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bot.config import Settings, get_settings
from bot.logger import get_logger

logger = get_logger(__name__)

_RETRYABLE: tuple[type[BaseException], ...] = (
    APITimeoutError,
    RateLimitError,
    APIError,
)


class LLMError(RuntimeError):
    """Wraps any non-recoverable LLM failure."""


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_request_timeout,
            max_retries=0,  # we do retries via tenacity for full control
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        response_format_json: bool = False,
    ) -> str:
        params: dict[str, Any] = {
            "model": model or self._settings.llm_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._settings.llm_temperature,
            "top_p": top_p if top_p is not None else self._settings.llm_top_p,
            "max_tokens": max_tokens or self._settings.llm_max_tokens,
        }
        if response_format_json:
            params["response_format"] = {"type": "json_object"}

        try:
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.6, min=0.5, max=6),
                retry=retry_if_exception_type(_RETRYABLE),
            ):
                with attempt:
                    completion = await self._client.chat.completions.create(**params)
        except APIStatusError as exc:
            logger.error("LLM API status error: %s", exc)
            raise LLMError(str(exc)) from exc
        except _RETRYABLE as exc:
            logger.error("LLM call failed after retries: %s", exc)
            raise LLMError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — surface unknown errors uniformly
            logger.exception("Unexpected LLM failure")
            raise LLMError(str(exc)) from exc

        choice = completion.choices[0]
        text = (choice.message.content or "").strip()
        return text

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> Any:
        """Like chat() but parses the response as JSON. Returns None on failure."""
        # Some providers don't support response_format=json_object — try with,
        # fall back to plain text and parse defensively.
        try:
            text = await self.chat(
                messages,
                model=model,
                temperature=temperature,
                response_format_json=True,
            )
        except LLMError:
            text = await self.chat(messages, model=model, temperature=temperature)

        text = text.strip()
        if text.startswith("```"):
            # strip ```json ... ``` fences if the model added them
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()

        # try to find a JSON object/array if the model added stray prose
        for opener, closer in (("[", "]"), ("{", "}")):
            i = text.find(opener)
            j = text.rfind(closer)
            if i != -1 and j != -1 and j > i:
                candidate = text[i : j + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON output: %r", text[:200])
            return None


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient(get_settings())
    return _client
