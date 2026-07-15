"""Ручные правки перевода, переживающие перегенерацию.

Проблема: пользователь поправил кривую строку прямо в выходном XML/txt — а
следующая генерация (обновление мода, смена движка) молча затирала правку
машинным переводом заново.

Механизм: после каждой генерации рядом с переводом сохраняется скрытый
снимок `.machine_translation.json` — {ключ: текст, который записала сама
программа}. При следующем запуске текущие файлы перевода сравниваются со
снимком: каждое расхождение — ручная правка пользователя. Она поднимается в
`manual_overrides.json` (обычный человекочитаемый JSON рядом с переводом) и
с этого момента ВСЕГДА подставляется вместо машинного перевода — при любом
режиме и движке. Чтобы отменить правку, удалите её строку из
manual_overrides.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from .incremental import _existing_translations
from .log_setup import get_logger
from .scanner import ScanResult

log = get_logger("overrides")

SNAPSHOT_FILENAME = ".machine_translation.json"
OVERRIDES_FILENAME = "manual_overrides.json"


def _load_json(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _save_json(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
                    encoding="utf-8")


def save_snapshot(out_root: Path, machine_texts: dict[str, str]) -> None:
    """Сохраняет снимок «что записала программа» — базу для следующего
    harvest_manual_edits. Вызывается только при УСПЕШНОМ завершении перевода
    (как и кэш incremental): снимок обязан соответствовать файлам на диске."""
    _save_json(out_root / SNAPSHOT_FILENAME, machine_texts)


def harvest_manual_edits(out_root: Path, lang_dir_name: str) -> dict[str, str]:
    """Сравнивает текущие файлы перевода со снимком прошлой генерации,
    поднимает все расхождения в manual_overrides.json и возвращает полный
    (обновлённый) словарь override'ов {ключ: текст пользователя}."""
    overrides_path = out_root / OVERRIDES_FILENAME
    overrides = _load_json(overrides_path)

    snapshot = _load_json(out_root / SNAPSHOT_FILENAME)
    if snapshot:
        current = _existing_translations(out_root, lang_dir_name)
        harvested = {
            key: text
            for key, text in current.items()
            if key in snapshot and text != snapshot[key]
        }
        if harvested:
            log.info("Обнаружено %d ручных правок в файлах перевода — сохраняю в %s",
                     len(harvested), OVERRIDES_FILENAME)
            overrides.update(harvested)
            _save_json(overrides_path, overrides)
    return overrides


def apply_overrides(scan: ScanResult, overrides: dict[str, str]) -> set[str]:
    """Подставляет ручные правки в результат сканирования. Возвращает
    множество ключей, к которым применилась правка — вызывающий код исключает
    их из перевода (правка пользователя финальна)."""
    if not overrides:
        return set()
    applied: set[str] = set()
    for task in list(scan.keyed) + list(scan.def_injected) + list(scan.strings):
        for entry in task.data.keyed_items():
            if entry.key in overrides:
                entry.text = overrides[entry.key]
                applied.add(entry.key)
    return applied
