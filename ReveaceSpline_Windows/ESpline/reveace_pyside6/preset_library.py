"""
Unified Preset Library — single source of truth for all presets.

Replaces FavoritesManager + SectionPresetsManager + FavoritesFolderManager.
Every preset (built-in + custom) has a unique ID and knows:
  - mode: "bezier" | "elastic" | "bounce"
  - sections: ["Easing", "Dynamic", ...]  — homescreen section tags
  - folder_id: str | None  — favorites page folder
  - deletable: bool

Data file: favorites.json (v2 format)
"""

import json
import os
import time
from typing import Any

from reveace_pyside6.app_paths import get_data_dir


LIBRARY_FILE = os.path.join(get_data_dir(), "favorites.json")

# Old v1 files (migrated once, then ignored)
_V1_FAV_FILE = os.path.join(get_data_dir(), "favorites.json")
_V1_SECTION_FILE = os.path.join(get_data_dir(), "section_presets.json")
_V1_FOLDER_FILE = os.path.join(get_data_dir(), "favorites_folders.json")


def _next_id(existing_ids: set) -> str:
    """Generate a unique preset ID."""
    n = 1
    while f"preset_{n:03d}" in existing_ids:
        n += 1
    return f"preset_{n:03d}"


class PresetLibrary:
    """Single source of truth for all presets."""

    def __init__(self):
        self._data: dict = {"version": 2, "presets": [], "folders": []}
        self.load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def load(self):
        """Load library from disk. Auto-migrate from v1 if needed."""
        if os.path.exists(LIBRARY_FILE):
            try:
                with open(LIBRARY_FILE, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                if self._data.get("version") != 2:
                    # Corrupt or unexpected version — attempt migration
                    self._migrate_v1_to_v2()
            except Exception:
                self._migrate_v1_to_v2()
        else:
            # No v2 file — check for v1 files to migrate
            self._migrate_v1_to_v2()

    def save(self):
        """Save library to disk."""
        try:
            with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            print(f"[PresetLibrary] Failed to save: {e}")

    # ── Migration ────────────────────────────────────────────────────────────

    def _migrate_v1_to_v2(self):
        """Migrate from old 3-file format to unified v2."""
        # Load old files if they exist
        old_favs = []
        old_sections = {}
        old_folders = {"folders": [], "preset_folders": {}}

        try:
            if os.path.exists(_V1_FAV_FILE):
                with open(_V1_FAV_FILE, "r", encoding="utf-8") as f:
                    old_favs = json.load(f)
        except Exception:
            old_favs = []

        try:
            if os.path.exists(_V1_SECTION_FILE):
                with open(_V1_SECTION_FILE, "r", encoding="utf-8") as f:
                    old_sections = json.load(f)
        except Exception:
            old_sections = {}

        try:
            if os.path.exists(_V1_FOLDER_FILE):
                with open(_V1_FOLDER_FILE, "r", encoding="utf-8") as f:
                    old_folders = json.load(f)
        except Exception:
            old_folders = {"folders": [], "preset_folders": {}}

        # Import PRESETS dict for reliable built-in detection
        try:
            from reveace_pyside6.core import PRESETS
        except Exception:
            PRESETS = {}

        # Build folder ID → folder dict mapping from old folders
        old_folder_map = {}
        for folder in old_folders.get("folders", []):
            old_folder_map[folder["id"]] = folder

        # Build name → sections lookup from old section_presets
        name_to_sections: dict[str, list] = {}
        for section_name, names in old_sections.items():
            for name in names:
                name_to_sections.setdefault(name, []).append(section_name)

        # Migrate presets
        presets = []
        existing_ids = set()
        for idx, fav in enumerate(old_favs):
            name = fav.get("name", "Unnamed")
            # Reliable built-in detection: name must exist in PRESETS dict
            is_built_in = name in PRESETS
            mode = fav.get("mode", "bezier")

            # Derive sections from old section_presets.json name lookup
            sections = list(name_to_sections.get(name, []))

            # For built-ins, also ensure correct section from PRESETS category
            if is_built_in:
                cat = PRESETS.get(name, {}).get("cat", "")
                if cat == "Elastic":
                    mode = "elastic"
                    if "Elastic" not in sections:
                        sections.append("Elastic")
                elif cat == "Bounce":
                    mode = "bounce"
                    if "Bounce" not in sections:
                        sections.append("Bounce")
                elif cat and cat not in sections:
                    sections.append(cat)

            preset_id = _next_id(existing_ids)
            existing_ids.add(preset_id)

            # Derive folder from old index-based mapping
            folder_id = None
            old_pf = old_folders.get("preset_folders", {})
            if str(idx) in old_pf:
                fid = old_pf[str(idx)]
                if fid in old_folder_map:
                    folder_id = fid

            preset = {
                "id": preset_id,
                "name": name,
                "mode": mode,
                "source": "built_in" if is_built_in else "user",
                "preset": name if is_built_in else fav.get("preset"),
                "direction": fav.get("direction", "out"),
                "params": fav.get("params", {}),
                "sections": sections,
                "folder_id": folder_id,
                "deletable": not is_built_in,
            }
            presets.append(preset)

        # Migrate folders
        folders = []
        for folder in old_folders.get("folders", []):
            folders.append({
                "id": folder["id"],
                "name": folder["name"],
                "is_default": folder.get("is_default", False),
            })

        self._data = {"version": 2, "presets": presets, "folders": folders}

        # After migrating custom favorites, seed any missing built-ins from PRESETS dict
        # This ensures Elastic/Bounce presets (which old system didn't store in
        # favorites.json) are present in the unified library.
        if PRESETS:
            self._seed_missing_built_ins(PRESETS)

        self.save()

        # Backup old files
        for src in [_V1_FAV_FILE, _V1_SECTION_FILE, _V1_FOLDER_FILE]:
            if os.path.exists(src):
                try:
                    os.replace(src, src + ".backup")
                except Exception:
                    pass

        total = len(self._data["presets"])
        print(f"[PresetLibrary] Migrated {len(presets)} presets + seeded built-ins = {total} total in v2.")

    def _seed_missing_built_ins(self, presets_dict: dict):
        """Add built-in presets from PRESETS dict that aren't already in the library."""
        existing_names = {p["name"] for p in self._data["presets"]}
        existing_ids = {p["id"] for p in self._data["presets"]}

        for name, data in presets_dict.items():
            if name in existing_names:
                continue
            preset_id = _next_id(existing_ids)
            existing_ids.add(preset_id)
            cat = data.get("cat", "")
            mode = "bezier"
            if cat == "Elastic":
                mode = "elastic"
            elif cat == "Bounce":
                mode = "bounce"

            folder_id = None
            sections = []
            if cat in ("Easing", "Dynamic", "Special"):
                folder_id = f"default_{cat.lower()}"
                sections = [cat]
            elif cat == "Elastic":
                folder_id = "default_elastic"
                sections = ["Elastic"]
            elif cat == "Bounce":
                folder_id = "default_bounce"
                sections = ["Bounce"]

            self._data["presets"].append({
                "id": preset_id,
                "name": name,
                "mode": mode,
                "source": "built_in",
                "preset": name,
                "direction": "out",
                "params": {},
                "sections": sections,
                "folder_id": folder_id,
                "deletable": False,
            })

        # Ensure default folders exist for all categories
        default_names = ["Easing", "Dynamic", "Special", "Elastic", "Bounce"]
        existing_default_names = {f["name"] for f in self._data["folders"] if f.get("is_default")}
        for name in default_names:
            if name not in existing_default_names:
                self._data["folders"].append({
                    "id": f"default_{name.lower()}",
                    "name": name,
                    "is_default": True,
                })

    # ── Queries ──────────────────────────────────────────────────────────────

    def get_all(self) -> list[dict]:
        return list(self._data["presets"])

    def get_by_id(self, preset_id: str) -> dict | None:
        for p in self._data["presets"]:
            if p["id"] == preset_id:
                return p
        return None

    def get_by_mode(self, mode: str) -> list[dict]:
        return [p for p in self._data["presets"] if p.get("mode") == mode]

    def get_by_section(self, section_name: str, mode: str | None = None) -> list[dict]:
        result = []
        for p in self._data["presets"]:
            if section_name in p.get("sections", []):
                if mode is None or p.get("mode") == mode:
                    result.append(p)
        return result

    def get_by_folder(self, folder_id: str | None) -> list[dict]:
        if folder_id is None:
            return [p for p in self._data["presets"] if p.get("folder_id") is None]
        return [p for p in self._data["presets"] if p.get("folder_id") == folder_id]

    def get_sections_for_preset(self, preset_id: str) -> list[str]:
        p = self.get_by_id(preset_id)
        return list(p.get("sections", [])) if p else []

    def get_preset_names_by_section(self, section_name: str) -> list[str]:
        """Return list of preset names in a section (for backward compat)."""
        return [p["name"] for p in self.get_by_section(section_name)]

    def get_folder_for_preset(self, preset_id: str) -> str | None:
        p = self.get_by_id(preset_id)
        return p.get("folder_id") if p else None

    # ── Mutations ────────────────────────────────────────────────────────────

    def add(self, name: str, mode: str, params: dict, direction: str,
            sections: list[str] | None = None, folder_id: str | None = None,
            source: str = "user", preset_ref: str | None = None) -> str:
        """Add a new preset. Returns the new preset_id."""
        existing_ids = {p["id"] for p in self._data["presets"]}
        preset_id = _next_id(existing_ids)

        preset = {
            "id": preset_id,
            "name": name,
            "mode": mode,
            "source": source,
            "preset": preset_ref,
            "direction": direction,
            "params": dict(params),
            "sections": list(sections) if sections else [],
            "folder_id": folder_id,
            "deletable": True,
        }
        self._data["presets"].append(preset)
        self.save()
        return preset_id

    def remove(self, preset_id: str) -> bool:
        """Remove a preset by ID. Returns True if found and removed."""
        for i, p in enumerate(self._data["presets"]):
            if p["id"] == preset_id:
                del self._data["presets"][i]
                self.save()
                return True
        return False

    def remove_multiple(self, preset_ids: list[str]) -> int:
        """Remove multiple presets. Returns count removed."""
        id_set = set(preset_ids)
        before = len(self._data["presets"])
        self._data["presets"] = [p for p in self._data["presets"] if p["id"] not in id_set]
        after = len(self._data["presets"])
        if after != before:
            self.save()
        return before - after

    def rename(self, preset_id: str, new_name: str) -> bool:
        p = self.get_by_id(preset_id)
        if p:
            p["name"] = new_name
            self.save()
            return True
        return False

    def update_params(self, preset_id: str, params: dict) -> bool:
        p = self.get_by_id(preset_id)
        if p:
            p["params"] = dict(params)
            self.save()
            return True
        return False

    # ── Section tags ─────────────────────────────────────────────────────────

    def add_section(self, preset_id: str, section: str) -> bool:
        p = self.get_by_id(preset_id)
        if p and section not in p.get("sections", []):
            p.setdefault("sections", []).append(section)
            self.save()
            return True
        return False

    def remove_section(self, preset_id: str, section: str) -> bool:
        p = self.get_by_id(preset_id)
        if p and section in p.get("sections", []):
            p["sections"].remove(section)
            self.save()
            return True
        return False

    def set_sections(self, preset_id: str, sections: list[str]) -> bool:
        p = self.get_by_id(preset_id)
        if p:
            p["sections"] = list(sections)
            self.save()
            return True
        return False

    # ── Folder management ────────────────────────────────────────────────────

    def move_to_folder(self, preset_id: str, folder_id: str | None) -> bool:
        p = self.get_by_id(preset_id)
        if p:
            p["folder_id"] = folder_id
            self.save()
            return True
        return False

    def create_folder(self, name: str = "New Folder") -> str:
        folder_id = f"folder_{int(time.time() * 1000)}"
        self._data["folders"].append({
            "id": folder_id,
            "name": name,
            "is_default": False,
        })
        self.save()
        return folder_id

    def delete_folder(self, folder_id: str) -> bool:
        """Delete a folder and unassign its presets."""
        before = len(self._data["folders"])
        self._data["folders"] = [f for f in self._data["folders"] if f["id"] != folder_id]
        # Also remove child folders (by convention, non-default folders have no children)
        # Unassign presets
        for p in self._data["presets"]:
            if p.get("folder_id") == folder_id:
                p["folder_id"] = None
        if len(self._data["folders"]) != before:
            self.save()
            return True
        return False

    def rename_folder(self, folder_id: str, new_name: str) -> bool:
        for folder in self._data["folders"]:
            if folder["id"] == folder_id:
                folder["name"] = new_name
                self.save()
                return True
        return False

    def get_folder(self, folder_id: str) -> dict | None:
        for folder in self._data["folders"]:
            if folder["id"] == folder_id:
                return dict(folder)
        return None

    def get_all_folders(self) -> list[dict]:
        return list(self._data["folders"])

    def get_default_folder_id(self, name: str) -> str | None:
        for folder in self._data["folders"]:
            if folder.get("is_default") and folder["name"] == name:
                return folder["id"]
        return None

    def ensure_default_folders(self, names: list[str]):
        """Create default system folders if they don't exist."""
        existing = {f["name"] for f in self._data["folders"] if f.get("is_default")}
        for name in names:
            if name not in existing:
                folder_id = f"default_{name.lower()}"
                self._data["folders"].append({
                    "id": folder_id,
                    "name": name,
                    "is_default": True,
                })
        self.save()

    # ── Seeding built-ins (first run after migration) ────────────────────────

    def seed_built_ins(self, presets_dict: dict):
        """Seed built-in presets from PRESETS dict if library is empty."""
        if self._data["presets"]:
            return

        existing_ids = set()
        for name, data in presets_dict.items():
            preset_id = _next_id(existing_ids)
            existing_ids.add(preset_id)
            cat = data.get("cat", "")
            mode = "bezier"
            if cat == "Elastic":
                mode = "elastic"
            elif cat == "Bounce":
                mode = "bounce"

            # Map category to default folder/section
            folder_id = None
            sections = []
            if cat in ("Easing", "Dynamic", "Special"):
                folder_id = f"default_{cat.lower()}"
                sections = [cat]
            elif cat == "Elastic":
                folder_id = "default_elastic"
                sections = ["Elastic"]
            elif cat == "Bounce":
                folder_id = "default_bounce"
                sections = ["Bounce"]

            self._data["presets"].append({
                "id": preset_id,
                "name": name,
                "mode": mode,
                "source": "built_in",
                "preset": name,
                "direction": "out",
                "params": {},
                "sections": sections,
                "folder_id": folder_id,
                "deletable": False,
            })

        self.ensure_default_folders(["Easing", "Dynamic", "Special", "Elastic", "Bounce"])
        self.save()
        print(f"[PresetLibrary] Seeded {len(presets_dict)} built-in presets.")
