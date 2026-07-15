"""Тесты src/generator.py — сборка выходного мода-русификатора."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from src.generator import OriginalModInfo, write_about_xml, write_translated_mod
from src.scanner import ScanResult, StringsTask
from src.xml_io import Entry, LanguageDataFile


def test_about_xml_escapes_special_characters(tmp_path: Path) -> None:
    """Имя мода вида "Cats & Dogs <Deluxe>" подставлялось в About.xml без
    экранирования — выходной файл был невалидным XML, и RimWorld молча не
    загружал мод-русификатор."""
    info = OriginalModInfo(
        name="Cats & Dogs <Deluxe>",
        package_id="author.catsanddogs",
        supported_versions=["1.6"],
        steam_workshop_url=None,
    )

    write_about_xml(tmp_path, info, "ru")

    about_path = tmp_path / "About" / "About.xml"
    root = ET.fromstring(about_path.read_text(encoding="utf-8"))  # не должно упасть
    assert root.findtext("name") == "Cats & Dogs <Deluxe> - Russian"
    assert root.findtext("packageId") == "author.catsanddogs.RU.Translation"
    assert "Cats & Dogs <Deluxe>" in (root.findtext("description") or "")


def test_about_xml_plain_name_unchanged(tmp_path: Path) -> None:
    info = OriginalModInfo(
        name="Simple Mod",
        package_id="author.simple",
        supported_versions=["1.5", "1.6"],
        steam_workshop_url="steam://url/CommunityFilePage/123456",
    )

    write_about_xml(tmp_path, info, "ru")

    root = ET.fromstring((tmp_path / "About" / "About.xml").read_text(encoding="utf-8"))
    assert root.findtext("name") == "Simple Mod - Russian"
    versions = [li.text for li in root.findall("supportedVersions/li")]
    assert versions == ["1.5", "1.6"]
    dep = root.find("modDependencies/li")
    assert dep is not None
    assert dep.findtext("packageId") == "author.simple"
    assert dep.findtext("steamWorkshopUrl") == "steam://url/CommunityFilePage/123456"


def test_strings_tasks_are_written_as_txt(tmp_path: Path) -> None:
    """Strings-задачи пишутся в Languages/<Lang>/Strings/<тот же путь>.txt —
    строка в строку с оригиналом, комментарии и пустые строки сохраняются."""
    data = LanguageDataFile()
    data.entries.append(Entry(key="", text="// ship names", is_comment=True))
    data.entries.append(Entry(key="Strings/Names/Ships.txt:1", text="Неустрашимый"))
    data.entries.append(Entry(key="", text="", is_comment=True))
    data.entries.append(Entry(key="Strings/Names/Ships.txt:3", text="Авантюра"))
    scan = ScanResult(source_lang_dir="English", keyed=[], def_injected=[],
                      strings=[StringsTask(rel_path=Path("Names/Ships.txt"), data=data)])

    write_translated_mod(tmp_path, scan, "ru")

    out_file = tmp_path / "Languages" / "Russian" / "Strings" / "Names" / "Ships.txt"
    assert out_file.read_text(encoding="utf-8") == \
        "// ship names\nНеустрашимый\n\nАвантюра\n"
