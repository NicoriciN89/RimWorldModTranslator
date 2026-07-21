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
from .diagnostics import log_environment_snapshot
from .i18n import SUPPORTED_UI_LANGUAGES, Translator, detect_system_ui_language
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


# Стабильные внутренние идентификаторы движка перевода — НЕ показываются
# пользователю напрямую (для этого есть i18n.t(ENGINE_I18N_KEYS[x])); хранятся
# в settings.json, поэтому должны переживать смену языка интерфейса и не
# зависеть от того, на каком языке был текст на момент сохранения.
ENGINE_ARGOS_ONLY = "argos_only"
ENGINE_LLM_ONLY = "llm_only"
ENGINE_BOTH = "both"
ENGINE_BOTH_CHECK = "both_check"
ENGINES = [ENGINE_ARGOS_ONLY, ENGINE_BOTH, ENGINE_BOTH_CHECK, ENGINE_LLM_ONLY]
ENGINE_I18N_KEYS = {
    ENGINE_ARGOS_ONLY: "engine_argos_only",
    ENGINE_LLM_ONLY: "engine_llm_only",
    ENGINE_BOTH: "engine_both",
    ENGINE_BOTH_CHECK: "engine_both_check",
}

# Языки ПЕРЕВОДА МОДА (не интерфейса программы — см. i18n.py для того) — код
# ISO 639-1 хранится в settings.json, а отображаемое название всегда
# смотрится через i18n.t("lang_" + code) на текущем языке интерфейса.
TRANSLATION_LANGUAGE_CODES = [
    "ru", "uk", "de", "fr", "es", "it", "pl", "pt", "zh", "ja", "ko", "cs", "nl", "tr",
]


class TranslatorApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.geometry("580x600")
        self.root.minsize(520, 520)

        self._queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None

        self._settings = load_settings()
        self.mod_path = self._settings.get("mod_path", "")
        self.out_path = self._settings.get("out_path", str(Path.cwd() / "output"))

        saved_ui_lang = self._settings.get("ui_language")
        ui_lang = saved_ui_lang if saved_ui_lang else detect_system_ui_language()
        self._t = Translator(ui_lang)

        self._build_widgets()
        self._apply_saved_settings()
        self._update_model_row_state()
        self._retranslate_ui()
        self.root.after(100, self._poll_queue)
        self._refresh_models()

    def _apply_saved_settings(self) -> None:
        """Восстанавливает выбор пользователя с прошлого запуска (см.
        settings.py); что-то не так в сохранённых значениях — молча остаёмся
        на значениях по умолчанию."""
        if self.mod_path:
            self.mod_entry.insert(0, self.mod_path)
        lang_code = self._settings.get("lang_code")
        if lang_code in TRANSLATION_LANGUAGE_CODES:
            self._lang_code = lang_code
        else:
            self._lang_code = TRANSLATION_LANGUAGE_CODES[0]
        engine = self._settings.get("engine")
        self._engine_code = engine if engine in ENGINES else ENGINE_ARGOS_ONLY
        model = self._settings.get("model")
        if model:
            self.model_var.set(model)
        self.update_var.set(bool(self._settings.get("update", False)))
        self.original_comments_var.set(bool(self._settings.get("comments", False)))

    def _save_current_settings(self) -> None:
        save_settings({
            "mod_path": self.mod_entry.get().strip(),
            "out_path": self.out_entry.get().strip(),
            "lang_code": self._lang_code,
            "engine": self._engine_code,
            "model": self.model_var.get(),
            "update": self.update_var.get(),
            "comments": self.original_comments_var.get(),
            "ui_language": self._t.language,
        })

    def _build_widgets(self) -> None:
        pad = {"padx": 10, "pady": 6}

        frame = ttk.Frame(self.root)
        frame.pack(fill=BOTH, expand=True, **pad)

        # Язык интерфейса — отдельно сверху, чтобы сразу бросался в глаза.
        ui_lang_row = ttk.Frame(frame)
        ui_lang_row.pack(fill=X, pady=(0, 8))
        self.ui_lang_label = ttk.Label(ui_lang_row)
        self.ui_lang_label.pack(side=LEFT)
        self._ui_lang_names = [name for name, _ in SUPPORTED_UI_LANGUAGES]
        self._ui_lang_codes = [code for _, code in SUPPORTED_UI_LANGUAGES]
        self.ui_lang_var = ttk.Combobox(ui_lang_row, values=self._ui_lang_names,
                                        state="readonly", width=16)
        current_ui_idx = self._ui_lang_codes.index(self._t.language) \
            if self._t.language in self._ui_lang_codes else 0
        self.ui_lang_var.current(current_ui_idx)
        self.ui_lang_var.bind("<<ComboboxSelected>>", self._on_ui_language_changed)
        self.ui_lang_var.pack(side=LEFT, padx=(6, 0))

        # Папка мода
        mod_row = ttk.Frame(frame)
        mod_row.pack(fill=X, pady=4)
        self.mod_folder_label = ttk.Label(mod_row)
        self.mod_folder_label.pack(anchor="w")
        path_row = ttk.Frame(mod_row)
        path_row.pack(fill=X, pady=2)
        self.mod_entry = ttk.Entry(path_row)
        self.mod_entry.pack(side=LEFT, fill=X, expand=True)
        self.mod_browse_btn = ttk.Button(path_row, command=self._pick_mod_folder)
        self.mod_browse_btn.pack(side=LEFT, padx=(6, 0))

        self.mod_info_label = ttk.Label(frame, text="", foreground="#666")
        self.mod_info_label.pack(fill=X, pady=(0, 6))

        # Очередь модов (пакетный режим): если в списке есть моды, кнопка
        # "Перевести" обрабатывает их по очереди с общей памятью переводов;
        # если очередь пуста — переводится мод из поля выше, как раньше.
        queue_row = ttk.Frame(frame)
        queue_row.pack(fill=X, pady=(0, 4))
        self.mod_queue_label = ttk.Label(queue_row)
        self.mod_queue_label.pack(anchor="w")
        queue_inner = ttk.Frame(queue_row)
        queue_inner.pack(fill=X, pady=2)
        self.queue_list = Listbox(queue_inner, height=3)
        self.queue_list.pack(side=LEFT, fill=X, expand=True)
        queue_btns = ttk.Frame(queue_inner)
        queue_btns.pack(side=LEFT, padx=(6, 0))
        self.queue_add_btn = ttk.Button(queue_btns, command=self._add_to_queue)
        self.queue_add_btn.pack(fill=X)
        self.queue_remove_btn = ttk.Button(queue_btns, command=self._remove_from_queue)
        self.queue_remove_btn.pack(fill=X, pady=(4, 0))

        # Папка вывода
        out_row = ttk.Frame(frame)
        out_row.pack(fill=X, pady=4)
        self.output_folder_label = ttk.Label(out_row)
        self.output_folder_label.pack(anchor="w")
        out_path_row = ttk.Frame(out_row)
        out_path_row.pack(fill=X, pady=2)
        self.out_entry = ttk.Entry(out_path_row)
        self.out_entry.insert(0, self.out_path)
        self.out_entry.pack(side=LEFT, fill=X, expand=True)
        self.out_browse_btn = ttk.Button(out_path_row, command=self._pick_out_folder)
        self.out_browse_btn.pack(side=LEFT, padx=(6, 0))

        # Язык перевода мода
        lang_row = ttk.Frame(frame)
        lang_row.pack(fill=X, pady=8)
        self.translation_language_label = ttk.Label(lang_row)
        self.translation_language_label.pack(side=LEFT)
        self.lang_var = ttk.Combobox(lang_row, state="readonly", width=25)
        self.lang_var.bind("<<ComboboxSelected>>", self._on_translation_language_changed)
        self.lang_var.pack(side=LEFT, padx=(6, 0))

        # Движок перевода
        engine_row = ttk.Frame(frame)
        engine_row.pack(fill=X, pady=(4, 2))
        self.translation_engine_label = ttk.Label(engine_row)
        self.translation_engine_label.pack(side=LEFT)
        self.engine_var = ttk.Combobox(engine_row, state="readonly", width=32)
        self.engine_var.bind("<<ComboboxSelected>>", self._on_engine_changed)
        self.engine_var.pack(side=LEFT, padx=(6, 0))

        # Модель LLM (активна только если движок использует LLM)
        model_row = ttk.Frame(frame)
        model_row.pack(fill=X, pady=(0, 4))
        self.ollama_model_label = ttk.Label(model_row)
        self.ollama_model_label.pack(side=LEFT)
        self.model_var = ttk.Combobox(model_row, values=[DEFAULT_MODEL], state="disabled", width=24)
        self.model_var.current(0)
        self.model_var.pack(side=LEFT, padx=(6, 0))
        self.refresh_models_btn = ttk.Button(model_row, command=self._refresh_models)
        self.refresh_models_btn.pack(side=LEFT, padx=(6, 0))

        # Режим обновления
        self.update_var = BooleanVar(value=False)
        update_row = ttk.Frame(frame)
        update_row.pack(fill=X, pady=(0, 4))
        self.update_mode_check = ttk.Checkbutton(update_row, variable=self.update_var)
        self.update_mode_check.pack(side=LEFT)

        # Комментарии с оригиналом
        self.original_comments_var = BooleanVar(value=False)
        comments_row = ttk.Frame(frame)
        comments_row.pack(fill=X, pady=(0, 4))
        self.original_comments_check = ttk.Checkbutton(
            comments_row, variable=self.original_comments_var)
        self.original_comments_check.pack(side=LEFT)

        # Кнопки
        btn_row = ttk.Frame(frame)
        btn_row.pack(pady=10)
        self.translate_btn = ttk.Button(btn_row, command=self._start_translation)
        self.translate_btn.pack(side=LEFT)
        self.cancel_btn = ttk.Button(btn_row, command=self._cancel_translation, state=DISABLED)
        self.cancel_btn.pack(side=LEFT, padx=(8, 0))

        # Прогресс
        self.progress = ttk.Progressbar(frame, orient=HORIZONTAL, mode="determinate")
        self.progress.pack(fill=X, pady=4)

        self.status_label = ttk.Label(frame, wraplength=520, justify=LEFT)
        self.status_label.pack(fill=X, pady=4)

        self.log_hint_label = ttk.Label(frame, foreground="#888", wraplength=520, justify=LEFT)
        self.log_hint_label.pack(fill=X, pady=(0, 4))

    def _on_ui_language_changed(self, _event=None) -> None:
        idx = self.ui_lang_var.current()
        self._t.set_language(self._ui_lang_codes[idx])
        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        """Переприменяет текст всех виджетов на текущем языке интерфейса —
        вызывается при старте и при каждой смене языка в комбобоксе, без
        необходимости перезапускать программу."""
        t = self._t.t
        self.root.title(t("window_title", version=__version__))
        self.ui_lang_label.config(text=t("ui_language"))
        self.mod_folder_label.config(text=t("mod_folder"))
        self.mod_browse_btn.config(text=t("browse"))
        self.mod_queue_label.config(text=t("mod_queue"))
        self.queue_add_btn.config(text=t("add"))
        self.queue_remove_btn.config(text=t("remove"))
        self.output_folder_label.config(text=t("output_folder"))
        self.out_browse_btn.config(text=t("browse"))
        self.translation_language_label.config(text=t("translation_language"))
        self.translation_engine_label.config(text=t("translation_engine"))
        self.ollama_model_label.config(text=t("ollama_model"))
        self.update_mode_check.config(text=t("update_mode"))
        self.original_comments_check.config(text=t("original_comments"))
        self.translate_btn.config(text=t("translate"))
        self.cancel_btn.config(text=t("cancel"))
        self.status_label.config(text=t("ready"))

        # Комбобоксы с переводимыми названиями — переприменяем список
        # значений на новом языке, сохраняя текущий выбор по стабильному коду.
        lang_names = [t(f"lang_{code}") for code in TRANSLATION_LANGUAGE_CODES]
        self.lang_var.config(values=lang_names)
        self.lang_var.current(TRANSLATION_LANGUAGE_CODES.index(self._lang_code))

        engine_names = [t(ENGINE_I18N_KEYS[code]) for code in ENGINES]
        self.engine_var.config(values=engine_names)
        self.engine_var.current(ENGINES.index(self._engine_code))

        self.refresh_models_btn.config(text=t("refresh_list"))

        log_path = Path(logging.getLogger("rmt").handlers[0].baseFilename) \
            if logging.getLogger("rmt").handlers else None
        self.log_hint_label.config(text=t("detailed_log", path=log_path) if log_path else "")

    def _pick_mod_folder(self) -> None:
        path = filedialog.askdirectory(
            title=self._t.t("pick_mod_folder_title"),
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
            self.mod_info_label.config(text=self._t.t("mod_detected", name=info.name))
        else:
            self.mod_info_label.config(text=self._t.t("about_not_found"))

    def _pick_out_folder(self) -> None:
        path = filedialog.askdirectory(title=self._t.t("pick_output_title"))
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
                title=self._t.t("pick_mod_for_queue_title"), initialdir=_default_mods_dir())
            if not path:
                return
        if path in self.queue_list.get(0, END):
            return
        if not Path(path).is_dir():
            messagebox.showwarning(self._t.t("folder_not_found_title"),
                                   self._t.t("folder_not_found_body", path=path))
            return
        self.queue_list.insert(END, path)

    def _remove_from_queue(self) -> None:
        for idx in reversed(self.queue_list.curselection()):
            self.queue_list.delete(idx)

    def _cancel_translation(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.cancel_btn.config(state=DISABLED)
            self.status_label.config(text=self._t.t("cancelling"))

    def _on_translation_language_changed(self, _event=None) -> None:
        self._lang_code = TRANSLATION_LANGUAGE_CODES[self.lang_var.current()]

    def _on_engine_changed(self, _event=None) -> None:
        self._engine_code = ENGINES[self.engine_var.current()]
        self._update_model_row_state()

    def _update_model_row_state(self) -> None:
        uses_llm = self._engine_code != ENGINE_ARGOS_ONLY
        self.model_var.config(state="readonly" if uses_llm else "disabled")
        self.refresh_models_btn.config(state=NORMAL if uses_llm else DISABLED)

    def _refresh_models(self) -> None:
        def worker() -> None:
            models = list_installed_models()
            self._queue.put(("models", models))

        self.refresh_models_btn.config(text=self._t.t("searching_models"))
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
            messagebox.showwarning(self._t.t("no_folder_selected_title"),
                                   self._t.t("no_mod_selected_body"))
            return
        if not out_path_str:
            messagebox.showwarning(self._t.t("no_folder_selected_title"),
                                   self._t.t("no_output_selected_body"))
            return

        out_path = Path(out_path_str)
        lang_code = self._lang_code

        engine = self._engine_code
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
        self.status_label.config(text=self._t.t("starting_translation"))

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
            prefix = f"[{i}/{total_mods}] " if total_mods > 1 else ""

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
            self._queue.put(("done_with_errors", results, errors))
        elif errors:
            self._queue.put(("error", "\n".join(errors)))
        else:
            self._queue.put(("done", "\n".join(results)))

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                t = self._t.t
                if kind == "progress":
                    _, done, total, message = item
                    if total > 0:
                        self.progress.config(maximum=total, value=done)
                    if message:
                        self.status_label.config(text=message)
                elif kind == "done":
                    out_dir = item[1]
                    self.status_label.config(text=t("done_saved_to", path=out_dir))
                    self.translate_btn.config(state=NORMAL)
                    self.cancel_btn.config(state=DISABLED)
                    messagebox.showinfo(t("done_title"), t("done_saved_to", path=out_dir))
                elif kind == "done_with_errors":
                    results, errors = item[1], item[2]
                    body = t("done_saved_to", path="\n".join(results)) + "\n\n" + "\n".join(errors)
                    self.status_label.config(text=body)
                    self.translate_btn.config(state=NORMAL)
                    self.cancel_btn.config(state=DISABLED)
                    messagebox.showinfo(t("done_title"), body)
                elif kind == "cancelled":
                    self.status_label.config(text=t("cancelled", reason=item[1]))
                    self.translate_btn.config(state=NORMAL)
                    self.cancel_btn.config(state=DISABLED)
                elif kind == "error":
                    self.status_label.config(text=t("error_occurred"))
                    self.translate_btn.config(state=NORMAL)
                    self.cancel_btn.config(state=DISABLED)
                    messagebox.showerror(t("translation_error_title"), item[1])
                elif kind == "models":
                    models = item[1]
                    self.refresh_models_btn.config(text=t("refresh_list"))
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
    # В фоновом потоке: опрос WMI/PowerShell (антивирус, диск) занимает
    # секунды из-за холодного старта powershell.exe — блокировать этим
    # появление окна не стоит, а к моменту, когда лог понадобится для
    # разбора проблемы, снимок уже успеет дописаться.
    threading.Thread(target=log_environment_snapshot, args=(log_path.parent,), daemon=True).start()
    root = Tk()
    TranslatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
