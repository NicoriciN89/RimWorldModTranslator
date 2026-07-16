"""Тесты src/translator.py: установка встроенного (bundled) языкового пакета
Argos без скачивания.

Найден реальный баг у пользователя: антивирус карантинировал файл модели
сразу после распаковки exe, оставляя папку пакета "существующей", но
неполной (без sentencepiece.model). Хуже того — Argos Translate считает
языковую пару установленной по одному факту существования папки пакета с
валидным metadata.json, не проверяя файлы модели внутри, поэтому весь код
установки/докачки НИКОГДА не вызывался — перевод падал на первой строке с
невнятной ошибкой ctranslate2, без единого шанса на самоисправление даже
при повторных запусках. Починка требует ДВУХ вещей: обнаружить неполноту
(_bundled_copy_is_intact) и вызвать проверку ДО опроса Argos
(_repair_bundled_package_if_broken), а не только внутри пути "пакет ещё не
установлен" (_install_bundled_package)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import argostranslate.settings as argos_settings

from src.translator import (
    ArgosPackageSetupError,
    _bundled_copy_is_intact, _install_bundled_package, _repair_bundled_package_if_broken,
)


def _write(path: Path, content: bytes = b"data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _make_bundled_package(bundled_root: Path) -> Path:
    package_src = bundled_root / "translate-en_ru-1_9"
    _write(package_src / "metadata.json",
           json.dumps({"from_code": "en", "to_code": "ru"}).encode("utf-8"))
    _write(package_src / "sentencepiece.model", b"x" * 100)
    _write(package_src / "model" / "model.bin", b"y" * 500)
    return package_src


def test_intact_copy_is_detected(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    _write(src / "sentencepiece.model", b"x" * 100)
    _write(src / "model" / "model.bin", b"y" * 500)
    _write(dest / "sentencepiece.model", b"x" * 100)
    _write(dest / "model" / "model.bin", b"y" * 500)

    assert _bundled_copy_is_intact(src, dest)


def test_missing_file_is_detected_as_incomplete(tmp_path: Path) -> None:
    """Ровно баг из отчёта пользователя: dest_dir существует, но
    sentencepiece.model в ней нет (антивирус карантинировал файл)."""
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    _write(src / "sentencepiece.model", b"x" * 100)
    _write(src / "model" / "model.bin", b"y" * 500)
    _write(dest / "model" / "model.bin", b"y" * 500)  # sentencepiece.model отсутствует

    assert not _bundled_copy_is_intact(src, dest)


def test_truncated_file_is_detected_as_incomplete(tmp_path: Path) -> None:
    """Файл существует, но короче оригинала — тоже неполная копия."""
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    _write(src / "sentencepiece.model", b"x" * 100)
    _write(dest / "sentencepiece.model", b"x" * 40)

    assert not _bundled_copy_is_intact(src, dest)


def test_size_matching_but_unreadable_sentencepiece_is_detected_as_incomplete(tmp_path: Path) -> None:
    """Реальный внешний отчёт (Minduster, v1.4.3): stat() показывал у
    sentencepiece.model правильный размер (совпадающий с исходником), но сам
    файл нельзя было открыть на чтение — sentencepiece падал с "No such file
    or directory" при каждой попытке перевода, на каждом перезапуске
    программы, даже с полностью отключённым антивирусом. Проверка только по
    размеру такие файлы-заглушки пропускала как "целые"."""
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    _write(src / "sentencepiece.model", b"x" * 100)
    _write(dest / "sentencepiece.model", b"x" * 100)

    with patch("src.translator._file_is_actually_readable", return_value=False):
        assert not _bundled_copy_is_intact(src, dest)


def test_copy_raises_distinct_error_when_source_itself_is_unreadable(tmp_path: Path) -> None:
    """Если даже исходный (встроенный в программу) sentencepiece.model
    нельзя прочитать, переустановка пакета никогда не поможет — пользователю
    нужно чинить сам установленный дистрибутив программы, а не папку с
    языковыми пакетами. Сообщение об ошибке должно это явно называть, а не
    советовать "подождать и попробовать снова"."""
    from src.translator import _copy_bundled_package_or_raise

    candidate = tmp_path / "bundled" / "translate-en_ru-1_9"
    dest_dir = tmp_path / "installed" / "translate-en_ru-1_9"
    _write(candidate / "sentencepiece.model", b"x" * 100)

    def fake_readable(path: Path) -> bool:
        return path.name != "sentencepiece.model"

    with patch("src.translator._file_is_actually_readable", side_effect=fake_readable):
        try:
            _copy_bundled_package_or_raise(candidate, dest_dir, "en", "ru")
            assert False, "ожидалось ArgosPackageSetupError"
        except ArgosPackageSetupError as e:
            assert "внутри самой программы" in str(e)


def test_repair_reinstalls_broken_copy_argos_still_thinks_is_installed(tmp_path: Path) -> None:
    """Главный сценарий бага: Argos бы посчитал эту папку установленной
    (metadata.json валиден), но sentencepiece.model отсутствует —
    _repair_bundled_package_if_broken должна это заметить и переустановить
    БЕЗ участия _install_bundled_package (который бы даже не вызвался,
    потому что путь "уже установлен" в _ensure_ready никогда не доходит до
    кода установки)."""
    bundled_root = tmp_path / "bundled_packages"
    _make_bundled_package(bundled_root)

    package_data_dir = tmp_path / "installed_packages"
    dest = package_data_dir / "translate-en_ru-1_9"
    _write(dest / "metadata.json",
           json.dumps({"from_code": "en", "to_code": "ru"}).encode("utf-8"))
    _write(dest / "model" / "model.bin", b"y" * 500)  # sentencepiece.model отсутствует

    with patch("src.translator._bundled_packages_root", return_value=bundled_root), \
         patch.object(argos_settings, "package_data_dir", package_data_dir):
        repaired = _repair_bundled_package_if_broken("en", "ru")

    assert repaired is True
    assert (dest / "sentencepiece.model").is_file()
    assert (dest / "sentencepiece.model").read_bytes() == b"x" * 100


def test_repair_leaves_intact_copy_alone(tmp_path: Path) -> None:
    """Полная копия не должна пересоздаваться на каждом запуске — только
    diff-проверка размеров, без лишнего copytree."""
    bundled_root = tmp_path / "bundled_packages"
    _make_bundled_package(bundled_root)

    package_data_dir = tmp_path / "installed_packages"
    dest = package_data_dir / "translate-en_ru-1_9"
    _write(dest / "metadata.json",
           json.dumps({"from_code": "en", "to_code": "ru"}).encode("utf-8"))
    _write(dest / "sentencepiece.model", b"x" * 100)
    _write(dest / "model" / "model.bin", b"y" * 500)
    marker = dest / "sentencepiece.model"
    original_mtime = marker.stat().st_mtime

    with patch("src.translator._bundled_packages_root", return_value=bundled_root), \
         patch.object(argos_settings, "package_data_dir", package_data_dir):
        repaired = _repair_bundled_package_if_broken("en", "ru")

    assert repaired is False
    assert marker.stat().st_mtime == original_mtime


def test_repair_does_nothing_when_not_yet_installed(tmp_path: Path) -> None:
    """Пакет для этой пары ещё не установлен вовсе (нет dest_dir) —
    _repair_bundled_package_if_broken не должна его устанавливать, это
    задача _install_bundled_package (вызывается отдельно в _ensure_ready)."""
    bundled_root = tmp_path / "bundled_packages"
    _make_bundled_package(bundled_root)
    package_data_dir = tmp_path / "installed_packages"

    with patch("src.translator._bundled_packages_root", return_value=bundled_root), \
         patch.object(argos_settings, "package_data_dir", package_data_dir):
        repaired = _repair_bundled_package_if_broken("en", "ru")

    assert repaired is False
    assert not (package_data_dir / "translate-en_ru-1_9").exists()


def test_repair_does_nothing_when_no_bundled_package_for_pair(tmp_path: Path) -> None:
    """Языковая пара, для которой в дистрибутиве нет встроенного пакета
    (напр. en->de) — не ошибка, просто нечем чинить."""
    bundled_root = tmp_path / "bundled_packages"
    _make_bundled_package(bundled_root)  # только en->ru
    package_data_dir = tmp_path / "installed_packages"
    _write(package_data_dir / "translate-en_de-1_0" / "metadata.json")

    with patch("src.translator._bundled_packages_root", return_value=bundled_root), \
         patch.object(argos_settings, "package_data_dir", package_data_dir):
        repaired = _repair_bundled_package_if_broken("en", "de")

    assert repaired is False


def test_install_reinstalls_incomplete_copy_left_from_partial_run(tmp_path: Path) -> None:
    """_install_bundled_package (путь "ещё не установлен" в _ensure_ready)
    тоже должна обнаруживать и чинить неполную копию — на случай, если
    предыдущий запуск успел скопировать часть файлов и упасть на середине
    copytree (напр. диск закончился или процесс убили)."""
    bundled_root = tmp_path / "bundled_packages"
    _make_bundled_package(bundled_root)

    package_data_dir = tmp_path / "installed_packages"
    dest = package_data_dir / "translate-en_ru-1_9"
    _write(dest / "model" / "model.bin", b"y" * 500)  # копия без metadata.json и sentencepiece.model

    with patch("src.translator._bundled_packages_root", return_value=bundled_root), \
         patch.object(argos_settings, "package_data_dir", package_data_dir):
        result = _install_bundled_package("en", "ru")

    assert result is True
    assert (dest / "sentencepiece.model").is_file()


def test_install_leaves_already_intact_copy_alone(tmp_path: Path) -> None:
    """Полная копия не должна пересоздаваться на каждом запуске — только
    diff-проверка размеров, без лишнего copytree."""
    bundled_root = tmp_path / "bundled_packages"
    _make_bundled_package(bundled_root)

    package_data_dir = tmp_path / "installed_packages"
    dest = package_data_dir / "translate-en_ru-1_9"
    _write(dest / "metadata.json",
           json.dumps({"from_code": "en", "to_code": "ru"}).encode("utf-8"))
    _write(dest / "sentencepiece.model", b"x" * 100)
    _write(dest / "model" / "model.bin", b"y" * 500)
    marker = dest / "sentencepiece.model"
    original_mtime = marker.stat().st_mtime

    with patch("src.translator._bundled_packages_root", return_value=bundled_root), \
         patch.object(argos_settings, "package_data_dir", package_data_dir):
        result = _install_bundled_package("en", "ru")

    assert result is True
    assert marker.stat().st_mtime == original_mtime
