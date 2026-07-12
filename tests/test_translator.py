"""Тесты src/translator.py: защита плейсхолдеров и автоповтор при порче
перевода в случайный третий язык — оба бага найдены на реальных модах."""
from __future__ import annotations

from src.translator import TranslationEngine


def _engine_with_fake_translate(fake_translate_raw):
    engine = TranslationEngine("en", "ru")
    engine._translation = object()  # пропускаем реальную инициализацию Argos
    engine._translate_raw = fake_translate_raw
    return engine


def test_retries_once_when_result_contains_cjk() -> None:
    """Баг из pawnmorpher/bio_clip: Argos иногда выдаёт случайные CJK-символы
    вместо русского перевода. Один повторный вызов должен подхватываться,
    если он дал чистый результат."""
    calls = {"n": 0}

    def fake(text: str) -> str:
        calls["n"] += 1
        return "物种" if calls["n"] == 1 else "корректный перевод"

    engine = _engine_with_fake_translate(fake)
    result = engine.translate("some phrase")

    assert calls["n"] == 2
    assert result == "корректный перевод"


def test_keeps_last_attempt_if_both_corrupted() -> None:
    """Если и повторная попытка испорчена — не зацикливаемся, используем
    последний результат как есть."""
    engine = _engine_with_fake_translate(lambda text: "物种")
    result = engine.translate("some phrase")
    assert result == "物种"


def test_does_not_retry_on_clean_first_attempt() -> None:
    """Чистый результат с первого раза не должен вызывать повторный перевод —
    иначе долгий LLM/Argos перевод удвоился бы впустую на каждой строке."""
    calls = {"n": 0}

    def fake(text: str) -> str:
        calls["n"] += 1
        return "нормальный перевод"

    engine = _engine_with_fake_translate(fake)
    engine.translate("some phrase")
    assert calls["n"] == 1


def test_numeric_placeholders_survive_translation() -> None:
    """{0}/{1} никогда не должны отдаваться в "перевод" — здесь фейковый
    translate нарочно портит любой текст, чтобы отличить его от плейсхолдера."""
    engine = _engine_with_fake_translate(lambda text: text.upper())
    result = engine.translate("hello {0} world {1}")
    assert "{0}" in result
    assert "{1}" in result


def test_named_placeholders_survive_translation() -> None:
    """Баг с {species} -> {物种}: именованные плейсхолдеры должны защищаться
    так же, как числовые."""
    engine = _engine_with_fake_translate(lambda text: "物种" if "species" in text else text.upper())
    result = engine.translate("turned into a {species}")
    assert "{species}" in result
    assert "物种" not in result


def test_rule_string_key_prefix_is_not_translated() -> None:
    """QuestScriptDef.*.rulesStrings хранит "ключ->текст" (напр.
    "distress->Distress Call") — идентификатор до стрелки должен остаться
    буквально нетронутым, переводится только часть после неё."""
    engine = _engine_with_fake_translate(lambda text: text.upper())
    result = engine.translate("distress->Distress Call")
    assert result.startswith("distress->")
    assert "DISTRESS CALL" in result
