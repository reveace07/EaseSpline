#!/bin/bash
set -e

echo "========================================"
echo "  Rev EaseSpline — Mac Builder"
echo "  (Setup + lightweight launcher .app)"
echo "========================================"

APP_NAME="Rev EaseSpline"
APP_BUNDLE_NAME="ESpline"
BUNDLE_ID="com.reveace.espline"
VERSION="1.5.0"

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SRC_DIR/.." && pwd)"
APP_SRC="$REPO_ROOT/ESpline"
APP_DIR="$SRC_DIR/${APP_BUNDLE_NAME}.app"

# ── [1/6] Clean ───────────────────────────────────────────────────────────────
echo ""
echo "[1/6] Cleaning previous build..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources/app/reveace_pyside6"
echo "    OK"

# ── [2/6] Copy app source files into bundle ───────────────────────────────────
echo ""
echo "[2/6] Copying app source files..."
cp "$APP_SRC/main.py"        "$APP_DIR/Contents/Resources/app/"
cp "$APP_SRC/detector.py"    "$APP_DIR/Contents/Resources/app/"
cp "$APP_SRC/debug_check.py" "$APP_DIR/Contents/Resources/app/"
cp "$APP_SRC/repair_tool.py" "$APP_DIR/Contents/Resources/app/"
cp -R "$APP_SRC/reveace_pyside6/"* "$APP_DIR/Contents/Resources/app/reveace_pyside6/"
echo "    OK"

# ── [3/6] Build icon ──────────────────────────────────────────────────────────
echo ""
echo "[3/6] Building app icon..."
SVG_SRC="$APP_SRC/reveace_pyside6/espline_logo.svg"
ICONSET_DIR="$SRC_DIR/ESpline.iconset"
rm -rf "$ICONSET_DIR" && mkdir -p "$ICONSET_DIR"
SUCCESS=0
for size in 16 32 64 128 256 512 1024; do
    out="$ICONSET_DIR/icon_${size}x${size}.png"
    converted=0
    for rsvg in rsvg-convert /usr/local/bin/rsvg-convert /opt/homebrew/bin/rsvg-convert; do
        command -v "$rsvg" &>/dev/null || [ -f "$rsvg" ] || continue
        "$rsvg" "$SVG_SRC" -w "$size" -h "$size" -o "$out" 2>/dev/null && converted=1 && break
    done
    if [ $converted -eq 0 ] && command -v cairosvg &>/dev/null; then
        cairosvg "$SVG_SRC" -o "$out" -W "$size" -H "$size" 2>/dev/null && converted=1
    fi
    [ $converted -eq 1 ] && SUCCESS=$((SUCCESS+1))
done
if [ $SUCCESS -gt 0 ] && command -v iconutil &>/dev/null; then
    iconutil -c icns "$ICONSET_DIR" -o "$APP_DIR/Contents/Resources/espline_logo.icns" 2>/dev/null
    echo "    Icon built"
else
    echo "    WARNING: icon not built"
fi
rm -rf "$ICONSET_DIR"

# ── [4/6] Write Info.plist ────────────────────────────────────────────────────
echo ""
echo "[4/6] Writing Info.plist..."
cat > "$APP_DIR/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>      <string>ESpline</string>
    <key>CFBundleIdentifier</key>      <string>$BUNDLE_ID</string>
    <key>CFBundleName</key>            <string>$APP_BUNDLE_NAME</string>
    <key>CFBundleDisplayName</key>     <string>$APP_NAME</string>
    <key>CFBundleIconFile</key>        <string>espline_logo</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>CFBundleShortVersionString</key> <string>$VERSION</string>
    <key>CFBundleVersion</key>         <string>$VERSION</string>
    <key>LSBackgroundOnly</key>        <false/>
    <key>NSHighResolutionCapable</key> <true/>
    <key>LSMinimumSystemVersion</key>  <string>11.0</string>
</dict>
</plist>
EOF
echo "    OK"

# ── [5/6] Write launcher (tiny — no install logic, setup handles that) ────────
echo ""
echo "[5/6] Writing launcher..."
cat > "$APP_DIR/Contents/MacOS/ESpline" << 'LAUNCHER'
#!/bin/bash
APP_NAME="Rev EaseSpline"
BUNDLE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$BUNDLE_DIR/Resources/app"
CONFIG_DIR="$HOME/Library/Application Support/ESpline"
PYTHON_TXT="$CONFIG_DIR/python_path.txt"

# ── Check setup has been run ──────────────────────────────────────────────────
if [ ! -f "$PYTHON_TXT" ]; then
    osascript -e "display dialog \"$APP_NAME needs to be set up first.\n\nRun 'ESpline_Setup.command' from your Downloads folder, then re-open $APP_NAME.\" buttons {\"OK\"} default button \"OK\" with icon note"
    exit 1
fi

PYTHON=$(cat "$PYTHON_TXT")
if [ ! -f "$PYTHON" ]; then
    osascript -e "display dialog \"Python installation not found.\n\nPlease run 'ESpline_Setup.command' again to repair.\" buttons {\"OK\"} with icon stop"
    exit 1
fi

# ── Verify PySide6 still works ────────────────────────────────────────────────
if ! "$PYTHON" -c "from PySide6.QtWidgets import QApplication" 2>/dev/null; then
    osascript -e "display dialog \"PySide6 is missing or broken.\n\nRun 'ESpline_Setup.command' again to repair.\" buttons {\"OK\"} with icon stop"
    exit 1
fi

# ── Set SSL certs ─────────────────────────────────────────────────────────────
SSL_CERT=$("$PYTHON" -c "import certifi; print(certifi.where())" 2>/dev/null || true)
[ -n "$SSL_CERT" ] && [ -f "$SSL_CERT" ] && export SSL_CERT_FILE="$SSL_CERT" && export REQUESTS_CA_BUNDLE="$SSL_CERT"

# ── Set Resolve environment ───────────────────────────────────────────────────
export RESOLVE_SCRIPT_API="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
export RESOLVE_SCRIPT_LIB="/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

# ── Copy repair tool to config dir (so users can run it) ─────────────────────
cp "$SRC_DIR/repair_tool.py" "$CONFIG_DIR/repair_tool.py" 2>/dev/null || true

# ── Install app files if not present (first launch after setup) ───────────────
if [ ! -f "$CONFIG_DIR/main.py" ]; then
    cp "$SRC_DIR/main.py"        "$CONFIG_DIR/"
    cp "$SRC_DIR/detector.py"    "$CONFIG_DIR/" 2>/dev/null || true
    cp "$SRC_DIR/debug_check.py" "$CONFIG_DIR/" 2>/dev/null || true
    rm -rf "$CONFIG_DIR/reveace_pyside6"
    cp -R "$SRC_DIR/reveace_pyside6" "$CONFIG_DIR/"
    echo "$CONFIG_DIR" > "$CONFIG_DIR/espline_location.txt"
fi

export PYTHONPATH="$CONFIG_DIR"
exec "$PYTHON" "$CONFIG_DIR/main.py"
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/ESpline"
echo "    OK"

# ── [6/6] Write ESpline_Setup.command ────────────────────────────────────────
echo ""
echo "[6/6] Writing ESpline_Setup.command..."
cat > "$SRC_DIR/ESpline_Setup.command" << 'SETUP'
#!/bin/bash
# ═══════════════════════════════════════════════════════════
#   Rev EaseSpline — Mac Setup
#   Double-click to install. Run again anytime to repair.
# ═══════════════════════════════════════════════════════════

APP_NAME="Rev EaseSpline"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_SRC="$SCRIPT_DIR/ESpline.app/Contents/Resources/app"
CONFIG_DIR="$HOME/Library/Application Support/ESpline"
PYTHON_TXT="$CONFIG_DIR/python_path.txt"

BOLD='\033[1m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'
YELLOW='\033[0;33m'; RED='\033[0;31m'; X='\033[0m'

ok()   { echo -e "    ${GREEN}✓${X}  $1"; }
info() { echo -e "    ${BLUE}→${X}  $1"; }
warn() { echo -e "    ${YELLOW}⚠${X}  $1"; }
fail() { echo -e "\n  ${RED}✗  ERROR: $1${X}\n"; read -rp "  Press Enter to close..."; exit 1; }
step() { echo -e "\n  ${BOLD}[$1/5]${X} $2\n  ${BLUE}──────────────────────────────────────────${X}"; }

echo ""
echo -e "  ${BOLD}╔══════════════════════════════════════════════════╗${X}"
echo -e "  ${BOLD}║        Rev EaseSpline — Mac Setup                ║${X}"
echo -e "  ${BOLD}╚══════════════════════════════════════════════════╝${X}"
echo ""

mkdir -p "$CONFIG_DIR"

# ── [1/5] Find or install Python ─────────────────────────────────────────────
step 1 "Finding Python 3.10+"

is_good_python() {
    local exe="$1"
    [ -f "$exe" ] || return 1
    local ver
    ver=$("$exe" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    local major="${ver%%.*}" minor="${ver#*.}"
    [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]
}

find_python() {
    for cmd in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        command -v "$cmd" &>/dev/null && is_good_python "$(command -v "$cmd")" && command -v "$cmd" && return 0
    done
    for p in \
        /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 \
        /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3.10 \
        /opt/homebrew/bin/python3 \
        /usr/local/bin/python3.13 /usr/local/bin/python3.12 \
        /usr/local/bin/python3.11 /usr/local/bin/python3.10 \
        /usr/local/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
        /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
        /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 \
        /Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10; do
        is_good_python "$p" && echo "$p" && return 0
    done
    return 1
}

PYTHON=$(find_python)

if [ -z "$PYTHON" ]; then
    warn "Python 3.10+ not found — downloading installer..."
    PKG_URL="https://www.python.org/ftp/python/3.11.9/python-3.11.9-macos11.pkg"
    PKG_PATH="/tmp/python_espline.pkg"
    info "Downloading Python 3.11 (~45 MB)..."
    curl -L --progress-bar "$PKG_URL" -o "$PKG_PATH" || fail "Download failed. Install Python from python.org manually."
    info "Installing (will ask for your password)..."
    osascript -e "do shell script \"installer -pkg '$PKG_PATH' -target /\" with administrator privileges" \
        || fail "Installation failed. Install Python from python.org manually."
    rm -f "$PKG_PATH"
    PYTHON=$(find_python)
    [ -z "$PYTHON" ] && PYTHON=/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11
    [ -f "$PYTHON" ] && ok "Python installed: $PYTHON" || fail "Python installed but not found — please re-run setup."
fi

ok "Python: $PYTHON"
echo "$PYTHON" > "$PYTHON_TXT"

# ── [2/5] SSL certs + PySide6 ────────────────────────────────────────────────
step 2 "Installing required packages"

"$PYTHON" -m pip install --quiet certifi 2>/dev/null || true
SSL_CERT=$("$PYTHON" -c "import certifi; print(certifi.where())" 2>/dev/null || true)
[ -n "$SSL_CERT" ] && [ -f "$SSL_CERT" ] && export SSL_CERT_FILE="$SSL_CERT" && export REQUESTS_CA_BUNDLE="$SSL_CERT" && ok "SSL certificates configured"

if "$PYTHON" -c "from PySide6.QtWidgets import QApplication" 2>/dev/null; then
    ok "PySide6 already installed"
else
    info "Installing PySide6 (this may take a few minutes)..."
    "$PYTHON" -m pip install --upgrade pip -q 2>/dev/null || true
    if ! "$PYTHON" -m pip install PySide6 --no-warn-script-location; then
        info "Retrying with SSL workaround..."
        "$PYTHON" -m pip install PySide6 \
            --trusted-host pypi.org --trusted-host files.pythonhosted.org \
            || fail "PySide6 install failed. Run manually: pip3 install PySide6"
    fi
    "$PYTHON" -c "from PySide6.QtWidgets import QApplication" 2>/dev/null \
        && ok "PySide6 installed" \
        || fail "PySide6 installed but import failed. Try: pip3 install --force-reinstall PySide6"
fi

# ── [3/5] Copy app files ──────────────────────────────────────────────────────
step 3 "Installing app files"

[ -d "$APP_SRC" ] || fail "App source not found at: $APP_SRC\n  Make sure ESpline.app is in the same folder as this setup file."

rm -rf "$CONFIG_DIR/reveace_pyside6"
cp -R "$APP_SRC/reveace_pyside6" "$CONFIG_DIR/"
cp "$APP_SRC/main.py"        "$CONFIG_DIR/"
cp "$APP_SRC/detector.py"    "$CONFIG_DIR/" 2>/dev/null || true
cp "$APP_SRC/debug_check.py" "$CONFIG_DIR/" 2>/dev/null || true
cp "$APP_SRC/repair_tool.py" "$CONFIG_DIR/" 2>/dev/null || true
echo "$CONFIG_DIR" > "$CONFIG_DIR/espline_location.txt"
ok "App files installed to: $CONFIG_DIR"

# ── [4/5] Resolve launcher ────────────────────────────────────────────────────
step 4 "Setting up DaVinci Resolve menu entry"

RESOLVE_UTIL="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
if mkdir -p "$RESOLVE_UTIL" 2>/dev/null; then
    cat > "$RESOLVE_UTIL/EaseSpline.py" << 'PYEOF'
import os, subprocess, sys, shutil

APP_NAME = "ESpline"
for path in [f"/Applications/{APP_NAME}.app",
             f"{os.path.expanduser('~')}/Applications/{APP_NAME}.app"]:
    if os.path.exists(path):
        subprocess.Popen(["open", "-a", APP_NAME],
                         start_new_session=True,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        sys.exit(0)

print(f"{APP_NAME}.app not found in /Applications/")
print("Please drag ESpline.app to your Applications folder.")
sys.exit(1)
PYEOF
    ok "Resolve menu entry installed"
else
    warn "Could not install Resolve menu entry (permission denied)"
fi

# ── [5/5] Copy .app to Applications ─────────────────────────────────────────
step 5 "Installing ESpline.app to Applications"

APP_BUNDLE="$SCRIPT_DIR/ESpline.app"
APP_DEST="/Applications/ESpline.app"

if [ -d "$APP_BUNDLE" ]; then
    rm -rf "$APP_DEST"
    cp -R "$APP_BUNDLE" "$APP_DEST"
    ok "ESpline.app installed to /Applications/"
else
    warn "ESpline.app not found next to setup file — skipping"
fi

echo ""
echo -e "  ${BOLD}${GREEN}╔══════════════════════════════════════════════════╗${X}"
echo -e "  ${BOLD}${GREEN}║           Setup Complete!                        ║${X}"
echo -e "  ${BOLD}${GREEN}╠══════════════════════════════════════════════════╣${X}"
echo -e "  ${BOLD}${GREEN}║  ESpline is ready — open it from Applications    ║${X}"
echo -e "  ${BOLD}${GREEN}║  or search it with Spotlight (Cmd+Space)         ║${X}"
echo -e "  ${BOLD}${GREEN}╚══════════════════════════════════════════════════╝${X}"
echo ""
read -rp "  Press Enter to close..."
SETUP

chmod +x "$SRC_DIR/ESpline_Setup.command"
echo "    OK"

# ── Package ───────────────────────────────────────────────────────────────────
echo ""
echo "[Packaging] Creating ESpline_Mac.zip..."
cd "$SRC_DIR"
rm -f ESpline_Mac.zip
zip -r ESpline_Mac.zip ESpline.app ESpline_Setup.command
echo "    Created: $SRC_DIR/ESpline_Mac.zip"

echo ""
echo "========================================"
echo "  Build Complete!"
echo "========================================"
echo ""
echo "  ESpline_Mac.zip contains:"
echo "    ESpline_Setup.command  ← users double-click this FIRST"
echo "    ESpline.app            ← drag to Applications, double-click to run"
echo ""
echo "  App size: ~$(du -sh "$APP_DIR" 2>/dev/null | cut -f1) (no Python/PySide6 bundled)"
echo ""
