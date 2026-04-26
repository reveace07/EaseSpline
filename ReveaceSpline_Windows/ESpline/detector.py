"""
ESpline Location Detector
Run this if ESpline can't find its files, or if you moved the installation.
"""
import os
import sys

def _get_appdata_dir() -> str:
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ESpline")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/ESpline")
    return os.path.expanduser("~/.local/share/ESpline")

APPDATA_DIR   = _get_appdata_dir()
LOCATION_FILE = os.path.join(APPDATA_DIR, "espline_location.txt")
MARKER        = os.path.join("reveace_pyside6", "core.py")

def _all_drives():
    """Return all available drive roots on Windows."""
    drives = []
    if sys.platform == "win32":
        import string
        for letter in string.ascii_uppercase:
            d = f"{letter}:\\"
            if os.path.exists(d):
                drives.append(d)
    return drives

SEARCH_ROOTS = [
    APPDATA_DIR,
    os.path.dirname(os.path.abspath(__file__)),
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
]

# Common user folders
_home = os.path.expanduser("~")
for _sub in ["Desktop", "Downloads", "Documents", "ESpline"]:
    SEARCH_ROOTS.append(os.path.join(_home, _sub))

# All drives — check common install locations
if sys.platform == "win32":
    for _drive in _all_drives():
        for _sub in [
            "ESpline",
            "Program Files\\ESpline",
            "Program Files (x86)\\ESpline",
            os.path.join("Users", os.environ.get("USERNAME", ""), "ESpline"),
            os.path.join("Users", os.environ.get("USERNAME", ""), "AppData", "Roaming", "ESpline"),
        ]:
            SEARCH_ROOTS.append(os.path.join(_drive, _sub))


def find_espline():
    for root in SEARCH_ROOTS:
        if os.path.isfile(os.path.join(root, MARKER)):
            return root
    return None


def save(path):
    os.makedirs(APPDATA_DIR, exist_ok=True)
    with open(LOCATION_FILE, "w") as f:
        f.write(path.strip())


print()
print("  ESpline Location Detector")
print("  " + "─" * 40)

# Check currently saved path
current = None
if os.path.isfile(LOCATION_FILE):
    current = open(LOCATION_FILE).read().strip()
    if current:
        print(f"  Current saved path: {current}")
        valid = os.path.isfile(os.path.join(current, MARKER))
        print(f"  Status: {'✓ Valid' if valid else '✗ Files not found at this path'}")
    print()

# Auto-detect
found = find_espline()
if found:
    print(f"  Auto-detected: {found}")
else:
    print("  Could not auto-detect ESpline files.")

print()
print("  Options:")
print("  [Enter]     Use auto-detected path (or keep current if not found)")
print("  [Type path] Enter a custom path manually")
print("  [S]         Skip / cancel")
print()

try:
    choice = input("  > ").strip()
except (KeyboardInterrupt, EOFError):
    print("\n  Cancelled.")
    sys.exit(0)

if choice.lower() == "s":
    print("  Cancelled.")
    sys.exit(0)

if choice == "":
    path = found or current
    if not path:
        print("  No path available. Please type the path manually and run again.")
        sys.exit(1)
else:
    path = choice

if not os.path.isfile(os.path.join(path, MARKER)):
    print(f"  Warning: reveace_pyside6/core.py not found in: {path}")
    confirm = input("  Save anyway? [y/N] ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        sys.exit(0)

save(path)
print()
print(f"  Saved: {path}")
print(f"  Config: {LOCATION_FILE}")
print()
print("  Restart ESpline to apply.")
print()
input("  Press Enter to close...")
