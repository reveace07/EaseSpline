import os, subprocess, sys, traceback, platform

# __file__ is not defined in Resolve's scripting environment.
# Look for EaseSpline_path.txt in all known launcher install locations.
if platform.system() == "Windows":
    _SEARCH_DIRS = [
        os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
                     r"Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility"),
        os.path.join(os.environ.get("APPDATA", ""),
                     r"Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"),
    ]
elif platform.system() == "Darwin":
    _SEARCH_DIRS = [
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility",
        os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"),
    ]
else:  # Linux
    _SEARCH_DIRS = [
        "/opt/resolve/Fusion/Scripts/Utility",
        os.path.expanduser("~/.local/share/DaVinciResolve/Fusion/Scripts/Utility"),
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
        log_path = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "espline_launcher_log.txt")
        with open(log_path, "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass

try:
    log("=" * 50)
    log("Resolve launcher started")

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
    if platform.system() == "Windows":
        resolve_api = os.path.join(
            os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
            r"Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"
        )
        resolve_lib = os.path.join(
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            r"Blackmagic Design\DaVinci Resolve\fusionscript.dll"
        )
    elif platform.system() == "Darwin":
        resolve_api = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
        resolve_lib = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
    else:  # Linux
        resolve_api = "/opt/resolve/Developer/Scripting/Modules"
        resolve_lib = "/opt/resolve/libs/Fusion/fusionscript.so"

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
        if platform.system() == "Windows":
            python_exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(python_exe):
                python_exe = os.path.join(os.path.dirname(sys.executable), "python.exe")
        else:
            for candidate in ("python3.14", "python3.13", "python3.12", "python3.11", "python3.10", "python3"):
                import shutil as _shutil
                found = _shutil.which(candidate)
                if found:
                    python_exe = found
                    break
        log(f"Fallback Python: {python_exe}")

    # On Windows: prefer pythonw.exe to suppress console window
    if platform.system() == "Windows":
        python_dir = os.path.dirname(python_exe)
        python_name = os.path.basename(python_exe)
        # Try versioned pythonw first (e.g. python3.10.exe -> pythonw3.10.exe)
        pythonw = None
        if python_name.lower().startswith("python") and not python_name.lower().startswith("pythonw"):
            versioned_w = os.path.join(python_dir, "pythonw" + python_name[6:])
            if os.path.exists(versioned_w):
                pythonw = versioned_w
        if not pythonw:
            generic_w = os.path.join(python_dir, "pythonw.exe")
            if os.path.exists(generic_w):
                pythonw = generic_w
        if pythonw and os.path.exists(pythonw):
            python_exe = pythonw
            log(f"Switched to pythonw: {python_exe}")

    log(f"Launching: {python_exe} {os.path.join(app_dir, 'main.py')}")

    if platform.system() == "Windows":
        subprocess.Popen(
            [python_exe, os.path.join(app_dir, "main.py")],
            env=env,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
    else:
        subprocess.Popen(
            [python_exe, os.path.join(app_dir, "main.py")],
            env=env,
            start_new_session=True,   # detach from Resolve's process group
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    log("Launch succeeded")

except Exception as e:
    log(f"FATAL ERROR: {e}")
    log(traceback.format_exc())
    print(f"EaseSpline launcher failed: {e}")
    sys.exit(1)
