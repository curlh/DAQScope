"""Dark instrument theme: one palette and one style sheet for the whole application."""
from __future__ import annotations

from .qt import QtGui, QtWidgets

BG = "#0b0b0c"
PANEL = "#111113"
PANEL2 = "#0e0e10"
BORDER = "#2b2b30"
BORDER2 = "#3d3d46"
TEXT = "#cfcfd4"
MUTED = "#74747e"
ACCENT = "#ffb000"          # the one accent: amber, as on a lab instrument display
GOOD = "#37d67a"
WARN = "#ffb000"
BAD = "#ff4d4d"
MONO = '"JetBrains Mono","Cascadia Mono","Consolas","DejaVu Sans Mono","Liberation Mono",monospace'

STATUS_COLORS = {"Trig'd": GOOD, "Auto": WARN, "Roll": TEXT, "Armed": TEXT, "Ready": TEXT,
                 "Stop": BAD}

QSS = f"""
* {{ font-family: {MONO}; font-size: 12px; color: {TEXT}; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QFrame#header {{ background: {PANEL2}; border-bottom: 1px solid {BORDER}; }}
QLabel#brand {{ color: {ACCENT}; font-size: 14px; font-weight: 700; letter-spacing: 3px; }}
QLabel#device {{ color: {MUTED}; }}
QLabel#pill {{ padding: 3px 10px; font-weight: 700; border: 1px solid {BORDER2}; }}
QPushButton {{ background: {PANEL}; border: 1px solid {BORDER2}; padding: 5px 13px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT}; color: #000; }}
QPushButton:disabled {{ color: {MUTED}; }}
QPushButton[kind="run"] {{ background: #2fbf6a; border-color: #2fbf6a; color: #000; font-weight: 700; min-width: 64px; }}
QPushButton[kind="stop"] {{ background: #e0453f; border-color: #e0453f; color: #000; font-weight: 700; min-width: 64px; }}
QPushButton[kind="accent"] {{ color: {ACCENT}; border-color: {ACCENT}; font-weight: 700; }}
QPushButton[kind="accent"]:hover {{ background: #2a2200; }}
QPushButton[kind="rec"] {{ background: #7a1c1c; border-color: {BAD}; color: #fff; font-weight: 700; }}
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {{
    background: {BG}; border: 1px solid {BORDER2}; padding: 3px 6px; min-height: 20px;
    selection-background-color: {ACCENT}; selection-color: #000; }}
QComboBox:hover, QDoubleSpinBox:hover {{ border-color: #5a5a66; }}
QComboBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {BORDER2}; selection-background-color: {ACCENT}; selection-color: #000; outline: 0; }}
QTabWidget::pane {{ border: none; border-top: 1px solid {BORDER}; }}
QTabBar::tab {{ background: {PANEL2}; color: {MUTED}; padding: 6px 8px; border: 1px solid {BORDER}; border-bottom: none; margin-right: -1px; }}
QTabBar::tab:selected {{ background: {PANEL}; color: {ACCENT}; border-top: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 12px; height: 12px; border: 1px solid #5a5a66; background: {BG}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QListWidget {{ background: {BG}; border: 1px solid {BORDER2}; padding: 2px; }}
QListWidget::item {{ padding: 2px 4px; }}
QTableWidget {{ background: {BG}; border: 1px solid {BORDER}; gridline-color: #1e1e22; font-size: 11px; }}
QHeaderView::section {{ background: {PANEL}; color: {MUTED}; border: none; border-right: 1px solid #1e1e22; border-bottom: 1px solid {BORDER}; padding: 4px; font-weight: 700; }}
QTableWidget::item {{ padding: 0 3px; }}
QFrame#bar {{ background: {PANEL2}; border: 1px solid {BORDER}; }}
QFrame#seg {{ background: transparent; border: none; border-right: 1px solid {BORDER}; }}
QFrame#seg:hover {{ background: #18181c; }}
QFrame#screenFrame {{ background: #000; border: 1px solid {BORDER2}; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="section"] {{ color: {MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
QLabel[role="value"] {{ font-size: 13px; font-weight: 700; }}
QLabel[role="mono"] {{ }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER2}; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QStatusBar {{ background: {PANEL2}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QToolTip {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER2}; }}
"""


def apply_theme(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    for role, col in [(QtGui.QPalette.Window, BG), (QtGui.QPalette.WindowText, TEXT),
                      (QtGui.QPalette.Base, PANEL), (QtGui.QPalette.AlternateBase, PANEL2),
                      (QtGui.QPalette.Text, TEXT), (QtGui.QPalette.Button, PANEL),
                      (QtGui.QPalette.ButtonText, TEXT), (QtGui.QPalette.Highlight, ACCENT),
                      (QtGui.QPalette.HighlightedText, "#000000")]:
        pal.setColor(role, QtGui.QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(QSS)


def repolish(widget: QtWidgets.QWidget) -> None:
    """Re-apply the style sheet after a dynamic property (kind, role) changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
