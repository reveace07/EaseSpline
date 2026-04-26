"""
theme.py — Neo Brutalism UI primitives extracted from node_manager_v3.py
Self-contained, no external project dependencies.
"""

import os
import json

from PySide6.QtWidgets import (
    QApplication, QPushButton, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QCheckBox, QSlider, QSpinBox, QDoubleSpinBox,
    QFrame, QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QSize, QRect, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QRegion


# ═══════════════════════════════════════════════════════════════════════════════
# THEME MANAGER
# ═══════════════════════════════════════════════════════════════════════════════
class ThemeManager:
    STYLE_BRUTALIST = "brutalist"
    STYLE_MINIMAL = "minimal"

    THEMES = {
        "Lime": "#C5FD04",
        "Cyan": "#00D9FF",
        "Purple": "#B829DD",
        "Orange": "#FF6B35",
        "Blue": "#3B82F6",
        "Pink": "#FF0080",
        "Red": "#FF3333",
    }
    custom_color = "#C5FD04"
    SLIDER_HANDLE_SQUARE = "square"
    SLIDER_HANDLE_CIRCLE = "circle"
    SLIDER_HANDLE_NONE = "none"

    from reveace_pyside6.app_paths import get_data_dir
    SETTINGS_FILE = os.path.join(get_data_dir(), "theme_settings.json")

    def __init__(self):
        self.dark_mode = True
        self.design_style = self.STYLE_BRUTALIST
        self.border_radius = 0
        self.current_theme = "Lime"
        self.shadow_enabled = True
        self.border_width = 2
        self.highlight_border_width = 2
        self.hardware_acceleration = True
        self.slider_handle = self.SLIDER_HANDLE_CIRCLE
        self.resolve_path = ""  # DaVinci Resolve installation path
        self._listeners = []
        self._load_settings()

    def add_listener(self, callback):
        self._listeners.append(callback)

    def remove_listener(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def notify_change(self):
        dead = []
        for callback in self._listeners:
            try:
                callback()
            except RuntimeError:
                # C++ object (e.g., widget) was deleted but Python ref remains
                dead.append(callback)
        for cb in dead:
            self.remove_listener(cb)

    def _load_settings(self):
        """Load theme settings from file if it exists."""
        if os.path.exists(self.SETTINGS_FILE):
            try:
                with open(self.SETTINGS_FILE, 'r') as f:
                    data = json.load(f)
                self.dark_mode = data.get('dark_mode', self.dark_mode)
                self.design_style = data.get('design_style', self.design_style)
                self.border_radius = data.get('border_radius', self.border_radius)
                self.current_theme = data.get('current_theme', self.current_theme)
                self.shadow_enabled = data.get('shadow_enabled', self.shadow_enabled)
                self.border_width = data.get('border_width', self.border_width)
                self.highlight_border_width = data.get('highlight_border_width', self.highlight_border_width)
                self.hardware_acceleration = data.get('hardware_acceleration', self.hardware_acceleration)
                self.slider_handle = data.get('slider_handle', self.slider_handle)
                self.custom_color = data.get('custom_color', self.custom_color)
                self.resolve_path = data.get('resolve_path', self.resolve_path)
            except Exception:
                pass  # Use defaults if file is corrupt

    def _save_settings(self):
        """Save current theme settings to file."""
        try:
            data = {
                'dark_mode': self.dark_mode,
                'design_style': self.design_style,
                'border_radius': self.border_radius,
                'current_theme': self.current_theme,
                'shadow_enabled': self.shadow_enabled,
                'border_width': self.border_width,
                'highlight_border_width': self.highlight_border_width,
                'hardware_acceleration': self.hardware_acceleration,
                'slider_handle': self.slider_handle,
                'custom_color': self.custom_color,
                'resolve_path': self.resolve_path,
            }
            with open(self.SETTINGS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # Silently fail if can't write

    def set_design_style(self, style):
        self.design_style = style
        if style == self.STYLE_BRUTALIST:
            self.shadow_enabled = True
            self.border_width = 2
            # Don't reset border_radius - keep user's choice
        elif style == self.STYLE_MINIMAL:
            self.shadow_enabled = False
            self.border_width = 1
            # Don't reset border_radius - keep user's choice
        self._save_settings()
        self.notify_change()

    def set_border_radius(self, radius):
        self.border_radius = radius
        self._save_settings()
        self.notify_change()

    def set_theme(self, theme_name):
        if theme_name in self.THEMES:
            self.current_theme = theme_name
            self._save_settings()
            self.notify_change()

    def set_dark_mode(self, dark):
        self.dark_mode = dark
        self._save_settings()
        self.notify_change()

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        self.notify_change()

    def set_slider_handle(self, handle_type):
        if handle_type in [self.SLIDER_HANDLE_SQUARE, self.SLIDER_HANDLE_CIRCLE, self.SLIDER_HANDLE_NONE]:
            self.slider_handle = handle_type
            self._save_settings()
            self.notify_change()

    @property
    def accent(self):
        if self.current_theme == "Custom":
            return self.custom_color
        return self.THEMES.get(self.current_theme, "#C5FD04")

    def set_custom_color(self, color):
        self.custom_color = color
        self.current_theme = "Custom"
        self._save_settings()
        self.notify_change()

    @property
    def bg_outer(self):
        if self.design_style == self.STYLE_MINIMAL:
            return "#151515" if self.dark_mode else "#e0e0e0"
        return "#1a1a18" if self.dark_mode else "#e8e8e6"

    @property
    def bg_card(self):
        if self.design_style == self.STYLE_MINIMAL:
            return "#1f1f1f" if self.dark_mode else "#f5f5f5"
        return "#252523" if self.dark_mode else "#f0f0ee"

    @property
    def bg_input(self):
        if self.design_style == self.STYLE_MINIMAL:
            return "#1a1a1a" if self.dark_mode else "#e8e8e8"
        return "#1e1e1c" if self.dark_mode else "#d0d0ce"

    @property
    def text_primary(self):
        if self.design_style == self.STYLE_MINIMAL:
            return "#e0e0e0" if self.dark_mode else "#1a1a1a"
        return "#f0f0ee" if self.dark_mode else "#1a1a1a"

    @property
    def text_secondary(self):
        if self.design_style == self.STYLE_MINIMAL:
            return "#808080" if self.dark_mode else "#606060"
        return "#888884" if self.dark_mode else "#666664"

    @property
    def border_color(self):
        if self.design_style == self.STYLE_MINIMAL:
            return "#404040" if self.dark_mode else "#b0b0b0"
        return "#0a0a0a"

    @property
    def white(self):
        return "#f0f0ee"

    @property
    def black(self):
        return "#0a0a0a"

    @property
    def divider(self):
        if self.design_style == self.STYLE_MINIMAL:
            return "#333333" if self.dark_mode else "#dddddd"
        return "#1a1a18"

    def get_button_bg(self, variant="accent"):
        if variant == "accent":
            return self.accent
        elif variant == "white":
            return "#f0f0ee" if self.dark_mode else "#ffffff"
        elif variant == "dark":
            if self.design_style == self.STYLE_MINIMAL:
                return "#3d3d3b" if self.dark_mode else "#e0e0e0"
            return "#3d3d3b"
        return variant

    def get_button_text(self, variant="accent"):
        if variant == "accent":
            return "#0a0a0a"
        elif variant == "white":
            return "#0a0a0a"
        elif variant == "dark":
            return "#f0f0ee"
        return "#f0f0ee"


_theme_manager = None

def get_theme():
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager


# ═══════════════════════════════════════════════════════════════════════════════
# BRUTAL BUTTON
# ═══════════════════════════════════════════════════════════════════════════════
class BrutalButton(QPushButton):
    SHADOW_OFFSET = 3

    def __init__(self, text="", variant="accent", parent=None, icon_text=None):
        super().__init__(text, parent)
        self.variant = variant
        self._pressed = False
        self.icon_text = icon_text
        self.setFixedHeight(42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_text:
            self.setFont(QFont("Inter", 11, QFont.Weight.Bold))
        else:
            self.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.setContentsMargins(2, 2, 4, 4)
        get_theme().add_listener(self.on_theme_changed)
        self.on_theme_changed()
        self._scale = 1.0
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(100)
        self._anim.setEasingCurve(QEasingCurve.OutQuad)

    def on_theme_changed(self):
        self.update()

    def sizeHint(self):
        s = super().sizeHint()
        theme = get_theme()
        margin = 4
        if theme.shadow_enabled:
            return QSize(s.width() + self.SHADOW_OFFSET + margin, s.height() + self.SHADOW_OFFSET + margin)
        return QSize(s.width() + margin, s.height() + margin)

    def mousePressEvent(self, e):
        self._pressed = True
        theme = get_theme()
        if not theme.shadow_enabled:
            self._animate_press(True)
        self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._pressed = False
        theme = get_theme()
        if not theme.shadow_enabled:
            self._animate_press(False)
        self.update()
        super().mouseReleaseEvent(e)

    def _animate_press(self, pressed):
        self._scale = 0.96 if pressed else 1.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = get_theme()
        so = self.SHADOW_OFFSET if theme.shadow_enabled else 0
        scale_offset = 0
        if not theme.shadow_enabled and self._pressed:
            scale_offset = 2
        ox = so if (self._pressed and theme.shadow_enabled) else scale_offset
        oy = so if (self._pressed and theme.shadow_enabled) else scale_offset
        margin = 2
        w = self.width() - so - margin * 2
        h = self.height() - so - margin * 2
        if not theme.shadow_enabled and self._pressed:
            scale = 0.96
            new_w = int(w * scale)
            new_h = int(h * scale)
            ox += (w - new_w) // 2
            oy += (h - new_h) // 2
            w, h = new_w, new_h
        bg = QColor(theme.get_button_bg(self.variant))
        text_color = QColor(theme.get_button_text(self.variant))
        border = QColor(theme.border_color)
        radius = theme.border_radius
        if not theme.shadow_enabled and self._pressed:
            bg = bg.darker(115)
        if not self._pressed and theme.shadow_enabled:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.black))
            if radius > 0:
                p.drawRoundedRect(so + margin, so + margin, w, h, radius, radius)
            else:
                p.fillRect(so + margin, so + margin, w, h, QColor(theme.black))
        p.setBrush(bg)
        p.setPen(Qt.PenStyle.NoPen)
        if radius > 0:
            p.drawRoundedRect(ox + margin, oy + margin, w, h, radius, radius)
        else:
            p.fillRect(ox + margin, oy + margin, w, h, bg)
        pen = QPen(border, theme.border_width)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if radius > 0:
            p.drawRoundedRect(ox + margin, oy + margin, w - 1, h - 1, radius, radius)
        else:
            p.drawRect(ox + margin, oy + margin, w - 1, h - 1)
        p.setPen(text_color)
        text_x = ox + margin
        text_y = oy + margin
        if self.icon_text:
            icon_font = QFont("Segoe UI Symbol", 20)
            p.setFont(icon_font)
            icon_rect = p.boundingRect(QRect(0, 0, 0, 0), Qt.AlignmentFlag.AlignCenter, self.icon_text)
            text = self.text().upper()
            text_font = QFont("Inter", 9, QFont.Weight.Bold)
            p.setFont(text_font)
            text_rect = p.boundingRect(QRect(0, 0, 0, 0), Qt.AlignmentFlag.AlignCenter, text)
            spacing = 4
            total_width = icon_rect.width() + spacing + text_rect.width()
            center_x = text_x + w // 2
            center_y = text_y + h // 2
            icon_draw_x = center_x - total_width // 2
            icon_draw_y = center_y - icon_rect.height() // 2
            p.setFont(icon_font)
            p.drawText(icon_draw_x, icon_draw_y, icon_rect.width(), icon_rect.height(),
                      Qt.AlignmentFlag.AlignCenter, self.icon_text)
            text_draw_x = icon_draw_x + icon_rect.width() + spacing
            text_draw_y = center_y - text_rect.height() // 2
            p.setFont(text_font)
            p.drawText(text_draw_x, text_draw_y, text_rect.width(), text_rect.height(),
                      Qt.AlignmentFlag.AlignCenter, text)
        else:
            font = self.font()
            p.setFont(font)
            text_rect = QRect(text_x, text_y, w, h)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text().upper())


class IconButton(BrutalButton):
    def __init__(self, text="", variant="dark", parent=None):
        super().__init__(text, variant, parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setFixedSize(37, 37)
        self.setFont(QFont("Segoe UI", 15))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        return QSize(37, 37)

    def minimumSizeHint(self):
        return QSize(37, 37)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION CARD
# ═══════════════════════════════════════════════════════════════════════════════
class ArrowLabel(QLabel):
    def __init__(self, expanded=True, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        self.setFixedSize(14, 14)
        self.setStyleSheet("background: transparent;")
        get_theme().add_listener(self.update)

    def set_expanded(self, expanded):
        self._expanded = expanded
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(get_theme().accent))
        if self._expanded:
            points = [QPoint(2, 5), QPoint(12, 5), QPoint(7, 10)]
        else:
            points = [QPoint(4, 2), QPoint(9, 7), QPoint(4, 12)]
        p.drawPolygon(points)


class SectionHeader(QWidget):
    def __init__(self, title, expanded=True, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        self._content = None
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)
        self.arrow = ArrowLabel(expanded)
        self.title_lbl = QLabel(title)
        self._update_title_style()
        get_theme().add_listener(self._update_title_style)
        layout.addWidget(self.arrow)
        layout.addWidget(self.title_lbl)
        layout.addStretch()

    def _update_title_style(self):
        theme = get_theme()
        self.title_lbl.setStyleSheet(
            f"color: {theme.text_primary}; font-size: 12px; font-weight: bold; letter-spacing: 1px; background: transparent;"
        )

    def set_content(self, widget):
        self._content = widget
        widget.setVisible(self._expanded)

    def mousePressEvent(self, e):
        self._expanded = not self._expanded
        self.arrow.set_expanded(self._expanded)
        if self._content:
            self._content.setVisible(self._expanded)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(QPen(QColor(get_theme().divider), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class SectionCard(QWidget):
    def __init__(self, title, expanded=True, parent=None):
        super().__init__(parent)
        self._title = title
        self._expanded = expanded
        self._setup_ui()
        get_theme().add_listener(self._apply_theme)

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 8)
        outer.setSpacing(0)
        self.card = QFrame()
        self.card.setObjectName("card")
        # Enable clipping so rounded corners work properly
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        self.header = SectionHeader(self._title, self._expanded)
        card_layout.addWidget(self.header)
        self.content = QWidget()
        self.content.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(12, 10, 12, 12)
        self.content_layout.setSpacing(8)
        self.header.set_content(self.content)
        card_layout.addWidget(self.content)
        outer.addWidget(self.card)
        self._apply_theme()
        
    def _apply_theme(self):
        theme = get_theme()
        radius = theme.border_radius
        self.card.setStyleSheet(f"""
            QFrame#card {{
                background-color: {theme.bg_card};
                border: {theme.border_width}px solid {theme.border_color};
                border-radius: {radius}px;
            }}
        """)
        # Children are transparent so the card's CSS border-radius shows through cleanly
        self.content.setStyleSheet(f"""
            QWidget {{
                background-color: transparent;
                border: none;
                border-radius: 0px;
            }}
        """)
        # Clear any previous pixel mask — CSS border-radius handles rounding with AA
        if self.card:
            self.card.clearMask()

    def add(self, widget):
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)


# ═══════════════════════════════════════════════════════════════════════════════
# LABEL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def label(text, muted=False, size=11, bold=False):
    lbl = QLabel(text)
    theme = get_theme()
    color = theme.text_secondary if muted else theme.text_primary
    weight = "bold" if bold else "normal"
    actual_size = int(size * 1.05) if bold else size
    lbl.setStyleSheet(f"color: {color}; font-size: {actual_size}px; font-weight: {weight}; background: transparent;")
    return lbl


def accent_label(text, size=11):
    lbl = QLabel(text)
    theme = get_theme()
    lbl.setStyleSheet(f"color: {theme.accent}; font-size: {size}px; font-weight: bold; background: transparent;")
    return lbl


def heading_label(text, size=12):
    lbl = QLabel(text)
    theme = get_theme()
    actual_size = int(size * 1.05)
    get_theme().add_listener(lambda: lbl.setStyleSheet(
        f"color: {get_theme().text_primary}; font-size: {actual_size}px; font-weight: bold; background: transparent;"
    ))
    lbl.setStyleSheet(f"color: {theme.text_primary}; font-size: {actual_size}px; font-weight: bold; background: transparent;")
    return lbl


# ═══════════════════════════════════════════════════════════════════════════════
# STYLED COMBOBOX
# ═══════════════════════════════════════════════════════════════════════════════
class StyledCombo(QComboBox):
    def __init__(self, items, editable=False, parent=None):
        super().__init__(parent)
        self.addItems(items)
        if editable:
            self.setEditable(True)
            self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        get_theme().add_listener(self._update_style)
        self._update_style()

    def _update_style(self):
        theme = get_theme()
        radius = theme.border_radius
        bw = theme.border_width
        inner_radius = max(0, radius - bw)
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: {theme.bg_input};
                color: {theme.text_primary};
                border: {bw}px solid {theme.border_color};
                border-radius: {radius}px;
                padding: 5px 30px 5px 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QComboBox::drop-down {{
                background-color: {theme.accent};
                width: 26px;
                border: {bw}px solid {theme.accent};
                border-top: none;
                border-bottom: none;
                border-right: none;
                border-top-right-radius: {inner_radius}px;
                border-bottom-right-radius: {inner_radius}px;
                margin-top: -{bw}px;
                margin-bottom: -{bw}px;
                margin-right: -{bw}px;
                padding-top: {bw}px;
                padding-bottom: {bw}px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border: none;
                width: 0px;
                height: 0px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme.bg_input};
                color: {theme.text_primary};
                selection-background-color: {theme.accent};
                selection-color: {theme.black if not theme.dark_mode else theme.white};
                border: {bw}px solid {theme.border_color};
                border-radius: {max(0, radius - 2)}px;
                outline: none;
                padding: 2px;
            }}
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = get_theme()
        arrow_color = QColor("#0a0a0a")
        if theme.design_style == theme.STYLE_MINIMAL:
            arrow_color = QColor(theme.text_primary)
        arrow_size = 8
        dropdown_width = 24
        x = self.width() - dropdown_width + (dropdown_width - arrow_size) // 2
        y = (self.height() - arrow_size // 2) // 2
        p.setPen(QPen(arrow_color, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(x, y, x + arrow_size // 2, y + arrow_size // 2)
        p.drawLine(x + arrow_size // 2, y + arrow_size // 2, x + arrow_size, y)


def make_combo(items, editable=False):
    return StyledCombo(items, editable)


# ═══════════════════════════════════════════════════════════════════════════════
# STYLED CHECKBOX
# ═══════════════════════════════════════════════════════════════════════════════
class StyledCheckBox(QCheckBox):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        get_theme().add_listener(self._update_style)
        self._update_style()

    def _update_style(self):
        theme = get_theme()
        radius = min(theme.border_radius, 4)
        self.setStyleSheet(f"""
            QCheckBox {{
                color: {theme.text_primary};
                font-size: 11px;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: {theme.border_width}px solid {theme.border_color};
                background: {theme.bg_input};
                border-radius: {radius}px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {theme.accent};
                border-color: {theme.border_color};
            }}
        """)


def make_check(text):
    return StyledCheckBox(text)


# ═══════════════════════════════════════════════════════════════════════════════
# STYLED SPINBOXES
# ═══════════════════════════════════════════════════════════════════════════════
class StyledSpinBox(QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(60)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        get_theme().add_listener(self._update_style)
        self._update_style()
        
    def wheelEvent(self, e):
        if self.underMouse():
            delta = e.angleDelta().y()
            if delta > 0:
                self.stepBy(1)
            elif delta < 0:
                self.stepBy(-1)
            e.accept()
        else:
            super().wheelEvent(e)

    def _update_style(self):
        theme = get_theme()
        radius = min(theme.border_radius, 4)
        self.setStyleSheet(f"""
            QSpinBox {{
                background-color: {theme.bg_input};
                color: {theme.text_primary};
                border: {theme.border_width}px solid {theme.border_color};
                border-radius: {radius}px;
                padding: 5px 8px;
                font-size: 12px;
                font-weight: bold;
                min-height: 20px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 0px;
                border: none;
                background: transparent;
            }}
            QSpinBox:focus {{
                border: {theme.highlight_border_width}px solid {theme.accent};
            }}
        """)


class StyledDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(60)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        get_theme().add_listener(self._update_style)
        self._update_style()
        
    def wheelEvent(self, e):
        if self.underMouse():
            delta = e.angleDelta().y()
            if delta > 0:
                self.stepBy(1)
            elif delta < 0:
                self.stepBy(-1)
            e.accept()
        else:
            super().wheelEvent(e)

    def _update_style(self):
        theme = get_theme()
        radius = min(theme.border_radius, 4)
        self.setStyleSheet(f"""
            QDoubleSpinBox {{
                background-color: {theme.bg_input};
                color: {theme.text_primary};
                border: {theme.border_width}px solid {theme.border_color};
                border-radius: {radius}px;
                padding: 5px 8px;
                font-size: 12px;
                font-weight: bold;
                min-height: 20px;
            }}
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                width: 0px;
                border: none;
                background: transparent;
            }}
            QDoubleSpinBox:focus {{
                border: {theme.highlight_border_width}px solid {theme.accent};
            }}
        """)


def make_spinbox():
    return StyledSpinBox()


def make_double_spinbox():
    return StyledDoubleSpinBox()


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDER ROW
# ═══════════════════════════════════════════════════════════════════════════════
class SliderRow(QWidget):
    def __init__(self, label_text, soft_min=0, soft_max=100, default=0, decimals=0, hard_max=100000, scale=10, parent=None):
        super().__init__(parent)
        self.decimals = decimals
        self.scale = scale
        self.current_max = soft_max

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.lbl = label(label_text)
        self.lbl.setFixedWidth(80)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(soft_min)
        self.slider.setMaximum(soft_max)
        self.slider.setValue(default)

        if decimals > 0:
            self.spin = make_double_spinbox()
            self.spin.setRange(soft_min / self.scale, hard_max / self.scale)
            self.spin.setDecimals(decimals)
            self.spin.setValue(default / self.scale)
        else:
            self.spin = make_spinbox()
            self.spin.setRange(soft_min, hard_max)
            self.spin.setValue(default)

        self.spin.setFixedWidth(60)
        self.slider.valueChanged.connect(self._on_slider_change)
        self.spin.valueChanged.connect(self._on_spin_change)
        get_theme().add_listener(self._update_style)

        row.addWidget(self.lbl)
        row.addWidget(self.slider)
        row.addWidget(self.spin)
        self._update_style()

    def _on_slider_change(self, val):
        if self.decimals > 0:
            self.spin.setValue(val / self.scale)
        else:
            self.spin.setValue(val)

    def _on_spin_change(self):
        val = self.spin.value()
        if self.decimals > 0:
            val = int(val * self.scale)
        if val > self.current_max:
            self.current_max = min(val, 100000)
            self.slider.setMaximum(self.current_max)
        elif val < self.slider.minimum():
            self.slider.setMinimum(val)
        self.slider.setValue(val)

    def _update_style(self):
        theme = get_theme()
        self.lbl.setStyleSheet(f"color: {theme.text_secondary}; font-size: 11px; background: transparent;")
        radius = min(theme.border_radius, 4)
        self.spin.setStyleSheet(f"""
            QSpinBox, QDoubleSpinBox {{
                background-color: {theme.bg_input};
                color: {theme.text_primary};
                border: {theme.border_width}px solid {theme.border_color};
                border-radius: {radius}px;
                padding: 5px 8px;
                font-size: 12px;
                font-weight: bold;
                min-height: 20px;
            }}
            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                width: 0px;
                border: none;
                background: transparent;
            }}
            QSpinBox:focus, QDoubleSpinBox:focus {{
                border: {theme.highlight_border_width}px solid {theme.accent};
            }}
        """)

        handle_style = theme.slider_handle
        if handle_style == theme.SLIDER_HANDLE_NONE:
            handle_ss = f"""
                QSlider::handle:horizontal {{
                    background: {theme.bg_card};
                    border: 1px solid {theme.bg_card};
                    width: 1px;
                    height: 3px;
                    margin: 0px 0;
                    border-radius: 0px;
                }}
            """
        elif handle_style == theme.SLIDER_HANDLE_SQUARE:
            handle_size = 16
            margin = -((handle_size - 4) // 2)
            handle_ss = f"""
                QSlider::handle:horizontal {{
                    background: {theme.accent};
                    border: {theme.border_width}px solid {theme.border_color};
                    width: {handle_size}px;
                    height: {handle_size}px;
                    margin: {margin}px 0;
                    border-radius: {min(2, theme.border_radius)}px;
                }}
            """
        else:
            handle_size = 16
            radius = handle_size // 2
            margin = -((handle_size - 4) // 2)
            handle_ss = f"""
                QSlider::handle:horizontal {{
                    background: {theme.accent};
                    border: {theme.border_width}px solid {theme.border_color};
                    width: {handle_size}px;
                    height: {handle_size}px;
                    margin: {margin}px 0;
                    border-radius: {radius}px;
                }}
            """

        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 3px;
                background: {theme.divider};
                border: 1px solid {theme.border_color};
            }}
            QSlider::sub-page:horizontal {{
                background: {theme.accent};
            }}
            {handle_ss}
        """)

    def value(self):
        return self.spin.value()


def make_slider_row(label_text, soft_min=0, soft_max=100, default=0, decimals=0, hard_max=100000, scale=10):
    return SliderRow(label_text, soft_min, soft_max, default, decimals, hard_max, scale)

class ModeIconButton(QPushButton):
    """Icon button for keyframe mode selection with active/inactive states"""
    
    def __init__(self, svg_path, tooltip, parent=None, size=40, icon_size=24, svg_path_active=None):
        super().__init__(parent)
        self.svg_path = svg_path
        self.svg_path_active = svg_path_active
        self.is_active = False
        self.icon_size = icon_size
        self.setToolTip(tooltip)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()
        get_theme().add_listener(self._update_style)
    
    def set_active(self, active):
        """Set active state and update styling"""
        self.is_active = active
        self._update_style()
    
    def _update_style(self):
        theme = get_theme()
        if self.is_active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: {theme.highlight_border_width}px solid {theme.accent};
                    border-radius: 8px;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    background: {theme.bg_input};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: 1px solid {theme.border_color};
                    border-radius: 8px;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    background: {theme.bg_input};
                    border-color: {theme.text_secondary};
                }}
            """)

        # Load SVG with current color
        self._load_svg()
    
    def _load_svg(self):
        """Load SVG icon with current color"""
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtGui import QPixmap, QPainter, QIcon
        import os
        
        # Read SVG file
        try:
            # Determine which SVG to use
            if self.is_active and self.svg_path_active:
                path = self.svg_path_active
            else:
                path = self.svg_path

            with open(path, 'r') as f:
                svg_data = f.read()
            
            # Replace currentColor with actual color
            theme = get_theme()
            color = theme.accent if self.is_active else theme.text_secondary
            svg_data = svg_data.replace('currentColor', color)
            svg_data = svg_data.replace('accentColor', theme.accent)
            
            # Render to QIcon at higher resolution for crispness
            scale = 4
            target_size = self.icon_size * scale
            
            renderer = QSvgRenderer(svg_data.encode())
            pixmap = QPixmap(target_size, target_size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            
            # Enable antialiasing
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            
            renderer.render(painter)
            painter.end()
            
            self.setIcon(QIcon(pixmap))
            self.setIconSize(QSize(self.icon_size, self.icon_size))
        except Exception as e:
            print(f"Error loading SVG {self.svg_path}: {e}")
