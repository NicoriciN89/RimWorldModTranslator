# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('argostranslate')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('ctranslate2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('sentencepiece')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('minisbd')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pymorphy3')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pymorphy3_dicts_ru')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Встроенный языковой пакет Argos (en->ru) — избавляет пользователя от
# скачивания ~200 МБ при первом запуске (см. src/translator.py). Там же
# лежит модель сегментации MiniSBD (bundled_packages/minisbd/en.onnx).
datas += [('bundled_packages', 'bundled_packages')]

# Заглушка stanza: argostranslate/sbd.py импортирует stanza безусловно, но
# при ARGOS_CHUNK_TYPE=MINISBD (принудительно задаётся в src/translator.py)
# она никогда не используется. Настоящая stanza тянет torch — ради одного
# мёртвого импорта сборка была на ~470 МБ тяжелее (torch 366 + spacy 78 +
# blis 22 + thinc 9). Заглушка кладётся папкой в _internal (он в sys.path
# замороженного приложения), а настоящие пакеты вырезаются через excludes.
datas += [('build_stubs/stanza', 'stanza')]


a = Analysis(
    ['run_gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # см. комментарий у заглушки stanza выше
        'stanza', 'torch', 'torchgen', 'torchaudio', 'torchvision',
        'spacy', 'spacy_legacy', 'spacy_loggers', 'thinc', 'blis',
        'preshed', 'cymem', 'murmurhash', 'sympy', 'networkx',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RimWorldModTranslator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX выключен: сжатые им exe имеют характерную сигнатуру секций,
    # которую антивирусы (особенно Defender) массово считают подозрительной
    # само по себе, независимо от содержимого — один из известных источников
    # ложных срабатываний на PyInstaller-сборках.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='RimWorldModTranslator',
)
