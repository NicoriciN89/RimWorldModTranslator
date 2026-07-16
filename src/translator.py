"""Обёртка над Argos Translate: офлайн-перевод строк с защитой плейсхолдеров
от искажения моделью перевода — какие именно плейсхолдеры защищаются и
почему, см. rimworld_rules.TRANSLATION_PLACEHOLDER_RE."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from functools import lru_cache
from pathlib import Path

# Сегментация предложений: MiniSBD (onnx-модель ~200 КБ) вместо Stanza —
# качество для наших коротких игровых строк то же (длинные тексты мы и сами
# режем, см. _SENTENCE_SPLIT_RE), а Stanza тянет за собой torch (~370 МБ в
# собранном exe). Выбор должен попасть в argostranslate.settings ДО первого
# импорта argostranslate (settings читает переменную при своём импорте);
# явно заданная пользователем переменная окружения уважается.
os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")

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

# Найдено на: alpha_memes ("Ocular Warping ritual" рядом с глоссарным
# токеном-заглушкой перед концом предложения). Модель иногда детерминированно
# обрывает генерацию сразу после токена-заглушки глоссария (см. glossary.py),
# теряя весь хвост предложения после термина — не порча в третий язык (CJK),
# а именно преждевременная остановка генерации. Грубая эвристика: если
# результат защищённого глоссарием перевода заметно короче (по числу слов),
# чем перевод БЕЗ глоссарной защиты того же текста, это подозрительно похоже
# на обрезание — откатываемся на перевод без глоссария для этого сегмента
# (термин останется на английском, но лучше это, чем потерянный хвост фразы).
_TRUNCATION_WORD_RATIO_THRESHOLD = 0.7

# Найдено на: alpha_memes. Длинные многострочные описания (300+ символов,
# несколько предложений/абзацев с rich-text разметкой вида <color=...>...
# </color>) Argos иногда молча ОБРЕЗАЕТ в конце — NMT-модель генерирует
# ограниченное число токенов на вход, и если оригинал длинный, хвост текста
# (вплоть до закрывающего тега вроде </color>) просто теряется без всякой
# ошибки. Разбиение на предложения перед переводом устраняет это: каждое
# предложение короче лимита модели и переводится/склеивается по отдельности.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# Сегменты короче этого не разбиваем — короткие фразы и так не обрезаются,
# а разбиение по предложениям только повредило бы согласование внутри фразы.
_LONG_SEGMENT_THRESHOLD = 200


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


def _find_bundled_candidate(source_lang: str, target_lang: str) -> Path | None:
    """Ищет папку встроенного (bundled) пакета Argos для этой пары языков
    среди bundled_packages/ — без побочных эффектов, только поиск."""
    root = _bundled_packages_root()
    if root is None:
        return None
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
            return candidate
    return None


def _copy_bundled_package_or_raise(candidate: Path, dest_dir: Path,
                                    source_lang: str, target_lang: str) -> None:
    """Копирует candidate в dest_dir (dest_dir не должна существовать на
    входе) и проверяет результат — общая часть между "устанавливаю с нуля" и
    "переустанавливаю неполную копию", чтобы не дублировать текст ошибки."""
    shutil.copytree(candidate, dest_dir)
    if not _bundled_copy_is_intact(candidate, dest_dir):
        raise ArgosPackageSetupError(
            f"Не удалось полностью скопировать встроенный языковой пакет "
            f"{source_lang}->{target_lang} — часть файлов отсутствует после "
            f"копирования. Обычно это антивирус, который в реальном времени "
            f"проверяет и временно блокирует/карантинит только что "
            f"распакованные файлы программы. Попробуйте: 1) добавить папку "
            f"программы в исключения антивируса, 2) подождать немного и "
            f"запустить перевод ещё раз, 3) убедиться, что файл "
            f"{dest_dir / 'sentencepiece.model'} не пропал из карантина."
        )


def _repair_bundled_package_if_broken(source_lang: str, target_lang: str) -> bool:
    """Если для этой пары языков есть встроенный пакет И уже "установленная"
    копия существует, но повреждена/неполна — переустанавливает её и
    возвращает True (вызывающему коду нужно сбросить lru_cache
    get_installed_languages(), см. _ensure_ready).

    Почему это нужно ДО опроса Argos "установлен ли язык": Argos Translate
    считает языковую пару установленной по одному факту существования папки
    пакета с валидным metadata.json — не проверяя файлы модели внутри. Если
    антивирус карантинирует файл модели сразу после распаковки exe
    (реальный случай, воспроизведённый пользователем), Argos продолжает
    считать пакет "установленным", и весь код установки/докачки (см. вызов
    ниже в _ensure_ready) просто никогда не вызывается — перевод падает на
    первой же строке с невнятной ошибкой ctranslate2, и без вмешательства
    извне это никогда не самоисправляется. Отсутствие встроенного пакета
    (candidate is None, напр. для языка, для которого нет bundled-версии)
    не является ошибкой — тогда просто нечем чинить, поведение не меняется."""
    import argostranslate.settings as settings

    candidate = _find_bundled_candidate(source_lang, target_lang)
    if candidate is None:
        return False

    dest_dir = settings.package_data_dir / candidate.name
    if not dest_dir.is_dir() or _bundled_copy_is_intact(candidate, dest_dir):
        return False

    log.warning("Встроенный пакет Argos %s->%s скопирован не полностью (%s) — "
                "переустанавливаю", source_lang, target_lang, dest_dir)
    shutil.rmtree(dest_dir)
    _copy_bundled_package_or_raise(candidate, dest_dir, source_lang, target_lang)
    return True


def _install_bundled_package(source_lang: str, target_lang: str) -> bool:
    """Копирует встроенный пакет Argos (если он есть в дистрибутиве для этой
    пары языков) прямо в папку установленных пакетов Argos — тот же эффект,
    что у package.install_from_path(), но без скачивания. Возвращает True,
    если подходящий встроенный пакет найден и скопирован (в том числе если
    уже был установлен ранее). Обычно вызывается только когда Argos ЕЩЁ НЕ
    считает языковую пару установленной (см. _ensure_ready) — основной
    случай повреждённой уже "установленной" копии перехватывает раньше
    _repair_bundled_package_if_broken. Проверка целостности здесь — вторая
    линия защиты на случай, если copytree сам оборвался на середине (диск
    кончился, процесс убили) в один и тот же запуск."""
    import argostranslate.settings as settings

    candidate = _find_bundled_candidate(source_lang, target_lang)
    if candidate is None:
        return False

    dest_dir = settings.package_data_dir / candidate.name
    if dest_dir.is_dir():
        if _bundled_copy_is_intact(candidate, dest_dir):
            return True
        shutil.rmtree(dest_dir)
    else:
        log.info("Устанавливаю встроенный пакет Argos %s->%s из %s (без скачивания)",
                  source_lang, target_lang, candidate)
    _copy_bundled_package_or_raise(candidate, dest_dir, source_lang, target_lang)
    return True


def _bundled_copy_is_intact(source: Path, dest: Path) -> bool:
    """Сверяет размеры всех файлов source и dest — быстрая (без хеширования)
    проверка, что shutil.copytree реально перенёс все байты, а не оставил
    dest частично скопированной/карантинированной антивирусом папкой,
    которая выглядит как валидная (dest_dir.is_dir() == True), но у которой
    внутри не хватает или повреждён один из файлов модели."""
    for src_file in source.rglob("*"):
        if src_file.is_dir():
            continue
        dest_file = dest / src_file.relative_to(source)
        try:
            if not dest_file.is_file() or dest_file.stat().st_size != src_file.stat().st_size:
                return False
        except OSError:
            return False
    return True


def _install_bundled_minisbd_models() -> None:
    """Копирует встроенные onnx-модели сегментации предложений MiniSBD (en —
    исходный язык почти всех модов) в кэш, откуда их читает argostranslate.
    Без этого первый запуск скачивал бы модель из интернета (~200 КБ) — мелочь,
    но ломает обещание полностью офлайн-перевода."""
    import argostranslate.settings as settings

    root = _bundled_packages_root()
    if root is None:
        return
    src_dir = root / "minisbd"
    if not src_dir.is_dir():
        return
    dest_dir = Path(settings.data_dir) / "minisbd"
    for model in src_dir.glob("*.onnx"):
        dest = dest_dir / model.name
        if dest.is_file() and dest.stat().st_size == model.stat().st_size:
            continue
        # Файл может существовать, но быть недокопированным с прошлого
        # запуска (та же причина, что у _bundled_copy_is_intact выше —
        # антивирус временно блокирует свежераспакованные файлы) — размер
        # не совпадёт, и copy2 просто перезапишет его целиком.
        log.info("Устанавливаю встроенную модель сегментации MiniSBD: %s", model.name)
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(model, dest)


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

        _install_bundled_minisbd_models()

        # Argos Translate считает языковую пару "установленной" по одному
        # факту существования папки пакета с валидным metadata.json — не
        # проверяя, что файлы модели внутри реально целые. Раз в процессе
        # мы можем починить встроенный (bundled) пакет, если он битый, надо
        # сделать это ДО опроса get_installed_languages(), иначе Argos своим
        # ответом "уже установлен" целиком скрывает от нас необходимость
        # чинить — ровно тот баг, который уронил перевод у пользователя,
        # чью копию пакета антивирус карантинировал сразу после распаковки.
        repaired = _repair_bundled_package_if_broken(self.source_lang, self.target_lang)
        if repaired:
            translate.get_installed_languages.cache_clear()

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

    def _translate_short(self, stripped: str, use_glossary: bool) -> str:
        """Переводит один короткий (гарантированно не обрезаемый моделью по
        длине) кусок текста — с защитой глоссария, повторной попыткой при
        порче в случайный третий язык, и откатом на перевод без глоссария
        при подозрении на обрезание из-за токена-заглушки (см. комментарий
        у _TRUNCATION_WORD_RATIO_THRESHOLD)."""
        with_glossary = use_glossary and self.target_lang == "ru"

        def run_with_glossary() -> str:
            ctx = GlossaryContext()
            return ctx.restore(self._translate_raw(ctx.protect(stripped)))

        if not with_glossary:
            return self._translate_raw(stripped)

        translated = run_with_glossary()
        if self.target_lang == "ru" and _CJK_RE.search(translated):
            # Похоже на порчу перевода (случайный третий язык вместо
            # русского) — одна повторная попытка обычно даёт нормальный
            # результат, так как Argos не детерминирован по батчам.
            retry = run_with_glossary()
            if not _CJK_RE.search(retry):
                translated = retry

        source_words = len(stripped.split())
        translated_words = len(translated.split())
        if source_words >= 4 and translated_words < source_words * _TRUNCATION_WORD_RATIO_THRESHOLD:
            without_glossary = self._translate_raw(stripped)
            if len(without_glossary.split()) > translated_words:
                translated = without_glossary
        return translated

    def _translate_segment(self, part: str, use_glossary: bool) -> str:
        """Переводит один сегмент, сохраняя его ведущие/замыкающие пробелы
        буквально — модель обычно их обрезает при переводе. Игровые термины
        RimWorld (см. glossary.py) защищаются от Argos и подставляются как
        устоявшийся русский вариант уже после машинного перевода.

        Длинные сегменты (см. _LONG_SEGMENT_THRESHOLD) режутся на отдельные
        предложения и переводятся по одному — иначе NMT-модель может молча
        обрезать хвост длинного текста, теряя конец предложения или
        закрывающий rich-text тег вроде </color> (см. _SENTENCE_SPLIT_RE)."""
        if not part:
            return part
        stripped = part.strip()
        if not stripped:
            return part
        lead = part[:len(part) - len(part.lstrip())]
        trail = part[len(part.rstrip()):]

        if len(stripped) <= _LONG_SEGMENT_THRESHOLD:
            translated = self._translate_short(stripped, use_glossary)
        else:
            sentences = _SENTENCE_SPLIT_RE.split(stripped)
            translated = " ".join(self._translate_short(s, use_glossary) for s in sentences if s)

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
