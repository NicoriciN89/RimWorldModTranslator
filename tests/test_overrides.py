"""Тесты src/overrides.py и связанной логики main.translate_mod: ручные
правки пользователя, память переводов пакетного режима, отмена."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from src import main as main_module
from src import overrides
from src.scanner import scan_mod

_DEFS_XML = """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <ThingDef>
    <defName>TestThing</defName>
    <label>test thing</label>
    <description>A thing for testing.</description>
  </ThingDef>
</Defs>
"""


def _make_mod(tmp_path: Path) -> Path:
    mod = tmp_path / "some_mod"
    (mod / "Defs").mkdir(parents=True)
    (mod / "Defs" / "Things.xml").write_text(_DEFS_XML, encoding="utf-8")
    return mod


def _fake_argos(monkeypatch) -> None:
    """Подменяет движок Argos на детерминированную заглушку — тесты не должны
    зависеть от установленного языкового пакета и работать мгновенно."""
    class FakeEngine:
        def is_ready(self):
            return True

        def ensure_ready(self):
            pass

        def translate(self, text, use_glossary=True):
            return f"RU:{text}"

    monkeypatch.setattr(main_module, "get_engine", lambda s, t: FakeEngine())


def _out_key_text(out_root: Path) -> dict[str, str]:
    from src.incremental import _existing_translations
    return _existing_translations(out_root, "Russian")


def test_manual_edit_survives_regeneration(tmp_path: Path, monkeypatch) -> None:
    """Пользователь поправил строку в выходном XML — следующая генерация
    должна сохранить его правку, а не затереть машинным переводом."""
    _fake_argos(monkeypatch)
    mod = _make_mod(tmp_path)
    out = tmp_path / "out"

    out_root = main_module.translate_mod(mod, out, "en", "ru")
    texts = _out_key_text(out_root)
    assert texts["TestThing.label"] == "RU:test thing"

    # "Ручная правка": меняем текст прямо в выходном файле, как пользователь.
    xml_file = next((out_root / "Languages" / "Russian").rglob("Things.xml"))
    content = xml_file.read_text(encoding="utf-8")
    xml_file.write_text(content.replace("RU:test thing", "моя ручная правка"),
                        encoding="utf-8")

    out_root = main_module.translate_mod(mod, out, "en", "ru")
    texts = _out_key_text(out_root)
    assert texts["TestThing.label"] == "моя ручная правка"
    # Правка поднята в manual_overrides.json.
    assert "TestThing.label" in overrides._load_json(out_root / overrides.OVERRIDES_FILENAME)
    # Непоправленная строка переведена машиной как обычно.
    assert texts["TestThing.description"] == "RU:A thing for testing."


def test_translation_memory_reuses_between_mods(tmp_path: Path, monkeypatch) -> None:
    """Пакетный режим: одинаковая английская строка во втором моде очереди
    берётся из общей памяти переводов, а не переводится заново."""
    _fake_argos(monkeypatch)
    mod_a = _make_mod(tmp_path / "a")
    mod_b = _make_mod(tmp_path / "b")
    out = tmp_path / "out"

    memory: dict[str, str] = {}
    main_module.translate_mod(mod_a, out, "en", "ru", memory=memory)
    assert memory["test thing"] == "RU:test thing"

    # Ломаем "движок" — если второй мод попробует переводить сам, тест упадёт.
    def boom(s, t):
        raise AssertionError("движок не должен вызываться: всё есть в памяти")
    monkeypatch.setattr(main_module, "get_engine", lambda s, t: None)

    out_root_b = main_module.translate_mod(mod_b, out, "en", "ru", memory=memory)
    texts = _out_key_text(out_root_b)
    assert texts["TestThing.label"] == "RU:test thing"


def test_cancel_event_stops_translation(tmp_path: Path, monkeypatch) -> None:
    """Установленное событие отмены прерывает перевод с TranslationCancelled,
    а кэш инкрементального доперевода НЕ сохраняется (иначе недопереведённые
    строки считались бы готовыми при следующем запуске)."""
    _fake_argos(monkeypatch)
    mod = _make_mod(tmp_path)
    out = tmp_path / "out"

    cancel = threading.Event()
    cancel.set()  # отмена ещё до первой строки
    with pytest.raises(main_module.TranslationCancelled):
        main_module.translate_mod(mod, out, "en", "ru", cancel_event=cancel)

    out_root = out / f"{mod.name}_RU"
    from src.incremental import CACHE_FILENAME
    assert not (out_root / CACHE_FILENAME).exists()
    assert not (out_root / overrides.SNAPSHOT_FILENAME).exists()
