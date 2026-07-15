"""Извлечение переводимого текста из Patches/*.xml (PatchOperation*).

Многие моды не создают собственные Defs, а внедряют или меняют текст ЧУЖИХ
def-ов (из игры, DLC или других модов) через патчи: PatchOperationAdd /
PatchOperationReplace / PatchOperationInsert с xpath-адресом и <value> с
новыми XML-узлами. Такой текст реально показывается игроку, и DefInjected-
перевод для него работает как обычно (DefInjected глобален по DefType и
defName, не важно, какой мод определил сам def) — но раньше папка Patches/
не сканировалась вообще, и весь этот текст молча терялся.

Полный разбор xpath не нужен и не безопасен: поддерживаются типовые формы
"Defs/ThingDef[defName=\"X\"]/поле/подполе" (включая несколько defName через
or и индексы li[N]); всё более хитрое пропускается — лучше пропустить
редкий сложный патч, чем сгенерировать неверный DefInjected-ключ.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .xml_io import DefFieldRef, _walk_def, parse_defs_root

# Операции, чей <value> может содержать текст для игрока. Insert вставляет
# value РЯДОМ с узлом по xpath (как sibling), Replace — ВМЕСТО него: в обоих
# случаях итоговое место значения — родитель узла из xpath. Add добавляет
# value ВНУТРЬ узла по xpath.
_TEXT_OPERATIONS = frozenset({
    "PatchOperationAdd", "PatchOperationReplace", "PatchOperationInsert",
})

_XPATH_RE = re.compile(r"^/?Defs/([\w.]+)\[([^\]]+)\](?:/(.+))?$")
_XPATH_DEFNAME_RE = re.compile(r"""defName\s*=\s*["']([^"']+)["']""")
# xpath-индексы 1-базные (li[3] — третий элемент), DefInjected-ключи 0-базные.
_LI_INDEX_RE = re.compile(r"^li\[(\d+)\]$")
_PLAIN_SEGMENT_RE = re.compile(r"^\w+$")


def _parse_xpath(xpath: str) -> tuple[str, list[str], list[str]] | None:
    """Разбирает типовой xpath патча в (def_type, [defName...], [сегменты
    пути внутри def-а]). Возвращает None для форм, по которым нельзя надёжно
    построить DefInjected-ключ (Defs/*[...], предикаты по label и т.п.)."""
    m = _XPATH_RE.match(xpath.strip())
    if m is None:
        return None
    def_tag, predicate, rest = m.groups()
    def_type = def_tag.rsplit(".", 1)[-1]
    # Несколько defName в одном предикате (через or) — патч применяется к
    # каждому из них, и перевод нужен под ключом каждого.
    def_names = _XPATH_DEFNAME_RE.findall(predicate)
    if not def_names:
        return None
    parts: list[str] = []
    if rest:
        for segment in rest.split("/"):
            li = _LI_INDEX_RE.match(segment)
            if li:
                parts.append(str(int(li.group(1)) - 1))
            elif segment == "li":
                # Найдено на: more_informative_ideology, cables_and_plumbing.
                # "Голый" li без индекса (xpath вида .../associatedMemes/li)
                # выбирает ВСЕ элементы списка — позиция в итоговом списке
                # статически неизвестна, а ключ с буквальным ".li" невалиден
                # для DefInjected. Пропускаем всю операцию.
                return None
            elif _PLAIN_SEGMENT_RE.match(segment):
                parts.append(segment)
            else:
                return None
    return def_type, def_names, parts


def _extract_value(value_el: ET.Element, def_type: str, def_name: str,
                   prefix_parts: list[str], out: list[DefFieldRef]) -> None:
    """Обходит содержимое <value> той же логикой, что и обычный def
    (xml_io._walk_def) — _walk_def ждёт элемент, ДЕТИ которого являются
    полями (определение li-списков происходит на уровень ниже), поэтому
    дети value собираются в обёртку и передаются одним вызовом, а не
    контейнер за контейнером (иначе li попадал в путь буквально:
    "stuffCategories.li" вместо "stuffCategories.0")."""
    fields_wrapper = ET.Element("value")
    for child in value_el:
        if child.tag is ET.Comment:
            continue
        if child.tag == "li":
            # Добавление элементов в существующий список: итоговый индекс li
            # зависит от длины списка ПОСЛЕ всех прочих патчей и наследования —
            # статически он неизвестен, неверный ключ хуже пропуска.
            continue
        if not prefix_parts and child.find("defName") is not None:
            # value содержит целый def (замена def-а целиком) — обходим его
            # как обычный def, с его собственными типом и defName.
            name_el = child.find("defName")
            inner_name = name_el.text.strip() if name_el.text else None
            if inner_name:
                _walk_def(child, child.tag.rsplit(".", 1)[-1], inner_name, "", out)
            continue
        fields_wrapper.append(child)
    if len(fields_wrapper):
        _walk_def(fields_wrapper, def_type, def_name, ".".join(prefix_parts), out)


def extract_translatable_from_patch(path: Path) -> list[DefFieldRef]:
    root = parse_defs_root(path)
    if root is None:
        return []

    out: list[DefFieldRef] = []
    # Обход ВСЕХ потомков, а не только детей корня: операции вкладываются в
    # PatchOperationSequence (<operations><li Class=...>), PatchOperationFindMod
    # и PatchOperationConditional (<match>/<nomatch Class=...>) на любую
    # глубину — фильтр по атрибуту Class ловит их все единообразно. Патчи с
    # условиями (FindMod и т.п.) извлекаются безусловно — по той же логике,
    # что IfModActive в LoadFolders.xml: лишний перевод неактивного контента
    # безвреден, в отличие от отсутствия перевода активного.
    for op_el in root.iter():
        op_class = op_el.attrib.get("Class", "").rsplit(".", 1)[-1]
        if op_class not in _TEXT_OPERATIONS:
            continue
        xpath = op_el.findtext("xpath") or ""
        value_el = op_el.find("value")
        if not xpath or value_el is None:
            continue
        parsed = _parse_xpath(xpath)
        if parsed is None:
            continue
        def_type, def_names, parts = parsed
        if op_class in ("PatchOperationReplace", "PatchOperationInsert") and parts:
            parts = parts[:-1]
        for def_name in def_names:
            _extract_value(value_el, def_type, def_name, parts, out)
    return out
