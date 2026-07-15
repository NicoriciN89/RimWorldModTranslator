"""Чтение и запись RimWorld LanguageData XML (Keyed / DefInjected) с сохранением
порядка ключей, комментариев-разделителей и оригинального форматирования тегов.

Что считать переводимым текстом при извлечении из Defs/*.xml — не решается
здесь напрямую, см. rimworld_rules.py (база знаний с примерами модов, на
которых найдено каждое правило)."""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from . import rimworld_rules

_XML_DECL = '<?xml version="1.0" encoding="utf-8"?>\n'


@dataclass
class Entry:
    key: str
    text: str
    is_comment: bool = False
    # Английский оригинал строки, сохранённый ДО того, как text заменяется
    # переводом — используется только для необязательного комментария
    # <!--EN: ...--> в выходном файле (см. write_language_data), чтобы можно
    # было визуально сверить перевод с оригиналом без похода в исходный мод.
    original_text: str | None = None


@dataclass
class LanguageDataFile:
    """Одно значение из <LanguageData>...</LanguageData> — либо запись key/text,
    либо XML-комментарий (сохраняется как есть, не переводится)."""
    entries: list[Entry] = field(default_factory=list)
    has_bom: bool = False

    def keyed_items(self):
        return [e for e in self.entries if not e.is_comment]


def parse_language_data(path: Path) -> LanguageDataFile:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    if has_bom:
        raw = raw[3:]

    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.fromstring(raw, parser=parser)

    result = LanguageDataFile(has_bom=has_bom)
    for child in root:
        if child.tag is ET.Comment:
            result.entries.append(Entry(key="", text=child.text or "", is_comment=True))
        else:
            result.entries.append(Entry(key=child.tag, text=child.text or "", is_comment=False))
    return result


_ESCAPE_MAP = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
)


def _escape_text(text: str) -> str:
    for src, dst in _ESCAPE_MAP:
        text = text.replace(src, dst)
    return text


def _sanitize_comment(text: str) -> str:
    """Спецификация XML запрещает "--" внутри комментария целиком (не только
    "-->") и "-" в самом его конце — текст вроде "some -- note" в комментарии
    делал весь выходной файл невалидным. Разбавляем сдвоенные дефисы пробелом;
    цикл нужен, потому что "---" после одной замены снова содержит "--"."""
    while "--" in text:
        text = text.replace("--", "- -")
    if text.endswith("-"):
        text += " "
    return text


def write_language_data(path: Path, data: LanguageDataFile, with_original_comments: bool = False) -> None:
    lines = [_XML_DECL, "<LanguageData>\n"]
    for entry in data.entries:
        if entry.is_comment:
            lines.append(f"  <!--{_sanitize_comment(entry.text)}-->\n")
        else:
            if with_original_comments and entry.original_text is not None and entry.original_text != entry.text:
                lines.append(f"  <!--EN: {_sanitize_comment(entry.original_text)}-->\n")
            lines.append(f"  <{entry.key}>{_escape_text(entry.text)}</{entry.key}>\n")
    lines.append("</LanguageData>\n")

    content = "".join(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = content.encode("utf-8")
    if data.has_bom:
        encoded = b"\xef\xbb\xbf" + encoded
    path.write_bytes(encoded)


# --- Извлечение переводимых строк напрямую из Defs/*.xml (fallback, когда у мода
# нет Languages/English) ---------------------------------------------------
#
# Что считается переводимым текстом — см. rimworld_rules.py.


@dataclass
class DefFieldRef:
    def_type: str
    def_name: str
    field_path: str
    text: str


def _walk_def(el: ET.Element, def_type: str, def_name: str, path_prefix: str,
              out: list[DefFieldRef]) -> None:
    for child in el:
        if child.tag is ET.Comment:
            continue
        tag = child.tag
        cur_path = f"{path_prefix}.{tag}" if path_prefix else tag
        list_children = [c for c in child if c.tag is not ET.Comment]
        if list_children and all(c.tag == "li" for c in list_children):
            for idx, li in enumerate(list_children):
                li_grandchildren = [c for c in li if c.tag is not ET.Comment]
                if li_grandchildren:
                    _walk_def(li, def_type, def_name, f"{cur_path}.{idx}", out)
                    continue
                li_text = li.text or ""
                li_path = f"{cur_path}.{idx}"
                if rimworld_rules.is_rule_string(tag, li_text) or \
                        rimworld_rules.is_translatable_field(tag, li_text):
                    out.append(DefFieldRef(def_type, def_name, li_path, li_text))
            continue
        if list_children:
            _walk_def(child, def_type, def_name, cur_path, out)
        elif rimworld_rules.is_translatable_field(tag, child.text or ""):
            out.append(DefFieldRef(def_type, def_name, cur_path, child.text))


def parse_defs_root(path: Path) -> ET.Element | None:
    """Читает произвольный XML-файл мода (Defs, Patches...) с учётом BOM;
    невалидный XML не роняет сканирование, а просто пропускается."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return None


# --- Наследование Name/ParentName между def-элементами ----------------------
#
# RimWorld позволяет выносить общие поля (в т.ч. label/description) в
# абстрактного родителя: <ThingDef Name="ABase" Abstract="True"> задаёт
# шаблон, а <ThingDef ParentName="ABase"> наследует все его поля, которых
# не переопределил сам. Игра переводит УЖЕ разрешённый def — поэтому текст,
# заданный только в родителе, всё равно нужно перевести под ключом каждого
# конкретного def-а. Без разрешения наследования такие строки терялись.


def build_inheritance_registry(roots: Iterable[ET.Element]) -> dict[str, ET.Element]:
    """{значение атрибута Name: def-элемент} по всем переданным <Defs>-корням
    — родитель и наследник часто лежат в РАЗНЫХ файлах мода."""
    registry: dict[str, ET.Element] = {}
    for root in roots:
        for def_el in root:
            if def_el.tag is ET.Comment:
                continue
            name = def_el.attrib.get("Name")
            if name:
                registry.setdefault(name, def_el)
    return registry


def _merge_inherited(child: ET.Element, parent: ET.Element) -> ET.Element:
    """Рекурсивное слияние def-элемента с (уже разрешённым) родителем по
    правилам RimWorld XmlInheritance: текст наследника побеждает, недостающие
    узлы берутся у родителя, li-списки объединяются (родительские элементы
    первыми — от этого зависят числовые индексы в DefInjected-ключах),
    атрибут Inherit="False" на узле отключает наследование его содержимого."""
    if child.attrib.get("Inherit", "").lower() == "false":
        return child
    child_elems = [c for c in child if c.tag is not ET.Comment]
    parent_elems = [p for p in parent if p.tag is not ET.Comment]
    if not parent_elems:
        return child
    if not child_elems:
        if (child.text or "").strip():
            return child
        merged = ET.Element(child.tag, dict(child.attrib))
        for p in parent_elems:
            merged.append(copy.deepcopy(p))
        return merged

    merged = ET.Element(child.tag, dict(child.attrib))
    if all(c.tag == "li" for c in child_elems) and all(p.tag == "li" for p in parent_elems):
        for p in parent_elems:
            merged.append(copy.deepcopy(p))
        for c in child_elems:
            merged.append(copy.deepcopy(c))
        return merged

    parent_by_tag: dict[str, ET.Element] = {}
    for p in parent_elems:
        parent_by_tag.setdefault(p.tag, p)
    child_tags = {c.tag for c in child_elems}
    for c in child_elems:
        p = parent_by_tag.get(c.tag)
        merged.append(_merge_inherited(c, p) if p is not None else copy.deepcopy(c))
    for p in parent_elems:
        if p.tag not in child_tags:
            merged.append(copy.deepcopy(p))
    return merged


def resolve_inheritance(def_el: ET.Element, registry: dict[str, ET.Element],
                        _seen: frozenset[str] = frozenset()) -> ET.Element:
    """Возвращает def-элемент со всеми полями, унаследованными по цепочке
    ParentName (включая прародителей). Родители из самой игры или других
    модов в registry отсутствуют — тогда элемент возвращается как есть
    (типичный случай ParentName="BuildingBase" из ванильного Core: свои
    label/description такие базовые шаблоны не задают). _seen защищает от
    цикла ParentName в битом моде."""
    parent_name = def_el.attrib.get("ParentName")
    if not parent_name or parent_name in _seen:
        return def_el
    parent = registry.get(parent_name)
    if parent is None:
        return def_el
    resolved_parent = resolve_inheritance(parent, registry, _seen | {parent_name})
    return _merge_inherited(def_el, resolved_parent)


def extract_from_defs_root(root: ET.Element, registry: dict[str, ET.Element]) -> list[DefFieldRef]:
    out: list[DefFieldRef] = []
    for def_el in root:
        if def_el.tag is ET.Comment:
            continue
        # Abstract="True" — шаблон для наследования, в игре не существует
        # и не переводится (его текст попадёт в перевод через наследников).
        if def_el.attrib.get("Abstract", "").lower() == "true":
            continue
        # RimWorld разрешает полностью квалифицированное имя класса как тег
        # def-элемента (напр. <My.Namespace.FooDef>...</My.Namespace.FooDef>),
        # когда имя класса неоднозначно между несколькими using-namespace'ами.
        # Игра трактует его как обычный FooDef, и DefInjected-папка мода
        # называется по короткому имени (последний сегмент) — без этого мы
        # создавали бы отдельную (дублирующую) DefInjected-папку с полным
        # путём вместо короткого имени, которое ожидает игра.
        def_type = def_el.tag.rsplit(".", 1)[-1]
        name_el = def_el.find("defName")
        def_name = name_el.text.strip() if name_el is not None and name_el.text else None
        if not def_name:
            continue
        resolved = resolve_inheritance(def_el, registry)
        _walk_def(resolved, def_type, def_name, "", out)
    return out


def extract_translatable_from_defs(path: Path) -> list[DefFieldRef]:
    """Извлечение из одного файла — наследование разрешается только внутри
    него. Для межфайлового наследования сканер (scanner._def_refs_by_file)
    строит общий registry по всем Defs-файлам мода и вызывает
    extract_from_defs_root напрямую."""
    root = parse_defs_root(path)
    if root is None:
        return []
    return extract_from_defs_root(root, build_inheritance_registry([root]))


# --- Languages/<Lang>/Strings/*.txt (списки слов для генераторов имён) ------
#
# Формат: по одной записи на строку; пустые строки и строки, начинающиеся
# с "//", — не записи. Перевод — файл с тем же относительным путём в папке
# целевого языка, строка в строку.


def parse_strings_file(path: Path, key_prefix: str) -> LanguageDataFile:
    """Читает txt-файл в ту же структуру LanguageDataFile, что и XML: каждая
    содержательная строка становится Entry с ключом "{key_prefix}:{номер}"
    (номер строки в файле — стабилен, потому что при записи сохраняются ВСЕ
    строки, включая комментарии и пустые), остальные — is_comment-записями,
    которые переносятся в вывод буквально."""
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    if has_bom:
        raw = raw[3:]
    data = LanguageDataFile(has_bom=has_bom)
    for idx, line in enumerate(raw.decode("utf-8", errors="replace").splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            data.entries.append(Entry(key="", text=line, is_comment=True))
        else:
            data.entries.append(Entry(key=f"{key_prefix}:{idx}", text=line))
    return data


def write_strings_file(path: Path, data: LanguageDataFile) -> None:
    lines = [entry.text for entry in data.entries]
    content = "\n".join(lines) + ("\n" if lines else "")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = content.encode("utf-8")
    if data.has_bom:
        encoded = b"\xef\xbb\xbf" + encoded
    path.write_bytes(encoded)
