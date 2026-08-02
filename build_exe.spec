"""
PyInstaller spec for Party POS — standalone executable build.

Build on Linux:
    pyinstaller build_exe.spec

Build on Windows:
    pyinstaller build_exe.spec --windowed  (or --onefile)

For one-file builds, add --onefile to the command line.
For GUI-only (no console), add --windowed to the command line.

Notes:
  - Hidden imports include pywebview/webview submodules and the app package
  - collect_submodules grabs the 'app' package and all subpackages
  - add-data copies Flask templates and static files into the bundle
  - The entry_point.py script handles frozen mode path resolution
"""
# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# --- Collect Python submodules from the 'app' and 'webview' packages ---
hiddenimports = collect_submodules('app')
hiddenimports += collect_submodules('webview')

# --- Collect data files (templates, static assets) ---
datas = []
base = os.path.abspath('.')
for subdir in ['app/ui/templates', 'app/ui/static']:
    src = os.path.join(base, subdir)
    if os.path.exists(src):
        # dest: keep the same relative path so Flask's os.path.join works
        datas.append((src, subdir))

# --- Collect package data ---
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
    strip=False,
    upx=True,
    upx_dir=None,
    runtime_tmpdir=None,
    console=True,      # Console for debugging; override with --windowed on CLI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
