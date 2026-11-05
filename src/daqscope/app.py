from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="daqscope", description="DAQScope oscilloscope")
    ap.add_argument("--backend", default="simulated", help="simulated or nidaqmx")
    args = ap.parse_args(argv)
    from .gui.qt import QtWidgets
    from .gui.main_window import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    from .gui.theme import apply_theme
    apply_theme(app)
    win = MainWindow(args.backend)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
