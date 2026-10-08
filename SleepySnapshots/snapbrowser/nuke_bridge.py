"""Nuke side of Snapshot Browser: taking snapshots, restoring, callbacks and menus."""

from __future__ import annotations

import os
import sys
import tempfile
import traceback

import nuke

from snapbrowser import core
from snapbrowser.qt import QOpenGLWidget, QtCore, QtGui, QtWidgets, Signal

IN_NUKE = True

PANEL_ID = "com.sleepytools.SnapshotBrowser"
PANEL_TITLE = "Snapshot Browser"
PANEL_WIDGET = "__import__('snapbrowser.panel', fromlist=['panel']).SnapshotBrowserPanel"

THUMBNAIL_WIDTH = 480

_settings = None
_events = None
_auto = None
_busy = False


# --------------------------------------------------------------------------
# Shared state
# --------------------------------------------------------------------------

class _Events(QtCore.QObject):
    """Signals the panel listens to."""

    changed = Signal()
    script_changed = Signal()


def events() -> _Events:
    global _events
    if _events is None:
        _events = _Events(QtWidgets.QApplication.instance())
    return _events


def settings() -> dict:
    global _settings
    if _settings is None:
        _settings = core.load_settings()
    return _settings


def update_settings(values: dict) -> None:
    global _settings
    merged = dict(settings())
    merged.update(values)
    core.save_settings(merged)
    _settings = merged
    if _auto is not None:
        _auto.configure(int(merged.get("auto_interval_minutes") or 0))


def current_script():
    """Path of the open script, or None when it has never been saved."""
    try:
        path = nuke.scriptName()
    except RuntimeError:
        return None
    return path or None


def _log(message: str) -> None:
    print("[Snapshot Browser] " + message)


def _emit_changed() -> None:
    if _events is not None:
        _events.changed.emit()


def _emit_script_changed() -> None:
    if _events is not None:
        _events.script_changed.emit()


# --------------------------------------------------------------------------
# Snapshots
# --------------------------------------------------------------------------

def take_snapshot(kind: str = core.KIND_MANUAL, note: str = "", thumbnail=None, quiet: bool = False):
    """Save the current state of the script as a snapshot.

    Returns the new snapshot, or None when nothing was stored (unsaved
    script, nothing changed since the last snapshot, or an error).
    """
    return _take(kind, note, thumbnail, quiet)[0]


def _take(kind, note, thumbnail, quiet):
    """Returns (snapshot, reason) where reason is "", "unsaved", "unchanged", "busy" or "error"."""
    global _busy
    if _busy:
        return None, "busy"

    script = current_script()
    if not script:
        if not quiet:
            nuke.message("Save the script first.\n\nSnapshots are stored next to the script file.")
        return None, "unsaved"

    prefs = settings()
    store = core.SnapshotStore(script)
    _busy = True
    try:
        scratch = store.temp_path()
        nuke.scriptSaveToTemp(scratch)

        thumb = None
        if prefs.get("thumbnails") if thumbnail is None else thumbnail:
            thumb = grab_viewer_thumbnail(store.temp_path(".jpg"))

        snapshot = store.add(
            scratch,
            kind=kind,
            note=note,
            thumbnail_file=thumb,
            frame=int(nuke.frame()),
            source_script=script,
            app=getattr(nuke, "NUKE_VERSION_STRING", ""),
            dedupe=kind != core.KIND_MANUAL,
            compress=bool(prefs.get("compress_snapshots", True)),
        )
        if kind in core.AUTOMATIC_KINDS:
            store.prune(int(prefs.get("keep_automatic") or 0))
    except Exception as exc:
        _log("Snapshot failed: {}".format(exc))
        traceback.print_exc()
        if not quiet:
            nuke.message("Snapshot failed:\n{}".format(exc))
        return None, "error"
    finally:
        _busy = False

    if snapshot is None:
        return None, "unchanged"
    _emit_changed()
    return snapshot, ""


def take_snapshot_interactive() -> None:
    """Hotkey entry point: optional note, then snapshot with a small confirmation."""
    if not current_script():
        nuke.message("Save the script first.\n\nSnapshots are stored next to the script file.")
        return

    note = ""
    if settings().get("ask_note"):
        note, accepted = QtWidgets.QInputDialog.getText(
            QtWidgets.QApplication.activeWindow(),
            "Take Snapshot",
            "Note (optional):",
        )
        if not accepted:
            return

    snapshot, reason = _take(core.KIND_MANUAL, note.strip(), None, False)
    if snapshot is not None:
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "Snapshot saved")
    elif reason == "unchanged":
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "Nothing changed since the last snapshot")


# --------------------------------------------------------------------------
# Thumbnails
# --------------------------------------------------------------------------

def _viewer_widget():
    viewer = nuke.activeViewer()
    if viewer is None:
        return None
    name = viewer.node().name()
    app = QtWidgets.QApplication.instance()
    for widget in app.allWidgets():
        if widget.windowTitle() == name and widget.isVisible():
            return widget
    return None


def _viewport(widget):
    """The largest visible child of the viewer panel, i.e. the image area."""
    if QOpenGLWidget is not None:
        gl = [w for w in widget.findChildren(QOpenGLWidget) if w.isVisible()]
        if gl:
            return max(gl, key=lambda w: w.width() * w.height())
    children = [w for w in widget.findChildren(QtWidgets.QWidget) if w.isVisible()]
    if not children:
        return widget
    return max(children, key=lambda w: w.width() * w.height())


def _looks_blank(image) -> bool:
    if image is None or image.isNull():
        return True
    first = None
    for ix in range(1, 8):
        for iy in range(1, 8):
            color = image.pixelColor(image.width() * ix // 8, image.height() * iy // 8)
            if first is None:
                first = color
            elif color != first:
                return False
    return True


def grab_viewer_thumbnail(path: str):
    """Save the active viewer's image area to ``path``. Returns the path or None."""
    try:
        panel = _viewer_widget()
        if panel is None:
            return None
        target = _viewport(panel)
        if target.width() < 16 or target.height() < 16:
            return None

        image = None
        if QOpenGLWidget is not None and isinstance(target, QOpenGLWidget):
            image = target.grabFramebuffer()

        if _looks_blank(image):
            # Screen capture only while Nuke is in front, otherwise we would
            # grab whatever window is covering it.
            if QtWidgets.QApplication.activeWindow() is None:
                return None
            screen = target.screen()
            origin = target.mapToGlobal(QtCore.QPoint(0, 0))
            geometry = screen.geometry()
            image = screen.grabWindow(
                0,
                origin.x() - geometry.x(),
                origin.y() - geometry.y(),
                target.width(),
                target.height(),
            ).toImage()

        if image is None or image.isNull():
            return None
        if image.width() > THUMBNAIL_WIDTH:
            image = image.scaledToWidth(THUMBNAIL_WIDTH, QtCore.Qt.SmoothTransformation)
        return path if image.save(path, "JPG", 85) else None
    except Exception as exc:
        _log("Thumbnail skipped: {}".format(exc))
        return None


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------

def restore(path: str, label: str = "") -> bool:
    """Replace the open script's contents with ``path``, keeping its file name.

    The current state is snapshotted first and nothing is written to the
    script on disk until the user saves.
    """
    script = current_script()
    question = (
        "Replace the current script with {}?\n\n"
        "A snapshot of the current state is taken first. "
        "Nothing is written to disk until you save."
    ).format(label or os.path.basename(path))
    if not nuke.ask(question):
        return False

    if script:
        take_snapshot(core.KIND_RESTORE, note="Before restoring " + (label or os.path.basename(path)), quiet=True)

    nuke.scriptClear()
    with core.plain_script(path) as plain:
        nuke.scriptReadFile(plain)
    if script:
        nuke.root()["name"].setValue(script)
    nuke.root().setModified(True)
    _emit_changed()
    return True


def save_as_next_version(path: str, reference_script=None):
    """Copy ``path`` to the next free version of the shot and offer to open it."""
    reference = reference_script or current_script() or path
    destination = core.next_version_path(reference)
    try:
        core.copy_as_version(path, destination)
    except OSError as exc:
        nuke.message("Could not write {}:\n{}".format(destination, exc))
        return None
    _emit_changed()
    if nuke.ask("Saved {}.\n\nOpen it now?".format(os.path.basename(destination))):
        nuke.scriptOpen(destination)
    return destination


def open_script(path: str) -> None:
    nuke.scriptOpen(path)


def current_state_text() -> str:
    """The open script as it is right now, including unsaved changes."""
    handle, path = tempfile.mkstemp(suffix=".nk", prefix="snapshot_browser_")
    os.close(handle)
    os.remove(path)
    try:
        nuke.scriptSaveToTemp(path)
        with open(path, "r", encoding="utf-8", errors="replace") as stream:
            return stream.read()
    finally:
        if os.path.exists(path):
            os.remove(path)


# --------------------------------------------------------------------------
# Node actions used by the compare view
# --------------------------------------------------------------------------

#: Knobs that cannot be reverted by writing them back.
UNREVERTABLE_KNOBS = frozenset({"(class)", "inputs", "addUserKnob"})


def _node(path: str):
    if path == "Root":
        return nuke.root()
    with nuke.root():
        return nuke.toNode(path)


def select_nodes(paths) -> int:
    """Select the given nodes in the node graph and frame them.

    Nodes inside groups also select their top-level group, so something is
    visible in the main node graph. Returns how many nodes were found.
    """
    with nuke.root():
        for node in nuke.selectedNodes():
            node.setSelected(False)

    found = 0
    for path in paths:
        if path == "Root":
            continue
        node = _node(path)
        if node is None:
            continue
        node.setSelected(True)
        found += 1
        top = path.split(".", 1)[0]
        if top != path:
            group = _node(top)
            if group is not None:
                group.setSelected(True)
    if found:
        with nuke.root():
            nuke.zoomToFitSelected()
    return found


_DEFAULTS = {}


def _class_defaults(cls: str) -> dict:
    """Knob values of a freshly created node of ``cls``, as script strings."""
    if cls in _DEFAULTS:
        return _DEFAULTS[cls]
    values = {}
    maker = getattr(nuke.nodes, cls, None)
    if maker is not None:
        nuke.Undo.disable()
        temp = None
        try:
            with nuke.root():
                temp = maker()
                values = {name: knob.toScript() for name, knob in temp.knobs().items()}
        except Exception:
            values = {}
        finally:
            if temp is not None:
                nuke.delete(temp)
            nuke.Undo.enable()
    _DEFAULTS[cls] = values
    return values


def revert_knobs(path: str, changes):
    """Write older values from a comparison back onto a live node.

    ``changes`` are nkparse.KnobChange items and their ``old`` side is
    applied: knob values are written back, knobs that were at their default
    are reset, inputs are reconnected and a rename is undone. Everything for
    one node is a single undo step. Returns (number applied, names skipped).
    """
    node = _node(path)
    if node is None:
        return 0, [c.knob for c in changes]

    knobs = [c for c in changes if not c.is_input and c.knob != "name"
             and c.knob not in UNREVERTABLE_KNOBS]
    inputs = [c for c in changes if c.is_input]
    renames = [c for c in changes if c.knob == "name" and not c.is_input]
    skipped = [c.knob for c in changes if c.knob in UNREVERTABLE_KNOBS]
    defaults = _class_defaults(node.Class()) if any(c.old is None for c in knobs) else {}

    applied = 0
    undo = nuke.Undo()
    undo.begin("Revert " + node.name())
    try:
        for change in knobs:
            knob = node.knob(change.knob)
            try:
                if change.old is not None:
                    node.readKnobs("{} {}".format(change.knob, change.old))
                elif knob is not None and change.knob in defaults:
                    knob.fromScript(defaults[change.knob])
                else:
                    skipped.append(change.knob)
                    continue
                applied += 1
            except Exception as exc:
                _log("Could not revert {}.{}: {}".format(path, change.knob, exc))
                skipped.append(change.knob)

        for change in inputs:
            source = _node(change.old) if change.old else None
            if change.old and source is None:
                skipped.append("{} ({} not found)".format(change.knob, change.old))
                continue
            try:
                node.setInput(change.index, source)
                applied += 1
            except Exception as exc:
                _log("Could not reconnect {} {}: {}".format(path, change.knob, exc))
                skipped.append(change.knob)

        for change in renames:
            try:
                node["name"].setValue(change.old)
                applied += 1
            except Exception as exc:
                _log("Could not rename {}: {}".format(path, exc))
                skipped.append("name")
    finally:
        undo.end()
    return applied, skipped


def selected_node_path():
    """Full path (Group1.Blur1) of the selected node, or None."""
    try:
        node = nuke.selectedNode()
    except ValueError:
        return None
    return node.fullName() if node is not None else None


def show_node_history(path=None) -> None:
    """History of the selected node (or ``path``) across all saved states."""
    from snapbrowser import dialogs

    script = current_script()
    if not script:
        nuke.message("Save the script first.")
        return
    path = path or selected_node_path()
    if not path:
        nuke.message("Select a node to see its history.")
        return
    dialogs.open_node_history(sys.modules[__name__], script, path,
                              QtWidgets.QApplication.activeWindow())


def paste_node(snippet: str, parent_path: str = "") -> bool:
    """Paste node text (from nkparse.Node.snippet) into the script, disconnected."""
    handle, path = tempfile.mkstemp(suffix=".nk", prefix="snapshot_browser_")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(snippet)
    try:
        context = _node(parent_path) if parent_path else None
        if context is None or not hasattr(context, "begin"):
            context = nuke.root()
        with context:
            for node in nuke.selectedNodes():
                node.setSelected(False)
            nuke.nodePaste(path)
        return True
    except Exception as exc:
        _log("Paste failed: {}".format(exc))
        nuke.message("Could not paste the node:\n{}".format(exc))
        return False
    finally:
        os.remove(path)


# --------------------------------------------------------------------------
# Automatic snapshots
# --------------------------------------------------------------------------

class _AutoSnapshotter(QtCore.QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)

    def configure(self, minutes: int) -> None:
        if minutes > 0:
            self._timer.start(int(minutes * 60 * 1000))
        else:
            self._timer.stop()

    def _tick(self) -> None:
        if not current_script() or not nuke.root().modified():
            return
        app = QtWidgets.QApplication.instance()
        if app.activeModalWidget() is not None or app.activePopupWidget() is not None:
            return
        take_snapshot(core.KIND_AUTO, quiet=True)


def _on_save() -> None:
    if settings().get("snapshot_on_save"):
        take_snapshot(core.KIND_SAVE, quiet=True)
    QtCore.QTimer.singleShot(0, _emit_script_changed)


def _on_load() -> None:
    QtCore.QTimer.singleShot(0, _emit_script_changed)


def _on_close() -> None:
    QtCore.QTimer.singleShot(0, _emit_script_changed)


# --------------------------------------------------------------------------
# Panel and menus
# --------------------------------------------------------------------------

def show_panel() -> None:
    import nukescripts

    if nuke.getPaneFor(PANEL_ID) is not None:
        return
    panel = nukescripts.panels.registerWidgetAsPanel(PANEL_WIDGET, PANEL_TITLE, PANEL_ID, True)
    panel.addToPane(nuke.getPaneFor("Properties.1"))


def install() -> None:
    """Register menus, the dockable panel and callbacks. Safe to call twice."""
    global _auto
    if not nuke.GUI or getattr(nuke, "_snapshot_browser_installed", False):
        return
    nuke._snapshot_browser_installed = True

    import nukescripts

    prefs = settings()
    module = "from snapbrowser import nuke_bridge; nuke_bridge."
    menu = nuke.menu("Nuke").addMenu("SleepyTools").addMenu("Snapshots")
    menu.addCommand("Take Snapshot", module + "take_snapshot_interactive()", prefs.get("hotkey") or "")
    menu.addCommand("Take Snapshot Without Note", module + "take_snapshot()")
    menu.addCommand("Node History (Selected Node)", module + "show_node_history()")
    menu.addSeparator()
    menu.addCommand("Snapshot Browser", module + "show_panel()")

    nukescripts.panels.registerWidgetAsPanel(PANEL_WIDGET, PANEL_TITLE, PANEL_ID)

    nuke.addOnScriptSave(_on_save)
    nuke.addOnScriptLoad(_on_load)
    nuke.addOnScriptClose(_on_close)

    events()
    _auto = _AutoSnapshotter(QtWidgets.QApplication.instance())
    _auto.configure(int(prefs.get("auto_interval_minutes") or 0))
