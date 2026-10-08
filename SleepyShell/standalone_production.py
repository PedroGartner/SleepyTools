"""Standalone launcher for Version 2 (ShotGrid-inspired production view).

    python standalone_production.py
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
    from shellui.widgets import apply_standalone_icon
    from shellui_production.production_widget import ProductionWidget

    state, backend = get_session()
    theme.apply(app, state.prefs)
    state.refresh(force=True)

    window = QtWidgets.QMainWindow()
    apply_standalone_icon(app, window)
    window.setWindowTitle("Sleepy Shell — Project Manager (Production)")
    window.resize(1280, 800)
    widget = ProductionWidget(state, backend)
    window.setCentralWidget(widget)
    widget.reload()

    # opening a script from the standalone view launches Nuke
    widget.openScriptRequested.connect(lambda path: backend.open_script(path))

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
