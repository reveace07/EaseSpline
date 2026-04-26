import os, subprocess, sys, traceback, platform, shutil

# DaVinci Resolve script — launches ESpline as a separate process.
# This avoids Resolve's bundled Python (often old/incompatible) from
# conflicting with PySide6.

if platform.system() != "Darwin":
    print("This script is for macOS only.")
    sys.exit(1)

_SEARCH_DIRS = [
    os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"),
]

path_file = None
for _d in _SEARCH_DIRS:
    _candidate = os.path.join(_d, "EaseSpline_path.txt")
    if os.path.exists(_candidate):
        path_file = _candidate
        break
if path_file is None:
    path_file = os.path.join(_SEARCH_DIRS[0], "EaseSpline_path.txt")

def log(msg):
    try:
        log_path = os.path.join(os.environ.get("TMPDIR", "/tmp"), "espline_launcher_log.txt")
        with open(log_path, "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass

try:
    log("=" * 50)
    log("Resolve launcher started (macOS)")

    app_dir = None
    if os.path.exists(path_file):
        with open(path_file, "r") as f:
            app_dir = f.read().strip()
        log(f"Read path from tracker: {app_dir}")

    if not app_dir or not os.path.exists(os.path.join(app_dir, "main.py")):
        log("ERROR: main.py not found via tracker")
        print("EaseSpline folder not found. Please run the installer first.")
        sys.exit(1)

    # Set up Resolve API environment
    resolve_api = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
    resolve_lib = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

    env = os.environ.copy()
    env["RESOLVE_SCRIPT_API"] = resolve_api
    env["RESOLVE_SCRIPT_LIB"] = resolve_lib
    env["PYTHONPATH"] = app_dir

    # Find the right Python executable
    python_txt = os.path.join(app_dir, "python_path.txt")
    python_exe = None
    if os.path.exists(python_txt):
        with open(python_txt) as _f:
            python_exe = _f.read().strip()
        log(f"Using saved Python: {python_exe}")

    if not python_exe or not os.path.exists(python_exe):
        for candidate in ("python3.14", "python3.13", "python3.12", "python3.11", "python3.10", "python3"):
            found = shutil.which(candidate)
            if found:
                python_exe = found
                break
        log(f"Searched Python: {python_exe}")

    if not python_exe or not os.path.exists(python_exe):
        log("ERROR: Python not found")
        print("Python 3.10+ not found. Please install it from python.org.")
        sys.exit(1)

    main_py = os.path.join(app_dir, "main.py")
    log(f"Launching: {python_exe} {main_py}")

    subprocess.Popen(
        [python_exe, main_py],
        env=env,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    log("Launch succeeded")

except Exception as e:
    log(f"FATAL ERROR: {e}")
    log(traceback.format_exc())
    print(f"EaseSpline launcher failed: {e}")
    sys.exit(1)
