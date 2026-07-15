"""База знаний о том, что в XML-модах RimWorld является переводимым текстом,
а что — техническими данными (идентификаторы, плейсхолдеры, пути, grammar-
токены), которые нельзя трогать при переводе.

Это НЕ код перевода сам по себе — xml_io.py (что извлекать из Defs/*.xml) и
translator.py (что защищать от Argos/LLM при переводе одной строки) читают
эти правила отсюда. Смысл выделения в отдельный модуль: каждое правило тут
найдено на реальном моде из-за реального бага (см. комментарий с примером
мода при каждом правиле) — при добавлении нового правила для нового мода
проверяй сначала здесь, нет ли уже подходящей категории, вместо ещё одного
разрозненного regex внутри xml_io.py/translator.py.

Общий принцип категоризации поля <tag>значение</tag> в Defs/*.xml:
1. Тег в NEVER_TRANSLATABLE_TAGS / TYPE_ID_TAG_SUFFIXES / NEVER_TRANSLATABLE_TAG_KEYWORDS
   -> никогда не текст, независимо от того, как выглядит значение.
2. Значение похоже на число/true-false/чистый путь-или-цвет/составной
   Namespace.Class идентификатор -> не текст.
3. Однословное значение, где ЕСТЬ пробел -> текст.
4. Однословное значение без пробела: PascalCase из НЕСКОЛЬКИХ слов подряд
   (несколько заглавных букв внутри) -> идентификатор, не текст.
   Одно капитализированное слово ("Cockpit") ИЛИ полностью строчное
   ("cockpit") -> текст.
"""
from __future__ import annotations

import re

# --- Теги, которые никогда не содержат переводимый текст --------------------
#
# Это ссылки на другие defName/классы/идентификаторы, а не человеческий
# текст — перевод сломал бы ссылку на определение в другом месте мода/игры.
NEVER_TRANSLATABLE_TAGS: frozenset[str] = frozenset({
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
    # Найдено на: rustic_workbenches и cables_and_plumbing (stuffCategories:
    # "Stony", "Med_Cables"), more_informative_ideology (associatedMemes:
    # "Guilty"), alpha_memes (styles: "Morbid", "Techist" — ссылки на
    # StyleCategoryDef). Списки ссылок на defName других def-ов — их элементы
    # однословные и похожи на обычные слова, поэтому эвристика по форме
    # значения их не отлавливает; блокируем по имени тега-контейнера.
    "stuffcategories", "thingcategories", "associatedmemes", "conflictingmemes",
    "styles",
    # Найдено на: rustic_workbenches (Patches: altitudeLayer "Building") —
    # enum-значение движка, не текст.
    "altitudelayer",
    # Найдено на: alpha_memes (PreceptDef: impact "low"/"medium"/"high") —
    # enum PreceptImpact; перевод значения даёт ошибку DefInjected в логе
    # игры (поле не строковое), а игра переводит его сама через Keyed.
    "impact",
})

# Найдено на: celetech_shuttle_extension.
# Поля вида moduleTypeID, slotTypeID, segmentTypeID хранят строковые
# идентификаторы enum-подобного типа (напр. "cockpit", "support", "cargo"),
# используемые модом для сопоставления модулей с посадочными местами — не
# текст для игрока. Их значения однословные и в нижнем регистре, поэтому
# общая эвристика по форме значения (PascalCase-идентификатор) их не
# отлавливала — мод переставал находить нужный тип и падал в лог RimWorld с
# "defines unknown moduleTypeID unknown" при загрузке.
# "DefName" — найдено на: celetech_shuttle_extension (Patches:
# integrationDefName) — суффикс явно ссылается на defName другого def-а.
TYPE_ID_TAG_SUFFIXES: tuple[str, ...] = ("TypeID", "SlotID", "DefName")

# Найдено на: celetech_shuttle_extension.
# Списки installableSegmentTypes/installableModuleSlotTypes/... — та же
# природа, что TYPE_ID_TAG_SUFFIXES (enum-подобные идентификаторы слотов),
# но имя тега не оканчивается на TypeID/SlotID, поэтому нужен отдельный
# список точных имён.
NEVER_TRANSLATABLE_TAG_KEYWORDS: frozenset[str] = frozenset({
    "installablesegmenttypes", "installablemoduleslottypes",
    "installablemoduletypes", "installablesegmentslottypes",
})


def is_never_translatable_tag(tag: str) -> bool:
    """True, если сам по себе тег `tag` гарантированно не текст для игрока,
    независимо от того, как выглядит его значение."""
    tag_lower = tag.lower()
    if tag_lower in NEVER_TRANSLATABLE_TAGS:
        return True
    if tag_lower in NEVER_TRANSLATABLE_TAG_KEYWORDS:
        return True
    return any(tag.endswith(suffix) for suffix in TYPE_ID_TAG_SUFFIXES)


# --- Эвристики по форме значения --------------------------------------------

# defName-ссылки внутри списков (<recipeUsers><li>FabricationBench</li></...>)
# обычно PascalCase-идентификаторы без пробелов и строчных служебных слов —
# в отличие от настоящего текста вида "make bio clip" или "Making bio clip.".
_LOOKS_LIKE_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# Составной идентификатор вида Namespace.ClassName / My.Nested.Class —
# типично для driverClass/compClass и подобных ссылок на C#-типы, которые не
# всегда заранее известны и не попадают в NEVER_TRANSLATABLE_TAGS по имени тега.
_LOOKS_LIKE_DOTTED_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")

_LOOKS_LIKE_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?%?$")

# Путь (напр. "UI/Structures/AM_Neolithic") — ВЕСЬ текст должен состоять
# только из символов пути И реально содержать разделитель (иначе однословные
# label'ы вроде "Wall" тоже совпали бы с [\w.]+ и ложно считались бы путём).
# Дефис в наборе — найдено на: celetech_shuttle_extension (Patches:
# runtimeSystemKey "celetech.shuttle.extension.integrations/bhlite-hygiene-
# runtime"); безопасно, потому что отбрасывание всё равно требует наличия
# слэша, а настоящий текст со слэшем внутри содержит и пробелы.
_LOOKS_LIKE_PATH_RE = re.compile(r"^[\w/\\.-]+$")
# HEX-цвет (напр. "#E5E54C") — самостоятельная альтернатива, без слэша.
_LOOKS_LIKE_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{3,8}$")


def is_translatable_value(text: str) -> bool:
    """Эвристика "это человеческий текст, а не идентификатор/число/путь",
    БЕЗ учёта имени тега (для этого есть is_never_translatable_tag — вызови
    её первой). Раздельно на две функции, потому что в rulesStrings-списках
    (Grammar/RulePack) тег общий на весь список ("rulesStrings"), а
    транслируемость каждого <li> внутри зависит только от его значения."""
    if not text or not text.strip():
        return False
    stripped = text.strip()

    if _LOOKS_LIKE_NUMBER_RE.match(stripped):
        return False
    if stripped.lower() in ("true", "false"):
        return False

    # Найдено на: rustic_workbenches (Patches: drawSize "(5,3)"). Значение
    # вообще без букв — векторы/кортежи/чистая пунктуация, не текст.
    if not any(c.isalpha() for c in stripped):
        return False

    # Найдено на: cables_and_plumbing (Patches: stuffCategories "Med_Cables"),
    # celetech_shuttle_extension ("CT_Shuttle_CE_Projectile_6mmAP").
    # Однословное значение с подчёркиванием — идентификатор: в настоящем
    # тексте для игрока подчёркиваний внутри слова не бывает, а проверка
    # PascalCase ниже такие значения не ловила (isalnum() False из-за "_").
    if "_" in stripped and " " not in stripped:
        return False

    # Найдено на: alpha_memes. Баг был в проверке без скобок:
    # "regex.match(text) and '/' in text or '\\' in text" — из-за приоритета
    # операторов это парсилось как (regex AND '/') OR '\\', то есть ЛЮБОЙ
    # текст с обратным слэшем ГДЕ УГОДНО (напр. буквальный "\n\n" внутри
    # длинного multi-line description с rich-text разметкой) целиком
    # отбрасывался как "похоже на путь" — даже описания на десятки слов.
    # Путь — это когда ВЕСЬ текст целиком состоит только из символов пути И
    # реально содержит разделитель, а не просто похож на путь по алфавиту
    # символов (иначе однословные значения без пробелов ложно считались бы
    # путём) и не просто содержит слэш где-то внутри длинной фразы.
    if _LOOKS_LIKE_PATH_RE.match(stripped) and ("/" in stripped or "\\" in stripped):
        return False
    if _LOOKS_LIKE_COLOR_RE.match(stripped):
        return False

    if _LOOKS_LIKE_DOTTED_IDENTIFIER_RE.match(stripped):
        return False

    if " " in stripped:
        return True

    # Найдено на: celetech_shuttle_extension. Однословные значения: отличаем
    # обычное капитализированное слово ("Cockpit", "Wall" — единственная
    # заглавная буква, в начале) от настоящего PascalCase/camelCase
    # идентификатора ("ShuttleReactorModuleDef" — несколько заглавных букв,
    # "горбов" из нескольких слов, склеенных воедино). RimWorld сплошь и
    # рядом пишет однословные label с большой буквы — это не идентификатор.
    if _LOOKS_LIKE_IDENTIFIER_RE.match(stripped) and stripped.isalnum():
        has_inner_capital = any(c.isupper() for c in stripped[1:])
        if stripped[0].isupper() and has_inner_capital:
            return False
    return True


def is_translatable_field(tag: str, text: str) -> bool:
    """Полная проверка "это переводимый текст?" — тег + значение вместе.
    Используется при обходе Defs/*.xml (см. xml_io._walk_def)."""
    if is_never_translatable_tag(tag):
        return False
    return is_translatable_value(text)


# --- Grammar/RulePack: rulesStrings и плейсхолдеры в тексте -----------------

# Найдено на: QuestScriptDef-моды, alpha_memes (MemeDef).
# rulesStrings хранит строки вида "ruleKey->текст" или, с параметрами,
# "ruleKey(tag=x,uses=1)     ->текст" (пробелы перед стрелкой произвольные).
# Часть до стрелки — идентификатор правила генерации грамматики (Grammar/
# RulePack), не текст для игрока; переводится только часть после неё.
RULE_STRING_KEY_RE = re.compile(r"^([\w.\[\]]+(?:\([^)]*\))?\s*)->(.*)$", re.DOTALL)


def is_rule_string(tag: str, text: str) -> bool:
    """rulesStrings — особый случай: сама строка (целиком, с ключом и
    стрелкой) возвращается как обычное переводимое поле, а защита
    идентификатора-ключа от перевода происходит позже, в translator.py,
    тем же способом, что и для плейсхолдеров {0}/[species]."""
    return tag.lower() == "rulesstrings" and bool(RULE_STRING_KEY_RE.match(text))


# Найдено на: alpha_memes. Rich-text теги RimWorld вида <color=#33d733>...
# </color> (в исходном XML экранированы как &lt;color=...&gt;/&lt;/color&gt;,
# ElementTree разворачивает их обратно в буквальные < > при чтении текста
# узла). Отдавать их в Argos как обычный текст опасно: NMT-модель не обучена
# на HTML/rich-text разметке внутри предложений и может просто НЕ
# воспроизвести закрывающий тег в выводе — конец описания вместе с
# </color> тихо пропадает, даже когда сам текст короткий и легко умещается
# в лимит модели (не проблема длины — проблема самого вида токена).
_RICH_TEXT_TAG_RE = r"</?color(?:=[^>]*)?>"

# Найдено на: pawnmorpher/bio_clip ({species} -> {物种}), alpha_memes
# ([founder_pronoun] -> [founder pronoun]).
# Плейсхолдеры, которые НИКОГДА не должны отдаваться модели перевода как
# текст — она может их транслитерировать, просклонять, потерять при
# генерации, или даже перевести на случайный третий язык вместо целевого:
#   {0}, {1}, {species}, {PAWN_nameDef}   — RimWorld string.Format-подобные
#   [founderName], [founder_pronoun]      — Grammar/RulePack-токены внутри
#                                            rulesStrings (генератор истории
#                                            идеологии подставляет их сам)
#   <color=#RRGGBB>, </color>             — rich-text разметка (см. выше)
#   \n, \r                                — литеральные escape-последовательности
#   "key->" / "key(tag=x) ->"             — префикс до стрелки в rulesStrings
#                                            (см. RULE_STRING_KEY_RE выше)
TRANSLATION_PLACEHOLDER_RE = re.compile(
    r"\{\w+\}"                          # {0}, {species}, {PAWN_nameDef}
    r"|\[\w+\]"                         # [founderName], [founder_pronoun], [deity0_name]
    rf"|{_RICH_TEXT_TAG_RE}"            # <color=#33d733>, </color>
    r"|\\n|\\r"                         # литеральные \n/\r внутри текста
    r"|^[\w.\[\]]+(?:\([^)]*\))?\s*->"  # "key->" или "key(tag=x,uses=1)  ->"
)
