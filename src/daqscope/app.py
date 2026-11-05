from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="daqscope", description="DAQScope oscilloscope")
    ap.add_argument("--backend", default="simulated", help="simulated or nidaqmx")
    args = ap.parse_args(argv)
    from .gui.qt import QtGui, QtWidgets
    from .gui.main_window import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    for role, col in [(QtGui.QPalette.Window, "#2b2b2b"), (QtGui.QPalette.WindowText, "#e0e0e0"),
                      (QtGui.QPalette.Base, "#1e1e1e"), (QtGui.QPalette.AlternateBase, "#2b2b2b"),
                      (QtGui.QPalette.Text, "#e0e0e0"), (QtGui.QPalette.Button, "#3a3a3a"),
                      (QtGui.QPalette.ButtonText, "#e0e0e0"), (QtGui.QPalette.Highlight, "#2a82da"),
                      (QtGui.QPalette.HighlightedText, "#ffffff")]:
        pal.setColor(role, QtGui.QColor(col))
    app.setPalette(pal)
    win = MainWindow(args.backend)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
