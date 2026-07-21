# RimWorld Mod Translator

A local, fully offline translator for RimWorld mods. Point it at a mod
folder, and it finds every translatable string
(`Languages/English/Keyed`, `DefInjected` and `Strings/*.txt`; if those
don't exist, it extracts `label`/`description`/... directly from
`Defs/*.xml` with `Name`/`ParentName` inheritance resolved, plus text
injected into other mods' defs via `Patches/*.xml`), translates it fully
offline through [Argos Translate](https://www.argosopentech.com/), and
assembles a ready-to-use translation mod with the correct file structure
and `About/About.xml`.

Works fully offline, with no internet access and no cloud API at any point.
Russian, Ukrainian, German, and French language models are bundled directly
into the program; there is no download code for translation at all. Adding
another language pair requires manually placing an Argos Translate package
into `bundled_packages/` (see "Adding another language" below) — the program
will never try to fetch one over the network.

## Installation

```powershell
cd rimworld-mod-translator
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### Ready-made .exe (no Python needed)

The built file lives at `dist/RimWorldModTranslator/RimWorldModTranslator.exe`
— double-click to run it (don't move it away from the `_internal` folder
next to it, which holds all the required libraries).

If the file isn't there (not built yet, or `dist/` was deleted), rebuild it
with the included `RimWorldModTranslator.spec` (a directory-based build —
more antivirus-friendly than `--onefile`, see "Known limitations"):

```powershell
cd rimworld-mod-translator
.venv\Scripts\activate
pip install pyinstaller
pyinstaller RimWorldModTranslator.spec --noconfirm
```

The repo ships with Argos Translate packages for `en->ru`, `en->uk`, `en->de`,
and `en->fr` pre-placed in `bundled_packages/` — the built .exe embeds them
and can translate into any of those four languages immediately, with no
network access at any point. Sentence segmentation uses a small bundled
[MiniSBD](https://github.com/LibreTranslate/MiniSBD) onnx model instead of
Stanza, which used to drag the entire `torch` library into the package as a
dead import.

### Adding another language

There is no download code in the program at all — for any language pair
beyond the four bundled ones, a language package has to be placed by hand.
If a user selects a language with no matching package present, the program
raises a clear error explaining that the pair isn't bundled and that it will
never attempt to fetch one over the network.

**If you're using the pre-built .exe** (no rebuild needed): download the
package for your language from the
[language-packs release](https://github.com/NicoriciN89/RimWorldModTranslator2/releases/tag/language-packs)
in this repo, extract the zip, and copy the resulting `translate-en_XX-*`
folder into `_internal\bundled_packages\` next to `RimWorldModTranslator.exe`
(alongside the `translate-en_ru-1_9` folder already there). The next time you
open the program, the new language shows up in the dropdown and works fully
offline, same as the bundled ones. The `language-packs` release currently
covers Spanish, Portuguese, Portuguese (Brazil), Italian, Polish, Turkish,
Chinese, Japanese, and Korean; for anything else, get the package from
https://www.argosopentech.com/argospm/index/ instead — same drop-in step.

**If you're building from source:** get an Argos Translate package the same
way, then drop the folder into `bundled_packages/` at the project root
(alongside `translate-en_ru-1_9`) before running `pyinstaller` — it gets
picked up automatically the same way the four bundled ones are.

The build takes a few minutes and currently produces a folder of roughly
**736 MB** (four bundled language packages at ~150-215 MB each).

### Plain window from source (for development)

```powershell
python -m src.gui
```

Opens a window: the "Обзор..." (Browse) button picks the mod folder (the
one containing `About/About.xml`), the dropdown picks the target language,
and "Перевести" (Translate) starts the process with a progress bar.
Nothing else is required — the output folder is pre-filled (`./output`),
but can also be changed via "Обзор...".

The window additionally offers:
- **Translation engine** — Argos only (fast), LLM only (slow, higher
  quality), Argos + LLM polish (rewrites every line) or Argos + LLM error
  check (faster — see "Error-check mode" below).
- **Ollama model** — active when the engine uses an LLM; the list is
  pulled automatically from models installed in Ollama ("Обновить список" /
  Refresh list button if you installed a new model after opening the
  window).
- **Update mode** — see "Re-translating" below.
- **Mod queue** — batch mode: add several mod folders with the "Добавить"
  (Add) button and click "Перевести" (Translate) — the mods are processed
  one after another with a shared translation memory (identical strings
  are translated once). An error in one mod doesn't stop the rest. If the
  queue is empty, the mod from the "Папка мода" field is translated as
  usual.
- **Cancel button** — stops a running translation after the current
  string/batch; the partially translated result stays on disk, but the
  incremental-update cache is not saved (a subsequent run will honestly
  re-translate everything).

Your chosen settings (folders, language, engine, model, checkboxes) persist
between runs in `%APPDATA%\RimWorldModTranslator\settings.json`.

### Manual translation fixes

You can fix an awkward string right in the output XML/txt translation
file. On the next run, the program notices your edit by itself (by
comparing the files against a snapshot of what it wrote), saves it into
`manual_overrides.json` next to the translation, and from then on always
uses your wording — regardless of engine or mode. To undo a fix, delete
its line from `manual_overrides.json`.

### Command line (for automation/scripts)

```powershell
python -m src.main --src "path\to\mod\folder" --out ".\output" --lang ru
```

- `--src` — the mod folder (the one containing `About/`); can be given
  multiple times — mods are translated one after another with a shared
  translation memory (batch mode).
- `--out` — where to put the assembled translation mod (a `<ModName>_RU`
  subfolder is created).
- `--lang` — target language code (ISO 639-1: `ru`, `de`, `fr`, `es`, `uk`, ...).
- `--source-lang` — source language code, defaults to `en`.
- `--llm` — additionally polish the Argos draft with a local LLM via
  [Ollama](https://ollama.com/) (see "LLM polishing" below).
- `--llm-model` — which Ollama model to use for polishing (default
  `qwen2.5:7b`).
- `--no-argos` — don't use Argos Translate, translate only through the LLM
  (requires `--llm`). Slower, but doesn't waste time on a draft that will
  be rewritten anyway.
- `--update` — incremental re-translation mode, see "Re-translating" below.
- `--llm-mode` — LLM operating mode (see "Error-check mode" below):
  `rewrite` (default) rewrites every line, `check` first translates the
  whole mod through Argos at 100%, then has the LLM only find and fix
  errors in the draft.
- `--with-original-comments` — add an XML comment `<!--EN: original
  text-->` before each translated line, so you can visually compare the
  translation with the original right in the output file without opening
  the source mod. The comment is only added when the translation differs
  from the original. Doesn't affect translation speed — it's just a more
  convenient output format.

On the first run for a bundled language pair (ru/uk/de/fr), the required
model is installed from the files bundled with the program — no download,
no network access. For any other pair, see "Adding another language" above.

## Re-translating / updating a mod (`--update`)

If the `--out` folder already contains a translation of this mod (built by
this same tool earlier), the `--update` flag translates only new or
changed English strings, taking everything else from the existing
translation as-is — including any manual fixes you made directly in the
translated XML files.

How this is detected: a hidden `.translation_cache.json` file is kept next
to the translation — a snapshot of the English strings as of the last
translation, key by key. With `--update`, the tool compares the mod's
current English text against this snapshot:
- text unchanged and a translation already exists → the string is left alone;
- text is new or changed → the string is translated again (with whichever
  engine you picked for this run — e.g. you can run the whole mod through
  fast Argos the first time, then `--update --llm` only for the new
  strings after a mod update).

Without `--update` (the default), the tool simply translates the whole mod
from scratch and overwrites the output folder entirely.

## LLM translation polishing (optional, `--llm`)

Argos Translate doesn't see the mod's context and doesn't adjust case/gender
agreement when substituting glossary terms (`труба усиленный` instead of
`усиленная труба`). The `--llm` flag adds a second pass: a local LLM via
Ollama receives the original text, the Argos draft, and the string's
context (mod/field), and attempts to produce a more grammatically natural
version — also fully offline, no external APIs.

With `--llm` together with Argos (i.e. without `--no-argos`), translation
runs as two separate passes rather than line-by-line interleaving: Argos
first translates a draft for every string in the mod (fast), and only then
does the LLM polish every string one by one. In the log/window this shows
up as a transition from `[3a/4] Argos: ...` to `[3b/4] LLM: ...` — making
it easier to tell which stage a long translation is currently in.

**Setup** (one-time, needs internet only for this step):
1. Download and install [Ollama](https://ollama.com/download) (~1.4 GB).
2. Download the model: `ollama pull qwen2.5:7b` (~4.7 GB).

After that, Ollama runs locally as a background service at
`http://localhost:11434` — no internet is needed for the translation
itself. If Ollama isn't installed or running, `--llm` silently falls back
to the plain Argos draft without breaking anything.

**Honest quality assessment** (tested on real strings from
`cables_and_plumbing`):

| Field | Without `--llm` (Argos) | With `--llm` (Argos + qwen2.5:7b) |
|---|---|---|
| `Med_PipeHeavyDuty.label` | труба усиленный | **усиленная труба** ✓ fixed |
| `Med_ElectricalWiring.description` | "Роллс света, тонкие..." | "Роллы светлых, тонких..." — grammar improved, but "роллы/роллс" is still the wrong word (should be "мотки"/coils) |
| `Med_ElectricalCableCuprosteel.stuffAdjective` (Cuprosteel) | камуфляж | кварцевый — a different wrong guess, still incorrect |

The LLM reliably improves agreement (cases, word order), but it's not a
silver bullet — rare/compound words (`Cuprosteel`) can be mistranslated by
either model. Decisive semantic errors still need a manual review.

**Speed** is the main cost of the quality gain, but since v1.0.7+ polishing
doesn't happen one line at a time:

- **Batches of lines per request** (`--llm-batch-size`, default 12) — the
  LLM polishes 12 lines at once in a single request instead of 12 separate
  ones, spreading Ollama's overhead (context loading, etc.) across the
  whole batch.
- **Several batches in parallel** (`--llm-parallel`, default 2, can be set
  via the `RMT_LLM_PARALLEL` environment variable) — Ollama can serve
  several generations at once if CPU/RAM allow, so 2+ parallel requests
  speed up the pass almost proportionally to their count. Keep it at 1–2 on
  a weak PC; try 3–4 on a powerful one (8+ cores, plenty of RAM).
- **Short single-word strings skip the LLM entirely** (`Shuttle`, `Wall`,
  etc. — nothing to agree on there) and stay as the Argos draft, saving all
  the time on them.
- **`num_predict` is capped** at a length proportional to batch size — keeps
  the model from rambling and slightly speeds up generation.

Overall speedup compared to line-by-line processing is roughly 5–10x under
typical conditions (depends on batch size, number of parallel requests, and
PC performance), but LLM translation is still an order of magnitude slower
than plain Argos. Use `--llm` for small/medium mods, selectively for key
strings, or run a large mod's translation in the background — not as a
replacement for the fast default mode.

## Error-check mode (`--llm-mode check`)

By default (`--llm-mode rewrite`), the LLM rewrites EVERY line in a batch
from scratch — even if the Argos draft was already grammatically correct.
This not only wastes time on already-good lines, but also carries a small
risk that the model "fixes" something that was already fine into a
different phrasing.

`--llm-mode check` (in the GUI: the "Argos + LLM-проверка ошибок" engine)
works differently:

1. Argos first translates the **entire** mod at 100% (as usual).
2. The LLM receives large batches of lines (default 20,
   `--llm-batch-size`) with the task of **finding errors, not rewriting**:
   wrong case/gender agreement, broken word order, leftover untranslated
   English text, a damaged placeholder.
3. The model returns fixes **only for lines where it actually found a
   problem** — the rest are simply not mentioned in the response and stay
   as the Argos draft, completely unchanged.

Since the model's job is only to find and fix a minority of lines rather
than rewrite everything, batches can be larger (20 vs. 12 in the regular
mode) without losing accuracy, and the model's response itself is shorter
(fewer fix-lines, not text for the whole mod), which speeds up large mods —
especially when Argos already handles most lines without serious errors.

Requires Argos enabled (i.e. without `--no-argos`) — `check` mode
inherently makes no sense without a draft to check against.

## How it works

- **`src/gui.py`** — a tkinter window (part of Python's standard library,
  nothing extra to install). Translation runs on a separate thread so the
  window doesn't freeze during translation.
- **`src/scanner.py`** — walks the mod, looking for
  `Languages/English/{Keyed,DefInjected,Strings}`. If `DefInjected` is
  missing (or doesn't cover all Def types), the missing part is filled in by
  extracting translatable fields directly from `Defs/*.xml`, with
  `Name`/`ParentName` inheritance resolved across all Defs files so labels
  and descriptions defined only in abstract parent defs aren't lost. Text
  injected into defs via `Patches/*.xml` (`PatchOperationAdd`/`Replace`/
  `Insert`, including operations nested in `Sequence`/`FindMod`/
  `Conditional`) is also picked up and takes priority over stale Defs/
  DefInjected text. Only the folders the game actually loads for the newest
  supported version are scanned: if the mod has a `LoadFolders.xml`, the
  program reads it the same way RimWorld itself does and only takes the
  current paths (including `IfModActive`-gated branches — there's no way to
  know the user's installed mods, and translating unused content is
  harmless, unlike missing translations for active content); if there's no
  such file, it picks the newest version by folder name (`1.0`, `1.1`,
  ...). Without this, mods that keep several versioned copies of `Defs`
  side by side would have all of them scanned at once, translating the same
  text multiple times for nothing. Found `Defs`/`Languages`/`Patches`
  folders are deduplicated by their actual path on disk — needed when the
  mod root and one of its own versioned subfolders (e.g. `1.6/`) both end
  up in the set of paths to scan and would otherwise overlap.
- **`src/rimworld_rules.py`** — a knowledge base of what counts as
  translatable text in RimWorld's XML mods versus technical data
  (defName/class-reference identifiers, placeholders `{0}`/`[founderName]`,
  enum-like `moduleTypeID`/`installableSegmentTypes`, `ruleKey->text` from
  ideology/quest grammar, hex colors and file paths). `xml_io.py` (what to
  extract from `Defs/*.xml`) and `translator.py` (what to protect from
  Argos/LLM during translation) consult these rules instead of duplicating
  the logic themselves. Every rule is annotated with the real mod it was
  found on — when a new bug shows up on a new mod, check here first for an
  existing category before adding yet another ad-hoc regex elsewhere in the
  code.
- **`src/patches.py`** — extracts translatable text from `Patches/*.xml`.
  Parses the common xpath shapes (`Defs/ThingDef[defName="X"]/field/subfield`,
  multiple defNames via `or`, `li[N]` indices); anything more exotic is
  skipped rather than risking a wrong DefInjected key.
- **`src/xml_io.py`** — reads/writes `LanguageData` XML while preserving key
  order and XML comments (section markers like `<!-- CABLES -->`), with
  character-exact control over escaping and BOM, matching the original
  mods. Also resolves `Name`/`ParentName` inheritance between def elements
  and reads/writes `Strings/*.txt` word lists.
- **`src/translator.py`** — translation through Argos Translate. Any
  placeholders (see `rimworld_rules.TRANSLATION_PLACEHOLDER_RE`) are never
  handed to the model as text — the string is cut into segments at their
  boundaries, only the text between them is translated, and the
  placeholders are put back verbatim (without this, Argos would sometimes
  translate the placeholder's contents too, occasionally into a random
  third language instead of the target one, or damage ideology grammar
  tokens like `[founder_pronoun]`, causing RimWorld to log a "Bad string
  pass" crash). For the same reason, after translating each segment the
  result is checked for CJK characters (there shouldn't be any when the
  target language is `ru`); if found, the translation is automatically
  retried once, which usually produces a normal result.
- **`src/glossary.py`** — a glossary of established RimWorld terms
  (hediff, psycast, xenotype, shuttle, ...), gathered from real community
  translations and aligned with the game's own official Russian
  terminology. Terms are protected from machine translation the same way
  placeholders are, and after Argos translates the surrounding text, the
  community-accepted term is substituted back in (preserving the original's
  capitalization).
- **`src/generator.py`** — assembles the output mod: `Languages/<Lang>/...`
  and `About/About.xml` (with `packageId`/`modDependencies`/`loadAfter`
  pointing at the original mod, following the pattern of the existing
  human-made translations in this collection). All user-supplied text is
  XML-escaped.
- **`src/llm_polish.py`** — the optional second pass through a local LLM
  (Ollama), see "LLM translation polishing" above. Also fetches the list of
  models installed in Ollama for the GUI/`--llm-model` dropdown, and
  validates that every placeholder/rich-text tag in the model's answer
  survived intact — a damaged answer is discarded in favor of the Argos
  draft.
- **`src/overrides.py`** — manual translation fixes that survive
  regeneration: keeps a snapshot of what the program itself wrote, diffs
  the current output files against it to detect user edits, and persists
  them to `manual_overrides.json` so they always win on future runs.
- **`src/incremental.py`** — incremental re-translation: compares the
  mod's current English strings against a snapshot in
  `.translation_cache.json` in the output folder and decides which keys
  can be reused from the existing translation without re-translating them.
- **`src/settings.py`** — persists GUI settings between runs in
  `%APPDATA%\RimWorldModTranslator\settings.json`.
- **`run_gui.py`** — the entry point for building the `.exe` with
  PyInstaller (see "Ready-made .exe" above). Also doubles as a CLI entry
  point when given command-line arguments.
- **`src/safe_print.py`** — a `print()` wrapper that doesn't crash when
  `sys.stdout`/`sys.stderr` are absent, which is the case for the `.exe`
  built with `--windowed` (no console, and writing to it would otherwise
  crash the app).
- **`src/log_setup.py`** — a file log, `translator.log`, next to the exe
  (or next to the project when run from source): logs scanning, every
  translated string, and LLM request timings to Ollama line by line —
  useful for telling a real hang apart from ordinary slow LLM polishing,
  and for attaching to a support request.

## Known limitations

- Argos Translate is a statistical NMT model, not an LLM: it doesn't
  "understand" the mod's context as a whole. The glossary inserts terms in
  their dictionary form without declension — unnoticeable for short
  `label` strings, but case agreement in longer description sentences can
  be imperfect. `--llm` partially compensates for this at the cost of
  speed (see above).
- Hardcoded strings baked into the mod's C#/DLL (rather than XML) aren't
  translated by this tool — same as most manual translations in this
  collection.
- Determining "is this translatable text vs. an identifier/number/path" in
  `rimworld_rules.is_translatable_value` is a content-based heuristic
  (spaces, letters, doesn't look like an ID/path/number), not a full
  XSD/schema parse of every Def type. It's reliable on simple Defs
  (ThingDef, RecipeDef, HediffDef, etc.), but complex structures like
  `QuestScriptDef` contain dozens of node-specific technical parameters
  (`points`, `chance`, and other quest-node-class-specific fields) that can
  occasionally slip past the heuristic and get translated if they happen
  to look like text. Known technical fields (`storeAs`, `tile`, `faction`,
  `driverClass`-like compound identifiers, `rulesStrings` prefixes) are
  already filtered out, but the list doesn't claim to be complete for
  every Def type — new cases can be added to
  `rimworld_rules.NEVER_TRANSLATABLE_TAGS` as they're found.

## Tests

```powershell
cd rimworld-mod-translator
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest tests/ -v
```

Tests in `tests/` are small synthetic fixtures (not real mods) covering
bugs found by hand during development: missing `DefInjected` with a partial
`Languages/English`, duplicated strings from nested versioned folders,
`LoadFolders.xml` support, `Patches/*.xml` extraction, `Name`/`ParentName`
inheritance, manual overrides surviving regeneration, batch-mode
translation memory, cooperative cancellation, automatic retry on
translation corruption into a random third language, gender/number
agreement for glossary adjectives, and the heuristic for detecting
translatable fields in `Defs/*.xml`. Two tests are intentionally marked
`xfail` — they document known limits of the agreement heuristic (genitive
plural, adjacency to a verb), not a bug to fix.

## License

[Apache License 2.0](LICENSE).
