"""
Fusion Keyframe Helper - Run this inside DaVinci Resolve's Fusion console
or add it as a Python script to your workspace.

This script provides a bridge between ReveaceSpline and Fusion to properly
detect selected keyframes in the Spline Editor.
"""

import json
import os

def get_selected_keyframes():
    """
    Get the currently selected keyframes from the active tool's spline.
    This runs INSIDE Fusion and has access to the actual selection state.
    
    Returns: {
        "ok": True/False,
        "tool": tool_name,
        "input": input_name,
        "keyframes": [
            {"frame": frame_num, "value": value, "selected": True/False},
            ...
        ],
        "selected_frames": [frame1, frame2, ...],
        "error": error_message (if ok=False)
    }
    """
    try:
        comp = fusion.GetCurrentComp()
        if not comp:
            return {"ok": False, "error": "No active composition"}
        
        tool = comp.ActiveTool
        if not tool:
            return {"ok": False, "error": "No active tool"}
        
        tool_name = tool.Name
        
        # Get all inputs and check for animated ones
        inputs = tool.GetInputList()
        all_keyframes = []
        selected_frames = []
        
        for input_id, inp in inputs.items():
            try:
                input_attrs = inp.GetAttrs()
                input_name = input_attrs.get("INPS_Name", input_id)
                
                # Check if this input has a connected output (spline)
                conn = inp.GetConnectedOutput()
                if not conn:
                    continue
                
                # Get the connected spline tool
                spline_tool = conn.GetTool()
                if not spline_tool:
                    continue
                
                # Get spline attributes to check type
                spline_attrs = spline_tool.GetAttrs()
                spline_type = spline_attrs.get("TOOLS_RegID", "")
                
                if "BezierSpline" not in spline_type:
                    continue
                
                # Get the keyframes
                keyframes = spline_tool.GetKeyFrames()
                if not keyframes or not isinstance(keyframes, dict):
                    continue
                
                # Process keyframes
                numeric_frames = []
                for frame, value in keyframes.items():
                    if isinstance(frame, (int, float)):
                        # Extract value from keyframe structure
                        if isinstance(value, dict) and 1 in value:
                            val = value[1]
                        else:
                            val = value
                        
                        # Try to determine if keyframe is selected
                        # Fusion doesn't expose selection directly, but we can infer
                        # from various attributes
                        is_selected = False
                        
                        # Check for selection indicators in the keyframe data
                        if isinstance(value, dict):
                            # Check Flags
                            if "Flags" in value:
                                flags = value["Flags"]
                                if isinstance(flags, dict):
                                    # Selected keyframes often have certain flags
                                    if flags.get("Selected") or flags.get("selected"):
                                        is_selected = True
                            
                            # Check for selection in key name pattern
                            # Sometimes selected keyframes have different structure
                            
                        numeric_frames.append({
                            "frame": float(frame),
                            "value": float(val) if isinstance(val, (int, float)) else 0.0,
                            "input_name": input_name,
                            "selected": is_selected
                        })
                
                all_keyframes.extend(numeric_frames)
                
            except Exception as e:
                continue
        
        # Sort by frame
        all_keyframes.sort(key=lambda x: x["frame"])
        
        # Get selected frames (those marked as selected)
        selected_frames = [kf["frame"] for kf in all_keyframes if kf.get("selected")]
        
        return {
            "ok": True,
            "tool": tool_name,
            "keyframes": all_keyframes,
            "selected_frames": selected_frames,
            "count": len(all_keyframes),
            "selected_count": len(selected_frames)
        }
        
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_all_keyframe_ranges():
    """
    Get all keyframe ranges from the active tool.
    Returns consecutive keyframe pairs for "each segment" mode.
    """
    result = get_selected_keyframes()
    if not result["ok"]:
        return result
    
    keyframes = result["keyframes"]
    if len(keyframes) < 2:
        return {"ok": False, "error": "Need at least 2 keyframes"}
    
    frames = [kf["frame"] for kf in keyframes]
    values = [kf["value"] for kf in keyframes]
    
    # Create segments between consecutive keyframes
    segments = []
    for i in range(len(frames) - 1):
        segments.append({
            "start_frame": frames[i],
            "end_frame": frames[i + 1],
            "start_value": values[i],
            "end_value": values[i + 1]
        })
    
    return {
        "ok": True,
        "tool": result["tool"],
        "segments": segments,
        "all_frames": frames,
        "all_values": values
    }


def save_keyframe_info_to_file(filepath=None):
    """
    Save keyframe information to a JSON file that ReveaceSpline can read.
    """
    if filepath is None:
        # Default to temp location
        filepath = os.path.expandvars("%TEMP%\\reveace_keyframes.json")
    
    result = get_all_keyframe_ranges()
    
    try:
        with open(filepath, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"[Fusion Helper] Saved keyframe info to: {filepath}")
        return {"ok": True, "filepath": filepath, "data": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def print_keyframe_info():
    """
    Print keyframe information to the Fusion console.
    """
    result = get_selected_keyframes()
    
    if not result["ok"]:
        print(f"[Fusion Helper] Error: {result.get('error')}")
        return
    
    print(f"\n[========== Keyframe Info for {result['tool']} ==========]")
    print(f"Total keyframes: {result['count']}")
    print(f"Selected keyframes: {result['selected_count']}")
    
    if result['selected_count'] > 0:
        print(f"\nSelected frames: {result['selected_frames']}")
    
    print("\nAll keyframes:")
    for kf in result['keyframes']:
        sel_marker = " [SELECTED]" if kf.get('selected') else ""
        print(f"  Frame {kf['frame']}: {kf['value']:.4f} ({kf['input_name']}){sel_marker}")
    
    print("[=================================================]\n")


# Auto-run when imported
print("[Fusion Keyframe Helper] Loaded!")
print("[Fusion Keyframe Helper] Available functions:")
print("  - get_selected_keyframes() - Get all keyframes with selection state")
print("  - get_all_keyframe_ranges() - Get keyframe segments")
print("  - save_keyframe_info_to_file() - Save to JSON for ReveaceSpline")
print("  - print_keyframe_info() - Print current keyframe info")
print("")
print("[Fusion Keyframe Helper] Run print_keyframe_info() to see current keyframes.")

# Uncomment to auto-run:
# print_keyframe_info()
