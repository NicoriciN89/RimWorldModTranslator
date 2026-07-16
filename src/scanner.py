"""Обход папки мода: находит исходные строки для перевода в
Languages/English/{Keyed,DefInjected,Strings}, в Defs/*.xml (fallback и
дополнение, с разрешением наследования Name/ParentName) и в Patches/*.xml
(текст, внедряемый в чужие def-ы через PatchOperation*)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from . import patches, xml_io

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
class StringsTask:
    rel_path: Path          # относительный путь файла внутри Strings/
    data: xml_io.LanguageDataFile


@dataclass
class ScanResult:
    source_lang_dir: str | None   # "English" если найден, иначе None (fallback-режим)
    keyed: list[KeyedTask]
    def_injected: list[DefInjectedTask]
    strings: list[StringsTask] = field(default_factory=list)


def _find_languages_dir(mod_root: Path) -> Path | None:
    """Находит папку Languages согласованно с _resolve_content_roots:
    кандидаты внутри версионных папок (1.0/, 1.1/, ...), которые игра для
    новейшей поддерживаемой версии не грузит, отбрасываются. Раньше брался
    просто первый результат glob("**/Languages") — у мода с копиями
    1.4/Languages и 1.6/Languages алфавитный порядок обхода возвращал
    СТАРУЮ версию ("1.4" < "1.6"), и переводились устаревшие строки."""
    allowed_roots = {r.resolve() for r in _resolve_content_roots(mod_root)}

    def in_excluded_version_dir(candidate: Path) -> bool:
        prefix = mod_root
        for part in candidate.relative_to(mod_root).parts[:-1]:
            prefix = prefix / part
            if _VERSION_TAG_RE.match(part) and prefix.resolve() not in allowed_roots:
                return True
        return False

    candidates = [
        c for c in mod_root.glob("**/Languages")
        if c.is_dir() and not in_excluded_version_dir(c)
    ]
    if not candidates:
        return None
    # Из оставшихся берём наименее вложенную (обычно кандидат один);
    # сортировка по строке — лишь для детерминизма при равной глубине.
    return min(candidates, key=lambda c: (len(c.parts), str(c)))


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
    этой версии игры.

    Найдено на: alpha_memes. Пути с условием IfModActive (папки вида
    Mods/Biotech, Mods/Royalty, Mods/Anomaly — контент, зависящий от
    официальных DLC Ludeon или другого мода) раньше пропускались целиком,
    потому что у нас нет информации о списке модов/DLC пользователя. Но это
    означало, что весь DLC-специфичный контент крупных модов (типа Alpha
    Memes с отдельными подпапками под Biotech/Royalty/Anomaly/Ideology)
    НИКОГДА не переводился — даже если у игрока эти официальные DLC
    установлены и активны, что для большой части пользователей верно.
    Теперь такие пути включаются в сканирование безусловно: если DLC/мод
    реально не активны, лишние переведённые строки в выходном моде просто
    не используются игрой — не вредно, в отличие от полного отсутствия
    перевода контента, который реально показывается в игре.

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


def _content_subdirs(mod_root: Path, subdir_name: str) -> list[Path]:
    """Все существующие папки <content_root>/<subdir_name> по реально
    загружаемым корням (см. _resolve_content_roots), дедуплицированные по
    разрешённому абсолютному пути: разные content root могут указывать на
    одну и ту же физическую папку (напр. mod_root и mod_root/1.6).

    Берём подпапку только ПРЯМО под каждым корнем, БЕЗ рекурсивного
    "**/<subdir>" — рекурсивный поиск затягивал бы контент из вложенных
    путей, которые _resolve_content_roots специально исключил."""
    seen: dict[Path, Path] = {}
    for content_root in _resolve_content_roots(mod_root):
        candidate = content_root / subdir_name
        if candidate.is_dir():
            seen.setdefault(candidate.resolve(), candidate)
    return list(seen.values())


def _def_refs_by_file(mod_root: Path) -> list[tuple[Path, list[xml_io.DefFieldRef]]]:
    """Извлекает переводимые поля из всех Defs/*.xml мода, файл за файлом,
    с разрешением наследования Name/ParentName ПО ВСЕМ файлам сразу —
    родитель и наследник часто лежат в разных файлах, и текст, заданный
    только в абстрактном родителе, без этого терялся для наследников."""
    files_roots: list[tuple[Path, ET.Element]] = []
    for defs_dir in _content_subdirs(mod_root, "Defs"):
        for xml_file in sorted(defs_dir.rglob("*.xml")):
            root = xml_io.parse_defs_root(xml_file)
            if root is not None:
                files_roots.append((xml_file, root))

    registry = xml_io.build_inheritance_registry(root for _, root in files_roots)
    result: list[tuple[Path, list[xml_io.DefFieldRef]]] = []
    for xml_file, root in files_roots:
        refs = xml_io.extract_from_defs_root(root, registry)
        if refs:
            result.append((xml_file, refs))
    return result


def _ref_key(ref: xml_io.DefFieldRef) -> str:
    return f"{ref.def_name}.{ref.field_path}" if ref.field_path else ref.def_name


def _tasks_from_refs(refs_by_stem: dict[tuple[str, str], list[xml_io.DefFieldRef]]) -> list[DefInjectedTask]:
    result: list[DefInjectedTask] = []
    for (def_type, file_stem), refs in refs_by_stem.items():
        data = xml_io.LanguageDataFile()
        for ref in refs:
            data.entries.append(xml_io.Entry(key=_ref_key(ref), text=ref.text))
        result.append(DefInjectedTask(def_type=def_type, rel_path=Path(f"{file_stem}.xml"), data=data))
    return result


def _scan_defs_fallback(defs_refs: list[tuple[Path, list[xml_io.DefFieldRef]]]) -> list[DefInjectedTask]:
    """Раскладывает уже извлечённые поля (см. _def_refs_by_file) по задачам,
    сгруппированным по (DefType, имя файла) — так же, как их раскладывает по
    папкам DefInjected. Группировка по def_type КАЖДОЙ ссылки, а не первой в
    файле: один Defs-файл может смешивать несколько типов def-ов.

    Найдено на: makaitech_psycast (PsycasterPathDef из стороннего мода-
    фреймворка Vanilla Psycasts Expanded). Когда тег def-элемента был задан
    полным именем класса (ref.qualified_def_type — см.
    xml_io.extract_from_defs_root), нельзя статически определить, ждёт ли
    игра короткое имя папки DefInjected (обычный случай, когда мод просто
    снял неоднозначность namespace для СВОЕГО типа) или полное (когда сам
    класс определён в чужом моде-фреймворке, как VPE, и его собственный
    официальный русификатор называет папку полным путём) — без этого
    заголовки/тултипы путей психокастов молча оставались английскими, хотя
    перевод был сгенерирован под короткой, "неправильной" для игры папкой.
    Поэтому пишем перевод под ОБОИМИ именами; лишний файл-дубликат для игры
    безвреден, а его отсутствие вредило бы переводу."""
    grouped: dict[tuple[str, str], list[xml_io.DefFieldRef]] = {}
    for xml_file, refs in defs_refs:
        for ref in refs:
            grouped.setdefault((ref.def_type, xml_file.stem), []).append(ref)
            if ref.qualified_def_type:
                grouped.setdefault((ref.qualified_def_type, xml_file.stem), []).append(ref)
    return _tasks_from_refs(grouped)


def _current_defs_text_by_key(defs_refs: list[tuple[Path, list[xml_io.DefFieldRef]]]) -> dict[str, str]:
    """Плоский словарь {defName.field_path: актуальный английский текст} из
    Defs/*.xml (не из DefInjected) — используется, чтобы заметить случаи,
    когда автор мода обновил текст в Defs, но забыл синхронизировать
    Languages/English/DefInjected (см. scan_mod)."""
    return {_ref_key(ref): ref.text for _, refs in defs_refs for ref in refs}


def _scan_strings(english_dir: Path) -> list[StringsTask]:
    """Languages/English/Strings/*.txt — списки слов/имён для генераторов
    (по одной записи на строку). Перевод — файл с тем же относительным путём
    в папке целевого языка. Раньше этот канал не сканировался вовсе."""
    strings_dir = english_dir / "Strings"
    result: list[StringsTask] = []
    if not strings_dir.is_dir():
        return result
    for txt_file in sorted(strings_dir.rglob("*.txt")):
        rel = txt_file.relative_to(strings_dir)
        data = xml_io.parse_strings_file(txt_file, key_prefix=f"Strings/{rel.as_posix()}")
        if data.keyed_items():
            result.append(StringsTask(rel_path=rel, data=data))
    return result


def _apply_patches(mod_root: Path, def_injected: list[DefInjectedTask]) -> None:
    """Вносит в результат сканирования текст из Patches/*.xml (см. patches.py).
    Патчи применяются игрой ПОВЕРХ Defs, поэтому для уже найденных ключей
    пропатченный текст побеждает; ключи чужих def-ов (патчи на игру/DLC/другие
    моды) добавляются новыми задачами, сгруппированными по (DefType, имя
    файла патча)."""
    refs_by_stem: dict[str, list[xml_io.DefFieldRef]] = {}
    for patches_dir in _content_subdirs(mod_root, "Patches"):
        for xml_file in sorted(patches_dir.rglob("*.xml")):
            refs = patches.extract_translatable_from_patch(xml_file)
            if refs:
                refs_by_stem.setdefault(xml_file.stem, []).extend(refs)
    if not refs_by_stem:
        return

    # Последний патч по ключу побеждает — как при последовательном применении.
    patched_by_key: dict[str, xml_io.DefFieldRef] = {
        _ref_key(ref): ref
        for refs in refs_by_stem.values()
        for ref in refs
    }

    covered_keys: set[str] = set()
    for task in def_injected:
        for entry in task.data.keyed_items():
            ref = patched_by_key.get(entry.key)
            if ref is not None:
                entry.text = ref.text
                covered_keys.add(entry.key)

    grouped: dict[tuple[str, str], list[xml_io.DefFieldRef]] = {}
    seen_new_keys: set[str] = set()
    for file_stem, refs in refs_by_stem.items():
        for ref in refs:
            key = _ref_key(ref)
            if key in covered_keys or key in seen_new_keys:
                continue
            seen_new_keys.add(key)
            grouped.setdefault((ref.def_type, file_stem), []).append(ref)
    def_injected.extend(_tasks_from_refs(grouped))


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
    strings: list[StringsTask] = []
    defs_refs = _def_refs_by_file(mod_root)

    if english_dir is None:
        # Нет Languages/English вообще — извлекаем всё прямо из Defs/*.xml.
        def_injected = _scan_defs_fallback(defs_refs)
        _apply_patches(mod_root, def_injected)
        return ScanResult(source_lang_dir=None, keyed=keyed, def_injected=def_injected)

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
    for task in _scan_defs_fallback(defs_refs):
        if task.def_type not in covered_def_types:
            def_injected.append(task)

    # Некоторые моды обновляют текст (label/description/...) прямо в
    # Defs/*.xml, но забывают синхронизировать Languages/English/DefInjected
    # — RimWorld при этом показывает игроку АКТУАЛЬНЫЙ текст из Defs (мод
    # celetech_shuttle_extension: label "Cockpit" в Defs против устаревшего
    # "cockpit segment" в DefInjected). Если бы мы перевели устаревший текст
    # из DefInjected, игрок в итоге видел бы английский оригинал (раз перевод
    # не совпадает с тем, что мод ожидает подставить) или откровенно
    # устаревший, не соответствующий игре перевод. Поэтому для каждого ключа,
    # где Defs и DefInjected расходятся, подставляем актуальный текст из Defs.
    current_defs_text = _current_defs_text_by_key(defs_refs)
    if current_defs_text:
        for task in def_injected:
            for entry in task.data.keyed_items():
                current = current_defs_text.get(entry.key)
                if current is not None and current != entry.text:
                    entry.text = current

    # Патчи применяются игрой поверх Defs — поэтому в самом конце, чтобы
    # пропатченный текст победил и Defs, и устаревший DefInjected.
    _apply_patches(mod_root, def_injected)

    strings = _scan_strings(english_dir)

    return ScanResult(source_lang_dir="English", keyed=keyed,
                      def_injected=def_injected, strings=strings)
