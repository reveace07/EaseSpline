"""
Keyframe Detector - Multiple methods to detect selected keyframes in Fusion

This module provides various methods to detect which keyframes are selected
in Fusion's Spline Editor, since the API doesn't expose this directly.
"""

import os
import sys
import json
import time
import subprocess
import tempfile
from typing import List, Dict, Tuple, Optional

# Optional Windows API imports
try:
    import win32gui
    import win32con
    import win32api
    import win32process
    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False


class KeyframeDetector:
    """
    Detects selected keyframes in Fusion using multiple methods.
    """
    
    def __init__(self, fusion_comp=None):
        self.comp = fusion_comp
        self.last_error = ""
        
    # ═══════════════════════════════════════════════════════════════════════
    # METHOD 1: Clipboard parsing (original method)
    # ═══════════════════════════════════════════════════════════════════════
    
    def send_ctrl_c_to_resolve(self) -> bool:
        """Send Ctrl+C to DaVinci Resolve window to copy selected keyframes."""
        if not _HAS_WIN32:
            self.last_error = "pywin32 not installed. Run: pip install pywin32"
            return False
            
        # Try different window titles
        window_titles = [
            "DaVinci Resolve",
            "DaVinci Resolve Studio",
            "Resolve",
            "Spline Editor",  # The spline editor window
        ]
        
        hwnd = None
        for title in window_titles:
            hwnd = win32gui.FindWindow(None, title)
            if hwnd:
                break
        
        if not hwnd:
            # Try to find by partial match
            def callback(window_handle, extra):
                text = win32gui.GetWindowText(window_handle)
                if "Resolve" in text or "DaVinci" in text:
                    extra.append(window_handle)
                return True
            
            resolve_windows = []
            win32gui.EnumWindows(callback, resolve_windows)
            if resolve_windows:
                hwnd = resolve_windows[0]
        
        if hwnd:
            # Bring window to front first
            try:
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.1)
            except:
                pass
            
            # Send Ctrl+C
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(ord('C'), 0, 0, 0)
            win32api.keybd_event(ord('C'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
            
        self.last_error = "Could not find DaVinci Resolve window"
        return False
    
    def parse_clipboard_for_keyframes(self) -> Dict:
        """Parse keyframe data from clipboard after Ctrl+C."""
        try:
            result = subprocess.run(
                ['powershell', '-command', 'Get-Clipboard'],
                capture_output=True, text=True, timeout=2
            )
            clipboard = result.stdout.strip()
            
            # Look for frame numbers in various formats
            # Format 1: "[25] = { 0.5 }"  (Lua-style from Fusion)
            # Format 2: "Frame 25: Value 0.5"
            # Format 3: Just numbers that look like frame numbers
            
            import re
            
            # Try Lua-style keyframe format
            lua_pattern = r'\[(\d+(?:\.\d+)?)\]\s*=\s*\{\s*([\d.-]+)'
            lua_matches = re.findall(lua_pattern, clipboard)
            
            if lua_matches:
                frames = [float(m[0]) for m in lua_matches]
                values = [float(m[1]) for m in lua_matches]
                return {
                    "ok": True,
                    "method": "lua_format",
                    "start_frame": min(frames),
                    "end_frame": max(frames),
                    "all_frames": sorted(frames),
                    "values": values,
                    "raw": clipboard[:500]  # First 500 chars for debug
                }
            
            # Try to find any number that could be a frame number
            # Look for patterns like "f25", "frame 25", or just 25 followed by a value
            frame_patterns = [
                r'[Ff]rame\s+(\d+)',
                r'\bf(\d+)\b',
                r'[(\[](\d+)[)\]]',
            ]
            
            all_frames = []
            for pattern in frame_patterns:
                matches = re.findall(pattern, clipboard)
                all_frames.extend([int(m) for m in matches])
            
            if len(all_frames) >= 2:
                return {
                    "ok": True,
                    "method": "pattern_match",
                    "start_frame": min(all_frames),
                    "end_frame": max(all_frames),
                    "all_frames": sorted(set(all_frames)),
                    "raw": clipboard[:500]
                }
            
            return {
                "ok": False,
                "error": "No keyframe data found in clipboard",
                "raw": clipboard[:500] if clipboard else "(empty)"
            }
            
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════════
    # METHOD 2: Execute Python inside Fusion
    # ═══════════════════════════════════════════════════════════════════════
    
    def run_python_in_fusion(self, code: str) -> Dict:
        """
        Execute Python code inside Fusion's interpreter.
        This requires Fusion to be running and accessible.
        """
        try:
            # Save code to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_path = f.name
            
            # Try to use Fusion's console to execute the script
            # This is a workaround - we need Fusion to run this
            result = {
                "ok": False,
                "error": "Direct Fusion execution not implemented",
                "note": "Use the fusion_keyframe_helper.py script instead - run it inside Fusion"
            }
            
            os.unlink(temp_path)
            return result
            
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════════
    # METHOD 3: Read from shared file (most reliable)
    # ═══════════════════════════════════════════════════════════════════════
    
    def read_fusion_helper_output(self) -> Dict:
        """
        Read keyframe data from the fusion_keyframe_helper.py output.
        This requires the helper script to be running inside Fusion.
        """
        filepath = os.path.expandvars("%TEMP%\\reveace_keyframes.json")
        
        if not os.path.exists(filepath):
            return {
                "ok": False,
                "error": "No keyframe data file found. Run fusion_keyframe_helper.py inside Fusion first.",
                "filepath": filepath
            }
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            return data
        except Exception as e:
            return {"ok": False, "error": f"Failed to read keyframe file: {e}"}
    
    # ═══════════════════════════════════════════════════════════════════════
    # METHOD 4: Get all keyframes from spline (for "all" mode)
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_all_keyframes_from_spline(self, spline_tool) -> Dict:
        """
        Get all keyframes from a spline tool.
        This is the fallback method that always works.
        """
        try:
            keyframes = spline_tool.GetKeyFrames()
            if not keyframes or not isinstance(keyframes, dict):
                return {"ok": False, "error": "No keyframes found in spline"}
            
            # Extract numeric frame numbers
            all_frames = []
            all_values = []
            
            for frame, value in keyframes.items():
                if isinstance(frame, (int, float)):
                    all_frames.append(float(frame))
                    
                    # Extract value
                    if isinstance(value, dict) and 1 in value:
                        val = value[1]
                    else:
                        val = value
                    
                    all_values.append(float(val) if isinstance(val, (int, float)) else 0.0)
            
            if len(all_frames) < 2:
                return {"ok": False, "error": "Need at least 2 keyframes"}
            
            # Sort by frame
            sorted_pairs = sorted(zip(all_frames, all_values))
            all_frames = [p[0] for p in sorted_pairs]
            all_values = [p[1] for p in sorted_pairs]
            
            # Create segments
            segments = []
            for i in range(len(all_frames) - 1):
                segments.append({
                    "start_frame": all_frames[i],
                    "end_frame": all_frames[i + 1],
                    "start_value": all_values[i],
                    "end_value": all_values[i + 1]
                })
            
            return {
                "ok": True,
                "method": "spline_api",
                "segments": segments,
                "all_frames": all_frames,
                "all_values": all_values,
                "start_frame": all_frames[0],
                "end_frame": all_frames[-1]
            }
            
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════════
    # MAIN DETECTION METHODS
    # ═══════════════════════════════════════════════════════════════════════
    
    def detect_selected_keyframes(self) -> Dict:
        """
        Try multiple methods to detect selected keyframes.
        Returns the first successful result.
        """
        results = []
        
        # Method 1: Try clipboard (Ctrl+C method)
        print("[KeyframeDetector] Trying clipboard method...")
        if self.send_ctrl_c_to_resolve():
            time.sleep(0.3)  # Wait for clipboard
            result = self.parse_clipboard_for_keyframes()
            results.append(("clipboard", result))
            if result.get("ok"):
                return {**result, "methods_tried": [r[0] for r in results]}
        else:
            results.append(("clipboard", {"ok": False, "error": self.last_error}))
        
        # Method 2: Try shared file from Fusion helper
        print("[KeyframeDetector] Trying Fusion helper file...")
        result = self.read_fusion_helper_output()
        results.append(("fusion_file", result))
        if result.get("ok"):
            # Convert to our format
            if "segments" in result:
                first_seg = result["segments"][0] if result["segments"] else None
                if first_seg:
                    return {
                        "ok": True,
                        "method": "fusion_file",
                        "start_frame": first_seg["start_frame"],
                        "end_frame": first_seg["end_frame"],
                        "all_frames": result.get("all_frames", []),
                        "segments": result.get("segments", []),
                        "methods_tried": [r[0] for r in results]
                    }
        
        # Method 3: Last resort - get all keyframes from the active spline
        # This requires the comp to be provided
        if self.comp:
            print("[KeyframeDetector] Trying spline API method...")
            tool = self.comp.ActiveTool
            if tool:
                # Find the first animated input with a spline
                for input_id, inp in tool.GetInputList().items():
                    try:
                        conn = inp.GetConnectedOutput()
                        if conn:
                            spline = conn.GetTool()
                            if spline:
                                attrs = spline.GetAttrs()
                                if "BezierSpline" in attrs.get("TOOLS_RegID", ""):
                                    result = self.get_all_keyframes_from_spline(spline)
                                    results.append(("spline_api", result))
                                    if result.get("ok"):
                                        return {**result, "methods_tried": [r[0] for r in results]}
                    except:
                        continue
        
        # All methods failed
        return {
            "ok": False,
            "error": "All detection methods failed",
            "methods_tried": [r[0] for r in results],
            "results": {name: res for name, res in results}
        }
    
    def get_all_segments(self, spline_tool) -> List[Dict]:
        """Get all keyframe segments for 'each segment' mode."""
        result = self.get_all_keyframes_from_spline(spline_tool)
        if result.get("ok"):
            return result.get("segments", [])
        return []


# Convenience functions for direct use
def detect_selected_keyframes(comp=None) -> Dict:
    """Standalone function to detect selected keyframes."""
    detector = KeyframeDetector(comp)
    return detector.detect_selected_keyframes()


def get_all_keyframes(spline_tool) -> Dict:
    """Standalone function to get all keyframes from a spline."""
    detector = KeyframeDetector()
    return detector.get_all_keyframes_from_spline(spline_tool)


if __name__ == "__main__":
    # Test the detector
    print("Testing KeyframeDetector...")
    
    detector = KeyframeDetector()
    
    # Test clipboard parsing
    print("\n1. Testing clipboard method:")
    if detector.send_ctrl_c_to_resolve():
        time.sleep(0.3)
        result = detector.parse_clipboard_for_keyframes()
        print(f"   Result: {result}")
    else:
        print(f"   Failed: {detector.last_error}")
    
    # Test file reading
    print("\n2. Testing Fusion helper file:")
    result = detector.read_fusion_helper_output()
    print(f"   Result: {result}")
