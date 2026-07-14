"""Обёртка над Argos Translate: офлайн-перевод строк с защитой плейсхолдеров
от искажения моделью перевода — какие именно плейсхолдеры защищаются и
почему, см. rimworld_rules.TRANSLATION_PLACEHOLDER_RE."""
from __future__ import annotations

import json
import re
import shutil
import sys
from functools import lru_cache
from pathlib import Path

from .glossary import GlossaryContext
from .rimworld_rules import TRANSLATION_PLACEHOLDER_RE as _PLACEHOLDER_RE
from .safe_print import safe_print
from .log_setup import get_logger

log = get_logger("translator")

# Argos иногда даёт перевод не на целевой язык вместо русского для редких/
# составных слов, которых нет в её словаре (напр. случайные китайские
# иероглифы вместо перевода). У кириллицы и CJK нет общих символов, так что
# наличие CJK в результате при target_lang="ru" — надёжный признак порчи.
_CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힣]")


_PACKAGE_INDEX_TIMEOUT_SECONDS = 30
_PACKAGE_DOWNLOAD_TIMEOUT_SECONDS = 300

# Имя папки пакета внутри bundled_packages/ — совпадает с именем, которое
# сам Argos Translate даёт установленному пакету на диске.
_BUNDLED_PACKAGES_DIRNAME = "bundled_packages"


def _bundled_packages_root() -> Path | None:
    """Папка со встроенными в дистрибутив пакетами Argos (сейчас только
    en->ru — самая частая пара для перевода модов RimWorld на русский).
    Кладём её сюда, чтобы избавить пользователя от скачивания ~200 МБ через
    интернет при первом запуске — раньше это тихо зависало без прогресса
    при слабом/заблокированном соединении (см. ArgosPackageSetupError)."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base = Path(__file__).resolve().parent.parent
    candidate = base / _BUNDLED_PACKAGES_DIRNAME
    return candidate if candidate.is_dir() else None


def _install_bundled_package(source_lang: str, target_lang: str) -> bool:
    """Копирует встроенный пакет Argos (если он есть в дистрибутиве для этой
    пары языков) прямо в папку установленных пакетов Argos — тот же эффект,
    что у package.install_from_path(), но без скачивания. Возвращает True,
    если подходящий встроенный пакет найден и скопирован."""
    import argostranslate.settings as settings

    root = _bundled_packages_root()
    if root is None:
        return False

    for candidate in root.iterdir():
        if not candidate.is_dir():
            continue
        metadata_path = candidate / "metadata.json"
        if not metadata_path.is_file():
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if metadata.get("from_code") == source_lang and metadata.get("to_code") == target_lang:
            dest_dir = settings.package_data_dir / candidate.name
            if dest_dir.is_dir():
                return True
            log.info("Устанавливаю встроенный пакет Argos %s->%s из %s (без скачивания)",
                      source_lang, target_lang, candidate)
            shutil.copytree(candidate, dest_dir)
            return True
    return False


class ArgosPackageSetupError(RuntimeError):
    """Не удалось подготовить языковой пакет Argos (сеть недоступна/заблокирована,
    таймаут скачивания и т.п.) — отдельный тип, чтобы GUI/CLI могли показать
    пользователю понятную причину вместо голого зависания без объяснений."""


class TranslationEngine:
    """Ленивая инициализация Argos Translate: тяжёлый импорт/загрузка моделей
    откладывается до первого реального перевода."""

    def __init__(self, source_lang: str, target_lang: str):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self._translation = None

    def is_ready(self) -> bool:
        return self._translation is not None

    def ensure_ready(self) -> None:
        self._ensure_ready()

    def _ensure_ready(self) -> None:
        if self._translation is not None:
            return
        import argostranslate.package as package
        import argostranslate.translate as translate

        installed = translate.get_installed_languages()
        from_lang = next((l for l in installed if l.code == self.source_lang), None)
        to_lang = next((l for l in installed if l.code == self.target_lang), None)

        if from_lang is None or to_lang is None:
            if _install_bundled_package(self.source_lang, self.target_lang):
                safe_print(f"[translator] Пакет {self.source_lang}->{self.target_lang} установлен "
                           f"из встроенных в программу файлов (без скачивания).", file=sys.stderr)
            else:
                safe_print(f"[translator] Пакет {self.source_lang}->{self.target_lang} не установлен, "
                           f"скачиваю...", file=sys.stderr)
                self._download_and_install_package(package)

            # get_installed_languages() внутри самого argostranslate декорирован
            # @lru_cache — первый вызов (когда пакет ещё не установлен) навсегда
            # кэширует пустой результат, и без явного сброса кэша повторный
            # вызов после установки пакета вернул бы тот же пустой список,
            # из-за чего перевод падал бы с "языковая пара не найдена" сразу
            # после первой установки пакета (что бы мы ни делали — качали его
            # сами или брали из встроенного ресурса).
            translate.get_installed_languages.cache_clear()
            installed = translate.get_installed_languages()
            from_lang = next(l for l in installed if l.code == self.source_lang)
            to_lang = next(l for l in installed if l.code == self.target_lang)

        self._translation = from_lang.get_translation(to_lang)

    def _download_and_install_package(self, package) -> None:
        """Обновление индекса пакетов и само скачивание — единственные места
        в этой программе, где для перевода Argos нужен интернет. Оборачиваем
        таймаутом: без него зависший/заблокированный (файрвол, антивирус,
        VPN с полным перехватом трафика) сетевой запрос выглядел бы как
        бесконечное "зависание" программы без единого сообщения об ошибке."""
        import socket

        default_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(_PACKAGE_INDEX_TIMEOUT_SECONDS)
            package.update_package_index()
            available = package.get_available_packages()
        except OSError as e:
            raise ArgosPackageSetupError(
                f"Не удалось получить список языковых пакетов Argos Translate "
                f"(нет интернета или он заблокирован файрволом/антивирусом/VPN): {e}"
            ) from e
        finally:
            socket.setdefaulttimeout(default_timeout)

        match = next((p for p in available
                      if p.from_code == self.source_lang and p.to_code == self.target_lang),
                     None)
        if match is None:
            raise RuntimeError(
                f"Argos Translate не предоставляет пару {self.source_lang}->{self.target_lang}. "
                f"Проверьте коды языков (ISO 639-1)."
            )

        try:
            socket.setdefaulttimeout(_PACKAGE_DOWNLOAD_TIMEOUT_SECONDS)
            download_path = match.download()
        except OSError as e:
            raise ArgosPackageSetupError(
                f"Не удалось скачать языковой пакет Argos Translate {self.source_lang}->"
                f"{self.target_lang} (нет интернета, он заблокирован, или соединение "
                f"слишком медленное/оборвалось): {e}"
            ) from e
        finally:
            socket.setdefaulttimeout(default_timeout)

        package.install_from_path(download_path)

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
