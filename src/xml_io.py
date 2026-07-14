"""Чтение и запись RimWorld LanguageData XML (Keyed / DefInjected) с сохранением
порядка ключей, комментариев-разделителей и оригинального форматирования тегов.

Что считать переводимым текстом при извлечении из Defs/*.xml — не решается
здесь напрямую, см. rimworld_rules.py (база знаний с примерами модов, на
которых найдено каждое правило)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

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


def write_language_data(path: Path, data: LanguageDataFile, with_original_comments: bool = False) -> None:
    lines = [_XML_DECL, "<LanguageData>\n"]
    for entry in data.entries:
        if entry.is_comment:
            lines.append(f"  <!--{entry.text}-->\n")
        else:
            if with_original_comments and entry.original_text is not None and entry.original_text != entry.text:
                safe_original = entry.original_text.replace("-->", "--&gt;")
                lines.append(f"  <!--EN: {safe_original}-->\n")
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


def extract_translatable_from_defs(path: Path) -> list[DefFieldRef]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    out: list[DefFieldRef] = []
    for def_el in root:
        if def_el.tag is ET.Comment:
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
        _walk_def(def_el, def_type, def_name, "", out)
    return out
