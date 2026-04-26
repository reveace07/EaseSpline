# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for ESpline Desktop Launcher
# Builds a windowed (no-console) single-file EXE that launches the app.

import os

SRC = os.path.abspath(SPECPATH)

a = Analysis(
    [os.path.join(SRC, 'launcher.py')],
    pathex=[SRC],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
        'PySide6.QtNetwork', 'PySide6.QtOpenGL', 'PySide6.QtQml',
        'numpy', 'pandas', 'matplotlib', 'PIL', 'cv2',
        'tkinter', 'unittest', 'pydoc', 'email', 'html', 'http',
        'xml', 'xmlrpc', 'lib2to3', 'distutils', 'pkg_resources',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ESpline',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windowed app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SRC, '..', 'ESpline', 'reveace_pyside6', 'espline_logo.ico') if os.path.exists(os.path.join(SRC, '..', 'ESpline', 'reveace_pyside6', 'espline_logo.ico')) else None,
)
