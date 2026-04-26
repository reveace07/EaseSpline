# -*- mode: python ; coding: utf-8 -*-
import os

SPEC_DIR = os.path.abspath(SPECPATH)
SRC_DIR  = os.path.abspath(os.path.join(SPEC_DIR, '..', 'ESpline'))

a = Analysis(
    [os.path.join(SRC_DIR, 'main.py')],
    pathex=[SRC_DIR],
    binaries=[],
    datas=[
        (os.path.join(SRC_DIR, 'reveace_pyside6'), 'reveace_pyside6'),
        (os.path.join(SRC_DIR, 'detector.py'),    '.'),
        (os.path.join(SRC_DIR, 'debug_check.py'), '.'),
        (os.path.join(SRC_DIR, 'repair_tool.py'), '.'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'PySide6.QtNetwork',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel',
        'PySide6.QtPrintSupport',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy', 'pandas', 'matplotlib', 'PIL', 'cv2',
        'tensorflow', 'torch', 'tkinter',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ESpline',
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
    icon=os.path.join(SPEC_DIR, 'espline_logo.icns'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ESpline',
)

app = BUNDLE(
    coll,
    name='ESpline.app',
    icon=os.path.join(SPEC_DIR, 'espline_logo.icns'),
    bundle_identifier='com.reveace.espline',
    version='1.5.0',
    info_plist={
        'CFBundleDisplayName':       'Rev EaseSpline',
        'NSHighResolutionCapable':   True,
        'LSMinimumSystemVersion':    '11.0',
        'NSRequiresAquaSystemAppearance': False,
    },
)
