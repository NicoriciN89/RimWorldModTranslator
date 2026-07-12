"""Обход папки мода: находит исходные строки для перевода либо в
Languages/English/{Keyed,DefInjected}, либо (fallback) прямо в Defs/*.xml."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import xml_io


@dataclass
class KeyedTask:
    rel_path: Path          # относительный путь файла внутри Keyed/
    data: xml_io.LanguageDataFile


@dataclass
class DefInjectedTask:
    def_type: str
    rel_path: Path          # относительный путь файла внутри DefInjected/<DefType>/
    data: xml_io.LanguageDataFile


@dataclass
class ScanResult:
    source_lang_dir: str | None   # "English" если найден, иначе None (fallback-режим)
    keyed: list[KeyedTask]
    def_injected: list[DefInjectedTask]


def _find_languages_dir(mod_root: Path) -> Path | None:
    candidates = list(mod_root.glob("**/Languages"))
    return candidates[0] if candidates else None


def scan_mod(mod_root: Path) -> ScanResult:
    languages_dir = _find_languages_dir(mod_root)
    english_dir = None
    if languages_dir is not None:
        for d in languages_dir.iterdir():
            if d.is_dir() and d.name.lower() in ("english",):
                english_dir = d
                break

    keyed: list[KeyedTask] = []
    def_injected: list[DefInjectedTask] = []

    if english_dir is not None:
        keyed_dir = english_dir / "Keyed"
        if keyed_dir.is_dir():
            for xml_file in keyed_dir.rglob("*.xml"):
                rel = xml_file.relative_to(keyed_dir)
                keyed.append(KeyedTask(rel_path=rel, data=xml_io.parse_language_data(xml_file)))

        definj_dir = english_dir / "DefInjected"
        if definj_dir.is_dir():
            for def_type_dir in definj_dir.iterdir():
                if not def_type_dir.is_dir():
                    continue
                for xml_file in def_type_dir.rglob("*.xml"):
                    rel = xml_file.relative_to(def_type_dir)
                    def_injected.append(DefInjectedTask(
                        def_type=def_type_dir.name,
                        rel_path=rel,
                        data=xml_io.parse_language_data(xml_file),
                    ))
        return ScanResult(source_lang_dir="English", keyed=keyed, def_injected=def_injected)

    # Fallback: нет Languages/English — извлекаем строки прямо из Defs/*.xml
    defs_dirs = list(mod_root.glob("**/Defs"))
    grouped: dict[tuple[str, str], list[xml_io.DefFieldRef]] = {}
    for defs_dir in defs_dirs:
        for xml_file in defs_dir.rglob("*.xml"):
            refs = xml_io.extract_translatable_from_defs(xml_file)
            if not refs:
                continue
            def_type = refs[0].def_type
            grouped.setdefault((def_type, xml_file.stem), []).extend(refs)

    for (def_type, file_stem), refs in grouped.items():
        data = xml_io.LanguageDataFile()
        for ref in refs:
            key = f"{ref.def_name}.{ref.field_path}" if ref.field_path else ref.def_name
            data.entries.append(xml_io.Entry(key=key, text=ref.text))
        def_injected.append(DefInjectedTask(
            def_type=def_type,
            rel_path=Path(f"{file_stem}.xml"),
            data=data,
        ))

    return ScanResult(source_lang_dir=None, keyed=keyed, def_injected=def_injected)
