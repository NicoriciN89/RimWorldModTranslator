"""Тесты эвристики извлечения переводимых полей из Defs/*.xml
(src/xml_io.py) — покрывают баги, найденные при переходе с белого списка
тегов на определение переводимости по содержимому текста: составные
идентификаторы вида Namespace.ClassName (driverClass) и служебные ссылки
на переменные квест-скрипта (storeAs, tile, faction, ...) ошибочно
принимались за текст."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from src.xml_io import (
    Entry, LanguageDataFile, extract_translatable_from_defs, write_language_data,
)


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


def test_description_with_literal_backslash_is_still_translatable(tmp_path: Path) -> None:
    """Баг из alpha_memes: _looks_translatable() проверяло
    "regex.match(text) and '/' in text or '\\\\' in text" БЕЗ скобок —
    из-за приоритета операторов это парсилось как
    (regex.match AND '/' in text) OR ('\\\\' in text), то есть ЛЮБОЙ текст,
    содержащий обратный слэш ГДЕ УГОДНО (напр. буквальный "\\n\\n" внутри
    длинного multi-line description с rich-text разметкой), целиком
    отбрасывался как "похоже на путь" — даже настоящие многострочные
    описания на десятки слов. Реальный кейс: описание структуры идеологии
    с "\\n\\n<color=#E5E54C>Gameplay effect:</color>\\n - ..." внутри —
    целиком пропадало из перевода."""
    xml = """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <MemeDef>
    <defName>TestStructure</defName>
    <description>This culture has fallen from grace entirely.\\n\\n&lt;color=#E5E54C&gt;Gameplay effect:&lt;/color&gt;\\n - Some detail here.</description>
  </MemeDef>
</Defs>
"""
    refs = _extract(tmp_path, xml)
    by_path = {r.field_path: r.text for r in refs}
    assert "description" in by_path
    assert by_path["description"].startswith("This culture has fallen from grace entirely.")


def test_enum_like_type_id_fields_are_not_translatable(tmp_path: Path) -> None:
    """Баг из celetech_shuttle_extension: moduleTypeID/slotTypeID/segmentTypeID
    и списки installableSegmentTypes/installableModuleSlotTypes/
    installableModuleTypes/installableSegmentSlotTypes хранят enum-подобные
    строковые идентификаторы (cockpit, support, cargo...) для сопоставления
    модулей с посадочными местами мода — не текст для игрока. Их значения
    однословные и в нижнем регистре, поэтому старая эвристика (PascalCase)
    их не отлавливала и переводила, из-за чего мод падал в лог RimWorld с
    "defines unknown moduleTypeID unknown" при загрузке."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <ShuttleModuleDef>
    <defName>TestModule</defName>
    <label>test module</label>
    <moduleTypeID>cockpit</moduleTypeID>
    <installableSegmentTypes>
      <li>cockpit</li>
      <li>support</li>
    </installableSegmentTypes>
    <installableModuleSlotTypes>
      <li>support</li>
    </installableModuleSlotTypes>
  </ShuttleModuleDef>
</Defs>
""")
    by_path = {r.field_path: r.text for r in refs}
    assert by_path == {"label": "test module"}


def test_single_capitalized_word_label_is_translatable(tmp_path: Path) -> None:
    """Баг из celetech_shuttle_extension: <label>Cockpit</label> — обычное
    однословное название с большой буквы (RimWorld часто так пишет короткие
    label) — ошибочно считалось PascalCase-идентификатором и не попадало в
    перевод, потому что старая эвристика смотрела только на первую букву, не
    на форму слова целиком. Настоящие составные идентификаторы (несколько
    заглавных букв внутри слова, см. test_dotted_class_reference_is_not_translatable
    и ниже) по-прежнему должны исключаться."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <ThingDef>
    <defName>TestThing</defName>
    <label>Cockpit</label>
  </ThingDef>
</Defs>
""")
    by_path = {r.field_path: r.text for r in refs}
    assert by_path == {"label": "Cockpit"}


def test_multi_hump_pascal_case_identifier_is_not_translatable(tmp_path: Path) -> None:
    """Настоящий составной идентификатор (несколько заглавных букв внутри
    одного слова, напр. defName-ссылка вида "FabricationBench") должен
    оставаться исключённым, в отличие от обычного однословного label."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <RecipeDef>
    <defName>TestRecipe</defName>
    <recipeUsers>
      <li>FabricationBench</li>
    </recipeUsers>
  </RecipeDef>
</Defs>
""")
    assert refs == []


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


def test_label_from_abstract_parent_is_inherited(tmp_path: Path) -> None:
    """RimWorld позволяет выносить label/description в абстрактного родителя
    (<ThingDef Name="ABase" Abstract="True">), а наследник получает их через
    ParentName. Игра переводит уже РАЗРЕШЁННЫЙ def — текст из родителя нужен
    под ключом каждого наследника; раньше он терялся, а сам абстрактный
    родитель (без defName) вообще не сканировался."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <ThingDef Name="TestBase" Abstract="True">
    <label>base label</label>
    <description>Base description.</description>
  </ThingDef>
  <ThingDef ParentName="TestBase">
    <defName>ConcreteThing</defName>
    <label>concrete label</label>
  </ThingDef>
</Defs>
""")
    by_key = {f"{r.def_name}.{r.field_path}": r.text for r in refs}
    # label переопределён наследником, description унаследован от родителя.
    assert by_key == {
        "ConcreteThing.label": "concrete label",
        "ConcreteThing.description": "Base description.",
    }


def test_inheritance_chain_through_grandparent(tmp_path: Path) -> None:
    """Цепочка ParentName из нескольких звеньев: поле, заданное только у
    прародителя, доходит до конкретного def-а."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <ThingDef Name="GrandBase" Abstract="True">
    <description>Grandparent description.</description>
  </ThingDef>
  <ThingDef Name="MidBase" ParentName="GrandBase" Abstract="True">
    <label>mid label</label>
  </ThingDef>
  <ThingDef ParentName="MidBase">
    <defName>LeafThing</defName>
  </ThingDef>
</Defs>
""")
    by_key = {f"{r.def_name}.{r.field_path}": r.text for r in refs}
    assert by_key == {
        "LeafThing.label": "mid label",
        "LeafThing.description": "Grandparent description.",
    }


def test_inherited_li_lists_keep_parent_items_first(tmp_path: Path) -> None:
    """li-списки при наследовании объединяются: родительские элементы идут
    ПЕРВЫМИ — от этого зависят числовые индексы в DefInjected-ключах."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Defs>
  <RulePackDef Name="RulesBase" Abstract="True">
    <rulePack>
      <rulesStrings>
        <li>greet->Hello there.</li>
      </rulesStrings>
    </rulePack>
  </RulePackDef>
  <RulePackDef ParentName="RulesBase">
    <defName>ConcreteRules</defName>
    <rulePack>
      <rulesStrings>
        <li>bye->Farewell, friend.</li>
      </rulesStrings>
    </rulePack>
  </RulePackDef>
</Defs>
""")
    by_key = {f"{r.def_name}.{r.field_path}": r.text for r in refs}
    assert by_key == {
        "ConcreteRules.rulePack.rulesStrings.0": "greet->Hello there.",
        "ConcreteRules.rulePack.rulesStrings.1": "bye->Farewell, friend.",
    }


def test_comment_with_double_hyphen_produces_valid_xml(tmp_path: Path) -> None:
    """Спецификация XML запрещает "--" внутри комментария целиком (не только
    "-->") и "-" в самом конце — исходный комментарий вида "some -- note"
    раньше записывался как есть и делал весь выходной файл невалидным
    (RimWorld молча не загружал его)."""
    data = LanguageDataFile()
    data.entries.append(Entry(key="", text=" some -- note --- trailing-", is_comment=True))
    data.entries.append(Entry(key="TestKey", text="Some value"))
    out = tmp_path / "Out.xml"

    write_language_data(out, data)

    root = ET.fromstring(out.read_text(encoding="utf-8"))  # не должно упасть
    assert root.findtext("TestKey") == "Some value"


def test_en_comment_with_double_hyphen_produces_valid_xml(tmp_path: Path) -> None:
    """То же для необязательного комментария <!--EN: ...--> с оригиналом:
    раньше экранировалось только "-->", но "--" внутри комментария тоже
    запрещён спецификацией."""
    data = LanguageDataFile()
    data.entries.append(Entry(key="TestKey", text="перевод",
                              original_text="original -- with dashes -->"))
    out = tmp_path / "Out.xml"

    write_language_data(out, data, with_original_comments=True)

    content = out.read_text(encoding="utf-8")
    root = ET.fromstring(content)  # не должно упасть
    assert root.findtext("TestKey") == "перевод"
    assert "<!--EN: " in content
