"""Обёртка над Argos Translate: офлайн-перевод строк с защитой плейсхолдеров
({0}, {1}, {species}, {PAWN_nameDef}...) и литеральных \\n/\\r от искажения
моделью перевода.

Плейсхолдеры никогда не передаются модели как текст: она может их
транслитерировать и просклонять (напр. "PLACEHOLDERONE" в русском переводе
превращалось в "ПЛАСЕХОЛДЕРОНА"), а именованные плейсхолдеры вида {species}
она иногда переводит как обычное слово и даже на случайный третий язык
(напр. {species} -> {物种}). Вместо этого текст режется на сегменты по
границам плейсхолдеров, переводится только то, что между ними, а сами
плейсхолдеры склеиваются обратно как литералы после перевода.
"""
from __future__ import annotations

import re
import sys
from functools import lru_cache

from .glossary import GlossaryContext
from .safe_print import safe_print

_PLACEHOLDER_RE = re.compile(r"\{\w+\}|\\n|\\r")

# Argos иногда даёт перевод не на целевой язык вместо русского для редких/
# составных слов, которых нет в её словаре (напр. случайные китайские
# иероглифы вместо перевода). У кириллицы и CJK нет общих символов, так что
# наличие CJK в результате при target_lang="ru" — надёжный признак порчи.
_CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힣]")


class TranslationEngine:
    """Ленивая инициализация Argos Translate: тяжёлый импорт/загрузка моделей
    откладывается до первого реального перевода."""

    def __init__(self, source_lang: str, target_lang: str):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self._translation = None

    def _ensure_ready(self) -> None:
        if self._translation is not None:
            return
        import argostranslate.package as package
        import argostranslate.translate as translate

        installed = translate.get_installed_languages()
        from_lang = next((l for l in installed if l.code == self.source_lang), None)
        to_lang = next((l for l in installed if l.code == self.target_lang), None)

        if from_lang is None or to_lang is None:
            safe_print(f"[translator] Пакет {self.source_lang}->{self.target_lang} не установлен, "
                       f"скачиваю...", file=sys.stderr)
            package.update_package_index()
            available = package.get_available_packages()
            match = next((p for p in available
                          if p.from_code == self.source_lang and p.to_code == self.target_lang),
                         None)
            if match is None:
                raise RuntimeError(
                    f"Argos Translate не предоставляет пару {self.source_lang}->{self.target_lang}. "
                    f"Проверьте коды языков (ISO 639-1)."
                )
            download_path = match.download()
            package.install_from_path(download_path)

            installed = translate.get_installed_languages()
            from_lang = next(l for l in installed if l.code == self.source_lang)
            to_lang = next(l for l in installed if l.code == self.target_lang)

        self._translation = from_lang.get_translation(to_lang)

    def _translate_raw(self, text: str) -> str:
        return self._translation.translate(text)

    def _translate_segment(self, part: str, use_glossary: bool) -> str:
        """Переводит один сегмент, сохраняя его ведущие/замыкающие пробелы
        буквально — модель обычно их обрезает при переводе. Игровые термины
        RimWorld (см. glossary.py) защищаются от Argos и подставляются как
        устоявшийся русский вариант уже после машинного перевода."""
        if not part:
            return part
        stripped = part.strip()
        if not stripped:
            return part
        lead = part[:len(part) - len(part.lstrip())]
        trail = part[len(part.rstrip()):]
        with_glossary = use_glossary and self.target_lang == "ru"

        def run_once() -> str:
            if with_glossary:
                ctx = GlossaryContext()
                return ctx.restore(self._translate_raw(ctx.protect(stripped)))
            return self._translate_raw(stripped)

        translated = run_once()
        if self.target_lang == "ru" and _CJK_RE.search(translated):
            # Похоже на порчу перевода (случайный третий язык вместо
            # русского) — одна повторная попытка обычно даёт нормальный
            # результат, так как Argos не детерминирован по батчам.
            retry = run_once()
            if not _CJK_RE.search(retry):
                translated = retry

        return lead + translated + trail

    def translate(self, text: str, use_glossary: bool = True) -> str:
        if not text or not text.strip():
            return text
        self._ensure_ready()

        parts = _PLACEHOLDER_RE.split(text)
        placeholders = _PLACEHOLDER_RE.findall(text)

        translated_parts = [self._translate_segment(part, use_glossary) for part in parts]

        result = translated_parts[0]
        for ph, part in zip(placeholders, translated_parts[1:]):
            result += ph + part
        return result


@lru_cache(maxsize=None)
def get_engine(source_lang: str, target_lang: str) -> TranslationEngine:
    return TranslationEngine(source_lang, target_lang)
