"""
ESpline Desktop Launcher — clean, simple, no console.
"""
import os, sys, subprocess, ctypes, platform

# Tell Windows this EXE owns the taskbar slot
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ESpline.ReveaceSpline.1")

_APP_DIR = os.path.join(os.environ.get("APPDATA", ""), "ESpline")
_MAIN_PY = os.path.join(_APP_DIR, "main.py")

# Find pythonw — prefer the exact one we installed, fallback to PATH
_PYTHONW = None
_py_txt = os.path.join(_APP_DIR, "python_path.txt")
if os.path.exists(_py_txt):
    with open(_py_txt) as f:
        _py = f.read().strip()
    if _py:
        # Try versioned pythonw first, then generic pythonw in same folder
        _dir = os.path.dirname(_py)
        _name = os.path.basename(_py)
        if _name.lower().startswith("python") and not _name.lower().startswith("pythonw"):
            _w = os.path.join(_dir, "pythonw" + _name[6:])
            if os.path.exists(_w):
                _PYTHONW = _w
        if not _PYTHONW:
            _w = os.path.join(_dir, "pythonw.exe")
            if os.path.exists(_w):
                _PYTHONW = _w

if not _PYTHONW:
    import shutil
    _PYTHONW = shutil.which("pythonw")

if not _PYTHONW or not os.path.exists(_PYTHONW):
    ctypes.windll.user32.MessageBoxW(0, "Python not found. Please reinstall ESpline.", "ESpline", 0x10)
    sys.exit(1)

if not os.path.exists(_MAIN_PY):
    ctypes.windll.user32.MessageBoxW(0, f"App not found at:\n{_MAIN_PY}", "ESpline", 0x10)
    sys.exit(1)

# Resolve API paths (needed by main.py)
env = os.environ.copy()
if platform.system() == "Windows":
    env["RESOLVE_SCRIPT_API"] = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), r"Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules")
    env["RESOLVE_SCRIPT_LIB"] = os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), r"Blackmagic Design\DaVinci Resolve\fusionscript.dll")
env["PYTHONPATH"] = _APP_DIR

# Launch and wait so Windows sees ESpline.exe as the owner
proc = subprocess.Popen([_PYTHONW, _MAIN_PY], env=env)
proc.wait()
sys.exit(proc.returncode)
