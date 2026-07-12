"""print(), который не падает, если stdout/stderr отсутствуют — как в
windowed-сборке PyInstaller (--windowed), где у процесса нет консоли и
sys.stdout/sys.stderr равны None."""
from __future__ import annotations

import builtins
import sys


def safe_print(*args, **kwargs) -> None:
    target = kwargs.get("file", sys.stdout)
    if target is None:
        return
    builtins.print(*args, **kwargs)
