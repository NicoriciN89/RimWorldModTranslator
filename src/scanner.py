"""Обход папки мода: находит исходные строки для перевода либо в
Languages/English/{Keyed,DefInjected}, либо (fallback) прямо в Defs/*.xml."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from . import xml_io

_VERSION_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)$", re.IGNORECASE)


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


def _find_load_folders_xml(mod_root: Path) -> Path | None:
    for candidate in mod_root.glob("*"):
        if candidate.is_file() and candidate.name.lower() == "loadfolders.xml":
            return candidate
    return None


def _resolve_content_roots(mod_root: Path) -> list[Path]:
    """Определяет, какие подпапки мода реально грузятся игрой для новейшей
    поддерживаемой версии, чтобы не сканировать (и не дублировать перевод)
    контент из более старых версионных копий (1.0/, 1.1/, ...), которые мод
    хранит рядом просто для обратной совместимости со старыми версиями RimWorld.

    Источник истины — LoadFolders.xml мода (официальный механизм RimWorld):
    каждый элемент вида <v1.6><li>путь</li>...</v1.6> перечисляет папки для
    этой версии игры. Пути с условием IfModActive (грузятся только если
    установлен конкретный другой мод) пропускаем — у нас нет информации о
    списке модов пользователя, и лучше не разбирать зависимость, которая
    может не быть активна.

    Если LoadFolders.xml нет — ищем папки с именем-версией (1.0..1.6) в
    корне мода и берём только максимальную по номеру плюс сам корень (там,
    где обычно лежат общие для всех версий Defs)."""
    load_folders = _find_load_folders_xml(mod_root)
    if load_folders is not None:
        try:
            root = ET.parse(load_folders).getroot()
        except ET.ParseError:
            root = None
        if root is not None:
            versions = [child.tag for child in root if _VERSION_TAG_RE.match(child.tag)]
            if versions:
                best = max(versions, key=lambda v: tuple(int(x) for x in _VERSION_TAG_RE.match(v).groups()))
                version_el = root.find(best)
                roots: list[Path] = []
                for li in version_el:
                    if li.get("IfModActive"):
                        continue
                    rel = (li.text or "").strip().strip("/\\")
                    candidate = mod_root / rel if rel else mod_root
                    if candidate.is_dir():
                        roots.append(candidate)
                if roots:
                    return roots

    version_dirs = [
        d for d in mod_root.iterdir()
        if d.is_dir() and _VERSION_TAG_RE.match(d.name)
    ]
    if version_dirs:
        best_dir = max(version_dirs, key=lambda d: tuple(int(x) for x in _VERSION_TAG_RE.match(d.name).groups()))
        return [mod_root, best_dir]

    return [mod_root]


def _scan_defs_fallback(mod_root: Path) -> list[DefInjectedTask]:
    """Извлекает переводимые поля прямо из Defs/*.xml, сгруппированные по
    (DefType, имя файла) — так же, как их раскладывает по папкам DefInjected.
    Сканирует только папки, которые реально грузятся игрой (см.
    _resolve_content_roots), чтобы не дублировать перевод одного и того же
    контента из старых версионных копий мода."""
    # _resolve_content_roots уже перечисляет все нужные корни явно (включая
    # опциональные подпапки конкретных под-модов) — берём Defs только прямо
    # под каждым из них, БЕЗ рекурсивного "**/Defs". Рекурсивный поиск отсюда
    # был бы не только избыточен, но и опасен: он бы затягивал Defs из
    # вложенных путей, которые _resolve_content_roots специально исключил
    # (напр. опциональные Mods/<X> с IfModActive, для которых нет данных об
    # установленных у пользователя модах).
    # Разные content root всё ещё могут указывать на одну и ту же папку
    # (напр. mod_root и mod_root/1.6, если версионных подпапок нет вовсе) —
    # дедуплицируем по разрешённому абсолютному пути.
    seen_defs_dirs: dict[Path, Path] = {}
    for content_root in _resolve_content_roots(mod_root):
        defs_dir = content_root / "Defs"
        if defs_dir.is_dir():
            seen_defs_dirs.setdefault(defs_dir.resolve(), defs_dir)
    defs_dirs = list(seen_defs_dirs.values())

    grouped: dict[tuple[str, str], list[xml_io.DefFieldRef]] = {}
    for defs_dir in defs_dirs:
        for xml_file in defs_dir.rglob("*.xml"):
            refs = xml_io.extract_translatable_from_defs(xml_file)
            if not refs:
                continue
            def_type = refs[0].def_type
            grouped.setdefault((def_type, xml_file.stem), []).extend(refs)

    result: list[DefInjectedTask] = []
    for (def_type, file_stem), refs in grouped.items():
        data = xml_io.LanguageDataFile()
        for ref in refs:
            key = f"{ref.def_name}.{ref.field_path}" if ref.field_path else ref.def_name
            data.entries.append(xml_io.Entry(key=key, text=ref.text))
        result.append(DefInjectedTask(def_type=def_type, rel_path=Path(f"{file_stem}.xml"), data=data))
    return result


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

    if english_dir is None:
        # Нет Languages/English вообще — извлекаем всё прямо из Defs/*.xml.
        return ScanResult(source_lang_dir=None, keyed=keyed, def_injected=_scan_defs_fallback(mod_root))

    keyed_dir = english_dir / "Keyed"
    if keyed_dir.is_dir():
        for xml_file in keyed_dir.rglob("*.xml"):
            rel = xml_file.relative_to(keyed_dir)
            keyed.append(KeyedTask(rel_path=rel, data=xml_io.parse_language_data(xml_file)))

    definj_dir = english_dir / "DefInjected"
    covered_def_types: set[str] = set()
    if definj_dir.is_dir():
        for def_type_dir in definj_dir.iterdir():
            if not def_type_dir.is_dir():
                continue
            covered_def_types.add(def_type_dir.name)
            for xml_file in def_type_dir.rglob("*.xml"):
                rel = xml_file.relative_to(def_type_dir)
                def_injected.append(DefInjectedTask(
                    def_type=def_type_dir.name,
                    rel_path=rel,
                    data=xml_io.parse_language_data(xml_file),
                ))

    # Languages/English/Keyed может существовать без DefInjected (или с
    # DefInjected только для части DefType) — в этом случае строки label/
    # description/... в Defs/*.xml иначе молча терялись бы. Дополняем
    # fallback-сканированием только те DefType, которых нет в DefInjected.
    for task in _scan_defs_fallback(mod_root):
        if task.def_type not in covered_def_types:
            def_injected.append(task)

    return ScanResult(source_lang_dir="English", keyed=keyed, def_injected=def_injected)
