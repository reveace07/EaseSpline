# Rev EaseSpline — Mac Build Instructions

## What you need
- A Mac running **macOS 11 (Big Sur) or later**
- Python 3.10+ installed (for running the build script)
- DaVinci Resolve installed (optional, for the menu script)

## Quick Build (on a Mac)

1. **Copy the `ReveaceSpline_Windows/mac` folder** to the Mac
2. **Open Terminal** and navigate to it:
   ```bash
   cd /path/to/mac
   ```
3. **Make executable and run:**
   ```bash
   chmod +x build_mac.sh
   ./build_mac.sh
   ```
4. **Done!** You'll get `ESpline_Mac.zip` in the same folder.

## What the build does

- Copies all app source files **inside** the `.app` bundle (self-contained)
- Builds the app icon from SVG (if `rsvg-convert`, `cairosvg`, or `qlmanage` is available)
- Creates a **self-installing launcher** — on first run it:
  - Checks for Python 3.10+ (prompts to download if missing)
  - Checks for PySide6 (auto-installs via pip if missing)
  - Then launches the app
- Installs the Resolve menu script

## For End Users

Just send them `ESpline_Mac.zip`. They:

1. Unzip it
2. Drag `ESpline.app` to **Applications**
3. Double-click to launch
4. The app handles Python/PySide6 setup automatically

> **First launch security warning:** macOS may say "cannot be opened because the developer cannot be verified." Right-click the app → **Open** to bypass (only needed once).

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `python3: command not found` | Install Python 3.10+ from https://www.python.org/downloads/macos/ |
| Icon not generated | Install `librsvg`: `brew install librsvg` |
| `chmod: cannot access` | Make sure you're in the right folder: `cd /path/to/mac` |
| App won't open | Right-click → Open (first time only) |

## What gets installed on a user's Mac

| Location | What |
|---|---|
| `~/Applications/ESpline.app` or `/Applications/ESpline.app` | The app bundle (contains everything) |
| `~/Library/.../Fusion/Scripts/Utility/EaseSpline.py` | Resolve menu script |

## File size

The `.app` itself is tiny (~50 KB + source files ~500 KB) because it uses the system's Python. Much smaller than bundling Python + PySide6 (~200 MB).
