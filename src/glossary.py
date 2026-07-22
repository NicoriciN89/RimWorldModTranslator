"""Глоссарий устоявшихся игровых терминов RimWorld, применяется как pre/post-
обработка вокруг машинного перевода Argos Translate: перед переводом
английский термин заменяется на защищённый плейсхолдер (аналогично {0}/{1}),
чтобы модель не переводила его дословно, а после перевода плейсхолдер
разворачивается в устоявшийся вариант на целевом языке. Так итоговый текст
звучит "по-игровому", а не как буквальный машинный перевод отдельных слов.

Русский глоссарий (GLOSSARY, ниже) собран из РЕАЛЬНЫХ переводов сообщества,
найденных на диске пользователя (xenotype_summary, servers,
trauma_team_missions, celetech_shuttle_extension, psycasts,
cables_and_plumbing). Немецкий и французский (glossary_terms_de.py,
glossary_terms_fr.py) — сгенерированы как лучшее приближение без такой
проверки, см. предупреждение в начале тех файлов."""
from __future__ import annotations

import re

from .glossary_terms_de import GLOSSARY_DE
from .glossary_terms_fr import GLOSSARY_FR

# EN-термин (нижний регистр) -> RU-термин. Порядок в самом словаре не важен —
# сортировка по длине для regex делается автоматически ниже.
# Основано на живом глоссарии, извлечённом из реальных переводов сообщества
# RimWorld (xenotype_summary, servers, trauma_team_missions,
# celetech_shuttle_extension, psycasts, cables_and_plumbing).
GLOSSARY: dict[str, str] = {
    "hediffs": "хедиффы",
    "hediff": "хедифф",
    "xenotypes": "ксенотипы",
    "xenotype": "ксенотип",
    "xenogerms": "ксеногермы",
    "xenogerm": "ксеногерм",
    "xenogenes": "ксенгены",
    "xenogene": "ксенген",
    "genes": "гены",
    "gene": "ген",
    "archite": "структит",
    "archotech": "архотех",
    "psycasters": "психокастеры",
    "psycaster": "психокастер",
    "psycasts": "психокасты",
    "psycast": "психокаст",
    "psylink": "псайлинк",
    "psyfocus": "псифокус",
    "psychic sensitivity": "психическая чувствительность",
    "resonance": "резонанс",
    "enlightenment": "просветление",
    "mechanoids": "механоиды",
    "mechanoid": "механоид",
    "ideoligion": "идеология",
    "ideology": "идеология",
    # Официальный русский перевод Ideology использует «принцип» (видно в
    # ванильном UI: "Обязательные принципы"), а не «предписание» — держим
    # терминологию согласованной с игрой.
    "precepts": "принципы",
    "precept": "принцип",
    "colonists": "колонисты",
    "colonist": "колонист",
    "pawns": "персонажи",
    "pawn": "персонаж",
    "raiders": "рейдеры",
    "raid": "рейд",
    "traits": "черты характера",
    "trait": "черта характера",
    "passions": "увлечения",
    "passion": "увлечение",
    "backstory": "предыстория",
    "factions": "фракции",
    "faction": "фракция",
    "quests": "квесты",
    "quest": "квест",
    "caravans": "караваны",
    "caravan": "караван",
    "apparel": "одежда",
    "mood": "настроение",
    "needs": "потребности",
    "need": "потребность",
    "capacities": "способности организма",
    "capacity": "способность организма",
    "aptitudes": "способности",
    "aptitude": "способность",
    "stat modifiers": "модификаторы характеристик",
    "mental break": "нервный срыв",
    "prison break": "побег из тюрьмы",
    "tolerance": "толерантность",
    "overdose": "передозировка",
    "immunity": "иммунитет",
    "abilities": "способности",
    "ability": "способность",
    "research": "исследование",
    "rituals": "ритуалы",
    "ritual": "ритуал",
    "meditation": "медитация",
    "storyteller": "рассказчик",
    # Материалы/ресурсы (устоявшиеся русские названия из перевода игры)
    "plasteel": "пласталь",
    "chemfuel": "химтопливо",
    "neutroamine": "нейтроамин",
    "luciferium": "люциферий",
    "pemmican": "пеммикан",
    "kibble": "комбикорм",
    # Существа/события
    "thrumbo": "трумбо",
    "scythers": "жнецы",
    "scyther": "жнец",
    "centipedes": "многоножки",
    "centipede": "многоножка",
    "toxic fallout": "токсичные осадки",
    "solar flare": "солнечная вспышка",
    "cryptosleep": "криптосон",
    # Biotech
    "mechanitor": "механитор",
    "sanguophages": "сангвофаги",
    "sanguophage": "сангвофаг",
    "ghouls": "гули",
    "ghoul": "гуль",
    "deathrest": "смертный сон",
    # Ideology: деревья Гауранлен и дриады (найдено на: alpha_memes —
    # Argos разбирал "dryad" как "dry ad" и выдавал «сухих ад»).
    "gauranlen tree": "дерево Гауранлен",
    "gauranlen": "Гауранлен",
    "dryads": "дриады",
    "dryad": "дриада",
    "anima tree": "дерево анима",
    "anima": "анима",
    # Термины популярных модов (найдено на: alpha_memes — ритуал в labels
    # переводится, а упоминание в description оставалось английским).
    "ocular warping": "искривление глаз",
    # Строения/техника
    "turret": "турель",
    "mortar": "миномёт",
    "server": "сервер",
    "component": "компонент",
    "shuttle": "шаттл",
    "module": "модуль",
    "habitat": "жилой модуль",
    "crew": "экипаж",
    "cargo": "груз",
    "reactor": "реактор",
    "shield": "щит",
    "cockpit": "кабина пилота",
    "hull": "корпус",
    "bay": "отсек",
    "ammo": "боеприпасы",
    "prisoner": "заключённый",
    "electrical wiring": "электропроводка",
    "electrical cable": "электрический кабель",
    "heavy-duty": "усиленный",
    "power pole": "опорный столб",
    # Anomaly (термины из официальной русской локализации DLC — до этой
    # правки глоссарий покрывал Biotech/Ideology, но не Anomaly вообще, из-за
    # чего Argos переводил их дословно/непоследовательно: "shambler" как
    # "шаркальщик"/транслит, "metalhorror" разваливался на "металл ужас").
    "shamblers": "шамблеры",
    "shambler": "шамблер",
    "metalhorrors": "металлические ужасы",
    "metalhorror": "металлический ужас",
    "fleshbeasts": "плотезвери",
    "fleshbeast": "плотезверь",
    "revenants": "ревенанты",
    "revenant": "ревенант",
    # "entity"/"entities" — обычное английское слово вне контекста, но в
    # текстах RimWorld/модов почти всегда означает именно термин Anomaly, а
    # не программистское "сущность". Другие настолько же общие слова
    # ("study", "activity", "containment", "cult") намеренно НЕ добавлены —
    # там риск испортить перевод несвязанного текста выше пользы.
    "entities": "сущности",
    "entity": "сущность",
    "bioferrite": "биоферрит",
    "gorehulks": "кровавые громилы",
    "gorehulk": "кровавая громила",
    "deathpall": "мор",
    "noctol": "ноктол",
    "sightstealer": "похититель взгляда",
    "sightstealers": "похитители взгляда",
    "toxic gorger": "токсичный обжора",
    "toxic gorgers": "токсичные обжоры",
    "chimera": "химера",
    "chimeras": "химеры",
    "devourer": "пожиратель",
    "devourers": "пожиратели",
    "fingerspike": "костешип",
    "fingerspikes": "костешипы",
    "obelisk": "обелиск",
    "obelisks": "обелиски",
    "void monolith": "монолит пустоты",
    "monolith": "монолит",
    "unnatural darkness": "противоестественная тьма",
    "unnatural corpse": "противоестественный труп",
    "bloodrain": "кровавый дождь",
    "cultist": "культист",
    "cultists": "культисты",
    "psychic ritual": "психический ритуал",
    "hold cell": "камера содержания",
    "pit gate": "яма-портал",
    "pit burrow": "яма-нора",
    "flesh whip": "плотевая плеть",
    "twisted meat": "искажённая плоть",
    "corpse withering": "иссушение трупа",
    "ritual mutilation": "ритуальное увечье",
}

# Глоссарии по целевому языку — используются GlossaryContext(lang) вместо
# захардкоженного GLOSSARY, чтобы protect()/restore() работали для любого
# из поддерживаемых языков, а не только для русского.
_GLOSSARIES_BY_LANG: dict[str, dict[str, str]] = {
    "ru": GLOSSARY,
    "de": GLOSSARY_DE,
    "fr": GLOSSARY_FR,
}

# Прилагательные из русского глоссария, которые нужно согласовывать по роду/
# числу/падежу с существительным, стоящим рядом (глоссарий хранит только
# словарную форму м.р. ед.ч. им.п. — "усиленный"). Без этого получались
# реальные баги вида "труба усиленный", "трубы усиленный" вместо "усиленная
# труба", "усиленные трубы".
#
# Реальный морфологический разбор через pymorphy3 (а не эвристика по
# окончанию, как раньше) — умеет определять падеж, не только род/число:
# "10 труб усиленный" теперь согласуется в "10 труб усиленных" (родительный
# падеж мн.ч.), а не только в "усиленные" (именительный), что было пределом
# возможностей старой эвристики. Ограничение осталось — некоторые словоформы
# (напр. "трубы") морфологически неоднозначны сами по себе без контекста
# целого предложения (может быть и "трубы" им.п. мн.ч., и "трубы" род.п.
# ед.ч. — "нет трубы"); берём разбор с наибольшей вероятностью по pymorphy3
# и не пытаемся угадывать лучше него.
_RU_ADJECTIVES_NEEDING_AGREEMENT = {"усиленный"}

# То же для de/fr — словарная форма прилагательного, как она хранится в
# GLOSSARY_DE/GLOSSARY_FR (нем. м.р. ед.ч. им.п.: "verstärkt"; фр. м.р. ед.ч.:
# "renforcé").
_DE_ADJECTIVES_NEEDING_AGREEMENT = {"verstärkt"}
_FR_ADJECTIVES_NEEDING_AGREEMENT = {"renforcé"}

try:
    import pymorphy3
    _morph_ru: "pymorphy3.MorphAnalyzer | None" = pymorphy3.MorphAnalyzer(lang="ru")
except ImportError:
    _morph_ru = None

# spaCy для de/fr — ленивая загрузка (тяжёлая инициализация модели, ~1-2с),
# только если реально понадобится согласование для этих языков. Small-модели
# (_sm) не идеальны по точности тегирования (могут спутать часть речи на
# короткой/двусмысленной фразе), но дают нужные Gender/Number/Case из
# token.morph в подавляющем большинстве обычных игровых фраз.
_spacy_nlp_cache: dict[str, object] = {}


def _get_spacy_model(lang: str):
    if lang in _spacy_nlp_cache:
        return _spacy_nlp_cache[lang]
    model_name = {"de": "de_core_news_sm", "fr": "fr_core_news_sm"}.get(lang)
    if model_name is None:
        return None
    try:
        import spacy
        nlp = spacy.load(model_name)
    except (ImportError, OSError):
        nlp = None
    _spacy_nlp_cache[lang] = nlp
    return nlp


def _agree_adjective_with_noun_ru(adjective: str, noun: str, sentence: str) -> str:
    """Ставит русское adjective в форму, согласованную с noun, через
    реальный морфологический анализ pymorphy3. Если pymorphy3 недоступен
    или разбор не удался — возвращает adjective как есть (без согласования
    лучше, чем упавшая программа). sentence не используется (pymorphy3 —
    словарный анализ отдельного слова, не neural tagger, поэтому контекст
    предложения ему не нужен, в отличие от spaCy для de/fr ниже) — принят
    только чтобы все три функции имели общую сигнатуру для единого call
    site в agree_adjectives()."""
    if _morph_ru is None:
        return adjective
    noun_parse = _morph_ru.parse(noun)[0]
    adj_parse = _morph_ru.parse(adjective)[0]
    number = noun_parse.tag.number
    case = noun_parse.tag.case
    gender = noun_parse.tag.gender
    # Прилагательные во мн.ч. не различают род в русском ("усиленные", а не
    # "усиленные/усиленная" по родам) — передавать gender вместе с plur
    # ломает inflect() у pymorphy3.
    grammemes = {g for g in ((number, case) if number == "plur" else (gender, number, case)) if g}
    if not grammemes:
        return adjective
    inflected = adj_parse.inflect(grammemes)
    return inflected.word if inflected else adjective


# Немецкие формы согласования по роду/числу для прилагательных из
# _DE_ADJECTIVES_NEEDING_AGREEMENT — предикативное/атрибутивное окончание
# сильного склонения (без артикля), которое реально встречается в игровых
# строках вида "verstärktes Kabel". spaCy используется только чтобы
# ОПРЕДЕЛИТЬ Gender/Number существительного — саму словоформу прилагательного
# ищем в этой небольшой таблице (нет надобности в общем морфологическом
# генераторе для одного известного прилагательного).
_DE_ADJECTIVE_FORMS: dict[str, dict[str, str]] = {
    "verstärkt": {
        "Masc,Sing": "verstärkter", "Fem,Sing": "verstärkte",
        "Neut,Sing": "verstärktes", "Plur": "verstärkte",
    },
}

_FR_ADJECTIVE_FORMS: dict[str, dict[str, str]] = {
    "renforcé": {
        "Masc,Sing": "renforcé", "Fem,Sing": "renforcée",
        "Masc,Plur": "renforcés", "Fem,Plur": "renforcées",
    },
}


def _find_token(doc, word: str):
    """Ищет в разборе spaCy токен, совпадающий с word без учёта регистра —
    используется, чтобы получить Gender/Number существительного из разбора
    ЦЕЛОГО предложения, а не изолированного слова. Критично для точности:
    вне контекста spaCy_sm часто ошибается на инвариантных/двусмысленных
    словах (напр. нем. "Kabel" одинаково и в ед., и во мн.ч. — изолированно
    тегируется как Plur, а в "Das Kabel ist stark." корректно как Sing)."""
    lower = word.lower()
    for token in doc:
        if token.text.lower() == lower:
            return token
    return None


def _agree_adjective_with_noun_de(adjective: str, noun: str, sentence: str) -> str:
    """Определяет Gender/Number существительного через spaCy (de_core_news_sm),
    анализируя ЦЕЛОЕ предложение sentence (а не noun в отрыве от контекста —
    так спуско точнее для двусмысленных/инвариантных слов), и подставляет
    соответствующую форму прилагательного из _DE_ADJECTIVE_FORMS. Если spaCy
    недоступна, существительное не нашлось в разборе, или для него нет тега
    рода/числа — возвращает adjective как есть."""
    nlp = _get_spacy_model("de")
    if nlp is None:
        return adjective
    token = _find_token(nlp(sentence), noun)
    if token is None:
        return adjective
    number = token.morph.get("Number")
    gender = token.morph.get("Gender")
    if number and number[0] == "Plur":
        key = "Plur"
    elif gender and number:
        key = f"{gender[0]},{number[0]}"
    else:
        return adjective
    forms = _DE_ADJECTIVE_FORMS.get(adjective.lower())
    if forms is None:
        return adjective
    return forms.get(key, adjective)


def _agree_adjective_with_noun_fr(adjective: str, noun: str, sentence: str) -> str:
    """Аналог _agree_adjective_with_noun_de для французского
    (fr_core_news_sm) — французский не различает падежи, только род/число."""
    nlp = _get_spacy_model("fr")
    if nlp is None:
        return adjective
    token = _find_token(nlp(sentence), noun)
    if token is None:
        return adjective
    number = token.morph.get("Number")
    gender = token.morph.get("Gender")
    if not number or not gender:
        return adjective
    key = f"{gender[0]},{number[0]}"
    forms = _FR_ADJECTIVE_FORMS.get(adjective.lower())
    if forms is None:
        return adjective
    return forms.get(key, adjective)


_AGREEMENT_HANDLERS = {
    "ru": (_RU_ADJECTIVES_NEEDING_AGREEMENT, _agree_adjective_with_noun_ru),
    "de": (_DE_ADJECTIVES_NEEDING_AGREEMENT, _agree_adjective_with_noun_de),
    "fr": (_FR_ADJECTIVES_NEEDING_AGREEMENT, _agree_adjective_with_noun_fr),
}

_LATIN_NOUN_RE = r"[A-Za-zÀ-ÖØ-öø-ÿß]+"
_CYRILLIC_NOUN_RE = r"[А-ЯЁа-яё]+"

# Артикли/детерминативы de/fr, которые нельзя спутать с существительным —
# без этого списка регекс "слово + прилагательное" мог поймать "Die
# verstärkt" (артикль перед прилагательным) раньше, чем "verstärkt Server"
# (настоящее прилагательное+существительное) дальше в той же строке, и
# согласовать прилагательное по роду АРТИКЛЯ вместо настоящего
# существительного (найдено на: "Die verstärkt Server" -> опробовано
# согласование дало "verstärkte", хотя der Server мужского рода).
_DE_NON_NOUNS = {
    "der", "die", "das", "den", "dem", "des",
    "ein", "eine", "einer", "einem", "einen", "eines",
    "kein", "keine", "keiner", "keinem", "keinen", "keines",
}
_FR_NON_NOUNS = {
    "le", "la", "les", "un", "une", "des", "du", "au", "aux",
    "ce", "cet", "cette", "ces",
}
_NON_NOUNS_BY_LANG = {"de": _DE_NON_NOUNS, "fr": _FR_NON_NOUNS}


def _build_agreement_pattern(adjectives: set[str], lang: str) -> re.Pattern:
    noun_re = _CYRILLIC_NOUN_RE if lang == "ru" else _LATIN_NOUN_RE
    alternation = "|".join(re.escape(a) for a in adjectives)
    non_nouns = _NON_NOUNS_BY_LANG.get(lang)
    # Негативный lookahead/lookbehind исключает известные артикли из роли
    # "существительного" в обеих ветках альтернации — без словаря частей
    # речи это не отличит АБСОЛЮТНО любое не-существительное (см.
    # ограничение "Сделать усиленный трубы" для русского), но закрывает
    # самый частый и предсказуемый случай — артикль/детерминатив.
    if non_nouns:
        # (?<!\w) — соседний символ слева не буква/цифра/_: без этого
        # исключение "die" срабатывало только на позиции 0 строки, и движок
        # regex просто сдвигался на 1 символ вправо ("ie verstärkt..."),
        # где "ie" уже не в списке артиклей, и матчил его как "существительное".
        exclude = rf"(?<!\w)(?!(?:{'|'.join(non_nouns)})\b)"
        return re.compile(
            rf"\b({alternation})\b\s+{exclude}({noun_re})"
            rf"|{exclude}({noun_re})\s+\b({alternation})\b",
            re.IGNORECASE,
        )
    return re.compile(
        rf"\b({alternation})\b\s+({noun_re})"
        rf"|({noun_re})\s+\b({alternation})\b",
        re.IGNORECASE,
    )


def agree_adjectives(text: str, lang: str = "ru") -> str:
    """Подгоняет род/число/падеж защищённых прилагательных под соседнее
    существительное — "труба усиленный" -> "усиленная труба" остаётся в
    исходном порядке слов, меняется только форма прилагательного. lang
    выбирает, какой язык/анализатор использовать (ru: pymorphy3, de/fr:
    spaCy); язык без обработчика возвращает text без изменений."""
    handler = _AGREEMENT_HANDLERS.get(lang)
    if handler is None:
        return text
    adjectives, agree_fn = handler
    pattern = _build_agreement_pattern(adjectives, lang)

    def repl(m: re.Match) -> str:
        adj_before, noun_after, noun_before, adj_after = m.groups()
        adj = adj_before or adj_after
        noun = noun_after or noun_before
        agreed = agree_fn(adj.lower(), noun.lower() if lang == "ru" else noun, text)
        if adj_before:
            return f"{agreed} {noun}"
        return f"{noun} {agreed}"

    return pattern.sub(repl, text)

# Плейсхолдер-токен, который (эмпирически проверено) Argos Translate переносит
# через перевод буквально в подавляющем большинстве случаев, без транслитерации
# или склонения — латинское "слово" без цифр/подчёркиваний, похожее на имя.
_TOKEN_PREFIX = "Zqg"


def _build_term_pattern(glossary: dict[str, str]) -> re.Pattern:
    terms = sorted(glossary, key=len, reverse=True)
    alternation = "|".join(re.escape(t) for t in terms)
    return re.compile(rf"\b({alternation})\b", re.IGNORECASE)


_TERM_PATTERNS_BY_LANG: dict[str, re.Pattern] = {
    lang: _build_term_pattern(glossary) for lang, glossary in _GLOSSARIES_BY_LANG.items()
}


class GlossaryContext:
    """Держит соответствие "токен -> термин на целевом языке" для одного
    вызова protect()/restore(), чтобы разные строки не путали друг друга
    индексами. lang выбирает глоссарий (см. _GLOSSARIES_BY_LANG) — язык без
    глоссария (ещё) делает protect()/restore() no-op."""

    def __init__(self, lang: str = "ru") -> None:
        self.lang = lang
        self._glossary = _GLOSSARIES_BY_LANG.get(lang)
        self._term_re = _TERM_PATTERNS_BY_LANG.get(lang)
        self._tokens: list[str] = []

    def protect(self, text: str) -> str:
        if self._glossary is None or self._term_re is None:
            return text

        def repl(m: re.Match) -> str:
            matched = m.group(0)
            replacement = self._glossary[matched.lower()]
            # Сохраняем заглавную букву оригинала: "Dryad supremacy" в начале
            # предложения/заголовка должно давать «Дриада...», а не «дриада»
            # посреди фразы с большой буквы. Обратное (опустить регистр) не
            # делаем — в словаре имена собственные уже с большой буквы.
            if matched[:1].isupper() and replacement[:1].islower():
                replacement = replacement[0].upper() + replacement[1:]
            self._tokens.append(replacement)
            return f" {_TOKEN_PREFIX}{len(self._tokens) - 1} "

        return self._term_re.sub(repl, text)

    def restore(self, text: str) -> str:
        if self._glossary is None:
            return text
        # \s*-?\s* с обеих сторон: немецкий Argos иногда трактует токен-
        # заглушку как первую часть немецкого составного слова и вставляет
        # дефис ("Zqg0-Kabel", как в настоящих составных типа "Autokabel") —
        # без этого после подстановки термина оставался висячий "-Kabel".
        pattern = re.compile(rf"\s*-?\s*{_TOKEN_PREFIX}([0-9]+)\s*-?\s*")

        def repl(m: re.Match) -> str:
            idx = int(m.group(1))
            if idx < len(self._tokens):
                return f" {self._tokens[idx]} "
            return m.group(0)

        restored = pattern.sub(repl, text)
        restored = re.sub(r" {2,}", " ", restored).strip()
        restored = re.sub(r"\s+([.,!?;:])", r"\1", restored)
        return agree_adjectives(restored, self.lang)
