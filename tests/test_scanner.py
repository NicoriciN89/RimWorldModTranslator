"""Тесты src/scanner.py на маленьких синтетических модах — покрывают баги,
найденные и исправленные вручную на реальных модах в процессе разработки:
недостающий DefInjected, дублирование строк из вложенных версионных папок,
поддержку LoadFolders.xml."""
from __future__ import annotations

from pathlib import Path

from src import scanner

_DEFS_XML = """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <ThingDef>
    <defName>TestThing</defName>
    <label>test thing</label>
    <description>A thing for testing.</description>
  </ThingDef>
</Defs>
"""

_KEYED_XML = """<?xml version="1.0" encoding="utf-8"?>
<LanguageData>
  <TestKey>Some keyed string</TestKey>
</LanguageData>
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_no_languages_dir_falls_back_to_defs(tmp_path: Path) -> None:
    """Без Languages/English вообще — строки извлекаются прямо из Defs/*.xml."""
    _write(tmp_path / "Defs" / "ThingDefs.xml", _DEFS_XML)

    result = scanner.scan_mod(tmp_path)

    assert result.source_lang_dir is None
    assert len(result.keyed) == 0
    assert len(result.def_injected) == 1
    keys = [e.key for e in result.def_injected[0].data.keyed_items()]
    assert keys == ["TestThing.label", "TestThing.description"]


def test_keyed_without_definjected_still_extracts_defs(tmp_path: Path) -> None:
    """Баг из bio_clip: Languages/English/Keyed существует, но DefInjected
    нет вообще — раньше строки из Defs/*.xml терялись молча."""
    _write(tmp_path / "Languages" / "English" / "Keyed" / "Test.xml", _KEYED_XML)
    _write(tmp_path / "Defs" / "ThingDefs.xml", _DEFS_XML)

    result = scanner.scan_mod(tmp_path)

    assert result.source_lang_dir == "English"
    assert len(result.keyed) == 1
    assert len(result.def_injected) == 1
    keys = [e.key for e in result.def_injected[0].data.keyed_items()]
    assert keys == ["TestThing.label", "TestThing.description"]


def test_definjected_partial_coverage_fills_gap(tmp_path: Path) -> None:
    """DefInjected существует, но покрывает только часть DefType — недостающий
    тип (ThingDef) должен быть дополнен извлечением из Defs/*.xml, а уже
    покрытый (RecipeDef) не должен дублироваться."""
    _write(tmp_path / "Languages" / "English" / "DefInjected" / "RecipeDef" / "R.xml",
           '<?xml version="1.0" encoding="utf-8"?>\n<LanguageData>\n'
           '  <SomeRecipe.label>some recipe</SomeRecipe.label>\n</LanguageData>\n')
    _write(tmp_path / "Defs" / "ThingDefs.xml", _DEFS_XML)

    result = scanner.scan_mod(tmp_path)

    def_types = {task.def_type: task for task in result.def_injected}
    assert set(def_types) == {"RecipeDef", "ThingDef"}
    assert [e.key for e in def_types["RecipeDef"].data.keyed_items()] == ["SomeRecipe.label"]
    assert [e.key for e in def_types["ThingDef"].data.keyed_items()] == \
        ["TestThing.label", "TestThing.description"]


def test_fully_qualified_def_tag_matches_short_definjected_folder(tmp_path: Path) -> None:
    """Баг из celetech_shuttle_extension: RimWorld разрешает полностью
    квалифицированное имя класса как тег def-элемента (напр.
    <My.Namespace.FooDef>...</My.Namespace.FooDef>), а игра трактует его как
    обычный FooDef — DefInjected-папка мода называется по короткому имени.
    Раньше def_type брался как raw XML-тег целиком, из-за чего "покрыт ли
    этот DefType в DefInjected" никогда не совпадало, и fallback-сканирование
    дублировало уже покрытый контент под отдельной (неверной) папкой с
    полным путём класса вместо короткого имени."""
    qualified_defs_xml = """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <My.Namespace.FooDef>
    <defName>TestFoo</defName>
    <label>test foo</label>
  </My.Namespace.FooDef>
</Defs>
"""
    _write(tmp_path / "Languages" / "English" / "DefInjected" / "FooDef" / "F.xml",
           '<?xml version="1.0" encoding="utf-8"?>\n<LanguageData>\n'
           '  <TestFoo.label>test foo</TestFoo.label>\n</LanguageData>\n')
    _write(tmp_path / "Defs" / "FooDefs.xml", qualified_defs_xml)

    result = scanner.scan_mod(tmp_path)

    assert len(result.def_injected) == 1
    assert result.def_injected[0].def_type == "FooDef"


def test_stale_definjected_text_is_replaced_by_current_defs_text(tmp_path: Path) -> None:
    """Баг из celetech_shuttle_extension: автор мода обновил label/description
    в Defs/*.xml, но забыл синхронизировать Languages/English/DefInjected —
    RimWorld при этом показывает игроку АКТУАЛЬНЫЙ текст из Defs, а не
    устаревший из DefInjected. Раньше сканер безусловно доверял DefInjected
    как источнику правды, из-за чего переводился устаревший (не
    соответствующий игре) текст. Теперь при расхождении подставляется
    актуальный текст из Defs."""
    _write(tmp_path / "Languages" / "English" / "DefInjected" / "ThingDef" / "T.xml",
           '<?xml version="1.0" encoding="utf-8"?>\n<LanguageData>\n'
           '  <TestThing.label>old stale label</TestThing.label>\n'
           '  <TestThing.description>A thing for testing.</TestThing.description>\n'
           '</LanguageData>\n')
    _write(tmp_path / "Defs" / "ThingDefs.xml", _DEFS_XML)

    result = scanner.scan_mod(tmp_path)

    assert len(result.def_injected) == 1
    by_key = {e.key: e.text for e in result.def_injected[0].data.keyed_items()}
    assert by_key["TestThing.label"] == "test thing"
    assert by_key["TestThing.description"] == "A thing for testing."


def test_nested_version_folder_does_not_duplicate_strings(tmp_path: Path) -> None:
    """Баг между v1.0.4 и v1.0.5: если LoadFolders.xml (или fallback по имени
    папки) возвращает и корень мода, и вложенную в него версионную папку
    (mod_root/1.6), одна и та же физическая папка Defs не должна
    сканироваться дважды."""
    _write(tmp_path / "1.6" / "Defs" / "ThingDefs.xml", _DEFS_XML)

    result = scanner.scan_mod(tmp_path)

    assert len(result.def_injected) == 1
    keys = [e.key for e in result.def_injected[0].data.keyed_items()]
    assert keys == ["TestThing.label", "TestThing.description"]


def test_load_folders_xml_picks_only_newest_version(tmp_path: Path) -> None:
    """Мод хранит несколько версионных копий Defs (1.0 и 1.6) — при наличии
    LoadFolders.xml должна сканироваться только новейшая версия."""
    _write(tmp_path / "1.0" / "Defs" / "ThingDefs.xml",
           _DEFS_XML.replace("TestThing", "OldThing"))
    _write(tmp_path / "1.6" / "Defs" / "ThingDefs.xml", _DEFS_XML)
    _write(tmp_path / "LoadFolders.xml", """<?xml version="1.0" encoding="utf-8"?>
<loadFolders>
  <v1.0>
    <li>1.0</li>
  </v1.0>
  <v1.6>
    <li>1.6</li>
  </v1.6>
</loadFolders>
""")

    result = scanner.scan_mod(tmp_path)

    assert len(result.def_injected) == 1
    keys = [e.key for e in result.def_injected[0].data.keyed_items()]
    assert keys == ["TestThing.label", "TestThing.description"]


def test_load_folders_xml_scans_if_mod_active_paths(tmp_path: Path) -> None:
    """Баг из alpha_memes: пути с условием IfModActive (обычно DLC-специфичный
    контент вроде Mods/Biotech, Mods/Royalty, Mods/Anomaly) раньше
    пропускались целиком — под предлогом "нет данных об установленных у
    пользователя DLC/модах". На практике это означало, что весь DLC-контент
    крупных модов НИКОГДА не переводился, даже если у игрока эти официальные
    DLC реально установлены (частый случай). Теперь такие пути сканируются
    безусловно — лишние строки для неактивного контента не вредят, в отличие
    от отсутствия перевода активного контента."""
    _write(tmp_path / "1.6" / "Defs" / "ThingDefs.xml", _DEFS_XML)
    _write(tmp_path / "1.6" / "Mods" / "SomeMod" / "Defs" / "ThingDefs.xml",
           _DEFS_XML.replace("TestThing", "OptionalThing"))
    _write(tmp_path / "LoadFolders.xml", """<?xml version="1.0" encoding="utf-8"?>
<loadFolders>
  <v1.6>
    <li>1.6</li>
    <li IfModActive="some.other.mod">1.6/Mods/SomeMod</li>
  </v1.6>
</loadFolders>
""")

    result = scanner.scan_mod(tmp_path)

    keys = sorted(e.key for task in result.def_injected for e in task.data.keyed_items())
    assert keys == ["OptionalThing.description", "OptionalThing.label",
                     "TestThing.description", "TestThing.label"]
