"""Диагностический снимок окружения для лога — не чинит ничего сам по себе,
но резко сокращает время разбора отчётов вида "у меня не работает" от
пользователей, до которых нельзя дотянуться напрямую (см. историю багов с
sentencepiece.model, где несколько раундов переписки уходило только на то,
чтобы узнать версию антивируса и свободное место на диске). Все вызовы —
best-effort: если что-то не удалось узнать (WMI недоступен, PowerShell
запрещён политикой и т.п.), пишем это в снимок как отдельную строку, а не
роняем программу и не пропускаем весь снимок целиком."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .log_setup import get_logger

log = get_logger("diagnostics")

_SUBPROCESS_TIMEOUT_SECONDS = 10


def _run_powershell(command: str) -> str | None:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _security_products() -> list[str]:
    """Список активных антивирусов/защитного ПО через Windows Security
    Center (WMI root/SecurityCenter2) — источник, которым сама Windows
    пользуется для панели "Безопасность Windows". Работает только для
    основной сессии пользователя (не для служб/SYSTEM), но GUI-программа
    всегда запускается из-под обычного пользователя, так что это не проблема
    здесь."""
    output = _run_powershell(
        "Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct "
        "-ErrorAction SilentlyContinue | Select-Object displayName | ConvertTo-Json -Compress"
    )
    if not output:
        return []
    try:
        data = json.loads(output)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]
    names = [item.get("displayName") for item in data if isinstance(item, dict) and item.get("displayName")]
    return names


def _disk_info(path: Path) -> str:
    try:
        usage = shutil.disk_usage(path)
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
    except OSError as e:
        return f"could not determine free space ({e})"

    drive = path.resolve().drive.rstrip(":")
    fs_type = "unknown"
    if drive:
        output = _run_powershell(
            f"Get-Volume -DriveLetter {drive} -ErrorAction SilentlyContinue | "
            f"Select-Object FileSystem | ConvertTo-Json -Compress"
        )
        if output:
            try:
                fs_type = json.loads(output).get("FileSystem", fs_type)
            except (ValueError, AttributeError):
                pass
    return f"{free_gb:.1f} GB free out of {total_gb:.1f} GB, filesystem {fs_type}"


def _windows_version() -> str:
    try:
        return f"{sys.getwindowsversion()}"  # type: ignore[attr-defined]
    except AttributeError:
        return "not Windows or unavailable"


def _folder_access(path: Path) -> str:
    """Реальная проверка прав, а не предположение по владельцу — пытаемся
    действительно создать и удалить временный файл в этой папке."""
    probe = path / ".rmt_access_probe.tmp"
    try:
        probe.write_bytes(b"x")
        probe.unlink()
        return "read/write OK"
    except OSError as e:
        return f"ACCESS PROBLEM: {e}"


def log_environment_snapshot(app_dir: Path) -> None:
    """Пишет один раз при старте программы блок с диагностикой окружения —
    антивирус, диск, версия Windows, права на папку программы. Не влияет на
    работу программы, только на содержимое лога."""
    log.info("--- Environment diagnostic snapshot ---")
    log.info("Windows version: %s", _windows_version())
    log.info("Program folder: %s", app_dir)
    log.info("Program folder access: %s", _folder_access(app_dir))
    log.info("Program disk: %s", _disk_info(app_dir))

    products = _security_products()
    if products:
        log.info("Active security software: %s", ", ".join(products))
    else:
        log.info("Active security software: could not determine via Windows Security Center "
                 "(may be unavailable, disabled by policy, or the antivirus does not "
                 "register with Security Center)")
    log.info("--- End of diagnostic snapshot ---")


def log_model_file_probe(model_path: Path) -> None:
    """Замеряет реальное время открытия файла языковой модели — вызывается
    из translator.py в момент ArgosPackageSetupError, чтобы зафиксировать,
    было ли открытие аномально долгим (типичный признак вмешательства
    антивируса/EDR в реальном времени) или файл был просто недоступен сразу.
    Отдельная функция от log_environment_snapshot, потому что вызывается не
    при старте, а именно в момент сбоя — тайминг в момент самого сбоя
    информативнее любого снимка "на всякий случай" при старте."""
    import time

    start = time.monotonic()
    try:
        with model_path.open("rb") as f:
            f.read(4096)
        elapsed = time.monotonic() - start
        log.info("Model file probe %s: opened and read in %.3fs (size %s bytes)",
                  model_path, elapsed, model_path.stat().st_size if model_path.exists() else "?")
    except OSError as e:
        elapsed = time.monotonic() - start
        log.warning("Model file probe %s: FAILED to open after %.3fs — %s",
                    model_path, elapsed, e)
