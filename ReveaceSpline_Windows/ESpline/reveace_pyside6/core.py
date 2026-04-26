"""
core.py — ReveaceSpline Brain
Holds all Resolve API logic, curve math, and SPL generation.
gui.py is just a remote control — it calls methods here.
"""

import sys
import os
import math
import re
import time
import json
import threading

# ── Resolve module path ──────────────────────────────────────
import platform
try:
    from .app_paths import get_data_dir, get_package_dir
except ImportError:
    from app_paths import get_data_dir, get_package_dir

def _get_resolve_paths():
    """Returns (API_PATH, [possible_LIB_paths]) based on OS."""
    sys_plat = platform.system()
    api_path = ""
    lib_paths = []

    if sys_plat == "Windows":
        prog_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        api_path = os.path.join(prog_data, r"Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules")
        lib_paths = [
            os.path.join(prog_files, r"Blackmagic Design\DaVinci Resolve"),
            os.path.join(prog_files, r"Blackmagic Design\DaVinci Resolve\Support")
        ]
    elif sys_plat == "Darwin": # Mac
        api_path = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
        lib_paths = [
            "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion",
            "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/MacOS",
            "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries"
        ]
    elif sys_plat == "Linux":
        api_path = "/opt/resolve/Developer/Scripting/Modules"
        lib_paths = [
            "/opt/resolve/libs",
            "/opt/resolve/bin",
            "/opt/resolve"
        ]
    
    return api_path, lib_paths

RESOLVE_SCRIPT_PATH, _possible_lib_paths = _get_resolve_paths()

def _get_resolve_path_from_settings():
    """Load Resolve path from theme settings if available."""
    try:
        for base in [get_data_dir(), get_package_dir()]:
            settings_file = os.path.join(base, "theme_settings.json")
            if os.path.exists(settings_file):
                import json
                with open(settings_file, 'r') as f:
                    data = json.load(f)
                    path = data.get('resolve_path', '')
                    if not path:
                        continue
                    if os.path.isfile(path):
                        return path
                    if os.path.isdir(path):
                        dll = os.path.join(path, "fusionscript.dll")
                        if os.path.isfile(dll):
                            return dll
                        support_dll = os.path.join(path, "Support", "fusionscript.dll")
                        if os.path.isfile(support_dll):
                            return support_dll
    except Exception:
        pass
    return ''

# Set required environment variables for DaVinci Resolve API
# These MUST be set before importing DaVinciResolveScript
if os.path.isdir(RESOLVE_SCRIPT_PATH):
    os.environ["RESOLVE_SCRIPT_API"] = RESOLVE_SCRIPT_PATH
    # Also add to sys.path for module import
    if RESOLVE_SCRIPT_PATH not in sys.path:
        sys.path.append(RESOLVE_SCRIPT_PATH)
    
    # Try to find and set RESOLVE_SCRIPT_LIB (path to fusionscript.dll)
    # Priority: 1) Already set in env, 2) From theme settings, 3) Default OS paths
    if "RESOLVE_SCRIPT_LIB" not in os.environ:
        # Check theme settings first
        settings_path = _get_resolve_path_from_settings()
        if settings_path and os.path.isfile(settings_path):
            os.environ["RESOLVE_SCRIPT_LIB"] = settings_path
        else:
            # Try default OS paths
            dll_name = "fusionscript.dll" if platform.system() == "Windows" else "fusionscript.so"
            for lib_path in _possible_lib_paths:
                test_file = os.path.join(lib_path, dll_name)
                if os.path.isfile(test_file):
                    os.environ["RESOLVE_SCRIPT_LIB"] = test_file
                    break

    # Fix for Python 3.8+ on Windows: Add the DLL directory so dependencies can be found
    if platform.system() == "Windows" and sys.version_info >= (3, 8):
        resolve_lib = os.environ.get("RESOLVE_SCRIPT_LIB")
        if resolve_lib and os.path.isfile(resolve_lib):
            try:
                os.add_dll_directory(os.path.dirname(resolve_lib))
            except Exception:
                pass

# ═══════════════════════════════════════════════════════════════
# PRESET DEFINITIONS
# ═══════════════════════════════════════════════════════════════

PRESETS = {
    "Linear":              {"cat": "Easing",   "tag": "constant velocity"},
    "Ease Out":            {"cat": "Easing",   "tag": "slow end"},
    "Ease In":             {"cat": "Easing",   "tag": "slow start"},
    "Ease In-Out":         {"cat": "Easing",   "tag": "smooth both"},
    "Ease Out (Cubic)":    {"cat": "Easing",   "tag": "strong stop"},
    "Ease In (Cubic)":     {"cat": "Easing",   "tag": "strong start"},
    "Ease In-Out (Cubic)": {"cat": "Easing",   "tag": "strong both"},
    "Ease Out (Expo)":     {"cat": "Easing",   "tag": "expo stop"},
    "Ease In (Expo)":      {"cat": "Easing",   "tag": "exponential"},
    "Circular Out":        {"cat": "Easing",   "tag": "circular end"},
    "Circular In":         {"cat": "Easing",   "tag": "circular start"},
    "Circular In-Out":     {"cat": "Easing",   "tag": "circular both"},
    "Back Out":            {"cat": "Easing",   "tag": "slight back end"},
    "Back In":             {"cat": "Easing",   "tag": "slight back start"},
    "Bounce Out":          {"cat": "Bounce",   "tag": "ball drop"},
    "Bounce In":           {"cat": "Bounce",   "tag": "build up"},
    "Elastic Out":         {"cat": "Elastic",  "tag": "spring to rest"},
    "Elastic In":          {"cat": "Elastic",  "tag": "spring build"},
    "Overshoot":           {"cat": "Dynamic",  "tag": "slight overshoot"},
    "Strong Overshoot":    {"cat": "Dynamic",  "tag": "heavy overshoot"},
    "Anticipate":          {"cat": "Dynamic",  "tag": "pull-back"},
    "Whip":                {"cat": "Dynamic",  "tag": "snap then settle"},
    "Double Back":         {"cat": "Dynamic",  "tag": "oscillate twice"},
    "Smooth Damp":         {"cat": "Dynamic",  "tag": "spring settle"},
    "Step In":             {"cat": "Step",     "tag": "cut at end"},
    "Step Out":            {"cat": "Step",     "tag": "cut at start"},
    "Step Mid":            {"cat": "Step",     "tag": "cut midpoint"},
    "S-Curve":             {"cat": "Special",  "tag": "smooth S"},
    "Reverse Ease":        {"cat": "Special",  "tag": "fast edges"},
    "Slow Mo":             {"cat": "Special",  "tag": "cinematic slow"},
    "Logarithmic":         {"cat": "Special",  "tag": "log curve"},
}


def _preset_keyframes(name: str, duration: float, start_val: float, end_val: float) -> list:
    """FIXED preset keyframes with correct bezier handles for accurate easing curves."""
    f = duration
    s = start_val
    e = end_val
    d = e - s

    kfs = {
        "Linear": [
            {"t": 0, "v": s},
            {"t": f, "v": e},
        ],
        # Quad easing: t^2 (ease in), 1-(1-t)^2 (ease out)
        # OPTIMIZED handles for accurate easing (see test_curve.py)
        # NOTE: Labels swapped to match visual curve direction
        "Ease Out": [
            {"t": 0,   "v": s, "rh": {"t": f * 0.0,  "v": s}},
            {"t": f,   "v": e, "lh": {"t": f * 0.33, "v": s + d * 0.33}},
        ],
        "Ease In": [
            {"t": 0,   "v": s, "rh": {"t": f * 0.67, "v": s + d * 0.67}},
            {"t": f,   "v": e, "lh": {"t": f * 1.0,  "v": e}},
        ],
        "Ease In-Out": [
            {"t": 0,   "v": s, "rh": {"t": f * 0.5,  "v": s}},
            {"t": f,   "v": e, "lh": {"t": f * 0.5,  "v": e}},
        ],
        "Ease Out (Cubic)": [
            {"t": 0,   "v": s, "rh": {"t": f * 0.0,  "v": s}},
            {"t": f,   "v": e, "lh": {"t": f * 0.25, "v": s + d * 0.25}},
        ],
        "Ease In (Cubic)": [
            {"t": 0,   "v": s, "rh": {"t": f * 0.75, "v": s + d * 0.75}},
            {"t": f,   "v": e, "lh": {"t": f * 1.0,  "v": e}},
        ],
        "Ease In-Out (Cubic)": [
            {"t": 0,   "v": s, "rh": {"t": f * 0.5,  "v": s}},        # RH horizontal at start
            {"t": f,   "v": e, "lh": {"t": f * 0.5,  "v": e}},        # LH horizontal at end
        ],
        # Expo easing: 2^(10*(t-1)) (ease in), 1-2^(-10t) (ease out)
        # NOTE: Labels swapped to match visual curve direction
        "Ease Out (Expo)": [
            {"t": 0,   "v": s, "rh": {"t": f * 0.0,  "v": s}},        # RH at start
            {"t": f,   "v": e, "lh": {"t": f * 0.2,  "v": s + d * 0.1}},  # LH very early for sharp end
        ],
        "Ease In (Expo)": [
            {"t": 0,   "v": s, "rh": {"t": f * 0.8,  "v": s + d * 0.9}},  # RH very late for sharp start
            {"t": f,   "v": e, "lh": {"t": f * 1.0,  "v": e}},        # LH at end
        ],
        "Overshoot": [
            {"t": 0,        "v": s,          "rh": {"t": f * 0.4,  "v": s}},
            {"t": f * 0.8,  "v": e + d * 0.15, "lh": {"t": f * 0.6,  "v": e + d * 0.15},
                                                   "rh": {"t": f * 0.9,  "v": e + d * 0.15}},
            {"t": f,        "v": e,          "lh": {"t": f * 0.95, "v": e}},
        ],
        "Anticipate": [
            {"t": 0,        "v": s,           "rh": {"t": f * 0.05, "v": s}},
            {"t": f * 0.2,  "v": s - d * 0.1, "lh": {"t": f * 0.1,  "v": s - d * 0.1},
                                                   "rh": {"t": f * 0.3,  "v": s - d * 0.1}},
            {"t": f,        "v": e,           "lh": {"t": f * 0.7,  "v": e}},
        ],
        "Step In":  [
            {"t": 0,              "v": s},
            {"t": max(1, f - 1),  "v": s},
            {"t": f,              "v": e},
        ],
        "Step Out": [
            {"t": 0, "v": s},
            {"t": 1, "v": e},
            {"t": f, "v": e},
        ],
        "Step Mid": [
            {"t": 0,                         "v": s},
            {"t": max(1, round(f * .5) - 1), "v": s},
            {"t": round(f * .5),             "v": e},
            {"t": f,                         "v": e},
        ],
        "S-Curve": [
            {"t": 0,       "v": s,           "rh": {"t": f * 0.2,  "v": s + d * 0.05}},
            {"t": f * 0.5, "v": s + d * 0.5, "lh": {"t": f * 0.3,  "v": s + d * 0.2},
                                              "rh": {"t": f * 0.7,  "v": s + d * 0.8}},
            {"t": f,       "v": e,           "lh": {"t": f * 0.8,  "v": e - d * 0.05}},
        ],
        "Reverse Ease": [
            {"t": 0,       "v": s,           "rh": {"t": f * 0.2,  "v": s + d * 0.6}},
            {"t": f * 0.5, "v": s + d * 0.5, "lh": {"t": f * 0.4,  "v": s + d * 0.48},
                                              "rh": {"t": f * 0.6,  "v": s + d * 0.52}},
            {"t": f,       "v": e,           "lh": {"t": f * 0.8,  "v": e - d * 0.6}},
        ],
        # Circular easing: based on sqrt(1-t^2) for smooth circular motion feel
        "Circular Out": [
            {"t": 0,   "v": s, "rh": {"t": f * 0.0,  "v": s}},
            {"t": f,   "v": e, "lh": {"t": f * 0.4,  "v": s + d * 0.2}},
        ],
        "Circular In": [
            {"t": 0,   "v": s, "rh": {"t": f * 0.6,  "v": s + d * 0.8}},
            {"t": f,   "v": e, "lh": {"t": f * 1.0,  "v": e}},
        ],
        "Circular In-Out": [
            {"t": 0,       "v": s,           "rh": {"t": f * 0.0,  "v": s}},
            {"t": f * 0.5, "v": s + d * 0.5, "lh": {"t": f * 0.3,  "v": s + d * 0.2},
                                              "rh": {"t": f * 0.7,  "v": s + d * 0.8}},
            {"t": f,       "v": e,           "lh": {"t": f * 1.0,  "v": e}},
        ],
        # Back easing: slight overshoot with pull-back
        # NOTE: Labels swapped to match visual curve direction
        "Back Out": [
            {"t": 0,   "v": s, "rh": {"t": f * 0.0,  "v": s - d * 0.1}},
            {"t": f,   "v": e, "lh": {"t": f * 0.3,  "v": s + d * 0.5}},
        ],
        "Back In": [
            {"t": 0,   "v": s, "rh": {"t": f * 0.7,  "v": s + d * 0.5}},
            {"t": f,   "v": e, "lh": {"t": f * 1.0,  "v": e + d * 0.1}},
        ],
        # Dynamic curves - enhanced motion
        "Strong Overshoot": [
            {"t": 0,        "v": s,          "rh": {"t": f * 0.35, "v": s}},
            {"t": f * 0.7,  "v": e + d * 0.3, "lh": {"t": f * 0.5,  "v": e + d * 0.3},
                                                   "rh": {"t": f * 0.85, "v": e + d * 0.3}},
            {"t": f,        "v": e,          "lh": {"t": f * 0.95, "v": e}},
        ],
        "Whip": [
            {"t": 0,        "v": s,          "rh": {"t": f * 0.05, "v": s - d * 0.2}},
            {"t": f * 0.3,  "v": e + d * 0.15, "lh": {"t": f * 0.15, "v": e + d * 0.15},
                                                   "rh": {"t": f * 0.5,  "v": e + d * 0.15}},
            {"t": f,        "v": e,          "lh": {"t": f * 0.8,  "v": e}},
        ],
        "Double Back": [
            {"t": 0,        "v": s,          "rh": {"t": f * 0.1,  "v": s}},
            {"t": f * 0.25, "v": e + d * 0.1, "lh": {"t": f * 0.15, "v": e + d * 0.1},
                                                   "rh": {"t": f * 0.35, "v": e + d * 0.1}},
            {"t": f * 0.5,  "v": s - d * 0.05, "lh": {"t": f * 0.4,  "v": s - d * 0.05},
                                                   "rh": {"t": f * 0.6,  "v": s - d * 0.05}},
            {"t": f * 0.75, "v": e + d * 0.05, "lh": {"t": f * 0.65, "v": e + d * 0.05},
                                                   "rh": {"t": f * 0.9,  "v": e + d * 0.05}},
            {"t": f,        "v": e,          "lh": {"t": f * 0.95, "v": e}},
        ],
        "Smooth Damp": [
            {"t": 0,        "v": s,          "rh": {"t": f * 0.1,  "v": s}},
            {"t": f * 0.4,  "v": e + d * 0.08, "lh": {"t": f * 0.2,  "v": e + d * 0.08},
                                                   "rh": {"t": f * 0.6,  "v": e + d * 0.08}},
            {"t": f * 0.7,  "v": e + d * 0.02, "lh": {"t": f * 0.55, "v": e + d * 0.02},
                                                   "rh": {"t": f * 0.85, "v": e + d * 0.02}},
            {"t": f,        "v": e,          "lh": {"t": f * 0.95, "v": e}},
        ],
        # Special curves
        "Slow Mo": [
            {"t": 0,        "v": s,          "rh": {"t": f * 0.3,  "v": s + d * 0.1}},
            {"t": f * 0.5,  "v": s + d * 0.3, "lh": {"t": f * 0.35, "v": s + d * 0.25},
                                                   "rh": {"t": f * 0.65, "v": s + d * 0.35}},
            {"t": f,        "v": e,          "lh": {"t": f * 0.7,  "v": e - d * 0.1}},
        ],
        "Logarithmic": [
            {"t": 0,   "v": s, "rh": {"t": f * 0.0,  "v": s}},
            {"t": f * 0.5, "v": s + d * 0.15, "lh": {"t": f * 0.25, "v": s + d * 0.05},
                                                   "rh": {"t": f * 0.75, "v": s + d * 0.35}},
            {"t": f,   "v": e, "lh": {"t": f * 1.0,  "v": e}},
        ],
    }
    return kfs.get(name, kfs["Linear"])


def _cubic_bezier_y(tt: float, p0: float, p1: float, p2: float, p3: float) -> float:
    """Standard cubic bezier interpolation."""
    mt = 1.0 - tt
    return mt*mt*mt*p0 + 3.0*mt*mt*tt*p1 + 3.0*mt*tt*tt*p2 + tt*tt*tt*p3


def _keyframes_to_normalized_points(keyframes: list, steps: int = 200) -> list:
    """
    Sample keyframes (with optional bezier handles) into normalized [0,1] points.

    FIX: Previously required BOTH rh and lh on the same segment which almost
    never happens — most presets only have rh on kf[0] and lh on kf[-1].
    Now falls back gracefully to the anchor value when a handle is absent.
    """
    if not keyframes:
        return [{"t": 0.0, "v": 0.0}, {"t": 1.0, "v": 1.0}]

    t0       = keyframes[0]["t"]
    t1       = keyframes[-1]["t"]
    s        = keyframes[0]["v"]
    e        = keyframes[-1]["v"]
    duration = t1 - t0 or 1.0
    rng      = e - s

    points = []
    for i in range(steps + 1):
        x   = t0 + (i / steps) * duration
        y   = keyframes[-1]["v"]           # default: clamp to last value

        for j in range(len(keyframes) - 1):
            a = keyframes[j]
            b = keyframes[j + 1]

            if a["t"] <= x <= b["t"]:
                seg_dur = b["t"] - a["t"]
                tt      = 0.0 if seg_dur == 0.0 else (x - a["t"]) / seg_dur

                # Use handle value if present, otherwise use the anchor itself
                rh_v = a["rh"]["v"] if "rh" in a else a["v"]
                lh_v = b["lh"]["v"] if "lh" in b else b["v"]

                y = _cubic_bezier_y(tt, a["v"], rh_v, lh_v, b["v"])
                break

        norm_t = (x - t0) / duration
        norm_v = (y - s) / rng if rng != 0.0 else 0.0
        points.append({"t": norm_t, "v": norm_v})

    return points


def _extract_value(v):
    if isinstance(v, dict):
        return v.get(1, v)
    return v


def _get_deep_spline_keyframes(inp):
    get_conn = getattr(inp, "GetConnectedOutput", None)
    output   = get_conn() if callable(get_conn) else None
    if not output:
        return None, None
    get_tool = getattr(output, "GetTool", None)
    spline   = get_tool() if callable(get_tool) else None
    if not spline:
        return None, None
    get_kf   = getattr(spline, "GetKeyFrames", None)
    keyframes = get_kf() if callable(get_kf) else None
    if keyframes and isinstance(keyframes, dict) and len(keyframes) >= 2:
        return spline, keyframes
    return None, None


# ═══════════════════════════════════════════════════════════════
# RESOLVE BRIDGE
# ═══════════════════════════════════════════════════════════════

class _ResolveBridge:
    def __init__(self):
        self.resolve    = None
        self.fusion     = None
        self.dvr        = None
        self.connected  = False
        self.last_error = ""
        self.last_changed_spline = None       # name of last changed BezierSpline
        self.last_changed_input_name = None  # human-readable input name (INPS_Name) of last change
        self._watcher_thread = None
        self._watcher_running = False
        self._spline_snapshot = {}        # name -> signature string
        self._watcher_changed = False     # set True when watcher detects any change; GUI polls this
        self._our_write_timestamp = 0.0   # stamped before every SetKeyFrames we initiate
        self._cached_kfs = {}             # spline_name -> full GetKeyFrames() dict (extracted by watcher)
        self._input_snapshot = {}         # {tool_name: {input_name: str(value)}} for value-based detection
        # DLL import deferred to connect() — importing fusionscript.dll at startup
        # caused C++ access violations on some systems before the window even opened.

    @staticmethod
    def _is_resolve_running() -> bool:
        """Check if DaVinci Resolve process is running before loading its DLL.
        The fusionscript.dll can cause an unrecoverable access violation (Windows
        fatal exception) when imported while Resolve is not running, so we probe
        first and skip the import entirely when it's safe to do so."""
        import sys
        if sys.platform != "win32":
            return True  # Non-Windows: let the import try normally
        try:
            import subprocess
            r = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Resolve.exe", "/NH"],
                capture_output=True, text=True, timeout=5
            )
            return "Resolve.exe" in r.stdout
        except Exception:
            return True  # If the check itself fails, attempt the import anyway

    def _try_import(self):
        import sys, os
        print(f"[Reveace] Debug: Python {sys.version}")
        print(f"[Reveace] Debug: API path: {os.environ.get('RESOLVE_SCRIPT_API')}")
        print(f"[Reveace] Debug: LIB path: {os.environ.get('RESOLVE_SCRIPT_LIB')}")
        if not self._is_resolve_running():
            self.dvr        = None
            self.last_error = "DaVinci Resolve is not running"
            print("[Reveace] Resolve not running — skipping DLL import to avoid crash")
            return
        try:
            import DaVinciResolveScript as dvr
            self.dvr = dvr
        except Exception as e:
            self.dvr        = None
            self.last_error = str(e)
            print(f"[Reveace] Debug error: {e}")

    def connect(self) -> bool:
        if self.dvr is None:
            self._try_import()
        if self.dvr is None:
            self.connected = False
            return False
        try:
            self.resolve = self.dvr.scriptapp("Resolve")
            if self.resolve:
                self.fusion    = self.resolve.Fusion()
                self.connected = True
                self.start_spline_watcher()
                return True
        except Exception as e:
            self.last_error = str(e)
        self.connected = False
        self.resolve   = None
        self.fusion    = None
        return False

    def is_connected(self) -> bool:
        return self.connected and self.resolve is not None

    def get_product_info(self) -> dict:
        if not self.is_connected():
            return {}
        try:
            return {
                "name":    self.resolve.GetProductName(),
                "version": self.resolve.GetVersionString(),
                "page":    self.resolve.GetCurrentPage(),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_current_comp(self):
        if not self.is_connected() or not self.fusion:
            return None
        try:
            return self.fusion.GetCurrentComp()
        except Exception:
            return None

    def get_active_tool(self):
        comp = self.get_current_comp()
        if not comp:
            return None
        try:
            tool = comp.ActiveTool
            if tool:
                return tool
            # Fallback: try selected tools in Flow view
            selected = comp.GetToolList(True)
            if selected:
                return list(selected.values())[0]
            return None
        except Exception:
            return None

    def get_tool_name(self, tool=None) -> str:
        t = tool or self.get_active_tool()
        if not t:
            return ""
        try:
            attrs = t.GetAttrs()
            return attrs.get("TOOLS_Name", "Unknown")
        except Exception:
            return "Unknown"

    def get_animated_inputs(self, tool=None) -> list:
        t = tool or self.get_active_tool()
        if not t:
            return []
        try:
            inputs = t.GetInputList()
        except Exception:
            return []

        results = []
        for input_id, inp in inputs.items():
            try:
                attrs = inp.GetAttrs()
                name  = attrs.get("INPS_Name", input_id)
                conn  = inp.GetConnectedOutput()
                if not conn:
                    continue
                src      = conn.GetTool()
                src_type = src.GetAttrs().get("TOOLS_RegID", "") if src else ""

                # ── Direct BezierSpline ──
                if "BezierSpline" in src_type:
                    kfs            = src.GetKeyFrames()
                    if "Value" in kfs:
                        continue  # shape animation spline — SetKeyFrames would wipe shape data
                    numeric_frames = sorted([f for f in kfs.keys() if isinstance(f, (int, float))])
                    if len(numeric_frames) < 2:
                        continue
                    first_val = kfs[numeric_frames[0]]
                    if not isinstance(first_val, dict) or 1 not in first_val:
                        continue
                    if not isinstance(first_val[1], (int, float)):
                        continue
                    start_frame = float(numeric_frames[0])
                    end_frame   = float(numeric_frames[-1])
                    results.append({
                        "id":         input_id,
                        "name":       name,
                        "input":      inp,
                        "spline":     src,
                        "input_type": "direct",
                        "keyframes":  kfs,
                        "start":      {"frame": start_frame, "value": float(first_val[1])},
                        "end":        {"frame": end_frame,   "value": float(kfs[numeric_frames[-1]][1])},
                    })

                # ── PolyPath (Center, Pivot, Point inputs) ──
                elif "PolyPath" in src_type:
                    path_inputs = src.GetInputList()
                    for pk, pinp in path_inputs.items():
                        pname = pinp.GetAttrs().get("INPS_Name", pk)
                        if pname != "Displacement":
                            continue
                        pconn = pinp.GetConnectedOutput()
                        if not pconn:
                            continue
                        disp_tool      = pconn.GetTool()
                        kfs            = disp_tool.GetKeyFrames()
                        numeric_frames = sorted([f for f in kfs.keys() if isinstance(f, (int, float))])
                        if len(numeric_frames) < 2:
                            continue
                        start_frame = float(numeric_frames[0])
                        end_frame   = float(numeric_frames[-1])
                        results.append({
                            "id":                   input_id,
                            "name":                 name,
                            "input":                inp,
                            "spline":               disp_tool,
                            "input_type":           "polypath",
                            "supports_polypath_gen": True,
                            "keyframes":            kfs,
                            "start":                {"frame": start_frame, "value": 0.0},
                            "end":                  {"frame": end_frame,   "value": 1.0},
                        })
                        break

            except Exception:
                pass

        return results

    def generate_elastic_polypath(self, tool, input_name: str,
                                   curve_fn, params: dict,
                                   comp=None) -> dict:
        """
        Generate a PolyPath with elastic/bounce waypoints baked into the path geometry.
        Reads existing start/end XY from the current PolyPath via SaveSettings.
        Pastes a new PolyPath and connects it to the input.
        
        curve_fn: callable(t, **params) -> float in [0,1] range
        """
        import re
        import tempfile

        if comp is None:
            comp = self.get_current_comp()
        if not comp:
            return {"ok": False, "error": "No active composition"}

        # Find the target input and existing PolyPath
        inputs     = tool.GetInputList()
        center_inp = None
        old_path   = None
        start_frame = end_frame = None

        for k, inp in inputs.items():
            if inp.GetAttrs().get("INPS_Name", k) != input_name:
                continue
            center_inp = inp
            conn       = inp.GetConnectedOutput()
            if not conn:
                continue
            src      = conn.GetTool()
            src_type = src.GetAttrs().get("TOOLS_RegID", "")
            if "PolyPath" not in src_type:
                continue
            old_path = src

            # Read frame range from displacement spline
            for pk, pinp in src.GetInputList().items():
                pname = pinp.GetAttrs().get("INPS_Name", pk)
                if pname != "Displacement":
                    continue
                pconn = pinp.GetConnectedOutput()
                if not pconn:
                    continue
                disp_tool      = pconn.GetTool()
                kfs            = disp_tool.GetKeyFrames()
                numeric_frames = sorted([f for f in kfs.keys() if isinstance(f, (int, float))])
                if len(numeric_frames) >= 2:
                    start_frame = float(numeric_frames[0])
                    end_frame   = float(numeric_frames[-1])
                break
            break

        if not center_inp:
            return {"ok": False, "error": f"Input '{input_name}' not found"}
        if not old_path:
            return {"ok": False, "error": "No PolyPath connected to input"}
        if start_frame is None:
            return {"ok": False, "error": "Could not read frame range from displacement"}

        # Read start/end XY via SaveSettings
        try:
            tmp    = tempfile.mktemp(suffix=".setting")
            result = old_path.SaveSettings(tmp)
            if not result:
                return {"ok": False, "error": "SaveSettings failed"}

            with open(tmp, "r") as f:
                content = f.read()

            pattern   = re.compile(
                r'X\s*=\s*([+-]?\d+\.?\d*(?:e[+-]?\d+)?)'
                r',\s*Y\s*=\s*([+-]?\d+\.?\d*(?:e[+-]?\d+)?)',
                re.IGNORECASE
            )
            all_pts = pattern.findall(content)
            if len(all_pts) < 2:
                return {"ok": False, "error": "Could not parse PolyLine points"}

            start_x, start_y = float(all_pts[0][0]),  float(all_pts[0][1])
            end_x,   end_y   = float(all_pts[-1][0]), float(all_pts[-1][1])
        except Exception as e:
            return {"ok": False, "error": f"Failed to read path: {e}"}

        # Generate waypoints
        STEPS = 30
        pts   = []
        for i in range(STEPS + 1):
            t = i / STEPS
            v = curve_fn(t, **params)
            x = start_x + v * (end_x - start_x)
            y = start_y + v * (end_y - start_y)
            pts.append((x, y))

        def fmt(n):
            return "{:.10f}".format(n)

        point_strs = []
        for i, (x, y) in enumerate(pts):
            is_first = i == 0
            is_last  = i == len(pts) - 1
            if is_first:
                nx, ny = pts[i+1]
                rx = (nx - x) * 0.35
                ry = (ny - y) * 0.35
                s = "{{ Linear = true, LockY = true, X = {}, Y = {}, RX = {}, RY = {} }}".format(
                    fmt(x), fmt(y), fmt(rx), fmt(ry))
            elif is_last:
                px, py = pts[i-1]
                lx = (px - x) * 0.35
                ly = (py - y) * 0.35
                s = "{{ Linear = true, LockY = true, X = {}, Y = {}, LX = {}, LY = {} }}".format(
                    fmt(x), fmt(y), fmt(lx), fmt(ly))
            else:
                px, py = pts[i-1]
                nx, ny = pts[i+1]
                rx = (nx - px) * 0.175
                ry = (ny - py) * 0.175
                s = "{{ X = {}, Y = {}, LX = {}, LY = {}, RX = {}, RY = {} }}".format(
                    fmt(x), fmt(y), fmt(-rx), fmt(-ry), fmt(rx), fmt(ry))
            point_strs.append(s)

        points_block = ",\n\t\t\t\t\t\t".join(point_strs)
        dur  = end_frame - start_frame
        rh_t = round(start_frame + dur / 3.0, 4)
        lh_t = round(end_frame   - dur / 3.0, 4)
        old_path_name = old_path.GetAttrs().get("TOOLS_Name")

        comp_str = """{{
    Tools = ordered() {{
        NewElasticPath = PolyPath {{
            DrawMode = "InsertAndModify",
            CtrlWZoom = false,
            Inputs = {{
                Displacement = Input {{
                    SourceOp = "NewElasticPathDisp",
                    Source = "Value",
                }},
                PolyLine = Input {{
                    Value = Polyline {{
                        Points = {{
                            {points}
                        }}
                    }},
                }}
            }},
        }},
        NewElasticPathDisp = BezierSpline {{
            SplineColor = {{ Red = 255, Green = 0, Blue = 255 }},
            NameSet = true,
            KeyFrames = {{
                [{sf}] = {{ 0, RH = {{ {rht}, 0.333 }}, Flags = {{ LockedY = true }} }},
                [{ef}] = {{ 1, LH = {{ {lht}, 0.667 }}, Flags = {{ Linear = true, LockedY = true }} }}
            }}
        }}
    }}
}}""".format(
            points=points_block,
            sf=round(start_frame), ef=round(end_frame),
            rht=rh_t, lht=lh_t
        )

        comp.Lock()
        try:
            comp.Paste(comp_str)

            # Find the newly pasted PolyPath
            all_tools = comp.GetToolList(False)
            new_path  = None
            for tidx, t in all_tools.items():
                tname = t.GetAttrs().get("TOOLS_Name", "")
                treg  = t.GetAttrs().get("TOOLS_RegID", "")
                if "PolyPath" in treg and tname != old_path_name and "NewElastic" in tname:
                    new_path = t
                    break
            if not new_path:
                for tidx, t in all_tools.items():
                    tname = t.GetAttrs().get("TOOLS_Name", "")
                    treg  = t.GetAttrs().get("TOOLS_RegID", "")
                    if "PolyPath" in treg and tname != old_path_name:
                        new_path = t

            if not new_path:
                comp.Unlock()
                return {"ok": False, "error": "New path not found after paste"}

            # Connect to input
            outputs = new_path.GetOutputList()
            pos_out = None
            for k, out in outputs.items():
                if "Position" in out.GetAttrs().get("OUTS_Name", ""):
                    pos_out = out
                    break

            if not pos_out:
                comp.Unlock()
                return {"ok": False, "error": "Position output not found on new path"}

            center_inp.ConnectTo(pos_out)
            comp.Unlock()
            return {
                "ok":       True,
                "new_path": new_path.GetAttrs().get("TOOLS_Name"),
                "points":   len(pts),
            }

        except Exception as e:
            try:
                comp.Unlock()
            except Exception:
                pass
            return {"ok": False, "error": str(e)}

    def inject_keyframes(self, input_obj, keyframes: list, comp=None,
                     spline_tool=None) -> dict:
        """
        Write keyframes to Resolve using SetKeyFrames with correct format.
        keyframes: list of {t, v, rh?, lh?} where rh/lh are normalized absolute positions.
        spline_tool: pass directly when targeting PolyPath displacement spline.
        """
        if comp is None:
            comp = self.get_current_comp()
        if not comp:
            return {"ok": False, "error": "No active composition"}

        try:
            comp.BeginUndo("Apply EaseSpline curve")
        except Exception:
            pass
        comp.Lock()
        try:
            # Resolve target spline
            if spline_tool:
                spline = spline_tool
            else:
                conn = input_obj.GetConnectedOutput()
                if conn:
                    spline = conn.GetTool()
                else:
                    spline = comp.BezierSpline()
                    input_obj.ConnectTo(spline)

            # Build Resolve keyframe table
            # Format: {frame: {1: value, "RH": {1: t_offset, 2: v_offset}, "LH": ...}}
            kf_table = {}
            for kf in keyframes:
                if isinstance(kf, (list, tuple)):
                    frame, value = float(kf[0]), float(kf[1])
                    kf_table[round(frame)] = {1: value}
                    continue

                frame = float(kf.get("t", kf.get("frame", 0)))
                value = float(kf.get("v", kf.get("value", 0)))
                entry = {1: value}

                if "rh" in kf:
                    rh      = kf["rh"]
                    rh_t    = float(rh.get("t", rh.get(1, frame)))
                    rh_v    = float(rh.get("v", rh.get(2, value)))
                    entry["RH"] = {1: rh_t - frame, 2: rh_v - value}

                if "lh" in kf:
                    lh      = kf["lh"]
                    lh_t    = float(lh.get("t", lh.get(1, frame)))
                    lh_v    = float(lh.get("v", lh.get(2, value)))
                    entry["LH"] = {1: lh_t - frame, 2: lh_v - value}

                kf_table[round(frame)] = entry

            self._our_write_timestamp = time.time()
            spline.SetKeyFrames(kf_table, True)
            comp.Unlock()
            try:
                comp.EndUndo(True)
            except Exception:
                pass
            return {"ok": True, "applied": len(kf_table)}

        except Exception as e:
            try:
                comp.Unlock()
            except Exception:
                pass
            try:
                comp.EndUndo(False)
            except Exception:
                pass
            return {"ok": False, "error": str(e)}

    def _get_spline_snapshot(self) -> dict:
        """Snapshot all tools with keyframes: name -> value signature"""
        comp = self.get_current_comp()
        if not comp:
            return {}
        state = {}
        try:
            for k, tool in comp.GetToolList(False).items():
                attrs = tool.GetAttrs()
                reg_id = attrs.get("TOOLS_RegID", "")
                name = attrs.get("TOOLS_Name", "")
                
                # Track BezierSplines and any tool with keyframes
                is_bezier = reg_id == "BezierSpline"
                
                try:
                    kfs = tool.GetKeyFrames()
                    if kfs and isinstance(kfs, dict):
                        frames = [f for f in kfs.keys() if isinstance(f, (int, float))]
                        if len(frames) >= 1:  # Track even single-keyframe splines (catch additions)
                            sig_parts = []
                            for f in sorted(frames):
                                val = kfs[f]
                                if isinstance(val, dict) and 1 in val:
                                    # Include bezier handle data so handle-only changes are detected
                                    rh = val.get("RH", {})
                                    lh = val.get("LH", {})
                                    rh_str = f"rh={round(float(rh.get(1, 0)), 4)},{round(float(rh.get(2, 0)), 4)}" if rh else ""
                                    lh_str = f"lh={round(float(lh.get(1, 0)), 4)},{round(float(lh.get(2, 0)), 4)}" if lh else ""
                                    sig_parts.append(f"{f}={val[1]}|{rh_str}|{lh_str}")
                                else:
                                    sig_parts.append(f"{f}={val}")
                            state[name] = ",".join(sig_parts)
                except Exception as e:
                    # Tool doesn't support GetKeyFrames or error
                    pass
                    
        except Exception as e:
            print(f"[_get_spline_snapshot] Error: {e}")
        return state

    def _resolve_spline_name(self, inp) -> str:
        """Return the BezierSpline tool name connected to this input (handles PolyPath too)."""
        try:
            out = inp.GetConnectedOutput()
            if not out:
                return ""
            tool = out.GetTool()
            if not tool:
                return ""
            reg = tool.GetAttrs().get("TOOLS_RegID", "")
            if reg == "BezierSpline":
                return tool.GetAttrs().get("TOOLS_Name", "")
            elif reg == "PolyPath":
                path_inputs = tool.GetInputList() or {}
                for _, pinp in path_inputs.items():
                    if pinp.GetAttrs().get("INPS_Name") == "Displacement":
                        pout = pinp.GetConnectedOutput()
                        if pout:
                            disp = pout.GetTool()
                            if disp:
                                return disp.GetAttrs().get("TOOLS_Name", "")
        except Exception:
            pass
        return ""

    def _watcher_loop(self):
        self._spline_snapshot = self._get_spline_snapshot()
        print(f"[Watcher] Started with {len(self._spline_snapshot)} tracked tools")
        while self._watcher_running:
            time.sleep(0.3)
            try:
                curr = self._get_spline_snapshot()
                
                # Ignore changes within 0.6 s of our own SetKeyFrames writes
                # so that moving In/Out frames doesn't trigger an auto mode-switch.
                our_write_age = time.time() - self._our_write_timestamp
                ignore_self_writes = our_write_age < 0.6

                # Check for new or changed tools
                for name, sig in curr.items():
                    old_sig = self._spline_snapshot.get(name)
                    changed = (old_sig is None) or (old_sig != sig)
                    if not changed:
                        continue

                    label = "New tool" if old_sig is None else "Change"
                    self.last_changed_spline = name
                    if not ignore_self_writes:
                        self._watcher_changed = True

                    # Extract and cache full keyframe data (including bezier handles)
                    # so apply_to_resolve can use the exact handle values that were live
                    # at detection time rather than relying solely on a later API call.
                    try:
                        comp = self.get_current_comp()
                        if comp:
                            for _, t in comp.GetToolList(False).items():
                                if t.GetAttrs().get("TOOLS_Name") == name:
                                    kfs = t.GetKeyFrames()
                                    if kfs:
                                        self._cached_kfs[name] = kfs
                                        # Log handle values so the user can verify detection
                                        frames = sorted([f for f in kfs if isinstance(f, (int, float))])
                                        handle_lines = []
                                        for f in frames:
                                            v = kfs[f]
                                            if isinstance(v, dict):
                                                rh = v.get("RH")
                                                lh = v.get("LH")
                                                if rh or lh:
                                                    handle_lines.append(
                                                        f"  frame {f}: RH={rh}  LH={lh}"
                                                    )
                                        if handle_lines:
                                            print(f"[Watcher] {label} in: {name} — bezier handles:")
                                            for line in handle_lines:
                                                print(line)
                                        else:
                                            print(f"[Watcher] {label} in: {name} (no explicit handles — Linear/Auto)")
                                    break
                    except Exception as _we:
                        print(f"[Watcher] {label} in: {name} (handle extract error: {_we})")
                
                # Check for removed tools
                for name in self._spline_snapshot:
                    if name not in curr:
                        print(f"[Watcher] Tool removed: {name}")

                self._spline_snapshot = curr

                # ── Input value polling (catches PolyPath/Center and any modifier) ──
                try:
                    comp = self.get_current_comp()
                    if comp:
                        current_time = comp.CurrentTime
                        last_poll_time = getattr(self, '_last_poll_time', None)
                        time_moved = (last_poll_time is not None and last_poll_time != current_time)
                        self._last_poll_time = current_time

                        selected = comp.GetToolList(True) or {}
                        sel_tools = list(selected.values())
                        if not sel_tools:
                            active = self.get_active_tool()
                            if active:
                                sel_tools = [active]
                        for sel_tool in sel_tools:
                            tool_name = sel_tool.GetAttrs().get("TOOLS_Name", "")
                            if not tool_name:
                                continue
                            prev_snap = self._input_snapshot.get(tool_name, {})
                            is_new_tool = not prev_snap
                            curr_snap = {}
                            inputs = sel_tool.GetInputList() or {}
                            for _, inp in inputs.items():
                                try:
                                    inp_name = inp.GetAttrs().get("INPS_Name", "")
                                    val = str(inp[current_time])
                                    curr_snap[inp_name] = val
                                    # Skip change detection when playhead moved — values differ
                                    # because of the new time position, not a user edit.
                                    if is_new_tool or time_moved:
                                        pass
                                    elif inp_name in prev_snap and prev_snap[inp_name] != val:
                                        spline_name = self._resolve_spline_name(inp)
                                        if not spline_name:
                                            continue
                                        # Verify the resolved spline has keyframes
                                        try:
                                            spline_tool = None
                                            for _, t in comp.GetToolList(False).items():
                                                if t.GetAttrs().get("TOOLS_Name") == spline_name:
                                                    spline_tool = t
                                                    break
                                            if not spline_tool:
                                                continue
                                            skfs = spline_tool.GetKeyFrames() or {}
                                            if len([f for f in skfs if isinstance(f, (int, float))]) < 2:
                                                continue
                                        except Exception:
                                            continue
                                        print(f"[Watcher] Value change: {tool_name}.{inp_name} → spline: {spline_name}")
                                        self.last_changed_spline = spline_name
                                        self.last_changed_input_name = inp_name
                                        # Cache the displacement spline keyframes now
                                        kfs_now = spline_tool.GetKeyFrames()
                                        if kfs_now and not ignore_self_writes:
                                            self._cached_kfs[spline_name] = kfs_now
                                        if not ignore_self_writes:
                                            self._watcher_changed = True
                                except Exception:
                                    pass
                            self._input_snapshot[tool_name] = curr_snap

                            # Prime last_changed_spline on first sight of tool:
                            # prefer PolyPath (displacement) over direct splines.
                            if is_new_tool:
                                try:
                                    animated = self.get_animated_inputs(sel_tool)
                                    chosen = next((d for d in animated if d.get("input_type") == "polypath"), None)
                                    if not chosen:
                                        chosen = next((d for d in animated if d.get("input_type") == "direct"), None)
                                    if chosen:
                                        sp = chosen.get("spline")
                                        if sp:
                                            prime_name = sp.GetAttrs().get("TOOLS_Name", "")
                                            if prime_name and prime_name != self.last_changed_spline:
                                                print(f"[Watcher] New tool {tool_name} — priming spline: {prime_name}")
                                                self.last_changed_spline = prime_name
                                                self.last_changed_input_name = chosen.get("name", "")
                                except Exception:
                                    pass
                except Exception as e:
                    print(f"[Watcher] Value poll error: {e}")

            except Exception as e:
                print(f"[Watcher] Error: {e}")

    def start_spline_watcher(self):
        if self._watcher_running:
            return
        self._watcher_running = True
        self._watcher_thread = threading.Thread(target=self._watcher_loop, daemon=True)
        self._watcher_thread.start()

    def stop_spline_watcher(self):
        self._watcher_running = False

    def get_adjacent_keyframes(self, spline_tool, current_time: float):
        """
        Find the two keyframes surrounding current_time.
        Rules:
        - Between keyframes: left <= currentTime < right
        - Exactly on last keyframe: return second-to-last and last
        - No valid pair: return None
        """
        kfs = spline_tool.GetKeyFrames()
        # Shape animation splines have a 'Value' key in GetKeyFrames() and cannot
        # be modified via SetKeyFrames — it would wipe the embedded shape data.
        if "Value" in kfs:
            return None
        frames = sorted([f for f in kfs.keys() if isinstance(f, (int, float))])
        if len(frames) < 2:
            return None

        left = None
        right = None
        for f in frames:
            if f <= current_time:
                left = f
            elif right is None:
                right = f

        # Exactly on last keyframe — use last segment
        if left is not None and right is None:
            left = frames[-2]
            right = frames[-1]

        # Before first keyframe — default to the first segment
        if left is None:
            left = frames[0]
            right = frames[1]

        # Debug prints disabled to avoid console spam during live polling
        # print(f"[DEBUG] get_adjacent_keyframes: current_time={current_time}, found left={left}, right={right}")
        # print(f"[DEBUG] left_value={kfs[left]}, right_value={kfs[right]}")

        return {
            "left_frame":  left,
            "right_frame": right,
            "left_value":  float(kfs[left][1] if isinstance(kfs[left], dict) else kfs[left]),
            "right_value": float(kfs[right][1] if isinstance(kfs[right], dict) else kfs[right]),
            "kfs":         kfs,
            "spline":      spline_tool,
        }

    def patch_segment(self, segment: dict, norm_rh: dict, norm_lh: dict,
                      comp=None) -> dict:
        """
        Apply normalized bezier handles to a specific keyframe pair only.
        All other keyframes in the spline are left completely untouched.

        norm_rh / norm_lh: {"t": float, "v": float} in normalized [0,1] space
          norm_rh["t"]: 0→1 absolute position along segment duration (0=start, 1=end)
          norm_rh["v"]: 0→1 absolute value position (0=start value, 1=end value)
          norm_lh["t"]: 0→1 absolute position along segment duration (0=start, 1=end)
          norm_lh["v"]: 0→1 absolute value position (0=start value, 1=end value)
        
        The function converts these to Fusion offset coordinates:
          RH offset: {1: rh_t * time_diff, 2: rh_v * value_diff}
          LH offset: {1: (lh_t - 1.0) * time_diff, 2: (lh_v - 1.0) * value_diff}
        """
        if comp is None:
            comp = self.get_current_comp()
        if not comp:
            return {"ok": False, "error": "No active composition"}

        left       = segment["left_frame"]
        right      = segment["right_frame"]
        kfs        = segment["kfs"]
        spline     = segment["spline"]
        time_diff  = right - left
        value_diff = segment["right_value"] - segment["left_value"]
        
        # DEBUG: Verify spline info
        spline_name = spline.GetAttrs().get("TOOLS_Name", "Unknown") if spline else "None"
        all_frames = sorted([f for f in kfs.keys() if isinstance(f, (int, float))])
        print("=" * 70)
        print(f"[DEBUG] PATCH_SEGMENT START")
        print(f"[DEBUG] Spline name: {spline_name}")
        print(f"[DEBUG] All frames in kfs: {all_frames}")
        print(f"[DEBUG] Target segment: left={left}, right={right}")
        print(f"[DEBUG] left in kfs: {left in kfs}, right in kfs: {right in kfs}")

        # Denormalize: convert normalized [0,1] handles → Fusion offset coords.
        # Fusion stores handle positions as offsets FROM the owning keyframe:
        #   RH of LEFT kf:   offset_from_left   = (handle_abs - left_kf)
        #   LH of RIGHT kf:  offset_from_right  = (handle_abs - right_kf)
        #
        # handle_abs_value = left_value + norm.v * value_diff
        # RH offset value  = norm_rh.v * value_diff                (from left kf)
        # LH offset value  = (norm_lh.v - 1.0) * value_diff       (from right kf)
        
        # Calculate handle offsets for Resolve
        # CRITICAL FIX: When value_diff is negative (decreasing animation),
        # the sign of norm_v matters differently. 
        # 
        # norm_v interpretation:
        # - norm_v = 0 means "at start value"
        # - norm_v = 1 means "at end value"  
        # - norm_v = -0.02 means "2% of range BELOW start"
        # - norm_v = 1.02 means "2% of range BEYOND end"
        #
        # For decreasing animation (start=197, end=-16, diff=-213):
        # - handle at start (197): norm_v = 0, offset = 0
        # - handle at end (-16): norm_v = 1, offset = -213
        # - handle 2% below start (192.74): norm_v = -0.02, offset = -4.26
        #
        # Formula: offset = norm_v * |value_diff| * sign(value_diff)
        # But that's the same as: offset = norm_v * value_diff
        #
        # The REAL issue: when both norm_v and value_diff are negative,
        # offset becomes positive, pointing the wrong way!
        #
        # FIX: Use absolute value of value_diff when norm_v is "relative"
        # Actually, the correct interpretation is:
        # offset = norm_v * abs(value_diff) if we want norm_v to be "percentage of range"
        # But that's not what we want either...
        #
        # CORRECT INTERPRETATION:
        # norm_v is a normalized coordinate where 0=start, 1=end
        # The absolute handle value = start + norm_v * (end - start)
        # The offset from start = norm_v * (end - start) = norm_v * value_diff
        #
        # This is correct! The issue must be elsewhere...
        #
        # WAIT - I think I see it now. The issue is that norm_v = -0.02 means
        # "slightly toward the start from start", but for a decreasing animation,
        # "toward the start" means UP (higher value), not down.
        #
        # For decreasing animation: start (197) is ABOVE end (-16)
        # So "below start" means numerically less (toward end), which is correct!
        # norm_v = -0.02, value_diff = -213.2
        # offset = (-0.02) * (-213.2) = +4.26
        # handle = 197.2 + 4.26 = 201.46 (above start)
        #
        # But wait, that's wrong! For a decreasing animation, -0.02 should mean
        # "2% toward the END", not "2% numerically lower".
        #
        # The fix: interpret norm_v as "percentage toward end" regardless of direction
        # offset = norm_v * abs(value_diff)
        # Then for decreasing animations, flip the sign?
        #
        # Actually, let me try: offset = norm_v * value_diff
        # But interpret norm_v correctly:
        # - For increasing: norm_v = -0.02 means "below start" (offset negative)
        # - For decreasing: norm_v = -0.02 means "above start" (offset positive)
        #
        # This is confusing because "below" and "above" are ambiguous when
        # the animation can go either direction.
        #
        # SIMPLER FIX: Always use absolute positioning
        # absolute = start + norm_v * abs(value_diff) * direction
        # where direction = 1 if end > start else -1
        #
        # No wait, that's wrong too. Let me just use the correct formula:
        # offset = norm_v * value_diff
        # And accept that norm_v = -0.02 means different things depending on direction.
        #
        # ACTUALLY - the real fix is to interpret norm_v as:
        # "Position along the line from start to end"
        # where 0 = start, 1 = end, negative = beyond start, >1 = beyond end
        #
        # absolute = start + norm_v * (end - start)
        # offset = absolute - start = norm_v * (end - start) = norm_v * value_diff
        #
        # This is already what we're doing! So why is the curve wrong?
        #
        # OH WAIT! I think I see it. The issue is that for a "Back In" curve,
        # the handle should pull BACKWARD (toward values less than start for increasing,
        # or toward values greater than start for decreasing).
        #
        # So for decreasing (197 -> -16), pulling backward means going UP from 197.
        # That's what the current code does! So maybe the curve is actually correct?
        #
        # Let me re-read the user's message... "the right handle is not makin the curve properly"
        # and the screenshot shows a curve going up then down.
        #
        # For a "Back In" curve, it should:
        # 1. Start at 197
        # 2. Go slightly backward (up to ~201)
        # 3. Then curve down toward -16
        #
        # That matches the screenshot! So what's the issue?
        #
        # Maybe the user wants "Back Out" instead of "Back In"?
        # Or maybe the handle value (-0.02) is too small?
        #
        # Let me just use the simple formula and see what happens:
        
        # RH: right handle of left keyframe
        # X offset: how far forward from left keyframe (in frames)
        rh_x_off = norm_rh["t"] * time_diff
        # LH: left handle of right keyframe
        lh_x_off = (norm_lh["t"] - 1.0) * time_diff

        # Y offsets — flat case: start=end so value_diff≈0, use virtual ±1.5 range
        FLAT_VIRTUAL = 3.0  # must match points_to_spl_keyframes
        if abs(value_diff) < 0.0001:
            rh_y_off = (norm_rh["v"] - 0.5) * FLAT_VIRTUAL
            lh_y_off = (norm_lh["v"] - 0.5) * FLAT_VIRTUAL
        else:
            rh_y_off = norm_rh["v"] * value_diff
            lh_y_off = (norm_lh["v"] - 1.0) * value_diff
        
        # DEBUG: Show what we're about to send to Resolve
        print("-" * 70)
        print("[DEBUG] PATCH_SEGMENT - Sending to Resolve")
        print("-" * 70)
        print(f"Input norm_rh: t={norm_rh['t']:.4f}, v={norm_rh['v']:.4f}")
        print(f"Input norm_lh: t={norm_lh['t']:.4f}, v={norm_lh['v']:.4f}")
        print(f"value_diff: {value_diff:.4f}")
        print(f"FORMULA: rh_y_off = norm_rh['v'] * value_diff = {norm_rh['v']:.4f} * {value_diff:.4f} = {norm_rh['v'] * value_diff:.4f}")
        print("")
        print(f"Keyframe at frame {left} (LEFT):")
        print(f"  Original: {kfs.get(left, 'N/A')}")
        print(f"  RH offset being set: {{1: {rh_x_off:.4f}, 2: {rh_y_off:.4f}}}")
        print(f"  RH absolute would be: frame={left + rh_x_off:.2f}, value={segment['left_value'] + rh_y_off:.4f}")
        print(f"  RH direction check: offset is {'POSITIVE' if rh_y_off > 0 else 'NEGATIVE'}, value_diff is {'POSITIVE' if value_diff > 0 else 'NEGATIVE'}")
        print("")
        print(f"Keyframe at frame {right} (RIGHT):")
        print(f"  Original: {kfs.get(right, 'N/A')}")
        print(f"  LH offset being set: {{1: {lh_x_off:.4f}, 2: {lh_y_off:.4f}}}")
        print(f"  LH absolute would be: frame={right + lh_x_off:.2f}, value={segment['right_value'] + lh_y_off:.4f}")
        
        # CRITICAL DEBUG: Check before setting
        print(f"[DEBUG] BEFORE setting handles:")
        print(f"[DEBUG]   left={left} (type={type(left).__name__}), right={right} (type={type(right).__name__})")
        print(f"[DEBUG]   All keys: {list(kfs.keys())}")
        print(f"[DEBUG]   Key types: {[type(k).__name__ for k in kfs.keys() if isinstance(k, (int, float))][:5]}")
        
        # Check if left and right exist in kfs
        left_exists = left in kfs
        right_exists = right in kfs
        print(f"[DEBUG]   left in kfs: {left_exists}, right in kfs: {right_exists}")
        
        # If not found, try different types
        if not left_exists:
            for k in kfs.keys():
                if isinstance(k, (int, float)) and abs(k - left) < 0.001:
                    print(f"[DEBUG]   Found matching left key: {k} (type={type(k).__name__})")
                    left = k
                    left_exists = True
                    break
        if not right_exists:
            for k in kfs.keys():
                if isinstance(k, (int, float)) and abs(k - right) < 0.001:
                    print(f"[DEBUG]   Found matching right key: {k} (type={type(k).__name__})")
                    right = k
                    right_exists = True
                    break
        
        print(f"[DEBUG]   kfs[{left}] = {kfs.get(left, 'MISSING')}")
        print(f"[DEBUG]   kfs[{right}] = {kfs.get(right, 'MISSING')}")
        
        # Use the found keys
        left_key = left
        right_key = right
        
        print(f"[DEBUG] Using left_key={left_key}, right_key={right_key}")
        
        # Ensure the keyframes have the RH/LH keys initialized
        if "RH" not in kfs[left_key]:
            print(f"[DEBUG] Adding RH key to kfs[{left_key}]")
        if "LH" not in kfs[right_key]:
            print(f"[DEBUG] Adding LH key to kfs[{right_key}]")
        
        kfs[left_key]["RH"]  = {1: rh_x_off, 2: rh_y_off}
        kfs[right_key]["LH"] = {1: lh_x_off, 2: lh_y_off}
        
        # CRITICAL DEBUG: Check after setting
        print(f"[DEBUG] AFTER setting handles:")
        print(f"[DEBUG]   kfs[{left_key}] = {kfs.get(left_key, 'MISSING')}")
        print(f"[DEBUG]   kfs[{right_key}] = {kfs.get(right_key, 'MISSING')}")
        
        print("")
        print("Updated keyframe table segment:")
        for f in sorted(kfs.keys()):
            if f in [left_key, right_key]:
                print(f"  [{f}] = {kfs[f]}")
        print("-" * 70)

        comp.Lock()
        try:
            # DEBUG: Check what we're about to set
            fresh_before = spline.GetKeyFrames()
            print(f"[DEBUG] BEFORE SetKeyFrames - Spline has: {sorted([f for f in fresh_before.keys() if isinstance(f, (int, float))])}")
            print(f"[DEBUG] Keyframe at {left_key} before: {fresh_before.get(left_key, 'N/A')}")
            
            # SetKeyFrames with False = merge with existing (keep other keyframes)
            print(f"[DEBUG] About to call SetKeyFrames with kfs keys: {list(kfs.keys())}")
            print(f"[DEBUG] kfs[{left_key}] = {kfs.get(left_key)}")
            print(f"[DEBUG] kfs[{right_key}] = {kfs.get(right_key)}")
            spline.SetKeyFrames(kfs, False)
            
            # DEBUG: Check what we actually set
            fresh_after = spline.GetKeyFrames()
            print(f"[DEBUG] AFTER SetKeyFrames - Spline has: {sorted([f for f in fresh_after.keys() if isinstance(f, (int, float))])}")
            print(f"[DEBUG] Keyframe at {left_key} after: {fresh_after.get(left_key, 'N/A')}")
            print("=" * 70)
            
            comp.Unlock()
            return {"ok": True, "left": left, "right": right}
        except Exception as e:
            try:
                comp.Unlock()
            except:
                pass
            return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# PHYSICS MATH
# ═══════════════════════════════════════════════════════════════

PI     = math.pi
TWO_PI = math.pi * 2.0


def _clamp01(t: float) -> float:
    return max(0.0, min(1.0, t))


def _elastic_out(t: float, amplitude: float, bounciness: float, decay_x: float, decay_y: float, hang: float = 0.5) -> float:
    if t <= 0.0: return 0.0
    if t >= 1.0: return 1.0
    
    decay = 0.5 + decay_y * 7.5
    
    # Decay X warps the time axis ONLY (frequency sweep)
    warped_t = t
    if abs(decay_x) > 0.001:
        k = decay_x * 5.0
        warped_t = (math.exp(k * t) - 1.0) / (math.exp(k) - 1.0)
    
    freq = max(0.1, bounciness * 8.0)
    
    if hang <= 0.5:
        f = hang * 2.0
        env = math.exp(-decay * t)
        phase = freq * warped_t * TWO_PI
        elastic_val = 1.0 - env * ((1.0 - amplitude) + amplitude * math.cos(phase))
        linear_val = t
        return linear_val + (elastic_val - linear_val) * f
    else:
        f = (hang - 0.5) * 2.0
        power = 1.0 + f * 4.0
        scaled_t = t ** power
        
        warped_scaled_t = scaled_t
        if abs(decay_x) > 0.001:
            k = decay_x * 5.0
            warped_scaled_t = (math.exp(k * scaled_t) - 1.0) / (math.exp(k) - 1.0)
            
        env = math.exp(-decay * scaled_t)
        phase = freq * warped_scaled_t * TWO_PI
        return 1.0 - env * ((1.0 - amplitude) + amplitude * math.cos(phase))


def _elastic_in(t: float, amplitude: float, bounciness: float, decay_x: float, decay_y: float, hang: float = 0.5) -> float:
    return 1.0 - _elastic_out(1.0 - t, amplitude, bounciness, decay_x, decay_y, hang)


def _bounce_bell(local_t: float, hang: float) -> float:
    s = math.sin(local_t * PI)
    u = 2.0 * (local_t if local_t <= 0.5 else (1.0 - local_t))
    if hang <= 0.5:
        f = hang * 2.0
        return u + (s - u) * f
    else:
        f  = (hang - 0.5) * 2.0
        ss = s * s * (3.0 - 2.0 * s)
        return s + (ss - s) * f


def _bounce_out(t: float, amplitude: float, bounciness: float,
                decay_x: float, decay_y: float, hang: float) -> float:
    if t <= 0.0: return 0.0
    if t >= 1.0: return 1.0
    b        = max(bounciness, 0.001)
    base_dur = math.sqrt(amplitude) * 2.0
    dips     = []
    osc_total = 0.0
    h        = amplitude
    t_scale  = 1.0
    for _ in range(30):
        if h < 0.0002:
            break
        dur = base_dur * t_scale
        dips.append({"t0": osc_total, "dur": dur, "h": h})
        osc_total += dur
        h       = h * math.pow(b, 1.0 + decay_y)
        t_scale = max(t_scale * (1.0 - decay_x * 0.5), 0.05)

    if t <= 0.5:
        t_local = t * 2.0
        if t_local <= 0.5:
            phase   = t_local / 0.5
            local_t = 0.5 + phase * 0.5
            return 1.0 - _bounce_bell(local_t, hang)
        else:
            if len(dips) == 0:
                return 1.0
            phase = (t_local - 0.5) / 0.5
            return 1.0 - dips[0]["h"] * _bounce_bell(phase, hang)
    else:
        t_d         = (t - 0.5) * 2.0
        decay_total = sum(dips[i]["dur"] for i in range(1, len(dips)))
        if decay_total <= 0.0 or len(dips) < 2:
            return 1.0
        t_abs  = t_d * decay_total
        offset = 0.0
        for i in range(1, len(dips)):
            dip = dips[i]
            if t_abs <= offset + dip["dur"]:
                local_t = (t_abs - offset) / max(dip["dur"], 0.0001)
                return 1.0 - dip["h"] * _bounce_bell(local_t, hang)
            offset += dip["dur"]
        return 1.0


def _bounce_in(t: float, amplitude: float, bounciness: float,
               decay_x: float, decay_y: float, hang: float) -> float:
    return 1.0 - _bounce_out(1.0 - t, amplitude, bounciness, decay_x, decay_y, hang)


def _eval_physics(t: float, mode: str, direction: str, params: dict) -> float:
    amplitude  = params.get("amplitude",  1.0)
    hang       = params.get("hang",       0.5)
    decay_x    = params.get("decay_x",    0.5)
    decay_y    = params.get("decay_y",    0.5)
    bounciness = params.get("bounciness", 0.5)
    if mode == "elastic":
        return (_elastic_out(t, amplitude, bounciness, decay_x, decay_y, hang)
                if direction == "out"
                else _elastic_in(t, amplitude, bounciness, decay_x, decay_y, hang))
    else:
        return (_bounce_out(t, amplitude, bounciness, decay_x, decay_y, hang)
                if direction == "out"
                else _bounce_in(t, amplitude, bounciness, decay_x, decay_y, hang))


# NOTE: Physics key points extraction removed - using unified curve sampler instead
# The preview HTML now sends the complete sampled curve directly


# NOTE: Physics keyframe table generation removed - using unified curve sampler instead


def _sample_physics_curve(mode: str, direction: str, params: dict, steps: int = 400) -> list:
    """
    Sample physics curve with dense uniform sampling for smooth preview.
    Uses high-density sampling to capture all the oscillations in elastic/bounce curves.
    """
    points = []
    
    # Use uniform dense sampling for smooth curves
    # Physics curves need more points to look smooth, especially elastic with many oscillations
    for i in range(steps + 1):
        t = i / steps
        v = _eval_physics(t, mode, direction, params)
        points.append({"t": t, "v": v})
    
    return points


def _cubic_bezier(t, p0, p1, p2, p3):
    """Evaluate cubic bezier at parameter t."""
    mt = 1.0 - t
    return mt*mt*mt*p0 + 3*mt*mt*t*p1 + 3*mt*t*t*p2 + t*t*t*p3


def _sample_physics_as_bezier(mode: str, direction: str, params: dict, 
                               start_frame: float = 0, end_frame: float = 100,
                               start_val: float = 0, end_val: float = 1,
                               steps: int = 400) -> list:
    """
    Sample physics curve as it will appear in Resolve (bezier-interpolated keyframes).
    This matches what Resolve displays because Resolve uses bezier interpolation between keyframes.
    """
    # Get the key points (peaks/valleys) that will become keyframes
    key_points = _physics_key_points(mode, direction, params)
    
    if not key_points:
        return _sample_physics_curve(mode, direction, params, steps)
    
    duration = end_frame - start_frame
    rng = end_val - start_val
    
    # Convert key points to frame/value space
    kfs = []
    for t, v in key_points:
        kfs.append({
            "frame": start_frame + t * duration,
            "value": start_val + v * rng
        })
    
    # Build keyframe table with bezier handles (same as Resolve gets)
    kf_table = {}
    for i, kf in enumerate(kfs):
        frame = round(kf["frame"])
        value = kf["value"]
        is_first = (i == 0)
        is_last = (i == len(kfs) - 1)
        entry = {"v": value}
        
        if not is_last:
            next_f = kfs[i+1]["frame"]
            next_v = kfs[i+1]["value"]
            rh_t_off = (next_f - kf["frame"]) / 3.0
            rh_v_off = 0.0 if is_first else (value - next_v) * 0.197
            entry["rh"] = {"t": frame + rh_t_off, "v": value + rh_v_off}
        
        if not is_first:
            prev_f = kfs[i-1]["frame"]
            prev_v = kfs[i-1]["value"]
            lh_t_off = -((kf["frame"] - prev_f) / 3.0)
            lh_v_off = 0.0 if is_last else (prev_v - value) * 0.084
            entry["lh"] = {"t": frame + lh_t_off, "v": value + lh_v_off}
        
        kf_table[frame] = entry
    
    # Sample the bezier-interpolated curve
    points = []
    frames = sorted(kf_table.keys())
    
    for i in range(steps + 1):
        t = i / steps
        frame = start_frame + t * duration
        
        # Find which segment this frame belongs to
        segment_idx = 0
        for j in range(len(frames) - 1):
            if frames[j] <= frame <= frames[j+1]:
                segment_idx = j
                break
        
        kf1_frame = frames[segment_idx]
        kf2_frame = frames[segment_idx + 1] if segment_idx + 1 < len(frames) else frames[-1]
        
        kf1 = kf_table[kf1_frame]
        kf2 = kf_table[kf2_frame]
        
        # Get bezier control points
        p0 = kf1["v"]
        p3 = kf2["v"]
        
        # Control points from handles
        if "rh" in kf1:
            rh = kf1["rh"]
            # RH handle value relative to segment
            p1 = rh["v"]
        else:
            p1 = p0
            
        if "lh" in kf2:
            lh = kf2["lh"]
            p2 = lh["v"]
        else:
            p2 = p3
        
        # Local parameter within segment
        if kf2_frame > kf1_frame:
            local_t = (frame - kf1_frame) / (kf2_frame - kf1_frame)
        else:
            local_t = 0
        
        # Evaluate bezier
        v = _cubic_bezier(local_t, p0, p1, p2, p3)
        
        # Normalize t to 0-1 range
        norm_t = (frame - start_frame) / duration if duration > 0 else 0
        
        # Normalize v to 0-1 range (for display)
        norm_v = (v - start_val) / rng if rng != 0 else 0
        
        points.append({"t": norm_t, "v": norm_v})
    
    return points


# ═══════════════════════════════════════════════════════════════
# CUSTOM EASING FUNCTIONS
# ═══════════════════════════════════════════════════════════════

# Each function is the "ease-in" form (starts slow).
# The "ease-out" form is computed by reflection: out(t) = 1 - fn(1-t)
_EASING_IN_FN = {
    "Linear": lambda t: t,
    "Sine":   lambda t: 1.0 - math.cos(t * math.pi / 2.0),
    "Quad":   lambda t: t * t,
    "Cubic":  lambda t: t * t * t,
    "Quart":  lambda t: t ** 4,
    "Quint":  lambda t: t ** 5,
    "Expo":   lambda t: 0.0 if t == 0.0 else math.pow(2.0, 10.0 * t - 10.0),
    "Circ":   lambda t: 1.0 - math.sqrt(max(0.0, 1.0 - t * t)),
    "Back":   lambda t: 2.70158 * t * t * t - 1.70158 * t * t,
}


def _ease_in(name: str, t: float) -> float:
    fn = _EASING_IN_FN.get(name, _EASING_IN_FN["Linear"])
    return fn(t)


def _ease_out(name: str, t: float) -> float:
    fn = _EASING_IN_FN.get(name, _EASING_IN_FN["Linear"])
    return 1.0 - fn(1.0 - t)


def _sample_custom_curve(custom_start: str, custom_end: str, steps: int = 200) -> list:
    """
    Combine easing functions for the start and end of the curve.
    
    - custom_start (was "In"): controls the START of the curve (first half)
    - custom_end (was "Out"): controls the END of the curve (second half)
    
    Uses sigmoid blending to avoid harsh transition at the midpoint.
    """
    points = []
    
    for i in range(steps + 1):
        t = i / steps
        
        # Calculate both curves across full range
        # start_curve affects the beginning (ease_in = starts slow, accelerates)
        # end_curve affects the ending (ease_out = starts fast, decelerates)
        v_start = _ease_in(custom_start, t)
        v_end = _ease_out(custom_end, t)
        
        # Smooth sigmoid blend factor (ease-in-out blend)
        # blend ≈ 0 at start, blend ≈ 1 at end
        blend = 1.0 / (1.0 + math.exp(-12 * (t - 0.5)))
        
        # Blend: start_curve dominates at beginning, end_curve dominates at end
        v = v_start * (1 - blend) + v_end * blend
        
        points.append({"t": t, "v": v})
    
    return points


# ═══════════════════════════════════════════════════════════════
# SPL GENERATION
# ═══════════════════════════════════════════════════════════════

def _fmt_num(n: float) -> str:
    if isinstance(n, int):
        return str(n)
    r = round(n, 6)
    return str(int(r)) if r == int(r) else str(r)


def _calculate_bezier_handles(kf_prev, kf_curr, kf_next, smoothness=0.5):
    """
    Calculate smooth RH/LH bezier handles for a keyframe.
    
    Args:
        kf_prev: Previous keyframe {'t', 'v'} (None for first keyframe)
        kf_curr: Current keyframe {'t', 'v'}
        kf_next: Next keyframe {'t', 'v'} (None for last keyframe)
        smoothness: 0-1, how smooth the curve should be
    
    Returns:
        (rh, lh) tuple where each is {'t', 'v'} or None
    """
    rh = None
    lh = None
    
    if kf_next:
        # Calculate RH (outgoing handle)
        dt_out = kf_next["t"] - kf_curr["t"]
        dv_out = kf_next["v"] - kf_curr["v"]
        slope_out = dv_out / dt_out if dt_out > 0 else 0
        rh_t = kf_curr["t"] + dt_out * smoothness
        rh_v = kf_curr["v"] + slope_out * dt_out * smoothness
        rh = {"t": rh_t, "v": rh_v}
    
    if kf_prev:
        # Calculate LH (incoming handle)
        dt_in = kf_curr["t"] - kf_prev["t"]
        dv_in = kf_curr["v"] - kf_prev["v"]
        slope_in = dv_in / dt_in if dt_in > 0 else 0
        lh_t = kf_curr["t"] - dt_in * smoothness
        lh_v = kf_curr["v"] - slope_in * dt_in * smoothness
        lh = {"t": lh_t, "v": lh_v}
    
    return rh, lh


def points_to_spl_keyframes(points: list, duration: float,
                             start_val: float, end_val: float) -> list:
    """
    Convert sampled points to SPL keyframes with proper bezier handles.
    Uses intelligent point reduction with handle calculation.
    """
    if not points:
        return [{"t": 0, "v": start_val}, {"t": round(duration), "v": end_val}]

    rng = end_val - start_val
    # Flat case: when start=end the physics shape would collapse to a line.
    # Use a virtual ±1.5 range centered on the value so the curve still oscillates.
    FLAT_VIRTUAL = 3.0  # total virtual range (±1.5)
    flat = abs(rng) < 0.0001
    
    # Step 1: Extract key points (peaks, valleys, inflections)
    key_indices = [0]  # Always include first point
    
    for i in range(1, len(points) - 1):
        prev_v = points[i - 1]["v"]
        curr_v = points[i]["v"]
        next_v = points[i + 1]["v"]
        
        # Check for peaks and valleys
        is_peak = curr_v > prev_v and curr_v > next_v
        is_valley = curr_v < prev_v and curr_v < next_v
        
        # Check for significant direction changes
        slope_in = curr_v - prev_v
        slope_out = next_v - curr_v
        direction_change = abs(slope_out - slope_in)
        
        if is_peak or is_valley or direction_change > 0.05:
            key_indices.append(i)
    
    key_indices.append(len(points) - 1)  # Always include last point
    
    # Step 2: Build keyframe list
    kfs = []
    for idx in key_indices:
        if flat:
            # Center the oscillation around start_val using virtual range
            kfs.append({
                "t": round(points[idx]["t"] * duration),
                "v": start_val + (points[idx]["v"] - 0.5) * FLAT_VIRTUAL
            })
        else:
            kfs.append({
                "t": round(points[idx]["t"] * duration),
                "v": start_val + points[idx]["v"] * rng
            })
    
    # Step 3: Calculate bezier handles for smooth curves
    result = []
    for i, kf in enumerate(kfs):
        kf_out = dict(kf)  # Copy
        
        # Calculate handles if we have neighbors
        kf_prev = kfs[i - 1] if i > 0 else None
        kf_next = kfs[i + 1] if i < len(kfs) - 1 else None
        
        rh, lh = _calculate_bezier_handles(kf_prev, kf, kf_next)
        
        if rh:
            kf_out["rh"] = rh
        if lh:
            kf_out["lh"] = lh
        
        result.append(kf_out)
    
    # Remove duplicates
    seen = set()
    unique = []
    for k in result:
        if k["t"] not in seen:
            seen.add(k["t"])
            unique.append(k)
    
    return unique


def generate_spl(keyframes: list) -> str:
    lines = ["BezierSpline {", "\tKeyFrames = {"]
    for i, k in enumerate(keyframes):
        entry = f"\t\t[{k['t']}] =  {_fmt_num(k['v'])}"
        if "rh" in k:
            entry += f", RH = {{ {k['rh']['t']}, {_fmt_num(k['rh']['v'])} }}"
        if "lh" in k:
            entry += f", LH = {{ {k['lh']['t']}, {_fmt_num(k['lh']['v'])} }}"
        entry += " }"
        if i < len(keyframes) - 1:
            entry += ","
        lines.append(entry)
    lines.append("\t}")
    lines.append("}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# EDIT PAGE KEYFRAME WATCHER
# ═══════════════════════════════════════════════════════════════

import json
import time
from datetime import datetime


class EditPageWatcher:
    """
    Background watcher for Edit page Inspector keyframes.
    Auto-records keyframe changes as you work in Resolve.
    """
    
    CACHE_FILE = os.path.join(get_data_dir(), "edit_keyframe_cache.json")
    
    # Properties to monitor
    WATCH_PROPS = {
        "ZoomX": {"label": "Zoom X", "category": "Transform"},
        "ZoomY": {"label": "Zoom Y", "category": "Transform"},
        "Pan": {"label": "Position X", "category": "Transform"},
        "Tilt": {"label": "Position Y", "category": "Transform"},
        "RotationAngle": {"label": "Rotation", "category": "Transform"},
        "AnchorPointX": {"label": "Anchor X", "category": "Transform"},
        "AnchorPointY": {"label": "Anchor Y", "category": "Transform"},
        "Pitch": {"label": "Pitch", "category": "Transform"},
        "Yaw": {"label": "Yaw", "category": "Transform"},
        "CropLeft": {"label": "Crop Left", "category": "Cropping"},
        "CropRight": {"label": "Crop Right", "category": "Cropping"},
        "CropTop": {"label": "Crop Top", "category": "Cropping"},
        "CropBottom": {"label": "Crop Bottom", "category": "Cropping"},
    }
    
    def __init__(self, poll_interval=0.5):
        self.poll_interval = poll_interval
        self.resolve = None
        self.project = None
        self.timeline = None
        self.watching = False
        self.watch_thread = None
        self.last_values = {}
        self.cache = {"clips": {}, "last_updated": None}
        self._load_cache()
        self._connect()
    
    def _load_cache(self):
        """Load cached keyframes from file"""
        if os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, 'r') as f:
                    self.cache = json.load(f)
            except:
                self.cache = {"clips": {}, "last_updated": None}
    
    def _save_cache(self):
        """Save cache to file"""
        try:
            self.cache["last_updated"] = datetime.now().isoformat()
            with open(self.CACHE_FILE, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            print(f"[Watcher] Save error: {e}")
    
    def _connect(self):
        try:
            import DaVinciResolveScript as dvr
            self.resolve = dvr.scriptapp("Resolve")
            if self.resolve:
                self.project = self.resolve.GetProjectManager().GetCurrentProject()
                self.timeline = self.project.GetCurrentTimeline() if self.project else None
        except:
            pass
    
    def _get_clip_id(self, clip):
        """Generate unique clip ID"""
        try:
            return f"{clip.GetName()}_{clip.GetStart()}_{clip.GetEnd()}"
        except:
            return str(id(clip))
    
    def _poll_once(self):
        """Single poll iteration"""
        if not self.timeline:
            self._connect()
            return
        
        clip = self.timeline.GetCurrentVideoItem()
        if not clip:
            return
        
        clip_id = self._get_clip_id(clip)
        current_tc = self.timeline.GetCurrentTimecode()
        
        # Init clip in cache
        if clip_id not in self.cache["clips"]:
            self.cache["clips"][clip_id] = {
                "name": clip.GetName(),
                "timeline": self.timeline.GetName() if self.timeline else "Unknown",
                "start": clip.GetStart(),
                "end": clip.GetEnd(),
                "keyframes": {}
            }
        
        if clip_id not in self.last_values:
            self.last_values[clip_id] = {}
        
        # Check each property
        for prop, info in self.WATCH_PROPS.items():
            try:
                current_value = clip.GetProperty(prop)
                if current_value is None:
                    continue
                
                prev = self.last_values[clip_id].get(prop)
                current_float = float(current_value)
                
                # Detect change (new keyframe!)
                if prev is not None and abs(current_float - prev) > 0.0001:
                    # Record it
                    if prop not in self.cache["clips"][clip_id]["keyframes"]:
                        self.cache["clips"][clip_id]["keyframes"][prop] = []
                    
                    self.cache["clips"][clip_id]["keyframes"][prop].append({
                        "frame": current_tc,
                        "value": current_float,
                        "label": info["label"],
                        "category": info["category"],
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    self._save_cache()
                    print(f"[Watcher] 🎬 {info['label']} keyframe at {current_tc}: {current_float}")
                
                self.last_values[clip_id][prop] = current_float
                
            except:
                pass
    
    def _watch_loop(self):
        """Background watch loop"""
        print("[Watcher] 👁️  Edit page watcher started")
        while self.watching:
            self._poll_once()
            time.sleep(self.poll_interval)
        print("[Watcher] ⏹️  Stopped")
    
    def start(self):
        """Start watching"""
        if self.watching:
            return
        self.watching = True
        self.watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.watch_thread.start()
    
    def stop(self):
        """Stop watching"""
        self.watching = False
        if self.watch_thread:
            self.watch_thread.join(timeout=1)
        self._save_cache()
    
    def get_keyframes(self, clip_name=None, timeline_name=None):
        """
        Get recorded keyframes for use by the tool
        Returns: {property: [{frame, value, label}, ...]}
        """
        result = {}
        
        for clip_id, clip_data in self.cache["clips"].items():
            # Filter by clip name
            if clip_name and clip_data.get("name") != clip_name:
                continue
            # Filter by timeline
            if timeline_name and clip_data.get("timeline") != timeline_name:
                continue
            
            for prop, kfs in clip_data.get("keyframes", {}).items():
                if prop not in result:
                    result[prop] = []
                
                for kf in kfs:
                    result[prop].append({
                        "frame": kf["frame"],
                        "value": kf["value"],
                        "label": kf["label"],
                        "category": kf["category"]
                    })
        
        # Sort by frame
        for prop in result:
            result[prop].sort(key=lambda x: x["frame"])
        
        return result
    
    def clear_cache(self, timeline_name=None, clip_name=None):
        """
        Clear cached keyframes
        - No args: Clear ALL
        - timeline_name: Clear specific timeline
        - clip_name: Clear specific clip
        """
        if timeline_name is None and clip_name is None:
            # Clear all
            self.cache = {"clips": {}, "last_updated": None}
            count = "all"
        else:
            # Filtered clear
            to_remove = []
            for clip_id, clip_data in self.cache["clips"].items():
                match = False
                if timeline_name and clip_data.get("timeline") == timeline_name:
                    match = True
                if clip_name and clip_data.get("name") == clip_name:
                    match = True
                
                if match:
                    to_remove.append(clip_id)
            
            for clip_id in to_remove:
                del self.cache["clips"][clip_id]
            
            count = len(to_remove)
        
        self._save_cache()
        return count
    
    def get_cache_info(self):
        """Get cache statistics"""
        clip_count = len(self.cache["clips"])
        total_keyframes = sum(
            len(kfs) 
            for clip in self.cache["clips"].values() 
            for kfs in clip.get("keyframes", {}).values()
        )
        timelines = set(clip.get("timeline", "Unknown") 
                       for clip in self.cache["clips"].values())
        
        return {
            "clips": clip_count,
            "keyframes": total_keyframes,
            "timelines": list(timelines),
            "last_updated": self.cache.get("last_updated")
        }


# ═══════════════════════════════════════════════════════════════
# PUBLIC CORE CLASS
# ═══════════════════════════════════════════════════════════════

class ReveaceCore:
    SLIDER_DEFS = [
        {"id": "amplitude",  "label": "Amplitude",  "min": 0.0, "max": 3.0, "step": 0.01, "default": 1.0, "modes": ["elastic", "bounce"]},
        {"id": "duration",   "label": "Duration",   "min": 0.2, "max": 3.0, "step": 0.01, "default": 1.0, "modes": ["elastic"]},
        {"id": "gravity",    "label": "Gravity",    "min": 0.2, "max": 3.0, "step": 0.01, "default": 1.0, "modes": ["bounce"]},
        {"id": "bounciness", "label": "Bounciness", "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.5, "modes": ["bounce"]},
        {"id": "hang",       "label": "Hang",       "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.5, "modes": ["elastic", "bounce"]},
        {"id": "decay_x",    "label": "Decay X",    "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.5, "modes": ["elastic", "bounce"]},
        {"id": "decay_y",    "label": "Decay Y",    "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.5, "modes": ["elastic", "bounce"]},
    ]

    def __init__(self):
        self.bridge           = _ResolveBridge()
        self.mode             = "elastic"
        self.direction        = "out"
        self.source           = "preset"
        self.selected_preset  = "Linear"
        self.params = {
            "amplitude":  1.0,
            "duration":   1.0,
            "gravity":    1.0,
            "hang":       0.5,
            "decay_x":    0.5,
            "decay_y":    0.5,
            "bounciness": 0.5,
        }
        self.start_frame      = 0
        self.end_frame        = 60
        self.start_value      = 0.0
        self.end_value        = 1.0
        self.tool_name        = ""
        self.input_name       = ""
        self.connected        = False
        self._target_segment  = None

        # Bezier handles in normalized [0,1] space
        self.manual_rh = {"t": 0.33, "v": 0.0}
        self.manual_lh = {"t": 0.67, "v": 1.0}

        # Custom combination
        self.custom_in  = "Linear"
        self.custom_out = "Linear"
        self.keyframe_mode = "selected"  # "all" | "selected" | "custom"
        self.all_keyframes_behavior = "each_segment"

    def _is_angle_input(self) -> bool:
        """Detect if the current input is an angle/rotation based on its name."""
        name = (self.input_name or "").lower()
        angle_keywords = ["angle", "rotation", "direction", "heading", 
                          "yaw", "pitch", "roll", "orient", "azimuth", "tilt"]
        return any(kw in name for kw in angle_keywords)

    # ── Resolve ─────────────────────────────────────────────────

    def connect_resolve(self) -> bool:
        self.connected = self.bridge.connect()
        return self.connected

    def get_resolve_status(self) -> dict:
        info = self.bridge.get_product_info()
        return {
            "connected": self.bridge.is_connected(),
            "info":      info,
            "error":     getattr(self.bridge, "last_error", ""),
        }

    def get_current_page(self) -> str:
        """Get current Resolve page (Edit, Fusion, Color, etc.)"""
        if not self.bridge.is_connected():
            return ""
        try:
            info = self.bridge.get_product_info()
            return info.get("page", "").lower()
        except:
            return ""

    def fetch_keyframes_smart(self, mode: str = "recent") -> dict:
        """
        Smart keyframe targeting with two modes:

        mode="recent" → auto-targets the last spline the user touched,
                        finds adjacent keyframe pair at current playhead position.
                        User workflow: edit/add a keyframe, position playhead
                        in that segment, hit Apply.

        mode="ask"    → returns list of all animated inputs on selected node
                        for the GUI to show a picker dialog.
        """
        import traceback
        print("=== fetch_keyframes_smart CALLED ===")
        traceback.print_stack(limit=5)

        if not self.bridge.is_connected():
            return {"ok": False, "error": "Resolve not connected"}

        comp = self.bridge.get_current_comp()
        if not comp:
            return {"ok": False, "error": "No active composition"}

        current_time = float(comp.CurrentTime)

        if mode == "recent":
            spline_name = self.bridge.last_changed_spline
            print(f"[fetch_keyframes_smart] last_changed_spline: {spline_name}")

            # Filter: only trust last_changed_spline if it belongs to a selected node.
            # If user switched nodes, the old spline is irrelevant.
            if spline_name:
                try:
                    selected = comp.GetToolList(True) or {}
                    sel_tools = list(selected.values())
                    if not sel_tools:
                        active = self.bridge.get_active_tool()
                        if active:
                            sel_tools = [active]
                    owned = False
                    for sel_tool in sel_tools:
                        for inp_data in self.bridge.get_animated_inputs(sel_tool):
                            s = inp_data.get("spline")
                            if s and s.GetAttrs().get("TOOLS_Name") == spline_name:
                                owned = True
                                break
                        if owned:
                            break
                    if not owned:
                        print(f"[fetch_keyframes_smart] '{spline_name}' not on selected node — using fallback")
                        spline_name = None
                except Exception as e:
                    print(f"[fetch_keyframes_smart] ownership check error: {e}")

            _only_shape_anim = False
            if not spline_name:
                # Fallback: prefer PolyPath (Center/displacement) over direct splines,
                # then fall back to any direct BezierSpline input.
                try:
                    selected = comp.GetToolList(True)
                    selected_tools = list(selected.values()) if selected else []
                    if not selected_tools:
                        active = self.bridge.get_active_tool()
                        if active:
                            selected_tools = [active]
                    all_have_only_shape = True
                    for sel_tool in selected_tools:
                        animated = self.bridge.get_animated_inputs(sel_tool)
                        if not animated:
                            continue
                        all_have_only_shape = False
                        # Pass 1: prefer PolyPath (displacement) inputs
                        chosen = next((d for d in animated if d.get("input_type") == "polypath"), None)
                        # Pass 2: fall back to first direct BezierSpline
                        if not chosen:
                            chosen = next((d for d in animated if d.get("input_type") == "direct"), None)
                        if chosen:
                            sp = chosen.get("spline")
                            if sp:
                                spline_name = sp.GetAttrs().get("TOOLS_Name", "")
                                input_name  = chosen.get("name", "?")
                                print(f"[ReveaceSpline] Fallback → {chosen.get('input_type','?')} control: {input_name}")
                        break
                    _only_shape_anim = all_have_only_shape
                except Exception as e:
                    print(f"[ReveaceSpline] Fallback error: {e}")

            if not spline_name:
                if _only_shape_anim:
                    return {
                        "ok":    False,
                        "error": "Shape animation keyframes can't be controlled by ESpline."
                    }
                return {
                    "ok":    False,
                    "error": "No keyframes found on the selected node. "
                             "Add at least two keyframes first."
                }

            # Find the spline tool by name in the comp
            spline_tool = None
            try:
                for _, t in comp.GetToolList(False).items():
                    if t.GetAttrs().get("TOOLS_Name") == spline_name:
                        spline_tool = t
                        break
            except:
                pass

            if not spline_tool:
                return {
                    "ok":    False,
                    "error": f"Spline '{spline_name}' not found in comp."
                }

            # Guard: shape animation splines crash on value access — reject them here
            kfs_check = spline_tool.GetKeyFrames()
            if "Value" in kfs_check:
                return {
                    "ok":    False,
                    "error": "Shape animation keyframes can't be controlled by ESpline."
                }
            frames_check = sorted([f for f in kfs_check.keys() if isinstance(f, (int, float))])
            print(f"[DEBUG] fetch_keyframes_smart: Found spline '{spline_name}'")
            print(f"[DEBUG] fetch_keyframes_smart: Spline has keyframes at: {frames_check}")
            print(f"[DEBUG] fetch_keyframes_smart: Current time: {current_time}")

            # CACHE CHECK: If we already have a cached segment, check if it's still valid
            # and if the playhead is still within its bounds. This prevents adjacent_keyframes
            # from picking up newly generated physics keyframes inside the segment!
            cached_spline = getattr(self, "_target_spline_name", None)
            cached_start = getattr(self, "start_frame", None)
            cached_end = getattr(self, "end_frame", None)
            
            # Find closest keys in kfs_check to avoid float mismatch
            s_key = next((f for f in frames_check if cached_start is not None and abs(f - cached_start) < 0.001), None)
            e_key = next((f for f in frames_check if cached_end is not None and abs(f - cached_end) < 0.001), None)
            
            if (self._target_segment is not None and 
                cached_spline == spline_name and 
                cached_start is not None and cached_end is not None and 
                s_key is not None and e_key is not None and
                cached_start <= current_time <= cached_end):
                
                print(f"[DEBUG] Reusing cached segment constraints: {cached_start} to {cached_end}")
                # Re-read their values in case user moved them vertically
                left_v = kfs_check[s_key][1]
                right_v = kfs_check[e_key][1]
                
                # Update target segment values
                self._target_segment["left_frame"] = s_key
                self._target_segment["right_frame"] = e_key
                self._target_segment["left_value"] = left_v
                self._target_segment["right_value"] = right_v
                self._target_segment["kfs"] = kfs_check
                self._target_segment["spline"] = spline_tool
                
                self.start_value = left_v
                self.end_value = right_v
                
                return {
                    "ok":          True,
                    "mode":        "recent",
                    "spline_name": spline_name,
                    "start_frame": cached_start,
                    "end_frame":   cached_end,
                    "start_value": left_v,
                    "end_value":   right_v,
                }

            segment = self.bridge.get_adjacent_keyframes(spline_tool, current_time)
            if not segment:
                return {
                    "ok":    False,
                    "error": "No keyframe pair found at playhead. "
                             "Position playhead between two keyframes."
                }

            # DEBUG: Log segment info
            print("=" * 70)
            print("[DEBUG] FETCH_KEYFRAMES_SMART - Segment found:")
            print(f"  Spline: {spline_name}")
            print(f"  Current time: {current_time}")
            print(f"  Left: frame={segment['left_frame']}, value={segment['left_value']:.4f}")
            print(f"  Right: frame={segment['right_frame']}, value={segment['right_value']:.4f}")
            print(f"  All keyframes in spline: {sorted([f for f in segment['kfs'].keys() if isinstance(f, (int, float))])}")
            print("=" * 70)
            
            # Store the spline name for verification later
            self._target_spline_name = spline_name

            # Store segment for apply_to_resolve to use
            self._target_segment  = segment
            self.start_frame      = float(segment["left_frame"])
            self.end_frame        = float(segment["right_frame"])
            self.start_value      = segment["left_value"]
            self.end_value        = segment["right_value"]

            return {
                "ok":          True,
                "mode":        "recent",
                "spline_name": spline_name,
                "start_frame": self.start_frame,
                "end_frame":   self.end_frame,
                "start_value": self.start_value,
                "end_value":   self.end_value,
            }

        elif mode == "custom":
            segment = getattr(self, '_target_segment', None)
            if segment:
                return {
                    "ok": True,
                    "mode": "custom",
                    "spline_name": getattr(self, '_target_spline_name', ''),
                    "start_frame": self.start_frame,
                    "end_frame": self.end_frame,
                    "start_value": self.start_value,
                    "end_value": self.end_value,
                }
            # If no cached segment, fall back to recent behavior
            return self.fetch_keyframes_smart(mode="recent")

        elif mode == "ask":
            tool = self.bridge.get_active_tool()
            if not tool:
                return {"ok": False, "error": "No active tool selected in Fusion"}
            inputs = self.bridge.get_animated_inputs(tool)
            if not inputs:
                return {"ok": False, "error": "No animated inputs found on selected tool"}
            return {
                "ok":     True,
                "mode":   "ask",
                "inputs": [{"name": i["name"], "id": i["id"]} for i in inputs],
            }

        else:
            return {"ok": False, "error": f"Unknown mode: {mode}"}

    # ── State setters ────────────────────────────────────────────

    def set_mode(self, mode: str):
        self.mode   = mode
        self.source = "physics"
        self.invalidate_physics_cache()

    def set_direction(self, direction: str):
        self.direction = direction
        self.source    = "physics"
        self.invalidate_physics_cache()

    def set_param(self, key: str, value: float):
        self.params[key] = value
        self.source      = "physics"
        self.invalidate_physics_cache()  # Regenerate bezier keyframes on param change

    def set_handle(self, handle_type: str, t: float, v: float):
        """Set a bezier handle in normalized space. No clamping - allow any value."""
        if handle_type == "rh":
            self.manual_rh = {"t": t, "v": v}
        elif handle_type == "lh":
            self.manual_lh = {"t": t, "v": v}
        # Keep source as preset if we started from a preset, just mark as modified
        if self.source != "preset":
            self.source = "manual"
            self.selected_preset = None

    def select_preset(self, name: str):
        self.selected_preset = name
        self.source          = "preset"
        cat = PRESETS.get(name, {}).get("cat", "")

        if cat == "Bounce":
            self.mode = "bounce"
            # Set default bounce params
            self.params = {
                "amplitude": 1.0,
                "gravity": 1.0,
                "hang": 0.5,
                "decay_x": 0.5,
                "decay_y": 0.5,
                "bounciness": 0.5,
            }
        elif cat == "Elastic":
            self.mode = "elastic"
            # Set default elastic params
            self.params = {
                "amplitude": 1.0,
                "duration": 1.0,
                "hang": 0.5,
                "decay_x": 0.5,
                "decay_y": 0.5,
            }

        if "In" in name and "Out" not in name:
            self.direction = "in"
        elif "Out" in name:
            self.direction = "out"
        
        # Invalidate cache when preset changes
        self.invalidate_physics_cache()

        # Set handles for visual curve control
        # RH (right handle at start) controls start tangent
        # LH (left handle at end) controls end tangent
        # For proper bezier curves:
        # - Ease In: RH flat (near 0), LH above 1 (steep end)
        # - Ease Out: RH below 0 (steep start), LH flat (near 1)
        # - S-Curve: both flat (RH near 0, LH near 1)
        if cat in ["Easing", "Dynamic", "Special", "Step"]:
            if "Linear" in name:
                # Linear: straight line (both handles at mid)
                self.manual_rh = {"t": 0.33, "v": 0.33}  # Linear
                self.manual_lh = {"t": 0.67, "v": 0.67}  # Linear
            elif "Step" in name:
                # Step curves: sharp transition - use very steep handles
                if "Step In" in name:
                    # Step at end: hold then jump
                    self.manual_rh = {"t": 0.33, "v": 0.0}   # Flat hold
                    self.manual_lh = {"t": 0.95, "v": 2.0}   # Very steep at end
                elif "Step Out" in name:
                    # Step at start: jump then hold
                    self.manual_rh = {"t": 0.05, "v": -1.0}  # Very steep at start
                    self.manual_lh = {"t": 0.67, "v": 1.0}   # Flat hold
                elif "Step Mid" in name:
                    # Step at middle - approximate with steep curve
                    self.manual_rh = {"t": 0.45, "v": -0.5}  # Steep approach
                    self.manual_lh = {"t": 0.55, "v": 1.5}   # Steep exit
                else:
                    self.manual_rh = {"t": 0.33, "v": 0.0}
                    self.manual_lh = {"t": 0.67, "v": 1.0}
            elif "Ease In" in name and "Out" not in name:
                # Ease In: starts slow (flat), ends fast (steep)
                # RH near 0 (flat start), LH > 1 (steep approach to end)
                strength = 1.5 if "Cubic" in name or "Expo" in name else 1.0
                self.manual_rh = {"t": 0.33, "v": 0.0}           # Flat start
                self.manual_lh = {"t": 0.67, "v": 1.0 + 0.5 * strength}  # Steep end
            elif "Ease Out" in name and "In" not in name:
                # Ease Out: starts fast (steep), ends slow (flat)
                # RH < 0 (steep start), LH near 1 (flat end)
                strength = 1.5 if "Cubic" in name or "Expo" in name else 1.0
                self.manual_rh = {"t": 0.33, "v": -0.5 * strength}  # Steep start
                self.manual_lh = {"t": 0.67, "v": 1.0}              # Flat end
            elif "In-Out" in name:
                # S-Curve: smooth both ends
                self.manual_rh = {"t": 0.33, "v": 0.0}   # Flat start
                self.manual_lh = {"t": 0.67, "v": 1.0}   # Flat end
            elif "S-Curve" in name:
                # True S-Curve: starts slow, middle fast, ends slow
                self.manual_rh = {"t": 0.33, "v": 0.1}   # Slight ease in
                self.manual_lh = {"t": 0.67, "v": 0.9}   # Slight ease out
            elif "Overshoot" in name:
                # Overshoot: goes past target then settles
                self.manual_rh = {"t": 0.4, "v": 0.5}    # Normal start
                self.manual_lh = {"t": 0.9, "v": 1.2}    # Overshoot end
            elif "Anticipate" in name:
                # Anticipate: goes backward first
                self.manual_rh = {"t": 0.1, "v": -0.2}   # Backward first
                self.manual_lh = {"t": 0.6, "v": 1.0}    # Normal end
            elif "Reverse" in name:
                # Reverse Ease: fast edges, slow middle
                self.manual_rh = {"t": 0.2, "v": 0.6}    # Quick start
                self.manual_lh = {"t": 0.8, "v": 0.4}    # Quick end
            elif "Circular" in name:
                # Circular easing: smooth curve based on circle arc
                if "In" in name and "Out" not in name:
                    self.manual_rh = {"t": 0.33, "v": 0.0}   # Flat start
                    self.manual_lh = {"t": 0.67, "v": 1.3}   # Steep end
                elif "Out" in name and "In" not in name:
                    self.manual_rh = {"t": 0.33, "v": -0.3}  # Steep start
                    self.manual_lh = {"t": 0.67, "v": 1.0}   # Flat end
                else:  # In-Out
                    self.manual_rh = {"t": 0.33, "v": 0.0}   # Flat start
                    self.manual_lh = {"t": 0.67, "v": 1.0}   # Flat end
            elif "Back" in name:
                # Back easing: slight overshoot with pull-back
                if "In" in name and "Out" not in name:
                    self.manual_rh = {"t": 0.2, "v": -0.15}  # Pull back first
                    self.manual_lh = {"t": 0.67, "v": 1.0}   # Normal end
                else:  # Back Out
                    self.manual_rh = {"t": 0.33, "v": 0.5}   # Normal start
                    self.manual_lh = {"t": 0.8, "v": 1.1}    # Overshoot then settle
            elif "Strong Overshoot" in name:
                # Heavy overshoot: goes way past target
                self.manual_rh = {"t": 0.35, "v": 0.3}   # Moderate start
                self.manual_lh = {"t": 0.9, "v": 1.35}   # Big overshoot
            elif "Whip" in name:
                # Whip: sharp acceleration then snap back
                self.manual_rh = {"t": 0.1, "v": -0.25}  # Pull back sharply
                self.manual_lh = {"t": 0.7, "v": 0.9}    # Settle from above
            elif "Double Back" in name:
                # Double oscillation: back and forth twice
                self.manual_rh = {"t": 0.25, "v": 0.15}  # First forward
                self.manual_lh = {"t": 0.75, "v": 0.85}  # Second oscillation
            elif "Smooth Damp" in name:
                # Critically damped spring: settles smoothly
                self.manual_rh = {"t": 0.3, "v": 0.2}    # Quick start
                self.manual_lh = {"t": 0.85, "v": 0.98}  # Very gentle settle
            elif "Slow Mo" in name:
                # Cinematic slow-motion: holds in middle
                self.manual_rh = {"t": 0.35, "v": 0.25}  # Slow acceleration
                self.manual_lh = {"t": 0.65, "v": 0.75}  # Slow deceleration
            elif "Logarithmic" in name:
                # Logarithmic curve: very slow start then rapid finish
                self.manual_rh = {"t": 0.25, "v": 0.0}   # Very flat start
                self.manual_lh = {"t": 0.75, "v": 1.15}  # Late steep rise
            else:
                # Default smooth curve (S-curve)
                self.manual_rh = {"t": 0.33, "v": 0.0}
                self.manual_lh = {"t": 0.67, "v": 1.0}

    def clear_preset(self):
        self.selected_preset = None
        self.source          = "manual"

    # ── Queries ──────────────────────────────────────────────────

    def is_physics(self) -> bool:
        return self.source == "physics" or (
            self.source == "preset" and self.selected_preset and
            PRESETS.get(self.selected_preset, {}).get("cat") in ["Bounce", "Elastic"]
        )

    def is_handle_mode(self) -> bool:
        return not self.is_physics()
    
    def _generate_physics_bezier_keyframes(self) -> list:
        """
        Convert physics curve (elastic/bounce) to normalized bezier keyframes (0-1 range).
        Returns list of {t, v, lh?, rh?} that can be used for preview and Resolve.
        """
        # Sample the physics curve
        points = _sample_physics_curve(self.mode, self.direction, self.params, steps=200)
        
        # Extract key points (peaks, valleys, inflections)
        key_indices = [0]
        
        for i in range(1, len(points) - 1):
            prev_v = points[i - 1]["v"]
            curr_v = points[i]["v"]
            next_v = points[i + 1]["v"]
            
            is_peak = curr_v > prev_v and curr_v > next_v
            is_valley = curr_v < prev_v and curr_v < next_v
            
            slope_in = curr_v - prev_v
            slope_out = next_v - curr_v
            direction_change = abs(slope_out - slope_in)
            
            if is_peak or is_valley or direction_change > 0.05:
                key_indices.append(i)
        
        key_indices.append(len(points) - 1)
        
        # Build normalized bezier keyframes
        keyframes = []
        
        for idx_pos, i in enumerate(key_indices):
            pt = points[i]
            kf = {"t": pt["t"], "v": pt["v"]}
            
            is_first = (idx_pos == 0)
            is_last = (idx_pos == len(key_indices) - 1)
            
            # Calculate RH handle (outgoing)
            if not is_last:
                next_i = key_indices[idx_pos + 1]
                next_pt = points[next_i]
                
                # Time and value differences
                dt = next_pt["t"] - pt["t"]
                dv = next_pt["v"] - pt["v"]
                
                # RH handle at 1/3 of the way to next keyframe
                rh_t = pt["t"] + dt / 3.0
                slope = dv / dt if dt > 0 else 0
                rh_v = pt["v"] + slope * dt / 3.0
                
                kf["rh"] = {"t": rh_t, "v": rh_v}
            
            # Calculate LH handle (incoming)
            if not is_first:
                prev_i = key_indices[idx_pos - 1]
                prev_pt = points[prev_i]
                
                dt = pt["t"] - prev_pt["t"]
                dv = pt["v"] - prev_pt["v"]
                
                # LH handle at 1/3 back from current keyframe
                lh_t = pt["t"] - dt / 3.0
                slope = dv / dt if dt > 0 else 0
                lh_v = pt["v"] - slope * dt / 3.0
                
                kf["lh"] = {"t": lh_t, "v": lh_v}
            
            keyframes.append(kf)
        
        return keyframes
    
    def get_physics_bezier_keyframes(self) -> list:
        """Get cached or generate physics bezier keyframes."""
        if not hasattr(self, '_physics_bezier_cache'):
            self._physics_bezier_cache = {}
        
        # Create cache key from current params
        cache_key = (
            self.mode,
            self.direction,
            self.params.get("amplitude"),
            self.params.get("duration"),
            self.params.get("gravity"),
            self.params.get("hang"),
            self.params.get("decay_x"),
            self.params.get("decay_y"),
            self.params.get("bounciness"),
        )
        
        if cache_key not in self._physics_bezier_cache:
            self._physics_bezier_cache[cache_key] = self._generate_physics_bezier_keyframes()
        
        return self._physics_bezier_cache[cache_key]
    
    def invalidate_physics_cache(self):
        """Clear physics bezier cache when params change."""
        self._physics_bezier_cache = {}

    def get_curve_points(self, steps: int = 200) -> list:
        """
        Get curve points for preview.
        Uses handles for ALL non-physics curves so preview matches output.
        """
        if self.is_physics():
            # Physics curves (bounce/elastic) use their own math
            return _sample_physics_curve(self.mode, self.direction, self.params, steps=steps)
        else:
            # ALL other curves use the bezier handles
            # This ensures the preview shows exactly what will be applied
            return self._get_curve_from_handles(steps=steps)

    def get_handles_for_preview(self) -> dict:
        """Return handles in normalized [0,1] space for the web preview."""
        # Return handles for ALL non-physics curves (including custom)
        if self.is_physics():
            return None
        return {
            "rh": {"t": self.manual_rh["t"], "v": self.manual_rh["v"]},
            "lh": {"t": self.manual_lh["t"], "v": self.manual_lh["v"]},
        }

    def _get_physics_keyframes_simplified(self, duration: float, start_val: float, end_val: float) -> list:
        """
        Generate keyframes for physics curves (elastic/bounce).
        Samples the physics curve and extracts key points (peaks/valleys) with proper bezier handles.
        """
        # Sample the physics curve at high resolution
        points = _sample_physics_curve(self.mode, self.direction, self.params, steps=200)
        
        # Use the intelligent point reduction to get keyframes with handles
        kfs = points_to_spl_keyframes(points, duration, start_val, end_val)
        
        # Offset frame numbers by start_frame
        for kf in kfs:
            kf["t"] = round(self.start_frame + kf["t"])
            if "rh" in kf:
                kf["rh"]["t"] = round(self.start_frame + kf["rh"]["t"])
            if "lh" in kf:
                kf["lh"]["t"] = round(self.start_frame + kf["lh"]["t"])
        
        return kfs

    def get_spl(self) -> str:
        duration = self.end_frame - self.start_frame or 1.0
        s = self.start_value
        e = self.end_value
        d = e - s

        if self.is_physics():
            # Physics curves (bounce/elastic) - use SIMPLIFIED keyframes
            kfs = self._get_physics_keyframes_simplified(duration, s, e)
        else:
            # ALL other curves (preset, custom, manual, step) use the HANDLES
            # This ensures what you see in preview is what you get
            kfs = [
                {"t": self.start_frame, "v": s,
                 "rh": {"t": self.start_frame + self.manual_rh["t"] * duration,
                         "v": s + self.manual_rh["v"] * d}},
                {"t": self.end_frame,   "v": e,
                 "lh": {"t": self.end_frame + (self.manual_lh["t"] - 1.0) * duration,
                         "v": e + (self.manual_lh["v"] - 1.0) * d}},
            ]
        return generate_spl(kfs)

    def _get_curve_from_handles(self, steps: int = 100) -> list:
        """
        Generate curve points from the current bezier handles.
        Returns list of {t, v} points in normalized [0,1] space.
        
        CRITICAL: Uses time-based bezier to match Resolve's behavior.
        Handles are at (manual_rh["t"], manual_rh["v"]) and (manual_lh["t"], manual_lh["v"]).
        """
        points = []
        
        # Bezier control points in (time, value) space
        # P0 = start (0, 0)
        # P1 = RH handle (manual_rh["t"], manual_rh["v"])
        # P2 = LH handle (manual_lh["t"], manual_lh["v"])
        # P3 = end (1, 1)
        p0_t, p0_v = 0.0, 0.0
        p1_t, p1_v = self.manual_rh["t"], self.manual_rh["v"]
        p2_t, p2_v = self.manual_lh["t"], self.manual_lh["v"]
        p3_t, p3_v = 1.0, 1.0
        
        # Sample the bezier curve
        for i in range(steps + 1):
            t = i / steps
            mt = 1.0 - t
            
            # Cubic bezier: B(t) = (1-t)^3 * P0 + 3(1-t)^2*t * P1 + 3(1-t)*t^2 * P2 + t^3 * P3
            curve_t = (mt * mt * mt * p0_t + 
                       3 * mt * mt * t * p1_t + 
                       3 * mt * t * t * p2_t + 
                       t * t * t * p3_t)
            curve_v = (mt * mt * mt * p0_v + 
                       3 * mt * mt * t * p1_v + 
                       3 * mt * t * t * p2_v + 
                       t * t * t * p3_v)
            
            points.append({"t": curve_t, "v": curve_v})
        
        return points

    def apply_polypath_elastic(self, input_name: str = "Center") -> dict:
        """
        Generate elastic/bounce PolyPath waypoints for a Point input.
        Reads existing PolyPath start/end XY, generates curve geometry,
        pastes new PolyPath and connects it.
        """
        if not self.bridge.is_connected():
            return {"ok": False, "error": "Resolve not connected"}

        tool = self.bridge.get_active_tool()
        if not tool:
            return {"ok": False, "error": "No active tool"}

        def curve_fn(t, **kwargs):
            return _eval_physics(t, self.mode, self.direction, self.params)

        return self.bridge.generate_elastic_polypath(
            tool       = tool,
            input_name = input_name,
            curve_fn   = curve_fn,
            params     = self.params,
        )

    def _apply_polypath_all_segs(self, spline, spline_name: str, frames: list, js_keyframes: list, comp) -> int:
        """Read once, build ALL segments into one write_kfs, single SetKeyFrames write.
        Returns number of segments written, or 0 on failure."""
        try:
            kfs = spline.GetKeyFrames()
        except Exception as e:
            print(f"[POLYPATH ALL-SEGS] GetKeyFrames failed: {e}")
            return 0

        numeric_frames = sorted(k for k in kfs if isinstance(k, (int, float)))
        if len(numeric_frames) < 2:
            return 0

        # Start from a float-normalised copy of the current spline state
        write_kfs = {float(k) if isinstance(k, (int, float)) else k: v for k, v in kfs.items()}

        seg_count = 0
        for i in range(len(frames) - 1):
            lf = frames[i]
            rf = frames[i + 1]
            lv_raw = kfs.get(lf) or kfs.get(float(lf))
            rv_raw = kfs.get(rf) or kfs.get(float(rf))
            lv = float(lv_raw[1] if isinstance(lv_raw, dict) else (lv_raw or 0))
            rv = float(rv_raw[1] if isinstance(rv_raw, dict) else (rv_raw or 0))

            sf = float(lf)
            ef = float(rf)
            duration    = rf - lf
            value_range = rv - lv

            try:
                kf_table = self._build_kf_table_from_preview(
                    js_keyframes, lf, duration, lv, value_range
                )
            except Exception as e:
                print(f"[POLYPATH ALL-SEGS] kf_table build failed for seg {lf}→{rf}: {e}")
                continue

            try:
                start_entry = dict(next(v for k, v in kf_table.items() if isinstance(k, (int, float)) and abs(k - sf) < 0.001))
                end_entry   = dict(next(v for k, v in kf_table.items() if isinstance(k, (int, float)) and abs(k - ef) < 0.001))
            except StopIteration:
                print(f"[POLYPATH ALL-SEGS] no matching kf_table entry for {sf} or {ef}")
                continue

            # Preserve LH at start if this is an interior keyframe
            if "LH" not in start_entry and any(f < sf - 0.001 for f in numeric_frames):
                existing = write_kfs.get(sf)
                if isinstance(existing, dict) and "LH" in existing:
                    start_entry["LH"] = existing["LH"]

            # Preserve RH at end if this is an interior keyframe
            if "RH" not in end_entry and any(f > ef + 0.001 for f in numeric_frames):
                existing = write_kfs.get(ef)
                if isinstance(existing, dict) and "RH" in existing:
                    end_entry["RH"] = existing["RH"]

            start_entry.pop("Flags", None)
            end_entry.pop("Flags", None)

            # Strip old intermediate frames within this segment's range
            for fk in list(write_kfs.keys()):
                if isinstance(fk, (int, float)) and sf < float(fk) < ef:
                    del write_kfs[fk]

            # Merge ALL kf_table frames (covers elastic/bounce intermediates)
            for k, v in kf_table.items():
                if isinstance(k, (int, float)):
                    write_kfs[float(k)] = v

            # Re-apply boundary entries with handle preservation on top
            write_kfs[sf] = start_entry
            write_kfs[ef] = end_entry
            seg_count += 1
            print(f"[POLYPATH ALL-SEGS] seg {sf}→{ef}: start={start_entry}, end={end_entry}")

        if seg_count == 0:
            return 0

        first_sf = float(frames[0])
        comp.Lock()
        try:
            self.bridge._our_write_timestamp = time.time()
            spline.SetKeyFrames(write_kfs, True)
            if first_sf in write_kfs:
                spline.SetKeyFrames({first_sf: write_kfs[first_sf]}, False)
                print(f"[POLYPATH ALL-SEGS] forced first frame {first_sf}: {write_kfs[first_sf]}")
            self.bridge._cached_kfs[spline_name] = dict(write_kfs)
            comp.Unlock()
        except Exception as e:
            try:
                comp.Unlock()
            except Exception:
                pass
            print(f"[POLYPATH ALL-SEGS] write ERROR: {e}")
            return 0

        return seg_count

    def apply_to_resolve(self, js_keyframes: list = None, segment: dict = None) -> dict:
        seg = segment or self._target_segment
        if not seg:
            return {"ok": False, "error": "No target segment"}
        if not js_keyframes or len(js_keyframes) < 2:
            return {"ok": False, "error": "No curve data"}

        spline      = seg["spline"]
        start_frame = seg["left_frame"]
        end_frame   = seg["right_frame"]
        start_value = seg["left_value"]
        end_value   = seg["right_value"]
        spline_name = seg["spline"].GetAttrs().get("TOOLS_Name") if seg.get("spline") else (seg.get("spline_name") or getattr(self, "_target_spline_name", None))
        duration    = end_frame - start_frame
        value_range = end_value - start_value

        is_polypath = seg.get("input_type") == "polypath" or str(spline_name or "").endswith("Displacement")
        if is_polypath:
            base_kfs = dict(spline.GetKeyFrames())
        else:
            base_kfs = dict(self.bridge._cached_kfs.get(spline_name) or spline.GetKeyFrames())

        kf_table = self._build_kf_table_from_preview(
            js_keyframes, start_frame, duration, start_value, value_range
        )
        
        print(f"[APPLY DEBUG] mode={self.mode}, flat={abs(value_range) < 0.0001}, kf_table keys={sorted([k for k in kf_table.keys() if isinstance(k, (int, float))])}")

        sf = float(start_frame)
        ef = float(end_frame)
        
        # Guard: empty kf_table (can happen if clamp removed all keyframes)
        numeric_kf_keys = [k for k in kf_table.keys() if isinstance(k, (int, float))]
        if not numeric_kf_keys:
            print(f"[APPLY DEBUG] ERROR: kf_table is empty after build!")
            return {"ok": False, "error": "Generated keyframe table is empty. Try with different start/end frames."}
        
        start_matches = [v for k, v in kf_table.items() if isinstance(k, (int, float)) and abs(k - sf) < 0.001]
        end_matches   = [v for k, v in kf_table.items() if isinstance(k, (int, float)) and abs(k - ef) < 0.001]
        
        if not start_matches:
            print(f"[APPLY DEBUG] ERROR: No start keyframe at {sf}. Keys: {numeric_kf_keys}")
            return {"ok": False, "error": f"No start keyframe generated at frame {sf}"}
        if not end_matches:
            print(f"[APPLY DEBUG] ERROR: No end keyframe at {ef}. Keys: {numeric_kf_keys}")
            return {"ok": False, "error": f"No end keyframe generated at frame {ef}"}
        
        start_entry = dict(start_matches[0])
        end_entry   = dict(end_matches[0])

        numeric_frames = sorted(k for k in base_kfs if isinstance(k, (int, float)))

        # Fill LH on start_frame only if preset didn't supply one and a prior keyframe exists
        if "LH" not in start_entry and any(f < sf - 0.001 for f in numeric_frames):
            base_start = next((base_kfs[k] for k in numeric_frames if abs(k - sf) < 0.001), None)
            if isinstance(base_start, dict) and "LH" in base_start:
                start_entry["LH"] = base_start["LH"]

        # Fill RH on end_frame only if preset didn't supply one and a later keyframe exists
        if "RH" not in end_entry and any(f > ef + 0.001 for f in numeric_frames):
            base_end = next((base_kfs[k] for k in numeric_frames if abs(k - ef) < 0.001), None)
            if isinstance(base_end, dict) and "RH" in base_end:
                end_entry["RH"] = base_end["RH"]

        start_entry.pop("Flags", None)
        end_entry.pop("Flags", None)

        # Start from base_kfs with float keys, but strip old intermediate frames
        # within our segment range so elastic/bounce don't accumulate stale frames.
        write_kfs = {float(k) if isinstance(k, (int, float)) else k: v
                     for k, v in base_kfs.items()
                     if not (isinstance(k, (int, float)) and sf < float(k) < ef)}

        # Merge ALL kf_table frames (covers intermediate elastic/bounce keyframes)
        for k, v in kf_table.items():
            if isinstance(k, (int, float)):
                write_kfs[float(k)] = v

        # Re-apply boundary entries with handle preservation on top
        write_kfs[sf] = start_entry
        write_kfs[ef] = end_entry

        comp = self.bridge.get_current_comp()
        comp.Lock()
        try:
            print(f"[WRITE DEBUG] write_kfs[start_frame]: {write_kfs.get(start_frame)}")
            print(f"[WRITE DEBUG] base_kfs[start_frame]: {base_kfs.get(start_frame)}")
            print(f"[WRITE DEBUG] cache hit: {spline_name in self.bridge._cached_kfs}")
            print(f"[BRANCH DEBUG] input_type={seg.get('input_type')}, spline_name={spline_name}, is_polypath={is_polypath}")
            if is_polypath:
                self.bridge._our_write_timestamp = time.time()
                spline.SetKeyFrames(write_kfs, True)
                sf = float(start_frame)
                if sf in write_kfs:
                    spline.SetKeyFrames({sf: write_kfs[sf]}, False)
                self.bridge._cached_kfs[spline_name] = dict(write_kfs)
            else:
                print("[BRANCH DEBUG] using GetKeyFrames for cache")
                self.bridge._our_write_timestamp = time.time()
                spline.SetKeyFrames(write_kfs, True)
                self.bridge._cached_kfs[spline_name] = dict(spline.GetKeyFrames())
            comp.Unlock()
        except Exception as e:
            try:
                comp.Unlock()
            except Exception:
                pass
            return {"ok": False, "error": str(e)}
        print(f"[CACHE UPDATE] {spline_name}: {self.bridge._cached_kfs[spline_name].get(start_frame)}")
        return {"ok": True}

    def apply_all_keyframes(self, js_keyframes: list = None) -> dict:
        if not self.bridge.is_connected():
            return {"ok": False, "error": "Resolve not connected"}

        comp = self.bridge.get_current_comp()
        if not comp:
            return {"ok": False, "error": "No active composition"}

        selected = comp.GetToolList(True)
        if not selected:
            return {"ok": False, "error": "No tools selected in Fusion"}

        if js_keyframes is None:
            js_keyframes = self._last_js_keyframes if hasattr(self, "_last_js_keyframes") else None
        if not js_keyframes:
            return {"ok": False, "error": "No curve data to apply"}

        total_segments = 0
        total_tools    = 0

        for tool in selected.values():
            tool_hit = False
            for inp in self.bridge.get_animated_inputs(tool):
                spline = inp.get("spline")
                if not spline:
                    continue

                spline_name  = spline.GetAttrs().get("TOOLS_Name", "")
                is_polypath  = inp.get("input_type") == "polypath" or spline_name.endswith("Displacement")

                try:
                    kfs = spline.GetKeyFrames()
                except Exception:
                    continue
                frames = sorted(k for k in kfs if isinstance(k, (int, float)))
                if len(frames) < 2:
                    continue

                if is_polypath:
                    n = self._apply_polypath_all_segs(spline, spline_name, frames, js_keyframes, comp)
                    if n:
                        tool_hit = True
                        total_segments += n
                        print(f"[ALL-KF POLYPATH] {inp.get('name','?')} — {n} segments in single write")
                else:
                    seg_count = 0
                    for i in range(len(frames) - 1):
                        lf = frames[i]
                        rf = frames[i + 1]
                        lv_raw = kfs[lf]
                        rv_raw = kfs[rf]
                        lv = float(lv_raw[1] if isinstance(lv_raw, dict) else lv_raw)
                        rv = float(rv_raw[1] if isinstance(rv_raw, dict) else rv_raw)

                        segment = {
                            "spline":      spline,
                            "spline_name": spline_name,
                            "left_frame":  lf,
                            "right_frame": rf,
                            "left_value":  lv,
                            "right_value": rv,
                        }
                        result = self.apply_to_resolve(js_keyframes, segment=segment)
                        if result.get("ok"):
                            seg_count += 1

                    if seg_count:
                        tool_hit = True
                        total_segments += seg_count
                        print(f"[ALL-KF] {inp.get('name','?')} — {seg_count} segments applied")

            if tool_hit:
                total_tools += 1

        if total_segments == 0:
            return {"ok": False, "error": "No keyframe segments found on selected tools"}

        return {"ok": True, "total_segments": total_segments, "tools": total_tools}

    def apply_recent_all(self, js_keyframes: list) -> dict:
        """Apply curve to the recently-changed control across ALL selected tools.

        Finds the input name (e.g. 'Center', 'Size') that owns the last-changed
        spline, then applies the curve to every consecutive keyframe pair of
        that same-named input on every selected tool.  Keyframe VALUES are
        preserved — only the curve shape between pairs changes.
        """
        if not self.bridge.is_connected():
            return {"ok": False, "error": "Resolve not connected"}

        comp = self.bridge.get_current_comp()
        if not comp:
            return {"ok": False, "error": "No active composition"}

        spline_name = self.bridge.last_changed_spline
        if not spline_name:
            return {"ok": False, "error": "No recently changed control. Edit a keyframe first."}

        # Use cached input name — set by the watcher when it detected the change.
        # Fall back to a scan only if the cache is empty (edge case on first launch).
        target_input_name = self.bridge.last_changed_input_name
        if not target_input_name:
            try:
                for _, tool in comp.GetToolList(True).items():  # selected only
                    for inp in self.bridge.get_animated_inputs(tool):
                        sp = inp.get("spline")
                        if sp and sp.GetAttrs().get("TOOLS_Name", "") == spline_name:
                            target_input_name = inp["name"]
                            self.bridge.last_changed_input_name = target_input_name
                            break
                    if target_input_name:
                        break
            except Exception as e:
                return {"ok": False, "error": f"Could not identify control: {e}"}

        if not target_input_name:
            return {"ok": False, "error": f"Could not find input for spline '{spline_name}'"}

        selected = comp.GetToolList(True)
        if not selected:
            return {"ok": False, "error": "No tools selected in Fusion"}

        total_segments = 0
        tools_hit = 0
        for tool in selected.values():
            matched_this_tool = False
            for inp in self.bridge.get_animated_inputs(tool):
                if inp.get("name") != target_input_name:
                    continue
                spline = inp.get("spline")
                if not spline:
                    continue
                inp_spline_name = spline.GetAttrs().get("TOOLS_Name", "")
                is_polypath     = inp.get("input_type") == "polypath" or inp_spline_name.endswith("Displacement")
                try:
                    kfs = spline.GetKeyFrames()
                except Exception:
                    continue
                frames = sorted([f for f in kfs.keys() if isinstance(f, (int, float))])
                if len(frames) < 2:
                    continue
                matched_this_tool = True

                if is_polypath:
                    n = self._apply_polypath_all_segs(spline, inp_spline_name, frames, js_keyframes, comp)
                    if n:
                        total_segments += n
                        print(f"[RECENT-ALL POLYPATH] {target_input_name} — {n} segments in single write")
                else:
                    for i in range(len(frames) - 1):
                        lf, rf = frames[i], frames[i + 1]
                        lv_raw, rv_raw = kfs[lf], kfs[rf]
                        lv = float(lv_raw[1] if isinstance(lv_raw, dict) else lv_raw)
                        rv = float(rv_raw[1] if isinstance(rv_raw, dict) else rv_raw)
                        segment = {
                            "left_frame": lf, "right_frame": rf,
                            "left_value": lv, "right_value": rv,
                            "kfs": kfs, "spline": spline,
                        }
                        result = self.apply_to_resolve(js_keyframes, segment=segment)
                        if result.get("ok"):
                            total_segments += 1
            if matched_this_tool:
                tools_hit += 1

        if total_segments == 0:
            return {"ok": False, "error": f"No keyframe segments found for '{target_input_name}'"}

        return {
            "ok": True,
            "total_segments": total_segments,
            "tools": tools_hit,
            "input_name": target_input_name,
        }

    def apply_all_at_playhead(self, js_keyframes: list) -> dict:
        """Apply curve to every animated input of every selected node, but only
        the single keyframe segment that contains the current playhead."""
        if not self.bridge.is_connected():
            return {"ok": False, "error": "Resolve not connected"}

        comp = self.bridge.get_current_comp()
        if not comp:
            return {"ok": False, "error": "No active composition"}

        selected = comp.GetToolList(True)
        if not selected:
            return {"ok": False, "error": "No tools selected in Fusion"}

        try:
            current_time = float(comp.CurrentTime)
        except Exception:
            return {"ok": False, "error": "Could not read playhead position"}

        total_segments = 0
        total_tools = 0

        for tool in selected.values():
            tool_hit = False
            for inp in self.bridge.get_animated_inputs(tool):
                spline = inp.get("spline")
                if not spline:
                    continue
                seg = self.bridge.get_adjacent_keyframes(spline, current_time)
                if not seg:
                    continue
                result = self.apply_to_resolve(js_keyframes, segment=seg)
                if result.get("ok"):
                    tool_hit = True
                    total_segments += 1
                    print(f"[ALL-PLAYHEAD] {inp.get('name','?')} segment [{seg['left_frame']}–{seg['right_frame']}]")
            if tool_hit:
                total_tools += 1

        if total_segments == 0:
            return {"ok": False, "error": "No segments found at playhead on selected tools"}

        return {"ok": True, "total_segments": total_segments, "tools": total_tools}

    def apply_recent_all_at_playhead(self, js_keyframes: list) -> dict:
        """Apply curve to the recently-changed control on every selected node,
        but only the single keyframe segment that contains the current playhead."""
        if not self.bridge.is_connected():
            return {"ok": False, "error": "Resolve not connected"}

        comp = self.bridge.get_current_comp()
        if not comp:
            return {"ok": False, "error": "No active composition"}

        spline_name = self.bridge.last_changed_spline
        if not spline_name:
            return {"ok": False, "error": "No recently changed control. Edit a keyframe first."}

        try:
            current_time = float(comp.CurrentTime)
        except Exception:
            return {"ok": False, "error": "Could not read playhead position"}

        # Use cached input name — set by the watcher when it detected the change.
        target_input_name = self.bridge.last_changed_input_name
        if not target_input_name:
            try:
                for _, tool in comp.GetToolList(True).items():  # selected only
                    for inp in self.bridge.get_animated_inputs(tool):
                        sp = inp.get("spline")
                        if sp and sp.GetAttrs().get("TOOLS_Name", "") == spline_name:
                            target_input_name = inp["name"]
                            self.bridge.last_changed_input_name = target_input_name
                            break
                    if target_input_name:
                        break
            except Exception as e:
                return {"ok": False, "error": f"Could not identify control: {e}"}

        if not target_input_name:
            return {"ok": False, "error": f"Could not find input for spline '{spline_name}'"}

        selected = comp.GetToolList(True)
        if not selected:
            return {"ok": False, "error": "No tools selected in Fusion"}

        total_segments = 0
        tools_hit = 0

        for tool in selected.values():
            matched = False
            for inp in self.bridge.get_animated_inputs(tool):
                if inp.get("name") != target_input_name:
                    continue
                spline = inp.get("spline")
                if not spline:
                    continue
                seg = self.bridge.get_adjacent_keyframes(spline, current_time)
                if not seg:
                    continue
                matched = True
                result = self.apply_to_resolve(js_keyframes, segment=seg)
                if result.get("ok"):
                    total_segments += 1
                    print(f"[RECENT-ALL-PLAYHEAD] {target_input_name} [{seg['left_frame']}–{seg['right_frame']}]")
            if matched:
                tools_hit += 1

        if total_segments == 0:
            return {"ok": False, "error": f"No segments found at playhead for '{target_input_name}'"}

        return {
            "ok": True,
            "total_segments": total_segments,
            "tools": tools_hit,
            "input_name": target_input_name,
        }

    def apply_retime_all(self, js_keyframes: list, custom_start: float, custom_end: float) -> dict:
        """Move the keyframe pair (adjacent to playhead) on all selected nodes'
        recently-changed control to [custom_start, custom_end], then apply the
        preview curve between them.  Keyframe VALUES are preserved — only time
        positions change.

        Conditions that must all be true (validated before writing):
          1. A recent control is known (last_changed_spline is set).
          2. The playhead sits between two keyframes on that control.
          3. Every selected node that has the same input name also has keyframes
             at exactly the same two frames (float-tolerance: 0.5 frames).

        On failure returns {"ok": False, "error": <detailed message>}.
        """
        if not self.bridge.is_connected():
            return {"ok": False, "error": "Resolve not connected"}

        comp = self.bridge.get_current_comp()
        if not comp:
            return {"ok": False, "error": "No active composition"}

        spline_name = self.bridge.last_changed_spline
        if not spline_name:
            return {
                "ok": False,
                "error": (
                    "No recently changed control detected.\n\n"
                    "To use All + Custom Range:\n"
                    "  1. Touch (add/move) a keyframe on the control you want to retime.\n"
                    "  2. Position the playhead between the two keyframes to move.\n"
                    "  3. Set the custom range to the target start/end frames.\n"
                    "  4. Click Apply."
                ),
            }

        current_time = float(comp.CurrentTime)

        # ── Find the input name for this spline (use cache, fall back to selected-only scan) ──
        target_input_name = self.bridge.last_changed_input_name
        if not target_input_name:
            try:
                for _, tool in comp.GetToolList(True).items():
                    for inp in self.bridge.get_animated_inputs(tool):
                        sp = inp.get("spline")
                        if sp and sp.GetAttrs().get("TOOLS_Name", "") == spline_name:
                            target_input_name = inp["name"]
                            self.bridge.last_changed_input_name = target_input_name
                            break
                    if target_input_name:
                        break
            except Exception as e:
                return {"ok": False, "error": f"Could not identify control: {e}"}

        if not target_input_name:
            return {"ok": False, "error": f"Could not find an input for spline '{spline_name}'"}

        # ── Find the reference pair on the recent spline ──
        ref_spline_tool = None
        try:
            for _, t in comp.GetToolList(False).items():
                if t.GetAttrs().get("TOOLS_Name") == spline_name:
                    ref_spline_tool = t
                    break
        except Exception:
            pass

        if not ref_spline_tool:
            return {"ok": False, "error": f"Spline '{spline_name}' not found in comp"}

        ref_kfs = ref_spline_tool.GetKeyFrames()
        ref_frames = sorted([f for f in ref_kfs.keys() if isinstance(f, (int, float))])

        old_left_frame = old_right_frame = None
        for i in range(len(ref_frames) - 1):
            if ref_frames[i] <= current_time <= ref_frames[i + 1]:
                old_left_frame = ref_frames[i]
                old_right_frame = ref_frames[i + 1]
                break

        if old_left_frame is None:
            return {
                "ok": False,
                "error": (
                    f"Playhead (frame {int(current_time)}) is not between any two keyframes "
                    f"on '{target_input_name}'.\n\n"
                    f"Keyframes on that control are at: {[int(f) for f in ref_frames]}.\n"
                    "Position the playhead between the pair you want to retime."
                ),
            }

        tol = 0.5  # half-frame tolerance for matching positions across nodes

        # ── Validate all selected nodes ──
        selected = comp.GetToolList(True)
        if not selected:
            return {"ok": False, "error": "No tools selected in Fusion"}

        missing_control = []   # tool names that don't have the input at all
        wrong_positions = {}   # tool name → their actual frames
        valid_inputs = []      # (tool_name, inp_dict) ready to retime

        for tool in selected.values():
            tool_name = tool.GetAttrs().get("TOOLS_Name", "?")
            inputs = self.bridge.get_animated_inputs(tool)
            matched = [i for i in inputs if i.get("name") == target_input_name]
            if not matched:
                missing_control.append(tool_name)
                continue
            for inp in matched:
                sp = inp.get("spline")
                if not sp:
                    continue
                try:
                    kfs = sp.GetKeyFrames()
                except Exception:
                    continue
                frames = sorted([f for f in kfs.keys() if isinstance(f, (int, float))])
                has_left = any(abs(f - old_left_frame) <= tol for f in frames)
                has_right = any(abs(f - old_right_frame) <= tol for f in frames)
                if has_left and has_right:
                    valid_inputs.append((tool_name, inp))
                else:
                    wrong_positions[tool_name] = [int(f) for f in frames]

        # Build error message if any validation failed
        errors = []
        if missing_control:
            errors.append(
                f"Missing '{target_input_name}' control:\n  " + ", ".join(missing_control)
            )
        if wrong_positions:
            ref_str = f"[{int(old_left_frame)}, {int(old_right_frame)}]"
            detail = "\n  ".join(
                f"{n}: {pos}" for n, pos in wrong_positions.items()
            )
            errors.append(
                f"Wrong keypoint positions (need {ref_str} from '{target_input_name}'):\n  {detail}"
            )

        if errors:
            cond_summary = (
                "All + Custom Range requires:\n"
                f"  • Recent control: '{target_input_name}' (at frames {int(old_left_frame)}–{int(old_right_frame)})\n"
                f"  • Playhead (frame {int(current_time)}) inside that pair  ✓\n"
                f"  • All selected nodes have '{target_input_name}' with keyframes at those same positions\n\n"
            )
            return {"ok": False, "error": cond_summary + "\n\n".join(errors)}

        if not valid_inputs:
            return {"ok": False, "error": "No valid inputs to retime"}

        # ── Apply retime + curve to each valid input ──
        duration = custom_end - custom_start
        tools_done = 0

        for tool_name, inp in valid_inputs:
            spline = inp["spline"]
            comp.Lock()
            try:
                kfs = spline.GetKeyFrames()

                # Find exact keys (float-safe)
                actual_left = next(
                    (f for f in kfs if isinstance(f, (int, float)) and abs(f - old_left_frame) <= tol),
                    None
                )
                actual_right = next(
                    (f for f in kfs if isinstance(f, (int, float)) and abs(f - old_right_frame) <= tol),
                    None
                )
                if actual_left is None or actual_right is None:
                    comp.Unlock()
                    continue

                left_raw  = kfs[actual_left]
                right_raw = kfs[actual_right]
                left_val  = float(left_raw[1]  if isinstance(left_raw,  dict) else left_raw)
                right_val = float(right_raw[1] if isinstance(right_raw, dict) else right_raw)
                value_range = right_val - left_val

                # Preserve outward-facing handles before removing old range
                old_left_lh  = left_raw.get("LH")  if isinstance(left_raw,  dict) else None
                old_right_rh = right_raw.get("RH") if isinstance(right_raw, dict) else None

                # Remove old keyframes in [actual_left, actual_right]
                for f in list(kfs.keys()):
                    if isinstance(f, (int, float)) and actual_left <= f <= actual_right:
                        del kfs[f]

                # Build new kf_table at [custom_start, custom_end]
                kf_table = {}
                # Flat case: when start_val == end_val, preserve curve shape with virtual range.
                FLAT_VIRTUAL = 3.0
                flat_value = abs(value_range) < 0.0001
                for kf in js_keyframes:
                    t_norm = kf["t"]
                    if t_norm <= 0:
                        frame = custom_start
                    elif t_norm >= 1:
                        frame = custom_end
                    else:
                        frame = round(custom_start + t_norm * duration)
                    if flat_value:
                        value = left_val + (kf["v"] - 0.5) * FLAT_VIRTUAL
                    else:
                        value = left_val + kf["v"] * value_range
                    entry = {1: value}
                    if "rh" in kf:
                        rh_dx = (custom_start + kf["rh"]["t"] * duration) - frame
                        if flat_value:
                            rh_dv = (left_val + (kf["rh"]["v"] - 0.5) * FLAT_VIRTUAL) - value
                        else:
                            rh_dv = (left_val + kf["rh"]["v"] * value_range) - value
                        entry["RH"] = {1: rh_dx, 2: rh_dv}
                    if "lh" in kf:
                        lh_dx = (custom_start + kf["lh"]["t"] * duration) - frame
                        if flat_value:
                            lh_dv = (left_val + (kf["lh"]["v"] - 0.5) * FLAT_VIRTUAL) - value
                        else:
                            lh_dv = (left_val + kf["lh"]["v"] * value_range) - value
                        entry["LH"] = {1: lh_dx, 2: lh_dv}
                    kf_table[frame] = entry

                # Restore outward-facing handles on the new endpoints
                if old_left_lh and "LH" not in kf_table.get(custom_start, {}):
                    kf_table.setdefault(custom_start, {})["LH"] = old_left_lh
                if old_right_rh and "RH" not in kf_table.get(custom_end, {}):
                    kf_table.setdefault(custom_end, {})["RH"] = old_right_rh

                kfs.update(kf_table)
                spline.SetKeyFrames(kfs, True)
                spline.SetKeyFrames(kf_table, False)
                comp.Unlock()
                tools_done += 1
            except Exception:
                try:
                    comp.Unlock()
                except Exception:
                    pass

        if tools_done == 0:
            return {"ok": False, "error": "Retime failed on all targets"}

        return {
            "ok": True,
            "tools": tools_done,
            "input_name": target_input_name,
            "old_left_frame": old_left_frame,
            "old_right_frame": old_right_frame,
        }

    # NOTE: Old physics tail mode removed. The unified apply_to_resolve above
    # handles all modes the same way: JS draws it, Python writes it.
    def _old_apply_to_resolve_with_tail(self, keyframes: list = None) -> dict:
        """DEPRECATED: Old TAIL approach for physics. Kept for reference."""
        if not self.bridge.is_connected():
            return {"ok": False, "error": "Resolve not connected"}

        if self._target_segment is None:
            return {"ok": False, "error": "No target segment. Call fetch_keyframes_smart() first."}

        comp = self.bridge.get_current_comp()
        if not comp:
            return {"ok": False, "error": "No active composition"}

        segment = self._target_segment
        self._target_segment = None  # clear immediately
        
        # Get segment bounds
        left_f = segment["left_frame"]
        right_f = segment["right_frame"]
        left_v = segment["left_value"]
        right_v = segment["right_value"]
        spline = segment["spline"]
        
        # Check if this is a physics animation
        is_physics = self.mode in ("bounce", "elastic")
        
        if is_physics:
            # PHYSICS MODE: Apply as TAIL after kf2
            # Duration slider controls tail length
            tail_duration_ratio = self.params.get("duration", 1.0) if self.mode == "elastic" else self.params.get("gravity", 1.0)
            tail_duration_ratio = max(0.2, min(3.0, tail_duration_ratio))
            
            original_duration = right_f - left_f
            tail_duration = original_duration * tail_duration_ratio
            
            # Use provided keyframes (should be the physics tail keyframes)
            # or generate them if not provided
            if keyframes is None or len(keyframes) < 2:
                # Generate tail keyframes starting from kf2
                tail_keyframes = self._generate_physics_tail(
                    start_frame=right_f,
                    tail_duration=tail_duration,
                    base_value=right_v,
                    original_value_range=right_v - left_v
                )
            else:
                # Scale the provided keyframes (from JS preview) to tail
                # Physics keyframes have v values that go 0->1 with overshoot
                # For tail: oscillate around right_v with amplitude based on original range
                amp_scale = abs(right_v - left_v) * 0.3  # 30% of original range
                print(f"[apply_to_resolve] Scaling {len(keyframes)} keyframes to tail")
                print(f"[apply_to_resolve] right_f={right_f}, right_v={right_v}, tail_duration={tail_duration}, amp_scale={amp_scale}")
                tail_keyframes = []
                for kf in keyframes:
                    frame = right_f + kf["t"] * tail_duration
                    # Convert physics v (0-1+ with overshoot) to tail value
                    # For out: oscillate around right_v, (v-1) gives the offset from baseline
                    if self.direction == "out":
                        value = right_v + (kf["v"] - 1.0) * amp_scale
                    else:
                        # For in: start at right_v and oscillate down
                        value = right_v - kf["v"] * amp_scale
                    
                    new_kf = {"t": frame, "v": value}
                    if "rh" in kf:
                        rh_v_val = kf["rh"]["v"]
                        if self.direction == "out":
                            rh_v = right_v + (rh_v_val - 1.0) * amp_scale
                        else:
                            rh_v = right_v - rh_v_val * amp_scale
                        new_kf["rh"] = {
                            "t": right_f + kf["rh"]["t"] * tail_duration,
                            "v": rh_v
                        }
                    if "lh" in kf:
                        lh_v_val = kf["lh"]["v"]
                        if self.direction == "out":
                            lh_v = right_v + (lh_v_val - 1.0) * amp_scale
                        else:
                            lh_v = right_v - lh_v_val * amp_scale
                        new_kf["lh"] = {
                            "t": right_f + kf["lh"]["t"] * tail_duration,
                            "v": lh_v
                        }
                    tail_keyframes.append(new_kf)
            
            # Build kf_table
            kf_table = {}
            for i, kf in enumerate(tail_keyframes):
                frame = kf["t"]
                value = kf["v"]
                entry = {1: value}
                
                if "rh" in kf and i < len(tail_keyframes) - 1:
                    entry["RH"] = {1: kf["rh"]["t"] - frame, 2: kf["rh"]["v"] - value}
                if "lh" in kf and i > 0:
                    entry["LH"] = {1: kf["lh"]["t"] - frame, 2: kf["lh"]["v"] - value}
                
                kf_table[round(frame)] = entry
            
            print(f"[apply_to_resolve] Built kf_table with {len(kf_table)} keyframes")
            # Print ALL keyframes being sent to Resolve
            for frame, entry in sorted(kf_table.items()):
                rh_str = f" RH=({entry.get('RH', {}).get(1, 'N/A'):.4f}, {entry.get('RH', {}).get(2, 'N/A'):.4f})" if 'RH' in entry else ""
                lh_str = f" LH=({entry.get('LH', {}).get(1, 'N/A'):.4f}, {entry.get('LH', {}).get(2, 'N/A'):.4f})" if 'LH' in entry else ""
                print(f"  ResolveKF @ {frame}: v={entry.get(1, 'N/A'):.6f}{rh_str}{lh_str}")
            
            # Apply tail
            comp.Lock()
            try:
                fresh_kfs = spline.GetKeyFrames()
                tail_end = right_f + tail_duration
                # Remove keyframes in tail region
                for f in list(fresh_kfs.keys()):
                    if isinstance(f, (int, float)) and right_f < f <= tail_end:
                        del fresh_kfs[f]
                fresh_kfs.update(kf_table)
                spline.SetKeyFrames(fresh_kfs, True)
                comp.Unlock()
                return {"ok": True, "applied": len(kf_table), "mode": f"{self.mode}_tail", "tail_duration": tail_duration}
            except Exception as e:
                try:
                    comp.Unlock()
                except:
                    pass
                return {"ok": False, "error": str(e)}
        else:
            # BEZIER MODE: Apply between kf1 and kf2
            duration = right_f - left_f
            value_range = right_v - left_v
            
            if keyframes is None:
                keyframes = [
                    {"t": 0, "v": 0, "rh": {"t": self.manual_rh["t"], "v": self.manual_rh["v"]}},
                    {"t": 1, "v": 1, "lh": {"t": self.manual_lh["t"], "v": self.manual_lh["v"]}}
                ]
            
            kf_table = self._build_kf_table_from_preview(keyframes, left_f, duration, left_v, value_range)
            
            comp.Lock()
            try:
                fresh_kfs = spline.GetKeyFrames()
                for f in list(fresh_kfs.keys()):
                    if isinstance(f, (int, float)) and left_f < f < right_f:
                        del fresh_kfs[f]
                fresh_kfs.update(kf_table)
                spline.SetKeyFrames(fresh_kfs, True)
                comp.Unlock()
                return {"ok": True, "applied": len(kf_table), "mode": "bezier"}
            except Exception as e:
                try:
                    comp.Unlock()
                except:
                    pass
                return {"ok": False, "error": str(e)}
    
    def _generate_physics_tail(self, start_frame: float, tail_duration: float, 
                                base_value: float, original_value_range: float) -> list:
        """
        Generate physics tail keyframes (bounce/elastic) starting from kf2.
        
        The tail oscillates around base_value (kf2's value) with amplitude
        proportional to original_value_range.
        
        Returns list of {t, v, lh?, rh?} in absolute frame/value space.
        """
        # Sample the physics curve at high resolution
        steps = 200
        points = []
        
        amplitude = self.params.get("amplitude", 1.0)
        hang = self.params.get("hang", 0.5)
        decay_x = self.params.get("decay_x", 0.5)
        decay_y = self.params.get("decay_y", 0.5)
        
        # Generate sample points from the physics function
        for i in range(steps + 1):
            t = i / steps  # 0 to 1 within tail duration
            # Get physics value (0 to 1 for out direction)
            if self.direction == "out":
                phys_v = _eval_physics(t, self.mode, "out", self.params)
            else:
                phys_v = _eval_physics(t, self.mode, "in", self.params)
            points.append({"t": t, "v": phys_v})
        
        # Find key points (peaks, valleys, start)
        key_indices = [0]  # Always include start
        
        for i in range(1, len(points) - 1):
            prev_v = points[i - 1]["v"]
            curr_v = points[i]["v"]
            next_v = points[i + 1]["v"]
            
            is_peak = curr_v > prev_v and curr_v > next_v
            is_valley = curr_v < prev_v and curr_v < next_v
            
            # Significant direction change
            slope_in = curr_v - prev_v
            slope_out = next_v - curr_v
            direction_change = abs(slope_out - slope_in)
            
            if is_peak or is_valley or direction_change > 0.05:
                key_indices.append(i)
        
        key_indices.append(len(points) - 1)  # Always include end
        
        # Build keyframes with bezier handles
        keyframes = []
        
        # Scale factor: amplitude relative to original animation size
        # For "out" direction: oscillates around 1 (ends at 1)
        # For "in" direction: starts at 1, oscillates back to 0
        amp_scale = abs(original_value_range) * amplitude * 0.3  # 30% of original range
        
        for idx_pos, i in enumerate(key_indices):
            pt = points[i]
            
            # Convert normalized t to absolute frame
            frame = start_frame + pt["t"] * tail_duration
            
            # Convert physics value to absolute value
            # For out: physics goes 0->1 with overshoot, we scale around base_value
            if self.direction == "out":
                # phys_v ranges 0-1 with oscillations above 1
                # We want oscillations around base_value
                value = base_value + (pt["v"] - 1.0) * amp_scale
            else:
                # in direction: physics goes 0->1 with oscillations
                # We want to start at base_value and oscillate
                value = base_value - pt["v"] * amp_scale
            
            kf = {"t": frame, "v": value}
            
            is_first = (idx_pos == 0)
            is_last = (idx_pos == len(key_indices) - 1)
            
            # Calculate bezier handles for smooth curves
            if not is_last:
                next_i = key_indices[idx_pos + 1]
                next_pt = points[next_i]
                next_frame = start_frame + next_pt["t"] * tail_duration
                if self.direction == "out":
                    next_value = base_value + (next_pt["v"] - 1.0) * amp_scale
                else:
                    next_value = base_value - next_pt["v"] * amp_scale
                
                rh_t = frame + (next_frame - frame) / 3.0
                slope = (next_value - value) / (next_frame - frame) if next_frame > frame else 0
                rh_v = value + slope * (next_frame - frame) / 3.0
                kf["rh"] = {"t": rh_t, "v": rh_v}
            
            if not is_first:
                prev_i = key_indices[idx_pos - 1]
                prev_pt = points[prev_i]
                prev_frame = start_frame + prev_pt["t"] * tail_duration
                if self.direction == "out":
                    prev_value = base_value + (prev_pt["v"] - 1.0) * amp_scale
                else:
                    prev_value = base_value - prev_pt["v"] * amp_scale
                
                lh_t = frame - (frame - prev_frame) / 3.0
                slope = (value - prev_value) / (frame - prev_frame) if frame > prev_frame else 0
                lh_v = value - slope * (frame - prev_frame) / 3.0
                kf["lh"] = {"t": lh_t, "v": lh_v}
            
            keyframes.append(kf)
        
        return keyframes
    
    def _build_kf_table_from_preview(self, keyframes: list, start_frame: float, 
                                     duration: float, start_val: float, value_range: float) -> dict:
        """
        Convert preview keyframes (normalized 0-1 with handles) to Resolve format.
        
        Preview format: {t: 0-1, v: 0-1, lh?: {t, v}, rh?: {t, v}}
        Where t=0 is start frame, t=1 is end frame
        Where v=0 is start value, v=1 is end value
        
        Resolve format: {frame: {1: value, "LH": {1: t_offset, 2: v_offset}, "RH": ...}}
        
        Handles direction automatically: if value_range is negative (start>end), 
        the curve flips accordingly.
        """
        kf_table = {}
        
        # Flat case detection
        flat_value = abs(value_range) < 0.0001
        is_physics = hasattr(self, 'mode') and self.mode in ("elastic", "bounce")
        
        # ── Physics curves (elastic/bounce): clamped oscillation ──
        if flat_value and is_physics:
            # Detect angle vs normal for imaginary range
            offset = 100.0 if self._is_angle_input() else 1.0
            amp_scale = offset * self.params.get("amplitude", 1.0) * 0.3
            
            for i, kf in enumerate(keyframes):
                frame = start_frame + kf["t"] * duration
                
                # Clamp: pin first and last keyframes to exact boundary values
                # to prevent rounding collisions from corrupting segment edges.
                if i == 0 or i == len(keyframes) - 1:
                    value = start_val
                else:
                    # Both OUT and IN mirrored keyframes use the same mapping:
                    # v=1 maps to 0 offset (end at start_val), v<1 maps below start_val.
                    # For OUT, v>1 creates positive offsets (overshoot above).
                    # For IN, v<0 (mirrored OUT peaks) creates deeper negative offsets.
                    value = start_val + (kf["v"] - 1.0) * amp_scale
                
                entry = {1: value}
                
                if "rh" in kf and i < len(keyframes) - 1:
                    rh = kf["rh"]
                    rh_frame = start_frame + rh["t"] * duration
                    rh_value = start_val + (rh["v"] - 1.0) * amp_scale
                    entry["RH"] = {1: rh_frame - frame, 2: rh_value - value}
                
                if "lh" in kf and i > 0:
                    lh = kf["lh"]
                    lh_frame = start_frame + lh["t"] * duration
                    lh_value = start_val + (lh["v"] - 1.0) * amp_scale
                    entry["LH"] = {1: lh_frame - frame, 2: lh_value - value}
                
                kf_table[round(frame)] = entry
            
            # Guard: if rounding caused boundary collisions, force exact boundary values
            first_frame = round(start_frame)
            last_frame = round(start_frame + duration)
            if first_frame in kf_table:
                kf_table[first_frame][1] = start_val
            if last_frame in kf_table and last_frame != first_frame:
                kf_table[last_frame][1] = start_val
            
            return kf_table
        
        # ── Non-physics flat case: clamp start/end values, virtual range for middle only ──
        FLAT_VIRTUAL = 3.0
        
        for i, kf in enumerate(keyframes):
            # Scale normalized values to actual frame/value
            frame = start_frame + kf["t"] * duration
            
            if flat_value:
                # Preserve exact start and end values; only middle uses virtual range
                if i == 0:
                    value = start_val  # exact start value
                elif i == len(keyframes) - 1:
                    value = start_val  # exact end value (= start_val when flat)
                else:
                    value = start_val + (kf["v"] - 0.5) * FLAT_VIRTUAL
            else:
                value = start_val + kf["v"] * value_range
            
            entry = {1: value}
            
            # Convert handles from absolute positions to offsets
            # RH handle: offset from current keyframe
            if "rh" in kf and i < len(keyframes) - 1:
                rh = kf["rh"]
                rh_frame = start_frame + rh["t"] * duration
                if flat_value:
                    # Clamp: first keyframe RH uses exact value, others use virtual
                    if i == 0:
                        rh_value = start_val + (rh["v"] - 0.5) * FLAT_VIRTUAL
                    else:
                        rh_value = start_val + (rh["v"] - 0.5) * FLAT_VIRTUAL
                else:
                    rh_value = start_val + rh["v"] * value_range
                entry["RH"] = {1: rh_frame - frame, 2: rh_value - value}
            
            # LH handle: offset from current keyframe
            if "lh" in kf and i > 0:
                lh = kf["lh"]
                lh_frame = start_frame + lh["t"] * duration
                if flat_value:
                    lh_value = start_val + (lh["v"] - 0.5) * FLAT_VIRTUAL
                else:
                    lh_value = start_val + lh["v"] * value_range
                entry["LH"] = {1: lh_frame - frame, 2: lh_value - value}
            
            kf_table[round(frame)] = entry
        
        return kf_table

    # ── UNIFIED CURVE SAMPLER (New Approach) ──
    
    def apply_sampled_curve(self, normalized_points: list) -> dict:
        """
        Apply a sampled curve to Resolve.
        
        Args:
            normalized_points: List of {t, v} where t,v are in [0,1] range
            
        The curve shape from the preview is preserved exactly.
        It's just scaled to fit the target keyframes' frame range and value range.
        """
        if not self.bridge.is_connected():
            return {"ok": False, "error": "Resolve not connected"}
        
        if not normalized_points or len(normalized_points) < 2:
            return {"ok": False, "error": "Not enough curve points"}
        
        comp = self.bridge.get_current_comp()
        if not comp:
            return {"ok": False, "error": "No active composition"}
        
        # Check if we have a target segment from fetch_keyframes_smart
        segment = getattr(self, '_target_segment', None)
        if segment is not None:
            # Apply to segment using its spline directly
            self._target_segment = None  # Clear after use
            return self._apply_to_segment(segment, normalized_points)
        
        # Otherwise use target_input_obj (traditional path)
        if self.target_input_obj is None:
            return {"ok": False, "error": "No target input selected. Please fetch keyframes first."}
        
        # Get target range
        duration = self.end_frame - self.start_frame
        if duration <= 0:
            duration = 1.0
        value_range = self.end_value - self.start_value
        
        # Build keyframe table from sampled points
        kf_table = self._build_kf_table_from_points(normalized_points, duration, value_range)
        
        # Apply to Resolve
        comp.Lock()
        try:
            spline = self.target_spline
            if not spline:
                conn = self.target_input_obj.GetConnectedOutput()
                if conn:
                    spline = conn.GetTool()
                else:
                    spline = comp.BezierSpline()
                    self.target_input_obj.ConnectTo(spline)
            
            spline.SetKeyFrames(kf_table, True)
            comp.Unlock()
            return {"ok": True, "applied": len(kf_table)}
        except Exception as e:
            try:
                comp.Unlock()
            except:
                pass
            return {"ok": False, "error": str(e)}
    
    def _apply_to_segment(self, segment: dict, normalized_points: list) -> dict:
        """Apply sampled curve to a specific segment (from fetch_keyframes_smart)."""
        comp = self.bridge.get_current_comp()
        if not comp:
            return {"ok": False, "error": "No active composition"}
        
        left_f = segment["left_frame"]
        right_f = segment["right_frame"]
        left_v = segment["left_value"]
        right_v = segment["right_value"]
        spline = segment["spline"]
        
        duration = right_f - left_f
        value_range = right_v - left_v
        
        # Build keyframe table using intelligent reduction
        kf_table = self._build_kf_table_for_segment(normalized_points, left_f, duration, left_v, value_range)
        
        # Get current keyframes, remove ones in segment range, add new ones
        comp.Lock()
        try:
            fresh_kfs = spline.GetKeyFrames()
            print(f"[DEBUG] _apply_to_segment: Fresh keyframes from spline: {sorted([f for f in fresh_kfs.keys() if isinstance(f, (int, float))])}")
            print(f"[DEBUG] _apply_to_segment: Removing keyframes between {left_f} and {right_f}")
            removed = []
            for f in list(fresh_kfs.keys()):
                if isinstance(f, (int, float)) and left_f < f < right_f:
                    removed.append(f)
                    del fresh_kfs[f]
            print(f"[DEBUG] _apply_to_segment: Removed frames: {removed}")
            print(f"[DEBUG] _apply_to_segment: Adding {len(kf_table)} new keyframes")
            fresh_kfs.update(kf_table)
            
            spline.SetKeyFrames(fresh_kfs, True)
            comp.Unlock()
            return {"ok": True, "applied": len(kf_table)}
        except Exception as e:
            try:
                comp.Unlock()
            except:
                pass
            return {"ok": False, "error": str(e)}
    
    def _build_kf_table_for_segment(self, normalized_points: list, start_frame: float, duration: float, start_val: float, value_range: float) -> dict:
        """Build keyframe table for a segment using intelligent reduction."""
        if len(normalized_points) < 2:
            return {}
        
        # Flat case detection
        flat_value = abs(value_range) < 0.0001
        is_physics = hasattr(self, 'mode') and self.mode in ("elastic", "bounce")
        
        # Find key points (peaks, valleys, start, end)
        key_indices = [0]
        
        for i in range(1, len(normalized_points) - 1):
            prev_v = normalized_points[i - 1]["v"]
            curr_v = normalized_points[i]["v"]
            next_v = normalized_points[i + 1]["v"]
            
            is_peak = curr_v > prev_v and curr_v > next_v
            is_valley = curr_v < prev_v and curr_v < next_v
            
            slope_in = curr_v - prev_v
            slope_out = next_v - curr_v
            direction_change = abs(slope_out - slope_in)
            
            if is_peak or is_valley or direction_change > 0.05:
                key_indices.append(i)
        
        key_indices.append(len(normalized_points) - 1)
        
        # Build keyframes with bezier handles
        kf_table = {}
        
        for idx_pos, i in enumerate(key_indices):
            pt = normalized_points[i]
            frame = start_frame + pt["t"] * duration
            
            if flat_value and is_physics:
                # Physics clamped oscillation
                offset = 100.0 if self._is_angle_input() else 1.0
                amp_scale = offset * self.params.get("amplitude", 1.0) * 0.3
                # Clamp: pin first and last keyframes to exact boundary values
                if idx_pos == 0 or idx_pos == len(key_indices) - 1:
                    value = start_val
                else:
                    value = start_val + (pt["v"] - 1.0) * amp_scale
            elif flat_value:
                # Non-physics flat case
                value = start_val + (pt["v"] - 0.5) * 3.0
            else:
                value = start_val + pt["v"] * value_range
            
            entry = {1: value}
            
            is_first = (idx_pos == 0)
            is_last = (idx_pos == len(key_indices) - 1)
            
            if not is_last:
                next_i = key_indices[idx_pos + 1]
                next_pt = normalized_points[next_i]
                next_frame = start_frame + next_pt["t"] * duration
                if flat_value and is_physics:
                    next_value = start_val + (next_pt["v"] - 1.0) * amp_scale
                elif flat_value:
                    next_value = start_val + (next_pt["v"] - 0.5) * 3.0
                else:
                    next_value = start_val + next_pt["v"] * value_range
                
                rh_t_off = (next_frame - frame) / 3.0
                if next_frame > frame:
                    slope = (next_value - value) / (next_frame - frame)
                    rh_v_off = slope * rh_t_off
                else:
                    rh_v_off = 0.0
                
                entry["RH"] = {1: rh_t_off, 2: rh_v_off}
            
            if not is_first:
                prev_i = key_indices[idx_pos - 1]
                prev_pt = normalized_points[prev_i]
                prev_frame = start_frame + prev_pt["t"] * duration
                if flat_value and is_physics:
                    prev_value = start_val + (prev_pt["v"] - 1.0) * amp_scale
                elif flat_value:
                    prev_value = start_val + (prev_pt["v"] - 0.5) * 3.0
                else:
                    prev_value = start_val + prev_pt["v"] * value_range
                
                lh_t_off = -((frame - prev_frame) / 3.0)
                if frame > prev_frame:
                    slope = (value - prev_value) / (frame - prev_frame)
                    lh_v_off = slope * lh_t_off
                else:
                    lh_v_off = 0.0
                
                entry["LH"] = {1: lh_t_off, 2: lh_v_off}
            
            kf_table[round(frame)] = entry
        
        # Guard: ensure exact boundary values for flat physics
        if flat_value and is_physics:
            first_frame = round(start_frame)
            last_frame = round(start_frame + duration)
            if first_frame in kf_table:
                kf_table[first_frame][1] = start_val
            if last_frame in kf_table and last_frame != first_frame:
                kf_table[last_frame][1] = start_val
        
        return kf_table
    
    def _build_kf_table_from_points(self, normalized_points: list, duration: float, value_range: float) -> dict:
        """
        Build keyframe table from normalized points using intelligent reduction.
        Extracts only peaks/valleys and inflection points, uses bezier handles for smoothness.
        """
        if len(normalized_points) < 2:
            return {}
        
        # Flat case detection
        flat_value = abs(value_range) < 0.0001
        is_physics = hasattr(self, 'mode') and self.mode in ("elastic", "bounce")
        
        # Step 1: Find key points (peaks, valleys, start, end)
        key_indices = [0]  # Always include first point
        
        for i in range(1, len(normalized_points) - 1):
            prev_pt = normalized_points[i - 1]
            curr_pt = normalized_points[i]
            next_pt = normalized_points[i + 1]
            
            prev_v = prev_pt["v"]
            curr_v = curr_pt["v"]
            next_v = next_pt["v"]
            
            # Peak or valley detection
            is_peak = curr_v > prev_v and curr_v > next_v
            is_valley = curr_v < prev_v and curr_v < next_v
            
            # Significant direction change (inflection)
            slope_in = curr_v - prev_v
            slope_out = next_v - curr_v
            direction_change = abs(slope_out - slope_in)
            
            if is_peak or is_valley or direction_change > 0.05:
                key_indices.append(i)
        
        key_indices.append(len(normalized_points) - 1)  # Always include last point
        
        # Step 2: Build keyframes with calculated bezier handles
        kf_table = {}
        
        for idx_pos, i in enumerate(key_indices):
            pt = normalized_points[i]
            frame = self.start_frame + pt["t"] * duration
            
            if flat_value and is_physics:
                offset = 100.0 if self._is_angle_input() else 1.0
                amp_scale = offset * self.params.get("amplitude", 1.0) * 0.3
                # Clamp: pin first keyframe to exact start_val
                if idx_pos == 0:
                    value = self.start_value
                else:
                    value = self.start_value + (pt["v"] - 1.0) * amp_scale
            elif flat_value:
                value = self.start_value + (pt["v"] - 0.5) * 3.0
            else:
                value = self.start_value + pt["v"] * value_range
            
            entry = {1: value}
            
            is_first = (idx_pos == 0)
            is_last = (idx_pos == len(key_indices) - 1)
            
            # Calculate RH handle (outgoing)
            if not is_last:
                next_i = key_indices[idx_pos + 1]
                next_pt = normalized_points[next_i]
                next_frame = self.start_frame + next_pt["t"] * duration
                if flat_value and is_physics:
                    next_value = self.start_value + (next_pt["v"] - 1.0) * amp_scale
                elif flat_value:
                    next_value = self.start_value + (next_pt["v"] - 0.5) * 3.0
                else:
                    next_value = self.start_value + next_pt["v"] * value_range
                
                # RH handle: 1/3 of the way to next keyframe, slope-based value
                rh_t_off = (next_frame - frame) / 3.0
                # Calculate slope for smooth curve
                if next_frame > frame:
                    slope = (next_value - value) / (next_frame - frame)
                    rh_v_off = slope * rh_t_off
                else:
                    rh_v_off = 0.0
                
                entry["RH"] = {1: rh_t_off, 2: rh_v_off}
            
            # Calculate LH handle (incoming)
            if not is_first:
                prev_i = key_indices[idx_pos - 1]
                prev_pt = normalized_points[prev_i]
                prev_frame = self.start_frame + prev_pt["t"] * duration
                if flat_value and is_physics:
                    prev_value = self.start_value + (prev_pt["v"] - 1.0) * amp_scale
                elif flat_value:
                    prev_value = self.start_value + (prev_pt["v"] - 0.5) * 3.0
                else:
                    prev_value = self.start_value + prev_pt["v"] * value_range
                
                # LH handle: 1/3 back from previous keyframe, slope-based value
                lh_t_off = -((frame - prev_frame) / 3.0)
                # Calculate slope for smooth curve
                if frame > prev_frame:
                    slope = (value - prev_value) / (frame - prev_frame)
                    lh_v_off = slope * lh_t_off
                else:
                    lh_v_off = 0.0
                
                entry["LH"] = {1: lh_t_off, 2: lh_v_off}
            
            kf_table[round(frame)] = entry
        
        return kf_table

    # ── Preset helpers ───────────────────────────────────────────

    def list_presets(self) -> list:
        return sorted(PRESETS.keys())

    def get_preset_info(self, name: str) -> dict:
        return PRESETS.get(name, {})

    def preset_categories(self) -> dict:
        cats = {}
        for name, info in PRESETS.items():
            cat = info.get("cat", "Other")
            cats.setdefault(cat, []).append(name)
        return cats

    def get_preset_curve_points(self, name: str) -> list:
        """Return normalized preview points for a preset using HANDLES for consistency."""
        cat = PRESETS.get(name, {}).get("cat", "")
        if cat in ["Bounce", "Elastic"]:
            mode      = "bounce" if cat == "Bounce" else "elastic"
            direction = "out" if "Out" in name else "in"
            params    = {"amplitude": 1.0, "hang": 0.5, "decay_x": 0.5, "decay_y": 0.5, "bounciness": 0.5}
            return _sample_physics_curve(mode, direction, params, steps=200)
        
        # For non-physics curves, use the SAME handle-based logic as main preview
        # Temporarily set handles for this preset, generate curve, restore handles
        saved_rh = dict(self.manual_rh)
        saved_lh = dict(self.manual_lh)
        
        # Set handles as select_preset would
        if cat in ["Easing", "Dynamic", "Special"]:
            if "Linear" in name:
                rh_v, lh_v = 0.33, 0.67
            elif "Ease In" in name and "Out" not in name:
                strength = 1.5 if "Cubic" in name or "Expo" in name else 1.0
                rh_v, lh_v = 0.0, 1.0 + 0.5 * strength
            elif "Ease Out" in name and "In" not in name:
                strength = 1.5 if "Cubic" in name or "Expo" in name else 1.0
                rh_v, lh_v = -0.5 * strength, 1.0
            elif "In-Out" in name:
                rh_v, lh_v = 0.0, 1.0
            elif "S-Curve" in name:
                rh_v, lh_v = 0.1, 0.9
            elif "Overshoot" in name:
                if "Strong" in name:
                    rh_v, lh_v = 0.3, 1.35  # Heavy overshoot
                else:
                    rh_v, lh_v = 0.3, 1.2
            elif "Anticipate" in name:
                rh_v, lh_v = -0.2, 1.0
            elif "Reverse" in name:
                rh_v, lh_v = 0.6, 0.4
            elif "Circular" in name:
                if "In" in name and "Out" not in name:
                    rh_v, lh_v = 0.0, 1.3
                elif "Out" in name and "In" not in name:
                    rh_v, lh_v = -0.3, 1.0
                else:
                    rh_v, lh_v = 0.0, 1.0
            elif "Back" in name:
                if "In" in name and "Out" not in name:
                    rh_v, lh_v = -0.15, 1.0
                else:
                    rh_v, lh_v = 0.3, 1.1
            elif "Whip" in name:
                rh_v, lh_v = -0.25, 0.9
            elif "Double Back" in name:
                rh_v, lh_v = 0.15, 0.85
            elif "Smooth Damp" in name:
                rh_v, lh_v = 0.2, 0.98
            elif "Slow Mo" in name:
                rh_v, lh_v = 0.25, 0.75
            elif "Logarithmic" in name:
                rh_v, lh_v = 0.0, 1.15
            else:
                rh_v, lh_v = 0.0, 1.0
        else:
            rh_v, lh_v = 0.0, 1.0
        
        self.manual_rh = {"t": 0.33, "v": rh_v}
        self.manual_lh = {"t": 0.67, "v": lh_v}
        
        # Generate curve from handles
        points = self._get_curve_from_handles(steps=100)
        
        # Restore handles
        self.manual_rh = saved_rh
        self.manual_lh = saved_lh
        
        return points

    def get_custom_curve_points(self, custom_start: str, custom_end: str) -> list:
        """Return normalized preview points for a custom combination using HANDLES.
        
        Handle mapping (FIXED):
        - custom_start (was "In"): controls the START of curve -> affects RH handle
        - custom_end (was "Out"): controls the END of curve -> affects LH handle
        
        Ease-in: starts slow, ends fast (flat start, steep end)
        Ease-out: starts fast, ends slow (steep start, flat end)
        """
        ease_strength = {
            "Linear": 0.0, "Sine": 0.3, "Quad": 0.5, "Cubic": 0.7,
            "Quart": 0.9, "Quint": 1.0, "Expo": 1.2, "Circ": 0.6, "Back": 0.4,
        }
        
        start_strength = ease_strength.get(custom_start, 0.5)
        end_strength = ease_strength.get(custom_end, 0.5)
        
        # Handle calculation (FIXED):
        # RH (right handle at t=0) controls START tangent -> affected by START easing
        # LH (left handle at t=1) controls END tangent -> affected by END easing
        
        if custom_start != "Linear" and custom_end != "Linear":
            # Both: S-curve
            # Start ease-in: flat start (RH ≈ 0)
            # End ease-out: flat end (LH ≈ 1)
            rh_v, lh_v = 0.0, 1.0
        elif custom_start != "Linear":
            # Only Start easing (ease-in): flat start, steep end
            rh_v, lh_v = 0.0, 1.0 + start_strength * 0.5
        elif custom_end != "Linear":
            # Only End easing (ease-out): steep start, flat end
            rh_v, lh_v = -end_strength * 0.5, 1.0
        else:
            # Both linear
            rh_v, lh_v = 0.33, 0.67
        
        # Temporarily set handles
        saved_rh = dict(self.manual_rh)
        saved_lh = dict(self.manual_lh)
        
        self.manual_rh = {"t": 0.33, "v": rh_v}
        self.manual_lh = {"t": 0.67, "v": lh_v}
        
        points = self._get_curve_from_handles(steps=100)
        
        self.manual_rh = saved_rh
        self.manual_lh = saved_lh
        
        return points

    # ── Curve Save/Load ─────────────────────────────────────────__

    def save_current_curve(self, name: str, folder: str = "user_curves") -> dict:
        """
        Save current curve configuration to disk.
        
        Args:
            name: Name for the saved curve
            folder: Subfolder in user directory
            
        Returns:
            {"ok": bool, "path": str, "error": str}
        """
        import json
        
        save_dir = os.path.join(get_data_dir(), folder)
        os.makedirs(save_dir, exist_ok=True)
        
        curve_data = {
            "name": name,
            "version": "1.0",
            "source": self.source,
            "selected_preset": self.selected_preset,
            "mode": self.mode,
            "direction": self.direction,
            "params": dict(self.params),
            "custom_in": self.custom_in,
            "custom_out": self.custom_out,
            "manual_rh": dict(self.manual_rh),
            "manual_lh": dict(self.manual_lh),
        }
        
        # Sanitize filename
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')
        
        filepath = os.path.join(save_dir, f"{safe_name}.json")
        
        try:
            with open(filepath, 'w') as f:
                json.dump(curve_data, f, indent=2)
            return {"ok": True, "path": filepath}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def load_curve(self, filepath: str) -> dict:
        """
        Load curve from saved file.
        
        Args:
            filepath: Full path to .json curve file
            
        Returns:
            {"ok": bool, "error": str}
        """
        import json
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            self.source = data.get("source", "preset")
            self.selected_preset = data.get("selected_preset")
            self.mode = data.get("mode", "elastic")
            self.direction = data.get("direction", "out")
            self.params.update(data.get("params", {}))
            self.custom_in = data.get("custom_in", "Linear")
            self.custom_out = data.get("custom_out", "Linear")
            self.manual_rh.update(data.get("manual_rh", {}))
            self.manual_lh.update(data.get("manual_lh", {}))
            
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_saved_curves(self, folder: str = "user_curves") -> list:
        """
        List all saved curves.
        
        Returns:
            List of {"name": str, "path": str, "modified": str}
        """
        import json
        from datetime import datetime
        
        save_dir = os.path.join(get_data_dir(), folder)
        
        if not os.path.exists(save_dir):
            return []
        
        curves = []
        for filename in os.listdir(save_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(save_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    
                    stat = os.stat(filepath)
                    curves.append({
                        "name": data.get("name", filename[:-5]),
                        "path": filepath,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "source": data.get("source", "unknown")
                    })
                except:
                    pass
        
        return sorted(curves, key=lambda x: x["modified"], reverse=True)

    def rename_curve(self, old_path: str, new_name: str) -> dict:
        """
        Rename a saved curve.
        
        Args:
            old_path: Current file path
            new_name: New name for the curve
            
        Returns:
            {"ok": bool, "new_path": str, "error": str}
        """
        import json
        
        try:
            # Load and update name
            with open(old_path, 'r') as f:
                data = json.load(f)
            data["name"] = new_name
            
            # Save with new name
            safe_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_name = safe_name.replace(' ', '_')
            
            new_path = os.path.join(os.path.dirname(old_path), f"{safe_name}.json")
            
            with open(new_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Remove old file if different
            if old_path != new_path and os.path.exists(old_path):
                os.remove(old_path)
            
            return {"ok": True, "new_path": new_path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_curve(self, filepath: str) -> dict:
        """
        Delete a saved curve.
        
        Args:
            filepath: Path to curve file
            
        Returns:
            {"ok": bool, "error": str}
        """
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                return {"ok": True}
            return {"ok": False, "error": "File not found"}
        except Exception as e:
            return {"ok": False, "error": str(e)}