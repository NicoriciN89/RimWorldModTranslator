"""Тесты src/patches.py — извлечение переводимого текста из Patches/*.xml."""
from __future__ import annotations

from pathlib import Path

from src.patches import extract_translatable_from_patch


def _extract(tmp_path: Path, xml: str):
    path = tmp_path / "TestPatch.xml"
    path.write_text(xml, encoding="utf-8")
    return extract_translatable_from_patch(path)


def test_add_description_to_foreign_def(tmp_path: Path) -> None:
    """Типовой патч: мод добавляет description чужому def-у (из игры или
    другого мода) — текст показывается игроку и должен попадать в перевод,
    раньше папка Patches/ не сканировалась вообще."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Patch>
  <Operation Class="PatchOperationAdd">
    <xpath>Defs/ThingDef[defName="Wall"]</xpath>
    <value>
      <description>A sturdy wall for your colony.</description>
    </value>
  </Operation>
</Patch>
""")
    assert len(refs) == 1
    assert refs[0].def_type == "ThingDef"
    assert refs[0].def_name == "Wall"
    assert refs[0].field_path == "description"
    assert refs[0].text == "A sturdy wall for your colony."


def test_replace_label_targets_parent_of_xpath_node(tmp_path: Path) -> None:
    """PatchOperationReplace целится в САМ заменяемый узел — итоговое место
    значения это его родитель плюс тег из <value>."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Patch>
  <Operation Class="PatchOperationReplace">
    <xpath>Defs/ThingDef[defName="Wall"]/label</xpath>
    <value>
      <label>reinforced wall</label>
    </value>
  </Operation>
</Patch>
""")
    assert len(refs) == 1
    assert refs[0].def_name == "Wall"
    assert refs[0].field_path == "label"
    assert refs[0].text == "reinforced wall"


def test_multiple_defnames_in_one_xpath(tmp_path: Path) -> None:
    """xpath с несколькими defName через or — патч применяется к каждому,
    и перевод нужен под ключом каждого."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Patch>
  <Operation Class="PatchOperationAdd">
    <xpath>Defs/ThingDef[defName="Wall" or defName="Door"]</xpath>
    <value>
      <description>Shared new description.</description>
    </value>
  </Operation>
</Patch>
""")
    by_name = {r.def_name: r for r in refs}
    assert set(by_name) == {"Wall", "Door"}
    assert all(r.field_path == "description" for r in refs)


def test_operations_nested_in_sequence_and_findmod(tmp_path: Path) -> None:
    """Операции вложены в PatchOperationSequence и PatchOperationFindMod —
    текст из вложенных Add/Replace тоже должен извлекаться (условные патчи
    сканируются безусловно, как IfModActive в LoadFolders.xml)."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Patch>
  <Operation Class="PatchOperationFindMod">
    <mods><li>Royalty</li></mods>
    <match Class="PatchOperationSequence">
      <operations>
        <li Class="PatchOperationAdd">
          <xpath>Defs/ThingDef[defName="Throne"]</xpath>
          <value>
            <description>A royal seat.</description>
          </value>
        </li>
      </operations>
    </match>
  </Operation>
</Patch>
""")
    assert len(refs) == 1
    assert refs[0].def_name == "Throne"
    assert refs[0].text == "A royal seat."


def test_nested_value_fields_get_full_path(tmp_path: Path) -> None:
    """value с вложенной структурой — путь поля собирается целиком."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Patch>
  <Operation Class="PatchOperationAdd">
    <xpath>Defs/ThingDef[defName="Wall"]/building</xpath>
    <value>
      <uninstallLabel>uninstall the wall</uninstallLabel>
    </value>
  </Operation>
</Patch>
""")
    assert len(refs) == 1
    assert refs[0].field_path == "building.uninstallLabel"


def test_non_text_and_unparseable_patches_are_skipped(tmp_path: Path) -> None:
    """Патчи без текста (числа, идентификаторы) и слишком сложные xpath
    (Defs/*[...], предикаты по label) пропускаются молча — неверный
    DefInjected-ключ хуже пропуска."""
    refs = _extract(tmp_path, """<?xml version="1.0" encoding="utf-8"?>
<Patch>
  <Operation Class="PatchOperationReplace">
    <xpath>Defs/ThingDef[defName="Wall"]/statBases/MaxHitPoints</xpath>
    <value>
      <MaxHitPoints>500</MaxHitPoints>
    </value>
  </Operation>
  <Operation Class="PatchOperationAdd">
    <xpath>Defs/*[defName="Door"]</xpath>
    <value>
      <description>Wildcard def type cannot map to a folder.</description>
    </value>
  </Operation>
  <Operation Class="PatchOperationAdd">
    <xpath>Defs/ThingDef[defName="Wall"]/comps</xpath>
    <value>
      <li Class="CompProperties_Glower"><glowRadius>5</glowRadius></li>
    </value>
  </Operation>
  <Operation Class="PatchOperationAdd">
    <xpath>Defs/PreceptDef[defName="SomePrecept"]/associatedMemes/li</xpath>
    <value>
      <li>SomeMeme</li>
    </value>
  </Operation>
</Patch>
""")
    assert refs == []
