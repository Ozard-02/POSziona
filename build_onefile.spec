# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onefile spec — produces a single static binary for Linux."""
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

base = os.path.abspath('.')

hiddenimports = collect_submodules('app')
hiddenimports += collect_submodules('webview')

datas = []
for subdir in ['app/ui/templates', 'app/ui/static']:
    src = os.path.join(base, subdir)
    if os.path.exists(src):
        datas.append((src, subdir))

datas += collect_data_files('webview')

a = Analysis(
    [os.path.join(base, 'scripts', 'entry_point.py')],
    pathex=[base],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    exclude_binaries=True,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='party-pos',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_dir=None,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
