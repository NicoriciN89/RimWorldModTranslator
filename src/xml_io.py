"""Чтение и запись RimWorld LanguageData XML (Keyed / DefInjected) с сохранением
порядка ключей, комментариев-разделителей и оригинального форматирования тегов."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

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

# Теги, которые НИКОГДА не содержат переводимый текст, даже если их значение
# формально проходит по эвристике ниже — это ссылки на другие defName/классы/
# идентификаторы, а не человеческий текст, и переводить их означало бы сломать
# ссылку на определение в другом месте мода/игры.
_NEVER_TRANSLATABLE_TAGS = {
    "defname", "class", "parentname", "workertype", "compclass", "thingclass",
    "texpath", "graphicclass", "shaderclass", "soundtype", "drawertype",
    "researchviewx", "researchviewy", "packageid", "identifier", "hediff",
    "def", "recipeuser", "thingdef", "damagedef", "statdef", "verbclass",
    "jobdef", "workgiverdef", "traitdef", "genedef", "driverclass",
    "jobclass", "compclass", "workgiverclass", "mentalstateclass",
    "incidentclass", "gizmoclass", "interactionclass",
    # QuestScriptDef/квест-нода — служебные ссылки на переменные квеста
    # ($siteTile, $rewardValue...) и параметры узлов, не текст для игрока.
    "storeas", "tile", "faction", "sitepartdefs", "worldobject", "worldobjects",
    "insignal", "outsignal", "delayticks", "value1", "value2",
    "storesitepartsparamsas", "sitepartsparams",
}

# QuestScriptDef.*.rulesStrings хранит строки вида "ruleKey->текст" — только
# часть после "->" может быть человеческим текстом, сам ключ до стрелки это
# идентификатор правила генерации (напр. "distress->Distress Call").
_RULE_STRING_RE = re.compile(r"^([\w.\[\]]+)->(.*)$", re.DOTALL)

# Баг из celetech_shuttle_extension: поля вида moduleTypeID, slotTypeID,
# segmentTypeID и списки installableSegmentTypes/installableModuleSlotTypes/
# installableModuleTypes/installableSegmentSlotTypes хранят строковые
# идентификаторы enum-подобного типа (напр. "cockpit", "support", "cargo"),
# используемые модом для сопоставления модулей с посадочными местами — а не
# текст для игрока. Их значения однословные и в нижнем регистре, поэтому
# основная эвристика (PascalCase-идентификатор) их не отлавливала и
# переводила — после чего мод переставал находить нужный тип и падал в лог с
# "defines unknown moduleTypeID unknown" при загрузке. Имя тега — надёжный
# сигнал здесь, независимо от формы значения.
_ID_LIKE_TAG_RE = re.compile(r"TypeID$|SlotID$", re.IGNORECASE)
_NEVER_TRANSLATABLE_TAG_PATTERNS = (
    "installablesegmenttypes", "installablemoduleslottypes",
    "installablemoduletypes", "installablesegmentslottypes",
)

# defName-ссылки внутри списков (<recipeUsers><li>FabricationBench</li></...>)
# обычно PascalCase-идентификаторы без пробелов и строчных служебных слов —
# в отличие от настоящего текста вида "make bio clip" или "Making bio clip.".
_LOOKS_LIKE_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
# Составной идентификатор вида Namespace.ClassName / My.Nested.Class — типично
# для driverClass/compClass и подобных ссылок на C#-типы, которые не всегда
# заранее известны и не попадают в _NEVER_TRANSLATABLE_TAGS по имени тега.
_LOOKS_LIKE_DOTTED_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
_LOOKS_LIKE_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?%?$")
_LOOKS_LIKE_PATH_OR_COLOR_RE = re.compile(r"^[\w/\\.]+$|^#[0-9A-Fa-f]{3,8}$")


def _looks_translatable(tag: str, text: str) -> bool:
    """Эвристика "это человеческий текст, а не идентификатор/число/путь":
    вместо белого списка конкретных имён тегов (который никогда не покрыл бы
    все поля всех модов) проверяем сам текст. Явные технические теги
    (defName, class, texPath...) исключены заранее списком выше, даже если
    их значение случайно похоже на текст."""
    tag_lower = tag.lower()
    if tag_lower in _NEVER_TRANSLATABLE_TAGS:
        return False
    if _ID_LIKE_TAG_RE.search(tag) or tag_lower in _NEVER_TRANSLATABLE_TAG_PATTERNS:
        return False
    if not text or not text.strip():
        return False
    stripped = text.strip()
    if _LOOKS_LIKE_NUMBER_RE.match(stripped):
        return False
    if stripped.lower() in ("true", "false"):
        return False
    if _LOOKS_LIKE_PATH_OR_COLOR_RE.match(stripped) and "/" in stripped or "\\" in stripped:
        return False
    if _LOOKS_LIKE_DOTTED_IDENTIFIER_RE.match(stripped):
        return False
    if " " in stripped:
        return True
    # Однословные значения: отличаем обычное капитализированное слово
    # ("Cockpit", "Wall" — единственная заглавная буква, в начале) от
    # настоящего PascalCase/camelCase идентификатора ("ShuttleReactorModuleDef"
    # — несколько заглавных букв, "горбов" из нескольких слов, склеенных
    # воедино). Баг из celetech_shuttle_extension: <label>Cockpit</label>
    # ошибочно считалось идентификатором и не переводилось, потому что
    # старая проверка смотрела только на первую букву, а не на форму слова
    # целиком — RimWorld сплошь и рядом пишет однословные label с большой
    # буквы, это не идентификатор.
    if _LOOKS_LIKE_IDENTIFIER_RE.match(stripped) and stripped.isalnum():
        has_inner_capital = any(c.isupper() for c in stripped[1:])
        if stripped[0].isupper() and has_inner_capital:
            return False
    return True


@dataclass
class DefFieldRef:
    def_type: str
    def_name: str
    field_path: str
    text: str


def _is_rule_string(tag: str, text: str) -> bool:
    """rulesStrings хранит "ключ->текст" (напр. "distress->Distress Call") —
    сама строка возвращается целиком как обычный DefFieldRef, а защита
    идентификатора-ключа от перевода происходит в translator.py тем же
    способом, что и для плейсхолдеров {0}/{species}."""
    return tag.lower() == "rulesstrings" and bool(_RULE_STRING_RE.match(text))


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
                if _is_rule_string(tag, li_text) or _looks_translatable(tag, li_text):
                    out.append(DefFieldRef(def_type, def_name, li_path, li_text))
            continue
        if list_children:
            _walk_def(child, def_type, def_name, cur_path, out)
        elif _looks_translatable(tag, child.text or ""):
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
