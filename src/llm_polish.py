"""LLM-постредактор поверх черновика Argos Translate (см. translator.py).

Схема: Argos быстро и офлайн даёт дословный черновик перевода строки, а
локальная LLM через Ollama (тоже полностью офлайн, без внешних API) получает
на вход оригинал, черновик Argos и контекст строки (мод/тип Def/ключ) и
выдаёт финальный, грамматически согласованный перевод. Это решает главную
слабость чистого Argos — он не видит контекст и не согласует падежи/род при
подстановке терминов из глоссария (translator.py/glossary.py).

Если Ollama недоступна (не установлена/не запущена/нет модели), обёртка
прозрачно откатывается на черновик Argos, ничего не ломая.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .log_setup import get_logger

log = get_logger("llm_polish")

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:7b"
REQUEST_TIMEOUT_SECONDS = 120

LANG_HUMAN_NAMES = {
    "ru": "русский", "uk": "украинский", "de": "немецкий", "fr": "французский",
    "es": "испанский", "it": "итальянский", "pl": "польский", "pt": "португальский",
    "zh": "китайский", "ja": "японский", "ko": "корейский", "cs": "чешский",
    "nl": "нидерландский", "tr": "турецкий",
}

_SYSTEM_PROMPT = """Ты — редактор перевода модов для игры RimWorld. Тебе дают оригинальную
строку на английском, черновой машинный перевод на {lang_name} и контекст
(мод/поле). Верни только исправленный перевод: естественный, грамматически
согласованный (падежи, род, порядок слов), с сохранением игровой
терминологии RimWorld. Сохрани БУКВАЛЬНО любые {{0}}, {{1}} и \\n на тех же
местах по смыслу.

КРИТИЧЕСКИ ВАЖНО: не рассуждай, не объясняй, не пиши шагов и не используй
markdown. Ответ должен быть ЗАКЛЮЧЁН между тегами <ans> и </ans> и содержать
только сам перевод, одной строкой, без кавычек.

Пример:
Оригинал (EN): heavy-duty pipe
Черновой перевод: труба усиленный
<ans>усиленная труба</ans>"""

_USER_TEMPLATE = """Мод: {mod_name}
Поле: {field_key}
Оригинал (EN): {original}
Черновой перевод: {draft}"""

_ANSWER_RE = re.compile(r"<ans>(.*?)</ans>", re.DOTALL | re.IGNORECASE)


@dataclass
class LlmContext:
    mod_name: str = ""
    field_key: str = ""


class OllamaUnavailable(RuntimeError):
    pass


def list_installed_models(base_url: str = OLLAMA_URL) -> list[str]:
    """Возвращает имена моделей, установленных в локальной Ollama (пустой
    список, если Ollama не запущена/не установлена)."""
    try:
        req = urllib.request.Request(
            base_url.replace("/api/generate", "/api/tags"), method="GET"
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except (urllib.error.URLError, OSError, ValueError):
        return []


class LlmPolisher:
    """Ленивая проверка доступности Ollama: если сервер/модель недоступны,
    все вызовы polish() просто возвращают черновик Argos без изменений."""

    def __init__(self, model: str = DEFAULT_MODEL, lang_name: str = "русский",
                 base_url: str = OLLAMA_URL, enabled: bool = True):
        self.model = model
        self.lang_name = lang_name
        self.base_url = base_url
        self.enabled = enabled
        self._checked = False
        self._available = False

    def is_available(self) -> bool:
        """Публичная проверка: доступна ли Ollama с нужной моделью прямо сейчас."""
        return self._check_available()

    def _check_available(self) -> bool:
        if self._checked:
            return self._available
        self._checked = True
        try:
            req = urllib.request.Request(
                self.base_url.replace("/api/generate", "/api/tags"), method="GET"
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            self._available = any(m.split(":")[0] == self.model.split(":")[0] for m in models)
        except (urllib.error.URLError, OSError, ValueError):
            self._available = False
        return self._available

    def polish(self, original: str, draft: str, context: LlmContext) -> str:
        if not self.enabled or not original.strip():
            return draft
        if not self._check_available():
            return draft

        prompt = _USER_TEMPLATE.format(
            mod_name=context.mod_name or "неизвестен",
            field_key=context.field_key or "неизвестно",
            original=original,
            draft=draft,
        )
        system = _SYSTEM_PROMPT.format(lang_name=self.lang_name)

        payload = {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        log.debug("LLM-запрос: %s.%s (%.60s)", context.mod_name, context.field_key, original)
        started = time.monotonic()
        try:
            req = urllib.request.Request(
                self.base_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            raw = data.get("response", "").strip()
            elapsed = time.monotonic() - started
            answer = self._extract_answer(raw)
            log.debug("LLM-ответ за %.1fs: %s.%s -> %.60s",
                      elapsed, context.mod_name, context.field_key, answer or "(пусто, откат на Argos)")
            return answer or draft
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
            elapsed = time.monotonic() - started
            log.warning("LLM-запрос упал за %.1fs (%s.%s): %s — откат на черновик Argos",
                        elapsed, context.mod_name, context.field_key, e)
            return draft

    @staticmethod
    def _extract_answer(raw: str) -> str:
        """Модель иногда рассуждает вслух, несмотря на инструкцию — извлекаем
        текст между <ans>...</ans>, а если тегов нет, берём последнюю
        непустую строку как разумный компромисс."""
        if not raw:
            return ""
        match = _ANSWER_RE.search(raw)
        if match:
            return match.group(1).strip()
        lines = [line.strip().strip('"') for line in raw.splitlines() if line.strip()]
        return lines[-1] if lines else ""
