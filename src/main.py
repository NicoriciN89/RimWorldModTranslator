"""CLI: локальный офлайн-переводчик модов RimWorld.

Пример:
    python -m src.main --src "../3761869362_psycasts" --lang ru --out ./output
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from . import generator, incremental, scanner
from .generator import rimworld_lang_dir_name
from .llm_polish import LANG_HUMAN_NAMES, LlmContext, LlmPolisher
from .log_setup import get_logger
from .safe_print import safe_print
from .translator import get_engine

log = get_logger("main")

if sys.stdout is not None and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr is not None and sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

ProgressCallback = Callable[[int, int, str], None]


def _default_progress(done: int, total: int, message: str) -> None:
    if message:
        safe_print(message)
        return
    _progress(done, total)


def translate_mod(src: Path, out_dir: Path, source_lang: str, target_lang: str,
                   on_progress: ProgressCallback = _default_progress,
                   use_llm: bool = False, llm_model: str = "qwen2.5:7b",
                   use_argos: bool = True, update: bool = False) -> Path:
    if not src.is_dir():
        raise ValueError(f"Папка мода не найдена: {src}")
    if not use_argos and not use_llm:
        raise ValueError("Нужен хотя бы один движок перевода: Argos или LLM.")

    on_progress(0, 0, f"[1/4] Сканирую мод: {src}")
    scan = scanner.scan_mod(src)
    if scan.source_lang_dir:
        on_progress(0, 0, f"      Найден Languages/English — Keyed: {len(scan.keyed)} файлов, "
                           f"DefInjected: {len(scan.def_injected)} файлов")
    else:
        on_progress(0, 0, f"      Languages/English отсутствует — извлекаю строки из Defs напрямую. "
                           f"Сгенерировано DefInjected-файлов: {len(scan.def_injected)}")

    total_strings = sum(len(t.data.keyed_items()) for t in scan.keyed) + \
        sum(len(t.data.keyed_items()) for t in scan.def_injected)
    if total_strings == 0:
        raise ValueError("Переводимых строк не найдено — проверьте, что это папка мода RimWorld.")

    mod_name = src.name
    out_root = out_dir / f"{mod_name}_{target_lang.upper()}"
    lang_dir_name = rimworld_lang_dir_name(target_lang)

    english_by_key = {
        entry.key: entry.text
        for task in list(scan.keyed) + list(scan.def_injected)
        for entry in task.data.keyed_items()
    }

    reused_keys: set[str] = set()
    if update:
        reused_keys = incremental.apply_incremental(scan, out_root, lang_dir_name)
        to_translate = total_strings - len(reused_keys)
        on_progress(0, total_strings, f"[2/4] Режим обновления: {len(reused_keys)} строк без "
                                       f"изменений (пропущены), {to_translate} новых/изменённых к переводу.")
    else:
        on_progress(0, total_strings, f"[2/4] Всего строк к переводу: {total_strings}")

    engine_label = {
        (True, True): "Argos + LLM, двумя проходами",
        (True, False): "только Argos",
        (False, True): "только LLM",
    }[(use_argos, use_llm)]
    on_progress(0, total_strings, f"[3/4] Перевожу {source_lang} -> {target_lang} ({engine_label})...")

    engine = get_engine(source_lang, target_lang) if use_argos else None
    lang_name = LANG_HUMAN_NAMES.get(target_lang.lower(), target_lang)
    polisher = LlmPolisher(model=llm_model, lang_name=lang_name, enabled=use_llm)

    if use_llm:
        if polisher.is_available():
            on_progress(0, total_strings, f"      LLM-доработка включена: Ollama/{llm_model} найдена.")
        else:
            on_progress(0, total_strings, f"      LLM-доработка запрошена, но Ollama/{llm_model} "
                                           f"недоступна — использую только доступный движок.")

    entries_to_translate = [
        entry
        for task in list(scan.keyed) + list(scan.def_injected)
        for entry in task.data.keyed_items()
        if entry.key not in reused_keys
    ]

    done = len(reused_keys)
    on_progress(done, total_strings, "")

    if use_argos:
        pass_label = "[3a/4] Argos" if use_llm else "[3/4] Argos"
        on_progress(done, total_strings, f"{pass_label}: перевожу черновик для {len(entries_to_translate)} строк...")
        for entry in entries_to_translate:
            log.debug("[Argos %d/%d] перевожу %s", done + 1, total_strings, entry.key)
            entry.text = engine.translate(entry.text)
            done += 1
            on_progress(done, total_strings, "")

    if use_llm:
        done = len(reused_keys)
        pass_label = "[3b/4] LLM" if use_argos else "[3/4] LLM"
        on_progress(done, total_strings, f"{pass_label}: дорабатываю {len(entries_to_translate)} строк "
                                          f"через {llm_model}...")
        for entry in entries_to_translate:
            log.debug("[LLM %d/%d] дорабатываю %s", done + 1, total_strings, entry.key)
            original_text = english_by_key[entry.key]
            entry.text = polisher.polish(original_text, entry.text, LlmContext(mod_name, entry.key))
            done += 1
            on_progress(done, total_strings, "")

    on_progress(done, total_strings, f"[4/4] Собираю мод-русификатор: {out_root}")

    original = generator.read_original_about(src)
    generator.write_about_xml(out_root, original, target_lang)
    generator.write_translated_mod(out_root, scan, target_lang)
    incremental.save_cache(out_root, english_by_key)

    on_progress(done, total_strings, f"Готово: {out_root}")
    return out_root


def _progress(done: int, total: int) -> None:
    width = 30
    filled = int(width * done / total)
    bar = "#" * filled + "-" * (width - filled)
    safe_print(f"\r      [{bar}] {done}/{total}", end="", file=sys.stderr, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Локальный офлайн-переводчик модов RimWorld")
    parser.add_argument("--src", required=True, type=Path, help="Путь к папке мода")
    parser.add_argument("--out", required=True, type=Path, help="Папка, куда собрать перевод")
    parser.add_argument("--source-lang", default="en", help="Код исходного языка (по умолчанию en)")
    parser.add_argument("--lang", required=True, help="Код целевого языка (ru, de, fr, ...)")
    parser.add_argument("--llm", action="store_true",
                         help="Дорабатывать черновик Argos локальной LLM через Ollama (если она запущена)")
    parser.add_argument("--llm-model", default="qwen2.5:7b", help="Модель Ollama для доработки перевода")
    parser.add_argument("--no-argos", action="store_true",
                         help="Не использовать Argos Translate — переводить только через LLM (--llm обязателен)")
    parser.add_argument("--update", action="store_true",
                         help="Доперевод: переводить только новые/изменившиеся строки, "
                              "остальное взять из уже существующего перевода в --out")
    args = parser.parse_args()

    from .log_setup import setup_logging
    log_path = setup_logging()
    log.info("=== CLI-запуск: %s ===", vars(args))
    safe_print(f"Лог: {log_path}", file=sys.stderr)

    try:
        translate_mod(args.src.resolve(), args.out.resolve(), args.source_lang, args.lang,
                       use_llm=args.llm, llm_model=args.llm_model,
                       use_argos=not args.no_argos, update=args.update)
    except ValueError as e:
        log.error("Перевод прерван: %s", e)
        raise SystemExit(str(e))
    except Exception:
        log.exception("Необработанное исключение в CLI")
        raise
    print()


if __name__ == "__main__":
    main()
