"""Локализация интерфейса программы (не путать с языком ПЕРЕВОДА мода —
см. gui.TRANSLATION_LANGUAGE_CODES). Два уровня выбора, как обсуждалось
с пользователем:
1. Автоопределение по системному языку Windows при первом запуске.
2. Явный выбор в самой программе — сохраняется в settings.json и имеет
   приоритет над автоопределением при последующих запусках."""
from __future__ import annotations

import ctypes
import locale

_STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "window_title": "RimWorld Mod Translator v{version}",
        "ui_language": "Язык интерфейса:",
        "mod_folder": "Папка мода:",
        "browse": "Обзор...",
        "mod_queue": "Очередь модов (необязательно):",
        "add": "Добавить",
        "remove": "Убрать",
        "output_folder": "Куда сохранить перевод:",
        "translation_language": "Язык перевода:",
        "translation_engine": "Движок перевода:",
        "ollama_model": "Модель Ollama:",
        "refresh_list": "Обновить список",
        "searching_models": "Ищу модели...",
        "update_mode": "Режим обновления: переводить только новые/изменённые строки "
                       "(если в папке вывода уже есть перевод)",
        "original_comments": "Добавлять в файлы перевода комментарий с оригинальным "
                              "английским текстом (для сверки)",
        "translate": "Перевести",
        "cancel": "Отмена",
        "ready": "Готов к работе.",
        "detailed_log": "Подробный лог: {path}",
        "pick_mod_folder_title": "Выберите папку мода (там, где About/About.xml)",
        "mod_detected": "Обнаружен мод: {name}",
        "about_not_found": "About.xml не найден — проверьте, что это папка мода RimWorld.",
        "pick_output_title": "Куда сохранить перевод",
        "pick_mod_for_queue_title": "Выберите папку мода для очереди",
        "folder_not_found_title": "Папка не найдена",
        "folder_not_found_body": "Папка не существует:\n{path}",
        "cancelling": "Останавливаю... (дожидаюсь текущей строки/пачки)",
        "no_folder_selected_title": "Не выбрана папка",
        "no_mod_selected_body": "Укажите папку мода или добавьте моды в очередь.",
        "no_output_selected_body": "Укажите папку для сохранения результата.",
        "starting_translation": "Запускаю перевод...",
        "done_saved_to": "Готово! Перевод сохранён в:\n{path}",
        "done_title": "Готово",
        "cancelled": "Отменено. {reason}",
        "error_occurred": "Произошла ошибка — см. окно сообщения.",
        "translation_error_title": "Ошибка перевода",
        "engine_argos_only": "Только Argos (быстро)",
        "engine_llm_only": "Только LLM (медленно, качественнее)",
        "engine_both": "Argos + LLM-доработка (рекомендовано)",
        "engine_both_check": "Argos + LLM-проверка ошибок (быстрее)",
        "lang_ru": "Русский", "lang_uk": "Украинский", "lang_de": "Немецкий",
        "lang_fr": "Французский", "lang_es": "Испанский", "lang_it": "Итальянский",
        "lang_pl": "Польский", "lang_pt": "Португальский", "lang_zh": "Китайский (упрощ.)",
        "lang_ja": "Японский", "lang_ko": "Корейский", "lang_cs": "Чешский",
        "lang_nl": "Нидерландский", "lang_tr": "Турецкий",
    },
    "en": {
        "window_title": "RimWorld Mod Translator v{version}",
        "ui_language": "Interface language:",
        "mod_folder": "Mod folder:",
        "browse": "Browse...",
        "mod_queue": "Mod queue (optional):",
        "add": "Add",
        "remove": "Remove",
        "output_folder": "Save translation to:",
        "translation_language": "Translation language:",
        "translation_engine": "Translation engine:",
        "ollama_model": "Ollama model:",
        "refresh_list": "Refresh list",
        "searching_models": "Searching for models...",
        "update_mode": "Update mode: translate only new/changed strings "
                       "(if the output folder already has a translation)",
        "original_comments": "Add a comment with the original English text to translation "
                              "files (for comparison)",
        "translate": "Translate",
        "cancel": "Cancel",
        "ready": "Ready.",
        "detailed_log": "Detailed log: {path}",
        "pick_mod_folder_title": "Select the mod folder (the one with About/About.xml)",
        "mod_detected": "Mod detected: {name}",
        "about_not_found": "About.xml not found — make sure this is a RimWorld mod folder.",
        "pick_output_title": "Where to save the translation",
        "pick_mod_for_queue_title": "Select a mod folder for the queue",
        "folder_not_found_title": "Folder not found",
        "folder_not_found_body": "This folder does not exist:\n{path}",
        "cancelling": "Stopping... (waiting for the current line/batch)",
        "no_folder_selected_title": "No folder selected",
        "no_mod_selected_body": "Specify a mod folder or add mods to the queue.",
        "no_output_selected_body": "Specify a folder to save the result to.",
        "starting_translation": "Starting translation...",
        "done_saved_to": "Done! Translation saved to:\n{path}",
        "done_title": "Done",
        "cancelled": "Cancelled. {reason}",
        "error_occurred": "An error occurred — see the message window.",
        "translation_error_title": "Translation error",
        "engine_argos_only": "Argos only (fast)",
        "engine_llm_only": "LLM only (slow, better quality)",
        "engine_both": "Argos + LLM polish (recommended)",
        "engine_both_check": "Argos + LLM error check (faster)",
        "lang_ru": "Russian", "lang_uk": "Ukrainian", "lang_de": "German",
        "lang_fr": "French", "lang_es": "Spanish", "lang_it": "Italian",
        "lang_pl": "Polish", "lang_pt": "Portuguese", "lang_zh": "Chinese (simplified)",
        "lang_ja": "Japanese", "lang_ko": "Korean", "lang_cs": "Czech",
        "lang_nl": "Dutch", "lang_tr": "Turkish",
    },
    "uk": {
        "window_title": "RimWorld Mod Translator v{version}",
        "ui_language": "Мова інтерфейсу:",
        "mod_folder": "Папка мода:",
        "browse": "Огляд...",
        "mod_queue": "Черга модів (необов'язково):",
        "add": "Додати",
        "remove": "Прибрати",
        "output_folder": "Куди зберегти переклад:",
        "translation_language": "Мова перекладу:",
        "translation_engine": "Рушій перекладу:",
        "ollama_model": "Модель Ollama:",
        "refresh_list": "Оновити список",
        "searching_models": "Шукаю моделі...",
        "update_mode": "Режим оновлення: перекладати лише нові/змінені рядки "
                       "(якщо в папці виводу вже є переклад)",
        "original_comments": "Додавати у файли перекладу коментар з оригінальним "
                              "англійським текстом (для звірки)",
        "translate": "Перекласти",
        "cancel": "Скасувати",
        "ready": "Готовий до роботи.",
        "detailed_log": "Детальний журнал: {path}",
        "pick_mod_folder_title": "Виберіть папку мода (там, де About/About.xml)",
        "mod_detected": "Виявлено мод: {name}",
        "about_not_found": "About.xml не знайдено — перевірте, що це папка мода RimWorld.",
        "pick_output_title": "Куди зберегти переклад",
        "pick_mod_for_queue_title": "Виберіть папку мода для черги",
        "folder_not_found_title": "Папку не знайдено",
        "folder_not_found_body": "Ця папка не існує:\n{path}",
        "cancelling": "Зупиняю... (чекаю завершення поточного рядка/пакета)",
        "no_folder_selected_title": "Не вибрано папку",
        "no_mod_selected_body": "Вкажіть папку мода або додайте моди до черги.",
        "no_output_selected_body": "Вкажіть папку для збереження результату.",
        "starting_translation": "Запускаю переклад...",
        "done_saved_to": "Готово! Переклад збережено в:\n{path}",
        "done_title": "Готово",
        "cancelled": "Скасовано. {reason}",
        "error_occurred": "Сталася помилка — див. вікно повідомлення.",
        "translation_error_title": "Помилка перекладу",
        "engine_argos_only": "Тільки Argos (швидко)",
        "engine_llm_only": "Тільки LLM (повільно, якісніше)",
        "engine_both": "Argos + доопрацювання LLM (рекомендовано)",
        "engine_both_check": "Argos + перевірка помилок LLM (швидше)",
        "lang_ru": "Російська", "lang_uk": "Українська", "lang_de": "Німецька",
        "lang_fr": "Французька", "lang_es": "Іспанська", "lang_it": "Італійська",
        "lang_pl": "Польська", "lang_pt": "Португальська", "lang_zh": "Китайська (спрощ.)",
        "lang_ja": "Японська", "lang_ko": "Корейська", "lang_cs": "Чеська",
        "lang_nl": "Нідерландська", "lang_tr": "Турецька",
    },
    "de": {
        "window_title": "RimWorld Mod Translator v{version}",
        "ui_language": "Oberflächensprache:",
        "mod_folder": "Mod-Ordner:",
        "browse": "Durchsuchen...",
        "mod_queue": "Mod-Warteschlange (optional):",
        "add": "Hinzufügen",
        "remove": "Entfernen",
        "output_folder": "Übersetzung speichern unter:",
        "translation_language": "Zielsprache:",
        "translation_engine": "Übersetzungsengine:",
        "ollama_model": "Ollama-Modell:",
        "refresh_list": "Liste aktualisieren",
        "searching_models": "Suche Modelle...",
        "update_mode": "Aktualisierungsmodus: nur neue/geänderte Zeilen übersetzen "
                       "(falls der Ausgabeordner bereits eine Übersetzung enthält)",
        "original_comments": "Einen Kommentar mit dem englischen Originaltext in die "
                              "Übersetzungsdateien einfügen (zum Abgleich)",
        "translate": "Übersetzen",
        "cancel": "Abbrechen",
        "ready": "Bereit.",
        "detailed_log": "Ausführliches Protokoll: {path}",
        "pick_mod_folder_title": "Mod-Ordner auswählen (der mit About/About.xml)",
        "mod_detected": "Mod erkannt: {name}",
        "about_not_found": "About.xml nicht gefunden — stellen Sie sicher, dass dies ein "
                           "RimWorld-Mod-Ordner ist.",
        "pick_output_title": "Wohin die Übersetzung gespeichert werden soll",
        "pick_mod_for_queue_title": "Mod-Ordner für die Warteschlange auswählen",
        "folder_not_found_title": "Ordner nicht gefunden",
        "folder_not_found_body": "Dieser Ordner existiert nicht:\n{path}",
        "cancelling": "Wird gestoppt... (wartet auf aktuelle Zeile/Charge)",
        "no_folder_selected_title": "Kein Ordner ausgewählt",
        "no_mod_selected_body": "Geben Sie einen Mod-Ordner an oder fügen Sie Mods zur "
                                "Warteschlange hinzu.",
        "no_output_selected_body": "Geben Sie einen Ordner zum Speichern des Ergebnisses an.",
        "starting_translation": "Übersetzung wird gestartet...",
        "done_saved_to": "Fertig! Übersetzung gespeichert unter:\n{path}",
        "done_title": "Fertig",
        "cancelled": "Abgebrochen. {reason}",
        "error_occurred": "Ein Fehler ist aufgetreten — siehe Meldungsfenster.",
        "translation_error_title": "Übersetzungsfehler",
        "engine_argos_only": "Nur Argos (schnell)",
        "engine_llm_only": "Nur LLM (langsam, bessere Qualität)",
        "engine_both": "Argos + LLM-Politur (empfohlen)",
        "engine_both_check": "Argos + LLM-Fehlerprüfung (schneller)",
        "lang_ru": "Russisch", "lang_uk": "Ukrainisch", "lang_de": "Deutsch",
        "lang_fr": "Französisch", "lang_es": "Spanisch", "lang_it": "Italienisch",
        "lang_pl": "Polnisch", "lang_pt": "Portugiesisch", "lang_zh": "Chinesisch (vereinfacht)",
        "lang_ja": "Japanisch", "lang_ko": "Koreanisch", "lang_cs": "Tschechisch",
        "lang_nl": "Niederländisch", "lang_tr": "Türkisch",
    },
}

SUPPORTED_UI_LANGUAGES = [
    ("Русский", "ru"),
    ("English", "en"),
    ("Українська", "uk"),
    ("Deutsch", "de"),
]

_DEFAULT_UI_LANGUAGE = "en"


def detect_system_ui_language() -> str:
    """Автоопределение языка интерфейса по системному языку Windows —
    только для ПЕРВОГО запуска (когда пользователь ещё не выбрал язык
    явно в самой программе, см. settings.py). Явный выбор в программе
    всегда имеет приоритет и переопределяет это значение при следующих
    запусках. Best-effort: если определить не удалось — английский."""
    try:
        windll_lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        lang_code = locale.windows_locale.get(windll_lang_id)
        if lang_code:
            primary = lang_code.split("_")[0].lower()
            if primary in _STRINGS:
                return primary
    except (AttributeError, OSError):
        pass
    return _DEFAULT_UI_LANGUAGE


class Translator:
    """Держит текущий язык интерфейса и переводит строки по ключу. Один
    экземпляр на всё приложение (см. gui.py), а не глобальная функция —
    так смену языка можно применить сразу ко всем виджетам без перезапуска."""

    def __init__(self, language: str) -> None:
        self.language = language if language in _STRINGS else _DEFAULT_UI_LANGUAGE

    def set_language(self, language: str) -> None:
        self.language = language if language in _STRINGS else _DEFAULT_UI_LANGUAGE

    def t(self, key: str, **kwargs: object) -> str:
        strings = _STRINGS.get(self.language, _STRINGS[_DEFAULT_UI_LANGUAGE])
        template = strings.get(key) or _STRINGS[_DEFAULT_UI_LANGUAGE].get(key, key)
        return template.format(**kwargs) if kwargs else template
