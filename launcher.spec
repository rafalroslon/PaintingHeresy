# -*- mode: python ; coding: utf-8 -*-
# ═══════════════════════════════════════════════
#  launcher.spec
#  Uruchom: py -3.11 -m pyinstaller launcher.spec
# ═══════════════════════════════════════════════

block_cipher = None

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'requests',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'pandas',
        'flask', 'PIL', 'webview',
    ],
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
    name='PaintingHeresy',      # To jest launcher — główny .exe który użytkownik odpala
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # Brak czarnego okna konsoli
    target_arch=None,
)
