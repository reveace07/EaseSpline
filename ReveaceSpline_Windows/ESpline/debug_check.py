"""
ESpline Debug Checker
Run this to diagnose any installation or connection issues.
Usage: python debug_check.py
"""

import os
import sys

# Force UTF-8 output so box-drawing characters don't crash on cp1252 Windows consoles
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ── Helpers ──────────────────────────────────────────────────────────────────

PASS  = "[  OK  ]"
FAIL  = "[ FAIL ]"
WARN  = "[ WARN ]"
INFO  = "[ INFO ]"

results = []

def check(label, ok, detail="", warn_only=False):
    tag = WARN if (not ok and warn_only) else (PASS if ok else FAIL)
    line = f"  {tag}  {label}"
    if detail:
        line += f"\n           → {detail}"
    print(line)
    results.append((label, ok or warn_only))

def section(title):
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")

# ── Paths ─────────────────────────────────────────────────────────────────────

# Always check the installed location, not the exe's own temp folder
APP_DIR       = os.path.join(os.environ.get("APPDATA", ""), "ESpline")
PACKAGE_DIR   = os.path.join(APP_DIR, "reveace_pyside6")
MAIN_PY       = os.path.join(APP_DIR, "main.py")
LAUNCHER_SRC  = os.path.join(APP_DIR, "EaseSpline.py")
PYTHON_TXT    = os.path.join(APP_DIR, "python_path.txt")

RESOLVE_UTILITY_GLOBAL = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility"
RESOLVE_UTILITY_USER   = os.path.join(
    os.environ.get("APPDATA", ""),
    r"Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"
)
RESOLVE_API   = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
RESOLVE_DLL   = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"

# ─────────────────────────────────────────────────────────────────────────────
print()
print("  ╔═══════════════════════════════════════════════╗")
print("  ║        ESpline  —  Debug Checker              ║")
print("  ╚═══════════════════════════════════════════════╝")

# ── 1. Python ─────────────────────────────────────────────────────────────────
section("1. Python Environment")

check("Python executable", True, sys.executable)
check("Python version",
      sys.version_info >= (3, 10),
      f"{sys.version}",
      warn_only=sys.version_info < (3, 10))

# ── 2. App files ─────────────────────────────────────────────────────────────
section("2. App Files")

check("main.py exists",         os.path.isfile(MAIN_PY),       MAIN_PY)
check("reveace_pyside6/ exists", os.path.isdir(PACKAGE_DIR),   PACKAGE_DIR)

core_files = ["core.py", "gui_compact.py", "app_paths.py", "theme.py",
              "__init__.py", "preview_compact.html",
              "activation.py", "activation_dialog.py"]
import glob as _glob
for f in core_files:
    fp = os.path.join(PACKAGE_DIR, f)
    if os.path.isfile(fp):
        check(f"  {f}", True, fp)
    else:
        # Accept .pyc in __pycache__ as valid (source was stripped after install)
        stem = os.path.splitext(f)[0]
        pyc_pattern = os.path.join(PACKAGE_DIR, "__pycache__", f"{stem}.*.pyc")
        pyc_matches = _glob.glob(pyc_pattern)
        if pyc_matches:
            check(f"  {f}", True, f"(bytecode) {pyc_matches[0]}")
        else:
            check(f"  {f}", False, fp)

# ── 3. python_path.txt ───────────────────────────────────────────────────────
section("3. python_path.txt")

if os.path.isfile(PYTHON_TXT):
    with open(PYTHON_TXT) as fh:
        saved_py = fh.read().strip()
    check("python_path.txt exists", True, saved_py)
    check("Saved Python executable exists", os.path.isfile(saved_py), saved_py)
else:
    check("python_path.txt exists", False,
          f"Not found at {PYTHON_TXT} — run setup.bat first")

# ── 4. Resolve launcher ───────────────────────────────────────────────────────
section("4. Resolve Launcher")

check("Launcher source exists", os.path.isfile(LAUNCHER_SRC), LAUNCHER_SRC)

launcher_global = os.path.join(RESOLVE_UTILITY_GLOBAL, "EaseSpline.py")
launcher_user   = os.path.join(RESOLVE_UTILITY_USER,   "EaseSpline.py")
launcher_ok = os.path.isfile(launcher_global) or os.path.isfile(launcher_user)

if os.path.isfile(launcher_global):
    check("Launcher installed (global)", True, launcher_global)
elif os.path.isfile(launcher_user):
    check("Launcher installed (user)",   True, launcher_user)
else:
    check("Launcher installed in Resolve Scripts", False,
          f"Not found in:\n           → {launcher_global}\n           → {launcher_user}\n           Run ESpline_Setup.exe to install it.")

# Check path .txt written by setup
path_txt_global = os.path.join(RESOLVE_UTILITY_GLOBAL, "EaseSpline_path.txt")
path_txt_user   = os.path.join(RESOLVE_UTILITY_USER,   "EaseSpline_path.txt")
for pt in [path_txt_global, path_txt_user]:
    if os.path.isfile(pt):
        with open(pt) as fh:
            stored = fh.read().strip()
        check("ReveaceSpline_path.txt exists", True, f"{pt}\n           → points to: {stored}")
        check("Stored path matches app dir",
              os.path.normpath(stored) == os.path.normpath(APP_DIR),
              f"stored={stored}\n           actual ={APP_DIR}",
              warn_only=True)
        break
else:
    check("ReveaceSpline_path.txt exists", False,
          "Not found — setup.bat needs to run", warn_only=True)

# ── 5. DaVinci Resolve API ───────────────────────────────────────────────────
section("5. DaVinci Resolve API")

check("Resolve Scripting API folder", os.path.isdir(RESOLVE_API),  RESOLVE_API)
check("fusionscript.dll exists",      os.path.isfile(RESOLVE_DLL), RESOLVE_DLL)

modules_dir = os.path.join(RESOLVE_API, "Modules")
check("Scripting Modules folder", os.path.isdir(modules_dir), modules_dir)

dvr_script = os.path.join(modules_dir, "DaVinciResolveScript.py")
check("DaVinciResolveScript.py", os.path.isfile(dvr_script), dvr_script)

# ── 6. Python packages ────────────────────────────────────────────────────────
section("6. Python Packages")

packages = [
    ("PySide6",               "PySide6"),
    ("PySide6.QtWebEngine",   "PySide6.QtWebEngineWidgets"),
    ("PySide6.QtSvg",         "PySide6.QtSvg"),
    ("PySide6.QtWebChannel",  "PySide6.QtWebChannel"),
]
for label, mod in packages:
    try:
        __import__(mod)
        check(label, True)
    except ImportError as e:
        check(label, False, str(e))

# ── 7. Import app modules ─────────────────────────────────────────────────────
section("7. App Module Imports")

sys.path.insert(0, APP_DIR)
os.environ.setdefault("RESOLVE_SCRIPT_API", RESOLVE_API)
os.environ.setdefault("RESOLVE_SCRIPT_LIB", RESOLVE_DLL)
sys.path.insert(0, modules_dir)

modules_to_test = [
    ("reveace_pyside6.app_paths", "app_paths"),
    ("reveace_pyside6.theme",     "theme"),
    ("reveace_pyside6.core",      "core"),
    ("reveace_pyside6.gui_compact","gui_compact"),
]
for mod_path, label in modules_to_test:
    try:
        __import__(mod_path)
        check(f"import {label}", True)
    except Exception as e:
        check(f"import {label}", False, str(e))

# ── 8. Resolve connection (live) ──────────────────────────────────────────────
section("8. DaVinci Resolve Connection (Resolve must be open)")

try:
    import DaVinciResolveScript as dvr
    resolve = dvr.scriptapp("Resolve")
    if resolve:
        version = resolve.GetVersionString() if hasattr(resolve, "GetVersionString") else "unknown"
        check("Connected to Resolve", True, f"Version: {version}")
        try:
            fusion = resolve.Fusion()
            check("Fusion() accessible", fusion is not None)
            comp = fusion.GetCurrentComp() if fusion else None
            check("Active composition", comp is not None,
                  "No comp open — open a Fusion comp in Resolve" if not comp else "",
                  warn_only=True)
        except Exception as e:
            check("Fusion() accessible", False, str(e))
    else:
        check("Connected to Resolve", False,
              "Resolve returned None — is it open? Check Preferences > General > External scripting = Local")
except ImportError:
    check("DaVinciResolveScript importable", False,
          "Module not found — Resolve API path may be wrong or Resolve not installed")
except Exception as e:
    check("Connected to Resolve", False, str(e))

# ── Summary ───────────────────────────────────────────────────────────────────
section("Summary")

passed = sum(1 for _, ok in results if ok)
total  = len(results)
failed = [label for label, ok in results if not ok]

print(f"  {passed}/{total} checks passed")
if failed:
    print(f"\n  Issues to fix:")
    for f in failed:
        print(f"    ✗  {f}")
else:
    print("\n  Everything looks good!")

print()
input("  Press Enter to close...")
