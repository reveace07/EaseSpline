"""
Rev EaseSpline — Windows Setup Installer (Console)
Auto-downloads & installs 64-bit Python if missing/32-bit.
"""
import os, sys, subprocess, shutil, struct, time, urllib.request, datetime

APP_NAME = "Rev EaseSpline"
APP_VERSION = "1.5.0"
INSTALL_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ESpline")
PYTHON_TXT = os.path.join(INSTALL_DIR, "python_path.txt")
LOCATION_TXT = os.path.join(INSTALL_DIR, "espline_location.txt")

PYTHON_INSTALLER_URL = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
PYTHON_INSTALLER_NAME = "python-3.10.11-amd64.exe"

RESOLVE_UTILITY_DIRS = [
    os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
                 r"Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility"),
    os.path.join(os.environ.get("APPDATA", ""),
                 r"Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"),
]

def resource_path(rel):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

def banner():
    print("")
    print("  ╔══════════════════════════════════════════════════╗")
    print(f"  ║        {APP_NAME} — Setup Installer         ║")
    print(f"  ║                  Version {APP_VERSION}                     ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print("")

LOG_PATH = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "ESpline_Install.log")

def _log_write(level, msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  [{level}]  {msg}\n")
    except Exception:
        pass

def ok(msg):   print(f"    [OK]   {msg}"); _log_write("OK", msg)
def warn(msg): print(f"    [WARN] {msg}"); _log_write("WARN", msg)
def fail(msg): print(f"    [FAIL] {msg}"); _log_write("FAIL", msg)
def info(msg): print(f"    [INFO] {msg}"); _log_write("INFO", msg)

def get_python_info(exe):
    """Return (version_str, bits) or (None, None)."""
    try:
        out = subprocess.run([exe, "-c",
            "import sys, struct; v=sys.version_info; print(f'{v.major}.{v.minor}.{v.micro}|{struct.calcsize(\"P\")*8}')"],
            capture_output=True, text=True, timeout=10)
        if out.returncode != 0:
            return None, None
        parts = out.stdout.strip().split("|")
        if len(parts) != 2:
            return None, None
        return parts[0], int(parts[1])
    except Exception:
        return None, None

def find_python():
    """Find best Python 3.10+ 64-bit. Returns exe path or None."""
    candidates = ["python3.14", "python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"]
    best = None
    best_ver = (0, 0)
    for cmd in candidates:
        exe = shutil.which(cmd)
        if not exe:
            continue
        ver_str, bits = get_python_info(exe)
        if ver_str is None:
            continue
        major, minor = map(int, ver_str.split(".")[:2])
        if major == 3 and minor >= 10 and bits == 64:
            if best is None or (major, minor) > best_ver:
                best = exe
                best_ver = (major, minor)
    return best

def find_any_python():
    """Find any python to check if 32-bit exists."""
    for cmd in ["python3", "python"]:
        exe = shutil.which(cmd)
        if exe:
            return exe
    return None

def check_pyside6(python_exe):
    try:
        r = subprocess.run([python_exe, "-c", "from PySide6.QtWidgets import QApplication; print('ok')"],
            capture_output=True, text=True, timeout=15)
        return r.returncode == 0 and "ok" in r.stdout
    except Exception:
        return False

def install_pyside6(python_exe):
    print("  Installing PySide6... (this may take a few minutes)")
    try:
        r = subprocess.run([python_exe, "-m", "pip", "install", "PySide6", "--no-warn-script-location"],
            capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            print("  Upgrading pip and retrying...")
            subprocess.run([python_exe, "-m", "pip", "install", "--upgrade", "pip", "-q"],
                capture_output=True, timeout=60)
            r = subprocess.run([python_exe, "-m", "pip", "install", "PySide6", "--no-warn-script-location"],
                capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            ok("PySide6 installed")
            return True
        else:
            fail(f"PySide6 install failed: {r.stderr.strip()}")
            return False
    except Exception as e:
        fail(f"Error installing PySide6: {e}")
        return False

def download_file(url, dest, progress_fn=None):
    """Download with progress."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        total = int(response.headers.get('Content-Length', 0))
        downloaded = 0
        chunk_size = 256 * 1024
        with open(dest, 'wb') as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_fn and total:
                    progress_fn(downloaded, total)
    return dest

def install_python_64bit():
    """Download and silently install Python 3.10 64-bit. Returns exe path or None."""
    temp_dir = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "ESpline_Installer")
    os.makedirs(temp_dir, exist_ok=True)
    installer_path = os.path.join(temp_dir, PYTHON_INSTALLER_NAME)

    print("")
    info("Downloading Python 3.10.11 (64-bit)...")
    info(f"From: {PYTHON_INSTALLER_URL}")
    print("")

    def progress(done, total):
        pct = done * 100 // total
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r    [{bar}] {pct}%  ({done//1024//1024}MB / {total//1024//1024}MB)", end="", flush=True)

    try:
        download_file(PYTHON_INSTALLER_URL, installer_path, progress)
        print("")
        ok("Download complete")
    except Exception as e:
        print("")
        fail(f"Download failed: {e}")
        return None

    print("")
    info("Installing Python silently...")
    try:
        result = subprocess.run([
            installer_path,
            "/quiet", "InstallAllUsers=0", "PrependPath=1",
            "Include_test=0", "Include_launcher=1", "AssociateFiles=0"
        ], capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            fail(f"Python installer exited with code {result.returncode}")
            fail(result.stderr.strip())
            return None
        ok("Python installed")
    except Exception as e:
        fail(f"Python install failed: {e}")
        return None

    # Find the newly installed Python
    time.sleep(2)  # let PATH update settle
    likely_path = os.path.join(os.path.expanduser("~"), r"AppData\Local\Programs\Python\Python310", "python.exe")
    if os.path.exists(likely_path):
        return likely_path

    # Fallback: search in known locations
    for base in [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python310"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python311"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python312"),
        r"C:\Program Files\Python310",
        r"C:\Program Files\Python311",
        r"C:\Program Files\Python312",
    ]:
        exe = os.path.join(base, "python.exe")
        if os.path.exists(exe):
            return exe

    # Last resort: try PATH again
    return shutil.which("python") or shutil.which("python3")

def copy_app_files():
    os.makedirs(INSTALL_DIR, exist_ok=True)
    files_to_copy = [
        ("reveace_pyside6", "reveace_pyside6"),
        ("main.py", "."),
        ("detector.py", "."),
        ("debug_check.py", "."),
        ("EaseSpline.py", "."),
    ]
    for src_name, dst_sub in files_to_copy:
        src = resource_path(src_name)
        if not os.path.exists(src):
            continue
        dst = os.path.join(INSTALL_DIR, dst_sub)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            ok(f"Copied {src_name}/")
        else:
            shutil.copy2(src, dst)
            ok(f"Copied {src_name}")
    # Copy icon file for shortcuts
    ico_src = resource_path("espline_logo.ico")
    if os.path.exists(ico_src):
        shutil.copy2(ico_src, os.path.join(INSTALL_DIR, "espline_logo.ico"))
        ok("Copied icon file")
    with open(LOCATION_TXT, "w") as f:
        f.write(INSTALL_DIR)
    ok("Saved install location")

def install_resolve_launcher():
    src = os.path.join(INSTALL_DIR, "EaseSpline.py")
    if not os.path.exists(src):
        warn("EaseSpline.py not found — skipping Resolve menu")
        return False
    installed = False
    for d in RESOLVE_UTILITY_DIRS:
        try:
            os.makedirs(d, exist_ok=True)
            shutil.copy2(src, os.path.join(d, "EaseSpline.py"))
            with open(os.path.join(d, "EaseSpline_path.txt"), "w") as f:
                f.write(INSTALL_DIR)
            ok(f"Resolve menu entry: {d}")
            installed = True
            break
        except PermissionError:
            continue
        except Exception as e:
            warn(f"Could not write to {d}: {e}")
    return installed

def _create_shortcut_ps(lnk_path, target, working_dir, arguments="", icon_path=None, app_id=None):
    """Create a .lnk using PowerShell (avoids pywin32/winshell issues in PyInstaller).
    Sets icon, AppUserModelID, and working directory explicitly."""
    icon_cmd = f'$Shortcut.IconLocation = "{icon_path},0"' if icon_path else ""
    appid_cmd = f'$Shortcut.AppUserModelID = "{app_id}"' if app_id else ""
    ps = f'''
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut("{lnk_path}")
    $Shortcut.TargetPath = "{target}"
    $Shortcut.WorkingDirectory = "{working_dir}"
    $Shortcut.Arguments = "{arguments}"
    {icon_cmd}
    {appid_cmd}
    $Shortcut.Save()
    '''
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                       capture_output=True, text=True, timeout=30)
    return r.returncode == 0, r.stderr.strip()

def create_shortcuts(python_exe):
    """Create desktop/start-menu shortcuts and copy the launcher EXE."""
    # Copy bundled launcher EXE to install dir
    launcher_src = resource_path("ESpline.exe")
    launcher_dst = os.path.join(INSTALL_DIR, "ESpline.exe")
    if os.path.exists(launcher_src):
        try:
            shutil.copy2(launcher_src, launcher_dst)
            ok("Launcher EXE installed")
        except Exception as e:
            warn(f"Launcher copy failed: {e}")
    else:
        warn("Launcher EXE not found in installer bundle")

    # Determine target for shortcuts
    if os.path.exists(launcher_dst):
        shortcut_target = launcher_dst
        shortcut_args = ""
    else:
        pythonw = python_exe.replace("python.exe", "pythonw.exe")
        shortcut_target = pythonw if os.path.exists(pythonw) else python_exe
        shortcut_args = f'"{os.path.join(INSTALL_DIR, "main.py")}"'

    # Icon = the .ico file (Windows reads this more reliably than EXE-embedded icons)
    ico_path = os.path.join(INSTALL_DIR, "espline_logo.ico")
    icon_for_shortcut = ico_path if os.path.exists(ico_path) else None

    # Desktop shortcut
    desktop = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")
    try:
        os.makedirs(desktop, exist_ok=True)
        lnk = os.path.join(desktop, f"{APP_NAME}.lnk")
        success, err = _create_shortcut_ps(lnk, shortcut_target, INSTALL_DIR, shortcut_args,
                                           icon_path=icon_for_shortcut)
        if success:
            ok("Desktop shortcut created")
        else:
            warn(f"Desktop shortcut failed: {err}")
    except Exception as e:
        warn(f"Desktop shortcut skipped: {e}")

    # Start Menu shortcut
    start_menu = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
    try:
        os.makedirs(start_menu, exist_ok=True)
        lnk = os.path.join(start_menu, f"{APP_NAME}.lnk")
        success, err = _create_shortcut_ps(lnk, shortcut_target, INSTALL_DIR, shortcut_args,
                                           icon_path=icon_for_shortcut)
        if success:
            ok("Start Menu shortcut created")
        else:
            warn(f"Start Menu shortcut failed: {err}")
    except Exception as e:
        warn(f"Start Menu shortcut skipped: {e}")

def main():
    banner()

    # Step 1: Find or install Python
    print("  [1/5] Checking Python...")
    python_exe = find_python()

    if not python_exe:
        # Check if 32-bit Python exists
        any_py = find_any_python()
        if any_py:
            ver, bits = get_python_info(any_py)
            if ver and bits == 32:
                warn(f"Found Python {ver} but it's 32-bit — PySide6 requires 64-bit")
                info("Will auto-install 64-bit Python alongside it...")
            else:
                warn(f"Found Python {ver} but it's too old or not compatible")
                info("Will auto-install Python 3.10 (64-bit)...")
        else:
            warn("No Python found")
            info("Will auto-download and install Python 3.10 (64-bit)...")

        python_exe = install_python_64bit()
        if not python_exe:
            print("")
            fail("Could not install Python automatically.")
            print("  Please download and install manually from:")
            print("    https://www.python.org/downloads/release/python-31011/")
            print("  Make sure to select 'Windows installer (64-bit)'")
            print("")
            input("  Press Enter to close...")
            sys.exit(1)

        # Verify the new Python
        ver, bits = get_python_info(python_exe)
        ok(f"Now using Python {ver} ({bits}-bit) at {python_exe}")
    else:
        ver, bits = get_python_info(python_exe)
        ok(f"Found Python {ver} ({bits}-bit)")

    # Step 2: Check PySide6
    print("  [2/5] Checking PySide6...")
    has_pyside = check_pyside6(python_exe)
    if has_pyside:
        ok("PySide6 already installed")
    else:
        warn("PySide6 not found — will install")

    # Step 3: Install app files
    print("  [3/5] Installing app files...")
    os.makedirs(INSTALL_DIR, exist_ok=True)
    with open(PYTHON_TXT, "w") as f:
        f.write(python_exe)
    copy_app_files()

    # Step 4: Install PySide6 if needed
    if not has_pyside:
        print("  [4/5] Installing PySide6...")
        if not install_pyside6(python_exe):
            print("")
            fail("Installation failed.")
            print("  Try manually running:  pip install PySide6")
            print("")
            input("  Press Enter to close...")
            sys.exit(1)
    else:
        print("  [4/5] PySide6 already present — skipping")

    # Step 5: Shortcuts & Resolve
    print("  [5/5] Creating shortcuts & Resolve menu entry...")
    install_resolve_launcher()
    create_shortcuts(python_exe)

    print("")
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║           Installation Complete!                 ║")
    print("  ╠══════════════════════════════════════════════════╣")
    print("  ║  Launch from Desktop or Start Menu               ║")
    print("  ║  Or inside DaVinci Resolve:                      ║")
    print("  ║    Workspace > Scripts > Utility > EaseSpline    ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print("")
    info(f"Install log saved to: {LOG_PATH}")
    input("  Press Enter to close...")

if __name__ == "__main__":
    main()
