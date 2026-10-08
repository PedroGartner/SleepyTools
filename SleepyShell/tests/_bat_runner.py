"""Runs standalone.py's real code path with an auto-quit timer."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from SleepyCore.qt import QtCore, QtWidgets  # noqa: E402


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    from shellui import theme
    from shellui.session import get_session
    from shellui.mainwindow import MainWindow

    state, backend = get_session()
    theme.apply(app, state.prefs)
    window = MainWindow(state, backend)
    window.refresh(silent=True)
    window.show()
    QtCore.QTimer.singleShot(1200, app.quit)
    app.exec()
    window.close()


if __name__ == "__main__":
    main()
