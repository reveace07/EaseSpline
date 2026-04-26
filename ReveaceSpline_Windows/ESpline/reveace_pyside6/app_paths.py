"""App path utilities for PyInstaller compatibility."""
import os
import sys


def get_package_dir() -> str:
    """Directory where reveace_pyside6 package lives (bundled or source)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "reveace_pyside6")
    return os.path.dirname(os.path.abspath(__file__))


def get_data_dir() -> str:
    """Writable directory for user data (settings, favorites, caches)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    path = os.path.join(base, "ESpline")
    os.makedirs(path, exist_ok=True)
    return path


def init_data_files() -> None:
    """Copy bundled default data files from package dir to writable data dir on first run."""
    pkg = get_package_dir()
    data = get_data_dir()
    files = ["favorites.json", "favorites_folders.json", "section_presets.json", "theme_settings.json"]
    for fn in files:
        src = os.path.join(pkg, fn)
        dst = os.path.join(data, fn)
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                import shutil
                shutil.copy2(src, dst)
            except Exception:
                pass
