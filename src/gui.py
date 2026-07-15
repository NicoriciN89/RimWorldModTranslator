"""Простое окно для переводчика модов RimWorld: юзеру достаточно указать
папку мода (или собрать очередь из нескольких), выбрать язык и нажать
кнопку — остальное делает main.translate_mod."""
from __future__ import annotations

import logging
import queue
import threading
import traceback
from pathlib import Path
from tkinter import (
    BOTH, BooleanVar, DISABLED, END, HORIZONTAL, LEFT, Listbox, NORMAL, RIGHT, X,
    Tk, filedialog, messagebox,
)
from tkinter import ttk

from . import __version__, generator, main as main_module
from .llm_polish import DEFAULT_MODEL, list_installed_models
from .log_setup import get_logger, setup_logging
from .settings import load_settings, save_settings

log = get_logger("gui")

# Типичные пути установки RimWorld (Steam) — используются только как отправная
# точка для диалога "Обзор...", если существуют на этом ПК; если нет ни одной,
# диалог просто открывается без initialdir, как раньше.
_COMMON_RIMWORLD_DATA_DIRS = [
    r"C:\Program Files (x86)\Steam\steamapps\common\RimWorld\Data",
    r"D:\Steam\steamapps\common\RimWorld\Data",
    r"E:\games\RimWorld\Data",
    r"E:\SteamLibrary\steamapps\common\RimWorld\Data",
]


def _default_mods_dir() -> str:
    for candidate in _COMMON_RIMWORLD_DATA_DIRS:
        if Path(candidate).is_dir():
            return candidate
    return ""


ENGINE_ARGOS_ONLY = "Только Argos (быстро)"
ENGINE_LLM_ONLY = "Только LLM (медленно, качественнее)"
ENGINE_BOTH = "Argos + LLM-доработка (рекомендовано)"
ENGINE_BOTH_CHECK = "Argos + LLM-проверка ошибок (быстрее)"
ENGINES = [ENGINE_ARGOS_ONLY, ENGINE_BOTH, ENGINE_BOTH_CHECK, ENGINE_LLM_ONLY]

LANGUAGES = [
    ("Русский", "ru"),
    ("Украинский", "uk"),
    ("Немецкий", "de"),
    ("Французский", "fr"),
    ("Испанский", "es"),
    ("Итальянский", "it"),
    ("Польский", "pl"),
    ("Португальский", "pt"),
    ("Китайский (упрощ.)", "zh"),
    ("Японский", "ja"),
    ("Корейский", "ko"),
    ("Чешский", "cs"),
    ("Нидерландский", "nl"),
    ("Турецкий", "tr"),
]


class TranslatorApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(f"RimWorld Mod Translator v{__version__}")
        self.root.geometry("580x560")
        self.root.minsize(520, 480)

        self._queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None

        self._settings = load_settings()
        self.mod_path = self._settings.get("mod_path", "")
        self.out_path = self._settings.get("out_path", str(Path.cwd() / "output"))

        self._build_widgets()
        self._apply_saved_settings()
        self._update_model_row_state()
        self.root.after(100, self._poll_queue)
        self._refresh_models()

    def _apply_saved_settings(self) -> None:
        """Восстанавливает выбор пользователя с прошлого запуска (см.
        settings.py); что-то не так в сохранённых значениях — молча остаёмся
        на значениях по умолчанию."""
        if self.mod_path:
            self.mod_entry.insert(0, self.mod_path)
        lang = self._settings.get("lang")
        lang_names = [name for name, _ in LANGUAGES]
        if lang in lang_names:
            self.lang_var.current(lang_names.index(lang))
        engine = self._settings.get("engine")
        if engine in ENGINES:
            self.engine_var.current(ENGINES.index(engine))
        model = self._settings.get("model")
        if model:
            self.model_var.set(model)
        self.update_var.set(bool(self._settings.get("update", False)))
        self.original_comments_var.set(bool(self._settings.get("comments", False)))

    def _save_current_settings(self) -> None:
        save_settings({
            "mod_path": self.mod_entry.get().strip(),
            "out_path": self.out_entry.get().strip(),
            "lang": self.lang_var.get(),
            "engine": self.engine_var.get(),
            "model": self.model_var.get(),
            "update": self.update_var.get(),
            "comments": self.original_comments_var.get(),
        })

    def _build_widgets(self) -> None:
        pad = {"padx": 10, "pady": 6}

        frame = ttk.Frame(self.root)
        frame.pack(fill=BOTH, expand=True, **pad)

        # Папка мода
        mod_row = ttk.Frame(frame)
        mod_row.pack(fill=X, pady=4)
        ttk.Label(mod_row, text="Папка мода:").pack(anchor="w")
        path_row = ttk.Frame(mod_row)
        path_row.pack(fill=X, pady=2)
        self.mod_entry = ttk.Entry(path_row)
        self.mod_entry.pack(side=LEFT, fill=X, expand=True)
        ttk.Button(path_row, text="Обзор...", command=self._pick_mod_folder).pack(side=LEFT, padx=(6, 0))

        self.mod_info_label = ttk.Label(frame, text="", foreground="#666")
        self.mod_info_label.pack(fill=X, pady=(0, 6))

        # Очередь модов (пакетный режим): если в списке есть моды, кнопка
        # "Перевести" обрабатывает их по очереди с общей памятью переводов;
        # если очередь пуста — переводится мод из поля выше, как раньше.
        queue_row = ttk.Frame(frame)
        queue_row.pack(fill=X, pady=(0, 4))
        ttk.Label(queue_row, text="Очередь модов (необязательно):").pack(anchor="w")
        queue_inner = ttk.Frame(queue_row)
        queue_inner.pack(fill=X, pady=2)
        self.queue_list = Listbox(queue_inner, height=3)
        self.queue_list.pack(side=LEFT, fill=X, expand=True)
        queue_btns = ttk.Frame(queue_inner)
        queue_btns.pack(side=LEFT, padx=(6, 0))
        ttk.Button(queue_btns, text="Добавить", command=self._add_to_queue).pack(fill=X)
        ttk.Button(queue_btns, text="Убрать", command=self._remove_from_queue).pack(fill=X, pady=(4, 0))

        # Папка вывода
        out_row = ttk.Frame(frame)
        out_row.pack(fill=X, pady=4)
        ttk.Label(out_row, text="Куда сохранить перевод:").pack(anchor="w")
        out_path_row = ttk.Frame(out_row)
        out_path_row.pack(fill=X, pady=2)
        self.out_entry = ttk.Entry(out_path_row)
        self.out_entry.insert(0, self.out_path)
        self.out_entry.pack(side=LEFT, fill=X, expand=True)
        ttk.Button(out_path_row, text="Обзор...", command=self._pick_out_folder).pack(side=LEFT, padx=(6, 0))

        # Язык
        lang_row = ttk.Frame(frame)
        lang_row.pack(fill=X, pady=8)
        ttk.Label(lang_row, text="Язык перевода:").pack(side=LEFT)
        self.lang_var = ttk.Combobox(lang_row, values=[name for name, _ in LANGUAGES], state="readonly", width=25)
        self.lang_var.current(0)
        self.lang_var.pack(side=LEFT, padx=(6, 0))

        # Движок перевода
        engine_row = ttk.Frame(frame)
        engine_row.pack(fill=X, pady=(4, 2))
        ttk.Label(engine_row, text="Движок перевода:").pack(side=LEFT)
        self.engine_var = ttk.Combobox(engine_row, values=ENGINES, state="readonly", width=32)
        self.engine_var.current(0)
        self.engine_var.bind("<<ComboboxSelected>>", lambda e: self._update_model_row_state())
        self.engine_var.pack(side=LEFT, padx=(6, 0))

        # Модель LLM (активна только если движок использует LLM)
        model_row = ttk.Frame(frame)
        model_row.pack(fill=X, pady=(0, 4))
        ttk.Label(model_row, text="Модель Ollama:").pack(side=LEFT)
        self.model_var = ttk.Combobox(model_row, values=[DEFAULT_MODEL], state="disabled", width=24)
        self.model_var.current(0)
        self.model_var.pack(side=LEFT, padx=(6, 0))
        self.refresh_models_btn = ttk.Button(model_row, text="Обновить список", command=self._refresh_models)
        self.refresh_models_btn.pack(side=LEFT, padx=(6, 0))

        # Режим обновления
        self.update_var = BooleanVar(value=False)
        update_row = ttk.Frame(frame)
        update_row.pack(fill=X, pady=(0, 4))
        ttk.Checkbutton(
            update_row,
            text="Режим обновления: переводить только новые/изменённые строки "
                 "(если в папке вывода уже есть перевод)",
            variable=self.update_var,
        ).pack(side=LEFT)

        # Комментарии с оригиналом
        self.original_comments_var = BooleanVar(value=False)
        comments_row = ttk.Frame(frame)
        comments_row.pack(fill=X, pady=(0, 4))
        ttk.Checkbutton(
            comments_row,
            text="Добавлять в файлы перевода комментарий с оригинальным английским текстом (для сверки)",
            variable=self.original_comments_var,
        ).pack(side=LEFT)

        # Кнопки
        btn_row = ttk.Frame(frame)
        btn_row.pack(pady=10)
        self.translate_btn = ttk.Button(btn_row, text="Перевести", command=self._start_translation)
        self.translate_btn.pack(side=LEFT)
        self.cancel_btn = ttk.Button(btn_row, text="Отмена", command=self._cancel_translation,
                                     state=DISABLED)
        self.cancel_btn.pack(side=LEFT, padx=(8, 0))

        # Прогресс
        self.progress = ttk.Progressbar(frame, orient=HORIZONTAL, mode="determinate")
        self.progress.pack(fill=X, pady=4)

        self.status_label = ttk.Label(frame, text="Готов к работе.", wraplength=520, justify=LEFT)
        self.status_label.pack(fill=X, pady=4)

        log_path = Path(logging.getLogger("rmt").handlers[0].baseFilename) \
            if logging.getLogger("rmt").handlers else None
        log_hint = f"Подробный лог: {log_path}" if log_path else ""
        ttk.Label(frame, text=log_hint, foreground="#888", wraplength=520, justify=LEFT).pack(fill=X, pady=(0, 4))

    def _pick_mod_folder(self) -> None:
        path = filedialog.askdirectory(
            title="Выберите папку мода (там, где About/About.xml)",
            initialdir=_default_mods_dir(),
        )
        if not path:
            return
        self.mod_entry.delete(0, END)
        self.mod_entry.insert(0, path)
        self._describe_mod(Path(path))

    def _describe_mod(self, mod_path: Path) -> None:
        info = generator.read_original_about(mod_path)
        if info.name:
            self.mod_info_label.config(text=f"Обнаружен мод: {info.name}")
        else:
            self.mod_info_label.config(text="About.xml не найден — проверьте, что это папка мода RimWorld.")

    def _pick_out_folder(self) -> None:
        path = filedialog.askdirectory(title="Куда сохранить перевод")
        if not path:
            return
        self.out_entry.delete(0, END)
        self.out_entry.insert(0, path)

    def _add_to_queue(self) -> None:
        """Добавляет мод из поля "Папка мода" в очередь (или открывает диалог,
        если поле пустое)."""
        path = self.mod_entry.get().strip()
        if not path:
            path = filedialog.askdirectory(
                title="Выберите папку мода для очереди", initialdir=_default_mods_dir())
            if not path:
                return
        if path in self.queue_list.get(0, END):
            return
        if not Path(path).is_dir():
            messagebox.showwarning("Папка не найдена", f"Папка не существует:\n{path}")
            return
        self.queue_list.insert(END, path)

    def _remove_from_queue(self) -> None:
        for idx in reversed(self.queue_list.curselection()):
            self.queue_list.delete(idx)

    def _cancel_translation(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.cancel_btn.config(state=DISABLED)
            self.status_label.config(text="Останавливаю... (дожидаюсь текущей строки/пачки)")

    def _update_model_row_state(self) -> None:
        uses_llm = self.engine_var.get() != ENGINE_ARGOS_ONLY
        self.model_var.config(state="readonly" if uses_llm else "disabled")
        self.refresh_models_btn.config(state=NORMAL if uses_llm else DISABLED)

    def _refresh_models(self) -> None:
        def worker() -> None:
            models = list_installed_models()
            self._queue.put(("models", models))

        self.refresh_models_btn.config(text="Ищу модели...")
        threading.Thread(target=worker, daemon=True).start()

    def _start_translation(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return

        queued = list(self.queue_list.get(0, END))
        mod_path_str = self.mod_entry.get().strip()
        out_path_str = self.out_entry.get().strip()
        mod_paths = [Path(p) for p in queued] if queued else \
            ([Path(mod_path_str)] if mod_path_str else [])
        if not mod_paths:
            messagebox.showwarning("Не выбрана папка",
                                   "Укажите папку мода или добавьте моды в очередь.")
            return
        if not out_path_str:
            messagebox.showwarning("Не выбрана папка", "Укажите папку для сохранения результата.")
            return

        out_path = Path(out_path_str)
        lang_name = self.lang_var.get()
        lang_code = next(code for name, code in LANGUAGES if name == lang_name)

        engine = self.engine_var.get()
        use_argos = engine != ENGINE_LLM_ONLY
        use_llm = engine != ENGINE_ARGOS_ONLY
        llm_mode = main_module.LLM_MODE_CHECK if engine == ENGINE_BOTH_CHECK else main_module.LLM_MODE_REWRITE
        llm_model = self.model_var.get() if use_llm else DEFAULT_MODEL
        update = self.update_var.get()
        with_original_comments = self.original_comments_var.get()

        self._save_current_settings()
        self._cancel_event = threading.Event()
        self.translate_btn.config(state=DISABLED)
        self.cancel_btn.config(state=NORMAL)
        self.progress.config(value=0, maximum=100)
        self.status_label.config(text="Запускаю перевод...")

        self._worker = threading.Thread(
            target=self._run_translation,
            args=(mod_paths, out_path, lang_code, use_argos, use_llm, llm_model, update,
                  with_original_comments, llm_mode, self._cancel_event),
            daemon=True,
        )
        self._worker.start()

    def _run_translation(self, mod_paths: list[Path], out_path: Path, lang_code: str,
                          use_argos: bool, use_llm: bool, llm_model: str, update: bool,
                          with_original_comments: bool, llm_mode: str,
                          cancel_event: threading.Event) -> None:
        total_mods = len(mod_paths)
        memory: dict[str, str] = {}

        log.info("=== Запуск перевода: mods=%s out=%s lang=%s argos=%s llm=%s(%s, mode=%s) update=%s comments=%s ===",
                  [str(p) for p in mod_paths], out_path, lang_code, use_argos, use_llm,
                  llm_model, llm_mode, update, with_original_comments)

        results: list[str] = []
        errors: list[str] = []
        for i, mod_path in enumerate(mod_paths, 1):
            prefix = f"[мод {i}/{total_mods}] " if total_mods > 1 else ""

            def on_progress(done: int, total: int, message: str, _prefix: str = prefix) -> None:
                if message:
                    log.info("%s%s", _prefix, message)
                else:
                    log.debug("progress %d/%d", done, total)
                self._queue.put(("progress", done, total, _prefix + message if message else ""))

            try:
                result = main_module.translate_mod(
                    mod_path, out_path, "en", lang_code, on_progress=on_progress,
                    use_llm=use_llm, llm_model=llm_model, use_argos=use_argos, update=update,
                    llm_parallel_requests=main_module.DEFAULT_PARALLEL_REQUESTS,
                    with_original_comments=with_original_comments, llm_mode=llm_mode,
                    memory=memory, cancel_event=cancel_event,
                )
                log.info("Готово: %s", result)
                results.append(str(result))
            except main_module.TranslationCancelled as e:
                log.info("Отменено пользователем: %s", e)
                self._queue.put(("cancelled", str(e)))
                return
            except Exception as e:
                log.error("Перевод %s упал с ошибкой: %s\n%s", mod_path, e, traceback.format_exc())
                errors.append(f"{mod_path.name}: {e}")
                # Пакетный режим: ошибка одного мода не роняет всю очередь.
                continue

        if errors and results:
            self._queue.put(("done", "Готово: " + "\n".join(results) +
                              "\n\nС ошибками:\n" + "\n".join(errors)))
        elif errors:
            self._queue.put(("error", "\n".join(errors)))
        else:
            self._queue.put(("done", "\n".join(results)))

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, done, total, message = item
                    if total > 0:
                        self.progress.config(maximum=total, value=done)
                    if message:
                        self.status_label.config(text=message)
                elif kind == "done":
                    out_dir = item[1]
                    self.status_label.config(text=f"Готово! Перевод сохранён в:\n{out_dir}")
                    self.translate_btn.config(state=NORMAL)
                    self.cancel_btn.config(state=DISABLED)
                    messagebox.showinfo("Готово", f"Перевод завершён:\n{out_dir}")
                elif kind == "cancelled":
                    self.status_label.config(text=f"Отменено. {item[1]}")
                    self.translate_btn.config(state=NORMAL)
                    self.cancel_btn.config(state=DISABLED)
                elif kind == "error":
                    self.status_label.config(text="Произошла ошибка — см. окно сообщения.")
                    self.translate_btn.config(state=NORMAL)
                    self.cancel_btn.config(state=DISABLED)
                    messagebox.showerror("Ошибка перевода", item[1])
                elif kind == "models":
                    models = item[1]
                    self.refresh_models_btn.config(text="Обновить список")
                    if models:
                        current = self.model_var.get()
                        self.model_var.config(values=models)
                        self.model_var.set(current if current in models else models[0])
                    else:
                        self.model_var.config(values=[DEFAULT_MODEL])
                        self.model_var.set(DEFAULT_MODEL)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)


def main() -> None:
    log_path = setup_logging()
    log.info("=== RimWorld Mod Translator v%s запущен, лог: %s ===", __version__, log_path)
    root = Tk()
    TranslatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
