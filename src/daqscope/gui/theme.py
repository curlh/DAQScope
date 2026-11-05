"""Dark instrument theme: one palette and one style sheet for the whole application."""
from __future__ import annotations

from .qt import QtGui, QtWidgets

BG = "#0b0e14"
PANEL = "#121722"
PANEL2 = "#0f131c"
BORDER = "#232d42"
BORDER2 = "#2a354b"
TEXT = "#d7dde8"
MUTED = "#7d889c"
ACCENT = "#4f9dff"
GOOD = "#2ecc71"
WARN = "#ffb020"
BAD = "#ff4d5e"
MONO = '"JetBrains Mono","Cascadia Mono","Consolas","DejaVu Sans Mono",monospace'

STATUS_COLORS = {"Trig'd": GOOD, "Auto": WARN, "Roll": ACCENT, "Armed": ACCENT, "Ready": ACCENT,
                 "Stop": BAD}

QSS = f"""
* {{ font-family: "Inter","Segoe UI","Noto Sans","DejaVu Sans"; font-size: 13px; color: {TEXT}; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QFrame#header {{ background: {PANEL2}; border-bottom: 1px solid {BORDER}; }}
QLabel#brand {{ font-size: 17px; font-weight: 700; letter-spacing: 1px; }}
QLabel#device {{ color: {MUTED}; }}
QLabel#pill {{ border-radius: 11px; padding: 3px 12px; font-weight: 700; background: {PANEL}; }}
QPushButton {{ background: {PANEL}; border: 1px solid {BORDER2}; border-radius: 8px; padding: 7px 15px; }}
QPushButton:hover {{ background: #1b2336; border-color: #3a4a6b; }}
QPushButton:pressed {{ background: #243049; }}
QPushButton:disabled {{ color: {MUTED}; }}
QPushButton[kind="run"] {{ background: #1c8c4d; border-color: #2ecc71; color: white; font-weight: 700; min-width: 70px; }}
QPushButton[kind="run"]:hover {{ background: #22a35a; }}
QPushButton[kind="stop"] {{ background: #b83245; border-color: {BAD}; color: white; font-weight: 700; min-width: 70px; }}
QPushButton[kind="stop"]:hover {{ background: #d13b50; }}
QPushButton[kind="accent"] {{ background: #2b6cdf; border-color: {ACCENT}; color: white; font-weight: 600; }}
QPushButton[kind="accent"]:hover {{ background: #3a7cf0; }}
QPushButton[kind="rec"] {{ background: #7a1f2b; border-color: {BAD}; color: white; font-weight: 600; }}
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {{
    background: {PANEL}; border: 1px solid {BORDER2}; border-radius: 7px; padding: 4px 8px; min-height: 22px;
    selection-background-color: {ACCENT}; }}
QComboBox:hover, QDoubleSpinBox:hover {{ border-color: #3a4a6b; }}
QComboBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {BORDER2}; selection-background-color: #25417a; outline: 0; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 9px 7px; min-width: 52px; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: #eef2fb; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid #3a4763; background: {PANEL}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QListWidget {{ background: {PANEL}; border: 1px solid {BORDER2}; border-radius: 7px; padding: 3px; }}
QListWidget::item {{ padding: 3px 4px; }}
QTableWidget {{ background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 9px; gridline-color: {BORDER}; }}
QHeaderView::section {{ background: {PANEL}; color: {MUTED}; border: none; padding: 5px; font-weight: 600; }}
QTableWidget::item {{ padding: 2px 6px; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#card:hover {{ border-color: #3a4a6b; }}
QFrame#screenFrame {{ background: #05070b; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="section"] {{ color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1.2px; }}
QLabel[role="value"] {{ font-family: {MONO}; font-size: 15px; font-weight: 600; }}
QLabel[role="mono"] {{ font-family: {MONO}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER2}; border-radius: 4px; min-height: 30px; }}
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
                      (QtGui.QPalette.HighlightedText, "#ffffff")]:
        pal.setColor(role, QtGui.QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(QSS)


def repolish(widget: QtWidgets.QWidget) -> None:
    """Re-apply the style sheet after a dynamic property (kind, role) changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
