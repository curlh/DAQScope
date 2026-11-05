"""The only module that chooses the Qt binding. Everything else imports Qt from here."""
import os

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import pyqtgraph as pg                                        # noqa: E402
from PySide6 import QtCore, QtGui, QtWidgets                  # noqa: E402,F401
from PySide6.QtCore import Qt, QTimer, Signal                 # noqa: E402,F401

pg.setConfigOptions(antialias=False, background="k", foreground="w")
