#!/usr/bin/env python3
"""
Rev EaseSpline — Repair Tool
Checks and fixes the ESpline environment automatically.

Usage:
    python3 repair_tool.py          # check everything and auto-fix
    python3 repair_tool.py --check  # report only, no changes
"""

import os, sys, subprocess, platform, shutil, struct, argparse

PLATFORM = platform.system()  # Darwin, Linux, Windows
APP_NAME = "Rev EaseSpline"
REQUIRED_PYTHON = (3, 10)
PYTHON_PKG_URL  = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-macos11.pkg"
PYTHON_EXE_URL  = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"

if PLATFORM == "Windows":
    INSTALL_DIR = os.path.join(os.environ.get("APPDATA", ""), "ESpline")
elif PLATFORM == "Darwin":
    INSTALL_DIR = os.path.expanduser("~/Library/Application Support/ESpline")
else:
    INSTALL_DIR = os.path.expanduser("~/.local/share/ESpline")

PYTHON_TXT   = os.path.join(INSTALL_DIR, "python_path.txt")
LOCATION_TXT = os.path.join(INSTALL_DIR, "espline_location.txt")

# ── Terminal colours (graceful fallback on Windows without ANSI) ─────────────
if PLATFORM == "Windows":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7)
        _ansi = True
    except Exception:
        _ansi = False
else:
    _ansi = True

G  = "\033[0;32m"  if _ansi else ""
Y  = "\033[0;33m"  if _ansi else ""
R  = "\033[0;31m"  if _ansi else ""
B  = "\033[0;34m"  if _ansi else ""
BD = "\033[1m"     if _ansi else ""
X  = "\033[0m"     if _ansi else ""

def ok(m):   print(f"  {G}✓{X}  {m}")
def warn(m): print(f"  {Y}⚠{X}  {m}")
def err(m):  print(f"  {R}✗{X}  {m}")
def info(m): print(f"  {B}→{X}  {m}")
def fixing(m): print(f"  {BD}[FIX]{X} {m}")
def section(m): print(f"\n{BD}{m}{X}")

# ── Helpers ──────────────────────────────────────────────────────────────────

def run(cmd, timeout=300):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

def pip_install(python_exe, *packages, extra_flags=None):
    flags = ["--no-warn-script-location"] + (extra_flags or [])
    r = run([python_exe, "-m", "pip", "install"] + list(packages) + flags)
    if r.returncode != 0:
        # Retry with SSL workaround
        r = run([python_exe, "-m", "pip", "install"] + list(packages) + flags +
                ["--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org"])
    return r.returncode == 0

def get_python_info(exe):
    try:
        r = run([exe, "-c",
            "import sys,struct; v=sys.version_info; "
            "print(f'{v.major}.{v.minor}.{v.micro}|{struct.calcsize(\"P\")*8}')"])
        if r.returncode != 0:
            return None, None
        parts = r.stdout.strip().split("|")
        return parts[0], int(parts[1])
    except Exception:
        return None, None

def find_python():
    candidates = ["python3.14","python3.13","python3.12","python3.11","python3.10",
                  "python3","python"]
    for cmd in candidates:
        exe = shutil.which(cmd)
        if not exe:
            continue
        ver, bits = get_python_info(exe)
        if not ver:
            continue
        major, minor = map(int, ver.split(".")[:2])
        if major == 3 and minor >= 10:
            if PLATFORM == "Windows" and bits != 64:
                continue  # Windows needs 64-bit
            return exe
    return None

def check_import(python_exe, module):
    r = run([python_exe, "-c", f"import {module}; print('ok')"])
    return r.returncode == 0 and "ok" in r.stdout

# ── Checks ───────────────────────────────────────────────────────────────────

class Check:
    def __init__(self, name):
        self.name   = name
        self.passed = False
        self.detail = ""

    def __bool__(self):
        return self.passed


def check_python_version(python_exe):
    c = Check("Python version")
    ver, bits = get_python_info(python_exe)
    if not ver:
        c.detail = "could not query version"
        return c
    major, minor = map(int, ver.split(".")[:2])
    if major < REQUIRED_PYTHON[0] or (major == REQUIRED_PYTHON[0] and minor < REQUIRED_PYTHON[1]):
        c.detail = f"{ver} is too old (need 3.10+)"
        return c
    if PLATFORM == "Windows" and bits != 64:
        c.detail = f"{ver} is 32-bit — PySide6 requires 64-bit"
        return c
    c.passed = True
    c.detail = f"{ver} ({bits}-bit)"
    return c


def check_pip(python_exe):
    c = Check("pip")
    r = run([python_exe, "-m", "pip", "--version"])
    c.passed = r.returncode == 0
    c.detail = r.stdout.strip().split("\n")[0] if c.passed else "not available"
    return c


def check_certifi(python_exe):
    c = Check("certifi (SSL certs)")
    r = run([python_exe, "-c", "import certifi; print(certifi.where())"])
    if r.returncode == 0:
        cert_file = r.stdout.strip()
        c.passed = os.path.isfile(cert_file)
        c.detail = cert_file if c.passed else "cert file missing"
    else:
        c.detail = "not installed"
    return c


def check_pyside6(python_exe):
    c = Check("PySide6")
    r = run([python_exe, "-c",
             "from PySide6.QtWidgets import QApplication; "
             "from PySide6 import __version__; print(__version__)"])
    if r.returncode == 0 and r.stdout.strip():
        c.passed = True
        c.detail = r.stdout.strip()
    else:
        c.detail = r.stderr.strip().split("\n")[0] if r.stderr.strip() else "not installed"
    return c


def check_app_files():
    c = Check("App files")
    main_py   = os.path.join(INSTALL_DIR, "main.py")
    pkg_dir   = os.path.join(INSTALL_DIR, "reveace_pyside6")
    missing   = [f for f in [main_py, pkg_dir] if not os.path.exists(f)]
    if missing:
        c.detail = "missing: " + ", ".join(os.path.basename(m) for m in missing)
    else:
        c.passed = True
        c.detail = INSTALL_DIR
    return c


def check_python_txt(python_exe):
    c = Check("python_path.txt")
    if not os.path.isfile(PYTHON_TXT):
        c.detail = "file missing"
        return c
    saved = open(PYTHON_TXT).read().strip()
    if saved == python_exe and os.path.isfile(saved):
        c.passed = True
        c.detail = saved
    else:
        c.detail = f"points to wrong path: {saved}"
    return c


def check_location_txt():
    c = Check("espline_location.txt")
    if not os.path.isfile(LOCATION_TXT):
        c.detail = "file missing"
        return c
    saved = open(LOCATION_TXT).read().strip()
    if saved == INSTALL_DIR and os.path.isdir(INSTALL_DIR):
        c.passed = True
        c.detail = saved
    else:
        c.detail = f"wrong path: {saved}"
    return c

# ── Fixes ────────────────────────────────────────────────────────────────────

def fix_python():
    """Install a known-good Python. Returns new exe path or None."""
    if PLATFORM == "Windows":
        import urllib.request, time
        fixing("Downloading Python 3.10.11 (64-bit)...")
        tmp = os.path.join(os.environ.get("TEMP",""), "python_espline.exe")
        try:
            req = urllib.request.Request(PYTHON_EXE_URL,
                                         headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(256*1024)
                        if not chunk: break
                        f.write(chunk)
            ok("Download complete")
        except Exception as e:
            err(f"Download failed: {e}")
            return None
        fixing("Installing Python silently...")
        r = run([tmp, "/quiet", "InstallAllUsers=0", "PrependPath=1",
                 "Include_test=0", "Include_launcher=1", "AssociateFiles=0"],
                timeout=300)
        if r.returncode != 0:
            err("Python install failed")
            return None
        time.sleep(2)
        likely = os.path.join(os.environ.get("LOCALAPPDATA",""),
                              "Programs","Python","Python310","python.exe")
        if os.path.isfile(likely):
            ok(f"Python installed: {likely}")
            return likely
        return find_python()

    elif PLATFORM == "Darwin":
        import urllib.request
        fixing("Downloading Python 3.11.9 pkg (~45 MB)...")
        tmp = "/tmp/python_espline.pkg"
        try:
            req = urllib.request.Request(PYTHON_PKG_URL,
                                         headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(256*1024)
                        if not chunk: break
                        f.write(chunk)
            ok("Download complete")
        except Exception as e:
            err(f"Download failed: {e}")
            return None
        fixing("Installing pkg (may ask for password)...")
        r = subprocess.run(["sudo","installer","-pkg",tmp,"-target","/"])
        os.remove(tmp)
        if r.returncode != 0:
            err("pkg install failed")
            return None
        ok("Python installed")
        for p in [
            "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11",
            "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
        ]:
            if os.path.isfile(p): return p
        return find_python()

    else:  # Linux
        for mgr, cmd in [
            ("apt-get",  ["sudo","apt-get","install","-y","python3","python3-pip","python3-venv"]),
            ("dnf",      ["sudo","dnf","install","-y","python3","python3-pip"]),
            ("pacman",   ["sudo","pacman","-S","--noconfirm","python","python-pip"]),
            ("zypper",   ["sudo","zypper","install","-y","python3","python3-pip"]),
            ("apk",      ["sudo","apk","add","python3","py3-pip"]),
        ]:
            if shutil.which(mgr):
                fixing(f"Installing Python via {mgr}...")
                r = subprocess.run(cmd)
                if r.returncode == 0:
                    ok("Python installed")
                    return find_python()
                err(f"{mgr} install failed")
                return None
        err("No supported package manager found")
        return None


def fix_pip(python_exe):
    fixing("Bootstrapping pip...")
    import urllib.request
    tmp = os.path.join(os.environ.get("TEMP") or "/tmp", "get-pip.py")
    try:
        urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", tmp)
        r = run([python_exe, tmp])
        return r.returncode == 0
    except Exception as e:
        err(f"pip bootstrap failed: {e}")
        return False


def fix_certifi(python_exe):
    fixing("Installing certifi...")
    return pip_install(python_exe, "certifi")


def fix_pyside6(python_exe):
    fixing("Installing PySide6 (this may take a few minutes)...")
    # Upgrade pip first to avoid old resolver issues
    run([python_exe, "-m", "pip", "install", "--upgrade", "pip", "-q"])
    return pip_install(python_exe, "PySide6")


def fix_python_txt(python_exe):
    fixing(f"Writing python_path.txt → {python_exe}")
    os.makedirs(INSTALL_DIR, exist_ok=True)
    with open(PYTHON_TXT, "w") as f:
        f.write(python_exe)


def fix_location_txt():
    fixing(f"Writing espline_location.txt → {INSTALL_DIR}")
    os.makedirs(INSTALL_DIR, exist_ok=True)
    with open(LOCATION_TXT, "w") as f:
        f.write(INSTALL_DIR)

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=f"{APP_NAME} — Repair Tool")
    parser.add_argument("--check", action="store_true",
                        help="Report status only, do not fix anything")
    args = parser.parse_args()
    check_only = args.check

    print(f"\n{BD}{'═'*52}{X}")
    print(f"{BD}  {APP_NAME} — Repair Tool{X}")
    print(f"{BD}{'═'*52}{X}\n")
    print(f"  Platform : {PLATFORM}")
    print(f"  Install  : {INSTALL_DIR}")
    print()

    issues = 0

    # ── 1. Find a working Python ──────────────────────────────────────────────
    section("[1/6] Python")
    python_exe = find_python()

    if not python_exe:
        err("No Python 3.10+ found")
        issues += 1
        if not check_only:
            python_exe = fix_python()
            if python_exe:
                ok(f"Python ready: {python_exe}")
            else:
                err("Could not install Python automatically.")
                err("Please install Python 3.10+ from https://www.python.org/")
                sys.exit(1)
        else:
            warn("Run without --check to auto-install")
    else:
        c = check_python_version(python_exe)
        if c:
            ok(f"Python {c.detail} at {python_exe}")
        else:
            err(f"Python issue: {c.detail}")
            issues += 1
            if not check_only:
                python_exe = fix_python()
                if python_exe:
                    ok(f"Python ready: {python_exe}")
                else:
                    sys.exit(1)

    if not python_exe:
        err("Cannot continue without Python.")
        sys.exit(1)

    # ── 2. pip ────────────────────────────────────────────────────────────────
    section("[2/6] pip")
    c = check_pip(python_exe)
    if c:
        ok(c.detail)
    else:
        err(c.detail)
        issues += 1
        if not check_only:
            if fix_pip(python_exe):
                ok("pip installed")
            else:
                err("Could not install pip — subsequent steps may fail")

    # ── 3. SSL certs (certifi) ────────────────────────────────────────────────
    section("[3/6] SSL certificates (certifi)")
    c = check_certifi(python_exe)
    if c:
        ok(c.detail)
    else:
        warn(c.detail)
        issues += 1
        if not check_only:
            if fix_certifi(python_exe):
                ok("certifi installed")
            else:
                warn("Could not install certifi — SSL errors may occur")

    # ── 4. PySide6 ────────────────────────────────────────────────────────────
    section("[4/6] PySide6")
    c = check_pyside6(python_exe)
    if c:
        ok(f"PySide6 {c.detail}")
    else:
        err(c.detail)
        issues += 1
        if not check_only:
            if fix_pyside6(python_exe):
                # Verify
                c2 = check_pyside6(python_exe)
                if c2:
                    ok(f"PySide6 {c2.detail} installed and verified")
                else:
                    err(f"PySide6 installed but still failing: {c2.detail}")
                    err("Try:  pip install --force-reinstall PySide6")
            else:
                err("PySide6 install failed")
                err("Try manually:  pip install PySide6")

    # ── 5. App files ──────────────────────────────────────────────────────────
    section("[5/6] App files")
    c = check_app_files()
    if c:
        ok(c.detail)
    else:
        err(c.detail)
        issues += 1
        warn("App files cannot be restored by the repair tool.")
        warn("Please re-run install.sh (Linux/Mac) or ESpline_Setup.exe (Windows).")

    # ── 6. Config files ───────────────────────────────────────────────────────
    section("[6/6] Config files")
    c1 = check_python_txt(python_exe)
    c2 = check_location_txt()

    if c1:
        ok(f"python_path.txt  →  {c1.detail}")
    else:
        warn(f"python_path.txt: {c1.detail}")
        issues += 1
        if not check_only:
            fix_python_txt(python_exe)
            ok("python_path.txt fixed")

    if c2:
        ok(f"espline_location.txt  →  {c2.detail}")
    else:
        warn(f"espline_location.txt: {c2.detail}")
        issues += 1
        if not check_only:
            fix_location_txt()
            ok("espline_location.txt fixed")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{BD}{'═'*52}{X}")
    if issues == 0:
        print(f"  {G}{BD}All checks passed — environment is healthy.{X}")
    elif check_only:
        print(f"  {Y}{BD}{issues} issue(s) found.{X}  Run without --check to auto-fix.")
    else:
        print(f"  {G}{BD}Repair complete.{X}  Re-launch {APP_NAME} to verify.")
    print(f"{BD}{'═'*52}{X}\n")

    if issues > 0 and not check_only:
        input("  Press Enter to close...")


if __name__ == "__main__":
    main()
