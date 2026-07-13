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
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from .log_setup import get_logger

log = get_logger("llm_polish")

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:7b"
REQUEST_TIMEOUT_SECONDS = 120

# Сколько батч-запросов слать в Ollama одновременно. Ollama сама умеет
# обслуживать несколько параллельных генераций (если хватает RAM/CPU),
# поэтому несколько батчей одновременно почти всегда быстрее одного за раз.
# Через переменную окружения можно подстроить под слабую/мощную машину.
DEFAULT_PARALLEL_REQUESTS = int(os.environ.get("RMT_LLM_PARALLEL", "2"))

# Ограничиваем длину ответа модели — правки редко длиннее оригинала,
# а низкий num_predict не даёт модели "рассуждать" и ускоряет генерацию.
_NUM_PREDICT_PER_ITEM = 60
_MIN_NUM_PREDICT = 200

# Строки без пробелов и короче этого — почти всегда однословные ярлыки
# (Shuttle, Cargo, Wall...), где согласовывать нечего: пропускаем LLM,
# оставляем черновик Argos, экономя львиную долю времени на них.
_TRIVIAL_MAX_LEN = 12
_WORD_RE = re.compile(r"\w+", re.UNICODE)

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

_BATCH_SYSTEM_PROMPT = """Ты — редактор перевода модов для игры RimWorld. Тебе дают пронумерованный
список строк: для каждой — оригинал на английском, черновой машинный перевод
на {lang_name} и контекст (мод/поле). Для КАЖДОЙ строки верни исправленный
перевод: естественный, грамматически согласованный (падежи, род, порядок
слов), с сохранением игровой терминологии RimWorld. Сохрани БУКВАЛЬНО любые
{{0}}, {{1}} и \\n на тех же местах по смыслу.

КРИТИЧЕСКИ ВАЖНО: не рассуждай, не объясняй, не пиши markdown. Ответ должен
быть ЗАКЛЮЧЁН между тегами <ans> и </ans> и содержать ровно {count} строк —
по одной на каждый номер, в формате "N: перевод", по одной на строку, без
кавычек и без пустых строк между ними. Число строк в ответе должно точно
совпадать с числом строк на входе.

Пример входа:
1. Оригинал (EN): heavy-duty pipe | Черновой перевод: труба усиленный
2. Оригинал (EN): shuttle | Черновой перевод: шаттл

Пример ответа:
<ans>
1: усиленная труба
2: шаттл
</ans>"""

_BATCH_ITEM_TEMPLATE = "{idx}. Мод: {mod_name} | Поле: {field_key} | Оригинал (EN): {original} | Черновой перевод: {draft}"

_BATCH_LINE_RE = re.compile(r"^\s*(\d+)\s*:\s*(.*)$")


@dataclass
class LlmContext:
    mod_name: str = ""
    field_key: str = ""


class OllamaUnavailable(RuntimeError):
    pass


def is_trivial_string(original: str) -> bool:
    """Короткая строка без пробелов (одно слово/токен) — почти всегда простой
    ярлык вроде "Shuttle" или "Wall", где LLM-доработке нечего согласовывать.
    Пропуск таких строк экономит время на них без заметной потери качества."""
    stripped = original.strip()
    if not stripped or len(stripped) > _TRIVIAL_MAX_LEN:
        return False
    return len(_WORD_RE.findall(stripped)) <= 1


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

    def polish_batch(self, items: list[tuple[str, str, LlmContext]],
                      skip_trivial: bool = True) -> list[str]:
        """Дорабатывает несколько строк одним запросом к LLM. items — список
        (original, draft, context). Возвращает список того же размера, в том
        же порядке; при любой проблеме (модель недоступна, ответ не разобрать)
        возвращает исходные draft без изменений. Короткие однословные строки
        (см. is_trivial_string) по умолчанию не отправляются в LLM вовсе —
        они просто остаются как есть (черновик Argos)."""
        if not items:
            return []
        drafts = [draft for _, draft, _ in items]
        if not self.enabled:
            return drafts

        if skip_trivial:
            send_indices = [i for i, (original, _, _) in enumerate(items) if not is_trivial_string(original)]
        else:
            send_indices = list(range(len(items)))
        if not send_indices:
            return drafts

        if not self._check_available():
            return drafts

        to_send = [items[i] for i in send_indices]
        lines = [
            _BATCH_ITEM_TEMPLATE.format(
                idx=i + 1,
                mod_name=context.mod_name or "неизвестен",
                field_key=context.field_key or "неизвестно",
                original=original,
                draft=draft,
            )
            for i, (original, draft, context) in enumerate(to_send)
        ]
        prompt = "\n".join(lines)
        system = _BATCH_SYSTEM_PROMPT.format(lang_name=self.lang_name, count=len(to_send))

        payload = {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": max(_MIN_NUM_PREDICT, _NUM_PREDICT_PER_ITEM * len(to_send)),
            },
        }
        log.debug("LLM-батч-запрос: %d строк (из них тривиальных пропущено: %d)",
                  len(to_send), len(items) - len(to_send))
        started = time.monotonic()
        result = list(drafts)
        try:
            req = urllib.request.Request(
                self.base_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS * max(1, len(to_send) // 2)) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            raw = data.get("response", "").strip()
            elapsed = time.monotonic() - started
            answers = self._extract_batch_answers(raw, len(to_send))
            if answers is None:
                log.warning("LLM-батч за %.1fs: не удалось разобрать ответ на %d строк — откат на черновики",
                            elapsed, len(to_send))
                return result
            log.debug("LLM-батч-ответ за %.1fs: %d строк разобрано", elapsed, len(to_send))
            for original_idx, answer in zip(send_indices, answers):
                if answer:
                    result[original_idx] = answer
            return result
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
            elapsed = time.monotonic() - started
            log.warning("LLM-батч-запрос упал за %.1fs (%d строк): %s — откат на черновики",
                        elapsed, len(to_send), e)
            return result

    def polish_many(self, items: list[tuple[str, str, LlmContext]], batch_size: int,
                     parallel_requests: int = DEFAULT_PARALLEL_REQUESTS,
                     skip_trivial: bool = True,
                     on_batch_done: Callable[[int, list[str]], None] | None = None) -> list[str]:
        """Дорабатывает большой список строк, разбивая на пачки по batch_size
        и отправляя несколько пачек в Ollama ОДНОВРЕМЕННО (parallel_requests
        штук сразу) через пул потоков — Ollama способна параллельно обслуживать
        несколько генераций, если хватает CPU/RAM, поэтому это ускоряет общий
        проход почти пропорционально числу параллельных запросов.
        on_batch_done(batch_start_index, results), если задан, вызывается из
        рабочего потока сразу по завершении каждой пачки — batch_start_index
        это индекс первого элемента пачки в исходном items, results — уже
        готовые переводы для items[batch_start_index:batch_start_index+len(results)]
        (удобно, чтобы сразу записать результат и сохранить прогресс на диск)."""
        if not items:
            return []
        if not self.enabled or not self._check_available():
            drafts = [draft for _, draft, _ in items]
            if on_batch_done:
                on_batch_done(0, drafts)
            return drafts

        batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
        offsets = [i * batch_size for i in range(len(batches))]
        results: list[list[str]] = [[] for _ in batches]

        def run_batch(idx: int) -> None:
            batch_result = self.polish_batch(batches[idx], skip_trivial=skip_trivial)
            results[idx] = batch_result
            if on_batch_done:
                on_batch_done(offsets[idx], batch_result)

        workers = max(1, parallel_requests)
        if workers == 1:
            for i in range(len(batches)):
                run_batch(i)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(run_batch, range(len(batches))))

        return [text for batch_result in results for text in batch_result]

    @staticmethod
    def _extract_batch_answers(raw: str, expected_count: int) -> list[str] | None:
        """Разбирает ответ вида '<ans>1: текст\\n2: текст</ans>' в список строк
        по позиции (индекс = номер - 1). Возвращает None, если разобрать не
        удалось вовсе (пустой ответ / нет ни одной пронумерованной строки)."""
        if not raw:
            return None
        match = _ANSWER_RE.search(raw)
        body = match.group(1) if match else raw
        result: dict[int, str] = {}
        for line in body.splitlines():
            m = _BATCH_LINE_RE.match(line)
            if not m:
                continue
            num = int(m.group(1))
            if 1 <= num <= expected_count:
                result[num] = m.group(2).strip().strip('"')
        if not result:
            return None
        return [result.get(i + 1, "") for i in range(expected_count)]

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
