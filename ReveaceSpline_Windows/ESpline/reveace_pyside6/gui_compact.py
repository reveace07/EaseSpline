"""
gui_compact.py — Compact ReveaceSpline PySide6 UI
Clean design: HTML preview + floating controls only
"""

import os
import sys
import json
import time

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGridLayout, QScrollArea, QFrame, QStackedWidget, QSizePolicy,
    QPushButton, QDialog, QListWidget, QInputDialog, QSlider, QComboBox,
    QListWidgetItem, QAbstractItemView, QMenu, QLineEdit, QMessageBox,
    QRubberBand
)
from PySide6.QtCore import Qt, QUrl, QObject, Slot, QTimer, QPoint, QSize, QEvent, QRect, QMimeData
from PySide6.QtGui import QDrag
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QPainterPath

try:
    from .core import ReveaceCore, PRESETS, _sample_physics_curve
    from .theme import (
        get_theme, BrutalButton, IconButton, SectionCard,
        label, accent_label, heading_label,
        make_combo, StyledCheckBox, ModeIconButton
    )
    from .app_paths import get_data_dir
    from .preset_library import PresetLibrary
except ImportError:
    from core import ReveaceCore, PRESETS, _sample_physics_curve
    from theme import (
        get_theme, BrutalButton, IconButton, SectionCard,
        label, accent_label, heading_label,
        make_combo, StyledCheckBox, ModeIconButton
    )
    from app_paths import get_data_dir
    from preset_library import PresetLibrary


# ═══════════════════════════════════════════════════════════════════════════════
# DRAG SELECTION OVERLAY (Draws selection rectangle on top of widgets)
# ═══════════════════════════════════════════════════════════════════════════════
class DragSelectionOverlay(QWidget):
    """Transparent overlay that draws the selection rectangle on top of child widgets."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selection_rect = QRect()
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    
    def setSelectionRect(self, rect):
        """Update the selection rectangle."""
        self._selection_rect = rect
        self.update()
    
    def paintEvent(self, event):
        """Draw the selection rectangle."""
        if not self._selection_rect.isValid() or self._selection_rect.isEmpty():
            return
        
        from PySide6.QtGui import QPainter, QPen, QColor, QBrush
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Blue selection color with transparency (like Windows Explorer)
        fill_color = QColor(0, 120, 215, 60)  # Semi-transparent blue
        border_color = QColor(0, 120, 215, 180)  # More opaque border
        
        # Fill
        painter.fillRect(self._selection_rect, fill_color)
        
        # Border
        pen = QPen(border_color, 1, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawRect(self._selection_rect.adjusted(0, 0, -1, -1))


# ═══════════════════════════════════════════════════════════════════════════════
# MINI CURVE WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class MiniCurveWidget(QWidget):
    """Small painted preview of a curve for preset gallery."""
    clicked = None

    def __init__(self, points, parent=None):
        super().__init__(parent)
        self.points = points or [{"t": 0, "v": 0}, {"t": 1, "v": 1}]
        self.setFixedSize(80, 50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        get_theme().add_listener(self._update_theme)
    
    def _update_theme(self):
        """Redraw when theme changes"""
        self.update()

    def paintEvent(self, event):
        with QPainter(self) as p:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            
            w, h = self.width(), self.height()
            pad = 4
            gw = w - pad * 2
            gh = h - pad * 2

            theme = get_theme()
            bg = QColor(theme.bg_input)
            accent = QColor(theme.accent)

            p.fillRect(self.rect(), bg)

            if not self.points:
                return

            min_v = min(pt["v"] for pt in self.points)
            max_v = max(pt["v"] for pt in self.points)
            spread = max_v - min_v or 1.0
            min_v -= spread * 0.1
            max_v += spread * 0.1
            v_range = max_v - min_v

            def tx(t): return pad + t * gw
            def ty(v): return pad + gh - ((v - min_v) / v_range) * gh

            p.setPen(QPen(QColor(theme.divider), 1))
            p.drawLine(w // 2, pad, w // 2, h - pad)
            p.drawLine(pad, h // 2, w - pad, h // 2)

            path = QPainterPath()
            for i, pt in enumerate(self.points):
                x = tx(pt["t"])
                y = ty(pt["v"])
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.setPen(QPen(accent, 2, Qt.PenStyle.SolidLine))
            p.drawPath(path)

    def set_points(self, points):
        self.points = points or [{"t": 0, "v": 0}, {"t": 1, "v": 1}]
        self.update()

    def mousePressEvent(self, e):
        if self.clicked:
            self.clicked()


# ═══════════════════════════════════════════════════════════════════════════════
# ESPLINE LOGO WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class _EsplineLogo(QWidget):
    """
    Renders espline_logo.svg (viewBox 42×44) in the nav bar.
    Recolours accent (lime rect) and inner dark elements on every theme change.
    """

    def __init__(self, svg_path: str, parent=None):
        super().__init__(parent)
        self._raw_svg = ""
        try:
            with open(svg_path, "r", encoding="utf-8") as f:
                self._raw_svg = f.read()
        except Exception:
            pass
        # Display at 20×20 — matches the height of the nav button text
        self.setFixedSize(20, 20)
        get_theme().add_listener(self.update)   # repaint on theme change

    def _recoloured_svg(self) -> bytes:
        """Swap SVG colours to match the current theme accent."""
        theme  = get_theme()
        accent = theme.accent       # replaces the lime green rect fill
        dark   = theme.bg_card      # replaces rgb(11,11,11) on the curve/dots/E
        svg    = self._raw_svg
        # Green rect and its fill variants
        svg = svg.replace("fill:rgb(197,253,4)", f"fill:{accent}")
        svg = svg.replace("fill:rgb(197,253,4);", f"fill:{accent};")
        # Dark stroke / circle fills / text fill
        svg = svg.replace("fill:rgb(11,11,11)", f"fill:{dark}")
        svg = svg.replace("fill:rgb(11,11,11);", f"fill:{dark};")
        svg = svg.replace("stroke:rgb(11,11,11)", f"stroke:{dark}")
        svg = svg.replace("stroke:rgb(11,11,11);", f"stroke:{dark};")
        return svg.encode("utf-8")

    def paintEvent(self, event):
        from PySide6.QtSvg import QSvgRenderer
        with QPainter(self) as p:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer = QSvgRenderer(self._recoloured_svg())
            renderer.render(p, self.rect())


# ═══════════════════════════════════════════════════════════════════════════════
# SIMPLE SLIDER (with optional editable value)
# ═══════════════════════════════════════════════════════════════════════════════
class SimpleSlider(QWidget):
    """Simple slider with editable value label and throttled callbacks"""
    valueChanged = None      # callback(value)
    sliderReleased = None    # callback() — fired when user releases slider
    
    def __init__(self, label_text, min_val=0, max_val=100, default=50, scale=100, editable=False, parent=None, no_scroll=False):
        super().__init__(parent)
        self.scale = scale
        self.min_val = min_val
        self.max_val = max_val
        self._no_scroll = no_scroll
        self._editable = editable
        
        # Throttling state
        self._pending_value = None
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.timeout.connect(self._emit_pending_value)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(2)
        
        # Label row
        lbl_row = QHBoxLayout()
        self.lbl = QLabel(label_text)
        self.lbl.setStyleSheet(f"color: {get_theme().text_secondary}; font-size: 10px; border: none; background: transparent;")
        
        if editable:
            # Editable value as QLineEdit
            self.val_edit = QLineEdit(f"{default/scale:.2f}")
            self.val_edit.setFixedWidth(50)
            self.val_edit.setStyleSheet(f"""
                QLineEdit {{
                    color: {get_theme().accent};
                    font-size: 10px;
                    border: none;
                    background: transparent;
                    padding: 0;
                }}
            """)
            self.val_edit.setAlignment(Qt.AlignRight)
            self.val_edit.returnPressed.connect(self._on_edit_finished)
            self.val_edit.editingFinished.connect(self._on_edit_finished)
            self.val_edit.installEventFilter(self) # For wheel events
            lbl_row.addWidget(self.lbl)
            lbl_row.addStretch()
            lbl_row.addWidget(self.val_edit)
        else:
            # Read-only value label
            self.val_lbl = QLabel(f"{default/scale:.2f}")
            self.val_lbl.setStyleSheet(f"color: {get_theme().accent}; font-size: 10px; border: none; background: transparent;")
            self.val_lbl.setMinimumWidth(35)
            lbl_row.addWidget(self.lbl)
            lbl_row.addStretch()
            lbl_row.addWidget(self.val_lbl)
        
        layout.addLayout(lbl_row)
        
        # Slider
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(min_val, max_val)
        self.slider.setValue(default)
        self._update_slider_style()
        self.slider.valueChanged.connect(self._on_value_changed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        if no_scroll:
            self.slider.wheelEvent = lambda e: e.ignore()
        layout.addWidget(self.slider)
        
        get_theme().add_listener(self._update_style)
    
    def _update_slider_style(self):
        theme = get_theme()
        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 4px;
                background: {theme.divider};
                border-radius: 2px;
                border: none;
            }}
            QSlider::handle:horizontal {{
                background: {theme.accent};
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
                border: none;
            }}
            QSlider::sub-page:horizontal {{
                background: {theme.accent};
                height: 4px;
                border-radius: 2px;
                border: none;
            }}
        """)
    
    def _update_style(self):
        theme = get_theme()
        self.lbl.setStyleSheet(f"color: {theme.text_secondary}; font-size: 10px; border: none; background: transparent;")
        if self._editable:
            self.val_edit.setStyleSheet(f"""
                QLineEdit {{
                    color: {theme.accent};
                    font-size: 10px;
                    border: none;
                    background: transparent;
                    padding: 0;
                }}
            """)
        else:
            self.val_lbl.setStyleSheet(f"color: {theme.accent}; font-size: 10px; border: none; background: transparent;")
        self._update_slider_style()
    
    def _on_value_changed(self, val):
        float_val = val / self.scale
        if self._editable:
            # ONLY update text if user is not actively typing/scrolling
            if not self.val_edit.hasFocus():
                self.val_edit.setText(f"{float_val:.2f}")
        else:
            self.val_lbl.setText(f"{float_val:.2f}")
        
        # Throttle callback: update UI immediately but delay heavy processing
        self._pending_value = float_val
        if not self._throttle_timer.isActive():
            self._throttle_timer.start(16)  # ~60fps = 16ms
    
    def _on_slider_released(self):
        """Emit final value immediately when slider is released"""
        if self._pending_value is not None:
            self._throttle_timer.stop()
            self._emit_pending_value()
        if self.sliderReleased:
            self.sliderReleased()
    
    def _emit_pending_value(self):
        """Emit the pending value change"""
        if self.valueChanged and self._pending_value is not None:
            self.valueChanged(self._pending_value)
            self._pending_value = None
    
    def _on_edit_finished(self):
        try:
            text = self.val_edit.text()
            val = float(text)
            
            # 1. Update visual slider clamped to soft range
            min_v = self.min_val / self.scale
            max_v = self.max_val / self.scale
            clamped = max(min_v, min(max_v, val))
            
            self.slider.blockSignals(True)
            self.slider.setValue(int(clamped * self.scale))
            self.slider.blockSignals(False)
            
            # 2. Keep the original text if it was unbounded!
            self.val_edit.setText(text)
            
            # 3. Notify listeners of the REAL un-clamped value
            if self.valueChanged:
                self.valueChanged(val)
        except ValueError:
            # Reset to current slider value
            if self._editable:
                self.val_edit.setText(f"{self.slider.value() / self.scale:.2f}")
                
    def eventFilter(self, obj, event):
        if obj == getattr(self, 'val_edit', None) and event.type() == QEvent.Wheel:
            if self._no_scroll:
                event.ignore()
                return True
            delta = event.angleDelta().y()
            try:
                val = float(self.val_edit.text())
                # Shift for large steps, Alt for small steps
                modifiers = QApplication.keyboardModifiers()
                if modifiers & Qt.ShiftModifier: step = 1.0
                elif modifiers & Qt.AltModifier: step = 0.01
                else: step = 0.1
                
                if delta > 0: val += step
                else: val -= step
                
                self.val_edit.setText(f"{val:.2f}")
                self._on_edit_finished()
                return True
            except: pass
        return super().eventFilter(obj, event)
    
    def setValue(self, val):
        # Clamp to slider range to prevent Qt from rejecting the value
        min_val = self.min_val / self.scale
        max_val = self.max_val / self.scale
        clamped = max(min_val, min(max_val, val))
        
        self.slider.blockSignals(True)
        self.slider.setValue(int(clamped * self.scale))
        self.slider.blockSignals(False)
        
        if self._editable:
            self.val_edit.blockSignals(True)
            self.val_edit.setText(f"{val:.2f}")
            self.val_edit.blockSignals(False)
        else:
            self.val_lbl.setText(f"{val:.2f}")
    
    def value(self):
        if self._editable and hasattr(self, 'val_edit'):
            try:
                return float(self.val_edit.text())
            except ValueError:
                pass
        return self.slider.value() / self.scale
    
    def blockSignals(self, block):
        """Block/unblock signals from the slider and value edit"""
        self.slider.blockSignals(block)
        if self._editable and hasattr(self, 'val_edit'):
            self.val_edit.blockSignals(block)


# ═══════════════════════════════════════════════════════════════════════════════
# FAVORITES MANAGER - With Folder Support
# ═══════════════════════════════════════════════════════════════════════════════
class FavoritesManager:
    FAV_FILE = os.path.join(get_data_dir(), "favorites.json")

    def __init__(self):
        self.favorites = []
        self.load()

    def load(self):
        if os.path.exists(self.FAV_FILE):
            try:
                with open(self.FAV_FILE, "r") as f:
                    self.favorites = json.load(f)
            except Exception:
                self.favorites = []

    def save(self):
        try:
            with open(self.FAV_FILE, "w") as f:
                json.dump(self.favorites, f, indent=2)
        except Exception as e:
            print(f"Failed to save favorites: {e}")

    def add(self, name, curve_data):
        self.favorites.append({"name": name, **curve_data})
        self.save()

    def remove_multiple(self, indices):
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(self.favorites):
                del self.favorites[idx]
        self.save()

    def rename(self, index, new_name):
        if 0 <= index < len(self.favorites):
            self.favorites[index]["name"] = new_name
            self.save()
            return True
        return False

    def get_all(self):
        return self.favorites


# ═══════════════════════════════════════════════════════════════════════════════
# FAVORITES FOLDER MANAGER
# ═══════════════════════════════════════════════════════════════════════════════
class FavoritesFolderManager:
    """Manages folders and preset organization for the Favorites page."""
    FOLDER_FILE = os.path.join(get_data_dir(), "favorites_folders.json")
    
    # Default folders that mirror the Bezier page sections
    DEFAULT_FOLDERS = ["Easing", "Dynamic", "Special"]
    
    def __init__(self):
        self.folders = []  # List of folder dicts: {id, name, parent_id, created}
        self.preset_folders = {}  # Map preset_index -> folder_id
        self._default_folder_ids = {}  # Map folder name -> id
        self.load()
    
    def load(self):
        """Load folder structure from file."""
        if os.path.exists(self.FOLDER_FILE):
            try:
                with open(self.FOLDER_FILE, "r") as f:
                    data = json.load(f)
                    self.folders = data.get("folders", [])
                    self.preset_folders = data.get("preset_folders", {})
                    # Convert preset keys back to int
                    self.preset_folders = {int(k): v for k, v in self.preset_folders.items()}
            except Exception:
                self.folders = []
                self.preset_folders = {}
        
        # Create default folders if they don't exist
        self._ensure_default_folders()
    
    def _ensure_default_folders(self):
        """Create default folders (Easing, Dynamic, Special) if they don't exist."""
        existing_names = {f["name"] for f in self.folders}
        
        for name in self.DEFAULT_FOLDERS:
            if name not in existing_names:
                folder_id = self._create_default_folder(name)
                self._default_folder_ids[name] = folder_id
            else:
                # Store existing default folder id
                for f in self.folders:
                    if f["name"] == name:
                        self._default_folder_ids[name] = f["id"]
                        break
    
    def _create_default_folder(self, name):
        """Create a default system folder."""
        import time
        folder_id = f"default_{name.lower()}"
        folder = {
            "id": folder_id,
            "name": name,
            "parent_id": None,
            "created": time.time(),
            "is_default": True
        }
        self.folders.append(folder)
        self.save()
        return folder_id
    
    def get_default_folder_id(self, name):
        """Get the ID of a default folder by name."""
        return self._default_folder_ids.get(name)
    
    def is_default_folder(self, folder_id):
        """Check if a folder is a default folder."""
        for f in self.folders:
            if f["id"] == folder_id:
                return f.get("is_default", False)
        return False
    
    def save(self):
        """Save folder structure to file."""
        try:
            with open(self.FOLDER_FILE, "w") as f:
                json.dump({
                    "folders": self.folders,
                    "preset_folders": self.preset_folders
                }, f, indent=2)
        except Exception as e:
            print(f"Failed to save folders: {e}")
    
    def create_folder(self, name="New Folder", parent_id=None):
        """Create a new folder."""
        import time
        folder_id = f"folder_{int(time.time() * 1000)}"
        folder = {
            "id": folder_id,
            "name": name,
            "parent_id": parent_id,
            "created": time.time()
        }
        self.folders.append(folder)
        self.save()
        return folder_id
    
    def rename_folder(self, folder_id, new_name):
        """Rename a folder."""
        for folder in self.folders:
            if folder["id"] == folder_id:
                folder["name"] = new_name
                self.save()
                return True
        return False
    
    def delete_folder(self, folder_id):
        """Delete a folder and unassign its presets."""
        self.folders = [f for f in self.folders if f["id"] != folder_id]
        # Also delete child folders
        self.folders = [f for f in self.folders if f.get("parent_id") != folder_id]
        # Unassign presets in this folder
        self.preset_folders = {k: v for k, v in self.preset_folders.items() if v != folder_id}
        self.save()
    
    def move_preset_to_folder(self, preset_index, folder_id):
        """Move a preset to a folder."""
        if folder_id is None:
            if preset_index in self.preset_folders:
                del self.preset_folders[preset_index]
        else:
            self.preset_folders[preset_index] = folder_id
        self.save()
    
    def get_folder_for_preset(self, preset_index):
        """Get folder ID for a preset."""
        return self.preset_folders.get(preset_index)
    
    def get_folder_path(self, folder_id):
        """Get full path for a folder."""
        path = []
        current_id = folder_id
        while current_id:
            folder = self.get_folder(current_id)
            if folder:
                path.insert(0, folder["name"])
                current_id = folder.get("parent_id")
            else:
                break
        return path
    
    def get_folder(self, folder_id):
        """Get folder by ID."""
        for folder in self.folders:
            if folder["id"] == folder_id:
                return folder
        return None
    
    def get_child_folders(self, parent_id=None):
        """Get all folders with given parent."""
        return [f for f in self.folders if f.get("parent_id") == parent_id]
    
    def get_presets_in_folder(self, folder_id, total_presets):
        """Get preset indices for a folder."""
        if folder_id is None:
            # Return presets not in any folder
            assigned = set(self.preset_folders.keys())
            return [i for i in range(total_presets) if i not in assigned]
        return [i for i, fid in self.preset_folders.items() if fid == folder_id]
    
    def get_all_presets_in_folder_tree(self, folder_id, total_presets):
        """Get all preset indices in folder and its subfolders."""
        result = self.get_presets_in_folder(folder_id, total_presets)
        for child in self.get_child_folders(folder_id):
            result.extend(self.get_all_presets_in_folder_tree(child["id"], total_presets))
        return result
    
    def import_presets_to_folder(self, presets, folder_name):
        """Import presets into a new folder. Returns preset indices."""
        folder_id = self.create_folder(folder_name)
        start_idx = len(self.preset_folders)
        for i, _ in enumerate(presets):
            self.preset_folders[start_idx + i] = folder_id
        self.save()
        return folder_id


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION PRESETS MANAGER
# ═══════════════════════════════════════════════════════════════════════════════
class SectionPresetsManager:
    """Manages which presets are displayed in each section (Easing, Dynamic, Special, Elastic, Bounce)"""
    PRESETS_FILE = os.path.join(get_data_dir(), "section_presets.json")
    
    # Default presets for each section (from PRESETS categories)
    # NOTE: Order swapped so "Out" curves appear first (matching visual direction)
    DEFAULT_PRESETS = {
        "Easing": ["Linear", "Ease Out", "Ease In", "Ease In-Out", "Ease Out (Cubic)", 
                   "Ease In (Cubic)", "Ease In-Out (Cubic)", "Ease Out (Expo)", 
                   "Ease In (Expo)", "Circular Out", "Circular In", "Circular In-Out",
                   "Back Out", "Back In"],
        "Dynamic": ["Overshoot", "Strong Overshoot", "Anticipate", "Whip", 
                    "Double Back", "Smooth Damp"],
        "Special": ["Step In", "Step Out", "Step Mid", "S-Curve", 
                    "Reverse Ease", "Slow Mo", "Logarithmic"],
        "Elastic": ["Elastic Out", "Elastic In", "Elastic Out (Strong)", "Elastic In (Strong)"],
        "Bounce": ["Bounce Out", "Bounce In", "Bounce Out (Strong)", "Bounce In (Strong)"]
    }
    
    def __init__(self):
        self.section_presets = {}
        self.load()
    
    def load(self):
        """Load section presets from file or use defaults"""
        if os.path.exists(self.PRESETS_FILE):
            try:
                with open(self.PRESETS_FILE, "r") as f:
                    self.section_presets = json.load(f)
            except Exception:
                self.section_presets = dict(self.DEFAULT_PRESETS)
        else:
            self.section_presets = dict(self.DEFAULT_PRESETS)
    
    def save(self):
        """Save section presets to file"""
        try:
            with open(self.PRESETS_FILE, "w") as f:
                json.dump(self.section_presets, f, indent=2)
        except Exception as e:
            print(f"Failed to save section presets: {e}")
    
    def get_presets(self, section):
        """Get presets for a section"""
        return self.section_presets.get(section, [])
    
    def add_preset(self, section, preset_name):
        """Add a preset to a section"""
        if section not in self.section_presets:
            self.section_presets[section] = []
        if preset_name not in self.section_presets[section]:
            self.section_presets[section].append(preset_name)
            self.save()
            return True
        return False
    
    def remove_preset(self, section, preset_name):
        """Remove a preset from a section"""
        if section in self.section_presets and preset_name in self.section_presets[section]:
            self.section_presets[section].remove(preset_name)
            self.save()
            return True
        return False
    
    def remove_presets(self, section, preset_names):
        """Remove multiple presets from a section"""
        if section in self.section_presets:
            for name in preset_names:
                if name in self.section_presets[section]:
                    self.section_presets[section].remove(name)
            self.save()
    
    def reset_to_defaults(self, section=None):
        """Reset to defaults (all sections or specific section)"""
        if section:
            self.section_presets[section] = list(self.DEFAULT_PRESETS.get(section, []))
        else:
            self.section_presets = dict(self.DEFAULT_PRESETS)
        self.save()


# ═══════════════════════════════════════════════════════════════════════════════
# WEB BRIDGE
# ═══════════════════════════════════════════════════════════════════════════════
class WebBridge(QObject):
    def __init__(self, window=None):
        super().__init__()
        self._window = window
        self._pending_curve_callback = None

    @Slot()
    def jsReady(self):
        if self._window:
            self._window._on_preview_ready()

    @Slot(str, float, float)
    def handleMoved(self, handle_type: str, t: float, v: float):
        if self._window:
            self._window._on_handle_moved(handle_type, t, v)

    @Slot(str, float, float)
    def handleDragStarted(self, handle_type: str, t: float, v: float):
        """Called when user starts dragging a handle in the preview canvas"""
        if self._window:
            self._window._on_handle_drag_started(handle_type, t, v)

    @Slot(str, float, float, bool, bool)
    def handleMovedMod(self, handle_type: str, t: float, v: float, shift: bool, ctrl: bool):
        if self._window and hasattr(self._window, '_on_handle_moved_mod'):
            self._window._on_handle_moved_mod(handle_type, t, v, shift, ctrl)

    # ── Section 1: wire the JS handleReleased signal ──────────────────────────
    @Slot()
    def handleReleased(self):
        """Called by JS when the user releases a bezier handle drag."""
        if self._window and hasattr(self._window, '_on_handle_released'):
            self._window._on_handle_released()
    # ─────────────────────────────────────────────────────────────────────────

    @Slot(int, int, int)
    def framesChanged(self, in_frame: int, out_frame: int, duration: int):
        if self._window:
            self._window._on_frames_changed(in_frame, out_frame, duration)
    
    @Slot(list)
    def curvePointsReady(self, points):
        """Called by JS when curve points are ready"""
        if self._pending_curve_callback:
            self._pending_curve_callback(points)
            self._pending_curve_callback = None
    



# ═══════════════════════════════════════════════════════════════════════════════
# FLOATING CONTROLS POPUP - Smooth Animated Version
# ═══════════════════════════════════════════════════════════════════════════════
from PySide6.QtCore import Signal, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QAbstractAnimation

class FloatingControlsPopup(QFrame):
    """Floating popup for curve controls with smooth animations and smart positioning"""
    
    # Signals for communicating with parent instead of direct calls
    bezierXChanged = Signal(float)
    bezierYChanged = Signal(float)
    physicsChanged = Signal(str, float)
    sliderReleased = Signal()       # emitted when any slider is released
    pinRequested   = Signal(dict)   # emits snapshot dict when user clicks pin

    # ── Section 4: animation constants ───────────────────────────────────────
    ANIM_DURATION_SHOW = 150  # ms — snappy entrance
    ANIM_DURATION_HIDE = 200  # ms — slow Spotify-like fade out
    ANIM_EASING_SHOW = QEasingCurve.OutCubic  # clean pop, no overshoot bounce
    ANIM_EASING_HIDE = QEasingCurve.OutQuad   # smooth deceleration on fade
    # ─────────────────────────────────────────────────────────────────────────
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Animation state
        self._opacity = 0.0
        self._scale = 0.92
        self._target_pos = QPoint(0, 0)
        self._is_animating = False
        self._pending_hide = False
        self._pinned = False

        # Content state
        self._sliders = {}
        self._current_handle = None
        self._current_mode = None
        self._content_built = False
        
        self._build_ui()
        self._setup_animations()
        self._apply_theme()
        get_theme().add_listener(self._apply_theme)
        
        # Start hidden
        self.hide()
    
    def _build_ui(self):
        """Build the popup UI with layered containers for shadow and content"""
        # Main container with shadow layers
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 12, 12, 12)  # Space for shadow
        self.main_layout.setSpacing(0)
        
        # Inner container for actual content (no shadow margins)
        self.container = QFrame()
        self.container.setObjectName("popupContainer")
        self.main_layout.addWidget(self.container)
        
        # Content layout inside container
        self.content_layout = QVBoxLayout(self.container)
        self.content_layout.setContentsMargins(10, 8, 10, 8)
        self.content_layout.setSpacing(4)
        
        # Header row: title + pin button
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(4)

        self.header = QLabel()
        self.header.setAlignment(Qt.AlignCenter)
        self.header.setStyleSheet("font-size: 10px; font-weight: bold; padding-bottom: 4px;")
        header_row.addWidget(self.header, 1)

        self.pin_btn = QPushButton()
        self.pin_btn.setFixedSize(16, 16)
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(False)
        self.pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pin_btn.setToolTip("Pin — keep open")
        self.pin_btn.clicked.connect(self._on_pin_toggled)
        self._update_pin_icon()
        header_row.addWidget(self.pin_btn, 0, Qt.AlignTop)

        self.content_layout.addLayout(header_row)
        
        # Content widget that holds sliders
        self.content_widget = QWidget()
        self.content_widget_layout = QVBoxLayout(self.content_widget)
        self.content_widget_layout.setContentsMargins(0, 0, 0, 0)
        self.content_widget_layout.setSpacing(3)
        self.content_layout.addWidget(self.content_widget)
        
        # Connector arrow (visual indicator pointing to trigger)
        self._arrow_size = 10
    
    def _setup_animations(self):
        """Setup smooth entrance and exit animations"""
        # Opacity animation
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(self.ANIM_DURATION_SHOW)
        self._opacity_anim.setEasingCurve(self.ANIM_EASING_SHOW)
        
        # Position animation (slide up) instead of scale to avoid layout squishing
        self._pos_anim = QPropertyAnimation(self, b"pos")
        self._pos_anim.setDuration(self.ANIM_DURATION_SHOW)
        self._pos_anim.setEasingCurve(self.ANIM_EASING_SHOW)
        
        # Animation group for coordinated animations
        self._anim_group = QParallelAnimationGroup()
        self._anim_group.addAnimation(self._opacity_anim)
        self._anim_group.addAnimation(self._pos_anim)
        self._anim_group.finished.connect(self._on_animation_finished)
    
    def _apply_theme(self):
        theme = get_theme()
        
        # Container styling with border and background
        self.container.setStyleSheet(f"""
            QFrame#popupContainer {{
                background-color: {theme.bg_card};
                border: {theme.highlight_border_width}px solid {theme.accent};
                border-radius: 10px;
            }}
            QLabel {{
                color: {theme.text_primary};
                background: transparent;
                border: none;
            }}
        """)
        
        # Update header color
        self.header.setStyleSheet(f"""
            font-size: 10px;
            font-weight: bold;
            padding-bottom: 4px;
            color: {theme.accent};
            background: transparent;
        """)
        self._update_pin_icon()
        
        # Draw layered shadow manually (more performant than QGraphicsDropShadowEffect)
        self._update_shadow()
    
    def _update_shadow(self):
        """Update shadow styling based on theme"""
        # Shadow is handled by padding in main_layout
        # We could add shadow widgets here if needed
        pass
    
    def _animate_show(self, target_geometry):
        """Animate popup entrance with slide up and fade"""
        self._is_animating = True
        self._pending_hide = False
        
        # Calculate start position (slightly offset downward)
        target_pos = target_geometry.topLeft()
        start_pos = QPoint(target_pos.x(), target_pos.y() + 10)
        
        # Setup position animation
        self._pos_anim.setStartValue(start_pos)
        self._pos_anim.setEndValue(target_pos)
        self._pos_anim.setEasingCurve(self.ANIM_EASING_SHOW)
        self._pos_anim.setDuration(self.ANIM_DURATION_SHOW)
        
        # Setup opacity animation
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutQuad)
        self._opacity_anim.setDuration(self.ANIM_DURATION_SHOW)
        
        # Start coordinated animations
        self._anim_group.setDirection(QAbstractAnimation.Forward)
        self.setWindowOpacity(0.0)
        
        # We MUST apply the full size now to avoid squishing
        self.setGeometry(QRect(start_pos, target_geometry.size()))
        self.show()
        self.raise_()
        self._anim_group.start()
    
    def _animate_hide(self):
        """Animate popup exit with fade and slide down"""
        if not self.isVisible() or self._pending_hide:
            return
        
        self._pending_hide = True
        self._is_animating = True
        
        current_pos = self.pos()
        end_pos = QPoint(current_pos.x(), current_pos.y() + 8)
        
        # Setup animations for hide
        self._pos_anim.setStartValue(current_pos)
        self._pos_anim.setEndValue(end_pos)
        self._pos_anim.setEasingCurve(self.ANIM_EASING_HIDE)
        self._pos_anim.setDuration(self.ANIM_DURATION_HIDE)
        
        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(0.0)
        self._opacity_anim.setEasingCurve(self.ANIM_EASING_HIDE)
        self._opacity_anim.setDuration(self.ANIM_DURATION_HIDE)
        
        # Start hide animation
        self._anim_group.setDirection(QAbstractAnimation.Forward)
        self._anim_group.start()
    
    def _on_animation_finished(self):
        """Handle animation completion"""
        self._is_animating = False
        if self._pending_hide or self.windowOpacity() < 0.1:
            self.hide()
            self._pending_hide = False
    
    def _calculate_position(self, global_pos, popup_size, trigger_widget=None):
        """Calculate optimal popup position with screen boundary checking"""
        # Get screen geometry
        from PySide6.QtGui import QScreen
        screen = QApplication.primaryScreen()
        if self.parent():
            screen = QApplication.screenAt(self.parent().mapToGlobal(QPoint(0, 0)))
        if not screen:
            screen = QApplication.primaryScreen()
        
        screen_geo = screen.availableGeometry()
        
        # Default: center popup horizontally under the trigger
        # global_pos.x() is the center of the trigger widget
        x = global_pos.x() - popup_size.width() // 2
        y = global_pos.y() + 4  # tight gap — closes dead zone between pill and popup
        
        # Adjust if would go off right edge
        if x + popup_size.width() > screen_geo.right():
            x = global_pos.x() - popup_size.width() - 10
        
        # Adjust if would go off bottom edge - show above instead
        if y + popup_size.height() > screen_geo.bottom() - 20:
            y = global_pos.y() - popup_size.height() - 15
        
        # Ensure minimum visibility
        x = max(screen_geo.left() + 10, min(x, screen_geo.right() - popup_size.width() - 10))
        y = max(screen_geo.top() + 10, min(y, screen_geo.bottom() - popup_size.height() - 10))
        
        return QPoint(x, y)
    
    def show_bezier_controls(self, handle_type, x_val, y_val, global_pos, trigger_widget=None):
        """Show bezier handle controls with smooth animation"""
        # Same handle already showing — just update values with micro-animation
        if self.isVisible() and self._current_handle == handle_type and not self._pending_hide:
            self._update_bezier_values(x_val, y_val)
            return
        
        # If showing different content, force immediate hide first
        if self.isVisible():
            self._force_hide()
        
        # Clear and rebuild content
        self._clear_content()
        self._current_handle = handle_type
        self._current_mode = None
        
        # Update header
        handle_name = "Left Handle (In)" if handle_type == 'rh' else "Right Handle (Out)"
        self.header.setText(handle_name)
        
        # Build sliders
        x_slider = SimpleSlider("X (Time):", -50, 150, int(x_val * 100), 100, editable=True, parent=self)
        x_slider.valueChanged = self._on_bezier_x_changed
        x_slider.sliderReleased = self.sliderReleased.emit
        self._sliders['x'] = x_slider
        self.content_widget_layout.addWidget(x_slider)
        
        y_slider = SimpleSlider("Y (Value):", -50, 150, int(y_val * 100), 100, editable=True, parent=self)
        y_slider.valueChanged = self._on_bezier_y_changed
        y_slider.sliderReleased = self.sliderReleased.emit
        self._sliders['y'] = y_slider
        self.content_widget_layout.addWidget(y_slider)
        
        # Size and position
        self.setMinimumSize(220, 90)
        self.setMaximumWidth(240)
        # Show at opacity 0 first so Qt polishes child widgets and computes
        # correct size hints — without this, adjustSize() on a hidden widget
        # with fresh (never-shown) children returns stale/default metrics.
        self.setWindowOpacity(0.0)
        self.show()
        self.adjustSize()
        self.hide()

        target_pos = self._calculate_position(global_pos, self.size(), trigger_widget)
        target_geometry = QRect(target_pos, self.size())

        # Animate in
        self._animate_show(target_geometry)
    
    def _update_bezier_values(self, x_val, y_val):
        """Update slider values with visual feedback"""
        if 'x' in self._sliders:
            self._sliders['x'].blockSignals(True)
            self._sliders['x'].setValue(x_val)
            self._sliders['x'].blockSignals(False)
            # Flash the label briefly to indicate update
            self._flash_widget(self._sliders['x'].lbl)
        
        if 'y' in self._sliders:
            self._sliders['y'].blockSignals(True)
            self._sliders['y'].setValue(y_val)
            self._sliders['y'].blockSignals(False)
            self._flash_widget(self._sliders['y'].lbl)
    
    def _flash_widget(self, widget, duration=150):
        """Briefly flash a widget to indicate value change"""
        original_style = widget.styleSheet()
        theme = get_theme()
        flash_style = original_style.replace(theme.text_secondary, theme.accent)
        widget.setStyleSheet(flash_style)
        
        QTimer.singleShot(duration, lambda: widget.setStyleSheet(original_style))
    
    def show_physics_controls(self, mode, params, global_pos, callbacks, trigger_widget=None):
        """Show physics controls with smooth animation"""
        # Same mode already showing — nothing to rebuild
        if self.isVisible() and self._current_mode == mode and not self._pending_hide:
            return
        
        # If showing different content, force immediate hide first
        if self.isVisible():
            self._force_hide()
        
        self._clear_content()
        self._physics_callbacks = callbacks
        self._current_mode = mode
        self._current_handle = None
        
        # Update header
        mode_name = "Elastic" if mode == "elastic" else "Bounce"
        self.header.setText(f"{mode_name} Settings")
        
        if mode == "elastic":
            self._build_elastic_sliders(params)
            self.setMinimumSize(220, 130)
            self.setMaximumWidth(240)
        else:  # bounce
            self._build_bounce_sliders(params)
            self.setMinimumSize(320, 140)
            self.setMaximumWidth(360)
        
        # Show at opacity 0 first so Qt polishes child widgets and computes
        # correct size hints — without this, adjustSize() on a hidden widget
        # with fresh (never-shown) children returns stale/default metrics.
        self.setWindowOpacity(0.0)
        self.show()
        self.adjustSize()
        self.hide()

        target_pos = self._calculate_position(global_pos, self.size(), trigger_widget)
        target_geometry = QRect(target_pos, self.size())

        self._animate_show(target_geometry)
    
    def _build_elastic_sliders(self, params):
        """Build elastic mode sliders in 2 columns"""
        main_row = QWidget()
        row_layout = QHBoxLayout(main_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        
        left_col = QWidget()
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        
        for key, lbl_text, default, max_v in [
            ("bounciness",    "Elastic",    params.get("bounciness", 0.5), 99),
            ("amplitude",     "Amplitude",  params.get("amp", 1.0),        300),
            ("duration_ratio","Duration",   params.get("dur_ratio", 1.0), 100),
        ]:
            slider = SimpleSlider(lbl_text, 0, max_v, int(default * 100), 100, editable=True)
            slider.valueChanged = lambda v, k=key: self._on_physics_changed(k, v)
            slider.sliderReleased = self.sliderReleased.emit
            self._sliders[key] = slider
            left_layout.addWidget(slider)
        
        right_col = QWidget()
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        
        for key, lbl_text, default in [
            ("decay_x", "Decay X", params.get("dx", 0.5)),
            ("decay_y", "Decay Y", params.get("dy", 0.5)),
            ("hang",    "Hang",    params.get("hg", 0.5)),
        ]:
            slider = SimpleSlider(lbl_text, 0, 100, int(default * 100), 100, editable=True)
            slider.valueChanged = lambda v, k=key: self._on_physics_changed(k, v)
            slider.sliderReleased = self.sliderReleased.emit
            self._sliders[key] = slider
            right_layout.addWidget(slider)
            
        row_layout.addWidget(left_col)
        row_layout.addWidget(right_col)
        self.content_widget_layout.addWidget(main_row)
    
    def _build_bounce_sliders(self, params):
        """Build bounce mode sliders in 2 columns"""
        main_row = QWidget()
        row_layout = QHBoxLayout(main_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        
        left_col = QWidget()
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        
        for key, lbl_text, default, max_v in [
            ("bounciness",    "Bounciness", params.get("bounciness", 0.5), 99),
            ("amplitude",     "Amplitude",  params.get("amp", 1.0),        300),
            ("gravity_ratio", "Gravity",    params.get("grav_ratio", 1.0), 100),
        ]:
            slider = SimpleSlider(lbl_text, 0, max_v, int(default * 100), 100, editable=True)
            slider.valueChanged = lambda v, k=key: self._on_physics_changed(k, v)
            slider.sliderReleased = self.sliderReleased.emit
            self._sliders[key] = slider
            left_layout.addWidget(slider)
        
        right_col = QWidget()
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        
        for key, lbl_text, default in [
            ("decay_x", "Decay X", params.get("dx", 0.5)),
            ("decay_y", "Decay Y", params.get("dy", 0.5)),
            ("hang",    "Hang",    params.get("hg", 0.0)),
        ]:
            slider = SimpleSlider(lbl_text, 0, 100, int(default * 100), 100, editable=True)
            slider.valueChanged = lambda v, k=key: self._on_physics_changed(k, v)
            slider.sliderReleased = self.sliderReleased.emit
            self._sliders[key] = slider
            right_layout.addWidget(slider)
        
        row_layout.addWidget(left_col)
        row_layout.addWidget(right_col)
        self.content_widget_layout.addWidget(main_row)
    
    def _clear_content(self):
        """Clear all content widgets"""
        while self.content_widget_layout.count():
            item = self.content_widget_layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._sliders = {}
    
    def _on_bezier_x_changed(self, val):
        self.bezierXChanged.emit(val)
    
    def _on_bezier_y_changed(self, val):
        self.bezierYChanged.emit(val)
    
    def _on_physics_changed(self, param, val):
        self.physicsChanged.emit(param, val)
    
    def _on_pin_toggled(self, checked):
        if not checked:
            return
        # Snapshot current content and spawn an independent PinnedControlPanel
        snapshot = {
            "handle_type": self._current_handle,
            "mode":        self._current_mode,
            "pos":         self.pos(),
            "size":        self.size(),
        }
        if self._current_handle and 'x' in self._sliders and 'y' in self._sliders:
            snapshot["x_val"] = self._sliders['x'].value()
            snapshot["y_val"] = self._sliders['y'].value()
        if self._current_mode and self._sliders:
            # Store as raw integer slider positions (value() returns normalized float)
            snapshot["params_raw"] = {k: int(s.value() * 100) for k, s in self._sliders.items()}
        # Reset pin button and hide hover popup — the panel takes over
        self.pin_btn.setChecked(False)
        self._update_pin_icon()
        self._force_hide()
        self.pinRequested.emit(snapshot)

    def _update_pin_icon(self):
        _icons = os.path.join(os.path.dirname(__file__), "foldersicon")
        pinned = self._pinned
        path = os.path.join(_icons, "icon_pin_on.svg" if pinned else "icon_pin_offf.svg")
        
        from PySide6.QtGui import QIcon
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtGui import QPixmap, QPainter
        
        try:
            with open(path, 'r') as f:
                svg_data = f.read()
            
            theme = get_theme()
            color = theme.accent if pinned else theme.text_secondary
            svg_data = svg_data.replace('currentColor', color)
            
            renderer = QSvgRenderer(svg_data.encode())
            pix = QPixmap(14, 14)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            renderer.render(painter)
            painter.end()
            
            self.pin_btn.setIcon(QIcon(pix))
            self.pin_btn.setIconSize(pix.size())
        except Exception as e:
            print(f"Error loading pin icon: {e}")
        
        self.pin_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(128,128,128,40);
                border-radius: 3px;
            }
        """)

    def hide_popup(self):
        """Hide popup with smooth animation"""
        if self.isVisible() and not self._pending_hide:
            self._animate_hide()

    def _force_hide(self):
        """Force immediate hide without animation - for content switching"""
        self._anim_group.stop()
        self._is_animating = False
        self._pending_hide = False
        self.setWindowOpacity(0.0)
        self.hide()
    
    def enterEvent(self, event):
        """Cancel hide timer when mouse enters popup"""
        p = self.parent()
        if p and hasattr(p, '_hover_hide_timer'):
            p._hover_hide_timer.stop()
        # Cancel pending hide
        if self._pending_hide:
            self._pending_hide = False
            if self._is_animating:
                self._anim_group.stop()
                # Animate back to full opacity
                self._opacity_anim.setStartValue(self.windowOpacity())
                self._opacity_anim.setEndValue(1.0)
                self._opacity_anim.setDuration(100)
                self._opacity_anim.start()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Start hide timer when mouse leaves popup"""
        p = self.parent()
        if p and hasattr(p, '_hover_hide_timer'):
            p._hover_hide_timer.start(200)  # Section 3: 200ms wait then 200ms fade
        super().leaveEvent(event)
    
    def paintEvent(self, event):
        """Custom paint for connector arrow"""
        super().paintEvent(event)
        # Could draw connector arrow here if needed
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# PINNED CONTROL PANEL — Independent floating panel, stays on top always
# ═══════════════════════════════════════════════════════════════════════════════
class PinnedControlPanel(QFrame):
    """Independent pinned panel — Qt.Tool, no parent, stays on top of Resolve.
    Multiple can exist simultaneously (one per pinned control)."""

    bezierXChanged = Signal(float)
    bezierYChanged = Signal(float)
    physicsChanged = Signal(str, float)
    sliderReleased = Signal()         # emitted when any slider is released
    closed         = Signal(object)   # emits self on close

    def __init__(self, snapshot: dict, parent=None):
        super().__init__(None)   # Desktop level — no parent
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self._handle_type  = snapshot.get("handle_type")
        self._mode         = snapshot.get("mode")
        self._drag_pos     = None
        self._sliders      = {}

        self._build_ui(snapshot)
        self._apply_theme()
        get_theme().add_listener(self._apply_theme)

        # Position at same spot as hover popup
        pos  = snapshot.get("pos", QPoint(100, 100))
        self.move(pos)
        self.show()
        self.adjustSize()

        # Mac: force window above all native apps (NSFloatingWindowLevel)
        if sys.platform == "darwin":
            try:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, self._mac_set_topmost)
            except Exception:
                pass

    def _mac_set_topmost(self):
        try:
            import ctypes, ctypes.util
            # Use AppKit via PyObjC if available
            try:
                from AppKit import NSApplication, NSFloatingWindowLevel
                ns_view = self.winId().__int__()
                # Get NSWindow from view
                import objc
                from AppKit import NSView
                view = objc.objc_object(c_void_p=ns_view)
                window = view.window()
                if window:
                    window.setLevel_(NSFloatingWindowLevel)
                    return
            except Exception:
                pass
            # Fallback: use Objective-C runtime directly
            libobjc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
            libobjc.objc_msgSend.restype = ctypes.c_void_p
            libobjc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            sel = libobjc.sel_registerName(b"setLevel:")
            ns_win_ptr = self.winId().__int__()
            # NSFloatingWindowLevel = 3
            libobjc.objc_msgSend(ns_win_ptr, sel, ctypes.c_long(3))
        except Exception:
            pass

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self, snapshot):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(0)

        self.container = QFrame()
        self.container.setObjectName("pinnedContainer")
        outer.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # ── Title bar (drag area) ──────────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(4)

        if self._handle_type:
            title_text = "Left Handle (In)" if self._handle_type == 'rh' else "Right Handle (Out)"
        elif self._mode:
            title_text = "Elastic Settings" if self._mode == "elastic" else "Bounce Settings"
        else:
            title_text = "Controls"

        self.title_lbl = QLabel(title_text)
        self.title_lbl.setStyleSheet("font-size: 10px; font-weight: bold;")
        title_row.addWidget(self.title_lbl, 1)

        # Pin icon — click to unpin/close the panel
        _icons = os.path.join(os.path.dirname(__file__), "foldersicon")
        pin_path = os.path.join(_icons, "icon_pin_on.svg")
        self._pin_btn = QPushButton()
        self._pin_btn.setFixedSize(14, 14)
        self._pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pin_btn.setToolTip("Unpin — close panel")
        self._pin_btn.clicked.connect(self._on_close)
        try:
            from PySide6.QtSvg import QSvgRenderer
            from PySide6.QtGui import QPixmap, QPainter, QIcon
            with open(pin_path, 'r') as f:
                svg_data = f.read()
            theme = get_theme()
            svg_data = svg_data.replace('currentColor', theme.accent)
            renderer = QSvgRenderer(svg_data.encode())
            pix = QPixmap(14, 14)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            renderer.render(painter)
            painter.end()
            self._pin_btn.setIcon(QIcon(pix))
            self._pin_btn.setIconSize(pix.size())
        except Exception:
            pass
        self._pin_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(128,128,128,40);
                border-radius: 3px;
            }
        """)
        title_row.addWidget(self._pin_btn)
        layout.addLayout(title_row)

        # ── Sliders ───────────────────────────────────────────────────────
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(3)
        layout.addWidget(self.content_widget)

        if self._handle_type:
            self._build_bezier_sliders(snapshot)
        elif self._mode == "elastic":
            self._build_elastic_sliders(snapshot)
        elif self._mode == "bounce":
            self._build_bounce_sliders(snapshot)

    def _build_bezier_sliders(self, snapshot):
        x_val = snapshot.get("x_val", 33)
        y_val = snapshot.get("y_val", 0)
        x_slider = SimpleSlider("X (Time):", -50, 150, int(x_val), 100, editable=True, parent=self)
        x_slider.valueChanged = lambda v: self.bezierXChanged.emit(v)
        x_slider.sliderReleased = self.sliderReleased.emit
        self._sliders['x'] = x_slider
        self.content_layout.addWidget(x_slider)

        y_slider = SimpleSlider("Y (Value):", -50, 150, int(y_val), 100, editable=True, parent=self)
        y_slider.valueChanged = lambda v: self.bezierYChanged.emit(v)
        y_slider.sliderReleased = self.sliderReleased.emit
        self._sliders['y'] = y_slider
        self.content_layout.addWidget(y_slider)
        self.setMinimumWidth(220)

    def _build_elastic_sliders(self, snapshot):
        raw = snapshot.get("params_raw", {})
        main_row = QWidget()
        row_layout = QHBoxLayout(main_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        left_col  = QWidget(); left_layout  = QVBoxLayout(left_col);  left_layout.setContentsMargins(0,0,0,0);  left_layout.setSpacing(4)
        right_col = QWidget(); right_layout = QVBoxLayout(right_col); right_layout.setContentsMargins(0,0,0,0); right_layout.setSpacing(4)
        for key, lbl_text, default, max_v in [
            ("bounciness",     "Elastic",   raw.get("bounciness",    50), 99),
            ("amplitude",      "Amplitude", raw.get("amplitude",    100), 300),
            ("duration_ratio", "Duration",  raw.get("duration_ratio",100), 100),
        ]:
            s = SimpleSlider(lbl_text, 0, max_v, int(default), 100, editable=True)
            s.valueChanged = lambda v, k=key: self.physicsChanged.emit(k, v)
            s.sliderReleased = self.sliderReleased.emit
            self._sliders[key] = s
            left_layout.addWidget(s)
        for key, lbl_text, default in [
            ("decay_x", "Decay X", raw.get("decay_x", 50)),
            ("decay_y", "Decay Y", raw.get("decay_y", 50)),
            ("hang",    "Hang",    raw.get("hang",    50)),
        ]:
            s = SimpleSlider(lbl_text, 0, 100, int(default), 100, editable=True)
            s.valueChanged = lambda v, k=key: self.physicsChanged.emit(k, v)
            s.sliderReleased = self.sliderReleased.emit
            self._sliders[key] = s
            right_layout.addWidget(s)
        row_layout.addWidget(left_col)
        row_layout.addWidget(right_col)
        self.content_layout.addWidget(main_row)
        self.setMinimumWidth(320)

    def _build_bounce_sliders(self, snapshot):
        raw = snapshot.get("params_raw", {})
        main_row = QWidget()
        row_layout = QHBoxLayout(main_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        left_col  = QWidget(); left_layout  = QVBoxLayout(left_col);  left_layout.setContentsMargins(0,0,0,0);  left_layout.setSpacing(4)
        right_col = QWidget(); right_layout = QVBoxLayout(right_col); right_layout.setContentsMargins(0,0,0,0); right_layout.setSpacing(4)
        for key, lbl_text, default, max_v in [
            ("bounciness",    "Bounciness", raw.get("bounciness",    50), 99),
            ("amplitude",     "Amplitude",  raw.get("amplitude",    100), 300),
            ("gravity_ratio", "Gravity",    raw.get("gravity_ratio",100), 100),
        ]:
            s = SimpleSlider(lbl_text, 0, max_v, int(default), 100, editable=True)
            s.valueChanged = lambda v, k=key: self.physicsChanged.emit(k, v)
            s.sliderReleased = self.sliderReleased.emit
            self._sliders[key] = s
            left_layout.addWidget(s)
        for key, lbl_text, default in [
            ("decay_x", "Decay X", raw.get("decay_x", 50)),
            ("decay_y", "Decay Y", raw.get("decay_y", 50)),
            ("hang",    "Hang",    raw.get("hang",     0)),
        ]:
            s = SimpleSlider(lbl_text, 0, 100, int(default), 100, editable=True)
            s.valueChanged = lambda v, k=key: self.physicsChanged.emit(k, v)
            s.sliderReleased = self.sliderReleased.emit
            self._sliders[key] = s
            right_layout.addWidget(s)
        row_layout.addWidget(left_col)
        row_layout.addWidget(right_col)
        self.content_layout.addWidget(main_row)
        self.setMinimumWidth(320)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        theme = get_theme()
        self.container.setStyleSheet(f"""
            QFrame#pinnedContainer {{
                background-color: {theme.bg_card};
                border: {theme.highlight_border_width}px solid {theme.accent};
                border-radius: 10px;
            }}
            QLabel {{
                color: {theme.text_primary};
                background: transparent;
                border: none;
            }}
        """)
        self.title_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {theme.accent}; background: transparent;")

    # ── Drag ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        self.closed.emit(self)
        self.close()

    def closeEvent(self, event):
        get_theme().remove_listener(self._apply_theme)
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
# THEME COLOR BUTTON - Shows actual color
# ═══════════════════════════════════════════════════════════════════════════════
class ThemeColorButton(QPushButton):
    def __init__(self, color_name, color_hex, parent=None):
        super().__init__(parent)
        self.color_name = color_name
        self.color_hex = color_hex
        self.setFixedSize(32, 32)
        self.setToolTip(color_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()
        get_theme().add_listener(self._update_style)
    
    def _update_style(self):
        theme = get_theme()
        is_current = theme.current_theme == self.color_name
        border_col = theme.accent if is_current else theme.border_color
        border_w = 3 if is_current else 1
        
        radius = theme.border_radius
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.color_hex};
                border: {border_w}px solid {border_col};
                border-radius: {radius}px;
            }}
        """)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPACT MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════════
class ReveaceWindowCompact(QMainWindow):
    WIDTH = 380
    PREVIEW_HEIGHT = 260

    def __init__(self, core: ReveaceCore):
        super().__init__()
        self.core = core
        self.library = PresetLibrary()
        
        # Favorites page state
        self._fav_current_filter = "all"
        self._fav_current_folder = None
        self._fav_selected_ids = set()
        self._fav_last_selected = None
        self._fav_preset_cards = []
        self._fav_rename_in_progress = False
        self._fav_stay_on_page = True  # When True, clicking a fav card stays on Favorites page
        
        self._preview_ready = False
        self.auto_apply = False
        self.auto_apply_release = True       # ON = apply on release only; OFF = continuous
        self.auto_apply_card = True          # ON = card click auto-applies
        self.auto_apply_bezier = True        # Page 0
        self.auto_apply_elastic = True       # Page 1
        self.auto_apply_bounce = True        # Page 2
        self._pending_auto_apply = False     # Queued apply for release mode
        self._auto_apply_timer = QTimer(self)
        self._auto_apply_timer.setSingleShot(True)
        self._auto_apply_timer.timeout.connect(self._do_pending_auto_apply)
        self._keyframe_target_mode = "recent"  # "all" | "recent" | "custom" | "overwrite"
        self._playhead_filter = True  # When True, restrict "all" and "recent_all" to playhead segment
        self._physics_base_segment = None
        self._physics_base_spline_name = ""
        self._physics_base_left = 0.0
        self._physics_base_right = 0.0
        self._current_heading_idx = 0
        self._current_handle = None  # Track which bezier handle is being edited
        self._shift_pressed = False  # Shift key state for mirrored handles
        self._ctrl_pressed = False   # Ctrl key state for symmetrical/tangent handles
        # NOTE: elastic_sliders and bounce_sliders removed - using unified curve sampler
        self._comp_ref_frames = 60  # default reference, updated when popup opens
        self._curve_flip_enabled = False  # Toggle for curve direction flip in preview
        
        # Drag selection overlay (for section grids - Easing/Dynamic/Special)
        self._drag_select_overlay = None
        
        # Drag selection state flags
        self._drag_select_is_modal = False
        self._drag_select_viewport = None
        
        self.setWindowTitle("Rev EaseSpline")
        self.setMinimumWidth(self.WIDTH)
        self.setMinimumHeight(0)
        self.resize(self.WIDTH, 480)  # Default size, user can resize
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self._prev_resize_y = None  # For top-edge drag detection

        self._build_ui()

        # ── Section 3: hover popup timers ────────────────────────────────────
        # show=80ms (nearly instant, Spotify-like), hide=500ms (consistent everywhere)
        self._hover_pending = None
        self._current_tab_idx = 0
        self._hover_show_timer = QTimer(self)
        self._hover_show_timer.setSingleShot(True)
        self._hover_show_timer.timeout.connect(self._on_hover_show_fired)
        self._hover_hide_timer = QTimer(self)
        self._hover_hide_timer.setSingleShot(True)
        self._hover_hide_timer.timeout.connect(self._on_hover_hide_fired)
        self._popup_trigger_widget = None
        # ── Section 2: drag-release close timer ──────────────────────────────
        self._drag_release_timer = QTimer(self)
        self._drag_release_timer.setSingleShot(True)
        self._drag_release_timer.timeout.connect(self._on_drag_release_timeout)
        # ─────────────────────────────────────────────────────────────────────

        self._connect_signals()
        self._load_preview_html()
        
        get_theme().add_listener(self._on_theme_changed)
        self._on_theme_changed()
        
        # Set Bezier as default tab
        self._switch_tab(0)
        self._set_keyframe_mode("recent")
        
        # ── Live polling for In/Out/Dur from Resolve ────────────────────────────
        self._live_poll_timer = QTimer(self)
        self._live_poll_timer.timeout.connect(self._poll_live_frames)
        self._live_poll_timer.start(150)  # fast 150ms loop
        
        # Debounce timer for pushing frame edits to Resolve
        self._debounce_push_timer = QTimer(self)
        self._debounce_push_timer.setSingleShot(True)
        self._debounce_push_timer.timeout.connect(self._do_push_frame_change)
        self._pending_push_frames = False

    def minimumSizeHint(self):
        """Return zero height so the OS resize handle is never blocked.
        Content clips from the bottom as the window shrinks."""
        return QSize(self.WIDTH, 0)

    def showEvent(self, event):
        super().showEvent(event)
        self._prev_resize_y = self.y()  # Anchor after first show
        ok = self.core.connect_resolve()
        if ok:
            info = self.core.get_resolve_status()
            prod = info.get("info", {}).get("name", "Resolve")
            self.status_lbl.setText(f"Connected: {prod}")
            print(f"[Reveace] Connected to {prod}")
        else:
            err = self.core.bridge.last_error
            self.status_lbl.setText("Resolve: disconnected")
            print(f"[Reveace] Resolve connection failed: {err}")
            print(f"[Reveace] Python version: {__import__('sys').version}")
            print(f"[Reveace] DVR module: {self.core.bridge.dvr}")
            print(f"[Reveace] Resolve obj: {self.core.bridge.resolve}")

        # Mac: make window join all Spaces so it stays visible when DaVinci
        # goes fullscreen (otherwise clicking DaVinci hides this window)
        if sys.platform == "darwin":
            QTimer.singleShot(0, self._mac_main_window_setup)

    def _mac_main_window_setup(self):
        """Set NSWindowCollectionBehaviorCanJoinAllSpaces so the window
        floats across all Mac Spaces including fullscreen DaVinci."""
        try:
            import ctypes, ctypes.util
            libobjc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
            libobjc.objc_msgSend.restype  = ctypes.c_void_p
            libobjc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

            ns_win_ptr = self.winId().__int__()

            # NSWindowCollectionBehaviorCanJoinAllSpaces = 1 << 0  (value 1)
            # NSWindowCollectionBehaviorStationary        = 1 << 4  (value 16)
            # Combine: appear on every Space without jumping
            NSWindowCollectionBehaviorCanJoinAllSpaces = 1
            NSWindowCollectionBehaviorStationary       = 16

            sel_collection = libobjc.sel_registerName(b"setCollectionBehavior:")
            libobjc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
            libobjc.objc_msgSend(
                ns_win_ptr, sel_collection,
                ctypes.c_ulong(NSWindowCollectionBehaviorCanJoinAllSpaces |
                               NSWindowCollectionBehaviorStationary)
            )
        except Exception:
            pass

    def moveEvent(self, event):
        """Keep _prev_resize_y in sync after title-bar moves so bottom-drag
        doesn't falsely detect a top-drag on the next resize."""
        super().moveEvent(event)
        self._prev_resize_y = self.y()

    def resizeEvent(self, event):
        """Directional resize handler:
        - Top edge dragged down (Y increases): collapse preview from top,
          cards stay pinned at their screen position.
        - Bottom edge dragged up (Y unchanged): preview stays full,
          the card stack collapses naturally (minHeight = 0).
        """
        super().resizeEvent(event)
        if not hasattr(self, 'preview_container'):
            return

        curr_y = self.y()
        prev_y = self._prev_resize_y if self._prev_resize_y is not None else curr_y
        dy = curr_y - prev_y
        self._prev_resize_y = curr_y

        if dy > 0:
            # Top edge moved down → shrink preview by exactly that delta
            new_h = max(0, self.preview_container.height() - dy)
            self.preview_container.setFixedHeight(new_h)
        elif dy < 0:
            # Top edge moved up → restore preview by that delta (up to max)
            new_h = min(self.PREVIEW_HEIGHT, self.preview_container.height() + abs(dy))
            self.preview_container.setFixedHeight(new_h)
        # dy == 0: pure bottom-drag — don't touch preview height

    def _build_ui(self):
        print("_build_ui: start", flush=True)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(6, 4, 6, 2)
        layout.setSpacing(2)
        self.setCentralWidget(root)

        # === TOP NAV ===
        nav = QWidget()
        nav_h = QHBoxLayout(nav)
        nav_h.setContentsMargins(0, 0, 0, 0)
        nav_h.setSpacing(4)

        title = QLabel("ESpline")
        title.setStyleSheet(f"color: {get_theme().accent}; font-size: 13px; font-weight: bold;")
        get_theme().add_listener(lambda: title.setStyleSheet(f"color: {get_theme().accent}; font-size: 13px; font-weight: bold;"))
        nav_h.addWidget(title)
        nav_h.addStretch()

        self.btn_bezier = self._create_nav_btn("Bezier")
        self.btn_elastic = self._create_nav_btn("Elastic")
        self.btn_bounce = self._create_nav_btn("Bounce")
        
        from reveace_pyside6.app_paths import get_package_dir
        _icons = os.path.join(get_package_dir(), "foldersicon")
        base_dir = os.path.dirname(__file__)
        path_fav = os.path.join(_icons, "icon_favorites.svg")
        path_settings_off = os.path.join(_icons, "Icon_Settings_off.svg")
        path_settings_on = os.path.join(_icons, "icon_settings_on.svg")

        self.btn_favs = ModeIconButton(path_fav, "Favorites", size=32, icon_size=18)
        self.btn_settings = ModeIconButton(path_settings_off, "Settings", size=32, icon_size=18, svg_path_active=path_settings_on)

        # Curve flip toggle button
        path_flip = os.path.join(_icons, "icon_curve_flip.svg")
        self.btn_flip = ModeIconButton(path_flip, "Flip curve according to keyframe direction", size=32, icon_size=18)
        self.btn_flip.clicked.connect(self._on_flip_toggled)

        nav_h.addWidget(self.btn_bezier)
        nav_h.addWidget(self.btn_elastic)
        nav_h.addWidget(self.btn_bounce)
        nav_h.addWidget(self.btn_favs)
        nav_h.addWidget(self.btn_flip)
        nav_h.addWidget(self.btn_settings)
        layout.addWidget(nav)

        # === PREVIEW ===
        preview_container = QFrame()
        preview_container.setFixedHeight(self.PREVIEW_HEIGHT)
        preview_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        self.preview_container = preview_container  # ref for top-drag collapse in resizeEvent

        print("_build_ui: about to create QWebEngineView", flush=True)
        self.preview = QWebEngineView()
        self.preview.setMinimumHeight(0)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.page().settings().setAttribute(self.preview.page().settings().WebAttribute.ShowScrollBars, False)
        preview_layout.addWidget(self.preview)
        
        # Bottom strip with In/Out/Dur and % pills
        self.bottom_strip = self._build_bottom_strip()
        preview_layout.addWidget(self.bottom_strip)
        
        layout.addWidget(preview_container)
        
        self.floating_popup = FloatingControlsPopup(self)
        self._pinned_panels = []

        # Connect popup signals to handlers
        self.floating_popup.bezierXChanged.connect(self._update_bezier_from_popup)
        self.floating_popup.bezierYChanged.connect(lambda y: self._update_bezier_from_popup(y=y))
        self.floating_popup.physicsChanged.connect(self._on_popup_physics_changed)
        self.floating_popup.sliderReleased.connect(self._do_pending_auto_apply)
        self.floating_popup.pinRequested.connect(self._on_pin_requested)

        print("_build_ui: about to create QWebChannel", flush=True)
        self.channel = QWebChannel()
        self.bridge = WebBridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.preview.page().setWebChannel(self.channel)

        # === ACTION BAR ===
        action_bar = QWidget()
        action_bar.setFixedHeight(44)
        action_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        actions = QHBoxLayout(action_bar)
        actions.setSpacing(6)
        actions.setContentsMargins(4, 4, 4, 4)
        
        _icons = os.path.join(get_package_dir(), "foldersicon")
        path_all = os.path.join(_icons, "icon_all_keyframes.svg")
        path_recent = os.path.join(_icons, "icon_recent_keyframes.svg")
        path_cus = os.path.join(_icons, "icon_custom_range.svg")

        # Keyframe mode icon buttons
        self.btn_mode_all = ModeIconButton(path_all, "All Keyframes", size=36, icon_size=26)
        self.btn_mode_all.setFixedWidth(44)
        self.btn_mode_recent = ModeIconButton(path_recent, "Recent Keyframes", size=36, icon_size=26)
        self.btn_mode_recent.setFixedWidth(44)
        self.btn_mode_custom = ModeIconButton(path_cus, "Custom Range", size=36, icon_size=26)
        self.btn_mode_custom.setFixedWidth(44)

        self.btn_mode_all.clicked.connect(lambda: self._set_keyframe_mode("all"))
        self.btn_mode_recent.clicked.connect(lambda: self._set_keyframe_mode("recent"))
        self.btn_mode_custom.clicked.connect(lambda: self._set_keyframe_mode("custom"))

        # Playhead filter button: when active, "all" and "recent_all" only touch the segment at playhead
        path_playhead = os.path.join(_icons, "icon_playhead.svg")
        self.btn_playhead = ModeIconButton(path_playhead, "Playhead Segment Only", size=36, icon_size=22)
        self.btn_playhead.setFixedWidth(44)
        self.btn_playhead.set_active(True)  # Default ON
        self.btn_playhead.clicked.connect(self._on_playhead_filter_toggle)

        # Overwrite button for physics pages
        path_overwrite = os.path.join(_icons, "icon_overwrite_keyframe.svg")
        self.btn_overwrite = ModeIconButton(path_overwrite, "Overwrite Physics Curve", size=36, icon_size=20)
        self.btn_overwrite.clicked.connect(lambda: self._set_keyframe_mode("overwrite"))
        self.btn_overwrite.hide()
        
        # IN/OUT direction toggle for Elastic/Bounce pages (single button, shown/hidden based on page)
        self.btn_dir = BrutalButton("OUT", variant="accent")
        self.btn_dir.setFixedHeight(40)
        self.btn_dir.setFixedWidth(50)
        self.btn_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dir.clicked.connect(self._on_direction_toggle)
        self.btn_dir.hide()  # Hidden by default, shown on Elastic/Bounce
        
        # Single Apply button - uses smart recent spline detection
        self.btn_apply = BrutalButton("Apply", variant="accent")
        self.btn_apply.setFixedHeight(40)
        self.btn_apply.setMinimumWidth(80)
        
        path_save = os.path.join(get_package_dir(), "foldersicon", "icon_add_favorite.svg")
        self.btn_save = ModeIconButton(path_save, "Save Favorite", size=36, icon_size=20)
        
        # Pin toggle: stay on Favorites page when clicking cards
        _pin_icons = os.path.join(get_package_dir(), "foldersicon")
        self.btn_fav_pin = ModeIconButton(os.path.join(_pin_icons, "icon_pin_on.svg"), "Stay on Favorites page (click card without switching tab)", size=36, icon_size=20, svg_path_active=os.path.join(_pin_icons, "icon_pin_offf.svg"))
        self.btn_fav_pin.set_active(self._fav_stay_on_page)
        self.btn_fav_pin.clicked.connect(self._on_fav_pin_toggled)
        self.btn_fav_pin.hide()  # Only visible on Favorites page
        
        actions.addStretch()
        actions.addWidget(self.btn_fav_pin)
        actions.addWidget(self.btn_mode_all)
        actions.addWidget(self.btn_playhead)
        actions.addWidget(self.btn_mode_recent)
        actions.addWidget(self.btn_mode_custom)
        actions.addWidget(self.btn_overwrite)
        actions.addWidget(self.btn_dir)
        actions.addWidget(self.btn_apply)
        actions.addWidget(self.btn_save)
        layout.addWidget(action_bar)

        # === CONTENT STACK ===
        self.stack = QStackedWidget()
        self.stack.setMinimumHeight(0)
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)

        self.page_bezier = self._build_bezier_page()
        self.page_elastic = self._build_elastic_page()
        self.page_bounce = self._build_bounce_page()
        self.page_favs = self._build_favorites_page()
        self.page_settings = self._build_settings_page()

        self.stack.addWidget(self.page_bezier)
        self.stack.addWidget(self.page_elastic)
        self.stack.addWidget(self.page_bounce)
        self.stack.addWidget(self.page_favs)
        self.stack.addWidget(self.page_settings)

        layout.addWidget(self.stack)

        # === STATUS BAR ===
        self.status_lbl = QLabel("Ready")
        self.status_lbl.setStyleSheet(f"color: {get_theme().text_secondary}; font-size: 9px; padding: 2px 0px;")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setFixedHeight(16)
        layout.addWidget(self.status_lbl)

        self._update_nav_buttons(0)

    def _create_nav_btn(self, text):
        btn = BrutalButton(text, variant="dark")
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _build_bottom_strip(self):
        """Build the bottom strip with In/Out/Dur and % pills/controls"""
        strip = QWidget()
        strip.setFixedHeight(40)
        strip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        
        theme = get_theme()
        strip.setStyleSheet(f"""
            QWidget {{ background-color: {theme.bg_card}; }}
            QLabel {{ color: {theme.text_primary}; font-size: 11px; background: transparent; }}
        """)
        
        # Left side: % pills or Controls label
        pill_style = f"""
            QLabel {{
                color: {theme.text_secondary};
                font-size: 11px;
                padding: 2px 6px;
                border-radius: 3px;
                background: transparent;
            }}
            QLabel:hover {{
                color: {theme.accent};
                background: rgba({int(theme.accent[1:3], 16)}, {int(theme.accent[3:5], 16)}, {int(theme.accent[5:7], 16)}, 0.1);
            }}
        """
        
        self.lbl_rh_pill = QLabel("33%")
        self.lbl_rh_pill.setStyleSheet(pill_style)
        self.lbl_rh_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_rh_pill.installEventFilter(self)

        self.lbl_lh_pill = QLabel("33%")
        self.lbl_lh_pill.setStyleSheet(pill_style)
        self.lbl_lh_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_lh_pill.installEventFilter(self)

        self.lbl_controls = QLabel("Controls")
        self.lbl_controls.setStyleSheet(pill_style)
        self.lbl_controls.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_controls.installEventFilter(self)
        
        layout.addWidget(self.lbl_rh_pill)
        self.lbl_separator = QLabel("|", styleSheet=f"color: {theme.border_color};")
        layout.addWidget(self.lbl_separator)
        layout.addWidget(self.lbl_lh_pill)
        layout.addWidget(self.lbl_controls)
        layout.addStretch()
        
        # Right side: In/Out/Dur (editable with mouse drag)
        # Helper class for drag-editable line edit
        class DragLineEdit(QLineEdit):
            def __init__(self, parent=None, callback=None, min_val=0, max_val=99999):
                super().__init__(parent)
                self._callback = callback
                self._min_val = min_val
                self._max_val = max_val
                self._drag_start_y = None
                self._drag_start_val = None
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            
            def mousePressEvent(self, e):
                if e.button() == Qt.LeftButton:
                    self._drag_start_y = e.globalY()
                    try:
                        self._drag_start_val = int(self.text())
                    except:
                        self._drag_start_val = 0
                    self.setFocus()
                super().mousePressEvent(e)
            
            def mouseMoveEvent(self, e):
                if self._drag_start_y is not None:
                    delta = self._drag_start_y - e.globalY()
                    new_val = self._drag_start_val + int(delta / 2)
                    new_val = max(self._min_val, min(self._max_val, new_val))
                    self.setText(str(new_val))
                    if self._callback:
                        self._callback()
                super().mouseMoveEvent(e)
            
            def mouseReleaseEvent(self, e):
                self._drag_start_y = None
                super().mouseReleaseEvent(e)
                
            def wheelEvent(self, e):
                delta = e.angleDelta().y()
                if delta > 0:
                    self._step_value(1)
                elif delta < 0:
                    self._step_value(-1)
                e.accept()
                
            def keyPressEvent(self, e):
                if e.key() == Qt.Key_Up:
                    self._step_value(1)
                    e.accept()
                elif e.key() == Qt.Key_Down:
                    self._step_value(-1)
                    e.accept()
                else:
                    super().keyPressEvent(e)
                    
            def _step_value(self, step):
                try:
                    val = int(self.text())
                except ValueError:
                    val = 0
                new_val = max(self._min_val, min(self._max_val, val + step))
                self.setText(str(new_val))
                if self._callback:
                    self._callback()
        
        # Right side: In/Out/Dur container
        self.right_strip_container = QWidget()
        right_layout = QHBoxLayout(self.right_strip_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # In
        right_layout.addWidget(QLabel("In", styleSheet=f"color: {theme.text_secondary}; font-size: 10px;"))
        self.lbl_in_frame = DragLineEdit(callback=lambda: self._on_frame_edit('in'), min_val=0)
        self.lbl_in_frame.setMinimumWidth(35)
        self.lbl_in_frame.setMaximumWidth(45)
        self.lbl_in_frame.setStyleSheet(f"""
            QLineEdit {{
                color: {theme.accent};
                font-size: 11px;
                border: none;
                background: transparent;
                padding: 2px 4px;
            }}
        """)
        self.lbl_in_frame.setAlignment(Qt.AlignCenter)
        self.lbl_in_frame.returnPressed.connect(lambda: self._on_frame_edit('in'))
        right_layout.addWidget(self.lbl_in_frame)
        
        right_layout.addWidget(QLabel("—", styleSheet=f"color: {theme.border_color};"))
        
        # Out
        right_layout.addWidget(QLabel("Out", styleSheet=f"color: {theme.text_secondary}; font-size: 10px;"))
        self.lbl_out_frame = DragLineEdit(callback=lambda: self._on_frame_edit('out'), min_val=0)
        self.lbl_out_frame.setMinimumWidth(35)
        self.lbl_out_frame.setMaximumWidth(45)
        self.lbl_out_frame.setStyleSheet(f"""
            QLineEdit {{
                color: {theme.accent};
                font-size: 11px;
                border: none;
                background: transparent;
                padding: 2px 4px;
            }}
        """)
        self.lbl_out_frame.setAlignment(Qt.AlignCenter)
        self.lbl_out_frame.returnPressed.connect(lambda: self._on_frame_edit('out'))
        right_layout.addWidget(self.lbl_out_frame)
        
        # Dur
        right_layout.addWidget(QLabel("Dur", styleSheet=f"color: {theme.text_secondary}; font-size: 10px; margin-left: 6px;"))
        self.lbl_dur = DragLineEdit(callback=lambda: self._on_frame_edit('dur'), min_val=1)
        self.lbl_dur.setMinimumWidth(35)
        self.lbl_dur.setMaximumWidth(45)
        self.lbl_dur.setStyleSheet(f"""
            QLineEdit {{
                color: {theme.text_secondary};
                font-size: 11px;
                border: none;
                background: transparent;
                padding: 2px 4px;
            }}
        """)
        self.lbl_dur.setAlignment(Qt.AlignCenter)
        self.lbl_dur.returnPressed.connect(lambda: self._on_frame_edit('dur'))
        right_layout.addWidget(self.lbl_dur)
        # Flip-value icon: mirrors the actual curve output (v → 1-v)
        from reveace_pyside6.app_paths import get_package_dir
        _flip_icon_path = os.path.join(get_package_dir(), "foldersicon", "icon_flip_values.svg")
        self.btn_flip_value = ModeIconButton(_flip_icon_path, "Mirror curve values", size=22, icon_size=14)
        self.btn_flip_value.clicked.connect(self._on_mirror_values)
        right_layout.addWidget(self.btn_flip_value)
        
        # Add the container to the main layout
        layout.addWidget(self.right_strip_container)
        
        return strip

    # Removed: _set_keyframe_mode - now using smart recent spline detection only

    def _auto_apply_current_page(self):
        """Return whether auto-apply is enabled for the current page."""
        if self.stack.currentIndex() == 0:
            return self.auto_apply_bezier
        elif self.stack.currentIndex() == 1:
            return self.auto_apply_elastic
        else:
            return self.auto_apply_bounce

    def _should_auto_apply(self, source="slider", mode=None):
        """
        source: "slider" | "card" | "combo" | "direction" | "favorite"
        mode: "bezier" | "elastic" | "bounce" (preset mode, for page-aware card checks)
        Returns True if we should apply immediately.
        """
        page = self.stack.currentIndex()
        result = False
        if not self.auto_apply:
            result = False
        elif source in ("card", "favorite") and not self.auto_apply_card:
            result = False
        elif mode == "elastic":
            result = self.auto_apply_elastic
        elif mode == "bounce":
            result = self.auto_apply_bounce
        elif mode == "bezier":
            result = self.auto_apply_bezier
        else:
            result = self._auto_apply_current_page()
        print(f"[AUTO_APPLY] source={source} mode={mode} page={page} master={self.auto_apply} card={self.auto_apply_card} bezier={self.auto_apply_bezier} elastic={self.auto_apply_elastic} bounce={self.auto_apply_bounce} -> {result}")
        return result

    def _trigger_auto_apply(self, source="slider", mode=None):
        """Trigger auto-apply respecting release mode."""
        if not self._should_auto_apply(source, mode=mode):
            return
        if source == "slider" and self.auto_apply_release:
            self._pending_auto_apply = True
            # Start fallback timer: if no release event arrives (e.g. JS drag),
            # apply 200 ms after the last change
            self._auto_apply_timer.stop()
            self._auto_apply_timer.start(200)
        else:
            self._on_apply()

    def _do_pending_auto_apply(self):
        """Called when slider is released or timer fires."""
        self._auto_apply_timer.stop()
        if self._pending_auto_apply:
            self._pending_auto_apply = False
            self._on_apply()

    # ═══════════════════════════════════════════════════════════════════════════
    # UNIFIED PRESET HELPERS (PresetLibrary)
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_preset_preview_points(self, preset: dict):
        """Generate preview curve points for any preset (bezier/elastic/bounce)."""
        mode = preset.get("mode", "bezier")
        if mode == "bezier":
            name = preset.get("preset") or preset.get("name")
            if name in PRESETS:
                return self.core.get_preset_curve_points(name)
            # Custom bezier from saved params
            params = preset.get("params", {})
            rh = params.get("rh", {"t": 0.33, "v": 0.0})
            lh = params.get("lh", {"t": 0.67, "v": 1.0})
            return self._sample_bezier_curve(rh, lh, steps=50)
        else:
            # Physics mode: sample the curve
            params = preset.get("params", {})
            direction = preset.get("direction", "out")
            return _sample_physics_curve(mode, direction, params, steps=100)

    def _load_preset(self, preset: dict):
        """Load a preset dict into core and sync preview."""
        preset_name = preset.get("preset")
        source = preset.get("source", "manual")
        params = preset.get("params", {})

        if source == "built_in" and preset_name and preset_name in PRESETS and not params:
            self.core.select_preset(preset_name)
        else:
            self.core.source = source
            self.core.selected_preset = preset_name
            self.core.mode = preset.get("mode", "bezier")
            self.core.direction = preset.get("direction", "out")
            self.core.params = dict(params)

            if self.core.mode == "bezier":
                if "rh" in params:
                    self.core.manual_rh = dict(params["rh"])
                if "lh" in params:
                    self.core.manual_lh = dict(params["lh"])
            else:
                self.core.invalidate_physics_cache()

            if preset.get("custom_in"):
                self.core.custom_in = preset["custom_in"]
            if preset.get("custom_out"):
                self.core.custom_out = preset["custom_out"]

        if hasattr(self, 'floating_popup'):
            self.floating_popup._current_mode = None

    def _on_fav_pin_toggled(self):
        """Toggle whether clicking a favorite card stays on the Favorites page."""
        self._fav_stay_on_page = not self._fav_stay_on_page
        self.btn_fav_pin.set_active(self._fav_stay_on_page)
        state = "ON" if self._fav_stay_on_page else "OFF"
        self.status_lbl.setText(f"Stay on Favorites page: {state}")

    def _on_card_clicked(self, preset_id: str):
        """Unified click handler for ALL preset cards (homescreen + favorites)."""
        preset = self.library.get_by_id(preset_id)
        if not preset:
            return

        mode = preset.get("mode", "bezier")

        # Switch to correct tab (skip if we're on Favorites page and pin is ON)
        is_favorites_page = (self.stack.currentIndex() == 3)
        if not (is_favorites_page and getattr(self, '_fav_stay_on_page', False)):
            if mode == "elastic":
                self._switch_tab(1)
            elif mode == "bounce":
                self._switch_tab(2)
            else:
                self._switch_tab(0)

        # Reset manual edits in preview
        if getattr(self, '_preview_ready', False):
            self.preview.page().runJavaScript(
                "if(typeof resetManualEdits !== 'undefined') { resetManualEdits(); }")

        # Load preset into core
        self._load_preset(preset)

        # Sync preview
        if mode in ("elastic", "bounce"):
            self._sync_params_to_preview()
        else:
            self._sync_preview_with_core()

        self._trigger_auto_apply("card", mode=mode)
        self.status_lbl.setText(f"Selected: {preset.get('name', 'Preset')}")

    def _section_presets_add_preset_compat(self, section_name: str, preset_name: str) -> bool:
        """Backward-compat: find preset by name and add section tag."""
        for preset in self.library.get_all():
            if preset.get("name") == preset_name:
                return self.library.add_section(preset["id"], section_name)
        return False

    def _refresh_all_pages(self):
        """Refresh all page grids after library changes."""
        self._refresh_section_grid("Easing")
        self._refresh_section_grid("Dynamic")
        self._refresh_section_grid("Special")
        self._refresh_section_grid("Elastic")
        self._refresh_section_grid("Bounce")
        self._refresh_favorites()
        self._refresh_sidebar_folders()

    def _on_frame_edit(self, which):
        """Handle frame value edits and debounce push to Resolve."""
        try:
            if which == 'in':
                val = int(self.lbl_in_frame.text())
                self.core.start_frame = max(0, val)
                # Keep end after start
                if self.core.end_frame <= self.core.start_frame:
                    self.core.end_frame = self.core.start_frame + 1
            elif which == 'out':
                val = int(self.lbl_out_frame.text())
                self.core.end_frame = max(self.core.start_frame + 1, val)
            elif which == 'dur':
                val = int(self.lbl_dur.text())
                self.core.end_frame = self.core.start_frame + max(1, val)
                # Sync Duration/Gravity slider in popup if open
                popup = self.floating_popup
                if popup.isVisible():
                    # Use stable _comp_ref_frames (NOT the new val — that's circular)
                    ref = max(1, self._comp_ref_frames)
                    if hasattr(popup, '_current_mode'):
                        if popup._current_mode == "elastic" and "duration_ratio" in popup._sliders:
                            ratio = min(1.0, max(0.0, val / ref))
                            s = popup._sliders["duration_ratio"]
                            s.slider.blockSignals(True)
                            s.slider.setValue(int(ratio * 100))
                            if hasattr(s, 'val_edit'):
                                s.val_edit.setText(f"{ratio:.2f}")
                            s.slider.blockSignals(False)
                        elif popup._current_mode == "bounce" and "gravity_ratio" in popup._sliders:
                            ratio = min(1.0, max(0.0, val / ref))
                            s = popup._sliders["gravity_ratio"]
                            s.slider.blockSignals(True)
                            s.slider.setValue(int(ratio * 100))
                            if hasattr(s, 'val_edit'):
                                s.val_edit.setText(f"{ratio:.2f}")
                            s.slider.blockSignals(False)
            
            # Update display
            self.lbl_in_frame.setText(str(int(self.core.start_frame)))
            self.lbl_out_frame.setText(str(int(self.core.end_frame)))
            self.lbl_dur.setText(str(int(self.core.end_frame - self.core.start_frame)))
            self._sync_preview_with_core()
            
            # Switch to custom range mode when user edits frames manually
            self._set_keyframe_mode("custom")
            
            # Debounce push to Resolve (prevents choking Resolve during drag)
            self._debounce_push_timer.stop()
            self._pending_push_frames = True
            self._debounce_push_timer.start(50)
        except ValueError:
            # Reset to current values
            self.lbl_in_frame.setText(str(int(self.core.start_frame)))
            self.lbl_out_frame.setText(str(int(self.core.end_frame)))
            self.lbl_dur.setText(str(int(self.core.end_frame - self.core.start_frame)))

    def _poll_live_frames(self):
        """Poll Resolve for current segment frames and update UI live."""
        # Auto-switch to Recent mode whenever the watcher detects a bezier or keyframe change.
        # This fires even from custom/overwrite so the user doesn't have to manually click Recent.
        if self.core.bridge.is_connected() and getattr(self.core.bridge, '_watcher_changed', False):
            self.core.bridge._watcher_changed = False
            current_mode = getattr(self, '_keyframe_target_mode', 'recent')
            # Always clear cached segment on any spline change — stale cache causes
            # intermediate keyframes to be deleted or wrong handles to be used on Apply.
            self.core._target_segment = None
            self.core._target_spline_name = None
            if current_mode not in ('recent', 'recent_all', 'all', 'all_custom'):
                self._set_keyframe_mode("recent")

        # Skip if in custom/overwrite mode (user has manually set range or physics base)
        if getattr(self, '_keyframe_target_mode', 'recent') in ('custom', 'overwrite'):
            return
        # Skip if user is actively editing the fields
        if self.lbl_in_frame.hasFocus() or self.lbl_out_frame.hasFocus() or self.lbl_dur.hasFocus():
            return
        
        if not self.core.bridge.is_connected():
            return
        
        comp = self.core.bridge.get_current_comp()
        if not comp:
            return
        
        try:
            current_time = float(comp.CurrentTime)
        except Exception:
            return
        
        # FIX: Respect the segment cache to prevent physics curves from causing
        # the UI to jump to newly-created sub-segments inside the original range.
        cached_spline = getattr(self.core, "_target_spline_name", None)
        cached_start = getattr(self.core, "start_frame", None)
        cached_end = getattr(self.core, "end_frame", None)
        if (cached_spline and cached_start is not None and cached_end is not None and
            cached_start <= current_time <= cached_end):
            return
        
        # Find target spline (last changed or any BezierSpline)
        spline_tool = None
        spline_name = self.core.bridge.last_changed_spline
        if spline_name:
            try:
                for _, t in comp.GetToolList(False).items():
                    if t.GetAttrs().get("TOOLS_Name") == spline_name:
                        spline_tool = t
                        break
            except Exception:
                pass
        
        if not spline_tool:
            try:
                for _, tool in comp.GetToolList(False, "BezierSpline").items():
                    try:
                        kfs = tool.GetKeyFrames()
                        if kfs and len([f for f in kfs.keys() if isinstance(f, (int, float))]) >= 2:
                            spline_tool = tool
                            break
                    except Exception:
                        pass
            except Exception:
                pass
        
        if not spline_tool:
            return
        
        segment = self.core.bridge.get_adjacent_keyframes(spline_tool, current_time)
        if not segment:
            return
        
        left = float(segment["left_frame"])
        right = float(segment["right_frame"])
        
        # Only update if changed
        if (self.core.start_frame != left or self.core.end_frame != right or
            getattr(self, '_last_poll_left', None) != left or getattr(self, '_last_poll_right', None) != right):
            
            self.core.start_frame = left
            self.core.end_frame = right
            self.core.start_value = segment["left_value"]
            self.core.end_value = segment["right_value"]
            self.core._target_segment = segment
            self.core._target_spline_name = spline_tool.GetAttrs().get("TOOLS_Name", "")
            
            self.lbl_in_frame.setText(str(int(left)))
            self.lbl_out_frame.setText(str(int(right)))
            self.lbl_dur.setText(str(int(right - left)))
            
            self._sync_preview_with_core()
            
            self._last_poll_left = left
            self._last_poll_right = right

    def _do_push_frame_change(self):
        if not getattr(self, '_pending_push_frames', False):
            return
        self._pending_push_frames = False
        self._push_frame_change_to_resolve()

    def _push_frame_change_to_resolve(self):
        """Push In/Out frame changes to Resolve by moving the boundary keyframes."""
        segment = getattr(self.core, '_target_segment', None)
        if not segment:
            return
        
        spline = segment.get("spline")
        if not spline:
            return
        
        comp = self.core.bridge.get_current_comp()
        if not comp:
            return
        
        try:
            kfs = spline.GetKeyFrames()
        except Exception:
            return
        
        old_start = segment.get("left_frame")
        old_end = segment.get("right_frame")
        new_start = int(self.core.start_frame)
        new_end = int(self.core.end_frame)
        
        changed = False
        comp.Lock()
        try:
            if old_start is not None and new_start != old_start and old_start in kfs:
                val = kfs[old_start]
                del kfs[old_start]
                kfs[new_start] = val
                changed = True
                segment["left_frame"] = new_start
            
            if old_end is not None and new_end != old_end and old_end in kfs:
                val = kfs[old_end]
                del kfs[old_end]
                kfs[new_end] = val
                changed = True
                segment["right_frame"] = new_end
            
            if changed:
                self.core.bridge._our_write_timestamp = time.time()
                spline.SetKeyFrames(kfs, True)
                self.core._target_segment = segment
            
            comp.Unlock()
        except Exception as e:
            try:
                comp.Unlock()
            except Exception:
                pass
            print(f"[_push_frame_change_to_resolve] Error: {e}")

    # ── Hover popup: event filter + debounced show/hide ──────────────────────

    def eventFilter(self, obj, event):
        # Reflow fav grid only when viewport WIDTH changes (not height-only from overlay/scrollbar)
        if (event.type() == QEvent.Type.Resize
                and hasattr(self, 'fav_content_scroll')
                and obj is self.fav_content_scroll.viewport()):
            new_w = obj.width()
            if new_w != getattr(self, '_fav_last_vp_width', -1):
                self._fav_last_vp_width = new_w
                if not getattr(self, '_fav_reflow_pending', False):
                    self._fav_reflow_pending = True
                    QTimer.singleShot(80, self._reflow_fav_grid)
            return False

        if event.type() == QEvent.Type.Enter:
            if obj is self.lbl_rh_pill and self._current_tab_idx == 0:
                self._schedule_popup('rh')
                return False
            elif obj is self.lbl_lh_pill and self._current_tab_idx == 0:
                self._schedule_popup('lh')
                return False
            elif obj is self.lbl_controls and self._current_tab_idx in (1, 2):
                self._schedule_popup('controls')
                return False
        elif event.type() == QEvent.Type.Leave:
            if obj in (self.lbl_rh_pill, self.lbl_lh_pill, self.lbl_controls):
                self._hover_show_timer.stop()
                if self.floating_popup.isVisible() and not self.floating_popup.underMouse():
                    self._hover_hide_timer.start(200)  # Section 3: 200ms wait then 200ms fade
                return False
        
        # Check if this is the favorites grid or its viewport/scroll area
        is_fav_grid = False
        if hasattr(self, 'fav_grid_widget') and self.fav_grid_widget:
            if obj is self.fav_grid_widget:
                is_fav_grid = True
            elif obj is self.fav_grid_widget.parent():  # ScrollArea viewport
                is_fav_grid = True
            elif hasattr(obj, 'parent') and obj.parent() is self.fav_grid_widget.parent():
                is_fav_grid = True
        
        # Check for section grid (inner widget) or its viewport/scroll area
        is_section_grid = hasattr(obj, '_is_section_grid') and obj._is_section_grid
        is_section_scroll = hasattr(obj, '_is_section_scroll') and obj._is_section_scroll
        is_section_viewport = False
        section_grid_widget = None
        section_name = None
        
        if is_section_grid:
            section_grid_widget = obj
            section_name = getattr(obj, '_section_name', None)
        elif is_section_scroll:
            # Clicked on scroll area itself - find the inner widget
            if hasattr(obj, 'widget') and obj.widget():
                section_grid_widget = obj.widget()
                section_name = getattr(section_grid_widget, '_section_name', None)
        elif hasattr(obj, 'parent'):
            parent = obj.parent()
            if parent and hasattr(parent, '_is_section_grid') and parent._is_section_grid:
                is_section_viewport = True
                section_grid_widget = parent
                section_name = getattr(parent, '_section_name', None)
            # Also check grandparent (viewport -> scroll area -> grid widget)
            elif parent and hasattr(parent, 'parent'):
                grandparent = parent.parent()
                if grandparent and hasattr(grandparent, '_is_section_grid') and grandparent._is_section_grid:
                    is_section_viewport = True
                    section_grid_widget = grandparent
                    section_name = getattr(grandparent, '_section_name', None)
                # Check for scroll area -> inner widget
                elif grandparent and hasattr(grandparent, '_is_section_scroll') and grandparent._is_section_scroll:
                    is_section_viewport = True
                    if hasattr(grandparent, 'widget') and grandparent.widget():
                        section_grid_widget = grandparent.widget()
                        section_name = getattr(section_grid_widget, '_section_name', None)
        
        # Check for modal grid (Add Preset dialog)
        is_modal_grid = hasattr(obj, '_is_modal_grid') and obj._is_modal_grid
        is_modal_viewport = False
        modal_grid_widget = None
        if not is_modal_grid and hasattr(obj, 'parent'):
            parent = obj.parent()
            if parent and hasattr(parent, '_is_modal_grid') and parent._is_modal_grid:
                is_modal_viewport = True
                modal_grid_widget = parent
            # Also check grandparent for modal (viewport -> scroll area)
            elif parent and hasattr(parent, 'parent'):
                grandparent = parent.parent()
                if grandparent and hasattr(grandparent, '_is_modal_grid') and grandparent._is_modal_grid:
                    is_modal_viewport = True
                    modal_grid_widget = grandparent
        
        target_widget = obj
        if is_section_viewport and section_grid_widget:
            target_widget = section_grid_widget
        elif is_fav_grid:
            target_widget = self.fav_grid_widget
        elif is_modal_viewport and modal_grid_widget:
            target_widget = modal_grid_widget
        
        if (is_fav_grid or is_section_grid or is_section_scroll or is_section_viewport or is_modal_grid or is_modal_viewport):
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    # Check if clicking on empty space (not on a card)
                    try:
                        map_pos = target_widget.mapFromGlobal(event.globalPos())
                        child_at = target_widget.childAt(map_pos)
                        # Allow drag selection if clicking on empty space OR on the grid widget itself
                        if child_at is None or child_at is target_widget:
                            self._start_drag_selection(event, target_widget)
                            return True
                    except Exception as e:
                        pass
            elif event.type() == QEvent.Type.MouseMove:
                if self._drag_select_active:
                    self._update_drag_selection(event, target_widget)
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.LeftButton and self._drag_select_active:
                    if is_modal_grid or is_modal_viewport:
                        self._finish_modal_drag_selection(event, target_widget)
                    else:
                        self._finish_drag_selection(event, target_widget)
                    return True
        
        return super().eventFilter(obj, event)

    def _schedule_popup(self, target):
        """Debounce: wait 80ms before showing — Spotify-like, nearly instant."""
        self._hover_pending = target
        self._hover_hide_timer.stop()
        self._hover_show_timer.start(80)  # Section 3

    def _on_hover_show_fired(self):
        if not self._hover_pending:
            return
        target = self._hover_pending
        # Gate: bezier handles only on tab 0, controls only on physics tabs
        if target in ('rh', 'lh') and self._current_tab_idx != 0:
            self._hover_pending = None
            return
        if target == 'controls' and self._current_tab_idx not in (1, 2):
            self._hover_pending = None
            return
        self._execute_popup_show(target)

    def _on_hover_hide_fired(self):
        if not self.floating_popup.underMouse():
            self.floating_popup.hide_popup()

    def _execute_popup_show(self, target):
        """Execute popup display with smart positioning relative to trigger"""
        # Determine trigger widget and position based on target
        if target == 'rh':
            trigger_widget = self.lbl_rh_pill
            pos = self.lbl_rh_pill.mapToGlobal(QPoint(self.lbl_rh_pill.width() // 2, self.lbl_rh_pill.height()))
        elif target == 'lh':
            trigger_widget = self.lbl_lh_pill
            pos = self.lbl_lh_pill.mapToGlobal(QPoint(self.lbl_lh_pill.width() // 2, self.lbl_lh_pill.height()))
        elif target == 'controls':
            trigger_widget = self.lbl_controls
            pos = self.lbl_controls.mapToGlobal(QPoint(self.lbl_controls.width() // 2, self.lbl_controls.height()))
        else:
            trigger_widget = self.bottom_strip
            pos = self.bottom_strip.mapToGlobal(QPoint(self.bottom_strip.width() // 2, self.bottom_strip.height()))
        
        self._popup_trigger_widget = trigger_widget
        
        if target in ('rh', 'lh'):
            handle_data = self.core.manual_rh if target == 'rh' else self.core.manual_lh
            self._current_handle = target
            self.floating_popup.show_bezier_controls(
                target,
                handle_data.get("t", 0.33 if target == 'rh' else 0.67),
                handle_data.get("v", 0.0 if target == 'rh' else 1.0),
                pos,
                trigger_widget=trigger_widget
            )
        elif target == 'controls':
            self._comp_ref_frames = max(1, int(self.core.end_frame - self.core.start_frame)) * 2
            # Force clear popup mode to ensure fresh values on mode switch
            if self.floating_popup._current_mode != self.core.mode:
                self.floating_popup._current_mode = None
                self.floating_popup.hide_popup()
            
            if self.core.mode == "elastic":
                self.floating_popup.show_physics_controls("elastic", {
                    "amp":       self.core.params.get("amplitude", 1.0),
                    "dur_ratio": self.core.params.get("duration_ratio", 0.5),
                    "dx":        self.core.params.get("decay_x", 0.5),
                    "dy":        self.core.params.get("decay_y", 0.5),
                    "hg":        self.core.params.get("hang", 0.5),
                }, pos, self._on_popup_physics_changed, trigger_widget=trigger_widget)
            elif self.core.mode == "bounce":
                # Invert bounciness for intuitive behavior: high value = more bounce
                raw_bounciness = self.core.params.get("bounciness", 0.5)
                display_bounciness = 0.99 - raw_bounciness  # Invert: 0->0.99, 0.99->0
                self.floating_popup.show_physics_controls("bounce", {
                    "bounciness": display_bounciness,
                    "amp":        self.core.params.get("amplitude", 1.0),
                    "grav_ratio": self.core.params.get("gravity_ratio", 0.5),
                    "dx":         self.core.params.get("decay_x", 0.5),
                    "dy":         self.core.params.get("decay_y", 0.5),
                    "hg":         self.core.params.get("hang", 0.0),
                }, pos, self._on_popup_physics_changed, trigger_widget=trigger_widget)

    def _get_comp_total_frames(self):
        """Read total comp frame count from Fusion comp (GlobalEnd - GlobalStart).
        Falls back to timeline length, then to current Dur box."""
        try:
            bridge = self.core.bridge
            if bridge and bridge.is_connected():
                # Try Fusion comp first (most accurate for Fusion page)
                comp = bridge.get_current_comp()
                if comp:
                    try:
                        attrs = comp.GetAttrs()
                        g_start = attrs.get("COMPN_GlobalStart", None)
                        g_end = attrs.get("COMPN_GlobalEnd", None)
                        if g_start is not None and g_end is not None:
                            total = int(g_end) - int(g_start)
                            if total > 0:
                                return total
                        # Fallback: try RenderEnd - RenderStart
                        r_start = attrs.get("COMPN_RenderStart", None)
                        r_end = attrs.get("COMPN_RenderEnd", None)
                        if r_start is not None and r_end is not None:
                            total = int(r_end) - int(r_start)
                            if total > 0:
                                return total
                    except Exception:
                        pass
                # Fallback: timeline length
                if bridge.resolve:
                    pm = bridge.resolve.GetProjectManager()
                    proj = pm.GetCurrentProject()
                    tl = proj.GetCurrentTimeline()
                    if tl:
                        total = tl.GetEndFrame() - tl.GetStartFrame()
                        if total > 0:
                            return int(total)
        except Exception:
            pass
        return max(1, int(self.core.end_frame - self.core.start_frame))

    def _update_nav_buttons(self, active_idx):
        buttons = [self.btn_bezier, self.btn_elastic, self.btn_bounce]
        for i, btn in enumerate(buttons):
            self._set_button_variant(btn, "accent" if i == active_idx else "dark")
            
        self.btn_favs.set_active(active_idx == 3)
        self.btn_settings.set_active(active_idx == 4)
        self.btn_flip.set_active(self._curve_flip_enabled)
        self.btn_flip_value.setVisible(active_idx == 0)

    def _on_flip_toggled(self):
        """Toggle curve flip direction in preview."""
        self._curve_flip_enabled = not self._curve_flip_enabled
        self._update_nav_buttons(self.stack.currentIndex())

        # Fix mode: when enabling flip for flat bezier keypoints, auto-set handles
        # to produce a visible S-curve oscillation around the baseline value.
        if (self._curve_flip_enabled
                and self.stack.currentIndex() == 0
                and abs(self.core.start_value - self.core.end_value) < 0.0001):
            self.core.manual_rh = {"t": 0.33, "v": 0.0}
            self.core.manual_lh = {"t": 0.67, "v": 1.0}
            self.status_lbl.setText("Fix mode ON: curve adjusted for flat keypoints")
            self._sync_preview_with_core()
            return

        self._sync_preview_with_core()
        state = "ON" if self._curve_flip_enabled else "OFF"
        self.status_lbl.setText(f"Curve flip {state}")

    def _on_mirror_values(self):
        """Mirror the actual curve output values (v → 1-v).
        For bezier: flips both handle Y values.
        For elastic/bounce: swaps start/end values so oscillation goes the other way.
        For page-0 XY handles: x→1-x, y→1-y.
        """
        tab = self.stack.currentIndex()
        if tab == 0:  # Bezier handle page — mirror both X and Y
            if hasattr(self, 'floating_popup') and self.floating_popup:
                js = """
                    if(typeof rh !== 'undefined' && typeof lh !== 'undefined'){
                        rh = {t: 1.0 - rh.t, v: 1.0 - rh.v};
                        lh = {t: 1.0 - lh.t, v: 1.0 - lh.v};
                        if(bridge && bridge.handleMoved){ bridge.handleMoved('rh', rh.t, rh.v); }
                        if(bridge && bridge.handleMoved){ bridge.handleMoved('lh', lh.t, lh.v); }
                        queueDraw();
                    }
                """
                self.preview.page().runJavaScript(js)
                # Mirror core handles too
                self.core.manual_rh = {"t": 1.0 - self.core.manual_rh["t"], "v": 1.0 - self.core.manual_rh["v"]}
                self.core.manual_lh = {"t": 1.0 - self.core.manual_lh["t"], "v": 1.0 - self.core.manual_lh["v"]}
        else:  # Elastic / Bounce — swap start/end values so oscillation flips direction
            self.core.start_value, self.core.end_value = self.core.end_value, self.core.start_value
            self._sync_preview_with_core()
        self.status_lbl.setText("Values mirrored")

    def _set_button_variant(self, button, variant):
        theme = get_theme()
        bg = theme.accent if variant == "accent" else theme.bg_input
        fg = theme.bg_input if variant == "accent" else theme.text_primary
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: {theme.border_width}px solid {theme.border_color};
                border-radius: {theme.border_radius}px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }}
        """)

    def _build_bezier_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Heading buttons
        headings = QWidget()
        hlay = QHBoxLayout(headings)
        hlay.setContentsMargins(2, 0, 2, 0)
        hlay.setSpacing(3)

        self.btn_easing = self._create_heading_btn("EASING")
        self.btn_dynamic = self._create_heading_btn("DYNAMIC")
        self.btn_special = self._create_heading_btn("SPECIAL")
        self.btn_custom = self._create_heading_btn("CUSTOM")

        hlay.addWidget(self.btn_easing)
        hlay.addWidget(self.btn_dynamic)
        hlay.addWidget(self.btn_special)
        hlay.addWidget(self.btn_custom)
        layout.addWidget(headings)

        # Content stack
        self.bezier_stack = QStackedWidget()
        
        # Build grids with section names and user-customizable presets
        self.easing_grid = self._build_preset_grid(
            [p["id"] for p in self.library.get_by_section("Easing", mode="bezier")], "Easing")
        self.dynamic_grid = self._build_preset_grid(
            [p["id"] for p in self.library.get_by_section("Dynamic", mode="bezier")], "Dynamic")
        self.special_grid = self._build_preset_grid(
            [p["id"] for p in self.library.get_by_section("Special", mode="bezier")], "Special")
        
        self.bezier_stack.addWidget(self.easing_grid)
        self.bezier_stack.addWidget(self.dynamic_grid)
        self.bezier_stack.addWidget(self.special_grid)
        self.bezier_stack.addWidget(self._build_custom_section())
        
        layout.addWidget(self.bezier_stack)

        self.btn_easing.clicked.connect(lambda: self._on_heading_clicked(0))
        self.btn_dynamic.clicked.connect(lambda: self._on_heading_clicked(1))
        self.btn_special.clicked.connect(lambda: self._on_heading_clicked(2))
        self.btn_custom.clicked.connect(lambda: self._on_heading_clicked(3))
        self._on_heading_clicked(0)
        
        return page

    def _create_heading_btn(self, text):
        btn = QPushButton(text)
        btn.setFixedHeight(24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    def _on_heading_clicked(self, idx):
        self.bezier_stack.setCurrentIndex(idx)
        self._current_heading_idx = idx
        self._update_heading_buttons()
    
    def _update_heading_buttons(self):
        buttons = [self.btn_easing, self.btn_dynamic, self.btn_special, self.btn_custom]
        for i, btn in enumerate(buttons):
            self._set_heading_button_style(btn, i == self._current_heading_idx)
    
    def _set_heading_button_style(self, button, is_active):
        theme = get_theme()
        if is_active:
            color = theme.text_primary
            font_size = "11px"
            weight = "bold"
        else:
            color = theme.text_secondary
            font_size = "11px"
            weight = "bold"
        
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {color};
                border: none;
                padding: 0px 4px;
                font-weight: {weight};
                font-size: {font_size};
            }}
            QPushButton:hover {{
                color: {theme.accent};
            }}
        """)

    def _build_preset_grid(self, preset_ids, section_name=None):
        """Build preset grid with 'Add Preset' box at the end"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        inner = QWidget()
        inner._preset_ids = list(preset_ids)  # Don't sort - preserve user order
        inner._section_name = section_name
        inner._parent_ref = self
        
        grid = QGridLayout(inner)
        grid.setSpacing(6)
        grid.setContentsMargins(4, 4, 4, 4)
        
        # Clear any existing section cards tracking
        if section_name and hasattr(self, '_section_preset_cards'):
            self._section_preset_cards[section_name] = []
        
        # Build preset cards
        cards = []
        for preset_id in inner._preset_ids:
            card = self._build_preset_card(preset_id, section_name)
            cards.append(card)
        
        # Add "Add Preset" box for Easing, Dynamic, Special, Elastic, Bounce sections (not Custom)
        if section_name and section_name != "Custom":
            add_box = self._build_add_preset_box(section_name)
            cards.append(add_box)
        
        # Initial layout with 3 columns
        for i, card in enumerate(cards):
            grid.addWidget(card, i // 3, i % 3)
        
        scroll.setWidget(inner)
        
        # Override resizeEvent on the scroll area to reflow the grid
        orig_resize = scroll.resizeEvent
        def _on_resize(event):
            orig_resize(event)
            w = scroll.viewport().width()
            card_w = 106  # card width (100) + spacing (6)
            cols = max(1, w // card_w)
            layout = inner.layout()
            # Re-add all widgets to the grid with new column count
            widgets = []
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    widgets.append(item.widget())
            for i, widget in enumerate(widgets):
                layout.addWidget(widget, i // cols, i % cols)
        scroll.resizeEvent = _on_resize
        
        # Enable drag selection for section grids
        if section_name:
            inner.setMouseTracking(True)
            inner.installEventFilter(self)
            scroll.viewport().setMouseTracking(True)
            scroll.viewport().installEventFilter(self)
            # Store references for drag selection
            inner._is_section_grid = True
            inner._section_name = section_name
            
            # Also mark the scroll area itself for proper identification
            scroll._is_section_scroll = True
            scroll._section_name = section_name
        
        return scroll

    def _build_preset_card(self, preset_id, section=None):
        """Build a preset card widget. If section is provided, enables multi-selection."""
        preset = self.library.get_by_id(preset_id)
        if not preset:
            # Fallback: empty card
            container = QWidget()
            container.setFixedSize(100, 70)
            return container

        name = preset.get("name", "Unnamed")
        container = QWidget()
        container.setCursor(Qt.CursorShape.PointingHandCursor)
        container.setFixedSize(100, 70)
        
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(4, 4, 4, 4)
        vlay.setSpacing(2)
        vlay.setAlignment(Qt.AlignCenter)

        points = self._get_preset_preview_points(preset)
        mini = MiniCurveWidget(points)
        mini.setFixedSize(70, 40)
        # For section cards, make mini widget transparent to mouse events
        # so the container can handle multi-selection
        if section:
            mini.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        else:
            mini.clicked = lambda pid=preset_id: self._on_card_clicked(pid)

        lbl = QLabel(name)
        lbl.setStyleSheet(f"color: {get_theme().text_primary}; font-size: 9px;")
        lbl.setAlignment(Qt.AlignCenter)

        vlay.addWidget(mini)
        vlay.addWidget(lbl)

        theme = get_theme()
        container.setObjectName("PresetCard")
        container._preset_id = preset_id
        container._preset_name = name
        container._section = section
        container._selected = False
        
        # Apply styles
        self._update_preset_card_style(container)
        
        # Store reference for multi-selection
        if section:
            if not hasattr(self, '_section_preset_cards'):
                self._section_preset_cards = {}
            if section not in self._section_preset_cards:
                self._section_preset_cards[section] = []
            self._section_preset_cards[section].append(container)
        
        container.mousePressEvent = lambda e, pid=preset_id, c=container: self._on_preset_card_clicked(e, pid, c)
        
        # Add context menu for section presets
        if section:
            def context_menu_event(event):
                menu = QMenu(container)
                menu.setStyleSheet(f"""
                    QMenu {{ background-color: {get_theme().bg_card}; color: {get_theme().text_primary}; border: 1px solid {get_theme().border_color}; }}
                    QMenu::item:selected {{ background-color: {get_theme().accent}; color: {get_theme().bg_card}; }}
                """)
                
                # Only show remove for actual presets (not the Add box)
                if hasattr(container, '_preset_id') and container._preset_id:
                    action_remove = menu.addAction("Remove from Section")
                    action_remove.triggered.connect(lambda: self._remove_preset_from_section(section, container._preset_id))
                    menu.addSeparator()
                
                action_reset = menu.addAction("Reset Section to Defaults")
                action_reset.triggered.connect(lambda: self._reset_section_to_defaults(section))
                
                menu.exec(event.globalPos())
            
            container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            container.customContextMenuRequested.connect(lambda pos, c=container: context_menu_event(pos))
        
        return container
    
    def _remove_preset_from_section(self, section_name, preset_id):
        """Remove a single preset from a section"""
        preset = self.library.get_by_id(preset_id)
        if preset and self.library.remove_section(preset_id, section_name):
            self._refresh_section_grid(section_name)
            self.status_lbl.setText(f"Removed {preset.get('name', 'Preset')} from {section_name}")
    
    def _reset_section_to_defaults(self, section_name):
        """Reset a section to its default presets"""
        from PySide6.QtWidgets import QMessageBox
        
        reply = QMessageBox.question(
            self, "Reset Section",
            f"Reset {section_name} section to default presets?\n\nThis will remove any custom additions.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove section tag from all custom presets in this section
            for preset in self.library.get_by_section(section_name):
                if preset.get("deletable"):
                    self.library.remove_section(preset["id"], section_name)
            # Ensure built-ins have the section tag
            for preset in self.library.get_all():
                if not preset.get("deletable") and section_name in preset.get("sections", []):
                    # Already has it — built-ins are correct by design
                    pass
            self._refresh_section_grid(section_name)
            self.status_lbl.setText(f"Reset {section_name} to defaults")
    
    def _update_preset_card_style(self, card):
        """Update preset card styling based on selection state"""
        theme = get_theme()
        if getattr(card, '_selected', False):
            # Selected state - highlighted
            card.setStyleSheet(f"""
                #PresetCard {{ background: {theme.bg_card}; 
                    border: {theme.highlight_border_width}px solid {theme.accent}; 
                    border-radius: {theme.border_radius}px; }}
            """)
        else:
            # Normal state
            card.setStyleSheet(f"""
                #PresetCard {{ background: {theme.bg_card}; 
                    border: {theme.border_width}px solid {theme.border_color}; 
                    border-radius: {theme.border_radius}px; }}
                #PresetCard:hover {{ border-color: {theme.accent}; }}
            """)
    
    def _on_preset_card_clicked(self, event, preset_id, card):
        """Handle preset card click with multi-selection support (Ctrl+Click, Shift+Click)"""
        from PySide6.QtWidgets import QApplication
        
        modifiers = QApplication.keyboardModifiers()
        ctrl_pressed = modifiers & Qt.KeyboardModifier.ControlModifier
        shift_pressed = modifiers & Qt.KeyboardModifier.ShiftModifier
        section = getattr(card, '_section', None)
        
        if ctrl_pressed and section:
            # Ctrl+Click: Toggle selection
            card._selected = not card._selected
            self._update_preset_card_style(card)
            
            # Update last selected anchor
            if not hasattr(self, '_shift_selection_anchor'):
                self._shift_selection_anchor = {}
            self._shift_selection_anchor[section] = card
            
        elif shift_pressed and section:
            # Shift+Click: Range selection
            if not hasattr(self, '_shift_selection_anchor'):
                self._shift_selection_anchor = {}
            
            anchor_card = self._shift_selection_anchor.get(section)
            
            if anchor_card and anchor_card in self._section_preset_cards.get(section, []):
                # Get all cards in this section
                all_cards = self._section_preset_cards[section]
                
                # Find indices
                try:
                    anchor_idx = all_cards.index(anchor_card)
                    current_idx = all_cards.index(card)
                except ValueError:
                    anchor_idx = -1
                    current_idx = -1
                
                if anchor_idx >= 0 and current_idx >= 0:
                    start_idx = min(anchor_idx, current_idx)
                    end_idx = max(anchor_idx, current_idx)
                    
                    # Select all cards in range
                    for i in range(start_idx, end_idx + 1):
                        all_cards[i]._selected = True
                        self._update_preset_card_style(all_cards[i])
            else:
                # No anchor, just toggle this card
                card._selected = True
                self._update_preset_card_style(card)
            
            self._shift_selection_anchor[section] = card
            
        else:
            # Normal click - if already selected and only one selected, apply it
            # Otherwise clear and select this one
            is_already_selected = card._selected
            
            if section and hasattr(self, '_section_preset_cards'):
                selected_count = sum(1 for c in self._section_preset_cards.get(section, []) if c._selected)
                
                if is_already_selected and selected_count == 1:
                    # Apply the preset
                    self._on_card_clicked(preset_id)
                    return
                
                # Clear other selections
                for c in self._section_preset_cards.get(section, []):
                    if c._selected:
                        c._selected = False
                        self._update_preset_card_style(c)
            
            # Select this card
            card._selected = True
            self._update_preset_card_style(card)
            
            # Update anchor
            if not hasattr(self, '_shift_selection_anchor'):
                self._shift_selection_anchor = {}
            self._shift_selection_anchor[section] = card
            
            # Apply the preset
            self._on_card_clicked(preset_id)
    
    def _build_add_preset_box(self, section_name):
        """Build the empty 'Add Preset' box with dashed border and plus icon"""
        container = QWidget()
        container.setCursor(Qt.CursorShape.PointingHandCursor)
        container.setFixedSize(100, 70)
        container.setObjectName("AddPresetBox")
        
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(4, 4, 4, 4)
        vlay.setSpacing(4)
        vlay.setAlignment(Qt.AlignCenter)
        
        # Plus icon (using QLabel with custom paint or unicode)
        plus_lbl = QLabel("+")
        plus_lbl.setAlignment(Qt.AlignCenter)
        plus_lbl.setStyleSheet("""
            color: #606060; 
            font-size: 28px; 
            font-weight: bold;
            margin-top: 5px;
        """)
        
        # Text label
        text_lbl = QLabel("Add Preset")
        text_lbl.setAlignment(Qt.AlignCenter)
        text_lbl.setStyleSheet("""
            color: #606060; 
            font-size: 10px; 
            font-weight: bold;
        """)
        
        vlay.addWidget(plus_lbl)
        vlay.addWidget(text_lbl)
        
        # Dashed border styling
        container.setStyleSheet("""
            #AddPresetBox {
                background: #1a1a1a;
                border: 2px dashed #606060;
                border-radius: 15px;
            }
            #AddPresetBox:hover {
                border-color: #808080;
                background: #202020;
            }
        """)
        
        container.mousePressEvent = lambda e, s=section_name: self._on_add_preset_clicked(s)
        return container

    def _build_custom_section(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        
        CUSTOM_OPTIONS = ["Linear", "Sine", "Quad", "Cubic", "Quart", "Quint", "Expo", "Circ", "Back"]
        
        layout.addWidget(QLabel("In:", styleSheet=f"color: {get_theme().text_primary}; font-size: 11px;"))
        self.combo_in = make_combo(CUSTOM_OPTIONS)
        self.combo_in.currentTextChanged.connect(self._on_custom_changed)
        layout.addWidget(self.combo_in)
        
        layout.addWidget(QLabel("Out:", styleSheet=f"color: {get_theme().text_primary}; font-size: 11px;"))
        self.combo_out = make_combo(CUSTOM_OPTIONS)
        self.combo_out.currentTextChanged.connect(self._on_custom_changed)
        layout.addWidget(self.combo_out)
        
        layout.addStretch()
        return page

    def _build_elastic_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(6)

        # Small hint at top
        hint = QLabel("Click 'Controls' in strip above to adjust elastic")
        hint.setStyleSheet(f"color: {get_theme().text_secondary}; font-size: 10px;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        # Preset grid for Elastic section
        self.elastic_grid = self._build_preset_grid(
            [p["id"] for p in self.library.get_by_mode("elastic")], "Elastic")
        layout.addWidget(self.elastic_grid)

        return page

    def _build_bounce_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(6)

        # Small hint at top
        hint = QLabel("Click 'Controls' in strip above to adjust bounce")
        hint.setStyleSheet(f"color: {get_theme().text_secondary}; font-size: 10px;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        # Preset grid for Bounce section
        self.bounce_grid = self._build_preset_grid(
            [p["id"] for p in self.library.get_by_mode("bounce")], "Bounce")
        layout.addWidget(self.bounce_grid)

        return page

    def _build_favorites_page(self):
        """Build the full-featured Favorites page with sidebar, grid, and file management."""
        page = QWidget()
        page.setObjectName("FavPage")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Default favorites are now seeded inside PresetLibrary migration
        
        # ═══════════════════════════════════════════════════════════════════════
        # LEFT SIDEBAR
        # ═══════════════════════════════════════════════════════════════════════
        sidebar = QFrame()
        sidebar.setFixedWidth(52)
        sidebar.setObjectName("FavSidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(4, 6, 4, 6)
        sidebar_layout.setSpacing(2)

        # Quick filter buttons (icon-only, 44x44)
        self.sidebar_filter_all = self._create_sidebar_item("≡", "all", True, tooltip="All Presets")
        from reveace_pyside6.app_paths import get_package_dir as _gpd
        _recent_icon = os.path.join(_gpd(), "foldersicon", "icon_recent_sidebar.svg")
        self.sidebar_filter_recent = ModeIconButton(_recent_icon, "Recent", size=44, icon_size=22)
        self.sidebar_filter_recent.setProperty("filter_key", "recent")
        self.sidebar_filter_recent.clicked.connect(lambda: self._on_sidebar_filter_clicked("recent", self.sidebar_filter_recent))
        self.sidebar_filter_uncategorized = self._create_sidebar_item("○", "uncategorized", tooltip="Uncategorized")
        sidebar_layout.addWidget(self.sidebar_filter_all)
        sidebar_layout.addWidget(self.sidebar_filter_recent)
        sidebar_layout.addWidget(self.sidebar_filter_uncategorized)

        # Divider
        _div = QFrame()
        _div.setFrameShape(QFrame.Shape.HLine)
        _div.setFixedHeight(1)
        _div.setStyleSheet(f"background: {get_theme().border_color}; border: none;")
        sidebar_layout.addWidget(_div)
        sidebar_layout.addSpacing(2)

        # Folder list container wrapped in scroll area
        self.sidebar_folders_container = QWidget()
        self.sidebar_folders_layout = QVBoxLayout(self.sidebar_folders_container)
        self.sidebar_folders_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_folders_layout.setSpacing(3)
        self.sidebar_folders_layout.setAlignment(Qt.AlignTop)

        folder_scroll = QScrollArea()
        folder_scroll.setWidgetResizable(True)
        folder_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        folder_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        folder_scroll.setFrameShape(QFrame.Shape.NoFrame)
        folder_scroll.setWidget(self.sidebar_folders_container)
        folder_scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollBar:vertical { width: 4px; }")
        sidebar_layout.addWidget(folder_scroll)

        # New Folder button at bottom
        self.btn_new_folder = QPushButton("+")
        self.btn_new_folder.setFixedSize(44, 32)
        self.btn_new_folder.setToolTip("New Folder")
        self.btn_new_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new_folder.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {get_theme().text_secondary};
                border: 1px solid {get_theme().border_color};
                border-radius: 4px;
                font-weight: bold;
                font-size: 16px;
            }}
            QPushButton:hover {{
                border-color: {get_theme().accent};
                color: {get_theme().accent};
            }}
        """)
        self.btn_new_folder.clicked.connect(self._on_new_folder_clicked)
        sidebar_layout.addWidget(self.btn_new_folder)
        
        # Apply sidebar theme
        self._update_sidebar_theme(sidebar)
        get_theme().add_listener(lambda: self._update_sidebar_theme(sidebar))
        
        layout.addWidget(sidebar)
        
        # ═══════════════════════════════════════════════════════════════════════
        # MAIN CONTENT AREA
        # ═══════════════════════════════════════════════════════════════════════
        main_content = QWidget()
        main_content.setObjectName("FavMainContent")
        main_layout = QVBoxLayout(main_content)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Top Action Bar
        action_bar = QWidget()
        action_bar.setFixedHeight(44)
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        
        # Search bar
        self.fav_search_edit = QLineEdit()
        self.fav_search_edit.setPlaceholderText("Search presets...")
        self.fav_search_edit.setFixedWidth(150)
        self.fav_search_edit.setFixedHeight(32)
        theme = get_theme()
        self.fav_search_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {theme.bg_input};
                color: {theme.text_primary};
                border: 1px solid {theme.border_color};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border-color: {theme.accent};
            }}
        """)
        self.fav_search_edit.textChanged.connect(self._on_fav_search_changed)
        get_theme().add_listener(lambda: self._update_search_style())
        
        # Selection counter (right side)
        self.selection_counter = QLabel("")
        self.selection_counter.setStyleSheet(f"color: {get_theme().accent}; font-size: 10px;")
        self.selection_counter.hide()
        
        from reveace_pyside6.app_paths import get_package_dir
        _ficons = os.path.join(get_package_dir(), "foldersicon")
        # Load button
        self.btn_fav_load = ModeIconButton(os.path.join(_ficons, "icon_load.svg"), "Import presets from file", size=36, icon_size=20)
        self.btn_fav_load.clicked.connect(self._on_fav_load_clicked)

        # Save button (export)
        self.btn_fav_save = ModeIconButton(os.path.join(_ficons, "icon_save_fav.svg"), "Export selected presets", size=36, icon_size=20)
        self.btn_fav_save.clicked.connect(self._on_fav_save_clicked)

        # New Folder button for top bar
        self.btn_fav_new_folder = ModeIconButton(os.path.join(_ficons, "icon_new_folder.svg"), "Create new folder", size=36, icon_size=20)
        self.btn_fav_new_folder.clicked.connect(self._on_new_folder_clicked)

        # Delete button
        self.btn_fav_delete = ModeIconButton(os.path.join(_ficons, "icon_delete.svg"), "Delete selected (Delete key)", size=36, icon_size=20)
        self.btn_fav_delete.clicked.connect(self._on_fav_delete_clicked)
        
        action_layout.addWidget(self.fav_search_edit)
        action_layout.addSpacing(8)
        action_layout.addWidget(self.btn_fav_load)
        action_layout.addWidget(self.btn_fav_save)
        action_layout.addWidget(self.btn_fav_new_folder)
        action_layout.addWidget(self.btn_fav_delete)
        action_layout.addStretch()
        action_layout.addWidget(self.selection_counter)
        
        main_layout.addWidget(action_bar)
        
        # Grid area with scroll - use a container to hold both grid and overlay
        grid_container = QFrame()
        grid_container.setObjectName("FavGridContainer")
        grid_container_layout = QVBoxLayout(grid_container)
        grid_container_layout.setContentsMargins(0, 0, 0, 0)
        grid_container_layout.setSpacing(0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.fav_content_scroll = scroll

        self.fav_grid_widget = QWidget()
        self.fav_grid_widget.setObjectName("FavGridWidget")
        self.fav_grid = QGridLayout(self.fav_grid_widget)
        self.fav_grid.setSpacing(8)
        self.fav_grid.setContentsMargins(4, 4, 4, 4)
        self.fav_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        # Drag selection overlay for favorites (created on demand)
        self._fav_drag_overlay = None
        
        # Enable drag selection
        self.fav_grid_widget.setMouseTracking(True)
        self.fav_grid_widget.installEventFilter(self)
        
        # Drag selection state
        self._drag_select_rect = None
        self._drag_select_start_pos = None
        self._drag_select_modifier = None
        self._drag_select_active = False
        self._drag_select_target = None
        self._drag_select_is_section = False
        self._drag_select_section = None
        self._drag_select_original_selection = set()
        
        # Enable drag selection on scroll area viewport too
        scroll.viewport().setMouseTracking(True)
        scroll.viewport().installEventFilter(self)
        
        scroll.setWidget(self.fav_grid_widget)
        scroll.viewport().installEventFilter(self)
        grid_container_layout.addWidget(scroll)
        main_layout.addWidget(grid_container)
        
        layout.addWidget(main_content)
        
        # Initialize state
        self._fav_current_filter = "all"
        self._fav_current_folder = None
        self._fav_selected_ids = set()
        self._fav_last_selected = None
        self._fav_preset_cards = []  # List to track all preset cards
        self._fav_folder_buttons = {}  # Map folder_id -> button
        self._fav_dragging_preset = None
        self._fav_rename_in_progress = False
        self._fav_search_text = ""  # Current search filter text
        
        # Clipboard for copy/cut/paste
        self._fav_clipboard = None  # {action: 'copy'|'cut', presets: [], source_folder: id}
        
        # Refresh folder list
        self._refresh_sidebar_folders()
        
        return page
    
    def _initialize_default_favorites(self):
        """Initialize default favorites from presets if not already done.
        
        DEPRECATED: Built-in presets are now seeded inside PresetLibrary.
        This method is kept for compatibility but does nothing.
        """
        pass
    
    def _create_sidebar_item(self, text, filter_key, is_active=False, tooltip=""):
        """Create a compact icon-only sidebar filter button."""
        btn = QPushButton(text)
        btn.setFixedSize(44, 44)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("filter_key", filter_key)
        btn.setCheckable(True)
        btn.setChecked(is_active)
        btn.setToolTip(tooltip or text)
        btn.setStyleSheet(self._get_sidebar_item_style(is_active))
        btn.clicked.connect(lambda: self._on_sidebar_filter_clicked(filter_key, btn))
        return btn
    
    def _get_sidebar_item_style(self, is_active):
        theme = get_theme()
        if is_active:
            return f"""
                QPushButton {{
                    background: {theme.accent};
                    color: {theme.black};
                    border: none;
                    border-radius: 6px;
                    font-size: 15px;
                    font-weight: bold;
                }}
            """
        return f"""
            QPushButton {{
                background: transparent;
                color: {theme.text_primary};
                border: none;
                border-radius: 6px;
                font-size: 15px;
            }}
            QPushButton:hover {{
                background: {theme.bg_input};
            }}
        """
    
    def _update_sidebar_theme(self, sidebar):
        theme = get_theme()
        sidebar.setStyleSheet(f"""
            #FavSidebar {{
                background: {theme.bg_card};
                border-right: 1px solid {theme.border_color};
            }}
        """)
    
    def _on_sidebar_filter_clicked(self, filter_key, btn):
        """Handle sidebar filter selection."""
        # Uncheck all filter buttons
        parent = btn.parent()
        for child in parent.findChildren(QPushButton):
            if child.property("filter_key"):
                child.setChecked(False)
                if hasattr(child, 'set_active'):
                    child.set_active(False)
                else:
                    child.setStyleSheet(self._get_sidebar_item_style(False))

        # Check this button
        btn.setChecked(True)
        if hasattr(btn, 'set_active'):
            btn.set_active(True)
        else:
            btn.setStyleSheet(self._get_sidebar_item_style(True))
        
        self._fav_current_filter = filter_key
        self._fav_current_folder = None
        self._clear_fav_selection()
        self._refresh_favorites()
    
    def _refresh_sidebar_folders(self):
        """Refresh the folders list in sidebar - default folders first, then user folders."""
        # Clear existing folder buttons
        while self.sidebar_folders_layout.count():
            item = self.sidebar_folders_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self._fav_folder_buttons.clear()
        
        # Get all folders
        all_folders = self.library.get_all_folders()
        
        # Separate default and user folders
        default_folders = [f for f in all_folders if f.get("is_default")]
        user_folders = [f for f in all_folders if not f.get("is_default")]
        
        # Add default folders first (Easing, Dynamic, Special)
        for i, folder in enumerate(default_folders):
            btn = self._create_folder_button(folder, is_default=True, color_index=i)
            self._fav_folder_buttons[folder["id"]] = btn
            self.sidebar_folders_layout.addWidget(btn)

        # Add separator if there are user folders
        if user_folders and default_folders:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFixedHeight(1)
            sep.setStyleSheet(f"background: {get_theme().border_color}; border: none;")
            self.sidebar_folders_layout.addWidget(sep)

        # Add user folders
        offset = len(default_folders)
        for i, folder in enumerate(user_folders):
            btn = self._create_folder_button(folder, is_default=False, color_index=offset + i)
            self._fav_folder_buttons[folder["id"]] = btn
            self.sidebar_folders_layout.addWidget(btn)
    
    _FOLDER_COLORS = [
        "#C5FD04", "#FF6B6B", "#4ECDC4", "#FFE66D",
        "#A8E6CF", "#FF8B94", "#B4A7D6", "#F4A261",
    ]

    def _set_folder_glow(self, btn, tab_color, active):
        """Apply drop-shadow glow to the icon only (not the box border)."""
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor
        if active:
            fx = QGraphicsDropShadowEffect()
            fx.setBlurRadius(14)
            fx.setOffset(0, 0)
            fx.setColor(QColor(tab_color))
            btn.setGraphicsEffect(fx)
        else:
            btn.setGraphicsEffect(None)

    def _make_folder_icon(self, tab_color, active=False):
        """Render a neo-brutalist folder QIcon with the given tab color."""
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtGui import QPixmap, QPainter, QIcon
        body = "#4a4a4a" if active else "#3a3a3a"
        # Glow baked into SVG filter so only the icon shape glows, not the button box
        glow_filter = ""
        glow_attr = ""
        if active:
            glow_filter = (
                f'<defs>'
                f'<filter id="g" x="-40%" y="-40%" width="180%" height="180%">'
                f'<feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="blur"/>'
                f'<feFlood flood-color="{tab_color}" flood-opacity="0.85" result="color"/>'
                f'<feComposite in="color" in2="blur" operator="in" result="glow"/>'
                f'<feMerge><feMergeNode in="glow"/><feMergeNode in="SourceGraphic"/></feMerge>'
                f'</filter></defs>'
            )
            glow_attr = ' filter="url(#g)"'
        svg = (
            f'<svg width="40" height="34" viewBox="-4 -4 40 34" fill="none" xmlns="http://www.w3.org/2000/svg">'
            f'{glow_filter}'
            f'<g{glow_attr}>'
            f'<rect x="1" y="4" width="13" height="8" rx="3" fill="{tab_color}"/>'
            f'<rect x="1" y="10" width="30" height="15" rx="3" fill="{body}"/>'
            f'</g>'
            f'</svg>'
        )
        renderer = QSvgRenderer(bytearray(svg.encode()))
        px = QPixmap(80, 68)  # 2x for crispness
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(p)
        p.end()
        return QIcon(px)

    def _create_folder_button(self, folder, level=0, is_default=False, color_index=0):
        """Create a compact icon-only folder button for the narrow sidebar."""
        tab_color = self._FOLDER_COLORS[color_index % len(self._FOLDER_COLORS)]
        is_active = self._fav_current_folder == folder["id"]

        btn = QPushButton()
        btn.setFixedSize(44, 44)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(folder["name"])
        btn.setProperty("folder_id", folder["id"])
        btn.setProperty("is_default", is_default)
        btn.setProperty("tab_color", tab_color)
        btn.setCheckable(True)
        btn.setChecked(is_active)
        btn.setIcon(self._make_folder_icon(tab_color, active=is_active))
        btn.setIconSize(QSize(40, 34))
        btn.setStyleSheet(self._get_folder_button_style(is_active))
        btn.clicked.connect(lambda checked, fid=folder["id"]: self._on_folder_clicked(fid, btn))

        btn.setAcceptDrops(True)
        btn.dragEnterEvent = lambda e, b=btn: self._on_folder_drag_enter(e, b)
        btn.dragLeaveEvent = lambda e, b=btn: self._on_folder_drag_leave(e, b)
        btn.dropEvent = lambda e, fid=folder["id"]: self._on_folder_drop(e, fid)

        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda pos, b=btn, f=folder: self._on_folder_context_menu(b, f))

        return btn
    
    def _on_folder_context_menu(self, btn, folder):
        """Show context menu for a folder button."""
        from PySide6.QtWidgets import QMenu, QMessageBox
        
        menu = QMenu(self)
        is_default = folder.get("is_default", False)
        
        action_rename = menu.addAction("Rename")
        action_rename.triggered.connect(lambda: self._start_folder_rename(folder["id"], btn))
        
        if not is_default:
            menu.addSeparator()
            action_delete = menu.addAction("Delete")
            action_delete.triggered.connect(lambda: self._on_folder_delete(folder["id"]))
        
        menu.exec(btn.mapToGlobal(btn.rect().center()))
    
    def _on_folder_delete(self, folder_id):
        """Delete a folder after confirmation."""
        from PySide6.QtWidgets import QMessageBox
        
        folder = self.library.get_folder(folder_id)
        if not folder:
            return
        
        # Don't allow deleting default folders
        if folder.get("is_default", False):
            self.status_lbl.setText("Cannot delete default folders")
            return
        
        reply = QMessageBox.question(
            self,
            "Delete Folder",
            f"Delete folder '{folder['name']}'?\n\nPresets inside will become uncategorized.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # If currently viewing this folder, switch to "all"
            if self._fav_current_folder == folder_id:
                self._fav_current_folder = None
                self._fav_current_filter = "all"
            
            self.library.delete_folder(folder_id)
            self._refresh_sidebar_folders()
            self._refresh_favorites()
            self.status_lbl.setText(f"Deleted folder '{folder['name']}'")
    
    def _get_folder_button_style(self, is_active, level=0, is_default=False):
        theme = get_theme()
        bg = theme.bg_input if is_active else "transparent"
        return f"""
            QPushButton {{
                background: {bg};
                border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background: {theme.bg_input};
            }}
        """

    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(6)
        inner_layout.setContentsMargins(4, 4, 4, 4)

        # === DESIGN STYLE (consolidated) ===
        design_sec = SectionCard("DESIGN STYLE", expanded=True)
        
        # Style dropdown
        style_row = QHBoxLayout()
        style_row.addWidget(label("Style:", muted=True))
        self.style_combo = make_combo(["Brutalist", "Minimal"])
        self.style_combo.currentTextChanged.connect(self._on_style_changed)
        style_row.addWidget(self.style_combo)
        design_sec.add_layout(style_row)
        
        # Roundness slider (max 10 for all styles)
        self.roundness_slider = SimpleSlider("Border Radius:", 0, 10, get_theme().border_radius, 1, no_scroll=True)
        self.roundness_slider.valueChanged = lambda v: get_theme().set_border_radius(int(v))
        design_sec.add(self.roundness_slider)
        
        # Border width slider
        self.border_slider = SimpleSlider("Border Width:", 0, 6, get_theme().border_width, 1, no_scroll=True)
        self.border_slider.valueChanged = lambda v: setattr(get_theme(), 'border_width', int(v)) or get_theme().notify_change()
        design_sec.add(self.border_slider)

        # Highlight border width slider
        self.highlight_border_slider = SimpleSlider("Highlight Width:", 0, 6, get_theme().highlight_border_width, 1, no_scroll=True)
        def _on_highlight_border_changed(v):
            get_theme().highlight_border_width = int(v)
            get_theme()._save_settings()
            get_theme().notify_change()
        self.highlight_border_slider.valueChanged = _on_highlight_border_changed
        design_sec.add(self.highlight_border_slider)

        # Hardware acceleration toggle
        self.hw_accel_check = StyledCheckBox("Hardware Acceleration (restart required)")
        self.hw_accel_check.blockSignals(True)
        self.hw_accel_check.setChecked(get_theme().hardware_acceleration)
        self.hw_accel_check.blockSignals(False)
        def _on_hw_accel_changed(state):
            val = bool(state) if isinstance(state, int) else (state == Qt.CheckState.Checked)
            get_theme().hardware_acceleration = val
            get_theme()._save_settings()
        self.hw_accel_check.stateChanged.connect(_on_hw_accel_changed)
        design_sec.add(self.hw_accel_check)

        inner_layout.addWidget(design_sec)

        # === THEME COLORS ===
        color_sec = SectionCard("THEME COLORS", expanded=True)
        
        # Color grid with actual colors
        color_grid = QGridLayout()
        color_grid.setSpacing(8)
        
        themes = {
            "Lime": "#C5FD04",
            "Cyan": "#00D9FF",
            "Purple": "#B829DD",
            "Orange": "#FF6B35",
            "Blue": "#3B82F6",
            "Pink": "#FF0080",
            "Red": "#FF3333",
        }
        
        for i, (name, color) in enumerate(themes.items()):
            btn = ThemeColorButton(name, color)
            btn.clicked.connect(lambda checked, n=name: get_theme().set_theme(n))
            color_grid.addWidget(btn, i // 4, i % 4)
        
        # Custom color button
        custom_btn = QPushButton("+")
        custom_btn.setFixedSize(32, 32)
        custom_btn.setToolTip("Custom Color")
        custom_btn.clicked.connect(self._on_custom_color)
        color_grid.addWidget(custom_btn, len(themes) // 4, len(themes) % 4)
        
        color_sec.add_layout(color_grid)
        
        # Dark mode
        self.dark_mode_check = StyledCheckBox("Dark Mode")
        # Block signals during initialization
        self.dark_mode_check.blockSignals(True)
        self.dark_mode_check.setChecked(get_theme().dark_mode)
        self.dark_mode_check.blockSignals(False)
        
        def _on_dark_mode_changed(state):
            is_checked = bool(state) if isinstance(state, int) else (state == Qt.CheckState.Checked)
            get_theme().set_dark_mode(is_checked)
        self.dark_mode_check.stateChanged.connect(_on_dark_mode_changed)
        
        # Keep checkbox in sync with theme
        def _update_dark_mode_checkbox():
            self.dark_mode_check.blockSignals(True)
            self.dark_mode_check.setChecked(get_theme().dark_mode)
            self.dark_mode_check.blockSignals(False)
        get_theme().add_listener(_update_dark_mode_checkbox)
        
        color_sec.add(self.dark_mode_check)
        
        inner_layout.addWidget(color_sec)

        # === AUTO APPLY ===
        app_sec = SectionCard("AUTO APPLY", expanded=True)
        
        self.auto_apply_master = StyledCheckBox("Enable auto-apply")
        self.auto_apply_master.setChecked(self.auto_apply)
        self.auto_apply_master.toggled.connect(lambda checked: setattr(self, 'auto_apply', checked))
        app_sec.add(self.auto_apply_master)
        
        self.auto_apply_release_chk = StyledCheckBox("Apply on release only (recommended)")
        self.auto_apply_release_chk.setChecked(self.auto_apply_release)
        self.auto_apply_release_chk.toggled.connect(lambda checked: setattr(self, 'auto_apply_release', checked))
        app_sec.add(self.auto_apply_release_chk)
        
        self.auto_apply_card_chk = StyledCheckBox("Apply on preset card click")
        self.auto_apply_card_chk.setChecked(self.auto_apply_card)
        self.auto_apply_card_chk.toggled.connect(lambda checked: setattr(self, 'auto_apply_card', checked))
        app_sec.add(self.auto_apply_card_chk)
        
        # Per-page toggles
        page_row = QHBoxLayout()
        self.auto_apply_bezier_chk = StyledCheckBox("Bezier")
        self.auto_apply_bezier_chk.setChecked(self.auto_apply_bezier)
        self.auto_apply_bezier_chk.toggled.connect(lambda checked: setattr(self, 'auto_apply_bezier', checked))
        page_row.addWidget(self.auto_apply_bezier_chk)
        
        self.auto_apply_elastic_chk = StyledCheckBox("Elastic")
        self.auto_apply_elastic_chk.setChecked(self.auto_apply_elastic)
        self.auto_apply_elastic_chk.toggled.connect(lambda checked: setattr(self, 'auto_apply_elastic', checked))
        page_row.addWidget(self.auto_apply_elastic_chk)
        
        self.auto_apply_bounce_chk = StyledCheckBox("Bounce")
        self.auto_apply_bounce_chk.setChecked(self.auto_apply_bounce)
        self.auto_apply_bounce_chk.toggled.connect(lambda checked: setattr(self, 'auto_apply_bounce', checked))
        page_row.addWidget(self.auto_apply_bounce_chk)
        page_row.addStretch()
        app_sec.add_layout(page_row)
        
        inner_layout.addWidget(app_sec)
        
        # === DAVINCI RESOLVE ===
        resolve_sec = SectionCard("DAVINCI RESOLVE", expanded=True)
        
        # Current path display
        path_row = QHBoxLayout()
        path_row.addWidget(label("Install Path:", muted=True))
        
        self.resolve_path_edit = QLineEdit()
        self.resolve_path_edit.setText(self._get_resolve_path())
        self.resolve_path_edit.setReadOnly(True)
        self.resolve_path_edit.setStyleSheet(f"""
            QLineEdit {{
                color: {get_theme().text_primary};
                background: {get_theme().bg_input};
                border: 1px solid {get_theme().border_color};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }}
        """)
        path_row.addWidget(self.resolve_path_edit, 1)
        
        # Browse button
        browse_btn = QPushButton("BROWSE...")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {get_theme().text_secondary};
                border: none;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: {get_theme().text_primary};
            }}
        """)
        browse_btn.setFixedHeight(36)
        browse_btn.clicked.connect(self._on_browse_resolve_path)
        path_row.addWidget(browse_btn)

        resolve_sec.add_layout(path_row)

        # Connection status and test
        status_row = QHBoxLayout()
        self.resolve_status_lbl = label("Status: Unknown", muted=True)
        status_row.addWidget(self.resolve_status_lbl)
        status_row.addStretch()

        test_btn = BrutalButton("Test Connection", variant="accent")
        test_btn.setFixedHeight(36)
        test_btn.setMinimumWidth(140)
        test_btn.clicked.connect(self._on_test_resolve_connection)
        status_row.addWidget(test_btn)
        
        resolve_sec.add_layout(status_row)
        
        # Help text with examples
        help_lbl = label(r"Example: C:\Program Files\Blackmagic Design\DaVinci Resolve", muted=True)
        help_lbl.setStyleSheet(f"color: {get_theme().text_secondary}; font-size: 9px;")
        resolve_sec.add(help_lbl)
        
        # Hint about what file to look for
        hint_lbl = label("(This folder should contain fusionscript.dll)", muted=True)
        hint_lbl.setStyleSheet(f"color: {get_theme().text_secondary}; font-size: 8px; font-style: italic;")
        resolve_sec.add(hint_lbl)
        
        inner_layout.addWidget(resolve_sec)
        inner_layout.addStretch()
        
        scroll.setWidget(inner)
        layout.addWidget(scroll)
        
        # Sync UI with current theme settings after building
        self._sync_settings_ui_with_theme()
        
        return page
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # SECTION PRESET MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════════
    
    def _on_add_preset_clicked(self, section_name):
        """Handle click on 'Add Preset' box - show appropriate selection modal"""
        self._pending_add_section = section_name
        
        if section_name in ["Easing", "Dynamic", "Special"]:
            # Bezier sections - show favorites modal
            self._show_favorites_selection_modal(section_name)
        elif section_name == "Elastic":
            # Elastic section - show filtered preset picker
            self._show_preset_picker_modal(section_name, filter_category="Elastic")
        elif section_name == "Bounce":
            # Bounce section - show filtered preset picker
            self._show_preset_picker_modal(section_name, filter_category="Bounce")
    
    def _show_favorites_selection_modal(self, section_name):
        """Show modal dialog with full favorites interface (filters, folders, grid)"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Add Preset to {section_name}")
        dialog.setMinimumSize(500, 450)
        theme = get_theme()
        dialog.setStyleSheet(f"""
            QDialog {{ background-color: {theme.bg_outer}; }}
            QLabel {{ color: {theme.text_primary}; }}
        """)
        
        # Main layout - sidebar + content
        main_layout = QHBoxLayout(dialog)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # ═════════════════════════════════════════════════════════════════
        # LEFT SIDEBAR
        # ═════════════════════════════════════════════════════════════════
        sidebar = QFrame()
        sidebar.setFixedWidth(160)
        sidebar.setStyleSheet(f"background: {theme.bg_card}; border-right: 1px solid {theme.border_color};")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(8, 12, 8, 12)
        sidebar_layout.setSpacing(6)
        
        # Sidebar title
        sidebar_title = QLabel("FILTERS")
        sidebar_title.setStyleSheet(f"color: {theme.accent}; font-size: 10px; font-weight: bold;")
        sidebar_layout.addWidget(sidebar_title)
        
        # Track selected filter and folder
        self._modal_filter = "all"
        self._modal_folder = None
        self._modal_selected_presets = []  # List for multi-selection
        self._modal_last_selected_idx = None
        self._modal_all_cards = []  # Track all cards for multi-select
        
        # Filter buttons
        def create_filter_btn(text, filter_key, is_active=False):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setChecked(is_active)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if is_active:
                btn.setStyleSheet(f"""
                    QPushButton {{ background: {theme.accent}; color: {theme.black}; 
                        border: none; border-radius: 6px; padding: 8px; text-align: left;
                        font-size: 11px; font-weight: bold; }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {theme.text_primary}; 
                        border: none; border-radius: 6px; padding: 8px; text-align: left;
                        font-size: 11px; }}
                    QPushButton:hover {{ background: {theme.bg_input}; }}
                """)
            return btn
        
        btn_all = create_filter_btn("All Presets", "all", True)
        btn_recent = create_filter_btn("Recent", "recent")
        btn_uncat = create_filter_btn("Uncategorized", "uncategorized")
        
        sidebar_layout.addWidget(btn_all)
        sidebar_layout.addWidget(btn_recent)
        sidebar_layout.addWidget(btn_uncat)
        
        # Folders section
        sidebar_layout.addSpacing(16)
        folders_title = QLabel("MY FOLDERS")
        folders_title.setStyleSheet(f"color: {theme.text_secondary}; font-size: 10px;")
        sidebar_layout.addWidget(folders_title)
        
        # Folder buttons
        self._modal_folder_buttons = {}
        for folder in self.library.get_all_folders():
            is_default = folder.get("is_default", False)
            icon = "📂" if is_default else "📁"
            btn = QPushButton(f"{icon} {folder['name']}")
            btn.setProperty("folder_id", folder["id"])
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {theme.text_primary if not is_default else theme.accent}; 
                    border: {'1px solid ' + theme.border_color if is_default else 'none'}; 
                    border-radius: 6px; padding: 8px; text-align: left; font-size: 11px;
                    {'font-weight: bold;' if is_default else ''} }}
                QPushButton:hover {{ background: {theme.bg_input}; }}
            """)
            sidebar_layout.addWidget(btn)
            self._modal_folder_buttons[folder["id"]] = btn
        
        sidebar_layout.addStretch()
        main_layout.addWidget(sidebar)
        
        # ═════════════════════════════════════════════════════════════════
        # RIGHT CONTENT AREA
        # ═════════════════════════════════════════════════════════════════
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(10)
        
        # Title
        title = QLabel(f"Select preset to add to {section_name}")
        title.setStyleSheet(f"color: {theme.accent}; font-size: 13px; font-weight: bold;")
        content_layout.addWidget(title)
        
        # Grid area with drag selection support
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(8)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(grid_widget)
        content_layout.addWidget(scroll)
        
        # Enable drag selection for modal
        grid_widget.setMouseTracking(True)
        grid_widget.installEventFilter(self)
        scroll.viewport().setMouseTracking(True)
        scroll.viewport().installEventFilter(self)
        grid_widget._is_modal_grid = True
        self._modal_grid_widget = grid_widget
        
        # Status label
        self._modal_status_lbl = QLabel("Select preset(s)...")
        self._modal_status_lbl.setStyleSheet(f"color: {theme.text_secondary}; font-size: 10px;")
        content_layout.addWidget(self._modal_status_lbl)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self._modal_btn_add = BrutalButton("ADD PRESET(S)", variant="accent")
        self._modal_btn_add.setFixedHeight(36)
        self._modal_btn_add.setEnabled(False)
        
        btn_cancel = BrutalButton("CANCEL", variant="dark")
        btn_cancel.setFixedHeight(36)
        btn_cancel.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self._modal_btn_add)
        content_layout.addLayout(btn_layout)
        
        main_layout.addWidget(content)
        
        # ═════════════════════════════════════════════════════════════════
        # FUNCTIONS TO POPULATE GRID
        # ═════════════════════════════════════════════════════════════════
        def refresh_grid():
            """Refresh the preset grid based on current filter/folder"""
            # Clear grid
            while grid.count():
                item = grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            current_presets = set(self.library.get_preset_names_by_section(section_name))
            favorites = self.library.get_all()
            available = []
            
            # Filter based on selection
            for fav in favorites:
                preset_id = fav.get("id")
                fav_name = fav.get("name", "Unnamed")
                
                # Skip if already in this section
                if section_name in fav.get("sections", []):
                    continue
                
                # Check folder assignment
                folder_id = self.library.get_folder_for_preset(preset_id)
                
                if self._modal_folder:
                    # Show only presets in selected folder
                    if folder_id == self._modal_folder:
                        available.append((fav, preset_id))
                elif self._modal_filter == "uncategorized":
                    # Show only uncategorized presets
                    if folder_id is None:
                        available.append((fav, preset_id))
                elif self._modal_filter == "recent":
                    # Show last 10 added
                    available.append((fav, preset_id))
                else:  # "all"
                    available.append((fav, preset_id))
            
            # Sort by index for "recent" filter (newest first)
            if self._modal_filter == "recent":
                available = available[-10:]
                available.reverse()
            
            # Build cards
            self._modal_all_cards = []
            if not available:
                msg = QLabel("No presets available\nTry a different filter or folder")
                msg.setStyleSheet(f"color: {theme.text_secondary}; font-size: 12px;")
                msg.setAlignment(Qt.AlignCenter)
                grid.addWidget(msg, 0, 0)
            else:
                for i, (fav, preset_id) in enumerate(available):
                    card = self._build_modal_preset_card(fav, preset_id, i, dialog, self._modal_btn_add, self._modal_status_lbl, available)
                    self._modal_all_cards.append((card, fav, preset_id))
                    grid.addWidget(card, i // 4, i % 4)
            
            # Force update of scroll area to ensure curves are rendered
            grid_widget.update()
            scroll.viewport().update()
            
            # Update status
            self._modal_status_lbl.setText(f"{len(available)} presets available")
        
        # Connect filter buttons
        def on_filter_clicked(filter_key, btn):
            self._modal_filter = filter_key
            self._modal_folder = None
            # Update styles
            for b in [btn_all, btn_recent, btn_uncat]:
                b.setChecked(False)
                b.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {theme.text_primary}; 
                        border: none; border-radius: 6px; padding: 8px; text-align: left;
                        font-size: 11px; }}
                    QPushButton:hover {{ background: {theme.bg_input}; }}
                """)
            btn.setChecked(True)
            btn.setStyleSheet(f"""
                QPushButton {{ background: {theme.accent}; color: {theme.black}; 
                    border: none; border-radius: 6px; padding: 8px; text-align: left;
                    font-size: 11px; font-weight: bold; }}
            """)
            # Clear folder selection
            for fid, b in self._modal_folder_buttons.items():
                b.setChecked(False)
                is_def = self.library.get_folder(fid)
                b.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {theme.text_primary if not is_def else theme.accent}; 
                        border: {'1px solid ' + theme.border_color if is_def else 'none'}; 
                        border-radius: 6px; padding: 8px; text-align: left; font-size: 11px;
                        {'font-weight: bold;' if is_def else ''} }}
                    QPushButton:hover {{ background: {theme.bg_input}; }}
                """)
            refresh_grid()
        
        def on_folder_clicked(folder_id, btn):
            self._modal_folder = folder_id
            self._modal_filter = None
            # Update styles
            for b in [btn_all, btn_recent, btn_uncat]:
                b.setChecked(False)
                b.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {theme.text_primary}; 
                        border: none; border-radius: 6px; padding: 8px; text-align: left;
                        font-size: 11px; }}
                    QPushButton:hover {{ background: {theme.bg_input}; }}
                """)
            for fid, b in self._modal_folder_buttons.items():
                b.setChecked(False)
                is_def = self.library.get_folder(fid)
                b.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {theme.text_primary if not is_def else theme.accent}; 
                        border: {'1px solid ' + theme.border_color if is_def else 'none'}; 
                        border-radius: 6px; padding: 8px; text-align: left; font-size: 11px;
                        {'font-weight: bold;' if is_def else ''} }}
                    QPushButton:hover {{ background: {theme.bg_input}; }}
                """)
            btn.setChecked(True)
            btn.setStyleSheet(f"""
                QPushButton {{ background: {theme.accent}; color: {theme.black}; 
                    border: none; border-radius: 6px; padding: 8px; text-align: left;
                    font-size: 11px; font-weight: bold; }}
            """)
            refresh_grid()
        
        btn_all.clicked.connect(lambda: on_filter_clicked("all", btn_all))
        btn_recent.clicked.connect(lambda: on_filter_clicked("recent", btn_recent))
        btn_uncat.clicked.connect(lambda: on_filter_clicked("uncategorized", btn_uncat))
        
        for folder_id, btn in self._modal_folder_buttons.items():
            btn.clicked.connect(lambda checked, fid=folder_id, b=btn: on_folder_clicked(fid, b))
        
        # Connect add button
        def on_add_clicked():
            if self._modal_selected_presets:
                added = 0
                for fav in self._modal_selected_presets:
                    preset_id = fav.get("id")
                    if preset_id and self.library.add_section(preset_id, section_name):
                        added += 1
                
                if added > 0:
                    self._refresh_section_grid(section_name)
                    self.status_lbl.setText(f"Added {added} preset(s) to {section_name}")
                else:
                    self.status_lbl.setText("No presets added (may already exist)")
                
                dialog.accept()
        
        self._modal_btn_add.clicked.connect(on_add_clicked)
        
        # Initial load
        refresh_grid()
        
        # Force repaint of all curve widgets after dialog is shown
        def force_repaint():
            for widget in grid_widget.findChildren(QWidget):
                widget.update()
        
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, force_repaint)
        
        dialog.exec()
    
    def _build_modal_preset_card(self, fav, preset_id, display_idx, dialog, btn_add, status_lbl, all_available):
        """Build a preset card for the modal dialog with multi-selection support"""
        from PySide6.QtWidgets import QApplication
        
        theme = get_theme()
        card = QFrame()
        card.setFixedHeight(85)
        card.setMinimumWidth(80)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setObjectName("FavCard")
        card._is_selected = False
        card._fav = fav
        card._preset_id = preset_id
        card._display_idx = display_idx
        
        vlay = QVBoxLayout(card)
        vlay.setContentsMargins(4, 4, 4, 4)
        vlay.setSpacing(2)
        vlay.setAlignment(Qt.AlignCenter)
        
        # Get preview points using unified method (same as favorites page)
        points = self._get_preset_preview_points(fav)
        mini = MiniCurveWidget(points)
        mini.setFixedSize(70, 40)
        mini.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        
        name_lbl = QLabel(fav.get("name", "Unnamed")[:14])
        name_lbl.setStyleSheet(f"color: {theme.text_primary}; font-size: 9px;")
        name_lbl.setAlignment(Qt.AlignCenter)
        
        vlay.addWidget(mini)
        vlay.addWidget(name_lbl)
        
        def update_style():
            if card._is_selected:
                card.setStyleSheet(f"""
                    #FavCard {{ background: {theme.bg_card}; border: 3px solid #4CAF50; 
                        border-radius: {theme.border_radius}px; }}
                """)
            else:
                card.setStyleSheet(f"""
                    #FavCard {{ background: {theme.bg_card}; border: {theme.border_width}px solid {theme.border_color}; 
                        border-radius: {theme.border_radius}px; }}
                    #FavCard:hover {{ border-color: {theme.accent}; }}
                """)
        
        update_style()
        
        def on_click(event=None):
            modifiers = QApplication.keyboardModifiers() if event else Qt.NoModifier
            ctrl_pressed = modifiers & Qt.ControlModifier
            shift_pressed = modifiers & Qt.ShiftModifier
            
            if ctrl_pressed:
                # Ctrl+Click: Toggle selection
                card._is_selected = not card._is_selected
                if card._is_selected:
                    if fav not in self._modal_selected_presets:
                        self._modal_selected_presets.append(fav)
                    self._modal_last_selected_idx = display_idx
                else:
                    if fav in self._modal_selected_presets:
                        self._modal_selected_presets.remove(fav)
                
            elif shift_pressed and self._modal_last_selected_idx is not None:
                # Shift+Click: Range selection
                start_idx = min(self._modal_last_selected_idx, display_idx)
                end_idx = max(self._modal_last_selected_idx, display_idx)
                
                # Select range
                for c, f, p in self._modal_all_cards:
                    if start_idx <= c._display_idx <= end_idx:
                        c._is_selected = True
                        if f not in self._modal_selected_presets:
                            self._modal_selected_presets.append(f)
                        c.setStyleSheet(f"""
                            #FavCard {{ background: {theme.bg_card}; border: 3px solid #4CAF50; 
                                border-radius: {theme.border_radius}px; }}
                        """)
                
            else:
                # Normal click: Single selection (clear others)
                self._modal_selected_presets.clear()
                for c, f, p in self._modal_all_cards:
                    c._is_selected = False
                    c.setStyleSheet(f"""
                        #FavCard {{ background: {theme.bg_card}; border: {theme.border_width}px solid {theme.border_color}; 
                            border-radius: {theme.border_radius}px; }}
                        #FavCard:hover {{ border-color: {theme.accent}; }}
                    """)
                
                card._is_selected = True
                self._modal_selected_presets.append(fav)
                self._modal_last_selected_idx = display_idx
            
            update_style()
            
            # Update button and status
            count = len(self._modal_selected_presets)
            self._modal_btn_add.setEnabled(count > 0)
            if count == 1:
                self._modal_status_lbl.setText(f"Selected: {self._modal_selected_presets[0].get('name', 'Unnamed')}")
            elif count > 1:
                self._modal_status_lbl.setText(f"Selected: {count} presets")
            else:
                self._modal_status_lbl.setText("Select preset(s)...")
        
        card._modal_click_handler = on_click
        card.mousePressEvent = lambda e: on_click(e)
        return card
    
    def _show_preset_picker_modal(self, section_name, filter_category):
        """Show modal dialog to pick from available PRESETS filtered by category (Elastic/Bounce)"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Add {filter_category} Preset to {section_name}")
        dialog.setMinimumSize(480, 400)
        theme = get_theme()
        dialog.setStyleSheet(f"""
            QDialog {{ background-color: {theme.bg_outer}; }}
            QLabel {{ color: {theme.text_primary}; }}
        """)
        
        # Main layout
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Title
        title = QLabel(f"Select {filter_category} preset(s) to add to {section_name}")
        title.setStyleSheet(f"color: {theme.accent}; font-size: 13px; font-weight: bold;")
        layout.addWidget(title)
        
        # Grid area with drag selection support
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(8)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(grid_widget)
        layout.addWidget(scroll)
        
        # Track selected presets
        self._modal_selected_presets = []
        self._modal_all_cards = []
        
        # Enable drag selection
        grid_widget.setMouseTracking(True)
        grid_widget.installEventFilter(self)
        scroll.viewport().setMouseTracking(True)
        scroll.viewport().installEventFilter(self)
        grid_widget._is_modal_grid = True
        self._modal_grid_widget = grid_widget
        
        # Get current presets in section (to filter out)
        current_presets = set(self.library.get_preset_names_by_section(section_name))
        
        # Get available presets filtered by category and not already in section
        available = []
        for preset_name, preset_data in PRESETS.items():
            preset_cat = preset_data.get("cat", "")
            if preset_cat == filter_category and preset_name not in current_presets:
                available.append(preset_name)
        
        # Sort alphabetically
        available.sort()
        
        # Build cards
        if not available:
            msg = QLabel(f"No {filter_category} presets available\nAll presets already in {section_name}")
            msg.setStyleSheet(f"color: {theme.text_secondary}; font-size: 12px;")
            msg.setAlignment(Qt.AlignCenter)
            grid.addWidget(msg, 0, 0)
        else:
            for i, preset_name in enumerate(available):
                card = self._build_preset_picker_card(preset_name, i, dialog)
                self._modal_all_cards.append((card, preset_name))
                grid.addWidget(card, i // 4, i % 4)
        
        # Status label
        self._modal_status_lbl = QLabel(f"{len(available)} presets available")
        self._modal_status_lbl.setStyleSheet(f"color: {theme.text_secondary}; font-size: 10px;")
        layout.addWidget(self._modal_status_lbl)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self._modal_btn_add = BrutalButton("ADD PRESET(S)", variant="accent")
        self._modal_btn_add.setFixedHeight(36)
        self._modal_btn_add.setEnabled(False)
        
        btn_cancel = BrutalButton("CANCEL", variant="dark")
        btn_cancel.setFixedHeight(36)
        btn_cancel.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self._modal_btn_add)
        layout.addLayout(btn_layout)
        
        # Connect add button
        def on_add_clicked():
            if self._modal_selected_presets:
                added = 0
                for preset_name in self._modal_selected_presets:
                    if self._section_presets_add_preset_compat(section_name, preset_name):
                        added += 1
                
                if added > 0:
                    self._refresh_section_grid(section_name)
                    self.status_lbl.setText(f"Added {added} preset(s) to {section_name}")
                else:
                    self.status_lbl.setText("No presets added (may already exist)")
                
                dialog.accept()
        
        self._modal_btn_add.clicked.connect(on_add_clicked)
        
        # Force repaint after dialog is shown
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, grid_widget.update)
        
        dialog.exec()
    
    def _build_preset_picker_card(self, preset_name, display_idx, dialog):
        """Build a preset card for the preset picker modal"""
        from PySide6.QtWidgets import QApplication
        
        theme = get_theme()
        card = QFrame()
        card.setFixedSize(100, 85)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card._is_selected = False
        card._preset_name = preset_name
        card._display_idx = display_idx
        
        vlay = QVBoxLayout(card)
        vlay.setContentsMargins(4, 4, 4, 4)
        vlay.setSpacing(2)
        vlay.setAlignment(Qt.AlignCenter)
        
        # Get preview points from core
        points = self.core.get_preset_curve_points(preset_name)
        mini = MiniCurveWidget(points)
        mini.setFixedSize(70, 40)
        mini.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        mini.show()
        
        name_lbl = QLabel(preset_name[:14])
        name_lbl.setStyleSheet(f"color: {theme.text_primary}; font-size: 9px;")
        name_lbl.setAlignment(Qt.AlignCenter)
        
        vlay.addWidget(mini)
        vlay.addWidget(name_lbl)
        
        def update_style():
            if card._is_selected:
                card.setStyleSheet(f"""
                    QFrame {{ background: {theme.bg_card}; border: 3px solid #4CAF50; 
                        border-radius: {theme.border_radius}px; }}
                """)
            else:
                card.setStyleSheet(f"""
                    QFrame {{ background: {theme.bg_card}; border: {theme.border_width}px solid {theme.border_color}; 
                        border-radius: {theme.border_radius}px; }}
                    QFrame:hover {{ border-color: {theme.accent}; }}
                """)
        
        update_style()
        
        def on_click(event=None):
            modifiers = QApplication.keyboardModifiers() if event else Qt.NoModifier
            ctrl_pressed = modifiers & Qt.ControlModifier
            shift_pressed = modifiers & Qt.ShiftModifier
            
            if ctrl_pressed:
                # Ctrl+Click: Toggle selection
                card._is_selected = not card._is_selected
                if card._is_selected:
                    if preset_name not in self._modal_selected_presets:
                        self._modal_selected_presets.append(preset_name)
                    self._modal_last_selected_idx = display_idx
                else:
                    if preset_name in self._modal_selected_presets:
                        self._modal_selected_presets.remove(preset_name)
                
            elif shift_pressed and hasattr(self, '_modal_last_selected_idx') and self._modal_last_selected_idx is not None:
                # Shift+Click: Range selection
                start_idx = min(self._modal_last_selected_idx, display_idx)
                end_idx = max(self._modal_last_selected_idx, display_idx)
                
                # Select range
                for c, p in self._modal_all_cards:
                    if start_idx <= c._display_idx <= end_idx:
                        c._is_selected = True
                        if p not in self._modal_selected_presets:
                            self._modal_selected_presets.append(p)
                        c.setStyleSheet(f"""
                            QFrame {{ background: {theme.bg_card}; border: 3px solid #4CAF50; 
                                border-radius: {theme.border_radius}px; }}
                        """)
                
            else:
                # Normal click: Single selection (clear others)
                self._modal_selected_presets.clear()
                for c, p in self._modal_all_cards:
                    c._is_selected = False
                    c.setStyleSheet(f"""
                        QFrame {{ background: {theme.bg_card}; border: {theme.border_width}px solid {theme.border_color}; 
                            border-radius: {theme.border_radius}px; }}
                        QFrame:hover {{ border-color: {theme.accent}; }}
                    """)
                
                card._is_selected = True
                self._modal_selected_presets.append(preset_name)
                self._modal_last_selected_idx = display_idx
            
            update_style()
            
            # Update button and status
            count = len(self._modal_selected_presets)
            self._modal_btn_add.setEnabled(count > 0)
            if count == 1:
                self._modal_status_lbl.setText(f"Selected: {self._modal_selected_presets[0]}")
            elif count > 1:
                self._modal_status_lbl.setText(f"Selected: {count} presets")
            else:
                self._modal_status_lbl.setText("Select preset(s)...")
        
        card._modal_click_handler = on_click
        card.mousePressEvent = lambda e: on_click(e)
        return card
    
    def _refresh_section_grid(self, section_name):
        """Refresh the preset grid for a section (Easing/Dynamic/Special/Elastic/Bounce)"""
        # Get preset IDs from library
        if section_name in ["Easing", "Dynamic", "Special"]:
            presets = [p["id"] for p in self.library.get_by_section(section_name, mode="bezier")]
        elif section_name == "Elastic":
            presets = [p["id"] for p in self.library.get_by_mode("elastic")]
        elif section_name == "Bounce":
            presets = [p["id"] for p in self.library.get_by_mode("bounce")]
        else:
            presets = []
        
        # Build new grid
        new_grid = self._build_preset_grid(presets, section_name)
        
        if section_name in ["Easing", "Dynamic", "Special"]:
            # These are in the bezier_stack
            section_idx = {"Easing": 0, "Dynamic": 1, "Special": 2}.get(section_name, 0)
            
            # Replace in stack
            old_widget = self.bezier_stack.widget(section_idx)
            self.bezier_stack.removeWidget(old_widget)
            old_widget.deleteLater()
            self.bezier_stack.insertWidget(section_idx, new_grid)
            
            # Update reference
            if section_name == "Easing":
                self.easing_grid = new_grid
            elif section_name == "Dynamic":
                self.dynamic_grid = new_grid
            elif section_name == "Special":
                self.special_grid = new_grid
            
            # Keep current index
            self.bezier_stack.setCurrentIndex(self._current_heading_idx)
            
        elif section_name == "Elastic":
            # Elastic page has a simple layout: hint + grid
            old_grid = self.elastic_grid
            if old_grid:
                self.page_elastic.layout().removeWidget(old_grid)
                old_grid.deleteLater()
            self.page_elastic.layout().addWidget(new_grid)
            self.elastic_grid = new_grid
            
        elif section_name == "Bounce":
            # Bounce page has a simple layout: hint + grid
            old_grid = self.bounce_grid
            if old_grid:
                self.page_bounce.layout().removeWidget(old_grid)
                old_grid.deleteLater()
            self.page_bounce.layout().addWidget(new_grid)
            self.bounce_grid = new_grid
    
    def _delete_selected_presets(self, section_name):
        """Remove selected presets from a section (untag, not delete from library)."""
        if not hasattr(self, '_section_preset_cards'):
            return
        
        selected_ids = []
        for card in self._section_preset_cards.get(section_name, []):
            if getattr(card, '_selected', False) and getattr(card, '_preset_id', None):
                selected_ids.append(card._preset_id)
        
        if selected_ids:
            for preset_id in selected_ids:
                self.library.remove_section(preset_id, section_name)
            self._refresh_section_grid(section_name)
            self.status_lbl.setText(f"Removed {len(selected_ids)} presets from {section_name}")
    
    def _sync_settings_ui_with_theme(self):
        """Sync all settings UI controls with current theme values"""
        t = get_theme()
        
        # Sync style dropdown (handle legacy styles by mapping to Minimal)
        style_map = {
            t.STYLE_BRUTALIST: "Brutalist",
            t.STYLE_MINIMAL: "Minimal",
            "rounded": "Minimal",  # Legacy style mapping
            "bw": "Minimal",       # Legacy style mapping
        }
        current_style = style_map.get(t.design_style, "Brutalist")
        self.style_combo.blockSignals(True)
        self.style_combo.setCurrentText(current_style)
        self.style_combo.blockSignals(False)
        
        # Sync sliders
        self.roundness_slider.blockSignals(True)
        self.roundness_slider.setValue(t.border_radius)
        self.roundness_slider.blockSignals(False)
        
        self.border_slider.blockSignals(True)
        self.border_slider.setValue(t.border_width)
        self.border_slider.blockSignals(False)
        
        # Sync dark mode checkbox
        self.dark_mode_check.blockSignals(True)
        self.dark_mode_check.setChecked(t.dark_mode)
        self.dark_mode_check.blockSignals(False)
        
        # NOTE: all_keyframes_behavior setting removed - using unified curve sampler instead

    def _get_resolve_path(self) -> str:
        """Get current Resolve installation path from settings, environment, or default."""
        import os
        
        # Helper to find dll inside a folder
        def _find_dll(folder):
            for cand in [folder, os.path.join(folder, "Support")]:
                dll = os.path.join(cand, "fusionscript.dll")
                if os.path.isfile(dll):
                    return dll
            return None
        
        # First check theme settings
        path = get_theme().resolve_path
        if path:
            # path might be a folder or the dll itself
            if os.path.isfile(path):
                os.environ["RESOLVE_SCRIPT_LIB"] = path
                return os.path.dirname(path)
            elif os.path.isdir(path):
                dll = _find_dll(path)
                if dll:
                    os.environ["RESOLVE_SCRIPT_LIB"] = dll
                    return path
        
        # Then check environment
        env_path = os.environ.get("RESOLVE_SCRIPT_LIB", "")
        if env_path and os.path.isfile(env_path):
            return os.path.dirname(env_path)
        if env_path and os.path.isdir(env_path):
            dll = _find_dll(env_path)
            if dll:
                os.environ["RESOLVE_SCRIPT_LIB"] = dll
                return env_path
        
        # Try default paths
        defaults = [
            r"C:\Program Files\Blackmagic Design\DaVinci Resolve",
            r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Support",
        ]
        for d in defaults:
            if os.path.isdir(d):
                dll = _find_dll(d)
                if dll:
                    os.environ["RESOLVE_SCRIPT_LIB"] = dll
                return d
        return "Not found - click Browse to set"

    def _on_browse_resolve_path(self):
        """Open folder dialog to select Resolve installation path."""
        from PySide6.QtWidgets import QFileDialog
        import os
        
        current = self.resolve_path_edit.text()
        # Start from common locations
        if not os.path.isdir(current):
            if os.path.isdir(r"C:\Program Files\Blackmagic Design"):
                current = r"C:\Program Files\Blackmagic Design"
            else:
                current = r"C:\Program Files"
        
        path = QFileDialog.getExistingDirectory(
            self, 
            "Select the 'DaVinci Resolve' folder (contains fusionscript.dll)",
            current,
            QFileDialog.ShowDirsOnly
        )
        
        if path and os.path.isdir(path):
            # Validate it looks like a Resolve folder (contains fusionscript.dll or similar)
            has_fusion = os.path.exists(os.path.join(path, "fusionscript.dll"))
            has_resolve = os.path.exists(os.path.join(path, "Resolve.exe"))
            has_support = os.path.exists(os.path.join(path, "Support", "fusionscript.dll"))
            
            # Derive actual dll path for the env var
            dll_path = None
            if has_fusion:
                dll_path = os.path.join(path, "fusionscript.dll")
            elif has_support:
                dll_path = os.path.join(path, "Support", "fusionscript.dll")
            
            if has_fusion or has_resolve or has_support:
                if dll_path:
                    os.environ["RESOLVE_SCRIPT_LIB"] = dll_path
                    get_theme().resolve_path = dll_path
                else:
                    os.environ["RESOLVE_SCRIPT_LIB"] = path
                    get_theme().resolve_path = path
                get_theme()._save_settings()
                self.resolve_path_edit.setText(path)
                self.resolve_status_lbl.setText("Status: Path saved (click Test)")
                self.resolve_status_lbl.setStyleSheet(f"color: {get_theme().accent};")
            else:
                # Still allow it but warn
                os.environ["RESOLVE_SCRIPT_LIB"] = path
                get_theme().resolve_path = path
                get_theme()._save_settings()
                self.resolve_path_edit.setText(path)
                self.resolve_status_lbl.setText("Status: Path saved (warning: may not be valid)")
                self.resolve_status_lbl.setStyleSheet("color: #FFAA00;")

    def _on_test_resolve_connection(self):
        """Test connection to DaVinci Resolve with current settings."""
        import os
        
        self.resolve_status_lbl.setText("Status: Testing...")
        self.resolve_status_lbl.setStyleSheet(f"color: {get_theme().text_secondary};")
        QApplication.processEvents()
        
        # Try to connect
        ok = self.core.connect_resolve()
        if ok:
            info = self.core.get_resolve_status()
            prod = info.get("info", {}).get("name", "Resolve")
            ver = info.get("info", {}).get("version", "")
            self.resolve_status_lbl.setText(f"Status: Connected to {prod} {ver}")
            self.resolve_status_lbl.setStyleSheet(f"color: #00FF00;")
            self.status_lbl.setText(f"Connected: {prod}")
        else:
            err = self.core.bridge.last_error
            self.resolve_status_lbl.setText(f"Status: Failed - {err[:40]}...")
            self.resolve_status_lbl.setStyleSheet("color: #FF5555;")
            self.status_lbl.setText("Resolve: disconnected")

    def _on_style_changed(self, text):
        t = get_theme()
        if text == "Brutalist":
            t.set_design_style(t.STYLE_BRUTALIST)
        elif text == "Minimal":
            t.set_design_style(t.STYLE_MINIMAL)

    def _on_custom_color(self):
        from PySide6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(QColor(get_theme().accent), self, "Choose Accent Color")
        if color.isValid():
            get_theme().set_custom_color(color.name())

    def _load_preview_html(self):
        preview_path = os.path.join(os.path.dirname(__file__), "preview_compact.html")
        self.preview.load(QUrl.fromLocalFile(preview_path))

    def _on_preview_ready(self):
        self._preview_ready = True
        # Sync theme colors to HTML preview
        theme = get_theme()
        self.preview.page().runJavaScript(f"""
            if(typeof setAccentColor !== 'undefined') setAccentColor('{theme.accent}');
            if(typeof setBgColor !== 'undefined') setBgColor('{theme.bg_outer}');
        """)
        self._sync_preview_with_core()

    def _sync_preview_with_core(self):
        if not self._preview_ready:
            return
        
        # Update bottom strip labels
        self.lbl_in_frame.setText(str(int(self.core.start_frame)))
        self.lbl_out_frame.setText(str(int(self.core.end_frame)))
        self.lbl_dur.setText(str(int(self.core.end_frame - self.core.start_frame)))
        
        # Update % pills
        rh = self.core.manual_rh
        lh = self.core.manual_lh
        self.lbl_rh_pill.setText(f"{int(rh.get('t', 0.33) * 100)}%")
        self.lbl_lh_pill.setText(f"{int((1 - lh.get('t', 0.67)) * 100)}%")
        
        is_bezier = self.core.is_handle_mode()

        # For flat bezier (start == end), if both handles are near 0.5 the preview
        # renders a nearly-invisible flat line.  Reset to the default S-curve so the
        # user always sees a meaningful curve without having to touch the handles.
        if (is_bezier and abs(self.core.start_value - self.core.end_value) < 0.0001
                and not self._curve_flip_enabled):
            rh_v = self.core.manual_rh.get('v', 0.0)
            lh_v = self.core.manual_lh.get('v', 1.0)
            if abs(rh_v - 0.5) < 0.15 and abs(lh_v - 0.5) < 0.15:
                self.core.manual_rh = {"t": self.core.manual_rh.get('t', 0.33), "v": 0.0}
                self.core.manual_lh = {"t": self.core.manual_lh.get('t', 0.67), "v": 1.0}

        # Sync value range for curve direction (high->low or low->high)
        js_range = f"""
            if(typeof setValueRange !== 'undefined') {{ setValueRange({self.core.start_value}, {self.core.end_value}); }}
            if(typeof setFlipEnabled !== 'undefined') {{ setFlipEnabled({str(self._curve_flip_enabled).lower()}); }}
        """
        self.preview.page().runJavaScript(js_range)
        
        if is_bezier:
            js = f"""
                if(typeof setMode !== 'undefined') {{ setMode('bezier'); }}
                if(typeof setHandles !== 'undefined') {{ setHandles({json.dumps(self.core.manual_rh)}, {json.dumps(self.core.manual_lh)}); }}
            """
            self.preview.page().runJavaScript(js)
        else:
            # Ensure JS mode matches Python mode — prevents stale bezier display
            p = self.core.params
            if self.core.mode == "elastic":
                js = f"""
                    if(typeof setMode !== 'undefined') {{ setMode('elastic'); }}
                    if(typeof setElasticParams !== 'undefined') {{ setElasticParams({p.get('bounciness', 0.5)}, {p.get('amplitude', 1)}, 1, {p.get('decay_x', 0.5)}, {p.get('decay_y', 0.5)}, {p.get('hang', 0.5)}); }}
                """
            elif self.core.mode == "bounce":
                # Invert bounciness for intuitive behavior: high value = more bounce
                raw_bounciness = p.get('bounciness', 0.5)
                display_bounciness = 0.99 - raw_bounciness  # Invert: 0->0.99, 0.99->0
                js = f"""
                    if(typeof setMode !== 'undefined') {{ setMode('bounce'); }}
                    if(typeof setBounceParams !== 'undefined') {{ setBounceParams({display_bounciness}, {p.get('amplitude', 1)}, {p.get('gravity', 1)}, {p.get('decay_x', 0.5)}, {p.get('decay_y', 0.5)}, {p.get('hang', 0)}); }}
                """
            else:
                js = None
            if js:
                self.preview.page().runJavaScript(js)

    def _connect_signals(self):
        self.btn_bezier.clicked.connect(lambda: self._switch_tab(0))
        self.btn_elastic.clicked.connect(lambda: self._switch_tab(1))
        self.btn_bounce.clicked.connect(lambda: self._switch_tab(2))
        self.btn_favs.clicked.connect(lambda: self._switch_tab(3))
        self.btn_settings.clicked.connect(lambda: self._switch_tab(4))

        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_save.clicked.connect(self._on_add_favorite)

    def _set_keyframe_mode(self, clicked_mode):
        """Switch keyframe targeting mode using explicit feature toggles.

        Each mode button (Recent, All, Custom) toggles its own feature on/off.
        Combined modes (recent_all, all_custom) are created by having multiple
        features active at once. Overwrite is mutually exclusive.
        """
        original_mode = self._keyframe_target_mode

        if clicked_mode == "overwrite":
            new_mode = "recent" if original_mode == "overwrite" else "overwrite"
        else:
            # If leaving overwrite, reset to recent before applying the click
            base_mode = "recent" if original_mode == "overwrite" else original_mode

            # Parse current mode into active features
            features = set()
            if "recent" in base_mode: features.add("recent")
            if "all" in base_mode: features.add("all")
            if "custom" in base_mode: features.add("custom")

            # Toggle the clicked feature
            # "recent" and "custom" are mutually exclusive — clicking one always
            # deactivates the other so you can never be stuck in an invalid combo.
            feature = {"recent": "recent", "all": "all", "custom": "custom"}.get(clicked_mode)
            if feature in features:
                features.remove(feature)
            else:
                if feature == "recent":
                    features.discard("custom")   # recent clears custom
                elif feature == "custom":
                    features.discard("recent")   # custom clears recent
                    features.discard("all")      # custom clears all
                elif feature == "all":
                    features.discard("custom")   # all clears custom
                    features.discard("all")      # custom clears all
                elif feature == "all":
                    features.discard("custom")   # all clears custom
                features.add(feature)

            # Ensure at least one feature remains active
            if not features:
                features.add(clicked_mode)

            # Map features back to mode string
            if features == {"recent"}:
                new_mode = "recent"
            elif features == {"all"}:
                new_mode = "all"
            elif features == {"custom"}:
                new_mode = "custom"
            elif features == {"recent", "all"}:
                new_mode = "recent_all"
            elif features == {"all", "custom"}:
                new_mode = "all"  # all_custom removed — custom is ignored when all is active
            else:
                new_mode = "recent"

        self._keyframe_target_mode = new_mode
        self.btn_mode_all.set_active(new_mode in ("all", "recent_all", "all_custom"))
        self.btn_mode_recent.set_active(new_mode in ("recent", "recent_all"))
        self.btn_mode_custom.set_active(new_mode in ("custom", "all_custom"))
        self.btn_overwrite.set_active(new_mode == "overwrite")

        if new_mode == "overwrite":
            self._get_or_update_physics_base()
        elif original_mode == "overwrite":
            # Leaving overwrite mode — clear the cached base
            self._physics_base_segment = None
            self._physics_base_spline_name = ""

        labels = {
            "recent": "Recent", "all": "All Keyframes",
            "custom": "Custom Range", "overwrite": "Overwrite",
            "recent_all": "Recent + All",
            "all_custom": "All + Custom Range",
        }
        self.status_lbl.setText(f"Mode: {labels.get(new_mode, new_mode)}")

    def _switch_tab(self, idx):
        prev_tab_idx = self._current_tab_idx
        self._current_tab_idx = idx
        # Cancel any pending hover popup from previous tab
        self._hover_show_timer.stop()
        self._hover_hide_timer.stop()
        self._hover_pending = None
        self.floating_popup.hide_popup()
        self.stack.setCurrentIndex(idx)
        self._update_nav_buttons(idx)

        # Only reset physics base when crossing between bezier (0) and physics (1,2).
        # Switching elastic↔bounce while overwrite is on keeps the same base so the
        # user can swap modes without losing their target segment.
        if prev_tab_idx == 0 or idx == 0:
            self._physics_base_segment = None
            self._physics_base_spline_name = ""

        # Strip visibility: strictly bound to page
        is_bezier_page  = (idx == 0)
        is_elastic_page = (idx == 1)
        is_bounce_page = (idx == 2)
        is_physics_page = (idx in (1, 2))
        is_favorites_page = (idx == 3)
        self.lbl_rh_pill.setVisible(is_bezier_page)
        self.lbl_lh_pill.setVisible(is_bezier_page)
        self.lbl_separator.setVisible(is_bezier_page)
        self.lbl_controls.setVisible(is_physics_page)
        
        # Direction toggle visibility: only on Elastic/Bounce pages
        self.btn_dir.setVisible(is_physics_page)

        # Playhead filter visible on all pages
        self.btn_playhead.setVisible(True)
        
        # Pin button only visible on Favorites page
        self.btn_fav_pin.setVisible(is_favorites_page)

        # Custom range hidden on physics, overwrite shown on physics
        self.btn_mode_custom.setVisible(not is_physics_page)
        self.btn_overwrite.setVisible(is_physics_page)
        
        # Reset mode if invalid for current page
        if is_bezier_page and self._keyframe_target_mode == "overwrite":
            self._set_keyframe_mode("recent")
        elif is_physics_page and self._keyframe_target_mode == "custom":
            self._set_keyframe_mode("recent")
        
        # Sync direction toggle label when switching to physics pages
        if is_physics_page:
            self.btn_dir.setText("IN" if self.core.direction == "in" else "OUT")
            self.btn_dir.update()
        
        # Preview and Save button visibility: hidden on Favorites page
        self.preview.parent().setVisible(not is_favorites_page)
        self.btn_save.setVisible(not is_favorites_page)
        
        # Adjust window height for Favorites page (no preview)
        if is_favorites_page:
            self.resize(self.width(), 400)

        if idx == 0:
            self.core.mode = "bezier"
            if self.core.source == "physics":
                self.core.source = "manual"
            self._sync_preview_with_core()
        elif idx == 1:
            self.core.set_mode("elastic")
            if self.core.params.get("duration_ratio", 0.0) > 0.99:
                self.core.params["duration_ratio"] = 0.5
            self.core.invalidate_physics_cache()  # Force regeneration
            self._sync_params_to_preview()
        elif idx == 2:
            self.core.set_mode("bounce")
            if self.core.params.get("gravity_ratio", 0.0) > 0.99:
                self.core.params["gravity_ratio"] = 0.5
            self.core.invalidate_physics_cache()  # Force regeneration
            self._sync_params_to_preview()
        elif idx == 3:
            self._refresh_favorites()

    def _on_preset_selected(self, name):
        # Built-in preset names always use the standard path.
        # Only route to favorites for names that are NOT in the PRESETS dict
        # (i.e. genuinely custom saved presets).
        if name not in PRESETS:
            favorites = self.library.get_all()
            for i, fav in enumerate(favorites):
                if fav.get("name") == name:
                    if getattr(self, '_preview_ready', False):
                        self.preview.page().runJavaScript(
                            "if(typeof resetManualEdits !== 'undefined') { resetManualEdits(); }")
                    self._load_favorite(i)
                    mode = fav.get("mode", "bezier")
                    if mode == "elastic":
                        self._switch_tab(1)
                    elif mode == "bounce":
                        self._switch_tab(2)
                    else:
                        self._switch_tab(0)
                    return

        self.core.select_preset(name)

        if getattr(self, '_preview_ready', False):
            self.preview.page().runJavaScript("if(typeof resetManualEdits !== 'undefined') { resetManualEdits(); }")

        # Sync preview with new handle values from preset
        self._sync_preview_with_core()

        preset_cat = PRESETS.get(name, {}).get("cat", "")
        if preset_cat == "Elastic":
            self._switch_tab(1)
        elif preset_cat == "Bounce":
            self._switch_tab(2)
        else:
            self._switch_tab(0)

        self.status_lbl.setText(f"Selected: {name}")
        self._trigger_auto_apply("card", mode=preset_cat.lower() if preset_cat else "bezier")

    def _on_custom_changed(self, _text=None):
        start_name = self.combo_in.currentText()
        end_name = self.combo_out.currentText()
        
        self.core.source = "custom"
        self.core.custom_in = start_name
        self.core.custom_out = end_name
        self.core.selected_preset = None
        
        # Standard ease-in values (Right Handle)
        ease_in = {
            "Linear": (0.0, 0.0),
            "Sine":   (0.12, 0.0),
            "Quad":   (0.11, 0.0),
            "Cubic":  (0.32, 0.0),
            "Quart":  (0.5, 0.0),
            "Quint":  (0.64, 0.0),
            "Expo":   (0.7, 0.0),
            "Circ":   (0.54, 0.0),
            "Back":   (0.36, -0.6),
        }
        
        # Standard ease-out values (Left Handle)
        ease_out = {
            "Linear": (1.0, 1.0),
            "Sine":   (0.61, 1.0),
            "Quad":   (0.5, 1.0),
            "Cubic":  (0.64, 1.0),
            "Quart":  (0.76, 1.0),
            "Quint":  (0.84, 1.0),
            "Expo":   (0.88, 1.0),
            "Circ":   (0.79, 1.0),
            "Back":   (0.64, 1.6),
        }
        
        # Get handle positions
        rh_t, rh_v = ease_in.get(start_name, (0.33, 0.33))
        lh_t, lh_v = ease_out.get(end_name, (0.67, 0.67))
        
        self.core.manual_rh = {"t": rh_t, "v": rh_v}
        self.core.manual_lh = {"t": lh_t, "v": lh_v}
        self._sync_preview_with_core()
        self._trigger_auto_apply("combo")

    def _on_elastic_param_changed(self, param, val):
        self.core.set_param(param, val)
        self._sync_params_to_preview()
        self._trigger_auto_apply("slider")

    def _on_bounce_param_changed(self, param, val):
        self.core.set_param(param, val)
        self._sync_params_to_preview()
        self._trigger_auto_apply("slider")

    def _on_pin_requested(self, snapshot: dict):
        """Spawn an independent PinnedControlPanel — one per control type max."""
        # Block duplicate: same handle_type or mode already pinned
        for existing in self._pinned_panels:
            if (existing._handle_type and existing._handle_type == snapshot.get("handle_type")):
                existing.raise_()  # bring existing to front instead
                return
            if (existing._mode and existing._mode == snapshot.get("mode")):
                existing.raise_()
                return

        panel = PinnedControlPanel(snapshot)
        self._pinned_panels.append(panel)

        # Wire signals — bezier panels track which handle they belong to
        handle_type = snapshot.get("handle_type")
        if handle_type:
            panel.bezierXChanged.connect(
                lambda v, h=handle_type: self._update_bezier_from_pinned(h, x=v))
            panel.bezierYChanged.connect(
                lambda v, h=handle_type: self._update_bezier_from_pinned(h, y=v))
        panel.physicsChanged.connect(self._on_popup_physics_changed)
        panel.sliderReleased.connect(self._do_pending_auto_apply)
        panel.closed.connect(self._on_pinned_panel_closed)

    def _update_bezier_from_pinned(self, handle_type, x=None, y=None):
        """Route pinned panel bezier changes to the correct handle."""
        prev = self._current_handle
        self._current_handle = handle_type
        self._update_bezier_from_popup(x=x, y=y)
        self._current_handle = prev

    def _on_pinned_panel_closed(self, panel):
        if panel in self._pinned_panels:
            self._pinned_panels.remove(panel)

    def _on_direction_toggle(self):
        """Toggle in/out direction for Elastic/Bounce pages."""
        self.core.direction = "in" if self.core.direction == "out" else "out"
        self.btn_dir.setText("IN" if self.core.direction == "in" else "OUT")
        self.btn_dir.update()
        self._sync_params_to_preview()
        self.status_lbl.setText(f"{self.core.mode.capitalize()}: {self.core.direction.upper()}")
        self._trigger_auto_apply("direction")

    def _on_playhead_filter_toggle(self):
        """Toggle playhead segment filter on/off for All and Recent+All modes."""
        self._playhead_filter = not self._playhead_filter
        self.btn_playhead.set_active(self._playhead_filter)
        state = "ON" if self._playhead_filter else "OFF"
        self.status_lbl.setText(f"Playhead filter: {state}")

    def _sync_params_to_preview(self):
        if not self._preview_ready:
            return
        
        # Update bottom strip for physics modes
        self.lbl_in_frame.setText(str(int(self.core.start_frame)))
        self.lbl_out_frame.setText(str(int(self.core.end_frame)))
        self.lbl_dur.setText(str(int(self.core.end_frame - self.core.start_frame)))
        
        # Sync value range for curve direction
        js_range = f"""
            if(typeof setValueRange !== 'undefined') {{ setValueRange({self.core.start_value}, {self.core.end_value}); }}
        """
        self.preview.page().runJavaScript(js_range)
        
        p = self.core.params
        direction_js = f"if(typeof setDirection !== 'undefined') {{ setDirection('{self.core.direction}'); }}"
        
        if self.core.mode == "elastic":
            js = f"""
                if(typeof setMode !== 'undefined') {{ setMode('elastic'); }}
                if(typeof setElasticParams !== 'undefined') {{ setElasticParams({p.get('bounciness', 0.5)}, {p.get('amplitude', 1)}, 1, {p.get('decay_x', 0.5)}, {p.get('decay_y', 0.5)}, {p.get('hang', 0.5)}); }}
                {direction_js}
            """
        elif self.core.mode == "bounce":
            # Invert bounciness for preview: high core value = high bounce, but HTML expects inverted
            preview_bounciness = 0.99 - p.get('bounciness', 0.5)
            js = f"""
                if(typeof setMode !== 'undefined') {{ setMode('bounce'); }}
                if(typeof setBounceParams !== 'undefined') {{ setBounceParams({preview_bounciness}, {p.get('amplitude', 1)}, {p.get('gravity', 1)}, {p.get('decay_x', 0.5)}, {p.get('decay_y', 0.5)}, {p.get('hang', 0)}); }}
                {direction_js}
            """
        else:
            return
        self.preview.page().runJavaScript(js)

    def _sync_params_to_preview_no_labels(self):
        """Send physics params to JS preview without touching frame labels."""
        if not self._preview_ready:
            return
        p = self.core.params
        if self.core.mode == "elastic":
            js = f"""if(typeof setElasticParams !== 'undefined') {{ setElasticParams({p.get('bounciness', 0.5)}, {p.get('amplitude', 1)}, 1, {p.get('decay_x', 0.5)}, {p.get('decay_y', 0.5)}, {p.get('hang', 0.5)}); }}"""
        elif self.core.mode == "bounce":
            # Invert bounciness for preview: high core value = high bounce, but HTML expects inverted
            preview_bounciness = 0.99 - p.get('bounciness', 0.5)
            js = f"""if(typeof setBounceParams !== 'undefined') {{ setBounceParams({preview_bounciness}, {p.get('amplitude', 1)}, {p.get('gravity', 1)}, {p.get('decay_x', 0.5)}, {p.get('decay_y', 0.5)}, {p.get('hang', 0)}); }}"""
        else:
            return
        self.preview.page().runJavaScript(js)



    def _on_handle_drag_started(self, handle_type, t, v):
        """Show popup when user starts dragging a handle in the preview."""
        # Section 2: cancel any pending drag-release close so re-grabbing mid-fade works cleanly
        self._drag_release_timer.stop()
        self._current_handle = handle_type
        if handle_type == 'rh':
            trigger_widget = self.lbl_rh_pill
            pos = self.lbl_rh_pill.mapToGlobal(QPoint(self.lbl_rh_pill.width() // 2, self.lbl_rh_pill.height()))
        else:
            trigger_widget = self.lbl_lh_pill
            pos = self.lbl_lh_pill.mapToGlobal(QPoint(self.lbl_lh_pill.width() // 2, self.lbl_lh_pill.height()))
        self._popup_trigger_widget = trigger_widget
        self.floating_popup.show_bezier_controls(
            handle_type, t, v, pos, trigger_widget=trigger_widget
        )

    # ── Section 2: handle drag-release → close popup ─────────────────────────
    def _on_handle_released(self):
        """Called when the user releases a bezier handle drag in the canvas.
        Starts a short timer; if the mouse isn't over the popup when it fires,
        the popup fades out — matching the handle-drag show/hide symmetry."""
        self._drag_release_timer.start(200)

    def _on_drag_release_timeout(self):
        if self.floating_popup.isVisible() and not self.floating_popup.underMouse():
            self.floating_popup.hide_popup()
    # ─────────────────────────────────────────────────────────────────────────

    def _on_handle_moved(self, handle_type, t, v):
        self.core.set_handle(handle_type, t, v)
        self._sync_preview_with_core()  # Update percentage pills
        # Also update the popup if it's visible
        if self.floating_popup.isVisible() and self.floating_popup._current_handle == handle_type:
            if 'x' in self.floating_popup._sliders:
                self.floating_popup._sliders['x'].blockSignals(True)
                self.floating_popup._sliders['x'].setValue(t)
                self.floating_popup._sliders['x'].blockSignals(False)
            if 'y' in self.floating_popup._sliders:
                self.floating_popup._sliders['y'].blockSignals(True)
                self.floating_popup._sliders['y'].setValue(v)
                self.floating_popup._sliders['y'].blockSignals(False)
        self._trigger_auto_apply("slider")

    def _on_handle_moved_mod(self, handle_type: str, t: float, v: float, shift: bool, ctrl: bool):
        """Update handles when dragged in the web preview, applying modifiers."""
        # Update the dragged handle
        self.core.set_handle(handle_type, t, v)
        
        # Apply modifier logic (mirror/tangent)
        other = "lh" if handle_type == "rh" else "rh"
        other_t = None
        other_v = None
        if shift:
            other_t = t
            other_v = v
            self.core.set_handle(other, other_t, other_v)
        elif ctrl:
            other_t = 1.0 - t
            other_v = 1.0 - v
            self.core.set_handle(other, other_t, other_v)
            
        self._sync_preview_with_core()
        
        # Update the popup if it's visible - update both dragged and other handle if linked
        if self.floating_popup.isVisible():
            popup_handle = self.floating_popup._current_handle
            # Update the dragged handle's sliders
            if popup_handle == handle_type:
                if 'x' in self.floating_popup._sliders:
                    self.floating_popup._sliders['x'].blockSignals(True)
                    self.floating_popup._sliders['x'].setValue(t)
                    self.floating_popup._sliders['x'].blockSignals(False)
                if 'y' in self.floating_popup._sliders:
                    self.floating_popup._sliders['y'].blockSignals(True)
                    self.floating_popup._sliders['y'].setValue(v)
                    self.floating_popup._sliders['y'].blockSignals(False)
            # If the popup is showing the OTHER handle and we're linked, update it too
            elif (shift or ctrl) and popup_handle == other and other_t is not None:
                if 'x' in self.floating_popup._sliders:
                    self.floating_popup._sliders['x'].blockSignals(True)
                    self.floating_popup._sliders['x'].setValue(other_t)
                    self.floating_popup._sliders['x'].blockSignals(False)
                if 'y' in self.floating_popup._sliders:
                    self.floating_popup._sliders['y'].blockSignals(True)
                    self.floating_popup._sliders['y'].setValue(other_v)
                    self.floating_popup._sliders['y'].blockSignals(False)
        
        self._trigger_auto_apply("slider")

    def _on_frames_changed(self, in_frame, out_frame, duration):
        self.core.start_frame = in_frame
        self.core.end_frame = out_frame
        self.lbl_in_frame.setText(str(int(in_frame)))
        self.lbl_out_frame.setText(str(int(out_frame)))
        self.lbl_dur.setText(str(int(duration)))
        self._sync_preview_with_core()
        # Switch to custom range mode when user drags frame boundaries in preview
        self._set_keyframe_mode("custom")
        # Debounce push to Resolve since this comes from JS preview interaction
        self._debounce_push_timer.stop()
        self._pending_push_frames = True
        self._debounce_push_timer.start(50)

    def _on_popup_physics_changed(self, param, val):
        """Handle physics param change from floating popup"""
        if param == "duration_ratio":
            # val is 0.0-1.0; show frames = ratio × reference comp dur
            comp = getattr(self, '_comp_ref_frames', max(1, int(self.core.end_frame - self.core.start_frame)))
            new_dur = max(1, int(val * comp))
            self.core.params["duration_ratio"] = val
            self.core.end_frame = self.core.start_frame + new_dur
            self.lbl_dur.setText(str(new_dur))
            self.lbl_out_frame.setText(str(int(self.core.end_frame)))
            # Sync preview BEFORE updating duration so the curve shape stays
            # stable — duration only affects the oscillation shape in JS, not timing
            self._sync_params_to_preview_no_labels()
            # Now set duration for apply-time keyframe generation
            self.core.params["duration"] = val
            # Push timing change to Resolve
            self._debounce_push_timer.stop()
            self._pending_push_frames = True
            self._debounce_push_timer.start(50)
            # Switch to custom range when physics duration is adjusted
            self._set_keyframe_mode("custom")
            self._trigger_auto_apply("slider")
            return
        if param == "gravity_ratio":
            # Gravity in Bounce is like Duration in Elastic
            comp = getattr(self, '_comp_ref_frames', max(1, int(self.core.end_frame - self.core.start_frame)))
            new_dur = max(1, int(val * comp))
            self.core.params["gravity_ratio"] = val
            self.core.params["gravity"] = val  
            self.core.params["duration"] = val # Sync duration key too
            self.core.end_frame = self.core.start_frame + new_dur
            self.lbl_dur.setText(str(new_dur))
            self.lbl_out_frame.setText(str(int(self.core.end_frame)))
            self._sync_params_to_preview_no_labels()
            # Push timing change to Resolve
            self._debounce_push_timer.stop()
            self._pending_push_frames = True
            self._debounce_push_timer.start(50)
            # Switch to custom range when physics gravity/duration is adjusted
            self._set_keyframe_mode("custom")
            self._trigger_auto_apply("slider")
            return

        self.core.set_param(param, val)
        self._sync_params_to_preview()
        self._trigger_auto_apply("slider")

    def _update_bezier_from_popup(self, x=None, y=None):
        """Update bezier handle from floating popup with Shift/Ctrl linking"""
        if not self._current_handle:
            return
        handle = self._current_handle
        other = "lh" if handle == "rh" else "rh"
        
        # Get FRESH current values directly from core (not cached)
        handle_data = self.core.manual_rh if handle == "rh" else self.core.manual_lh
        other_data = self.core.manual_lh if handle == "rh" else self.core.manual_rh
        
        # Use provided value or fall back to current
        t = x if x is not None else handle_data.get("t", 0.33 if handle == "rh" else 0.67)
        v = y if y is not None else handle_data.get("v", 0.0 if handle == "rh" else 1.0)
        
        from PySide6.QtWidgets import QApplication
        modifiers = QApplication.keyboardModifiers()
        shift_pressed = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        ctrl_pressed = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        
        # Shift = Same: other handle gets identical t and v
        # Ctrl = Symmetrical: other handle mirrors both t and v (inverted)
        if shift_pressed or ctrl_pressed:
            other_t = t if shift_pressed else 1.0 - t
            other_v = v if shift_pressed else 1.0 - v
            self.core.set_handle(other, other_t, other_v)
            # Also update the popup for the other handle if it's visible
            if self.floating_popup.isVisible() and self.floating_popup._current_handle == other:
                if 'x' in self.floating_popup._sliders:
                    self.floating_popup._sliders['x'].blockSignals(True)
                    self.floating_popup._sliders['x'].setValue(other_t)
                    self.floating_popup._sliders['x'].blockSignals(False)
                if 'y' in self.floating_popup._sliders:
                    self.floating_popup._sliders['y'].blockSignals(True)
                    self.floating_popup._sliders['y'].setValue(other_v)
                    self.floating_popup._sliders['y'].blockSignals(False)
        
        # Update the active handle
        self.core.set_handle(handle, t, v)
        self._sync_preview_with_core()
        self._trigger_auto_apply("slider")

    def _is_physics_base_valid(self):
        """Check if the cached physics base segment is still valid.

        Intentionally does NOT check playhead position — overwrite mode is
        sticky: once a base is captured it stays valid as long as the spline
        still has keyframes at both endpoint frames. This lets the user move
        the playhead to audition the result and re-apply with new params
        without losing the base.
        """
        seg = getattr(self, '_physics_base_segment', None)
        if not seg:
            return False
        # Verify the spline still has keyframes at both endpoint frames
        try:
            spline = seg.get("spline")
            if spline is None:
                return False
            kfs = spline.GetKeyFrames()
            left_ok = any(
                isinstance(k, (int, float)) and abs(k - self._physics_base_left) < 0.001
                for k in kfs
            )
            right_ok = any(
                isinstance(k, (int, float)) and abs(k - self._physics_base_right) < 0.001
                for k in kfs
            )
            return left_ok and right_ok
        except Exception:
            return False

    def _get_or_update_physics_base(self):
        """Return the cached base segment, or fetch recent and cache it."""
        if self._is_physics_base_valid():
            self.core._target_segment = dict(self._physics_base_segment)
            self.core.start_frame = self._physics_base_left
            self.core.end_frame = self._physics_base_right
            self.core.start_value = self._physics_base_segment["left_value"]
            self.core.end_value = self._physics_base_segment["right_value"]
            return {
                "ok": True,
                "spline_name": self._physics_base_spline_name,
                "start_frame": self._physics_base_left,
                "end_frame": self._physics_base_right,
            }
        res = self.core.fetch_keyframes_smart(mode="recent")
        if res.get("ok"):
            seg = getattr(self.core, '_target_segment', None)
            if seg:
                self._physics_base_segment = {
                    "left_frame": seg.get("left_frame"),
                    "right_frame": seg.get("right_frame"),
                    "left_value": seg.get("left_value"),
                    "right_value": seg.get("right_value"),
                    "spline": seg.get("spline"),
                    "kfs": seg.get("kfs"),
                }
                self._physics_base_spline_name = res.get("spline_name", getattr(self.core, '_target_spline_name', ''))
                self._physics_base_left = float(res.get("start_frame", 0))
                self._physics_base_right = float(res.get("end_frame", 0))
        return res

    def _on_apply(self):
        """
        Apply curve from preview to Resolve.
        Unified: JS draws it, Python writes it. Same for bezier/elastic/bounce.
        """
        if not self.core.bridge.is_connected():
            if not self.core.connect_resolve():
                self.status_lbl.setText("Resolve not connected")
                return

        if self._keyframe_target_mode == "all":
            if self._playhead_filter:
                self._on_apply_all_at_playhead()
            else:
                self._on_apply_all()
            return

        if self._keyframe_target_mode == "recent_all":
            if self._playhead_filter:
                self._on_apply_recent_all_at_playhead()
            else:
                self._on_apply_recent_all()
            return


        if self._keyframe_target_mode == "overwrite":
            res = self._get_or_update_physics_base()
        else:
            mode = "custom" if self._keyframe_target_mode == "custom" else "recent"
            res = self.core.fetch_keyframes_smart(mode=mode)
        
        if not res or not res.get("ok"):
            self.status_lbl.setText(res.get("message") or f"Fetch: {res.get('error', 'Failed')}")
            return

        # Step 2: Build keyframes
        # For bezier mode, generate directly in Python to avoid async JS state-sync races
        if self.core.is_handle_mode():
            js_keyframes = [
                {"t": 0, "v": 0, "rh": dict(self.core.manual_rh)},
                {"t": 1, "v": 1, "lh": dict(self.core.manual_lh)}
            ]
            import json
            self._finish_apply(json.dumps({"ok": True, "data": js_keyframes}), res)
        else:
            js_code = """
                (function() {
                    try {
                        if (typeof getCurveKeyframes !== 'undefined') {
                            return JSON.stringify({ok: true, data: getCurveKeyframes()});
                        }
                        return JSON.stringify({ok: false, error: "getCurveKeyframes missing"});
                    } catch (e) {
                        return JSON.stringify({ok: false, error: e.toString()});
                    }
                })()
            """
            self.preview.page().runJavaScript(
                js_code,
                lambda kfs: self._finish_apply(kfs, res)
            )


    def _on_apply_all(self):
        """Apply selected preset to every segment on every animated input of every selected node."""
        if self.core.is_handle_mode():
            js_keyframes = [
                {"t": 0, "v": 0, "rh": dict(self.core.manual_rh)},
                {"t": 1, "v": 1, "lh": dict(self.core.manual_lh)}
            ]
            import json
            self._finish_apply_all(json.dumps({"ok": True, "data": js_keyframes}))
        else:
            js_code = """
                (function() {
                    try {
                        if (typeof getCurveKeyframes !== 'undefined') {
                            return JSON.stringify({ok: true, data: getCurveKeyframes()});
                        }
                        return JSON.stringify({ok: false, error: "getCurveKeyframes missing"});
                    } catch (e) {
                        return JSON.stringify({ok: false, error: e.toString()});
                    }
                })()
            """
            self.preview.page().runJavaScript(js_code, self._finish_apply_all)

    def _finish_apply_all(self, raw_js):
        import json
        if not raw_js or not isinstance(raw_js, str):
            self.status_lbl.setText("No keyframes from preview")
            return
        try:
            parsed = json.loads(raw_js)
        except Exception:
            self.status_lbl.setText("Failed to parse JS output")
            return
        if not parsed.get("ok"):
            self.status_lbl.setText(f"JS Error: {parsed.get('error', 'Unknown')[:30]}")
            return
        js_keyframes = parsed.get("data", [])
        if not js_keyframes or len(js_keyframes) < 2:
            self.status_lbl.setText("No keyframes from preview")
            return
        result = self.core.apply_all_keyframes(js_keyframes)
        if result.get("ok"):
            total = result.get("total_segments", 0)
            tools = result.get("tools", 0)
            self.status_lbl.setText(f"Applied to {total} segments ({tools} tools)")
        else:
            self.status_lbl.setText(f"Failed: {result.get('error', 'Unknown')}")

    def _on_apply_recent_all(self):
        """Gather JS keyframes and apply to recently-changed control on all selected nodes."""
        if self.core.is_handle_mode():
            js_keyframes = [
                {"t": 0, "v": 0, "rh": dict(self.core.manual_rh)},
                {"t": 1, "v": 1, "lh": dict(self.core.manual_lh)}
            ]
            import json
            self._finish_apply_recent_all(json.dumps({"ok": True, "data": js_keyframes}))
        else:
            js_code = """
                (function() {
                    try {
                        if (typeof getCurveKeyframes !== 'undefined') {
                            return JSON.stringify({ok: true, data: getCurveKeyframes()});
                        }
                        return JSON.stringify({ok: false, error: "getCurveKeyframes missing"});
                    } catch (e) {
                        return JSON.stringify({ok: false, error: e.toString()});
                    }
                })()
            """
            self.preview.page().runJavaScript(js_code, self._finish_apply_recent_all)

    def _finish_apply_recent_all(self, raw_js):
        """Finish apply for recent+all mode: same control, all selected nodes, all segments."""
        import json
        if not raw_js or not isinstance(raw_js, str):
            self.status_lbl.setText("No keyframes from preview")
            return
        try:
            parsed = json.loads(raw_js)
        except Exception:
            self.status_lbl.setText("Failed to parse JS output")
            return
        if not parsed.get("ok"):
            self.status_lbl.setText(f"JS Error: {parsed.get('error', 'Unknown')[:30]}")
            return
        js_keyframes = parsed.get("data", [])
        if not js_keyframes or len(js_keyframes) < 2:
            self.status_lbl.setText("No keyframes from preview")
            return

        result = self.core.apply_recent_all(js_keyframes)
        if result["ok"]:
            total = result.get("total_segments", 0)
            tools = result.get("tools", 0)
            ctrl = result.get("input_name", "control")
            self.status_lbl.setText(
                f"Applied to {total} segments on '{ctrl}' ({tools} tools)"
            )
        else:
            self.status_lbl.setText(f"Failed: {result.get('error', 'Unknown')}")

    def _on_apply_all_custom(self):
        """Gather JS keyframes and start all+custom retime+apply."""
        if self.core.is_handle_mode():
            js_keyframes = [
                {"t": 0, "v": 0, "rh": dict(self.core.manual_rh)},
                {"t": 1, "v": 1, "lh": dict(self.core.manual_lh)}
            ]
            import json
            self._finish_apply_all_custom(json.dumps({"ok": True, "data": js_keyframes}))
        else:
            js_code = """
                (function() {
                    try {
                        if (typeof getCurveKeyframes !== 'undefined') {
                            return JSON.stringify({ok: true, data: getCurveKeyframes()});
                        }
                        return JSON.stringify({ok: false, error: "getCurveKeyframes missing"});
                    } catch (e) {
                        return JSON.stringify({ok: false, error: e.toString()});
                    }
                })()
            """
            self.preview.page().runJavaScript(js_code, self._finish_apply_all_custom)

    def _finish_apply_all_custom(self, raw_js):
        """Finish apply for all+custom retime mode."""
        from PySide6.QtWidgets import QMessageBox
        import json
        if not raw_js or not isinstance(raw_js, str):
            self.status_lbl.setText("No keyframes from preview")
            return
        try:
            parsed = json.loads(raw_js)
        except Exception:
            self.status_lbl.setText("Failed to parse JS output")
            return
        if not parsed.get("ok"):
            self.status_lbl.setText(f"JS Error: {parsed.get('error', 'Unknown')[:30]}")
            return
        js_keyframes = parsed.get("data", [])
        if not js_keyframes or len(js_keyframes) < 2:
            self.status_lbl.setText("No keyframes from preview")
            return

        custom_start = self.core.start_frame
        custom_end = self.core.end_frame

        result = self.core.apply_retime_all(js_keyframes, custom_start, custom_end)
        if result["ok"]:
            total = result.get("tools", 0)
            ctrl = result.get("input_name", "control")
            old_l = int(result.get("old_left_frame", custom_start))
            old_r = int(result.get("old_right_frame", custom_end))
            self.status_lbl.setText(
                f"Retimed '{ctrl}' [{old_l}–{old_r}] → [{int(custom_start)}–{int(custom_end)}]"
                f" on {total} node(s)"
            )
        else:
            # Show detailed error in a dialog so the user can read it in full
            error_msg = result.get("error", "Unknown error")
            QMessageBox.warning(self, "All + Custom Range — Conditions Not Met", error_msg)
            self.status_lbl.setText("All+Custom: conditions not met")

    def _on_apply_all_at_playhead(self):
        """Apply to every animated input of every selected node, but only the segment at playhead."""
        if self.core.is_handle_mode():
            js_keyframes = [
                {"t": 0, "v": 0, "rh": dict(self.core.manual_rh)},
                {"t": 1, "v": 1, "lh": dict(self.core.manual_lh)}
            ]
            import json
            self._finish_apply_all_at_playhead(json.dumps({"ok": True, "data": js_keyframes}))
        else:
            js_code = """
                (function() {
                    try {
                        if (typeof getCurveKeyframes !== 'undefined') {
                            return JSON.stringify({ok: true, data: getCurveKeyframes()});
                        }
                        return JSON.stringify({ok: false, error: "getCurveKeyframes missing"});
                    } catch (e) {
                        return JSON.stringify({ok: false, error: e.toString()});
                    }
                })()
            """
            self.preview.page().runJavaScript(js_code, self._finish_apply_all_at_playhead)

    def _finish_apply_all_at_playhead(self, raw_js):
        import json
        if not raw_js or not isinstance(raw_js, str):
            self.status_lbl.setText("No keyframes from preview")
            return
        try:
            parsed = json.loads(raw_js)
        except Exception:
            self.status_lbl.setText("Failed to parse JS output")
            return
        if not parsed.get("ok"):
            self.status_lbl.setText(f"JS Error: {parsed.get('error', 'Unknown')[:30]}")
            return
        js_keyframes = parsed.get("data", [])
        if not js_keyframes or len(js_keyframes) < 2:
            self.status_lbl.setText("No keyframes from preview")
            return
        result = self.core.apply_all_at_playhead(js_keyframes)
        if result.get("ok"):
            total = result.get("total_segments", 0)
            tools = result.get("tools", 0)
            self.status_lbl.setText(f"Applied to {total} segments at playhead ({tools} tools)")
        else:
            self.status_lbl.setText(f"Failed: {result.get('error', 'Unknown')}")

    def _on_apply_recent_all_at_playhead(self):
        """Apply to recently-changed control on all selected nodes, only the segment at playhead."""
        if self.core.is_handle_mode():
            js_keyframes = [
                {"t": 0, "v": 0, "rh": dict(self.core.manual_rh)},
                {"t": 1, "v": 1, "lh": dict(self.core.manual_lh)}
            ]
            import json
            self._finish_apply_recent_all_at_playhead(json.dumps({"ok": True, "data": js_keyframes}))
        else:
            js_code = """
                (function() {
                    try {
                        if (typeof getCurveKeyframes !== 'undefined') {
                            return JSON.stringify({ok: true, data: getCurveKeyframes()});
                        }
                        return JSON.stringify({ok: false, error: "getCurveKeyframes missing"});
                    } catch (e) {
                        return JSON.stringify({ok: false, error: e.toString()});
                    }
                })()
            """
            self.preview.page().runJavaScript(js_code, self._finish_apply_recent_all_at_playhead)

    def _finish_apply_recent_all_at_playhead(self, raw_js):
        import json
        if not raw_js or not isinstance(raw_js, str):
            self.status_lbl.setText("No keyframes from preview")
            return
        try:
            parsed = json.loads(raw_js)
        except Exception:
            self.status_lbl.setText("Failed to parse JS output")
            return
        if not parsed.get("ok"):
            self.status_lbl.setText(f"JS Error: {parsed.get('error', 'Unknown')[:30]}")
            return
        js_keyframes = parsed.get("data", [])
        if not js_keyframes or len(js_keyframes) < 2:
            self.status_lbl.setText("No keyframes from preview")
            return
        result = self.core.apply_recent_all_at_playhead(js_keyframes)
        if result.get("ok"):
            total = result.get("total_segments", 0)
            tools = result.get("tools", 0)
            ctrl = result.get("input_name", "control")
            self.status_lbl.setText(
                f"Applied to '{ctrl}' at playhead ({total} segments, {tools} tools)"
            )
        else:
            self.status_lbl.setText(f"Failed: {result.get('error', 'Unknown')}")

    def _finish_apply(self, raw_js, res):
        """Finish apply: scale JS keyframes and write to Resolve."""
        print(f"[_finish_apply] type={type(raw_js)}")
        print(f"[_finish_apply] raw_js={raw_js}")
        
        import json
        if not raw_js or not isinstance(raw_js, str):
            self.status_lbl.setText("No keyframes from preview")
            return
            
        try:
            parsed = json.loads(raw_js)
        except Exception as e:
            self.status_lbl.setText("Failed to parse JS output")
            return
            
        if not parsed.get("ok"):
            err = parsed.get("error", "Unknown JS error")
            self.status_lbl.setText(f"JS Error: {err[:20]}")
            return
            
        js_keyframes = parsed.get("data", [])
        if not js_keyframes or not isinstance(js_keyframes, list) or len(js_keyframes) < 2:
            self.status_lbl.setText("No keyframes from preview")
            return
        
        # Step 3: Apply to Resolve (unified - same for all modes)
        result = self.core.apply_to_resolve(js_keyframes)
        
        if result["ok"]:
            applied = result.get('applied', 0)
            if applied == 0:
                self.status_lbl.setText(
                    f"Applied to {res.get('spline_name', 'spline')} "
                    f"[{int(res.get('start_frame', 0))}–{int(res.get('end_frame', 0))}]"
                )
            else:
                self.status_lbl.setText(
                    f"Applied {applied} keyframes to {res.get('spline_name', 'spline')} "
                    f"[{int(res.get('start_frame', 0))}–{int(res.get('end_frame', 0))}]"
                )
        else:
            self.status_lbl.setText(f"Failed: {result.get('error', 'Unknown')}")
    
    def _apply_physics_tail(self, res):
        """Apply physics curve as tail after kf2, getting keyframes from preview with edits."""
        def on_keyframes_received(keyframes):
            print(f"[_apply_physics_tail] Received keyframes from JS: {type(keyframes)}, count: {len(keyframes) if isinstance(keyframes, list) else 'N/A'}")
            
            if keyframes is None or not isinstance(keyframes, list) or len(keyframes) < 2:
                print(f"[_apply_physics_tail] JS keyframes invalid, using Python fallback")
                # Fallback: generate from Python if JS fails
                keyframes = self.core.get_physics_bezier_keyframes()
                print(f"[_apply_physics_tail] Python fallback keyframes: {len(keyframes)}")
            else:
                print(f"[_apply_physics_tail] Using JS keyframes with {len(keyframes)} points")
                # Print ALL keyframes with their handles for debugging
                for i, kf in enumerate(keyframes):
                    rh_str = f" RH=({kf.get('rh', {}).get('t', 'N/A'):.4f}, {kf.get('rh', {}).get('v', 'N/A'):.4f})" if 'rh' in kf else ""
                    lh_str = f" LH=({kf.get('lh', {}).get('t', 'N/A'):.4f}, {kf.get('lh', {}).get('v', 'N/A'):.4f})" if 'lh' in kf else ""
                    print(f"  KF[{i}]: t={kf['t']:.4f}, v={kf['v']:.4f}{rh_str}{lh_str}")
            
            result = self.core.apply_to_resolve(keyframes)
            print(f"[_apply_physics_tail] Apply result: {result}")
            if result["ok"]:
                self.status_lbl.setText(
                    f"Applied {self.core.mode} tail to {res.get('spline_name', 'spline')} "
                    f"[{int(res.get('start_frame', 0))}–{int(res.get('end_frame', 0))}]"
                )
            else:
                self.status_lbl.setText(f"Failed: {result.get('error', 'Unknown')}")
        
        # Get keyframes from preview - this includes any manual handle edits
        js_code = """
            (function() {
                try {
                    if (typeof getCurveKeyframes !== 'undefined') {
                        return getCurveKeyframes();
                    }
                    return null;
                } catch (e) {
                    return null;
                }
            })()
        """
        self.preview.page().runJavaScript(js_code, on_keyframes_received)

    def _reflow_fav_grid(self):
        self._fav_reflow_pending = False
        self._refresh_favorites()

    def _fav_num_cols(self):
        """Compute how many columns fit in the current scroll viewport width."""
        if not hasattr(self, 'fav_content_scroll'):
            return 4
        vw = self.fav_content_scroll.viewport().width()
        card_min = 90
        spacing = 8
        margins = 8  # left + right grid margins combined
        cols = max(1, (vw - margins + spacing) // (card_min + spacing))
        return cols

    def _refresh_favorites(self):
        """Refresh favorites grid with current filter and selection state."""
        # Clear grid and tracking list
        while self.fav_grid.count():
            item = self.fav_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self._fav_preset_cards = []
        theme = get_theme()
        favorites = self.library.get_all()
        
        # Filter favorites based on current view
        visible_ids = self._get_visible_favorite_ids(favorites)
        
        # Show empty state if no matches
        if not visible_ids:
            empty_msg = "No presets found"
            if self._fav_search_text:
                empty_msg = f"No presets match '{self._fav_search_text}'"
            msg = QLabel(empty_msg)
            msg.setStyleSheet(f"color: {theme.text_secondary}; font-size: 12px;")
            msg.setAlignment(Qt.AlignCenter)
            self.fav_grid.addWidget(msg, 0, 0, 1, 4)
            return
        
        num_cols = self._fav_num_cols()
        # Make all columns equal width so cards fill the available space
        for c in range(num_cols):
            self.fav_grid.setColumnStretch(c, 1)

        for display_idx, preset_id in enumerate(visible_ids):
            fav = self.library.get_by_id(preset_id)
            if not fav:
                continue
            is_selected = preset_id in self._fav_selected_ids

            card = self._build_favorite_card(fav, preset_id, is_selected)
            self._fav_preset_cards.append(card)

            row = display_idx // num_cols
            col = display_idx % num_cols
            self.fav_grid.addWidget(card, row, col)
    
    def _get_visible_favorite_ids(self, favorites):
        """Get list of preset IDs to show based on current filter and search."""
        # First apply folder/filter selection
        if self._fav_current_folder is not None:
            # Show presets in selected folder
            preset_ids = [p["id"] for p in self.library.get_by_folder(self._fav_current_folder)]
        elif self._fav_current_filter == "uncategorized":
            # Show presets not in any folder
            preset_ids = [p["id"] for p in self.library.get_by_folder(None)]
        elif self._fav_current_filter == "recent":
            # Show last 10 added
            preset_ids = [p["id"] for p in favorites[-10:]]
        else:
            # "all" or default - show all
            preset_ids = [p["id"] for p in favorites]
        
        # Then apply search filter
        if self._fav_search_text:
            search_lower = self._fav_search_text.lower()
            preset_ids = [pid for pid in preset_ids
                          if search_lower in self.library.get_by_id(pid).get("name", "").lower()]
        
        return preset_ids
    
    def _build_favorite_card(self, fav, preset_id, is_selected):
        """Build a single favorite card widget."""
        theme = get_theme()
        
        card = QFrame()
        card.setFixedHeight(85)
        card.setMinimumWidth(80)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setObjectName("FavCard")
        card._preset_id = preset_id
        card._is_selected = is_selected
        
        # Selection border color: #4CAF50 (green)
        selection_color = "#4CAF50"
        
        if is_selected:
            card.setStyleSheet(f"""
                #FavCard {{
                    background-color: {theme.bg_card};
                    border: 3px solid {selection_color};
                    border-radius: {theme.border_radius}px;
                }}
            """)
        else:
            card.setStyleSheet(f"""
                #FavCard {{
                    background-color: {theme.bg_card};
                    border: {theme.border_width}px solid {theme.border_color};
                    border-radius: {theme.border_radius}px;
                }}
                #FavCard:hover {{
                    border-color: {theme.accent};
                }}
            """)
        
        vlay = QVBoxLayout(card)
        vlay.setContentsMargins(4, 4, 4, 4)
        vlay.setSpacing(2)
        vlay.setAlignment(Qt.AlignCenter)
        
        # Generate preview points based on saved data
        points = self._get_preset_preview_points(fav)
        mini = MiniCurveWidget(points)
        mini.setFixedSize(70, 40)
        # Disable MiniCurveWidget click handling - let card handle it
        mini.clicked = None
        mini.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        
        name_lbl = QLabel(fav.get("name", "Unnamed")[:14])
        name_lbl.setStyleSheet(f"color: {theme.text_primary}; font-size: 9px;")
        name_lbl.setAlignment(Qt.AlignCenter)
        
        vlay.addWidget(mini)
        vlay.addWidget(name_lbl)
        
        # Mouse events for click and drag - attach to card
        card._fav_card_preset_id = preset_id
        card.mousePressEvent = lambda e, c=card: self._on_fav_card_mouse_press(e, c)
        card.mouseMoveEvent = lambda e, c=card: self._on_fav_card_mouse_move(e, c)
        
        return card
    
    def _on_fav_card_mouse_press(self, event, card):
        """Handle mouse press on favorite card."""
        if event.button() == Qt.LeftButton:
            card._fav_drag_start_pos = event.pos()
            self._on_fav_card_clicked(card._fav_card_preset_id, event)
    
    def _on_fav_card_mouse_move(self, event, card):
        """Handle mouse move on favorite card - initiate drag."""
        if not hasattr(card, '_fav_drag_start_pos'):
            return
        
        if event.buttons() != Qt.LeftButton:
            return
        
        # Check if drag distance is enough
        if (event.pos() - card._fav_drag_start_pos).manhattanLength() < 10:
            return
        
        # Start drag
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"preset:{card._fav_card_preset_id}")
        drag.setMimeData(mime_data)
        
        # Create drag pixmap (simple representation)
        drag.exec(Qt.MoveAction)
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # FAVORITES PAGE - FOLDER & FILE MANAGEMENT METHODS
    # ═══════════════════════════════════════════════════════════════════════════════
    
    def _on_folder_clicked(self, folder_id, btn):
        """Handle folder selection - simple single select."""
        # Uncheck filter buttons
        sidebar = btn.parent().parent()
        for child in sidebar.findChildren(QPushButton):
            if child.property("filter_key"):
                child.setChecked(False)
                child.setStyleSheet(self._get_sidebar_item_style(False))
        
        # Uncheck other folder buttons
        for child in self.sidebar_folders_container.findChildren(QPushButton):
            if child.property("folder_id"):
                child.setChecked(False)
                child.setStyleSheet(self._get_folder_button_style(False))
                tc = child.property("tab_color")
                if tc:
                    child.setIcon(self._make_folder_icon(tc, active=False))

        # Check this button
        btn.setChecked(True)
        btn.setStyleSheet(self._get_folder_button_style(True))
        tc = btn.property("tab_color")
        if tc:
            btn.setIcon(self._make_folder_icon(tc, active=True))
        
        self._fav_current_folder = folder_id
        self._fav_current_filter = None
        self._clear_fav_selection()
        self._refresh_favorites()
        
        # Show folder name in status
        folder = self.library.get_folder(folder_id)
        if folder:
            self.status_lbl.setText(f"Browsing: {folder['name']}")
    
    def _on_folder_drag_enter(self, event, btn):
        """Handle drag enter on folder."""
        if event.mimeData().hasText() and event.mimeData().text().startswith("preset:"):
            theme = get_theme()
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {theme.accent}40;
                    border: {theme.highlight_border_width}px solid {theme.accent};
                    border-radius: 6px;
                    padding: 8px 12px;
                    text-align: left;
                    font-size: 11px;
                }}
            """)
            event.acceptProposedAction()
    
    def _on_folder_drag_leave(self, event, btn):
        """Handle drag leave from folder."""
        is_default = btn.property("is_default") or False
        btn.setStyleSheet(self._get_folder_button_style(btn.isChecked(), 0, is_default))
    
    def _on_folder_drop(self, event, folder_id):
        """Handle drop on folder."""
        _linked_sections = {"Easing", "Dynamic", "Special"}
        data = event.mimeData().text()
        if data.startswith("preset:"):
            preset_id = data.split(":", 1)[1]
            preset = self.library.get_by_id(preset_id)
            if preset:
                # Sync: remove from old linked section if applicable
                old_folder_id = self.library.get_folder_for_preset(preset_id)
                if old_folder_id:
                    old_folder = self.library.get_folder(old_folder_id)
                    if old_folder and old_folder.get("is_default") and old_folder.get("name") in _linked_sections:
                        self.library.remove_section(preset_id, old_folder["name"])
                # Move to new folder
                self.library.move_to_folder(preset_id, folder_id)
                # Sync: add to new linked section if applicable
                new_folder = self.library.get_folder(folder_id)
                if new_folder and new_folder.get("is_default") and new_folder.get("name") in _linked_sections:
                    self.library.add_section(preset_id, new_folder["name"])
                self._refresh_all_pages()
                self.status_lbl.setText("Moved preset to folder")
        event.acceptProposedAction()
    
    def _on_new_folder_clicked(self):
        """Create a new folder."""
        folder_id = self.library.create_folder("New Folder")
        self._refresh_sidebar_folders()
        
        # Find and trigger rename on the new folder
        for child in self.sidebar_folders_container.findChildren(QPushButton):
            if child.property("folder_id") == folder_id:
                self._start_folder_rename(folder_id, child)
                break
        
        self.status_lbl.setText("Created new folder")
    
    def _start_folder_rename(self, folder_id, btn):
        """Start inline rename of a folder."""
        folder = self.library.get_folder(folder_id)
        if not folder:
            return
        
        theme = get_theme()
        
        # Create a popup dialog that stays on top
        dialog = QDialog(self)
        dialog.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        dialog.setAttribute(Qt.WA_TranslucentBackground)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        
        edit = QLineEdit(folder["name"])
        edit.setStyleSheet(f"""
            QLineEdit {{
                background: {theme.bg_input};
                color: {theme.text_primary};
                border: {theme.highlight_border_width}px solid {theme.accent};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 11px;
                min-width: 120px;
            }}
        """)
        layout.addWidget(edit)
        
        # Position dialog near button
        dialog.move(btn.mapToGlobal(btn.rect().topLeft()))
        dialog.show()
        edit.selectAll()
        edit.setFocus()
        
        def finish_rename():
            new_name = edit.text().strip()
            if new_name:
                self.library.rename_folder(folder_id, new_name)
                self._refresh_sidebar_folders()
            dialog.accept()
        
        def cancel_rename():
            dialog.reject()
        
        edit.returnPressed.connect(finish_rename)
        edit.editingFinished.connect(cancel_rename)
        dialog.exec()
    
    def _update_search_style(self):
        """Update search bar style when theme changes."""
        theme = get_theme()
        self.fav_search_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {theme.bg_input};
                color: {theme.text_primary};
                border: 1px solid {theme.border_color};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border-color: {theme.accent};
            }}
        """)
    
    def _on_fav_search_changed(self, text):
        """Handle search text changes - filter favorites grid."""
        self._fav_search_text = text.strip().lower()
        self._refresh_favorites()
    
    def _on_fav_load_clicked(self):
        """Handle Load button - import presets/folder from file."""
        from PySide6.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Folder / Presets",
            "",
            "JSON Files (*.json);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            
            # Handle new folder bundle format
            if isinstance(data, dict) and data.get("format") == "reveace_favorites_folder":
                folder_data = data.get("folder", {})
                presets_to_import = folder_data.get("presets", [])
                folder_name = folder_data.get("name", "Imported Folder")
            elif isinstance(data, list):
                presets_to_import = data
                file_name = os.path.splitext(os.path.basename(file_path))[0]
                folder_name = f"Imported: {file_name}"
            elif isinstance(data, dict) and "favorites" in data:
                presets_to_import = data["favorites"]
                file_name = os.path.splitext(os.path.basename(file_path))[0]
                folder_name = f"Imported: {file_name}"
            else:
                presets_to_import = [data]
                file_name = os.path.splitext(os.path.basename(file_path))[0]
                folder_name = f"Imported: {file_name}"
            
            # Validate presets
            presets_to_import = [p for p in presets_to_import if isinstance(p, dict) and "name" in p]
            
            if not presets_to_import:
                self.status_lbl.setText("No valid presets found in file")
                return
            
            # Make folder name unique if needed
            existing_names = {f["name"] for f in self.library.get_all_folders()}
            original_name = folder_name
            counter = 1
            while folder_name in existing_names:
                folder_name = f"{original_name} ({counter})"
                counter += 1
            
            # Import presets
            for preset in presets_to_import:
                # Generate new ID and add to library
                self.library.add(
                    name=preset.get("name", "Imported"),
                    mode=preset.get("mode", "bezier"),
                    params=preset.get("params", {}),
                    direction=preset.get("direction", "out"),
                    sections=preset.get("sections", []),
                    folder_id=None,
                    source=preset.get("source", "user"),
                    preset_ref=preset.get("preset"),
                )
            
            # Create folder and assign newly-imported presets to it
            folder_id = self.library.create_folder(folder_name)
            for preset in self.library.get_all():
                if preset.get("source") != "built_in" and not preset.get("folder_id"):
                    # Check if this is one we just imported (by name match)
                    imported_names = {p.get("name") for p in presets_to_import}
                    if preset.get("name") in imported_names:
                        self.library.move_to_folder(preset["id"], folder_id)
            
            self._refresh_sidebar_folders()
            self._refresh_favorites()
            
            # Auto-select the imported folder
            self._on_folder_clicked(folder_id, self._fav_folder_buttons.get(folder_id))
            
            self.status_lbl.setText(f"Imported {len(presets_to_import)} presets to '{folder_name}'")
            
        except Exception as e:
            self.status_lbl.setText(f"Import failed: {str(e)[:40]}")
    
    def _on_fav_save_clicked(self):
        """Handle Save button - export current folder or selected presets."""
        from PySide6.QtWidgets import QFileDialog
        
        favorites = self.library.get_all()
        
        # If viewing a specific folder, export the entire folder
        if self._fav_current_folder is not None:
            folder = self.library.get_folder(self._fav_current_folder)
            if not folder:
                self.status_lbl.setText("Current folder not found")
                return
            
            # Gather all presets in this folder
            presets_to_export = self.library.get_by_folder(self._fav_current_folder)

            if not presets_to_export:
                self.status_lbl.setText("Folder is empty — nothing to export")
                return
            
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                f"Export Folder: {folder['name']}",
                f"{folder['name']}.json",
                "JSON Files (*.json);;All Files (*.*)"
            )
            
            if not file_path:
                return
            
            try:
                export_data = {
                    "format": "reveace_favorites_folder",
                    "version": 1,
                    "folder": {
                        "name": folder["name"],
                        "presets": presets_to_export
                    }
                }
                
                with open(file_path, "w") as f:
                    json.dump(export_data, f, indent=2)
                
                self.status_lbl.setText(f"Exported folder '{folder['name']}' ({len(presets_to_export)} presets)")
                
            except Exception as e:
                self.status_lbl.setText(f"Export failed: {str(e)[:40]}")
            return
        
        # No folder selected — fall back to exporting selected presets
        if not self._fav_selected_ids:
            self.status_lbl.setText("Select a folder or presets to export")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Selected Presets",
            "favorites_export.json",
            "JSON Files (*.json);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            selected_presets = []
            for idx in sorted(self._fav_selected_ids):
                if 0 <= idx < len(favorites):
                    selected_presets.append(favorites[idx])
            
            # Wrap selected presets in the folder format for better sharing
            file_name = os.path.splitext(os.path.basename(file_path))[0]
            export_data = {
                "format": "reveace_favorites_folder",
                "version": 1,
                "folder": {
                    "name": file_name,
                    "presets": selected_presets
                }
            }
            
            with open(file_path, "w") as f:
                json.dump(export_data, f, indent=2)
            
            self.status_lbl.setText(f"Exported {len(selected_presets)} presets")
            
        except Exception as e:
            self.status_lbl.setText(f"Export failed: {str(e)[:40]}")
    
    def _on_fav_delete_clicked(self):
        """Handle Delete button."""
        self._delete_selected_favorites()
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # DRAG SELECTION (Marquee/Box Selection)
    # ═══════════════════════════════════════════════════════════════════════════════
    
    def _start_drag_selection(self, event, target_widget=None):
        """Start a drag selection (marquee/box selection). Works like native file manager."""
        from PySide6.QtWidgets import QApplication
        
        # Determine target type
        self._drag_select_target = target_widget
        is_section = False
        is_favorites = False
        is_modal = False
        
        if target_widget:
            is_section = getattr(target_widget, '_is_section_grid', False)
            is_modal = getattr(target_widget, '_is_modal_grid', False)
            
            # Check for favorites grid
            if hasattr(self, 'fav_grid_widget') and self.fav_grid_widget:
                is_favorites = (
                    target_widget is self.fav_grid_widget or 
                    (hasattr(self.fav_grid_widget, 'parent') and target_widget is self.fav_grid_widget.parent())
                )
            
            # If target is a scroll area with section, get the inner widget
            if not is_section and hasattr(target_widget, '_is_section_scroll'):
                if hasattr(target_widget, 'widget') and target_widget.widget():
                    target_widget = target_widget.widget()
                    self._drag_select_target = target_widget
                    is_section = True
        
        # Get modifier keys
        modifiers = QApplication.keyboardModifiers()
        self._drag_select_modifier = modifiers
        self._drag_select_is_section = is_section
        self._drag_select_section = getattr(target_widget, '_section_name', None) if is_section else None
        self._drag_select_is_modal = is_modal
        
        # Debug
        if is_section:
            print(f"[DragSelect] Section mode: {self._drag_select_section}")
        elif is_modal:
            print(f"[DragSelect] Modal mode")
        
        # Get viewport for coordinate mapping
        viewport = None
        if is_section:
            scroll_area = target_widget.parent()
            while scroll_area and not isinstance(scroll_area, QScrollArea):
                scroll_area = scroll_area.parent()
            if scroll_area:
                viewport = scroll_area.viewport()
        elif is_favorites and hasattr(self, 'fav_grid_widget'):
            scroll = self.fav_grid_widget.parent()
            while scroll and not isinstance(scroll, QScrollArea):
                scroll = scroll.parent()
            if scroll:
                viewport = scroll.viewport()
        elif is_modal:
            # Modal grid - find its scroll area
            scroll_area = target_widget.parent()
            while scroll_area and not isinstance(scroll_area, QScrollArea):
                scroll_area = scroll_area.parent()
            if scroll_area:
                viewport = scroll_area.viewport()
        
        self._drag_select_viewport = viewport
        self._drag_select_start_pos = viewport.mapFromGlobal(event.globalPos()) if viewport else event.pos()
        self._drag_select_active = True
        
        # Create/get overlay
        if is_favorites or is_modal:
            # Use fav_drag_overlay for both favorites and modal (both use similar single-selection logic)
            if self._fav_drag_overlay is None:
                self._fav_drag_overlay = DragSelectionOverlay(viewport)
            else:
                self._fav_drag_overlay.setParent(viewport)
            self._fav_drag_overlay.setGeometry(viewport.rect())
            self._fav_drag_overlay.show()
            self._fav_drag_overlay.raise_()
            self._fav_drag_overlay.setSelectionRect(QRect(self._drag_select_start_pos, self._drag_select_start_pos))
        else:
            if self._drag_select_overlay is None:
                self._drag_select_overlay = DragSelectionOverlay()
            if viewport:
                self._drag_select_overlay.setParent(viewport)
                self._drag_select_overlay.setGeometry(viewport.rect())
            else:
                self._drag_select_overlay.setParent(target_widget)
                self._drag_select_overlay.setGeometry(target_widget.rect())
            self._drag_select_overlay.show()
            self._drag_select_overlay.raise_()
            self._drag_select_overlay.setSelectionRect(QRect(self._drag_select_start_pos, self._drag_select_start_pos))
        
        # Handle selection state based on modifiers
        if not (modifiers & Qt.ControlModifier or modifiers & Qt.ShiftModifier):
            # No modifier: clear previous selection (lightweight — no grid rebuild)
            self._drag_select_original_selection = set()
            if is_section:
                self._clear_section_selection(self._drag_select_section)
            elif is_favorites:
                self._fav_selected_ids.clear()
                self._update_selection_counter()
                self._update_card_selection_styles()
        else:
            # Store original selection for additive/subtractive
            if is_section:
                self._drag_select_original_selection = self._get_section_selected_indices(self._drag_select_section)
            elif is_favorites:
                self._drag_select_original_selection = self._fav_selected_ids.copy()
    
    def _get_section_selected_indices(self, section_name):
        """Get indices of selected cards in a section."""
        if not section_name or not hasattr(self, '_section_preset_cards'):
            return set()
        selected = set()
        for i, card in enumerate(self._section_preset_cards.get(section_name, [])):
            if getattr(card, '_selected', False):
                selected.add(i)
        return selected
    
    def _clear_section_selection(self, section_name):
        """Clear selection in a section."""
        if not section_name or not hasattr(self, '_section_preset_cards'):
            return
        for card in self._section_preset_cards.get(section_name, []):
            if getattr(card, '_selected', False):
                card._selected = False
                self._update_preset_card_style(card)
    
    def _update_drag_selection(self, event, target_widget=None):
        """Update the drag selection rectangle."""
        from PySide6.QtCore import QRect
        
        if not self._drag_select_active:
            return
        
        # Get overlay - favorites and modal use fav_drag_overlay, sections use drag_select_overlay
        is_favorites_or_modal = not self._drag_select_is_section
        overlay = self._fav_drag_overlay if is_favorites_or_modal else self._drag_select_overlay
        
        if overlay is None:
            return
        
        # Check overlay still exists
        try:
            overlay.parent()
        except RuntimeError:
            self._drag_select_active = False
            return
        
        # Get current position in viewport coordinates
        viewport = getattr(self, '_drag_select_viewport', None)
        if viewport:
            current_pos = viewport.mapFromGlobal(event.globalPos())
        else:
            current_pos = event.pos()
        
        # Update selection rect
        rect = QRect(self._drag_select_start_pos, current_pos).normalized()
        try:
            overlay.setSelectionRect(rect)
        except RuntimeError:
            self._drag_select_active = False
    
    def _finish_drag_selection(self, event, target_widget=None):
        """Finish drag selection and select items in the rectangle."""
        from PySide6.QtCore import QRect
        
        if not self._drag_select_active:
            return
        
        # Get overlay
        is_favorites = not self._drag_select_is_section
        overlay = self._fav_drag_overlay if is_favorites else self._drag_select_overlay
        
        # Check overlay still exists
        try:
            if overlay:
                overlay.parent()
        except RuntimeError:
            self._drag_select_active = False
            return
        
        # Get final selection rectangle
        viewport = getattr(self, '_drag_select_viewport', None)
        if viewport:
            current_pos = viewport.mapFromGlobal(event.globalPos())
        else:
            current_pos = event.pos()
        selection_rect = QRect(self._drag_select_start_pos, current_pos).normalized()
        
        # Apply selection
        if self._drag_select_is_section:
            self._finish_section_drag_selection(selection_rect)
        else:
            self._finish_favorites_drag_selection(selection_rect)
        
        # Cleanup
        try:
            if overlay:
                overlay.hide()
                overlay.setSelectionRect(QRect())
        except RuntimeError:
            pass
        
        self._drag_select_active = False
        self._drag_select_start_pos = None
        self._drag_select_modifier = None
        self._drag_select_target = None
        self._drag_select_is_section = False
        self._drag_select_is_modal = False
        self._drag_select_section = None
        self._drag_select_viewport = None
    
    def _finish_section_drag_selection(self, selection_rect):
        """Finish drag selection for section grids (Easing/Dynamic/Special)."""
        section_name = self._drag_select_section
        if not section_name or not hasattr(self, '_section_preset_cards'):
            return
        
        cards = self._section_preset_cards.get(section_name, [])
        if not cards:
            return
        
        # Find cards that intersect with selection rectangle
        newly_selected = set()
        for i, card in enumerate(cards):
            if selection_rect.intersects(card.geometry()):
                newly_selected.add(i)
        
        if not newly_selected:
            return
        
        # Apply selection based on modifier (like native file manager)
        modifiers = self._drag_select_modifier
        
        if modifiers & Qt.ControlModifier:
            # Ctrl: Toggle selection (add if not selected, remove if selected)
            for idx in newly_selected:
                cards[idx]._selected = not cards[idx]._selected
                self._update_preset_card_style(cards[idx])
        elif modifiers & Qt.ShiftModifier:
            # Shift: Add to existing selection
            for idx in newly_selected:
                cards[idx]._selected = True
                self._update_preset_card_style(cards[idx])
        else:
            # No modifier: Replace selection
            for card in cards:
                if card._selected:
                    card._selected = False
                    self._update_preset_card_style(card)
            for idx in newly_selected:
                cards[idx]._selected = True
                self._update_preset_card_style(cards[idx])
        
        # Update anchor for shift+click range selection
        if not hasattr(self, '_shift_selection_anchor'):
            self._shift_selection_anchor = {}
        self._shift_selection_anchor[section_name] = cards[max(newly_selected)]
        
        # Show status
        count = sum(1 for c in cards if c._selected)
        self.status_lbl.setText(f"Selected {count} preset{'s' if count > 1 else ''}")
    
    def _finish_favorites_drag_selection(self, selection_rect):
        """Finish drag selection for favorites grid."""
        if not hasattr(self, 'fav_grid_widget') or not self.fav_grid_widget:
            return
        
        # Calculate scroll offset
        scroll_offset = QPoint(0, 0)
        scroll = self.fav_grid_widget.parent()
        while scroll and not isinstance(scroll, QScrollArea):
            scroll = scroll.parent()
        if scroll:
            scroll_offset = QPoint(scroll.horizontalScrollBar().value(), 
                                   scroll.verticalScrollBar().value())
        
        # Find cards that intersect with selection rectangle
        newly_selected = set()
        for card in self._fav_preset_cards:
            # Convert card geometry to viewport coordinates
            card_rect_viewport = card.geometry().translated(-scroll_offset.x(), -scroll_offset.y())
            if selection_rect.intersects(card_rect_viewport):
                if hasattr(card, '_fav_card_index'):
                    newly_selected.add(card._fav_card_index)
        
        if not newly_selected:
            return
        
        # Apply selection based on modifier (like native file manager)
        modifiers = self._drag_select_modifier
        
        if modifiers & Qt.ControlModifier:
            # Ctrl: Toggle selection
            for idx in newly_selected:
                if idx in self._fav_selected_ids:
                    self._fav_selected_ids.discard(idx)
                else:
                    self._fav_selected_ids.add(idx)
        elif modifiers & Qt.ShiftModifier:
            # Shift: Add to selection
            self._fav_selected_ids.update(newly_selected)
        else:
            # No modifier: Replace selection
            self._fav_selected_ids = newly_selected
        
        # Update UI — only repaint card borders, don't rebuild grid (prevents scroll jump + glitch)
        self._update_selection_counter()
        self._update_card_selection_styles()

        count = len(self._fav_selected_ids)
        self.status_lbl.setText(f"Selected {count} preset{'s' if count > 1 else ''}")

    def _finish_modal_drag_selection(self, event, target_widget):
        """Finish drag selection for modal grid (Add Preset dialog) - multi-select."""
        from PySide6.QtCore import QRect
        
        if not self._drag_select_active:
            return
        
        # Get overlay
        overlay = self._fav_drag_overlay
        
        # Check overlay still exists
        try:
            if overlay:
                overlay.parent()
        except RuntimeError:
            self._drag_select_active = False
            return
        
        # Get final selection rectangle
        viewport = getattr(self, '_drag_select_viewport', None)
        if viewport:
            current_pos = viewport.mapFromGlobal(event.globalPos())
        else:
            current_pos = event.pos()
        selection_rect = QRect(self._drag_select_start_pos, current_pos).normalized()
        
        # Get scroll area and offset
        scroll_offset = QPoint(0, 0)
        scroll = target_widget.parent() if target_widget else None
        while scroll and not isinstance(scroll, QScrollArea):
            scroll = scroll.parent()
        if scroll:
            scroll_offset = QPoint(scroll.horizontalScrollBar().value(), 
                                   scroll.verticalScrollBar().value())
        
        # Convert selection rect to widget coordinates (accounting for scroll)
        selection_rect_in_widget = selection_rect.translated(scroll_offset)
        
        # Get modifier keys
        modifiers = self._drag_select_modifier
        ctrl_pressed = modifiers & Qt.ControlModifier if modifiers else False
        shift_pressed = modifiers & Qt.ShiftModifier if modifiers else False
        
        if not (ctrl_pressed or shift_pressed):
            # No modifier: Clear previous selection first
            self._modal_selected_presets.clear()
            for c, f, p in self._modal_all_cards:
                c._is_selected = False
                theme = get_theme()
                c.setStyleSheet(f"""
                    QFrame {{ background: {theme.bg_card}; border: {theme.border_width}px solid {theme.border_color}; 
                        border-radius: {theme.border_radius}px; }}
                    QFrame:hover {{ border-color: {theme.accent}; }}
                """)
        
        # Find cards that intersect with selection rectangle
        found_cards = []
        for card, fav, preset_name in self._modal_all_cards:
            if selection_rect_in_widget.intersects(card.geometry()):
                found_cards.append((card, fav))
        
        # Select all found cards
        for card, fav in found_cards:
            card._is_selected = True
            if fav not in self._modal_selected_presets:
                self._modal_selected_presets.append(fav)
            theme = get_theme()
            card.setStyleSheet(f"""
                QFrame {{ background: {theme.bg_card}; border: 3px solid #4CAF50; 
                    border-radius: {theme.border_radius}px; }}
            """)
        
        # Update last selected
        if found_cards:
            self._modal_last_selected_idx = found_cards[-1][0]._display_idx
        
        # UPDATE BUTTON AND STATUS LABEL (was missing!)
        count = len(self._modal_selected_presets)
        self._modal_btn_add.setEnabled(count > 0)
        if count == 1:
            self._modal_status_lbl.setText(f"Selected: {self._modal_selected_presets[0].get('name', 'Unnamed')}")
        elif count > 1:
            self._modal_status_lbl.setText(f"Selected: {count} presets")
        else:
            self._modal_status_lbl.setText("Select preset(s)...")
        
        # Cleanup
        try:
            if overlay:
                overlay.hide()
                overlay.setSelectionRect(QRect())
        except RuntimeError:
            pass
        
        self._drag_select_active = False
        self._drag_select_start_pos = None
        self._drag_select_modifier = None
        self._drag_select_target = None
        self._drag_select_is_section = False
        self._drag_select_is_modal = False
        self._drag_select_section = None
        self._drag_select_viewport = None
    
    def _clear_fav_selection(self):
        """Clear all selected favorites."""
        self._fav_selected_ids.clear()
        self._fav_last_selected = None
        self._update_selection_counter()
        self._refresh_favorites()
    
    def _update_card_selection_styles(self):
        """Repaint only the card border styles to reflect current selection — no grid rebuild."""
        theme = get_theme()
        selection_color = "#4CAF50"
        for card in self._fav_preset_cards:
            preset_id = getattr(card, '_preset_id', None)
            is_sel = preset_id in self._fav_selected_ids
            if is_sel:
                card.setStyleSheet(f"""
                    #FavCard {{
                        background-color: {theme.bg_card};
                        border: 3px solid {selection_color};
                        border-radius: {theme.border_radius}px;
                    }}
                """)
            else:
                card.setStyleSheet(f"""
                    #FavCard {{
                        background-color: {theme.bg_card};
                        border: {theme.border_width}px solid {theme.border_color};
                        border-radius: {theme.border_radius}px;
                    }}
                    #FavCard:hover {{ border-color: {theme.accent}; }}
                """)

    def _update_selection_counter(self):
        """Update the selection counter display."""
        count = len(self._fav_selected_ids)
        if count > 0:
            self.selection_counter.setText(f"{count} item{'s' if count > 1 else ''} selected")
            self.selection_counter.show()
        else:
            self.selection_counter.hide()
    
    def _delete_selected_favorites(self):
        """Delete selected favorites with confirmation for >3 items."""
        if not self._fav_selected_ids:
            return
        
        count = len(self._fav_selected_ids)
        
        # Confirm if more than 3 items
        if count > 3:
            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Delete {count} presets?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        # Filter out non-deletable (built-in) presets
        deletable_ids = []
        for preset_id in self._fav_selected_ids:
            preset = self.library.get_by_id(preset_id)
            if preset and preset.get("deletable", True):
                deletable_ids.append(preset_id)
        
        skipped = count - len(deletable_ids)
        if skipped > 0:
            self.status_lbl.setText(f"Skipped {skipped} built-in preset(s)")
        
        if deletable_ids:
            self.library.remove_multiple(deletable_ids)
            self._clear_fav_selection()
            self._refresh_all_pages()
            self.status_lbl.setText(f"Deleted {len(deletable_ids)} preset{'s' if len(deletable_ids) > 1 else ''}")
    
    def _start_fav_rename(self, preset_id):
        """Start inline rename of a favorite preset."""
        preset = self.library.get_by_id(preset_id)
        if not preset:
            return
        
        self._fav_rename_in_progress = True
        
        # Find the card for this preset_id
        for card in self._fav_preset_cards:
            if getattr(card, '_preset_id', None) == preset_id:
                self._show_inline_rename(card, preset_id)
                break
    
    def _show_inline_rename(self, card, preset_id):
        """Show inline rename editor on a card."""
        preset = self.library.get_by_id(preset_id)
        if not preset:
            return
        
        current_name = preset.get("name", "Unnamed")
        theme = get_theme()
        
        edit = QLineEdit(current_name)
        # WindowStaysOnTopHint keeps the floating edit above the main window on Windows
        edit.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        edit.setStyleSheet(f"""
            QLineEdit {{
                background: {theme.bg_input};
                color: {theme.text_primary};
                border: {theme.highlight_border_width}px solid {theme.accent};
                border-radius: 4px;
                padding: 2px 4px;
                font-size: 9px;
            }}
        """)
        edit.setFixedWidth(card.width() - 16)

        # Position over the card's name label
        card_layout = card.layout()
        if card_layout and card_layout.count() > 1:
            label_widget = card_layout.itemAt(1).widget()
            if label_widget:
                edit.move(label_widget.mapToGlobal(label_widget.rect().topLeft()))
        else:
            edit.move(card.mapToGlobal(card.rect().center()) - QPoint(card.width()//2 - 8, 10))

        edit.show()
        edit.selectAll()
        edit.setFocus()
        
        def finish_rename():
            new_name = edit.text().strip()
            if new_name and new_name != current_name:
                self.library.rename(preset_id, new_name)
                self._refresh_all_pages()
            self._fav_rename_in_progress = False
            edit.deleteLater()
        
        def cancel_rename():
            self._fav_rename_in_progress = False
            edit.deleteLater()
        
        edit.returnPressed.connect(finish_rename)
        edit.editingFinished.connect(cancel_rename)
    
    def _on_fav_copy(self):
        """Copy selected presets to clipboard."""
        if not self._fav_selected_ids:
            return
        
        presets_to_copy = []
        for preset_id in self._fav_selected_ids:
            preset = self.library.get_by_id(preset_id)
            if preset:
                presets_to_copy.append(dict(preset))
        
        self._fav_clipboard = {
            "action": "copy",
            "presets": presets_to_copy,
            "source_folder": self._fav_current_folder
        }
        
        count = len(presets_to_copy)
        self.status_lbl.setText(f"Copied {count} preset{'s' if count > 1 else ''}")
    
    def _on_fav_cut(self):
        """Cut selected presets to clipboard."""
        if not self._fav_selected_ids:
            return

        presets_to_cut = []
        preset_ids = list(self._fav_selected_ids)
        for preset_id in preset_ids:
            preset = self.library.get_by_id(preset_id)
            if preset:
                presets_to_cut.append(dict(preset))

        self._fav_clipboard = {
            "action": "cut",
            "presets": presets_to_cut,
            "preset_ids": preset_ids,
            "source_folder": self._fav_current_folder
        }

        count = len(presets_to_cut)
        self.status_lbl.setText(f"Cut {count} preset{'s' if count > 1 else ''}")
        self._refresh_favorites()
    
    def _on_fav_paste(self):
        """Paste presets from clipboard to current folder in Favorites."""
        if not self._fav_clipboard or not self._fav_clipboard["presets"]:
            return

        clipboard = self._fav_clipboard
        presets = clipboard["presets"]
        target_folder = self._fav_current_folder

        # For cut: delete originals first, then add copies
        if clipboard["action"] == "cut" and "preset_ids" in clipboard:
            preset_ids = clipboard["preset_ids"]
            self.library.remove_multiple(preset_ids)
            self._fav_clipboard = None

        for preset in presets:
            self.library.add(
                name=preset.get("name", "Copy"),
                mode=preset.get("mode", "bezier"),
                params=preset.get("params", {}),
                direction=preset.get("direction", "out"),
                sections=preset.get("sections", []),
                folder_id=target_folder,
                source=preset.get("source", "user"),
                preset_ref=preset.get("preset"),
            )
        self._clear_fav_selection()
        self._refresh_favorites()
        self._refresh_sidebar_folders()
        count = len(presets)
        self.status_lbl.setText(f"Pasted {count} preset{'s' if count > 1 else ''} to Favorites")

    def _paste_to_section(self):
        """Paste presets from clipboard to current section (Bezier/Elastic/Bounce)."""
        if not self._fav_clipboard or not self._fav_clipboard["presets"]:
            self.status_lbl.setText("Clipboard is empty")
            return
        
        # Determine current section based on tab
        section_name = None
        if self._current_tab_idx == 0:
            # Bezier page - use current heading
            section_map = {0: "Easing", 1: "Dynamic", 2: "Special"}
            section_name = section_map.get(self._current_heading_idx)
        elif self._current_tab_idx == 1:
            section_name = "Elastic"
        elif self._current_tab_idx == 2:
            section_name = "Bounce"
        
        if not section_name:
            self.status_lbl.setText("Cannot paste here")
            return
        
        clipboard = self._fav_clipboard
        presets = clipboard["presets"]
        
        added = 0
        skipped = 0
        for preset in presets:
            preset_id = preset.get("id")
            if not preset_id:
                continue
            
            # Check if already exists in section
            existing_ids = {p["id"] for p in self.library.get_by_section(section_name)}
            if preset_id in existing_ids:
                skipped += 1
                continue
            
            # Add to section
            if self.library.add_section(preset_id, section_name):
                added += 1
        
        # Refresh the section grid to show new presets
        if added > 0:
            self._refresh_section_grid(section_name)
        
        # Status message
        if added > 0 and skipped > 0:
            self.status_lbl.setText(f"Added {added} to {section_name}, {skipped} already existed")
        elif added > 0:
            self.status_lbl.setText(f"Added {added} preset{'s' if added > 1 else ''} to {section_name}")
        elif skipped > 0:
            self.status_lbl.setText(f"All presets already exist in {section_name}")
        else:
            self.status_lbl.setText("Nothing to paste")
    
    def _sample_bezier_curve(self, rh, lh, steps=50):
        """Sample a cubic bezier curve from handle positions."""
        # Control points: p0=(0,0), p1=(rh.t, rh.v), p2=(lh.t, lh.v), p3=(1,1)
        p0 = (0.0, 0.0)
        p1 = (rh.get("t", 0.33), rh.get("v", 0.0))
        p2 = (lh.get("t", 0.67), lh.get("v", 1.0))
        p3 = (1.0, 1.0)
        
        points = []
        for i in range(steps + 1):
            t = i / steps
            # Cubic bezier formula
            mt = 1.0 - t
            x = mt*mt*mt*p0[0] + 3*mt*mt*t*p1[0] + 3*mt*t*t*p2[0] + t*t*t*p3[0]
            y = mt*mt*mt*p0[1] + 3*mt*mt*t*p1[1] + 3*mt*t*t*p2[1] + t*t*t*p3[1]
            points.append({"t": x, "v": y})
        
        return points
    
    def _on_fav_card_clicked(self, preset_id, event=None):
        """Handle favorite card click - applies preset on normal click, selects on Ctrl+Click."""
        from PySide6.QtWidgets import QApplication
        
        modifiers = QApplication.keyboardModifiers() if event else Qt.NoModifier
        ctrl_pressed = modifiers & Qt.KeyboardModifier.ControlModifier
        
        if ctrl_pressed:
            # Ctrl+Click: Toggle selection only
            if preset_id in self._fav_selected_ids:
                self._fav_selected_ids.discard(preset_id)
            else:
                self._fav_selected_ids.add(preset_id)
                self._fav_last_selected = preset_id
            self._update_selection_counter()
            self._refresh_favorites()
        else:
            # Normal click: Apply the preset immediately (like other pages)
            # Selection state doesn't change on normal click
            preset = self.library.get_by_id(preset_id)
            if preset:
                self._on_card_clicked(preset_id)
            # Only clear selection if something was selected
            if self._fav_selected_ids:
                self._clear_fav_selection()
    
    def _load_favorite(self, index):
        """DEPRECATED: Use _on_card_clicked(preset_id) or _load_preset(preset) instead.
        Kept for backward compatibility."""
        preset = self.library.get_by_id(index) if isinstance(index, str) else None
        if not preset:
            # Try old index-based lookup for compatibility
            favorites = self.library.get_all()
            if 0 <= index < len(favorites):
                preset = favorites[index]
            else:
                return
        self._load_preset(preset)
        mode = preset.get("mode", "bezier")
        if mode == "elastic":
            self._switch_tab(1)
        elif mode == "bounce":
            self._switch_tab(2)
        else:
            self._switch_tab(0)
        self._trigger_auto_apply("favorite", mode=mode)
        self.status_lbl.setText(f"Applied: {preset.get('name', 'Favorite')}")

    def _on_add_favorite(self):
        """Save current curve as favorite AND add to current section."""
        name, ok = QInputDialog.getText(self, "Save Favorite", "Name:")
        if not ok or not name:
            return
        
        # Determine current section based on tab
        section_name = None
        if self._current_tab_idx == 0:
            # Bezier page - use current heading
            section_map = {0: "Easing", 1: "Dynamic", 2: "Special"}
            section_name = section_map.get(self._current_heading_idx)
        elif self._current_tab_idx == 1:
            section_name = "Elastic"
        elif self._current_tab_idx == 2:
            section_name = "Bounce"
        
        # Build sections list
        sections = [section_name] if section_name else []
        
        # Check for duplicate name in library
        existing_names = [p.get("name", "").lower() for p in self.library.get_all()]
        if name.lower() in existing_names:
            reply = QMessageBox.question(self, "Duplicate Name",
                f"A preset named '{name}' already exists.\n"
                "Do you want to continue and create a duplicate?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return
        
        # Build params based on mode
        params = dict(self.core.params)
        
        # For bezier mode, save the handle positions
        if self.core.mode == "bezier":
            params["rh"] = dict(self.core.manual_rh)
            params["lh"] = dict(self.core.manual_lh)
        
        # Determine folder
        folder_id = None
        if hasattr(self, '_fav_current_folder') and self._fav_current_folder:
            folder_id = self._fav_current_folder
        elif section_name:
            folder_id = self.library.get_default_folder_id(section_name)
        
        # Add to unified library
        preset_id = self.library.add(
            name=name,
            mode=self.core.mode,
            params=params,
            direction=self.core.direction,
            sections=sections,
            folder_id=folder_id,
            source=self.core.source,
            preset_ref=self.core.selected_preset,
        )
        
        self._refresh_all_pages()
        
        if section_name:
            self.status_lbl.setText(f"Saved '{name}' to {section_name} and Favorites")
        else:
            self.status_lbl.setText(f"Saved '{name}' to Favorites")

    def _on_del_favorite(self):
        # Show list dialog to select which to delete
        presets = self.library.get_all()
        deletable = [(p["id"], p.get("name", "Unnamed")) for p in presets if p.get("deletable", True)]
        if not deletable:
            return
        
        from PySide6.QtWidgets import QListWidget, QDialog, QVBoxLayout, QPushButton
        dialog = QDialog(self)
        dialog.setWindowTitle("Delete Favorites")
        layout = QVBoxLayout(dialog)
        
        list_widget = QListWidget()
        for _pid, name in deletable:
            list_widget.addItem(name)
        list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(list_widget)
        
        btn = QPushButton("Delete Selected")
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)
        
        if dialog.exec():
            selected_rows = [list_widget.row(item) for item in list_widget.selectedItems()]
            preset_ids = [deletable[r][0] for r in selected_rows]
            if preset_ids:
                self.library.remove_multiple(preset_ids)
                self._refresh_all_pages()

    def _on_rename_favorite(self):
        # Show list dialog to select which to rename
        presets = self.library.get_all()
        renameable = [(p["id"], p.get("name", "Unnamed")) for p in presets if p.get("deletable", True)]
        if not renameable:
            return
        
        from PySide6.QtWidgets import QListWidget, QDialog, QVBoxLayout, QPushButton
        dialog = QDialog(self)
        dialog.setWindowTitle("Rename Favorite")
        layout = QVBoxLayout(dialog)
        
        list_widget = QListWidget()
        for _pid, name in renameable:
            list_widget.addItem(name)
        layout.addWidget(list_widget)
        
        btn = QPushButton("Rename Selected")
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)
        
        if dialog.exec() and list_widget.currentRow() >= 0:
            row = list_widget.currentRow()
            preset_id = renameable[row][0]
            old_name = renameable[row][1]
            new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)
            if ok and new_name:
                self.library.rename(preset_id, new_name)
                self._refresh_all_pages()

    def _on_theme_changed(self):
        theme = get_theme()
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {theme.bg_outer}; color: {theme.text_primary}; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11px; }}
            QScrollArea {{ background: {theme.bg_outer}; border: none; }}
            QScrollBar:vertical {{ background: {theme.bg_outer}; width: 4px; }}
            QScrollBar::handle:vertical {{ background: #444; border-radius: 2px; }}
        """)
        if hasattr(self, '_current_heading_idx'):
            self._update_heading_buttons()
        self._update_nav_buttons(self.stack.currentIndex())
        
        # Update bottom strip styling
        if hasattr(self, 'bottom_strip'):
            self.bottom_strip.setStyleSheet(f"""
                QWidget {{ background-color: {theme.bg_card}; }}
                QLabel {{ color: {theme.text_primary}; font-size: 11px; background: transparent; }}
            """)
            self.lbl_in_frame.setStyleSheet(f"color: {theme.accent}; font-size: 11px; min-width: 30px;")
            self.lbl_out_frame.setStyleSheet(f"color: {theme.accent}; font-size: 11px; min-width: 30px;")
            self.lbl_dur.setStyleSheet(f"color: {theme.text_secondary}; font-size: 11px; min-width: 30px;")
        
        if self._preview_ready:
            # Update accent color and background in HTML preview
            bg_color = theme.bg_outer
            self.preview.page().runJavaScript(f"""
                if(typeof setAccentColor !== 'undefined') setAccentColor('{theme.accent}');
                if(typeof setBgColor !== 'undefined') setBgColor('{bg_color}');
            """)

    def keyPressEvent(self, event):
        # Track Shift and Control keys for bezier handle linking
        if event.key() == Qt.Key_Shift:
            self._shift_pressed = True
        if event.key() == Qt.Key_Control:
            self._ctrl_pressed = True
        
        # Handle Ctrl+ shortcuts globally
        ctrl_pressed = event.modifiers() & Qt.ControlModifier
        
        if ctrl_pressed and event.key() == Qt.Key_C:
            # Copy - works on both favorites and section pages
            if self.stack.currentIndex() == 3:
                self._on_fav_copy()
            elif self.stack.currentIndex() == 0:
                self._copy_section_selection()
            return
        elif ctrl_pressed and event.key() == Qt.Key_X:
            # Cut - works on favorites only (sections don't support cut)
            if self.stack.currentIndex() == 3:
                self._on_fav_cut()
            return
        elif ctrl_pressed and event.key() == Qt.Key_V:
            # Paste - bidirectional between Favorites and Sections
            if self.stack.currentIndex() == 3:
                # Favorites page - paste from clipboard to favorites
                self._on_fav_paste()
            elif self.stack.currentIndex() in (0, 1, 2):
                # Bezier/Elastic/Bounce page - paste to current section
                self._paste_to_section()
            else:
                # Settings page - not supported
                self.status_lbl.setText("Paste not supported here")
            return
        elif ctrl_pressed and event.key() == Qt.Key_A:
            # Select All - works on favorites and all section pages
            if self.stack.currentIndex() == 3:
                favorites = self.library.get_all()
                visible = self._get_visible_favorite_indices(favorites)
                self._fav_selected_ids = set(visible)
                self._update_selection_counter()
                self._refresh_favorites()
            elif self.stack.currentIndex() == 0:
                # Bezier page
                self._select_all_section_presets()
            elif self.stack.currentIndex() == 1:
                # Elastic page
                self._select_all_in_section("Elastic")
            elif self.stack.currentIndex() == 2:
                # Bounce page
                self._select_all_in_section("Bounce")
            return
        
        # Favorites page specific shortcuts
        if self.stack.currentIndex() == 3:
            if event.key() == Qt.Key_F2:
                if self._fav_selected_ids and len(self._fav_selected_ids) == 1:
                    idx = list(self._fav_selected_ids)[0]
                    self._start_fav_rename(idx)
                return
            elif event.key() == Qt.Key_Delete:
                self._delete_selected_favorites()
                return
            elif event.key() == Qt.Key_Escape:
                self._clear_fav_selection()
                return
        
        # Bezier/Elastic/Bounce pages - handle Delete for section preset removal
        if event.key() == Qt.Key_Delete:
            if self.stack.currentIndex() == 0:
                # Bezier page - uses heading index to determine section
                section_map = {0: "Easing", 1: "Dynamic", 2: "Special"}
                section_name = section_map.get(self._current_heading_idx)
                if section_name:
                    self._delete_selected_presets(section_name)
                return
            elif self.stack.currentIndex() == 1:
                # Elastic page
                self._delete_selected_presets("Elastic")
                return
            elif self.stack.currentIndex() == 2:
                # Bounce page
                self._delete_selected_presets("Bounce")
                return
        
        super().keyPressEvent(event)
    
    def _copy_section_selection(self):
        """Copy selected presets from current section to clipboard (for pasting to Favorites)."""
        # Determine current section based on tab
        section_name = None
        if self._current_tab_idx == 0:
            # Bezier page
            section_map = {0: "Easing", 1: "Dynamic", 2: "Special"}
            section_name = section_map.get(self._current_heading_idx)
        elif self._current_tab_idx == 1:
            section_name = "Elastic"
        elif self._current_tab_idx == 2:
            section_name = "Bounce"
        
        if not section_name:
            return
        
        # Get selected preset names
        selected_presets = []
        for card in self._section_preset_cards.get(section_name, []):
            if getattr(card, '_selected', False):
                preset_name = getattr(card, '_preset_name', None)
                if preset_name:
                    # Get preset data from core
                    preset_data = PRESETS.get(preset_name, {})
                    
                    # Create a favorite-like dict from preset
                    selected_presets.append({
                        "name": preset_name,
                        "mode": preset_data.get("mode", "bezier"),
                        "source": "preset",
                        "preset": preset_name,
                        "params": preset_data.get("params", {}),
                        "direction": preset_data.get("direction", "out")
                    })
        
        if selected_presets:
            self._fav_clipboard = {
                "action": "copy",
                "presets": selected_presets,
                "source": "section",
                "source_section": section_name
            }
            self.status_lbl.setText(f"Copied {len(selected_presets)} preset{'s' if len(selected_presets) > 1 else ''} from {section_name}")
    
    def _select_all_section_presets(self):
        """Select all presets in current section."""
        section_map = {0: "Easing", 1: "Dynamic", 2: "Special"}
        section_name = section_map.get(self._current_heading_idx)
        if not section_name:
            return
        
        for card in self._section_preset_cards.get(section_name, []):
            card._selected = True
            self._update_preset_card_style(card)
        
        count = len(self._section_preset_cards.get(section_name, []))
        self.status_lbl.setText(f"Selected {count} preset{'s' if count > 1 else ''}")
    
    def _select_all_in_section(self, section_name):
        """Select all presets in a specific section (Elastic/Bounce)."""
        if not section_name or not hasattr(self, '_section_preset_cards'):
            return
        
        for card in self._section_preset_cards.get(section_name, []):
            card._selected = True
            self._update_preset_card_style(card)
        
        count = len(self._section_preset_cards.get(section_name, []))
        self.status_lbl.setText(f"Selected {count} preset{'s' if count > 1 else ''}")
    
    def keyReleaseEvent(self, event):
        # Track Shift and Control keys for bezier handle linking
        if event.key() == Qt.Key_Shift:
            self._shift_pressed = False
        if event.key() == Qt.Key_Control:
            self._ctrl_pressed = False
        super().keyReleaseEvent(event)


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("Rev EaseSpline")
    app.setStyle("Fusion")
    core = ReveaceCore()
    window = ReveaceWindowCompact(core)
    window.show()
    sys.exit(app.exec())