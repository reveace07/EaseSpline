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
cp "$REPO_ROOT/ESpline/main.py"        "$APP_DIR/Contents/Resources/app/"
cp "$REPO_ROOT/ESpline/detector.py"    "$APP_DIR/Contents/Resources/app/"
cp "$REPO_ROOT/ESpline/debug_check.py" "$APP_DIR/Contents/Resources/app/"
cp "$REPO_ROOT/ESpline/repair_tool.py" "$APP_DIR/Contents/Resources/app/"
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
CONFIG_DIR="$HOME/Library/Application Support/ESpline"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10

mkdir -p "$CONFIG_DIR"

# ── Find Python 3.10+ ──
find_python() {
    # Check saved Python path first (set on previous launch)
    local saved="$CONFIG_DIR/python_path.txt"
    if [ -f "$saved" ]; then
        local saved_py
        saved_py=$(cat "$saved")
        if [ -f "$saved_py" ]; then
            local ver
            ver=$("$saved_py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            local major="${ver%%.*}"
            local minor="${ver#*.}"
            if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; then
                echo "$saved_py"
                return 0
            fi
        fi
    fi

    for cmd in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$cmd" &> /dev/null; then
            local exe
            exe=$(command -v "$cmd")
            local ver
            ver=$("$exe" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            local major="${ver%%.*}"
            local minor="${ver#*.}"
            if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; then
                echo "$exe"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON=$(find_python)

# ── No Python — auto-download and install the pkg, same as Windows ──
if [ -z "$PYTHON" ]; then
    PYTHON_PKG_URL="https://www.python.org/ftp/python/3.11.9/python-3.11.9-macos11.pkg"
    PYTHON_PKG="/tmp/python_espline_install.pkg"

    result=$(osascript -e "display dialog \"$APP_NAME needs Python 3.11, which is not installed.\n\nClick 'Install Automatically' and Python will be downloaded and installed for you (~45 MB).\n\nYou may be asked for your Mac password.\" buttons {\"Install Automatically\", \"Cancel\"} default button \"Install Automatically\" with icon note" 2>/dev/null)
    if ! echo "$result" | grep -q "Install Automatically"; then
        exit 1
    fi

    # Download with curl — uses macOS system SSL so no cert issues
    osascript -e "display dialog \"Downloading Python 3.11...\nThis will take a moment.\" giving up after 2" &>/dev/null
    if ! curl -L --silent --show-error "$PYTHON_PKG_URL" -o "$PYTHON_PKG" 2>/tmp/espline_curl_err; then
        osascript -e "display dialog \"Download failed.\n\nPlease check your internet connection and try again, or install Python manually from python.org.\" buttons {\"OK\"} with icon stop"
        exit 1
    fi

    # Install silently — prompts for password once via macOS
    if ! sudo installer -pkg "$PYTHON_PKG" -target / 2>/tmp/espline_install_err; then
        osascript -e "display dialog \"Python installation failed.\n\nPlease install Python 3.11 manually from python.org, then re-open $APP_NAME.\" buttons {\"OK\"} with icon stop"
        rm -f "$PYTHON_PKG"
        exit 1
    fi
    rm -f "$PYTHON_PKG"

    # Find the newly installed Python
    PYTHON=$(find_python)
    if [ -z "$PYTHON" ]; then
        # python.org pkg installs to a versioned path
        for p in /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 \
                  /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12; do
            if [ -f "$p" ]; then PYTHON="$p"; break; fi
        done
    fi

    if [ -z "$PYTHON" ]; then
        osascript -e "display dialog \"Python installed but could not be found.\n\nPlease re-open $APP_NAME.\" buttons {\"OK\"} with icon note"
        exit 1
    fi

    osascript -e "display dialog \"Python installed successfully!\n\n$APP_NAME will now continue.\" buttons {\"OK\"} default button \"OK\" with icon note" &>/dev/null
fi

# Save Python path so next launch is instant
echo "$PYTHON" > "$CONFIG_DIR/python_path.txt"

# Drop repair tool into config dir so users can run it if something breaks
cp "$SRC_DIR/repair_tool.py" "$CONFIG_DIR/repair_tool.py" 2>/dev/null || true

# ── Fix SSL certificates (macOS Python from python.org ships without certs) ──
# This was causing "not connected to internet" errors during pip installs and app use.
"$PYTHON" -m pip install --quiet certifi 2>/dev/null || true
SSL_CERT=$("$PYTHON" -c "import certifi; print(certifi.where())" 2>/dev/null || true)
if [ -n "$SSL_CERT" ] && [ -f "$SSL_CERT" ]; then
    export SSL_CERT_FILE="$SSL_CERT"
    export REQUESTS_CA_BUNDLE="$SSL_CERT"
fi

# ── Check PySide6 ──
if ! "$PYTHON" -c "from PySide6.QtWidgets import QApplication" 2>/dev/null; then
    result=$(osascript -e "display dialog \"PySide6 is required but not installed.\n\nClick 'Install Now' to install it automatically. This may take 2-3 minutes.\" buttons {\"Install Now\", \"Cancel\"} default button \"Install Now\" with icon note" 2>/dev/null)
    if ! echo "$result" | grep -q "Install Now"; then
        exit 1
    fi

    # Install PySide6, retry with --trusted-host on SSL failure
    if ! "$PYTHON" -m pip install PySide6 2>/dev/null; then
        "$PYTHON" -m pip install PySide6 \
            --trusted-host pypi.org \
            --trusted-host files.pythonhosted.org 2>/dev/null || true
    fi

    # Verify
    if ! "$PYTHON" -c "from PySide6.QtWidgets import QApplication" 2>/dev/null; then
        osascript -e "display dialog \"PySide6 installation failed.\n\nPlease open Terminal and run:\n\npip3 install PySide6\n\nThen re-open $APP_NAME.\" buttons {\"OK\"} default button \"OK\" with icon stop"
        exit 1
    fi
fi

# ── Set Resolve environment ──
export RESOLVE_SCRIPT_API="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
export RESOLVE_SCRIPT_LIB="/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
export PYTHONPATH="$SRC_DIR"

# ── Launch app (exec replaces shell so process is clean) ──
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
