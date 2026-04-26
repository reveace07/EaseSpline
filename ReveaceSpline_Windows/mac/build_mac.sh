#!/bin/bash
set -e

echo "========================================"
echo "  Rev EaseSpline — Mac Builder"
echo "========================================"

APP_NAME="Rev EaseSpline"
BUNDLE_ID="com.reveace.espline"
INSTALL_DIR="$HOME/Library/Application Support/ESpline"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SRC_DIR/.." && pwd)"

echo ""
echo "[1/6] Checking Python..."

# Find best Python 3.10+
PYTHON=""
for cmd in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &> /dev/null; then
        ver=$($cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON=$(command -v "$cmd")
            echo "    Found Python $ver at $PYTHON"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "    ERROR: Python 3.10+ not found."
    echo "    Install it from https://www.python.org/downloads/macos/"
    exit 1
fi

echo ""
echo "[2/6] Checking PySide6..."
if $PYTHON -c "from PySide6.QtWidgets import QApplication" 2>/dev/null; then
    echo "    PySide6 already installed"
else
    echo "    Installing PySide6 (this may take a few minutes)..."
    $PYTHON -m pip install PySide6 --quiet
    echo "    PySide6 installed"
fi

echo ""
echo "[3/6] Copying app files..."
mkdir -p "$INSTALL_DIR"
cp "$REPO_ROOT/ESpline/main.py" "$INSTALL_DIR/"
cp "$REPO_ROOT/ESpline/detector.py" "$INSTALL_DIR/"
cp "$REPO_ROOT/ESpline/debug_check.py" "$INSTALL_DIR/"
cp -R "$REPO_ROOT/ESpline/reveace_pyside6" "$INSTALL_DIR/"
echo "$PYTHON" > "$INSTALL_DIR/python_path.txt"
echo "$INSTALL_DIR" > "$INSTALL_DIR/espline_location.txt"
echo "    Files copied to: $INSTALL_DIR"

echo ""
echo "[4/6] Building app icon..."
ICONSET_DIR="$SRC_DIR/ESpline.iconset"
mkdir -p "$ICONSET_DIR"

# Try multiple methods to convert SVG to PNGs, then build .icns
convert_svg() {
    local svg="$REPO_ROOT/ESpline/reveace_pyside6/espline_logo.svg"
    local out="$1"
    local size="$2"

    # Method 1: cairosvg
    if command -v cairosvg &> /dev/null; then
        cairosvg "$svg" -o "$out" -W "$size" -H "$size" 2>/dev/null && return 0
    fi

    # Method 2: rsvg-convert (librsvg) — most reliable, install via: brew install librsvg
    if command -v rsvg-convert &> /dev/null; then
        rsvg-convert "$svg" -w "$size" -h "$size" -o "$out" 2>/dev/null && return 0
    fi

    # Method 2b: rsvg-convert via brew path (GitHub Actions)
    if [ -f /usr/local/bin/rsvg-convert ]; then
        /usr/local/bin/rsvg-convert "$svg" -w "$size" -h "$size" -o "$out" 2>/dev/null && return 0
    fi
    if [ -f /opt/homebrew/bin/rsvg-convert ]; then
        /opt/homebrew/bin/rsvg-convert "$svg" -w "$size" -h "$size" -o "$out" 2>/dev/null && return 0
    fi

    # Method 3: qlmanage (macOS Quick Look)
    if command -v qlmanage &> /dev/null; then
        local tmpdir=$(mktemp -d)
        qlmanage -t -s "$size" "$svg" -o "$tmpdir" &>/dev/null
        local thumb="$tmpdir/$(basename "$svg").png"
        if [ -f "$thumb" ]; then
            mv "$thumb" "$out" && return 0
        fi
    fi

    # Method 4: sips with an intermediate PDF
    if command -v sips &> /dev/null; then
        local pdf="$SRC_DIR/tmp_icon.pdf"
        if [ -f "$pdf" ] || qlmanage -p "$svg" &>/dev/null; then
            sips -z "$size" "$size" "$svg" --out "$out" &>/dev/null && return 0
        fi
    fi

    return 1
}

# Build iconset
SIZES=(16 32 64 128 256 512 1024)
SUCCESS=0
for size in "${SIZES[@]}"; do
    out="$ICONSET_DIR/icon_${size}x${size}.png"
    if convert_svg "$out" "$size"; then
        SUCCESS=$((SUCCESS + 1))
    else
        echo "    WARNING: Could not generate ${size}x${size} icon"
    fi
done

if [ $SUCCESS -gt 0 ] && command -v iconutil &> /dev/null; then
    iconutil -c icns "$ICONSET_DIR" -o "$SRC_DIR/espline_logo.icns" 2>/dev/null
    echo "    Icon built: espline_logo.icns"
else
    echo "    WARNING: Could not build .icns automatically."
    echo "    Please convert espline_logo.svg to espline_logo.icns manually"
    echo "    and place it in: $SRC_DIR/"
fi

# Clean up iconset
rm -rf "$ICONSET_DIR"

echo ""
echo "[5/6] Building ESpline.app..."
APP_DIR="$SRC_DIR/ESpline.app"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Info.plist
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
    <string>1.5.0</string>
    <key>LSBackgroundOnly</key>
    <false/>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# Launcher script
cat > "$APP_DIR/Contents/MacOS/ESpline" <<'LAUNCHER'
#!/bin/bash
INSTALL_DIR="$HOME/Library/Application Support/ESpline"
PYTHON_TXT="$INSTALL_DIR/python_path.txt"

if [ -f "$PYTHON_TXT" ]; then
    PYTHON=$(cat "$PYTHON_TXT" | tr -d '[:space:]')
else
    PYTHON=$(which python3)
fi

if [ -z "$PYTHON" ] || [ ! -f "$PYTHON" ]; then
    osascript -e 'display dialog "Python not found. Please reinstall Rev EaseSpline." buttons {"OK"} default button "OK" with icon stop'
    exit 1
fi

if [ ! -f "$INSTALL_DIR/main.py" ]; then
    osascript -e 'display dialog "App files not found. Please run the installer first." buttons {"OK"} default button "OK" with icon stop'
    exit 1
fi

# Resolve API paths
export RESOLVE_SCRIPT_API="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
export RESOLVE_SCRIPT_LIB="/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
export PYTHONPATH="$INSTALL_DIR"

# Launch app (detached)
exec "$PYTHON" "$INSTALL_DIR/main.py" &
LAUNCHER

chmod +x "$APP_DIR/Contents/MacOS/ESpline"

# Copy icon if available
if [ -f "$SRC_DIR/espline_logo.icns" ]; then
    cp "$SRC_DIR/espline_logo.icns" "$APP_DIR/Contents/Resources/"
fi

# Copy to Applications
cp -R "$APP_DIR" "$HOME/Applications/"
# Also try /Applications if writable
if [ -w "/Applications" ]; then
    cp -R "$APP_DIR" "/Applications/"
    echo "    Installed to /Applications/ESpline.app"
else
    echo "    Installed to ~/Applications/ESpline.app"
    echo "    (To install system-wide, run: cp -R \"$APP_DIR\" /Applications/)"
fi

echo ""
echo "[6/6] Installing Resolve menu script..."
RESOLVE_UTIL_DIR="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
mkdir -p "$RESOLVE_UTIL_DIR"
cp "$SRC_DIR/EaseSpline.py" "$RESOLVE_UTIL_DIR/"
echo "$INSTALL_DIR" > "$RESOLVE_UTIL_DIR/EaseSpline_path.txt"
echo "    Installed to: $RESOLVE_UTIL_DIR/EaseSpline.py"

echo ""
echo "========================================"
echo "  Build Complete!"
echo "========================================"
echo ""
echo "Launch from:"
echo "  • Launchpad / Applications"
echo "  • Or inside Resolve: Workspace > Scripts > Utility > EaseSpline"
echo ""
echo "To distribute, zip the app:"
echo "  cd '$SRC_DIR' && zip -r ESpline_Mac.zip ESpline.app"
