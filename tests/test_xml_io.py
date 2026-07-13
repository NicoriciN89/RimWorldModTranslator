"""Тесты эвристики извлечения переводимых полей из Defs/*.xml
(src/xml_io.py) — покрывают баги, найденные при переходе с белого списка
тегов на определение переводимости по содержимому текста: составные
идентификаторы вида Namespace.ClassName (driverClass) и служебные ссылки
на переменные квест-скрипта (storeAs, tile, faction, ...) ошибочно
принимались за текст."""
from __future__ import annotations

from src.xml_io import extract_translatable_from_defs
from pathlib import Path


def _extract(tmp_path: Path, xml: str):
    path = tmp_path / "Test.xml"
    path.write_text(xml, encoding="utf-8")
    return extract_translatable_from_defs(path)


def test_label_and_description_are_extracted(tmp_path: Path) -> None:
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <ThingDef>
    <defName>TestThing</defName>
    <label>test thing</label>
    <description>A thing for testing.</description>
  </ThingDef>
</Defs>
""")
    by_path = {r.field_path: r.text for r in refs}
    assert by_path == {"label": "test thing", "description": "A thing for testing."}


def test_fully_qualified_class_name_tag_yields_short_def_type(tmp_path: Path) -> None:
    """RimWorld разрешает полностью квалифицированное имя класса как тег
    def-элемента (напр. <My.Namespace.FooDef>...</My.Namespace.FooDef>) для
    разрешения неоднозначности между namespace'ами — игра трактует его как
    обычный FooDef, и Languages/<Lang>/DefInjected/ мода называется по
    короткому имени (последний сегмент), а не по полному пути класса."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <My.Namespace.FooDef>
    <defName>TestFoo</defName>
    <label>test foo</label>
  </My.Namespace.FooDef>
</Defs>
""")
    assert len(refs) == 1
    assert refs[0].def_type == "FooDef"


def test_dotted_class_reference_is_not_translatable(tmp_path: Path) -> None:
    """Баг из bio_clip: driverClass="MyMod.JobDriver_DoThing" (составной
    идентификатор Namespace.ClassName) попадало в перевод по старой
    эвристике "содержит текст"."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <JobDef>
    <defName>TestJob</defName>
    <driverClass>MyMod.JobDriver_DoThing</driverClass>
    <reportString>doing the thing.</reportString>
  </JobDef>
</Defs>
""")
    by_path = {r.field_path: r.text for r in refs}
    assert "driverClass" not in by_path
    assert by_path == {"reportString": "doing the thing."}


def test_defname_reference_list_is_not_translatable(tmp_path: Path) -> None:
    """defName-ссылки внутри списков (<recipeUsers><li>SomeBench</li></...>)
    не должны попадать в перевод — это идентификаторы, не текст."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <RecipeDef>
    <defName>TestRecipe</defName>
    <label>make test item</label>
    <recipeUsers>
      <li>SomeCraftingBench</li>
    </recipeUsers>
  </RecipeDef>
</Defs>
""")
    texts = {r.text for r in refs}
    assert "SomeCraftingBench" not in texts
    assert "make test item" in texts


def test_quest_script_technical_refs_are_not_translatable(tmp_path: Path) -> None:
    """Баг из trauma_team_missions: служебные ссылки на переменные квеста
    ($siteTile, storeAs...) ошибочно проходили эвристику "есть буквы"."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <QuestScriptDef>
    <defName>TestQuest</defName>
    <root>
      <nodes>
        <li Class="QuestNode_GetMap">
          <storeAs>siteTile</storeAs>
          <tile>$siteTile</tile>
        </li>
        <li Class="QuestNode_Letter">
          <label>Contract expired</label>
          <text>The situation resolved without you.</text>
        </li>
      </nodes>
    </root>
  </QuestScriptDef>
</Defs>
""")
    by_text = {r.text for r in refs}
    assert "siteTile" not in by_text
    assert "$siteTile" not in by_text
    assert "Contract expired" in by_text
    assert "The situation resolved without you." in by_text


def test_rule_string_prefix_is_kept_but_marked_translatable(tmp_path: Path) -> None:
    """Баг из trauma_team_missions: rulesStrings хранит "ключ->текст" —
    вся строка (включая ключ-идентификатор) должна попадать в перевод как
    один DefFieldRef, а защита ключа от перевода происходит отдельно в
    translator.py (см. test_translator.py)."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <QuestScriptDef>
    <defName>TestQuest</defName>
    <questNameRules>
      <rulesStrings>
        <li>distress->Distress Call</li>
      </rulesStrings>
    </questNameRules>
  </QuestScriptDef>
</Defs>
""")
    texts = [r.text for r in refs]
    assert texts == ["distress->Distress Call"]


def test_numeric_and_boolean_values_are_not_translatable(tmp_path: Path) -> None:
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <ThingDef>
    <defName>TestThing</defName>
    <marketValue>12.5</marketValue>
    <menuHidden>true</menuHidden>
    <label>test thing</label>
  </ThingDef>
</Defs>
""")
    texts = {r.text for r in refs}
    assert texts == {"test thing"}
