"""Development variant selector — pick a Project Manager frontend to open.

    python shell_selector.py

Small Qt chooser for comparing the three versions during development.
All three share one backend session in this process, so they show the
same project data. Close the chooser to exit.
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
    from SleepyCore.qt import QtWidgets, QtCore

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    from shellui import theme
    from shellui.session import get_session
    from shellui.widgets import apply_standalone_icon
    state, backend = get_session()
    theme.apply(app, state.prefs)
    state.refresh(force=True)

    window = QtWidgets.QMainWindow()
    apply_standalone_icon(app, window)
    window.setWindowTitle("Sleepy Shell — choose a Project Manager version")
    central = QtWidgets.QWidget()
    window.setCentralWidget(central)
    layout = QtWidgets.QVBoxLayout(central)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(12)

    title = QtWidgets.QLabel("Which version do you want to compare?")
    title.setStyleSheet("font-size: 16px; font-weight: 600;")
    layout.addWidget(title)
    subtitle = QtWidgets.QLabel(
        "All three share the same backend and the same project data in this session.")
    subtitle.setObjectName("ShellDim")
    layout.addWidget(subtitle)

    info = QtWidgets.QLabel(state_summary(state))
    info.setWordWrap(True)
    layout.addWidget(info)

    opened = []

    def open_variant(label, build):
        widget = build()
        child = QtWidgets.QMainWindow()
        apply_standalone_icon(app, child)
        child.setWindowTitle(label)
        child.setCentralWidget(widget)
        child.resize(1280, 800)
        child.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        child.show()
        opened.append(child)

    def build_v1():
        from shellui.mainwindow import MainWindow
        window = MainWindow(state, backend)
        window.refresh(silent=True)
        return window

    def build_v2():
        from shellui_production.production_widget import ProductionWidget
        widget = ProductionWidget(state, backend)
        widget.reload()
        widget.openScriptRequested.connect(lambda p: backend.open_script(p))
        return widget

    def build_v3():
        from shellui_nuke.nuke_pane import NukePaneWidget
        widget = NukePaneWidget(state, backend)
        widget.reload()
        return widget

    for label, build in (
            ("Version 1 — Current design", build_v1),
            ("Version 2 — ShotGrid-inspired (Production)", build_v2),
            ("Version 3 — Nuke-inspired", build_v3)):
        button = QtWidgets.QPushButton(label)
        button.setMinimumHeight(40)
        button.setProperty("accent", True)
        button.clicked.connect(lambda _=False, l=label, b=build: open_variant(l, b))
        layout.addWidget(button)

    layout.addStretch(1)
    window.resize(460, 320)
    window.show()
    return app.exec()


def state_summary(state):
    return "{} projects · {} shots · roots: {}".format(
        len(state.projects), len(state.shots),
        ", ".join(state.prefs.get("watched_roots", [])) or "none configured")


if __name__ == "__main__":
    sys.exit(main())
