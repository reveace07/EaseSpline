import os, sys, json, faulthandler, tempfile, atexit

# ── DaVinci Resolve Bridge Setup ─────────────────────────────────────────────
# Must be set BEFORE importing DaVinciResolveScript or anything Resolve-related.

# Default paths per platform
if sys.platform == "win32":
    _api = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
    _lib = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"

elif sys.platform == "darwin":
    _api = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
    _lib = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

else:  # Linux
    _api = "/opt/resolve/Developer/Scripting"
    _lib = "/opt/resolve/libs/Fusion/fusionscript.so"
    if not os.path.exists(_api):
        _api = "/home/resolve/Developer/Scripting"
        _lib = "/home/resolve/libs/Fusion/fusionscript.so"

# Override with user-saved path from settings (set via Browse in Settings tab)
def _load_saved_resolve_lib() -> str | None:
    try:
        if sys.platform == "win32":
            _base = os.environ.get("APPDATA", os.path.expanduser("~"))
        elif sys.platform == "darwin":
            _base = os.path.expanduser("~/Library/Application Support")
        else:
            _base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        settings = os.path.join(_base, "ReveaceSpline", "theme_settings.json")
        if os.path.isfile(settings):
            data = json.loads(open(settings).read())
            saved = data.get("resolve_path", "")
            if saved:
                saved = os.path.normpath(saved)
                # saved may be the dll itself or the folder
                if os.path.isfile(saved):
                    return saved
                dll = os.path.join(saved, "fusionscript.dll")
                if os.path.isfile(dll):
                    return dll
    except Exception:
        pass
    return None

_saved_lib = _load_saved_resolve_lib()
if _saved_lib:
    _lib = _saved_lib
    # Derive API path from the dll location (go up until we find the Scripting folder)
    _resolve_dir = os.path.dirname(_lib)
    _candidate_api = os.path.join(
        os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
        r"Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
    )
    if os.path.isdir(_candidate_api):
        _api = _candidate_api   # API stays standard — only lib changes

os.environ["RESOLVE_SCRIPT_API"] = _api
os.environ["RESOLVE_SCRIPT_LIB"] = _lib
sys.path.insert(0, os.path.join(_api, "Modules"))

# Ensure Resolve directory is on PATH so fusionscript.dll dependencies can be found
_resolve_dir = os.path.dirname(_lib)
if _resolve_dir and os.path.isdir(_resolve_dir):
    _path = os.environ.get("PATH", "")
    if _resolve_dir not in _path:
        os.environ["PATH"] = _resolve_dir + os.pathsep + _path
    # Python 3.8+ uses DLL load isolation — PATH alone is not enough for ctypes.
    # os.add_dll_directory() registers the folder so fusionscript.dll's own
    # dependencies (Qt, etc.) are found, preventing an access violation on import.
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(_resolve_dir)
        except Exception:
            pass
# ─────────────────────────────────────────────────────────────────────────────

# ── ESpline location (read from detector config, fall back to AppData default) ─
def _get_appdata_dir() -> str:
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ESpline")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/ESpline")
    return os.path.expanduser("~/.local/share/ESpline")

_APPDATA_DIR   = _get_appdata_dir()
_LOCATION_FILE = os.path.join(_APPDATA_DIR, "espline_location.txt")
_MARKER        = os.path.join("reveace_pyside6", "core.py")

def _resolve_project_root() -> str:
    """Return the folder containing reveace_pyside6/, using saved location if available."""
    # 1. Saved location from detector / installer
    try:
        if os.path.isfile(_LOCATION_FILE):
            saved = open(_LOCATION_FILE).read().strip()
            if saved and os.path.isfile(os.path.join(saved, _MARKER)):
                return saved
    except Exception:
        pass
    # 2. Default: AppData/ESpline (standard install)
    if os.path.isfile(os.path.join(_APPDATA_DIR, _MARKER)):
        return _APPDATA_DIR
    # 3. Same folder as this script (dev mode)
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.isfile(os.path.join(here, _MARKER)):
        return here
    # 4. Not found — return AppData path anyway so the import error is descriptive
    return _APPDATA_DIR

project_root = _resolve_project_root()
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Tell Windows this is its own app (not python.exe) so the taskbar shows our icon
if sys.platform == "win32":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ESpline.ReveaceSpline.1")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtCore import Qt
from PySide6.QtSvg import QSvgRenderer
from reveace_pyside6.core import ReveaceCore
from reveace_pyside6.gui_compact import ReveaceWindowCompact
from reveace_pyside6.app_paths import init_data_files
from reveace_pyside6.activation import check_activation
from reveace_pyside6.activation_dialog import ActivationDialog


def _make_app_icon() -> QIcon:
    """Render espline_logo.svg (v6, path-based E — no font) into a QIcon at multiple sizes."""
    svg_path = os.path.join(os.path.dirname(__file__), "reveace_pyside6", "espline_logo.svg")
    renderer = QSvgRenderer(svg_path)
    icon = QIcon()
    for size in (16, 32, 48, 64, 256):
        px = QPixmap(size, size)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(p)
        p.end()
        icon.addPixmap(px)
    return icon


# ── Crash log (faulthandler catches C++ level crashes) ───────────────────────
_CRASH_LOG = os.path.join(tempfile.gettempdir(), "espline_crash.log")
_crash_log_file = None

def _start_crash_log():
    global _crash_log_file
    try:
        _crash_log_file = open(_CRASH_LOG, "w")
        faulthandler.enable(_crash_log_file)
    except Exception:
        pass

def _stop_crash_log():
    try:
        faulthandler.disable()
        if _crash_log_file:
            _crash_log_file.close()
    except Exception:
        pass

def _read_last_crash_log() -> str:
    try:
        if os.path.isfile(_CRASH_LOG):
            content = open(_CRASH_LOG).read().strip()
            return content if content else ""
    except Exception:
        pass
    return ""

def _clear_crash_log():
    try:
        if os.path.isfile(_CRASH_LOG):
            open(_CRASH_LOG, "w").close()
    except Exception:
        pass

def _excepthook(exc_type, exc_value, exc_tb):
    import traceback
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        from PySide6.QtWidgets import QApplication
        if QApplication.instance():
            _startup_crash(tb, after_activation=True)
            return
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _excepthook

# ── WebEngine GPU flags ───────────────────────────────────────────────────────
# Read user preference from theme_settings.json before QApplication starts.
# Falls back to disabling GPU if previous run crashed.
def _load_gpu_setting() -> bool:
    """Return True if hardware acceleration should be enabled."""
    try:
        if sys.platform == "win32":
            _base = os.environ.get("APPDATA", os.path.expanduser("~"))
        elif sys.platform == "darwin":
            _base = os.path.expanduser("~/Library/Application Support")
        else:
            _base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        settings = os.path.join(_base, "ESpline", "theme_settings.json")
        if os.path.isfile(settings):
            data = json.loads(open(settings).read())
            return bool(data.get("hardware_acceleration", True))
    except Exception:
        pass
    return True

_prev_crashed = os.path.isfile(_CRASH_LOG) and bool(open(_CRASH_LOG).read().strip())
_gpu_enabled  = _load_gpu_setting() and not _prev_crashed
if _gpu_enabled:
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-software-rasterizer")
else:
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --disable-software-rasterizer")


def main():
    # ── Check if last run crashed at C++ level ────────────────────────────────
    last_crash = _read_last_crash_log()
    _clear_crash_log()
    _start_crash_log()
    atexit.register(_stop_crash_log)

    init_data_files()
    app = QApplication(sys.argv)
    app.setApplicationName("Rev EaseSpline")
    app.setStyle("Fusion")

    icon = _make_app_icon()
    app.setWindowIcon(icon)

    # ── Show crash report from previous run if any ────────────────────────────
    if last_crash:
        _startup_crash(
            f"[Previous run crashed at system level]\n\n{last_crash}",
            after_activation=False
        )

    # ── License check ─────────────────────────────────────────────────────────
    valid, reason = check_activation()
    if not valid:
        dlg = ActivationDialog(reason=reason)
        dlg.setWindowIcon(icon)
        if dlg.exec() != ActivationDialog.DialogCode.Accepted:
            sys.exit(0)
    # ─────────────────────────────────────────────────────────────────────────

    try:
        core = ReveaceCore()
        window = ReveaceWindowCompact(core)
        window.setWindowIcon(icon)
        window.show()
    except Exception:
        import traceback
        _startup_crash(traceback.format_exc(), after_activation=True)
        sys.exit(1)

    sys.exit(app.exec())


def _startup_crash(tb: str, after_activation: bool = False):
    """Called when the main window fails to launch. Shows a user-friendly diagnosis."""
    import subprocess
    from PySide6.QtWidgets import (QMessageBox, QPushButton, QDialog, QVBoxLayout,
                                   QTextEdit, QHBoxLayout, QLabel, QApplication)

    appdata = os.environ.get("APPDATA", "")
    python_txt = os.path.join(appdata, "ESpline", "python_path.txt")
    debug_script = os.path.join(appdata, "ESpline", "debug_check.py")

    # ── Auto-fix: missing PySide6 module ─────────────────────────────────────
    if "ModuleNotFoundError" in tb or "ImportError" in tb:
        try:
            python_exe = open(python_txt).read().strip() if os.path.isfile(python_txt) else sys.executable
            python_exe = python_exe.replace("pythonw.exe", "python.exe")
            fix_msg = QMessageBox()
            fix_msg.setWindowTitle("Rev EaseSpline — Fixing...")
            fix_msg.setIcon(QMessageBox.Icon.Information)
            fix_msg.setText("A missing package was detected.\nAttempting auto-fix — please wait...")
            fix_msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
            fix_msg.show()
            QApplication.processEvents()
            result = subprocess.run(
                [python_exe, "-m", "pip", "install", "--force-reinstall", "PySide6", "-q"],
                capture_output=True, timeout=300
            )
            fix_msg.close()
            if result.returncode == 0:
                done = QMessageBox()
                done.setWindowTitle("Rev EaseSpline")
                done.setIcon(QMessageBox.Icon.Information)
                done.setText("Auto-fix complete!\nPlease restart Rev EaseSpline.")
                done.exec()
                return
        except Exception:
            pass

    # ── Build human-readable diagnosis ────────────────────────────────────────
    steps = []
    if after_activation:
        steps.append("✓  Your license key was accepted successfully.")
        steps.append("")
        steps.append("✗  The app then crashed when loading the main window.")
        steps.append("")

    _missing_files = (
        "No module named 'reveace_pyside6'" in tb
        or "No module named 'core'" in tb
        or (not os.path.isfile(os.path.join(project_root, _MARKER)))
    )

    if _missing_files:
        steps += [
            "Possible cause: ESpline files could not be found.",
            f"  Expected location: {project_root}",
            f"  Location config:   {_LOCATION_FILE}",
            "",
            "  → Run the ESpline Detector to fix the path.",
            "  → Then restart ESpline.",
        ]
    elif "ssl" in tb.lower() or "certificate" in tb.lower():
        steps += [
            "Possible cause: SSL / certificate error.",
            "  → Try running the installer again (it includes certifi).",
            "  → Or run:  pip install certifi",
        ]
    elif "ModuleNotFoundError" in tb or "ImportError" in tb:
        steps += [
            "Possible cause: a required package is missing.",
            "  → Open a terminal and run:  pip install PySide6",
            "  → Then restart Rev EaseSpline.",
            "",
            "  If the problem persists, run the ESpline Detector",
            f"  to verify the install path is correct: {_LOCATION_FILE}",
        ]
    elif "PermissionError" in tb or "Access is denied" in tb:
        steps += [
            "Possible cause: file permission error.",
            "  → Try running as Administrator.",
            "  → Or re-run the installer.",
        ]
    else:
        steps += [
            "Something unexpected went wrong.",
            "  → Re-run the installer to repair the installation.",
            "  → If it keeps happening, send the report below to support.",
        ]

    steps += [
        "",
        "Support: babayaga37463@gmail.com",
        "  (click 'Copy Report' and paste it into your message)",
    ]

    # ── Run debug checker ─────────────────────────────────────────────────────
    report = tb
    if os.path.isfile(debug_script):
        try:
            python_exe = open(python_txt).read().strip() if os.path.isfile(python_txt) else sys.executable
            r = subprocess.run([python_exe, debug_script], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
            report = (r.stdout or "") + (r.stderr or "") + "\n\n--- Traceback ---\n" + tb
        except Exception:
            pass

    dlg = QDialog()
    dlg.setWindowTitle("Rev EaseSpline — Startup Error")
    dlg.setMinimumSize(540, 460)
    layout = QVBoxLayout(dlg)
    layout.setSpacing(8)
    layout.setContentsMargins(24, 20, 24, 20)

    title = QLabel("Rev EaseSpline couldn't start")
    title.setStyleSheet("font-size: 15px; font-weight: bold; color: #ff6b6b;")
    layout.addWidget(title)

    diagnosis = QLabel("\n".join(steps))
    diagnosis.setWordWrap(True)
    diagnosis.setStyleSheet("font-size: 12px; color: #e0e0e0; padding: 8px 0;")
    layout.addWidget(diagnosis)

    detail_lbl = QLabel("Technical details:")
    detail_lbl.setStyleSheet("font-size: 11px; color: #888;")
    layout.addWidget(detail_lbl)

    txt = QTextEdit()
    txt.setReadOnly(True)
    txt.setPlainText(report)
    txt.setStyleSheet("font-family: monospace; font-size: 10px; background: #1a1a1a; color: #aaa;")
    txt.setMaximumHeight(160)
    layout.addWidget(txt)

    btn_row = QHBoxLayout()
    copy_btn = QPushButton("Copy Report")
    copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(report))
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(copy_btn)
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)

    dlg.exec()


if __name__ == "__main__":
    main()
