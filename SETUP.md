# EaseSpline — Developer Setup Guide

> For your friend joining the project. This covers Windows development only.

---

## 1. Prerequisites

| Tool | Version | Download |
|------|---------|----------|
| Python | 3.10+ (64-bit) | https://python.org/downloads |
| Git | Any | https://git-scm.com/download/win |

**Important:** Install Python with "Add Python to PATH" checked.

---

## 2. Clone the Repository

```bash
git clone https://github.com/reveace07/EaseSpline.git
cd EaseSpline
```

**Use the whole `EaseSpline` folder** — not just the Windows subfolder. The repo contains:
- `ReveaceSpline_Windows/` — the actual Windows app
- `.github/workflows/` — CI/CD for auto-building releases
- `mac/` — Mac build scripts

---

## 3. Create a Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate
```

> Always activate `venv` before working. You'll see `(venv)` in your terminal.

---

## 4. Install Dependencies

```bash
pip install --upgrade pip
pip install PySide6 pyinstaller
```

That's it. The app itself only needs **PySide6** at runtime.

---

## 5. Run the App (Development Mode)

```bash
cd ReveaceSpline_Windows\ESpline
python main.py
```

This launches the app directly with console output for debugging.

---

## 6. Build the Distributables

There are **2 EXE files** to build. **Order matters.**

### Step A — Build the Launcher (`ESpline.exe`)

This is the windowed app users double-click. It spawns Python behind the scenes.

```bash
cd ReveaceSpline_Windows\setup_builder
pyinstaller ESpline_Launcher.spec --clean --noconfirm
```

Output: `dist/ESpline.exe` (~7 MB)

### Step B — Copy Launcher to Build Input

The installer bundles the launcher, so copy it first:

```bash
xcopy /Y dist\ESpline.exe ..\..\dist\
```

### Step C — Build the Installer (`ESpline_Setup.exe`)

This is the setup wizard users download. It auto-installs Python + PySide6 if missing.

```bash
pyinstaller ESpline_Setup.spec --clean --noconfirm
```

Output: `dist/ESpline_Setup.exe` (~15 MB)

---

## 7. Project Structure (What Matters)

```
EaseSpline/
├── .github/workflows/          # CI/CD — auto-build on GitHub
│   ├── build-windows.yml
│   ├── build-mac.yml
│   └── build-all.yml
├── ReveaceSpline_Windows/
│   ├── ESpline/                # App source code
│   │   ├── main.py             # Entry point
│   │   ├── detector.py         # Resolve connection
│   │   ├── debug_check.py      # Debug utilities
│   │   └── reveace_pyside6/    # All UI modules
│   │       ├── core.py
│   │       ├── gui_compact.py  # Main UI
│   │       ├── theme.py        # Theme engine (default: Lime)
│   │       ├── preset_library.py
│   │       ├── activation.py
│   │       └── ...
│   ├── setup_builder/          # Build scripts
│   │   ├── launcher.py         # Launcher source
│   │   ├── setup_main.py       # Installer source
│   │   ├── ESpline_Launcher.spec
│   │   ├── ESpline_Setup.spec
│   │   └── espline_logo.ico    # App icon
│   ├── mac/                    # Mac build scripts
│   └── ...
└── SETUP.md                    # This file
```

---

## 8. Quick Commands Cheat Sheet

```bash
# Activate venv
venv\Scripts\activate

# Run app (dev)
cd ReveaceSpline_Windows\ESpline && python main.py

# Build launcher
cd ReveaceSpline_Windows\setup_builder && pyinstaller ESpline_Launcher.spec --clean --noconfirm

# Build installer (AFTER launcher)
xcopy /Y dist\ESpline.exe ..\..\dist\
pyinstaller ESpline_Setup.spec --clean --noconfirm

# Check git status
git status

# Pull latest changes
git pull origin main
```

---

## 9. Troubleshooting

| Problem | Fix |
|---------|-----|
| `python: command not found` | Reinstall Python, check "Add to PATH" |
| `PySide6 not found` | Run `pip install PySide6` inside `venv` |
| `No module named pyinstaller` | Run `pip install pyinstaller` inside `venv` |
| Built EXE has no icon | Make sure `espline_logo.ico` exists in `setup_builder/` |
| Resolve not detected | Install DaVinci Resolve, or check `detector.py` |

---

## 10. What NOT to Commit

These are already in `.gitignore`, but don't add them manually:
- `venv/` or `.venv/`
- `build/` and `dist/` (local build artifacts)
- `__pycache__/` and `*.pyc`
- `node_modules/`
- User JSONs: `favorites.json`, `activation.json`, `theme_settings.json`

---

## 11. Making Changes & Pushing

```bash
git add .
git commit -m "Your change description"
git push origin main
```

If `git push` asks for a password, use a **GitHub Personal Access Token** (not your GitHub password). Create one at: https://github.com/settings/tokens

---

Done! DM if anything breaks.
