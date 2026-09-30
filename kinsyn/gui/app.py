import sys

import pyqtgraph as pg
from PySide6 import QtWidgets


def main():
    pg.setConfigOptions(antialias=True, background="#15171c", foreground="#c8d0dc")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName("kinsyn")
    from .main_window import MainWindow

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
