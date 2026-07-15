"""Тесты src/rimworld_rules.py — базы знаний о том, что в Defs/*.xml
переводимо, а что нет. Каждое правило тут привязано к реальному багу,
найденному на конкретном моде (см. комментарии в самом rimworld_rules.py) —
тесты те же случаи, что и в test_xml_io.py/test_translator.py, но проверяют
напрямую публичный API базы знаний, а не через xml_io/translator."""
from __future__ import annotations

from src.rimworld_rules import (
    RULE_STRING_KEY_RE,
    TRANSLATION_PLACEHOLDER_RE,
    is_never_translatable_tag,
    is_rule_string,
    is_translatable_field,
    is_translatable_value,
)


def test_never_translatable_tags_by_exact_name() -> None:
    assert is_never_translatable_tag("defName")
    assert is_never_translatable_tag("DEFNAME")
    assert is_never_translatable_tag("driverClass")
    assert not is_never_translatable_tag("label")
    assert not is_never_translatable_tag("description")


def test_type_id_suffix_tags_are_never_translatable() -> None:
    assert is_never_translatable_tag("moduleTypeID")
    assert is_never_translatable_tag("slotTypeID")
    assert is_never_translatable_tag("segmentTypeID")
    assert not is_never_translatable_tag("label")


def test_installable_types_keywords_are_never_translatable() -> None:
    assert is_never_translatable_tag("installableSegmentTypes")
    assert is_never_translatable_tag("installableModuleSlotTypes")
    assert not is_never_translatable_tag("installedComps")


def test_defname_suffix_tags_are_never_translatable() -> None:
    """Найдено на: celetech_shuttle_extension (Patches): integrationDefName
    и подобные теги — явные ссылки на defName другого def-а."""
    assert is_never_translatable_tag("integrationDefName")
    assert not is_never_translatable_tag("label")


def test_values_without_letters_are_not_translatable() -> None:
    """Найдено на: rustic_workbenches (Patches): drawSize "(5,3)" — векторы
    и кортежи без единой буквы не текст."""
    assert not is_translatable_value("(5,3)")
    assert not is_translatable_value("(0.5, 1.2, 3)")
    assert is_translatable_value("3 walls")  # буквы есть — текст


def test_impact_enum_field_is_never_translatable() -> None:
    """Найдено на: alpha_memes (PreceptDef): impact "low"/"medium"/"high" —
    enum PreceptImpact, перевод давал ошибку DefInjected в логе игры."""
    assert is_never_translatable_tag("impact")
    assert not is_never_translatable_tag("description")


def test_defname_reference_list_tags_are_never_translatable() -> None:
    """Найдено на: rustic_workbenches/cables_and_plumbing (stuffCategories),
    more_informative_ideology (associatedMemes), alpha_memes (styles) —
    списки ссылок на defName, чьи элементы выглядят как обычные слова
    ("Stony", "Guilty", "Morbid") и не отлавливаются эвристикой по значению."""
    assert is_never_translatable_tag("stuffCategories")
    assert is_never_translatable_tag("associatedMemes")
    assert is_never_translatable_tag("styles")
    assert is_never_translatable_tag("altitudeLayer")


def test_slash_path_with_hyphens_is_not_translatable() -> None:
    """Найдено на: celetech_shuttle_extension (Patches: runtimeSystemKey) —
    служебный ключ с дефисами и слэшем не проходил старую проверку пути."""
    assert not is_translatable_value("celetech.shuttle.extension.integrations/bhlite-hygiene-runtime")
    assert is_translatable_value("wall/floor paint")  # текст со слэшем и пробелом


def test_single_word_with_underscore_is_not_translatable() -> None:
    """Найдено на: cables_and_plumbing (Patches): "Med_Cables" — однословный
    идентификатор с подчёркиванием; PascalCase-проверка его не ловила
    (isalnum() False из-за "_")."""
    assert not is_translatable_value("Med_Cables")
    assert not is_translatable_value("CT_Shuttle_CE_Projectile_6mmAP")
    assert is_translatable_value("heavy_duty pipe segment")  # есть пробел — текст


def test_ordinary_capitalized_single_word_is_translatable_value() -> None:
    assert is_translatable_value("Cockpit")
    assert is_translatable_value("Wall")
    assert is_translatable_value("cockpit")


def test_multi_hump_pascal_case_identifier_is_not_translatable_value() -> None:
    assert not is_translatable_value("ShuttleReactorModuleDef")
    assert not is_translatable_value("FabricationBench")


def test_dotted_class_reference_is_not_translatable_value() -> None:
    assert not is_translatable_value("MyMod.JobDriver_DoThing")


def test_number_and_boolean_are_not_translatable_value() -> None:
    assert not is_translatable_value("123")
    assert not is_translatable_value("-4.5%")
    assert not is_translatable_value("true")
    assert not is_translatable_value("False")


def test_pure_path_or_color_is_not_translatable_value() -> None:
    assert not is_translatable_value("UI/Structures/AM_Neolithic")
    assert not is_translatable_value("#E5E54C")


def test_text_containing_backslash_is_still_translatable_value() -> None:
    """Регрессия на приоритет операторов (см. rimworld_rules.py) — обычный
    многострочный текст с литеральным \\n внутри не должен отбрасываться
    целиком только из-за наличия обратного слэша где-то в середине."""
    text = ("This culture has fallen from grace entirely.\\n\\n"
            "Gameplay effect:\\n - Some detail here.")
    assert is_translatable_value(text)


def test_rule_string_with_parenthesized_params_matches() -> None:
    assert is_rule_string("rulesStrings", "distress->Distress Call")
    assert is_rule_string("rulesStrings", "founderJoin(tag=meme_Artist)     ->text here")
    assert not is_rule_string("label", "distress->Distress Call")


def test_rule_string_key_re_splits_key_and_text() -> None:
    m = RULE_STRING_KEY_RE.match("founderJoin(tag=meme_Artist)     ->our founder was inspired")
    assert m is not None
    assert m.group(1) == "founderJoin(tag=meme_Artist)     "
    assert m.group(2) == "our founder was inspired"


def test_translation_placeholder_re_covers_all_known_forms() -> None:
    text = "{0} and [founderName] said \\n hello (rest of text)"
    found = TRANSLATION_PLACEHOLDER_RE.findall(text)
    assert "{0}" in found
    assert "[founderName]" in found
    assert "\\n" in found


def test_is_translatable_field_combines_tag_and_value_checks() -> None:
    assert is_translatable_field("label", "Cockpit")
    assert not is_translatable_field("moduleTypeID", "cockpit")
    assert not is_translatable_field("defName", "AnyValueWorks")
