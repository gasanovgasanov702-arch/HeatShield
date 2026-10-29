# -*- mode: python ; coding: utf-8 -*-

# copy_metadata сохраняет сведения пакета, которые OSMnx читает при импорте.
from PyInstaller.utils.hooks import copy_metadata

# Собираем Python-код, ресурсы карты и метаданные OSMnx для запуска без исходников.
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('ui/assets', 'ui/assets'), *copy_metadata('osmnx')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Poppler из окружения сборки принёс ICU 78; он конфликтует с Windows ICU для Qt.
a.binaries = [binary for binary in a.binaries if binary[0].lower() not in {'icuuc.dll', 'icudt78.dll'}]
# Упаковываем проверенные Python-модули в архив приложения.
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HeatShield',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='HeatShield',
)
