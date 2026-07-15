"""CLI: локальный офлайн-переводчик модов RimWorld.

Пример:
    python -m src.main --src "../3761869362_psycasts" --lang ru --out ./output
"""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path
from typing import Callable

from . import generator, incremental, overrides, scanner
from .generator import rimworld_lang_dir_name
from .llm_polish import (
    CHECK_BATCH_SIZE, DEFAULT_PARALLEL_REQUESTS, LANG_HUMAN_NAMES, LlmContext, LlmPolisher,
)
from .log_setup import get_logger
from .safe_print import safe_print
from .translator import ArgosPackageSetupError, get_engine

log = get_logger("main")


class TranslationCancelled(RuntimeError):
    """Пользователь остановил перевод (кнопка «Отмена» в GUI / Ctrl+C).
    Частичный результат уже сброшен на диск, но кэш/снимок не сохраняются —
    иначе режим обновления посчитал бы недопереведённые строки готовыми."""

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


LLM_BATCH_SIZE = 12

# Режимы LLM-доработки:
# "rewrite" — модель переписывает КАЖДУЮ строку пачки (polish_many), выше
#             качество согласования в среднем, но тратит время даже на уже
#             верные строки и есть небольшой риск "исправить" то, что и так
#             было хорошо.
# "check"   — модель сначала переводит ВЕСЬ мод через Argos на 100%, потом
#             только ИЩЕТ ошибки в черновике большими пачками (check_and_fix_many)
#             и правит лишь то, что реально сочла ошибкой — остальное остаётся
#             черновиком Argos без изменений. Быстрее на модах, где Argos и
#             так справляется с большинством строк.
LLM_MODE_REWRITE = "rewrite"
LLM_MODE_CHECK = "check"


def translate_mod(src: Path, out_dir: Path, source_lang: str, target_lang: str,
                   on_progress: ProgressCallback = _default_progress,
                   use_llm: bool = False, llm_model: str = "qwen2.5:7b",
                   use_argos: bool = True, update: bool = False,
                   llm_batch_size: int | None = None,
                   llm_parallel_requests: int = DEFAULT_PARALLEL_REQUESTS,
                   with_original_comments: bool = False,
                   llm_mode: str = LLM_MODE_REWRITE,
                   memory: dict[str, str] | None = None,
                   cancel_event: threading.Event | None = None) -> Path:
    """memory — общая память переводов пакетного режима: {английский текст:
    готовый перевод}. Заполняется по завершении каждого мода и позволяет
    следующим модам очереди переиспользовать уже переведённые строки.
    cancel_event — кооперативная отмена: при установке события перевод
    останавливается с TranslationCancelled, частичный результат на диске."""
    if not src.is_dir():
        raise ValueError(f"Папка мода не найдена: {src}")
    if not use_argos and not use_llm:
        raise ValueError("Нужен хотя бы один движок перевода: Argos или LLM.")
    if llm_mode == LLM_MODE_CHECK and not use_argos:
        raise ValueError('Режим LLM "check" (проверка ошибок Argos) требует включённый Argos.')
    if llm_batch_size is None:
        llm_batch_size = CHECK_BATCH_SIZE if llm_mode == LLM_MODE_CHECK else LLM_BATCH_SIZE

    on_progress(0, 0, f"[1/4] Сканирую мод: {src}")
    scan = scanner.scan_mod(src)
    strings_note = f", Strings: {len(scan.strings)} файлов" if scan.strings else ""
    if scan.source_lang_dir:
        on_progress(0, 0, f"      Найден Languages/English — Keyed: {len(scan.keyed)} файлов, "
                           f"DefInjected: {len(scan.def_injected)} файлов{strings_note}")
    else:
        on_progress(0, 0, f"      Languages/English отсутствует — извлекаю строки из Defs напрямую. "
                           f"Сгенерировано DefInjected-файлов: {len(scan.def_injected)}")

    all_tasks = list(scan.keyed) + list(scan.def_injected) + list(scan.strings)
    total_strings = sum(len(t.data.keyed_items()) for t in all_tasks)
    if total_strings == 0:
        raise ValueError("Переводимых строк не найдено — проверьте, что это папка мода RimWorld.")

    mod_name = src.name
    out_root = out_dir / f"{mod_name}_{target_lang.upper()}"
    lang_dir_name = rimworld_lang_dir_name(target_lang)

    all_entries = [
        entry
        for task in all_tasks
        for entry in task.data.keyed_items()
    ]
    english_by_key = {entry.key: entry.text for entry in all_entries}
    if with_original_comments:
        for entry in all_entries:
            entry.original_text = entry.text

    # Ручные правки пользователя в файлах ПРОШЛОЙ генерации собираются до
    # того, как мы что-либо перезапишем, и применяются после incremental —
    # правка финальна и побеждает и машинный перевод, и переиспользованный.
    overrides_map = overrides.harvest_manual_edits(out_root, lang_dir_name)

    reused_keys: set[str] = set()
    if update:
        reused_keys = incremental.apply_incremental(scan, out_root, lang_dir_name)

    override_keys = overrides.apply_overrides(scan, overrides_map)

    memory_keys: set[str] = set()
    if memory:
        for entry in all_entries:
            if entry.key in reused_keys or entry.key in override_keys:
                continue
            cached = memory.get(english_by_key[entry.key])
            if cached is not None:
                entry.text = cached
                memory_keys.add(entry.key)

    skipped_keys = reused_keys | override_keys | memory_keys
    to_translate = total_strings - len(skipped_keys)
    skip_notes = []
    if reused_keys:
        skip_notes.append(f"{len(reused_keys)} без изменений")
    if override_keys:
        skip_notes.append(f"{len(override_keys)} ручных правок (см. {overrides.OVERRIDES_FILENAME})")
    if memory_keys:
        skip_notes.append(f"{len(memory_keys)} из памяти переводов этой очереди")
    if skip_notes:
        on_progress(0, total_strings, f"[2/4] Пропущено: {', '.join(skip_notes)}; "
                                       f"к переводу: {to_translate}.")
    else:
        on_progress(0, total_strings, f"[2/4] Всего строк к переводу: {total_strings}")

    if use_argos and use_llm and llm_mode == LLM_MODE_CHECK:
        engine_label = "Argos на 100%, затем LLM ищет и правит только ошибки"
    else:
        engine_label = {
            (True, True): "Argos + LLM, двумя проходами",
            (True, False): "только Argos",
            (False, True): "только LLM",
        }[(use_argos, use_llm)]
    on_progress(0, total_strings, f"[3/4] Перевожу {source_lang} -> {target_lang} ({engine_label})...")

    engine = get_engine(source_lang, target_lang) if use_argos else None
    if engine is not None and not engine.is_ready():
        on_progress(0, total_strings,
                    f"      Готовлю движок Argos для пары {source_lang}->{target_lang}: "
                    f"если языковая модель ещё не скачана, программа сейчас скачает "
                    f"её из интернета (один раз, ~50-300 МБ, может занять до нескольких минут)...")
        try:
            engine.ensure_ready()
        except ArgosPackageSetupError as e:
            raise ValueError(
                f"{e} Проверьте подключение к интернету и попробуйте ещё раз. Если используете "
                f"VPN — попробуйте временно его отключить (некоторые VPN-клиенты в режиме "
                f"полного перехвата трафика мешают загрузке пакетов)."
            ) from e
        on_progress(0, total_strings, "      Движок Argos готов.")
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
        for task in all_tasks
        for entry in task.data.keyed_items()
        if entry.key not in skipped_keys
    ]

    original = generator.read_original_about(src)
    generator.write_about_xml(out_root, original, target_lang)

    flush_lock = threading.Lock()

    def flush_to_disk() -> None:
        with flush_lock:
            generator.write_translated_mod(out_root, scan, target_lang, with_original_comments)

    def check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            flush_to_disk()
            raise TranslationCancelled(
                f"Перевод отменён. Частичный результат сохранён в {out_root}")

    done = len(skipped_keys)
    on_progress(done, total_strings, "")

    if use_argos:
        pass_label = "[3a/4] Argos" if use_llm else "[3/4] Argos"
        on_progress(done, total_strings, f"{pass_label}: перевожу черновик для {len(entries_to_translate)} строк...")
        for entry in entries_to_translate:
            check_cancel()
            log.debug("[Argos %d/%d] перевожу %s", done + 1, total_strings, entry.key)
            entry.text = engine.translate(entry.text)
            done += 1
            on_progress(done, total_strings, "")
        flush_to_disk()

    if use_llm:
        check_cancel()
        done = len(skipped_keys)
        is_check_mode = llm_mode == LLM_MODE_CHECK
        pass_label = "[3b/4] LLM" if use_argos else "[3/4] LLM"
        if is_check_mode:
            on_progress(done, total_strings,
                        f"{pass_label}: ищу и исправляю ошибки Argos через {llm_model} "
                        f"(пачками по {llm_batch_size}, до {llm_parallel_requests} запросов параллельно)...")
        else:
            on_progress(done, total_strings,
                        f"{pass_label}: дорабатываю {len(entries_to_translate)} строк через {llm_model} "
                        f"(пачками по {llm_batch_size}, до {llm_parallel_requests} запросов параллельно)...")

        progress_lock = threading.Lock()
        done_box = [done]

        def on_batch_done(batch_start: int, batch_results: list[str]) -> None:
            for entry, new_text in zip(entries_to_translate[batch_start:], batch_results):
                entry.text = new_text
            with progress_lock:
                done_box[0] += len(batch_results)
                on_progress(done_box[0], total_strings, "")
            flush_to_disk()

        items = [
            (english_by_key[entry.key], entry.text, LlmContext(mod_name, entry.key))
            for entry in entries_to_translate
        ]
        if is_check_mode:
            polisher.check_and_fix_many(
                items, batch_size=llm_batch_size, parallel_requests=llm_parallel_requests,
                on_batch_done=on_batch_done, cancel_event=cancel_event,
            )
        else:
            polisher.polish_many(
                items, batch_size=llm_batch_size, parallel_requests=llm_parallel_requests,
                on_batch_done=on_batch_done, cancel_event=cancel_event,
            )
        flush_to_disk()
        check_cancel()
        # Прогресс LLM-прохода считался в done_box (обновляется из рабочих
        # потоков) — без синхронизации сюда финальные сообщения ниже
        # показывали бы счётчик, застывший на значении после Argos-прохода
        # (а в режиме "только LLM" — вообще на числе переиспользованных строк).
        done = done_box[0]

    on_progress(done, total_strings, f"[4/4] Дописываю мод-русификатор: {out_root}")

    flush_to_disk()
    incremental.save_cache(out_root, english_by_key)
    # Снимок «что записала программа» — база для обнаружения ручных правок
    # пользователя при следующей генерации (см. overrides.py). Сохраняется
    # только при успешном завершении, как и кэш выше.
    overrides.save_snapshot(out_root, {e.key: e.text for e in all_entries})
    if memory is not None:
        memory.update({english_by_key[e.key]: e.text for e in all_entries})

    on_progress(done, total_strings, f"Готово: {out_root}")
    return out_root


def _progress(done: int, total: int) -> None:
    width = 30
    filled = int(width * done / total)
    bar = "#" * filled + "-" * (width - filled)
    safe_print(f"\r      [{bar}] {done}/{total}", end="", file=sys.stderr, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Локальный офлайн-переводчик модов RimWorld")
    parser.add_argument("--src", required=True, type=Path, action="append",
                         help="Путь к папке мода; можно указать несколько раз — моды "
                              "переводятся по очереди с общей памятью переводов")
    parser.add_argument("--out", required=True, type=Path, help="Папка, куда собрать перевод")
    parser.add_argument("--source-lang", default="en", help="Код исходного языка (по умолчанию en)")
    parser.add_argument("--lang", required=True, help="Код целевого языка (ru, de, fr, ...)")
    parser.add_argument("--llm", action="store_true",
                         help="Дорабатывать черновик Argos локальной LLM через Ollama (если она запущена)")
    parser.add_argument("--llm-model", default="qwen2.5:7b", help="Модель Ollama для доработки перевода")
    parser.add_argument("--llm-mode", choices=[LLM_MODE_REWRITE, LLM_MODE_CHECK], default=LLM_MODE_REWRITE,
                         help=f'"{LLM_MODE_REWRITE}" — LLM переписывает каждую строку (по умолчанию); '
                              f'"{LLM_MODE_CHECK}" — Argos переводит всё на 100%%, затем LLM только ищет '
                              f"и правит ошибки в черновике, не трогая уже верные строки (быстрее, "
                              f"требует включённый Argos)")
    parser.add_argument("--llm-batch-size", type=int, default=None,
                         help=f"Сколько строк отправлять LLM за один запрос (по умолчанию {LLM_BATCH_SIZE} "
                              f"для rewrite, {CHECK_BATCH_SIZE} для check)")
    parser.add_argument("--llm-parallel", type=int, default=DEFAULT_PARALLEL_REQUESTS,
                         help=f"Сколько запросов к Ollama слать одновременно (по умолчанию {DEFAULT_PARALLEL_REQUESTS})")
    parser.add_argument("--no-argos", action="store_true",
                         help="Не использовать Argos Translate — переводить только через LLM (--llm обязателен)")
    parser.add_argument("--update", action="store_true",
                         help="Доперевод: переводить только новые/изменившиеся строки, "
                              "остальное взять из уже существующего перевода в --out")
    parser.add_argument("--with-original-comments", action="store_true",
                         help="Добавлять в выходной XML комментарий <!--EN: ...--> с оригинальным "
                              "английским текстом перед каждой переведённой строкой (для сверки)")
    args = parser.parse_args()

    from .log_setup import setup_logging
    log_path = setup_logging()
    log.info("=== CLI-запуск: %s ===", vars(args))
    safe_print(f"Лог: {log_path}", file=sys.stderr)

    memory: dict[str, str] = {}
    try:
        for i, src in enumerate(args.src, 1):
            if len(args.src) > 1:
                safe_print(f"=== Мод {i}/{len(args.src)}: {src.name} ===", file=sys.stderr)
            translate_mod(src.resolve(), args.out.resolve(), args.source_lang, args.lang,
                           use_llm=args.llm, llm_model=args.llm_model,
                           use_argos=not args.no_argos, update=args.update,
                           llm_batch_size=args.llm_batch_size, llm_parallel_requests=args.llm_parallel,
                           with_original_comments=args.with_original_comments, llm_mode=args.llm_mode,
                           memory=memory)
    except (ValueError, TranslationCancelled) as e:
        log.error("Перевод прерван: %s", e)
        raise SystemExit(str(e))
    except Exception:
        log.exception("Необработанное исключение в CLI")
        raise
    safe_print()


if __name__ == "__main__":
    main()
