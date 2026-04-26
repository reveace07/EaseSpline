# Rev EaseSpline — Mac Build Instructions

## What your friend needs
- A Mac running macOS 11 (Big Sur) or later
- Python 3.10+ installed (from https://www.python.org/downloads/macos/)
- DaVinci Resolve installed (optional, for the menu script)

## Steps (send these to your friend)

### 1. Get the source files
Your friend should download the `ReveaceSpline_Windows` folder from this repo.

### 2. Open Terminal
Navigate to the `mac` folder:
```bash
cd /path/to/ReveaceSpline_Windows/mac
```

### 3. Make the build script executable
```bash
chmod +x build_mac.sh
```

### 4. Run the build
```bash
./build_mac.sh
```

This will:
- Check for Python 3.10+ and PySide6
- Install PySide6 if missing
- Copy app files to `~/Library/Application Support/ESpline`
- Build `ESpline.app` (the native Mac app)
- Install the Resolve menu script
- Try to convert the SVG icon to `.icns`

### 5. Icon (if automatic conversion fails)
If the script can't convert the SVG automatically, your friend can:
- Open `espline_logo.svg` in any image editor or Preview
- Export as a square PNG (1024×1024)
- Or use an online SVG→ICNS converter
- Place the resulting `espline_logo.icns` in the `mac/` folder
- Re-run `./build_mac.sh`

### 6. Test it
- Launch from **Applications** or **Launchpad**
- Or inside DaVinci Resolve: **Workspace > Scripts > Utility > EaseSpline**

### 7. Package for distribution
```bash
cd /path/to/ReveaceSpline_Windows/mac
zip -r ESpline_Mac.zip ESpline.app
```

Then send `ESpline_Mac.zip` back to you.

## What gets installed on a user's Mac

| Location | What |
|---|---|
| `~/Applications/ESpline.app` | The app bundle (launcher) |
| `~/Library/Application Support/ESpline` | App source files (`main.py`, `reveace_pyside6/`, etc.) |
| `~/Library/Application Support/Blackmagic Design/.../Utility/EaseSpline.py` | Resolve menu script |

## Why this approach (small download)

Instead of bundling Python + PySide6 into a 200 MB app, the Mac build uses the **same pattern as Windows**:
- The `.app` is just a ~50 KB launcher script
- Python and PySide6 are installed once on the user's machine
- App updates only require replacing the small source files

## Troubleshooting

**"Python not found"**
→ Install Python 3.10+ from https://www.python.org/downloads/macos/

**"PySide6 install fails"**
→ Run: `python3 -m pip install --upgrade pip` then re-run `./build_mac.sh`

**"App won't open — unidentified developer"**
→ Right-click `ESpline.app` → **Open** (first time only)
