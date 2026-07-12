"""Файловый лог для GUI-сборки: у --windowed exe нет консоли, поэтому без
файла нельзя понять, что происходит долгий перевод (особенно с --llm — там
на строку уходит 40-90 секунд, и без лога пользователю кажется, что
программа зависла) или что упало и почему."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_FILENAME = "translator.log"


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def setup_logging() -> Path:
    """Настраивает логгер "rmt", пишущий в translator.log рядом с exe
    (или рядом с проектом при запуске из исходников). Возвращает путь к файлу."""
    log_path = _app_dir() / LOG_FILENAME
    logger = logging.getLogger("rmt")
    logger.setLevel(logging.DEBUG)

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(handler)
    logger.propagate = False
    return log_path


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"rmt.{name}")
