"""Snapshot Browser outside Nuke.

    python -m snapbrowser [script.nk]

Browse, compare, annotate and clean up snapshots without opening Nuke.
Anything that needs a live script (restore, revert knobs, paste nodes,
selecting nodes) is only available inside Nuke.
"""

from __future__ import annotations

import os
import sys

from snapbrowser import __version__, core
from snapbrowser.qt import QtCore, QtGui, QtWidgets, Signal

IN_NUKE = False
EMPTY_HINT = "Open a Nuke script (Ctrl+O) or drop a .nk file here."


class _Events(QtCore.QObject):
    changed = Signal()
    script_changed = Signal()


class StandaloneBackend:
    """Same interface as nuke_bridge, working on the saved script file."""

    IN_NUKE = False
    EMPTY_HINT = EMPTY_HINT

    def __init__(self):
        self._events = _Events()
        self._settings = None
        self._script = None

    # -- shared interface -------------------------------------------------

    def events(self):
        return self._events

    def settings(self):
        if self._settings is None:
            self._settings = core.load_settings()
        return self._settings

    def update_settings(self, values):
        merged = dict(self.settings())
        merged.update(values)
        core.save_settings(merged)
        self._settings = merged

    def current_script(self):
        return self._script

    def set_script(self, path):
        self._script = os.path.abspath(path) if path else None
        self._events.script_changed.emit()

    def open_script(self, path):
        self.set_script(path)

    def current_state_text(self):
        return core.read_script_text(self._script)

    def selected_node_path(self):
        return None

    def take_snapshot_interactive(self):
        if not self._script:
            return
        note = ""
        if self.settings().get("ask_note"):
            note, accepted = QtWidgets.QInputDialog.getText(
                QtWidgets.QApplication.activeWindow(), "Take Snapshot",
                "Snapshot of the saved file.\nNote (optional):")
            if not accepted:
                return
        core.SnapshotStore(self._script).add(
            self._script, kind=core.KIND_MANUAL, note=note.strip(), move=False,
            dedupe=False, source_script=self._script, app="Snapshot Browser " + __version__,
            compress=bool(self.settings().get("compress_snapshots", True)))
        self._events.changed.emit()

    def restore(self, path, label=""):
        QtWidgets.QMessageBox.information(
            QtWidgets.QApplication.activeWindow(), "Restore",
            "Restoring needs the script open in Nuke.\n\n"
            "Use Save As Next Version to turn this entry into a new version instead.")
        return False

    def save_as_next_version(self, path, reference_script=None):
        reference = reference_script or self._script or path
        destination = core.next_version_path(reference)
        parent = QtWidgets.QApplication.activeWindow()
        try:
            core.copy_as_version(path, destination)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(parent, "Save As Next Version",
                                          "Could not write {}:\n{}".format(destination, exc))
            return None
        answer = QtWidgets.QMessageBox.question(
            parent, "Save As Next Version",
            "Saved {}.\n\nBrowse that version now?".format(os.path.basename(destination)))
        if answer == QtWidgets.QMessageBox.Yes:
            self.set_script(destination)
        else:
            self._events.changed.emit()
        return destination


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, backend):
        super().__init__()
        from snapbrowser.panel import SnapshotBrowserPanel

        self.backend = backend
        self.setAcceptDrops(True)
        self.resize(1200, 720)

        self.panel = SnapshotBrowserPanel(backend=backend)
        self.setCentralWidget(self.panel)

        file_menu = self.menuBar().addMenu("File")
        open_action = file_menu.addAction("Open Script...", self.open_dialog)
        open_action.setShortcut(QtGui.QKeySequence.Open)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("Quit", self.close)
        quit_action.setShortcut(QtGui.QKeySequence.Quit)

        backend.events().script_changed.connect(self._update_title)
        self._update_title()

    def _update_title(self):
        script = self.backend.current_script()
        name = os.path.basename(script) if script else "No script"
        self.setWindowTitle("{} - Snapshot Browser".format(name))

    def open_dialog(self):
        start = os.path.dirname(self.backend.current_script() or "") or os.path.expanduser("~")
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Nuke Script", start, "Nuke scripts (*.nk);;All files (*)")
        if path:
            self.backend.set_script(path)

    def dragEnterEvent(self, event):
        if any(u.toLocalFile().lower().endswith(".nk") for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".nk"):
                self.backend.set_script(path)
                break


def _set_app_icon(app):
    """Use the Sleepy face as the icon of every window (title bar and taskbar)."""
    if os.name == "nt":
        try:
            # own taskbar identity, so the icon is not replaced by python.exe's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Sleepy.Snapshots")
        except (AttributeError, OSError):
            pass
    icon = QtGui.QIcon(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sleepy_icon.png"))
    if not icon.isNull():
        app.setWindowIcon(icon)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName("Snapshot Browser")
    _set_app_icon(app)

    backend = StandaloneBackend()
    if argv and os.path.isfile(argv[0]):
        backend.set_script(argv[0])

    window = MainWindow(backend)
    window.show()
    return app.exec()
