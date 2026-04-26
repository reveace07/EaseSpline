#!/bin/bash
set -e

echo "========================================"
echo "  Rev EaseSpline — Mac Builder"
echo "  (Self-Installing App Bundle)"
echo "========================================"

APP_NAME="Rev EaseSpline"
APP_BUNDLE_NAME="ESpline"
BUNDLE_ID="com.reveace.espline"
VERSION="1.5.0"

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SRC_DIR/.." && pwd)"
APP_DIR="$SRC_DIR/${APP_BUNDLE_NAME}.app"

echo ""
echo "[1/7] Cleaning previous build..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources/app"
mkdir -p "$APP_DIR/Contents/Resources/app/reveace_pyside6"
echo "    OK"

echo ""
echo "[2/7] Copying app source files into bundle..."
cp "$REPO_ROOT/ESpline/main.py" "$APP_DIR/Contents/Resources/app/"
cp "$REPO_ROOT/ESpline/detector.py" "$APP_DIR/Contents/Resources/app/"
cp "$REPO_ROOT/ESpline/debug_check.py" "$APP_DIR/Contents/Resources/app/"
cp -R "$REPO_ROOT/ESpline/reveace_pyside6/"* "$APP_DIR/Contents/Resources/app/reveace_pyside6/"
echo "    OK"

echo ""
echo "[3/7] Building app icon..."
ICONSET_DIR="$SRC_DIR/ESpline.iconset"
rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"

SVG_SRC="$REPO_ROOT/ESpline/reveace_pyside6/espline_logo.svg"
SIZES=(16 32 64 128 256 512 1024)
SUCCESS=0

convert_svg() {
    local out="$1"
    local size="$2"

    if command -v rsvg-convert &> /dev/null; then
        rsvg-convert "$SVG_SRC" -w "$size" -h "$size" -o "$out" 2>/dev/null && return 0
    fi
    if [ -f /usr/local/bin/rsvg-convert ]; then
        /usr/local/bin/rsvg-convert "$SVG_SRC" -w "$size" -h "$size" -o "$out" 2>/dev/null && return 0
    fi
    if [ -f /opt/homebrew/bin/rsvg-convert ]; then
        /opt/homebrew/bin/rsvg-convert "$SVG_SRC" -w "$size" -h "$size" -o "$out" 2>/dev/null && return 0
    fi
    if command -v cairosvg &> /dev/null; then
        cairosvg "$SVG_SRC" -o "$out" -W "$size" -H "$size" 2>/dev/null && return 0
    fi
    if command -v qlmanage &> /dev/null; then
        local tmpdir=$(mktemp -d)
        qlmanage -t -s "$size" "$SVG_SRC" -o "$tmpdir" &>/dev/null
        local thumb="$tmpdir/$(basename "$SVG_SRC").png"
        if [ -f "$thumb" ]; then
            mv "$thumb" "$out" && return 0
        fi
    fi
    return 1
}

for size in "${SIZES[@]}"; do
    out="$ICONSET_DIR/icon_${size}x${size}.png"
    if convert_svg "$out" "$size"; then
        SUCCESS=$((SUCCESS + 1))
    else
        echo "    WARNING: Could not generate ${size}x${size} icon"
    fi
done

if [ $SUCCESS -gt 0 ] && command -v iconutil &> /dev/null; then
    iconutil -c icns "$ICONSET_DIR" -o "$APP_DIR/Contents/Resources/espline_logo.icns" 2>/dev/null
    echo "    Icon built: espline_logo.icns"
else
    echo "    WARNING: Could not build .icns automatically."
fi
rm -rf "$ICONSET_DIR"

echo ""
echo "[4/7] Writing Info.plist..."
cat > "$APP_DIR/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>ESpline</string>
    <key>CFBundleIdentifier</key>
    <string>$BUNDLE_ID</string>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleIconFile</key>
    <string>espline_logo</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
    <key>LSBackgroundOnly</key>
    <false/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
</dict>
</plist>
EOF
echo "    OK"

echo ""
echo "[5/7] Writing self-installing launcher..."
cat > "$APP_DIR/Contents/MacOS/ESpline" <<'LAUNCHER'
#!/bin/bash

APP_NAME="Rev EaseSpline"
BUNDLE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$BUNDLE_DIR/Resources/app"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10

# ── Find Python 3.10+ ──
find_python() {
    for cmd in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$cmd" &> /dev/null; then
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; then
                command -v "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON=$(find_python)

# ── No Python ──
if [ -z "$PYTHON" ]; then
    osascript -e "display dialog \"$APP_NAME requires Python 3.10 or newer.\n\nClick 'Download' to get Python from python.org, then re-open $APP_NAME.\" buttons {\"Download Python\", \"Cancel\"} default button \"Download Python\" with icon stop"
    if [ $? -eq 0 ]; then
        open "https://www.python.org/downloads/macos/"
    fi
    exit 1
fi

# ── Check PySide6 ──
if ! "$PYTHON" -c "from PySide6.QtWidgets import QApplication" 2>/dev/null; then
    osascript -e "display dialog \"PySide6 is required but not installed.\n\nClick OK to install it now. This may take 2-3 minutes.\" buttons {\"Install Now\", \"Cancel\"} default button \"Install Now\" with icon note"
    if [ $? -ne 0 ]; then
        exit 1
    fi

    # Show "installing" dialog
    osascript -e "display dialog \"Installing PySide6...\nPlease wait, this window will close automatically.\" giving up after 1" &>/dev/null

    # Install PySide6
    if ! "$PYTHON" -m pip install PySide6 2>/dev/null; then
        osascript -e "display dialog \"Failed to install PySide6.\n\nPlease open Terminal and run:\n\npip3 install PySide6\n\nThen re-open $APP_NAME.\" buttons {\"OK\"} default button \"OK\" with icon stop"
        exit 1
    fi

    # Verify it worked
    if ! "$PYTHON" -c "from PySide6.QtWidgets import QApplication" 2>/dev/null; then
        osascript -e "display dialog \"PySide6 installation failed.\n\nPlease install manually in Terminal:\n\npip3 install PySide6\" buttons {\"OK\"} default button \"OK\" with icon stop"
        exit 1
    fi
fi

# ── Set Resolve environment ──
export RESOLVE_SCRIPT_API="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
export RESOLVE_SCRIPT_LIB="/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
export PYTHONPATH="$SRC_DIR"

# ── Launch app ──
exec "$PYTHON" "$SRC_DIR/main.py"
LAUNCHER

chmod +x "$APP_DIR/Contents/MacOS/ESpline"
echo "    OK"

echo ""
echo "[6/7] Installing Resolve menu script..."
RESOLVE_UTIL_DIR="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
mkdir -p "$RESOLVE_UTIL_DIR"

# Write updated Resolve script that points inside the .app bundle
cat > "$RESOLVE_UTIL_DIR/EaseSpline.py" <<PYEOF
import os, subprocess, sys, traceback, platform, shutil

if platform.system() != "Darwin":
    print("This script is for macOS only.")
    sys.exit(1)

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

    # Look for the app bundle in common locations
    app_dir = None
    for base in [
        os.path.expanduser("~/Applications/ESpline.app"),
        "/Applications/ESpline.app",
    ]:
        candidate = os.path.join(base, "Contents/Resources/app")
        if os.path.exists(os.path.join(candidate, "main.py")):
            app_dir = candidate
            break

    if not app_dir:
        log("ERROR: ESpline.app not found in Applications")
        print("ESpline.app not found. Please install it in Applications.")
        sys.exit(1)

    log(f"Found app at: {app_dir}")

    # Find Python
    python_exe = None
    for candidate in ("python3.14", "python3.13", "python3.12", "python3.11", "python3.10", "python3"):
        found = shutil.which(candidate)
        if found:
            # Verify version
            try:
                ver_str = subprocess.run([found, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                    capture_output=True, text=True, timeout=5).stdout.strip()
                major, minor = map(int, ver_str.split(".")[:2])
                if major == 3 and minor >= 10:
                    python_exe = found
                    break
            except Exception:
                continue

    if not python_exe:
        log("ERROR: Python 3.10+ not found")
        print("Python 3.10+ not found. Please install it from python.org.")
        sys.exit(1)

    log(f"Using Python: {python_exe}")

    # Set up Resolve API environment
    resolve_api = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
    resolve_lib = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

    env = os.environ.copy()
    env["RESOLVE_SCRIPT_API"] = resolve_api
    env["RESOLVE_SCRIPT_LIB"] = resolve_lib
    env["PYTHONPATH"] = app_dir

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
PYEOF

echo "    Installed to: $RESOLVE_UTIL_DIR/EaseSpline.py"

echo ""
echo "[7/7] Packaging ESpline_Mac.zip..."
cd "$SRC_DIR"
rm -f ESpline_Mac.zip
zip -r ESpline_Mac.zip ESpline.app
echo "    Created: $SRC_DIR/ESpline_Mac.zip"

echo ""
echo "========================================"
echo "  Build Complete!"
echo "========================================"
echo ""
echo "Output: $SRC_DIR/ESpline_Mac.zip"
echo ""
echo "To install on any Mac:"
echo "  1. Unzip ESpline_Mac.zip"
echo "  2. Drag ESpline.app to Applications"
echo "  3. Double-click to launch"
echo "  4. If PySide6 is missing, the app will auto-install it"
echo "  5. If Python is missing, it will open python.org for you"
echo ""
echo "Note: First launch may show 'unidentified developer' warning."
echo "      Right-click the app → Open to bypass."
echo ""
