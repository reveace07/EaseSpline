# -*- mode: python ; coding: utf-8 -*-
import os

SRC = os.path.abspath(SPECPATH)
BLOCK_CIPHER = None

a = Analysis(
    [os.path.join(SRC, 'setup_main.py')],
    pathex=[SRC],
    binaries=[],
    datas=[
        (os.path.join(SRC, '..', 'ESpline', 'reveace_pyside6'), 'reveace_pyside6'),
        (os.path.join(SRC, '..', 'ESpline', 'main.py'), '.'),
        (os.path.join(SRC, '..', 'ESpline', 'detector.py'), '.'),
        (os.path.join(SRC, '..', 'ESpline', 'debug_check.py'), '.'),
        (os.path.join(SRC, 'EaseSpline.py'), '.'),
        (os.path.join(SRC, '..', 'ESpline', 'repair_tool.py'), '.'),
        (os.path.join(SRC, '..', '..', 'dist', 'ESpline.exe'), '.'),
        (os.path.join(SRC, 'espline_logo.ico'), '.'),
    ],
    hiddenimports=[
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
        'PySide6.QtWebEngine',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'shiboken6',
        'numpy',
        'pandas',
        'matplotlib',
        'PIL',
        'cv2',
        'tensorflow',
        'torch',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=BLOCK_CIPHER,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=BLOCK_CIPHER)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ESpline_Setup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SRC, 'espline_logo.ico'),
)
