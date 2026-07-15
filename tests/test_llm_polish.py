"""Тесты src/llm_polish.py — чистые функции, не требующие запущенной Ollama."""
from __future__ import annotations

from src.llm_polish import model_name_matches, placeholders_preserved


def test_requested_tag_requires_exact_match() -> None:
    """Раньше сравнивались только базовые имена (до двоеточия): установленная
    qwen2.5:3b "проходила" проверку доступности за запрошенную qwen2.5:7b,
    после чего каждый запрос генерации тихо падал и откатывался на черновик
    Argos — пользователь видел лишь замедление без объяснений."""
    assert model_name_matches("qwen2.5:7b", "qwen2.5:7b")
    assert not model_name_matches("qwen2.5:7b", "qwen2.5:3b")
    assert not model_name_matches("qwen2.5:7b", "qwen2.5:latest")
    assert not model_name_matches("qwen2.5:7b", "llama3:7b")


def test_requested_without_tag_matches_any_installed_tag() -> None:
    assert model_name_matches("qwen2.5", "qwen2.5:latest")
    assert model_name_matches("qwen2.5", "qwen2.5:7b")
    assert not model_name_matches("qwen2.5", "llama3:latest")


def test_broken_color_tag_in_answer_is_detected() -> None:
    """Баг из alpha_memes: qwen2.5 съел ">" у открывающего <color=#33d733>,
    Unity перестал парсить разметку, и игрок видел теги буквальным текстом
    в тултипе мема. Такой ответ должен отбрасываться в пользу черновика."""
    original = "All turtles are stupid.\\n\\n<color=#33d733>*ahem* The sane part.</color>"
    good = "Все черепахи тупые.\\n\\n<color=#33d733>*кхм* Нормальная часть.</color>"
    broken = "Все черепахи тупые.\\n\\n<color=#33d733*кхм* Нормальная часть.</color>"
    assert placeholders_preserved(original, good)
    assert not placeholders_preserved(original, broken)


def test_lost_placeholder_and_token_are_detected() -> None:
    assert not placeholders_preserved("Gain {0} psyfocus", "Получить псифокус")
    assert placeholders_preserved("Gain {0} psyfocus", "Получить {0} псифокуса")
    assert not placeholders_preserved("[founderName] rises", "Основатель восстаёт")
    assert placeholders_preserved("[founderName] rises", "[founderName] восстаёт")


def test_answer_without_placeholders_in_original_is_always_ok() -> None:
    assert placeholders_preserved("plain text", "просто текст")
