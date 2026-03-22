# -*- mode: python ; coding: utf-8 -*-
# ═══════════════════════════════════════════════
#  PaintingHeresy.spec
#  Uruchom: py -3.11 -m pyinstaller PaintingHeresy.spec
# ═══════════════════════════════════════════════

import os

block_cipher = None

# ── Pliki dołączane do .exe (zasoby wewnętrzne) ──────────────
datas = [
    ('templates', 'templates'),  # szablony HTML
]

if os.path.exists('Cinzel-Bold.ttf'):
    datas.append(('Cinzel-Bold.ttf', '.'))

# ── Ukryte importy ────────────────────────────────────────────
hiddenimports = [
    'webview',
    'webview.platforms.winforms',
    'flask',
    'flask.templating',
    'jinja2',
    'jinja2.ext',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'PIL.ImageFilter',
    'sqlite3',
    'threading',
    'urllib.request',
    'clr',
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'tkinter', 'PyQt5', 'PyQt6', 'wx',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PaintingHeresy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',
)
