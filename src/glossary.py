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
}

# Прилагательные из глоссария, которые нужно согласовывать по роду/числу с
# существительным, стоящим рядом (глоссарий хранит только словарную форму
# м.р. ед.ч. — "усиленный"). Без этого получались реальные баги вида "труба
# усиленный", "трубы усиленный" вместо "усиленная труба", "усиленные трубы".
_ADJECTIVE_FORMS: dict[str, dict[str, str]] = {
    "усиленный": {
        "m": "усиленный", "f": "усиленная", "n": "усиленное", "pl": "усиленные",
    },
}

# Грубая эвристика рода/числа по окончанию существительного — этого достаточно
# для типовой игровой лексики (труба/трубы, кабель/кабели, проводка и т.п.),
# не претендует на полный морфологический разбор русского языка. Известное
# ограничение: не различает падежи, поэтому "труб усиленный" (родительный
# падеж мн.ч.) не исправляется — окончание "труб" неотличимо от м.р. ед.ч.
# без словаря морфологии (напр. pymorphy2). Тоже может спутать соседнее
# слово, если это не существительное, а глагол ("Сделать усиленный трубы").
# Такие случаи остаются как есть — это упрощение, а не полное решение.
_FEMININE_ENDINGS = ("а", "я")
_PLURAL_ENDINGS = ("ы", "и")
_NEUTER_ENDINGS = ("о", "е", "ё")


def _guess_gender_number(noun: str) -> str:
    lower = noun.lower()
    if lower.endswith(_PLURAL_ENDINGS):
        return "pl"
    if lower.endswith(_FEMININE_ENDINGS):
        return "f"
    if lower.endswith(_NEUTER_ENDINGS):
        return "n"
    return "m"


_NOUN_RE = r"[А-ЯЁа-яё]+"
_AGREEMENT_RE = re.compile(
    rf"\b({'|'.join(re.escape(a) for a in _ADJECTIVE_FORMS)})\b\s+({_NOUN_RE})"
    rf"|({_NOUN_RE})\s+\b({'|'.join(re.escape(a) for a in _ADJECTIVE_FORMS)})\b"
)


def agree_adjectives(text: str) -> str:
    """Подгоняет род/число защищённых прилагательных (см. _ADJECTIVE_FORMS)
    под соседнее существительное — "труба усиленный" -> "усиленная труба"
    остаётся в исходном порядке слов, меняется только форма прилагательного."""
    def repl(m: re.Match) -> str:
        adj_before, noun_after, noun_before, adj_after = m.groups()
        adj = adj_before or adj_after
        noun = noun_after or noun_before
        forms = _ADJECTIVE_FORMS[adj.lower()]
        agreed = forms[_guess_gender_number(noun)]
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
