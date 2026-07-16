"""Тесты src/translator.py: защита плейсхолдеров и автоповтор при порче
перевода в случайный третий язык — оба бага найдены на реальных модах."""
from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

from src.translator import ArgosPackageSetupError, TranslationEngine


def _engine_with_fake_translate(fake_translate_raw):
    engine = TranslationEngine("en", "ru")
    engine._translation = object()  # пропускаем реальную инициализацию Argos
    engine._translate_raw = fake_translate_raw
    return engine


def _engine_with_fake_underlying_translation(fake_translate):
    """В отличие от _engine_with_fake_translate (подменяет весь метод
    _translate_raw), здесь подменяется только self._translation.translate —
    нужно для тестов самой логики повтора ВНУТРИ _translate_raw."""
    engine = TranslationEngine("en", "ru")
    engine._translation = MagicMock(translate=fake_translate)
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


def test_rich_text_color_tags_survive_translation() -> None:
    """Баг из alpha_memes: <color=#RRGGBB>...</color> отдавалось модели как
    обычный текст — NMT-модель не обучена на HTML/rich-text разметке внутри
    предложений и иногда просто не воспроизводит закрывающий тег в выводе,
    даже когда сам текст короткий. Здесь фейковый translate нарочно "теряет"
    любой тег вида <...>, чтобы отличить настоящую защиту от случайного
    совпадения."""
    def fake(text: str) -> str:
        return re.sub(r"<[^>]*>", "", text).upper()

    engine = _engine_with_fake_translate(fake)
    result = engine.translate("some text <color=#33d733>colored part</color> more text")
    assert "<color=#33d733>" in result
    assert "</color>" in result


def test_glossary_truncation_falls_back_to_no_glossary_translation() -> None:
    """Баг из alpha_memes ("Ocular Warping ritual" рядом с глоссарным
    токеном-заглушкой): модель иногда детерминированно обрывает генерацию
    сразу после токена-заглушки Zqg{N}, теряя весь хвост предложения после
    термина — не порча в третий язык (CJK), а именно преждевременная
    остановка. Здесь фейковый translate нарочно обрезает текст сразу после
    токена-заглушки (сохраняя регистр, как это реально делает Argos, чтобы
    restore() из glossary.py мог найти и подставить термин обратно), но
    переводит нормально без неё — проверяем, что результат подхватывает
    более длинный (неусечённый) вариант без глоссария вместо усечённого."""
    def fake(text: str) -> str:
        if "Zqg" in text:
            # Обрезаем сразу после токена-заглушки, теряя длинный хвост —
            # регистр токена сохраняем, иначе glossary.restore() не найдёт
            # его в тексте и не сможет восстановить термин обратно.
            before, _, after = text.partition("Zqg0")
            return before.strip() + " Zqg0."
        return text.upper()

    engine = _engine_with_fake_translate(fake)
    # "ritual" в глоссарии — при защите текст станет "... prologue text
    # Ocular Warping Zqg0 <long tail lost by the bug>", мок оборвёт вывод
    # сразу после токена, теряя длинный хвост целиком (в отличие от
    # реального Argos, который иногда переводит пару слов после токена
    # перед обрывом) — так соотношение длин надёжно ниже порога.
    result = engine.translate(
        "Short prologue using the Ocular Warping ritual and then a very long tail "
        "of many additional words that should absolutely not be lost in translation "
        "if everything works correctly as expected here today."
    )
    assert "tail" in result.lower() or "TAIL" in result


def test_ensure_ready_clears_installed_languages_cache_after_first_install() -> None:
    """get_installed_languages() внутри самого argostranslate декорирован
    @lru_cache — первый вызов (пакет ещё не установлен) навсегда кэширует
    пустой результат. Без явного сброса кэша сразу после установки пакета
    (встроенного или скачанного) повторный вызов вернул бы тот же пустой
    список, и _ensure_ready() падал бы с StopIteration сразу после первой
    же установки пакета "с нуля" — ровно тот сценарий, который встречает
    любой пользователь при первом запуске программы."""
    import argostranslate.translate as real_translate

    fake_lang_en = MagicMock(code="en")
    fake_lang_ru = MagicMock(code="ru")
    fake_lang_en.get_translation = MagicMock(return_value="translation-object")

    call_count = {"n": 0}

    def fake_get_installed_languages():
        call_count["n"] += 1
        return [] if call_count["n"] == 1 else [fake_lang_en, fake_lang_ru]

    fake_get_installed_languages.cache_clear = MagicMock()

    with patch.object(real_translate, "get_installed_languages", fake_get_installed_languages):
        with patch("src.translator._install_bundled_package", return_value=True):
            engine = TranslationEngine("en", "ru")
            engine._ensure_ready()

    assert fake_get_installed_languages.cache_clear.called
    assert call_count["n"] == 2
    assert engine.is_ready()


def test_ensure_ready_repairs_broken_bundled_package_argos_thinks_is_installed() -> None:
    """Реальный баг из отчёта пользователя: антивирус карантинировал файл
    модели сразу после распаковки exe, но argostranslate.translate.
    get_installed_languages() всё равно возвращает язык как "установленный"
    (оно смотрит только на metadata.json, не на файлы модели) — поэтому
    старый код НИКОГДА не вызывал _install_bundled_package (тот вызывается
    только если from_lang/to_lang отсутствуют среди установленных), и
    неполная копия оставалась битой навсегда. _ensure_ready должна вызывать
    _repair_bundled_package_if_broken БЕЗУСЛОВНО, до опроса Argos."""
    import argostranslate.translate as real_translate

    fake_lang_en = MagicMock(code="en")
    fake_lang_ru = MagicMock(code="ru")
    fake_lang_en.get_translation = MagicMock(return_value="translation-object")

    # Argos с самого начала считает пару установленной — ровно то, что
    # происходит, когда metadata.json существует, а sentencepiece.model нет.
    with patch.object(real_translate, "get_installed_languages",
                      return_value=[fake_lang_en, fake_lang_ru]):
        with patch("src.translator._repair_bundled_package_if_broken",
                   return_value=True) as fake_repair:
            with patch("src.translator._install_bundled_package") as fake_install:
                engine = TranslationEngine("en", "ru")
                engine._ensure_ready()

    fake_repair.assert_called_once_with("en", "ru")
    # Раз Argos считает пару установленной, обычный путь установки не должен
    # вызываться вовсе — только починка уже "установленной" копии.
    fake_install.assert_not_called()
    assert engine.is_ready()


def test_rule_string_key_prefix_is_not_translated() -> None:
    """QuestScriptDef.*.rulesStrings хранит "ключ->текст" (напр.
    "distress->Distress Call") — идентификатор до стрелки должен остаться
    буквально нетронутым, переводится только часть после неё."""
    engine = _engine_with_fake_translate(lambda text: text.upper())
    result = engine.translate("distress->Distress Call")
    assert result.startswith("distress->")
    assert "DISTRESS CALL" in result


def test_rule_string_key_with_parenthesized_params_is_not_translated() -> None:
    """Баг из alpha_memes: MemeDef.*.rulesStrings часто хранит ключ с
    параметрами вида "founderJoin(tag=meme_Artist)     ->текст" (с
    произвольными пробелами перед стрелкой) — старый regex защищал только
    голое "word->", а всё, что содержало скобки/пробелы/"=" перед стрелкой,
    уходило в перевод целиком, коверкая "meme_Artist" в "meme Artist" и
    делая текст непригодным для системы генерации истории RimWorld."""
    engine = _engine_with_fake_translate(lambda text: text.upper())
    result = engine.translate("founderJoin(tag=meme_Artist)     ->our founder was inspired")
    assert result.startswith("founderJoin(tag=meme_Artist)     ->")
    assert "OUR FOUNDER WAS INSPIRED" in result


def test_bracketed_grammar_tokens_survive_translation() -> None:
    """Баг из alpha_memes: квадратноскобочные токены вида [founderName],
    [founder_pronoun], [deity0_name] внутри rulesStrings — это плейсхолдеры
    системы генерации истории идеологии RimWorld (Grammar/RulePack), не
    текст для игрока. Раньше они не были защищены вовсе и уходили в перевод
    как обычный текст: подчёркивание в "[founder_pronoun]" стиралось до
    "[founder pronoun]", из-за чего игра не находила нужный тег и падала в
    лог с "Bad string pass when reading rule"."""
    engine = _engine_with_fake_translate(lambda text: text.replace("_", " ").upper())
    result = engine.translate(
        "[founderName] spent decades perfecting [founder_possessive] style, "
        "and [founder_pronoun] was considered a true master."
    )
    assert "[founderName]" in result
    assert "[founder_possessive]" in result
    assert "[founder_pronoun]" in result
    assert "[founder pronoun]" not in result


def test_translate_raw_retries_once_on_transient_oserror() -> None:
    """Найдено на: внешний отчёт пользователя. Антивирус может ВРЕМЕННО
    заблокировать файл языковой модели для чтения (не удалить безвозвратно,
    а держать открытым на время своего сканирования) уже ПОСЛЕ того, как
    _ensure_ready проверила целостность файла по размеру и признала пакет
    готовым — sentencepiece/ctranslate2 в этот момент падают голым OSError
    на первом же вызове translate(). Одна повторная попытка (с паузой)
    должна подхватить успешный результат, если ко второму разу файл уже
    разблокирован."""
    calls = {"n": 0}

    def fake_translate(text: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError('Not found: "...\\sentencepiece.model": No such file or directory')
        return "переведено"

    engine = _engine_with_fake_underlying_translation(fake_translate)
    with patch("src.translator.time.sleep"):
        result = engine._translate_raw("some text")

    assert result == "переведено"
    assert calls["n"] == 2


def test_translate_raw_raises_clear_error_when_still_broken_after_retry() -> None:
    """Если файл модели недоступен даже со второй попытки — это не
    временная блокировка антивирусом, а что-то более серьёзное; пользователь
    должен увидеть понятную causa (не голый traceback ctranslate2/
    sentencepiece) с практическим советом, что делать."""
    def always_fails(text: str) -> str:
        raise OSError('Not found: "...\\sentencepiece.model": No such file or directory')

    engine = _engine_with_fake_underlying_translation(always_fails)
    with patch("src.translator.time.sleep"):
        try:
            engine._translate_raw("some text")
            assert False, "ожидалось исключение"
        except ArgosPackageSetupError as e:
            assert "антивирус" in str(e).lower()
