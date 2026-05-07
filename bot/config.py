"""Application configuration loaded from environment variables / .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Telegram
    bot_token: str = Field(..., min_length=20)
    # Stored as raw CSV (e.g. "111,222") and exposed as a parsed list via the
    # `admin_ids` property. We don't type this as `list[int]` because
    # pydantic-settings v2 tries to JSON-decode complex env values, and a CSV
    # like "111,222" isn't valid JSON.
    admin_ids_raw: str = Field(default="", alias="admin_ids")
    bot_persona_name: str = "tim"

    # LLM
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_summary_model: str = "gpt-4o-mini"
    llm_api_key: str = Field(..., min_length=8)
    llm_temperature: float = 0.95
    llm_top_p: float = 0.95
    llm_max_tokens: int = 400
    llm_request_timeout: float = 45.0

    # Storage
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"

    # Reply behaviour
    reply_debounce_seconds: float = 2.5
    typing_delay_per_char: float = 0.03
    typing_delay_min: float = 0.6
    typing_delay_max: float = 4.5
    context_recent_messages: int = 20
    summarise_after_messages: int = 40
    memory_top_k: int = 8

    # Rate limiting
    rate_limit_messages: int = 20
    rate_limit_window_seconds: int = 60

    # Logging
    log_level: str = "INFO"
    log_dir: str = "./logs"

    # Operational toggles
    start_paused: bool = False
    reply_in_groups: bool = False

    # ----- validators ------------------------------------------------------
    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    # ----- helpers ---------------------------------------------------------
    @property
    def admin_ids(self) -> list[int]:
        if not self.admin_ids_raw:
            return []
        out: list[int] = []
        for part in self.admin_ids_raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out.append(int(part))
            except ValueError:
                continue
        return out

    @property
    def log_dir_path(self) -> Path:
        return Path(self.log_dir).expanduser().resolve()

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def sqlite_path(self) -> Path | None:
        if not self.is_sqlite:
            return None
        # sqlite+aiosqlite:///./data/bot.db -> ./data/bot.db
        _, _, tail = self.database_url.partition(":///")
        return Path(tail).expanduser().resolve() if tail else None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
