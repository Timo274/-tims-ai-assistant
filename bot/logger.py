"""Centralised logging setup: rotating file handler + colourful console."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_CONFIGURED = False


def configure_logging(level: str = "INFO", log_dir: str | Path = "./logs") -> None:
    """Idempotently configure root logging."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir_path = Path(log_dir).expanduser().resolve()
    log_dir_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(_FMT, datefmt=_DATEFMT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_dir_path / "bot.log",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Tame noisy libraries.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
