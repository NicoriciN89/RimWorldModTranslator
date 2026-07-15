"""Сохранение настроек GUI между запусками: последняя папка мода/вывода,
язык, движок, модель Ollama, галочки. Файл лежит в профиле пользователя
(%APPDATA%), а не рядом с exe — программу могут положить в папку без прав
на запись (Program Files), и настройки там молча не сохранялись бы."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .log_setup import get_logger

log = get_logger("settings")


def _settings_path() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home()
    return root / "RimWorldModTranslator" / "settings.json"


def load_settings() -> dict:
    path = _settings_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError) as e:
        log.warning("Не удалось прочитать настройки %s: %s", path, e)
        return {}


def save_settings(data: dict) -> None:
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except OSError as e:
        # Настройки — удобство, не критичная функция: не роняем перевод.
        log.warning("Не удалось сохранить настройки %s: %s", path, e)
