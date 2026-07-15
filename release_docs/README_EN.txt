RimWorld Mod Translator
=======================

A local, fully offline translator for RimWorld mods. It never sends your
files anywhere over the internet — all translation happens on your own PC.

HOW TO RUN
----------
Go into the RimWorldModTranslator folder and double-click
RimWorldModTranslator.exe. No Python installation needed. Do not move the
exe out of this folder on its own — the _internal folder next to it holds
all the required libraries. If you want to move the program, move the whole
RimWorldModTranslator folder, not just the exe.

Windows SmartScreen may show a warning "Windows protected your PC" because
the exe isn't signed with a publisher's digital certificate (this is a
self-built utility, not software from a well-known vendor). To run it
anyway: click "More info" -> "Run anyway".

IF YOUR ANTIVIRUS FLAGS IT ("IS THIS A VIRUS?")
-------------------------------------------------
The program is built with PyInstaller, a standard open-source tool that
packages Python code into an exe — the same way many legitimate utilities
are built. Some antivirus engines occasionally flag such builds heuristically
just based on the packaging pattern, not because they found actual malicious
code (this is called a false positive). The program contains no networking
code that sends anything anywhere, except explicitly downloading Argos
Translate/Ollama language models, which you trigger yourself the first time
you use a new language.

An earlier build was checked on VirusTotal (a service that scans a file
with ~70 antivirus engines at once): 2 out of 68 engines flagged it (Bkav
Pro, SecureAge) — both are known for heightened heuristic sensitivity
specifically toward PyInstaller builds, with no specific threat name given
(a typical sign of a false positive rather than an actual finding). All
major antivirus engines (Kaspersky, ESET, BitDefender, Avast, Windows
Defender, CrowdStrike, Google, etc.) did not flag the file. Every new
version has a different file hash — feel free to check your exe yourself at
https://www.virustotal.com (upload the file and see the verdict from dozens
of antivirus engines at once) before running it. If your antivirus blocked
the file, add the program folder to your antivirus exclusions.

HOW TO USE
----------
1. Click "Обзор..." (Browse) next to "Папка мода" (Mod folder) — select the
   RimWorld mod folder (the one containing an About folder with About.xml).
2. Pick the target language from the dropdown.
3. Translation engine:
   - "Только Argos (быстро)" (Argos only, fast) — plain offline translation,
     takes seconds. Works right away, nothing extra to install.
   - "Argos + LLM-доработка" (Argos + LLM polish) and "Только LLM" (LLM
     only) — produce more grammatically natural translation (better
     case/gender agreement), but much slower (seconds per SINGLE string).
     Installing Ollama alone is NOT enough for this mode — you also need to
     download the actual language model (qwen2.5:7b) — it is open source
     and completely free, no subscription or payment required. The same
     goes for running models locally on your own PC through Ollama — it is
     also completely free and unlimited (the paid plans on ollama.com only
     apply to THEIR cloud service — we don't need that here):
       a) download and install Ollama: https://ollama.com/download
       b) open a command prompt (Win+R, type cmd, Enter) and run:
          ollama pull qwen2.5:7b
          (downloads ~4.7 GB, one time only, internet needed only for this
          step — the model itself is free, you only pay for your own
          internet traffic)
       c) the model will then show up in the "Модель Ollama" (Ollama model)
          dropdown in the app (or click "Обновить список" / Refresh list
          there)
     If you don't want to bother with Ollama, just use "Только Argos"
     (Argos only).
4. Click "Перевести" (Translate). The finished translated mod will appear
   in the output folder you specified (by default, an "output" folder next
   to the exe).
5. Install the resulting translated mod folder like any regular RimWorld
   mod — next to the original mod, below it in the mod list.

MOD QUEUE (TRANSLATING SEVERAL MODS AT ONCE)
----------------------------------------------
Use the "Добавить" (Add) button to collect several mod folders into the
queue list, then click "Перевести" (Translate) — the mods are processed one
after another. Identical strings across mods are translated only once (a
shared translation memory), and an error in one mod doesn't stop the rest.
If the queue is empty, the mod from the "Папка мода" (Mod folder) field is
translated as usual.

A running translation can be stopped with the "Отмена" (Cancel) button —
the partially translated result stays on disk.

MANUAL TRANSLATION FIXES
--------------------------
You can fix an awkward string right in the finished translation file
(XML/txt). On the next run the program notices your edit by itself, saves
it into manual_overrides.json next to the translation, and from then on
always uses your wording — even on a full re-translation. To undo a fix,
delete its line from manual_overrides.json.

RE-TRANSLATING / UPDATING A MOD
---------------------------------
If a mod was updated and you want to translate only the new strings instead
of redoing everything — check "Режим обновления" (Update mode) and point it
to the same output folder you used last time. Strings that are already
translated and unchanged (including any manual edits you made) will be left
untouched.

The window settings (folders, language, engine, checkboxes) are saved
between runs automatically.

BEING HONEST ABOUT TRANSLATION QUALITY
-----------------------------------------
This is machine translation, not perfect. The default mode (Argos) is fast
but sometimes produces awkward phrasing. LLM polishing fixes some grammar
issues (case/gender agreement), but it's not a silver bullet — both models
can mistranslate rare or made-up words. For important mods, a manual review
of the translation is recommended.
