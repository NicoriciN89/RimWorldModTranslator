"""Точка входа для сборки в .exe (PyInstaller).

Без аргументов открывает GUI-окно. С аргументами командной строки работает
как CLI (см. src/main.py --help) — так собранный .exe можно использовать в
скриптах/автоматизации без установки Python. Учтите: exe собран оконным
(console=False), поэтому текстовый вывод CLI не виден — смотрите лог-файл
и код возврата; результат в любом случае пишется в --out."""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from src.main import main
    else:
        from src.gui import main
    main()
