"""Тесты src/diagnostics.py: диагностический снимок окружения в лог.

Идея пользователя: раз "у меня не работает" отчёты от людей, до которых
нельзя дотянуться напрямую (см. историю с sentencepiece.model в
test_bundled_install.py/test_translator.py), стоят нескольких раундов
переписки только чтобы узнать версию антивируса и свободное место на диске —
логировать эту информацию сразу, автоматически, при каждом запуске. Все
источники (WMI, PowerShell) недоступны в тестовом окружении/CI как есть, так
что тесты проверяют устойчивость к сбоям сбора данных, а не точность самих
системных фактов."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.diagnostics import (
    _disk_info, _folder_access, _security_products, log_environment_snapshot, log_model_file_probe,
)


def test_security_products_returns_empty_list_when_powershell_unavailable() -> None:
    """Если PowerShell недоступен/запрещён политикой — не роняем программу,
    просто возвращаем пустой список (снимок логирует это как отдельную
    строку, см. log_environment_snapshot)."""
    with patch("src.diagnostics._run_powershell", return_value=None):
        assert _security_products() == []


def test_security_products_parses_single_product_json() -> None:
    """Get-CimInstance с единственным результатом отдаёт JSON-объект, а не
    массив — ConvertTo-Json так себя ведёт для одного элемента коллекции."""
    with patch("src.diagnostics._run_powershell",
               return_value='{"displayName": "Windows Defender"}'):
        assert _security_products() == ["Windows Defender"]


def test_security_products_parses_multiple_products_json() -> None:
    with patch("src.diagnostics._run_powershell",
               return_value='[{"displayName": "Defender"}, {"displayName": "Kaspersky"}]'):
        assert _security_products() == ["Defender", "Kaspersky"]


def test_security_products_survives_malformed_json() -> None:
    with patch("src.diagnostics._run_powershell", return_value="not json at all"):
        assert _security_products() == []


def test_disk_info_reports_missing_path_without_raising(tmp_path: Path) -> None:
    """Папка программы всегда существует на практике (мы же из неё
    запущены), но проверка не должна падать даже на несуществующем пути —
    лучше одна строка "не удалось узнать", чем упавший на старте снимок."""
    missing = tmp_path / "does_not_exist_at_all"
    result = _disk_info(missing)
    assert isinstance(result, str)


def test_disk_info_includes_free_space_for_real_path(tmp_path: Path) -> None:
    result = _disk_info(tmp_path)
    assert "GB" in result


def test_folder_access_reports_ok_for_writable_dir(tmp_path: Path) -> None:
    assert _folder_access(tmp_path) == "read/write OK"


def test_folder_access_reports_problem_for_unwritable_path(tmp_path: Path) -> None:
    """Реальная симуляция прав "только чтение" платформонезависима плохо
    (Windows ACL не совпадает с os.chmod), поэтому берём заведомо
    несуществующую вложенную папку — probe.write_bytes упадёт с OSError,
    ровно тот же код пути, что и при реальной проблеме с правами."""
    unwritable = tmp_path / "missing_parent" / "nested"
    result = _folder_access(unwritable)
    assert "ACCESS PROBLEM" in result


def test_log_environment_snapshot_does_not_raise_when_all_probes_fail(tmp_path: Path) -> None:
    """Главный контракт снимка: он не должен ронять запуск программы, даже
    если вообще ни один источник диагностики не сработал (PowerShell
    запрещён, WMI недоступен и т.п.) — лучше неполный лог, чем незапустившаяся
    программа."""
    with patch("src.diagnostics._run_powershell", return_value=None):
        log_environment_snapshot(tmp_path)


def test_log_model_file_probe_logs_success_for_readable_file(tmp_path: Path) -> None:
    model = tmp_path / "sentencepiece.model"
    model.write_bytes(b"x" * 100)
    with patch("src.diagnostics.log") as fake_log:
        log_model_file_probe(model)
    assert fake_log.info.called
    assert not fake_log.warning.called


def test_log_model_file_probe_logs_warning_for_unreadable_file(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist" / "sentencepiece.model"
    with patch("src.diagnostics.log") as fake_log:
        log_model_file_probe(missing)
    assert fake_log.warning.called
    assert not fake_log.info.called
