"""Сборка выходного мода-русификатора: Languages/<Lang>/{Keyed,DefInjected,
Strings} плюс About/About.xml, зависящий от оригинального мода."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

from . import xml_io
from .scanner import ScanResult

LANG_DISPLAY_NAMES = {
    "ru": "Russian", "en": "English", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "pl": "Polish", "pt": "Portuguese",
    "uk": "Ukrainian", "zh": "ChineseSimplified", "ja": "Japanese",
    "ko": "Korean", "cs": "Czech", "nl": "Dutch", "tr": "Turkish",
}


def rimworld_lang_dir_name(lang_code: str) -> str:
    return LANG_DISPLAY_NAMES.get(lang_code.lower(), lang_code.capitalize())


@dataclass
class OriginalModInfo:
    name: str | None
    package_id: str | None
    supported_versions: list[str]
    steam_workshop_url: str | None


def read_original_about(mod_root: Path) -> OriginalModInfo:
    about_path = next(iter(mod_root.glob("**/About/About.xml")), None)
    if about_path is None:
        return OriginalModInfo(None, None, [], None)

    raw = about_path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return OriginalModInfo(None, None, [], None)

    name = root.findtext("name")
    package_id = root.findtext("packageId")
    versions = [li.text for li in root.findall("supportedVersions/li") if li.text]

    steam_url = None
    m = re.search(r"CommunityFilePage/(\d+)", mod_root.name)
    if m:
        steam_url = f"steam://url/CommunityFilePage/{m.group(1)}"

    return OriginalModInfo(name, package_id, versions, steam_url)


def write_about_xml(out_root: Path, original: OriginalModInfo, lang_code: str,
                     translator_tag: str = "AutoTranslator") -> None:
    lang_dir = rimworld_lang_dir_name(lang_code)
    # Все значения из чужого About.xml экранируются: имя мода вида
    # "Cats & Dogs" без экранирования давало невалидный XML, и RimWorld
    # молча не загружал мод-русификатор.
    mod_name = _xml_escape(original.name or "Unknown Mod")
    orig_package_id = _xml_escape(original.package_id or "unknown.mod")
    new_package_id = f"{orig_package_id}.{lang_code.upper()}.Translation"

    versions_xml = "\n".join(f"    <li>{_xml_escape(v)}</li>"
                             for v in original.supported_versions) or "    <li>1.6</li>"

    dep_extra = ""
    if original.steam_workshop_url:
        dep_extra = f"\n      <steamWorkshopUrl>{_xml_escape(original.steam_workshop_url)}</steamWorkshopUrl>"

    content = f"""<?xml version="1.0" encoding="utf-8"?>
<ModMetaData>
  <name>{mod_name} - {lang_dir}</name>
  <author>{translator_tag}</author>
  <description>Automatic {lang_dir} translation of "{mod_name}", generated offline by {translator_tag}.

This is a translation-only add-on: install it together with the original mod and load it below the original in the mod list. Machine-translated — please report mistranslations.</description>
  <packageId>{new_package_id}</packageId>
  <supportedVersions>
{versions_xml}
  </supportedVersions>
  <modDependencies>
    <li>
      <packageId>{orig_package_id}</packageId>
      <displayName>{mod_name}</displayName>{dep_extra}
    </li>
  </modDependencies>
  <loadAfter>
    <li>{orig_package_id}</li>
  </loadAfter>
</ModMetaData>
"""
    about_dir = out_root / "About"
    about_dir.mkdir(parents=True, exist_ok=True)
    (about_dir / "About.xml").write_text(content, encoding="utf-8")


def write_translated_mod(out_root: Path, scan: ScanResult, lang_code: str,
                          with_original_comments: bool = False) -> None:
    lang_dir_name = rimworld_lang_dir_name(lang_code)
    lang_root = out_root / "Languages" / lang_dir_name

    for task in scan.keyed:
        out_path = lang_root / "Keyed" / task.rel_path
        xml_io.write_language_data(out_path, task.data, with_original_comments)

    for task in scan.def_injected:
        out_path = lang_root / "DefInjected" / task.def_type / task.rel_path
        xml_io.write_language_data(out_path, task.data, with_original_comments)

    for task in scan.strings:
        out_path = lang_root / "Strings" / task.rel_path
        xml_io.write_strings_file(out_path, task.data)
