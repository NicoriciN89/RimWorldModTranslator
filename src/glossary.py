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
    "precepts": "предписания",
    "precept": "предписание",
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
    "mental break": "срыв",
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
    # Строения/техника
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
            term = m.group(0).lower()
            self._tokens.append(GLOSSARY[term])
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
        return re.sub(r" {2,}", " ", restored).strip()
