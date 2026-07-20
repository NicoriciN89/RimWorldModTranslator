"""Тесты src/glossary.py: подстановка терминов через protect()/restore() и
согласование рода/числа прилагательных вроде "усиленный" по соседнему
существительному — баг найден на реальном моде (cables_and_plumbing:
"труба усиленный" вместо "усиленная труба")."""
from __future__ import annotations

import pytest

from src.glossary import GLOSSARY, GlossaryContext, agree_adjectives


def test_glossary_term_is_protected_and_restored() -> None:
    """protect() заменяет термин на защищённый токен так, что "переводчик"
    (тут — identity) его не трогает; restore() возвращает русский термин."""
    ctx = GlossaryContext()
    protected = ctx.protect("a hediff affects the pawn")
    assert "hediff" not in protected.lower()
    assert "pawn" not in protected.lower()

    restored = ctx.restore(protected)
    assert "хедифф" in restored
    assert "персонаж" in restored


@pytest.mark.parametrize("text,expected", [
    ("труба усиленный", "труба усиленная"),
    ("трубы усиленный", "трубы усиленные"),
    ("усиленный труба", "усиленная труба"),
])
def test_agree_adjectives_fixes_known_cases(text: str, expected: str) -> None:
    assert agree_adjectives(text) == expected


def test_restore_fixes_agreement_and_strips_space_before_punctuation() -> None:
    """Полный конвейер GlossaryContext.restore(): нормализация пробелов перед
    пунктуацией и согласование прилагательного применяются вместе — так, как
    это происходит при реальном переводе (баг из cables_and_plumbing:
    "проводка усиленный ." вместо "проводка усиленная.")."""
    ctx = GlossaryContext()
    protected = ctx.protect("проводка heavy-duty .")
    assert ctx.restore(protected) == "проводка усиленная."


def test_agree_adjectives_leaves_unrelated_text_alone() -> None:
    assert agree_adjectives("просто текст без прилагательных") == "просто текст без прилагательных"


def test_dryad_and_gauranlen_are_glossary_terms() -> None:
    """Найдено на: alpha_memes — Argos разбирал "dryad" как "dry ad" и
    выдавал «превосходство сухих ад»; "Gauranlen" транслитерировался
    произвольно. Оба должны защищаться глоссарием."""
    ctx = GlossaryContext()
    protected = ctx.protect("dryad supremacy near the gauranlen tree")
    assert "dryad" not in protected.lower()
    assert "gauranlen" not in protected.lower()
    restored = ctx.restore(protected)
    assert "дриада" in restored
    assert "дерево Гауранлен" in restored


def test_capitalized_term_keeps_capital_letter() -> None:
    """Термин, написанный в оригинале с большой буквы (начало предложения,
    заголовок), должен подставляться с большой буквы и по-русски."""
    ctx = GlossaryContext()
    restored_upper = ctx.restore(ctx.protect("Dryads are friendly."))
    assert restored_upper.startswith("Дриады")
    ctx2 = GlossaryContext()
    restored_lower = ctx2.restore(ctx2.protect("the dryads are friendly."))
    assert "дриады" in restored_lower


def test_precept_matches_official_translation() -> None:
    """Официальный перевод Ideology использует «принцип» (ванильный UI:
    "Обязательные принципы"), а не «предписание»."""
    ctx = GlossaryContext()
    assert "принцип" in ctx.restore(ctx.protect("precept"))


@pytest.mark.xfail(reason="Известное ограничение: эвристика по окончанию не различает "
                          "падежи, родительный падеж мн.ч. 'труб' неотличим от м.р. ед.ч.")
def test_agree_adjectives_genitive_plural_not_supported() -> None:
    assert agree_adjectives("10 труб усиленный") == "10 труб усиленные"


@pytest.mark.parametrize("term,expected", [
    ("shambler", "шамблер"),
    ("metalhorror", "металлический ужас"),
    ("fleshbeast", "плотезверь"),
    ("revenant", "ревенант"),
    ("entity", "сущность"),
    ("bioferrite", "биоферрит"),
    ("gorehulk", "кровавая громила"),
])
def test_anomaly_terms_are_glossary_protected(term: str, expected: str) -> None:
    """Anomaly-специфичные термины отсутствовали в глоссарии вовсе — Argos
    переводил "shambler"/"metalhorror" дословно или разваливал на куски
    ("metal horror" -> "металл ужас"). Проверяем, что термин целиком
    защищается и разворачивается в устоявшийся русский вариант."""
    ctx = GlossaryContext()
    protected = ctx.protect(f"a {term} appeared nearby")
    assert term not in protected.lower()
    restored = ctx.restore(protected)
    assert expected in restored


def test_generic_english_words_deliberately_excluded_from_anomaly_glossary() -> None:
    """"study"/"activity"/"cult"/"containment" — тоже термины Anomaly, но
    настолько общеупотребимые в английском (и в остальных текстах RimWorld:
    "study" как комната, "activity" как досуг персонажа), что глоссарная
    подмена дала бы больше ложных срабатываний на несвязанный текст, чем
    пользы. Намеренно не добавлены — тест фиксирует это решение, чтобы
    будущая правка не вернула их не глядя."""
    for word in ("study", "activity", "cult", "containment"):
        assert word not in GLOSSARY, f"{word!r} намеренно не должно быть в глоссарии"


@pytest.mark.xfail(reason="Известное ограничение: эвристика не различает части речи, "
                          "может принять соседний глагол за существительное.")
def test_agree_adjectives_confused_by_adjacent_verb() -> None:
    assert agree_adjectives("Сделать усиленный трубы") == "Сделать усиленные трубы"
