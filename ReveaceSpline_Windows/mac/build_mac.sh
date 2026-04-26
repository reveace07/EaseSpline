#!/bin/bash
set -e

echo "========================================"
echo "  Rev EaseSpline — Mac Builder"
echo "  (PyInstaller — fully self-contained)"
echo "========================================"

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SRC_DIR/.." && pwd)"
APP_SRC="$REPO_ROOT/ESpline"

# ── [1/5] Build dependencies ─────────────────────────────────────────────────
echo ""
echo "[1/5] Installing build dependencies..."
pip install --upgrade pip -q
pip install pyinstaller PySide6 -q
echo "    OK"

# ── [2/5] Build app icon (SVG → ICNS) ────────────────────────────────────────
echo ""
echo "[2/5] Building app icon..."

SVG_SRC="$APP_SRC/reveace_pyside6/espline_logo.svg"
ICONSET_DIR="$SRC_DIR/ESpline.iconset"
ICNS_OUT="$SRC_DIR/espline_logo.icns"

rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"

convert_svg() {
    local out="$1" size="$2"
    if command -v rsvg-convert &>/dev/null; then
        rsvg-convert "$SVG_SRC" -w "$size" -h "$size" -o "$out" 2>/dev/null && return 0
    fi
    for p in /usr/local/bin/rsvg-convert /opt/homebrew/bin/rsvg-convert; do
        [ -f "$p" ] && "$p" "$SVG_SRC" -w "$size" -h "$size" -o "$out" 2>/dev/null && return 0
    done
    if command -v cairosvg &>/dev/null; then
        cairosvg "$SVG_SRC" -o "$out" -W "$size" -H "$size" 2>/dev/null && return 0
    fi
    return 1
}

SUCCESS=0
for size in 16 32 64 128 256 512 1024; do
    out="$ICONSET_DIR/icon_${size}x${size}.png"
    convert_svg "$out" "$size" && SUCCESS=$((SUCCESS+1)) || echo "    WARNING: could not generate ${size}x${size}"
done

if [ $SUCCESS -gt 0 ] && command -v iconutil &>/dev/null; then
    iconutil -c icns "$ICONSET_DIR" -o "$ICNS_OUT" 2>/dev/null
    echo "    Icon built: espline_logo.icns"
else
    echo "    WARNING: icon not built — app will use default icon"
fi
rm -rf "$ICONSET_DIR"

# ── [3/5] Run PyInstaller ─────────────────────────────────────────────────────
echo ""
echo "[3/5] Running PyInstaller (this takes a few minutes)..."
cd "$SRC_DIR"
rm -rf dist build
pyinstaller ESpline_Mac.spec --noconfirm --clean
echo "    OK"

# ── [4/5] Add Resolve launcher to zip ────────────────────────────────────────
echo ""
echo "[4/5] Preparing Resolve launcher..."
cp "$REPO_ROOT/dist/ESpline/EaseSpline_mac.py" "$SRC_DIR/dist/EaseSpline.py" 2>/dev/null || \
cp "$REPO_ROOT/ESpline/../mac/EaseSpline_mac.py" "$SRC_DIR/dist/EaseSpline.py" 2>/dev/null || true

cat > "$SRC_DIR/dist/install_resolve_menu.sh" << 'RESOLVE_INSTALLER'
#!/bin/bash
# Run this once to add ESpline to DaVinci Resolve's Scripts menu.
UTIL_DIR="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
mkdir -p "$UTIL_DIR"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/EaseSpline.py" "$UTIL_DIR/EaseSpline.py"
echo "Done — restart DaVinci Resolve and look in Workspace > Scripts > Utility > EaseSpline"
RESOLVE_INSTALLER
chmod +x "$SRC_DIR/dist/install_resolve_menu.sh"
echo "    OK"

# ── [5/5] Zip everything ─────────────────────────────────────────────────────
echo ""
echo "[5/5] Packaging ESpline_Mac.zip..."
cd "$SRC_DIR"
rm -f ESpline_Mac.zip
cd dist
zip -r "../ESpline_Mac.zip" ESpline.app EaseSpline.py install_resolve_menu.sh 2>/dev/null || \
zip -r "../ESpline_Mac.zip" ESpline.app
cd "$SRC_DIR"
echo "    Created: $SRC_DIR/ESpline_Mac.zip"

echo ""
echo "========================================"
echo "  Build Complete!"
echo "========================================"
echo ""
echo "  ESpline_Mac.zip contains:"
echo "    ESpline.app               ← drag to Applications, double-click"
echo "    EaseSpline.py             ← Resolve menu script"
echo "    install_resolve_menu.sh   ← run once to add Resolve menu entry"
echo ""
echo "  No Python required on user's Mac — everything is bundled."
echo ""
