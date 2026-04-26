"""
EaseSpline — Activation Dialog
Shown on first launch when no valid activation.json is found.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from .theme import get_theme
from .activation import activate, deactivate


# ── Worker thread so the UI doesn't freeze during the API call ───────────────

class _ActivateWorker(QThread):
    done = Signal(bool, str)   # (success, message)

    def __init__(self, key: str):
        super().__init__()
        self.key = key

    def run(self):
        ok, msg = activate(self.key)
        self.done.emit(ok, msg)


# ── Dialog ────────────────────────────────────────────────────────────────────

class ActivationDialog(QDialog):

    def __init__(self, reason: str = "not_activated", parent=None):
        super().__init__(parent)
        self.setWindowTitle("EaseSpline — Activation")
        self.setFixedSize(520, 340)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self._worker = None
        self._build_ui(reason)
        self._apply_theme()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self, reason: str):
        t = get_theme()
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(0)

        # Title
        title = QLabel("EaseSpline")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)
        self._title = title

        root.addSpacing(6)

        # Subtitle / reason message
        sub_text = {
            "not_activated": "Enter your license key to continue.",
            "wrong_machine": "This copy is activated on a different machine.\nPurchase a new license or contact support.",
            "key_revoked":   "Your license has been revoked or refunded.\nPlease contact support.",
        }.get(reason, "Enter your license key to continue.")

        sub = QLabel(sub_text)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Segoe UI", 10))
        sub.setWordWrap(True)
        root.addWidget(sub)
        self._sub = sub

        root.addSpacing(24)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)
        self._divider = line

        root.addSpacing(20)

        # Key input row
        row = QHBoxLayout()
        row.setSpacing(10)

        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self._key_input.setFixedHeight(38)
        self._key_input.setFont(QFont("Consolas", 11))
        self._key_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._key_input.returnPressed.connect(self._on_activate)
        if reason in ("wrong_machine", "key_revoked"):
            self._key_input.setEnabled(False)
        row.addWidget(self._key_input, 1)

        self._btn = QPushButton("Activate")
        self._btn.setFixedSize(100, 38)
        self._btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self._on_activate)
        if reason in ("wrong_machine", "key_revoked"):
            self._btn.setEnabled(False)
        row.addWidget(self._btn)

        root.addLayout(row)
        root.addSpacing(14)

        # Status label
        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setFont(QFont("Segoe UI", 9))
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        root.addSpacing(8)

        # Reset button — lets user clear old machine-locked activation
        self._reset_btn = QPushButton("Reset activation")
        self._reset_btn.setFixedSize(150, 32)
        self._reset_btn.setFont(QFont("Segoe UI", 9))
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.clicked.connect(self._on_reset)
        self._reset_btn.setVisible(reason in ("wrong_machine", "key_revoked"))
        root.addWidget(self._reset_btn, 0, Qt.AlignmentFlag.AlignCenter)

        root.addSpacing(4)

        self._reset_note = QLabel("Reset activation in case activation key is disabled")
        self._reset_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._reset_note.setFont(QFont("Segoe UI", 8))
        self._reset_note.setVisible(reason in ("wrong_machine", "key_revoked"))
        root.addWidget(self._reset_note, 0, Qt.AlignmentFlag.AlignCenter)

        root.addStretch()

        # Purchase links
        links = QLabel(
            '<a href="https://reveace.gumroad.com/l/EaseSpline">Buy on Gumroad</a>'
            '  ·  '
            '<a href="https://payhip.com/b/VvfEb">Buy on Payhip</a>'
        )
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        links.setOpenExternalLinks(True)
        links.setFont(QFont("Segoe UI", 9))
        root.addWidget(links)
        self._links = links

    def _apply_theme(self):
        t = get_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background: {t.bg_outer};
            }}
            QLineEdit {{
                background: {t.bg_input};
                color: {t.text_primary};
                border: 2px solid {t.border_color};
                border-radius: {t.border_radius}px;
                padding: 4px 10px;
            }}
            QLineEdit:focus {{
                border: 2px solid {t.accent};
            }}
            QPushButton {{
                background: {t.accent};
                color: #000000;
                border: none;
                border-radius: {t.border_radius}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {t.accent}cc;
            }}
            QPushButton:disabled {{
                background: {t.bg_card};
                color: {t.text_secondary};
            }}
            QFrame[frameShape="4"] {{
                color: {t.border_color};
            }}
        """)
        self._title.setStyleSheet(f"color: {t.accent};")
        self._sub.setStyleSheet(f"color: {t.text_secondary};")
        self._status.setStyleSheet(f"color: {t.text_secondary};")
        self._links.setStyleSheet(f"color: {t.text_secondary};")

    # ── Activation logic ──────────────────────────────────────────────────────

    def _on_activate(self):
        key = self._key_input.text().strip()
        if not key:
            self._set_status("Please enter your license key.", error=True)
            return

        self._set_busy(True)
        self._set_status("Verifying…")

        self._worker = _ActivateWorker(key)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, success: bool, message: str):
        self._set_busy(False)
        if success:
            self._set_status("Activated! Starting EaseSpline…", error=False)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(800, self.accept)
        else:
            self._set_status(message, error=True)

    def _set_busy(self, busy: bool):
        self._key_input.setEnabled(not busy)
        self._btn.setEnabled(not busy)
        self._btn.setText("Checking…" if busy else "Activate")

    def _on_reset(self):
        deactivate()
        self._key_input.setEnabled(True)
        self._key_input.clear()
        self._btn.setEnabled(True)
        self._reset_btn.setVisible(False)
        self._reset_note.setVisible(False)
        self._sub.setText("Enter your license key to continue.")
        self._set_status("Activation reset. You can now enter your key.", error=False)

    def _set_status(self, msg: str, error: bool = False):
        t = get_theme()
        color = "#ff4444" if error else t.accent
        self._status.setStyleSheet(f"color: {color};")
        self._status.setText(msg)
