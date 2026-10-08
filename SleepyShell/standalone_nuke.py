"""Standalone launcher for Version 3 (Nuke-inspired pane).

    python standalone_nuke.py
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

    from shellui.session import get_session
    from shellui.widgets import apply_standalone_icon
    from shellui_nuke.nuke_pane import NukePaneWidget

    state, backend = get_session()
    state.refresh(force=True)

    window = QtWidgets.QMainWindow()
    apply_standalone_icon(app, window)
    window.setWindowTitle("Sleepy Shell — Project Manager (Nuke)")
    window.resize(860, 620)
    widget = NukePaneWidget(state, backend)
    window.setCentralWidget(widget)
    widget.reload()
    window.show()
    return app.exec()


if __name__ == "__main__":
    # V3 keeps Nuke's own neutral styling; do not apply the Sleepy theme
    sys.exit(main())
