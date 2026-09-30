import sys

import pyqtgraph as pg
from PySide6 import QtWidgets

from . import crashlog


def main():
    crashed = crashlog.install()
    pg.setConfigOptions(antialias=True, background="#15171c", foreground="#c8d0dc")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName("kinsyn")
    app.aboutToQuit.connect(crashlog.clean_exit)
    from .main_window import MainWindow

    win = MainWindow()
    win.show()
    if crashed:
        pid, started = crashed
        crashlog.breadcrumb(f"previous session pid {pid} (started {started}) did not exit cleanly")
        QtWidgets.QMessageBox.information(
            win, "kinsyn: previous session crashed",
            f"The previous kinsyn session (pid {pid}, started {started}) did not exit cleanly.\n\n"
            f"Diagnostics were saved in {crashlog.STATE_DIR}:\n"
            f"  • faulthandler.log: Python stack of every thread at the crash\n"
            f"  • breadcrumbs.log: what you were doing just before\n"
            f"  • errors.log: Python errors and Qt warnings\n\n"
            f"Ask Claude to diagnose it (diagnose-crash skill); it knows to read these logs.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
