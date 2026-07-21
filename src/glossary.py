"""Глоссарий устоявшихся игровых терминов RimWorld (EN -> RU), собранный из
реальных переводов сообщества. Применяется как pre/post-обработка вокруг
машинного перевода Argos Translate: перед переводом английский термин
заменяется на защищённый плейсхолдер (аналогично {0}/{1}), чтобы модель не
переводила его дословно, а после перевода плейсхолдер разворачивается в
устоявшийся русский вариант. Так итоговый текст звучит "по-русскомодски",
а не как буквальный машинный перевод отдельных игровых слов."""
from __future__ import annotations

import re

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

# Прилагательные из глоссария, которые нужно согласовывать по роду/числу/
# падежу с существительным, стоящим рядом (глоссарий хранит только словарную
# форму м.р. ед.ч. им.п. — "усиленный"). Без этого получались реальные баги
# вида "труба усиленный", "трубы усиленный" вместо "усиленная труба",
# "усиленные трубы".
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
_ADJECTIVES_NEEDING_AGREEMENT = {"усиленный"}

try:
    import pymorphy3
    _morph: "pymorphy3.MorphAnalyzer | None" = pymorphy3.MorphAnalyzer(lang="ru")
except ImportError:
    _morph = None


def _agree_adjective_with_noun(adjective: str, noun: str) -> str:
    """Ставит adjective в форму, согласованную с noun, через реальный
    морфологический анализ. Если pymorphy3 недоступен или разбор не удался —
    возвращает adjective как есть (без согласования лучше, чем упавшая
    программа)."""
    if _morph is None:
        return adjective
    noun_parse = _morph.parse(noun)[0]
    adj_parse = _morph.parse(adjective)[0]
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


_NOUN_RE = r"[А-ЯЁа-яё]+"
_AGREEMENT_RE = re.compile(
    rf"\b({'|'.join(re.escape(a) for a in _ADJECTIVES_NEEDING_AGREEMENT)})\b\s+({_NOUN_RE})"
    rf"|({_NOUN_RE})\s+\b({'|'.join(re.escape(a) for a in _ADJECTIVES_NEEDING_AGREEMENT)})\b"
)


def agree_adjectives(text: str) -> str:
    """Подгоняет род/число/падеж защищённых прилагательных (см.
    _ADJECTIVES_NEEDING_AGREEMENT) под соседнее существительное — "труба
    усиленный" -> "усиленная труба" остаётся в исходном порядке слов,
    меняется только форма прилагательного."""
    def repl(m: re.Match) -> str:
        adj_before, noun_after, noun_before, adj_after = m.groups()
        adj = adj_before or adj_after
        noun = noun_after or noun_before
        agreed = _agree_adjective_with_noun(adj.lower(), noun.lower())
        if adj_before:
            return f"{agreed} {noun}"
        return f"{noun} {agreed}"

    return _AGREEMENT_RE.sub(repl, text)

# Плейсхолдер-токен, который (эмпирически проверено) Argos Translate переносит
# через перевод буквально в подавляющем большинстве случаев, без транслитерации
# или склонения — латинское "слово" без цифр/подчёркиваний, похожее на имя.
_TOKEN_PREFIX = "Zqg"


def _build_pattern() -> re.Pattern:
    terms = sorted(GLOSSARY, key=len, reverse=True)
    alternation = "|".join(re.escape(t) for t in terms)
    return re.compile(rf"\b({alternation})\b", re.IGNORECASE)


_TERM_RE = _build_pattern()


class GlossaryContext:
    """Держит соответствие "токен -> русский термин" для одного вызова
    protect()/restore(), чтобы разные строки не путали друг друга индексами."""

    def __init__(self) -> None:
        self._tokens: list[str] = []

    def protect(self, text: str) -> str:
        def repl(m: re.Match) -> str:
            matched = m.group(0)
            replacement = GLOSSARY[matched.lower()]
            # Сохраняем заглавную букву оригинала: "Dryad supremacy" в начале
            # предложения/заголовка должно давать «Дриада...», а не «дриада»
            # посреди фразы с большой буквы. Обратное (опустить регистр) не
            # делаем — в словаре имена собственные уже с большой буквы.
            if matched[:1].isupper() and replacement[:1].islower():
                replacement = replacement[0].upper() + replacement[1:]
            self._tokens.append(replacement)
            return f" {_TOKEN_PREFIX}{len(self._tokens) - 1} "

        return _TERM_RE.sub(repl, text)

    def restore(self, text: str) -> str:
        pattern = re.compile(rf"\s*{_TOKEN_PREFIX}([0-9]+)\s*")

        def repl(m: re.Match) -> str:
            idx = int(m.group(1))
            if idx < len(self._tokens):
                return f" {self._tokens[idx]} "
            return m.group(0)

        restored = pattern.sub(repl, text)
        restored = re.sub(r" {2,}", " ", restored).strip()
        restored = re.sub(r"\s+([.,!?;:])", r"\1", restored)
        return agree_adjectives(restored)
