"""Инкрементальный доперевод: при повторном запуске на уже переведённый мод
переводим только новые или изменившиеся английские строки, остальное берём
из существующего перевода как есть.

Чтобы понять, что именно изменилось в английском тексте (а не просто узнать,
существует ли ключ), рядом с переводом хранится скрытый файл
`.translation_cache.json` — снимок английских строк на момент последнего
перевода, ключ в ключ. Без него по одному XML нельзя отличить "текст не
менялся" от "текст поменялся, но у ключа то же имя".
"""
from __future__ import annotations

import json
from pathlib import Path

from . import xml_io
from .scanner import ScanResult

CACHE_FILENAME = ".translation_cache.json"


def _cache_path(out_root: Path) -> Path:
    return out_root / CACHE_FILENAME


def load_cache(out_root: Path) -> dict[str, str]:
    path = _cache_path(out_root)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def save_cache(out_root: Path, english_by_key: dict[str, str]) -> None:
    _cache_path(out_root).write_text(
        json.dumps(english_by_key, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8",
    )


def _existing_translations(out_root: Path, lang_dir_name: str) -> dict[str, str]:
    """Читает уже собранный переведённый мод и возвращает {ключ: переведённый_текст}
    по всем Keyed/DefInjected файлам, которые там нашлись."""
    lang_root = out_root / "Languages" / lang_dir_name
    result: dict[str, str] = {}
    if not lang_root.is_dir():
        return result

    for sub in ("Keyed", "DefInjected"):
        sub_dir = lang_root / sub
        if not sub_dir.is_dir():
            continue
        for xml_file in sub_dir.rglob("*.xml"):
            data = xml_io.parse_language_data(xml_file)
            for entry in data.keyed_items():
                result[entry.key] = entry.text
    return result


def apply_incremental(scan: ScanResult, out_root: Path, lang_dir_name: str) -> set[str]:
    """Мутирует scan на месте: для ключей, чей английский текст не изменился
    с прошлого перевода (по кэшу) и для которых уже есть готовый перевод,
    подставляет старый перевод вместо английского текста. Остальные ключи
    остаются с английским текстом — их предстоит перевести как обычно.

    Возвращает множество ключей, которые были переиспользованы (чтобы вызывающий
    код мог однозначно пропустить их при переводе, не гадая по содержимому)."""
    old_english = load_cache(out_root)
    if not old_english:
        return set()

    old_translations = _existing_translations(out_root, lang_dir_name)

    reused_keys: set[str] = set()
    for task in list(scan.keyed) + list(scan.def_injected):
        for entry in task.data.keyed_items():
            unchanged = old_english.get(entry.key) == entry.text
            has_translation = entry.key in old_translations
            if unchanged and has_translation:
                entry.text = old_translations[entry.key]
                reused_keys.add(entry.key)
    return reused_keys
