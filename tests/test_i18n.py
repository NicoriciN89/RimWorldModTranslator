"""Тесты src/i18n.py: локализация интерфейса программы (не языка перевода
мода — тот отдельный, см. gui.TRANSLATION_LANGUAGE_CODES). Два уровня выбора
по требованию пользователя: автоопределение системного языка Windows при
первом запуске + явный выбор в самой программе, который всегда приоритетнее."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.i18n import SUPPORTED_UI_LANGUAGES, Translator, detect_system_ui_language


def test_all_supported_languages_have_the_same_keys() -> None:
    """Расхождение набора ключей между языками — тихий баг: t() в таком
    случае откатывается на английский для недостающего ключа, но лучше
    поймать несоответствие явно, чем полагаться на fallback."""
    from src.i18n import _STRINGS

    reference_keys = set(_STRINGS["en"].keys())
    for lang, strings in _STRINGS.items():
        assert set(strings.keys()) == reference_keys, f"{lang} keys mismatch"


def test_translator_returns_string_in_selected_language() -> None:
    t = Translator("ru")
    assert t.t("translate") == "Перевести"
    t.set_language("en")
    assert t.t("translate") == "Translate"


def test_translator_formats_placeholders() -> None:
    t = Translator("en")
    assert t.t("mod_detected", name="Xenotype Summary") == "Mod detected: Xenotype Summary"


def test_translator_falls_back_to_english_for_unknown_language() -> None:
    t = Translator("xx-not-a-real-language")
    assert t.language == "en"
    assert t.t("translate") == "Translate"


def test_translator_set_language_falls_back_to_english_for_unknown() -> None:
    t = Translator("ru")
    t.set_language("xx-not-a-real-language")
    assert t.language == "en"


def test_supported_ui_languages_match_translator_languages() -> None:
    """Комбобокс выбора языка интерфейса в gui.py строится из
    SUPPORTED_UI_LANGUAGES — если тут появится язык без словаря строк (или
    наоборот), выбор в UI либо покажет мусор, либо молча откатится на
    английский без объяснения."""
    from src.i18n import _STRINGS

    ui_codes = {code for _, code in SUPPORTED_UI_LANGUAGES}
    assert ui_codes == set(_STRINGS.keys())


@pytest.mark.parametrize("windows_lang_id,expected", [
    (1049, "ru"),  # ru-RU
    (1033, "en"),  # en-US
    (1058, "uk"),  # uk-UA
    (1031, "de"),  # de-DE
])
def test_detect_system_ui_language_maps_known_windows_locales(
        windows_lang_id: int, expected: str) -> None:
    with patch("ctypes.windll.kernel32.GetUserDefaultUILanguage", return_value=windows_lang_id,
               create=True):
        assert detect_system_ui_language() == expected


def test_detect_system_ui_language_falls_back_to_english_for_unsupported_locale() -> None:
    """Например, испанская Windows (es-ES) — язык перевода мода мы
    поддерживаем, но словаря строк интерфейса для него ещё нет, так что
    честный английский fallback лучше, чем показывать пустые ключи."""
    with patch("ctypes.windll.kernel32.GetUserDefaultUILanguage", return_value=3082,  # es-ES
               create=True):
        assert detect_system_ui_language() == "en"


def test_detect_system_ui_language_survives_missing_ctypes_support() -> None:
    """На не-Windows системах (или в урезанном окружении) GetUserDefaultUILanguage
    может отсутствовать вовсе — best-effort, не роняем программу."""
    with patch("ctypes.windll.kernel32.GetUserDefaultUILanguage",
               side_effect=AttributeError, create=True):
        assert detect_system_ui_language() == "en"
