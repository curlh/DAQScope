"""Dark instrument theme: one palette and one style sheet for the whole application."""
from __future__ import annotations

from .qt import QtGui, QtWidgets

BG = "#2b2b2b"
PANEL = "#313335"
PANEL2 = "#2b2b2b"
FIELD = "#3c3f41"
BORDER = "#4a4d50"
BORDER2 = "#5a5d60"
TEXT = "#d4d4d4"
MUTED = "#9a9a9a"
SELECT = "#4b6eaf"          # selection and focus only, not a brand colour
GOOD = "#7fbf7f"
WARN = "#d6b05a"
BAD = "#e07a7a"
MONO = '"DejaVu Sans Mono","Consolas","Liberation Mono",monospace'

STATUS_COLORS = {"Trig'd": GOOD, "Auto": WARN, "Roll": TEXT, "Armed": TEXT, "Ready": TEXT,
                 "Stop": BAD}

QSS = f"""
QGroupBox {{ border: 1px solid {BORDER}; margin-top: 11px; padding: 10px 6px 6px 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 9px; padding: 0 4px; color: {MUTED}; }}
QPushButton[kind="run"] {{ color: {GOOD}; font-weight: bold; }}
QPushButton[kind="stop"] {{ color: {BAD}; font-weight: bold; }}
QPushButton[kind="rec"] {{ color: {BAD}; font-weight: bold; }}
QFrame#bar {{ border: none; border-top: 1px solid {BORDER}; }}
QFrame#seg {{ border: none; border-right: 1px solid {BORDER}; }}
QFrame#seg:hover {{ background: #35383a; }}
QFrame#seg[selected="true"] {{ background: #3d4044; }}
QFrame#screenFrame {{ background: #000; border: 1px solid {BORDER2}; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="value"] {{ font-family: {MONO}; }}
QLabel[role="mono"] {{ font-family: {MONO}; }}
QTableWidget {{ gridline-color: {BORDER}; font-family: {MONO}; font-size: 11px; }}
QHeaderView::section {{ background: {PANEL}; color: {MUTED}; border: none; border-right: 1px solid {BORDER}; border-bottom: 1px solid {BORDER}; padding: 3px; }}
QTabBar::tab {{ padding: 4px 10px; }}
"""


def apply_theme(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    for role, col in [(QtGui.QPalette.Window, BG), (QtGui.QPalette.WindowText, TEXT),
                      (QtGui.QPalette.Base, FIELD), (QtGui.QPalette.AlternateBase, PANEL2),
                      (QtGui.QPalette.Text, TEXT), (QtGui.QPalette.Button, PANEL),
                      (QtGui.QPalette.ButtonText, TEXT), (QtGui.QPalette.Highlight, SELECT),
                      (QtGui.QPalette.HighlightedText, "#ffffff"),
                      (QtGui.QPalette.ToolTipBase, PANEL), (QtGui.QPalette.ToolTipText, TEXT),
                      (QtGui.QPalette.PlaceholderText, MUTED)]:
        pal.setColor(role, QtGui.QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(QSS)


def repolish(widget: QtWidgets.QWidget) -> None:
    """Re-apply the style sheet after a dynamic property (kind, role) changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
