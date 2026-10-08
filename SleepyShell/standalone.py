"""Standalone Sleepy Shell launcher.

Run with a normal Python that has PySide6 (or PySide2):
    python standalone.py

This is the front door before Nuke starts: browse projects and shots,
then launch Nuke on the right script. The same shellcore engine powers
the docked Nuke panel.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
for _path in (_HERE, _PARENT):
    if _path not in sys.path:
        sys.path.append(_path.replace("\\", "/"))


def main():
    # interface zoom must be set before QApplication exists
    from shellui import theme as _theme
    from shellcore import prefs as _prefs
    _theme.apply_scale_env(_prefs.load())
    from SleepyCore.qt import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    from shellui import theme
    from shellui.session import get_session
    from shellui.mainwindow import MainWindow
    from shellui.widgets import apply_standalone_icon

    state, backend = get_session()
    theme.apply(app, state.prefs)
    window = MainWindow(state, backend)
    apply_standalone_icon(app, window)
    window.refresh(silent=True)
    window.show()
    if not state.prefs.get("show_on_launch", True):
        # "Show Shell on launch" off: start on the Board instead of Home
        window._goto(window.board_page)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
