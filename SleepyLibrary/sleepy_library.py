"""Sleepy Library for Nuke.

Save node setups with a name, category, tags, description and a thumbnail rendered from the
viewer, then find them again by searching and insert them with a double-click (they connect to
the selected node, like Ctrl+V).

Each setup is a plain folder (setup.nk, meta.json, thumb.png), so a library can live on a
shared drive. Libraries:
  - your own:  ~/.nuke/sleepy_setup_library
  - shared:    any folders added in Settings, or listed in the SLEEPY_SETUP_LIBRARY environment
               variable (separated by ; on Windows, : elsewhere)
  - Nuke ToolSets from your plugin path are shown read-only.

Install: put the SleepyLibrary folder in ~/.nuke and add to ~/.nuke/init.py:
    nuke.pluginAddPath('./SleepyLibrary')
"""
import datetime
import getpass
import io
import json
import os
import re
import shutil
import time

import nuke

try:
    from nukescripts import panels as _nkpanels
except ImportError:
    _nkpanels = None

# Qt binding selection: use Nuke's Qt version to avoid second Qt binding crash
def _import_qt():
    """Qt binding for the running host: Nuke 13-15 -> PySide2, Nuke 16+ -> PySide6.

    Importing the other binding loads a second Qt into Nuke and crashes it, so
    the Nuke version is checked before any import. Prefers SleepyCore.qt
    when the core pack is installed; the copy below is the same logic so this
    file also works on its own.
    """
    try:
        from SleepyCore import qt as _core_qt
        return _core_qt
    except Exception:
        pass
    import sys
    try:
        import nuke
        _major = int(nuke.NUKE_VERSION_MAJOR)
    except Exception:
        _major = None
    if _major is not None:
        if _major >= 16:
            from PySide6 import QtCore, QtGui, QtWidgets
        else:
            from PySide2 import QtCore, QtGui, QtWidgets
    elif "PySide2.QtWidgets" in sys.modules:
        from PySide2 import QtCore, QtGui, QtWidgets
    else:
        try:
            from PySide6 import QtCore, QtGui, QtWidgets
        except ImportError:
            from PySide2 import QtCore, QtGui, QtWidgets
    from types import SimpleNamespace
    return SimpleNamespace(QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets)


_qt = _import_qt()
QtCore, QtGui, QtWidgets = _qt.QtCore, _qt.QtGui, _qt.QtWidgets

__version__ = "1.0"
PANEL_ID = "uk.co.pg.SetupLibrary"
PANEL_TITLE = "Sleepy Library"
NUKE_HOME = os.path.join(os.path.expanduser("~"), ".nuke")
DEFAULT_LIBRARY = os.path.join(NUKE_HOME, "sleepy_setup_library")
PREFS_FILE = os.path.join(NUKE_HOME, "sleepy_setup_library_prefs.json")
ENV_VAR = "SLEEPY_SETUP_LIBRARY"
THUMB_W, THUMB_H = 480, 270
TOOLSETS_CAT = "Nuke ToolSets"


# ---------------------------------------------------------------- prefs
def load_prefs():
    try:
        with io.open(PREFS_FILE, encoding="utf-8", errors="replace") as fh:
            p = json.load(fh)
            return p if isinstance(p, dict) else {}
    except (IOError, OSError, ValueError):
        return {}


def save_prefs(p):
    if not os.path.isdir(NUKE_HOME):
        os.makedirs(NUKE_HOME)
    tmp = PREFS_FILE + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        json.dump(p, fh, indent=1)
    os.replace(tmp, PREFS_FILE)


# ---------------------------------------------------------------- libraries
def libraries():
    """[(path, label, writable)] for every library folder, own library first."""
    out, seen = [], set()

    def add(path, label):
        path = os.path.normpath(os.path.expanduser(path))
        key = os.path.normcase(path)
        if key in seen:
            return
        seen.add(key)
        if path == os.path.normpath(DEFAULT_LIBRARY) and not os.path.isdir(path):
            try:
                os.makedirs(path)
            except OSError:
                pass
        writable = os.path.isdir(path) and os.access(path, os.W_OK)
        out.append((path, label, writable))

    add(DEFAULT_LIBRARY, "My library")
    for p in os.environ.get(ENV_VAR, "").split(os.pathsep):
        if p.strip():
            add(p.strip(), os.path.basename(p.strip().rstrip("/\\")) or p.strip())
    for p in load_prefs().get("extra_libraries", []):
        add(p, os.path.basename(p.rstrip("/\\")) or p)
    return out


def _slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()[:40] or "setup"


def setup_key(s):
    return os.path.normcase(os.path.join(s["lib"], s["id"]))


def scan():
    """Every setup in every library, plus ToolSets."""
    items = []
    for lib, label, writable in libraries():
        if not os.path.isdir(lib):
            continue
        for name in sorted(os.listdir(lib)):
            folder = os.path.join(lib, name)
            meta_path = os.path.join(folder, "meta.json")
            if not os.path.isfile(meta_path) or not os.path.isfile(os.path.join(folder, "setup.nk")):
                continue
            try:
                with io.open(meta_path, encoding="utf-8", errors="replace") as fh:
                    meta = json.load(fh)
                if not isinstance(meta, dict):
                    continue
            except Exception:
                continue
            meta.update({"id": name, "lib": lib, "lib_label": label, "writable": writable,
                         "nk": os.path.join(folder, "setup.nk"),
                         "thumb_path": os.path.join(folder, "thumb.png") if os.path.isfile(os.path.join(folder, "thumb.png")) else ""})
            meta.setdefault("name", name)
            meta.setdefault("category", "Uncategorised")
            meta.setdefault("tags", [])
            items.append(meta)
    items += scan_toolsets()
    return items


def toolset_folders():
    dirs = []
    try:
        dirs = list(nuke.pluginPath())
    except Exception:
        pass
    dirs.append(NUKE_HOME)
    out, seen = [], set()
    for d in dirs:
        ts = os.path.join(d, "ToolSets")
        key = os.path.normcase(os.path.normpath(ts))
        if os.path.isdir(ts) and key not in seen:
            seen.add(key)
            out.append(ts)
    return out


def scan_toolsets():
    items = []
    for ts in toolset_folders():
        for dirpath, dirnames, filenames in os.walk(ts):
            for f in sorted(filenames):
                if not f.lower().endswith(".nk"):
                    continue
                path = os.path.join(dirpath, f)
                sub = os.path.relpath(dirpath, ts)
                items.append({"id": path, "lib": ts, "lib_label": "ToolSets", "writable": False, "nk": path,
                              "thumb_path": "", "name": os.path.splitext(f)[0],
                              "category": TOOLSETS_CAT + ("" if sub == "." else " / " + sub.replace(os.sep, " / ")),
                              "tags": ["toolset"], "desc": "Nuke ToolSet: %s" % path, "toolset": True,
                              "classes": _classes_in_file(path)})
    return items


def _classes_in_file(path):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read(200000)
    except Exception:
        return []
    found = re.findall(r"^\s*([A-Z][A-Za-z0-9_]*)\s*\{", text, re.M)
    return sorted(set(c for c in found if c not in ("Root", "Viewer", "push", "set")))


# ---------------------------------------------------------------- selection analysis
def analyse_selection(nodes=None):
    nodes = nodes if nodes is not None else nuke.selectedNodes()
    names = set(n.fullName() for n in nodes)
    classes = sorted(set(n.Class() for n in nodes))
    external = 0
    for n in nodes:
        try:
            for i in range(n.inputs()):
                src = n.input(i)
                if src is not None and src.fullName() not in names:
                    external += 1
        except Exception:
            pass
    return {"node_count": len(nodes), "classes": classes, "inputs": external,
            "node_names": sorted(n.name() for n in nodes)[:200]}


# ---------------------------------------------------------------- thumbnails
class _Undo(object):
    def __init__(self, name):
        self.name, self.u = name, None

    def __enter__(self):
        try:
            self.u = nuke.Undo()
            self.u.begin(self.name)
        except Exception:
            self.u = None

    def __exit__(self, *exc):
        if self.u is not None:
            try:
                self.u.end()
            except Exception:
                pass
        return False


def render_viewer_thumbnail(path, frame=None):
    """Render what the active viewer shows (its active input, current frame) to a small png."""
    viewer = nuke.activeViewer()
    if viewer is None:
        raise RuntimeError("No viewer is open.")
    vnode = viewer.node()
    idx = viewer.activeInput()
    src = vnode.input(idx) if idx is not None else None
    if src is None:
        raise RuntimeError("The viewer has nothing connected.")
    frame = nuke.frame() if frame is None else frame
    keep = nuke.selectedNodes()
    with nuke.root():
        with _Undo("Setup Library thumbnail"):
            ref = nuke.nodes.Reformat()
            ref.setInput(0, src)
            for knob, value in (("type", "to box"), ("box_width", THUMB_W), ("box_height", THUMB_H),
                                ("box_fixed", True), ("resize", "fit"), ("black_outside", True)):
                try:
                    ref[knob].setValue(value)
                except Exception:
                    pass
            w = nuke.nodes.Write()
            w.setInput(0, ref)
            w["file"].setValue(path.replace("\\", "/"))
            for knob, value in (("file_type", "png"), ("channels", "rgb")):
                try:
                    w[knob].setValue(value)
                except Exception:
                    pass
            try:
                nuke.execute(w, int(frame), int(frame))
            finally:
                nuke.delete(w)
                nuke.delete(ref)
    for n in nuke.selectedNodes():
        n.setSelected(False)
    for n in keep:
        try:
            n.setSelected(True)
        except Exception:
            pass
    return os.path.isfile(path)


def set_thumbnail(setup, mode, image_file=None):
    """mode: 'viewer', 'file' or 'none'."""
    folder = os.path.join(setup["lib"], setup["id"])
    path = os.path.join(folder, "thumb.png")
    if mode == "viewer":
        tmp = os.path.join(folder, "thumb_new.png")
        if render_viewer_thumbnail(tmp):
            os.replace(tmp, path)
            return True
        return False
    if mode == "file" and image_file:
        img = QtGui.QImage(image_file)
        if img.isNull():
            raise RuntimeError("Couldn't read %s" % image_file)
        img = img.scaled(THUMB_W, THUMB_H, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        img.save(path, "PNG")
        return True
    if mode == "none" and os.path.isfile(path):
        os.remove(path)
    return False


# ---------------------------------------------------------------- save / update / insert / delete
def _write_meta(folder, meta):
    keep = dict((k, v) for k, v in meta.items()
                if k not in ("id", "lib", "lib_label", "writable", "nk", "thumb_path"))
    tmp = os.path.join(folder, "meta.json.tmp")
    with io.open(tmp, "w", encoding="utf-8") as fh:
        json.dump(keep, fh, indent=1)
    os.replace(tmp, os.path.join(folder, "meta.json"))


def save_selection(name, category="Uncategorised", tags=None, desc="", thumb="viewer", image_file=None, library=None):
    """Save the selected nodes as a new setup. Returns the setup dict."""
    nodes = nuke.selectedNodes()
    if not nodes:
        raise ValueError("Select the nodes you want to save first.")
    library = library or DEFAULT_LIBRARY
    if not os.path.isdir(library):
        os.makedirs(library)
    sid = "%s_%s" % (_slug(name), time.strftime("%Y%m%d%H%M%S"))
    folder = os.path.join(library, sid)
    os.makedirs(folder)
    nk_path = os.path.join(folder, "setup.nk").replace("\\", "/")
    nuke.nodeCopy(nk_path)
    # nodeCopy's return value is not a reliable success flag (Nuke 16 may
    # return None even when the file is written), so verify the file itself.
    if not os.path.isfile(nk_path) or os.path.getsize(nk_path) == 0:
        shutil.rmtree(folder, ignore_errors=True)
        raise ValueError("Nothing was copied: select the nodes first.")
    now = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        nuke_version = nuke.NUKE_VERSION_STRING
    except AttributeError:
        nuke_version = ""
    meta = {"name": name, "category": category or "Uncategorised", "tags": [t for t in (tags or []) if t],
            "desc": desc, "author": getpass.getuser(), "created": now, "updated": now, "nuke": nuke_version}
    meta.update(analyse_selection(nodes))
    _write_meta(folder, meta)
    setup = dict(meta, id=sid, lib=library)
    thumb_error = None
    if thumb in ("viewer", "file"):
        try:
            set_thumbnail(setup, thumb, image_file)
        except Exception as exc:
            thumb_error = str(exc)
    setup["thumb_error"] = thumb_error
    return setup


def update_info(setup, **changes):
    folder = os.path.join(setup["lib"], setup["id"])
    with io.open(os.path.join(folder, "meta.json"), encoding="utf-8", errors="replace") as fh:
        meta = json.load(fh)
    meta.update(changes)
    meta["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    _write_meta(folder, meta)


def update_nodes(setup):
    """Replace a setup's nodes with the current selection."""
    nodes = nuke.selectedNodes()
    if not nodes:
        raise ValueError("Select the nodes to store in this setup.")
    folder = os.path.join(setup["lib"], setup["id"])
    tmp = os.path.join(folder, "setup_new.nk")
    nuke.nodeCopy(tmp.replace("\\", "/"))
    if not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
        raise ValueError("Nothing was copied.")
    os.replace(tmp, os.path.join(folder, "setup.nk"))
    update_info(setup, **analyse_selection(nodes))


def insert(setup):
    """Paste a setup into the script, connected to the selected node like Ctrl+V."""
    with _Undo("Insert setup: %s" % setup["name"]):
        result = nuke.nodePaste(setup["nk"].replace("\\", "/"))
    p = load_prefs()
    usage = p.setdefault("usage", {})
    u = usage.setdefault(setup_key(setup), {"count": 0, "last": 0})
    u["count"] += 1
    u["last"] = time.time()
    save_prefs(p)
    return result


def delete_setup(setup):
    if setup.get("toolset") or not setup.get("writable", True):
        raise ValueError("This setup is read-only.")
    shutil.rmtree(os.path.join(setup["lib"], setup["id"]))


def toggle_favourite(setup):
    p = load_prefs()
    favs = set(p.get("favourites", []))
    key = setup_key(setup)
    if key in favs:
        favs.discard(key)
    else:
        favs.add(key)
    p["favourites"] = sorted(favs)
    save_prefs(p)
    return key in favs


def search_text(s):
    return " ".join([s.get("name", ""), s.get("category", ""), " ".join(s.get("tags", [])), s.get("desc", ""),
                     " ".join(s.get("classes", [])), " ".join(s.get("node_names", [])), s.get("author", ""),
                     s.get("lib_label", "")]).lower()


def filter_setups(items, query="", view="All", sort="Name"):
    p = load_prefs()
    favs, usage = set(p.get("favourites", [])), p.get("usage", {})
    words = query.lower().split()
    out = []
    for s in items:
        key = setup_key(s)
        if view == "Favourites" and key not in favs:
            continue
        if view == "Recent" and key not in usage:
            continue
        if view not in ("All", "Favourites", "Recent", "Most used") and not (s["category"] == view or s["category"].startswith(view + " / ")):
            continue
        if view == "Most used" and key not in usage:
            continue
        text = search_text(s)
        if all(w in text for w in words):
            out.append(s)
    if sort == "Recent" or view == "Recent":
        out.sort(key=lambda s: -usage.get(setup_key(s), {}).get("last", 0))
    elif sort == "Most used" or view == "Most used":
        out.sort(key=lambda s: -usage.get(setup_key(s), {}).get("count", 0))
    elif sort == "Newest":
        out.sort(key=lambda s: s.get("created", ""), reverse=True)
    else:
        out.sort(key=lambda s: s.get("name", "").lower())
    return out


# ---------------------------------------------------------------- UI
_instance = None


def _exec_menu(menu, pos):
    run = getattr(menu, "exec_", None) or getattr(menu, "exec")
    return run(pos)


def _exec(dlg):
    run = getattr(dlg, "exec_", None) or getattr(dlg, "exec")
    return run()
ACCENT = QtGui.QColor(240, 160, 67)


def placeholder_icon(setup, w=THUMB_W, h=THUMB_H):
    pm = QtGui.QPixmap(w, h)
    pm.fill(QtGui.QColor(38, 40, 44))
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    # a few node boxes, one per class (up to 4), wired top to bottom
    classes = (setup.get("classes") or ["Node"])[:4]
    bw, bh = w * 0.34, h * 0.13
    x = (w - bw) / 2
    gap = (h - len(classes) * bh) / (len(classes) + 1)
    for i, c in enumerate(classes):
        y = gap + i * (bh + gap)
        if i:
            p.setPen(QtGui.QPen(QtGui.QColor(120, 124, 132), 2))
            p.drawLine(QtCore.QPointF(w / 2, y - gap), QtCore.QPointF(w / 2, y))
        p.setPen(QtGui.QPen(ACCENT if i == 0 else QtGui.QColor(140, 146, 156), 2))
        p.setBrush(QtGui.QColor(58, 61, 67))
        p.drawRoundedRect(QtCore.QRectF(x, y, bw, bh), 6, 6)
        f = p.font()
        f.setPointSizeF(max(8.0, bh * 0.38))
        p.setFont(f)
        p.setPen(QtGui.QColor(225, 228, 232))
        p.drawText(QtCore.QRectF(x, y, bw, bh), QtCore.Qt.AlignCenter, c)
    p.setPen(QtGui.QColor(150, 155, 165))
    f = p.font()
    f.setPointSizeF(h * 0.06)
    p.setFont(f)
    p.drawText(QtCore.QRectF(8, h - h * 0.11, w - 16, h * 0.1), QtCore.Qt.AlignRight,
               "%s nodes" % setup.get("node_count", "?") if not setup.get("toolset") else "ToolSet")
    p.end()
    return pm


class SaveDialog(QtWidgets.QDialog):
    """Name, category, tags, description, thumbnail source and target library."""

    def __init__(self, categories, setup=None, parent=None):
        super(SaveDialog, self).__init__(parent)
        self.setWindowTitle("Edit setup" if setup else "Save setup")
        self.setMinimumWidth(460)
        form = QtWidgets.QFormLayout(self)
        self.name = QtWidgets.QLineEdit(setup["name"] if setup else "")
        self.name.setPlaceholderText("e.g. Green screen key + despill")
        form.addRow("Name", self.name)
        self.category = QtWidgets.QComboBox()
        self.category.setEditable(True)
        cats = sorted(set(c for c in categories if not c.startswith(TOOLSETS_CAT)) | {"Uncategorised"})
        self.category.addItems(cats)
        self.category.setCurrentText(setup["category"] if setup else (cats[0] if cats else "Uncategorised"))
        form.addRow("Category", self.category)
        self.tags = QtWidgets.QLineEdit(", ".join(setup.get("tags", [])) if setup else "")
        self.tags.setPlaceholderText("comma separated: key, despill, hair")
        form.addRow("Tags", self.tags)
        self.desc = QtWidgets.QPlainTextEdit(setup.get("desc", "") if setup else "")
        self.desc.setPlaceholderText("What it does, what it expects as input, anything to watch out for.")
        self.desc.setFixedHeight(90)
        form.addRow("Description", self.desc)
        self.thumb = QtWidgets.QComboBox()
        opts = ["Keep current", "Render from viewer", "Image file…", "No thumbnail"] if setup else ["Render from viewer", "Image file…", "No thumbnail"]
        self.thumb.addItems(opts)
        form.addRow("Thumbnail", self.thumb)
        self.image_file = None
        self.thumb.activated.connect(self._maybe_pick)
        self.lib = QtWidgets.QComboBox()
        for path, label, writable in libraries():
            if writable:
                self.lib.addItem("%s  (%s)" % (label, path), path)
        if setup:
            self.lib.setEnabled(False)
        else:
            last = load_prefs().get("save_to")
            i = self.lib.findData(last)
            if i >= 0:
                self.lib.setCurrentIndex(i)
            form.addRow("Save to", self.lib)
        if not setup:
            info = analyse_selection()
            note = QtWidgets.QLabel("%d node%s selected · %s%s" % (
                info["node_count"], "" if info["node_count"] == 1 else "s", ", ".join(info["classes"][:8]),
                ("  ·  expects %d input%s" % (info["inputs"], "" if info["inputs"] == 1 else "s")) if info["inputs"] else ""))
            note.setWordWrap(True)
            note.setStyleSheet("color: #a0a0a0;")
            form.addRow(note)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _maybe_pick(self, *a):
        if self.thumb.currentText().startswith("Image file"):
            f, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Thumbnail image", "", "Images (*.png *.jpg *.jpeg *.tif *.tiff *.exr *.bmp)")
            self.image_file = f or None
            if not f:
                self.thumb.setCurrentIndex(0)

    def _accept(self):
        if not self.name.text().strip():
            self.name.setFocus()
            return
        self.accept()

    def result_values(self):
        t = self.thumb.currentText()
        mode = "keep" if t.startswith("Keep") else "viewer" if t.startswith("Render") else "file" if t.startswith("Image") else "none"
        return {"name": self.name.text().strip(), "category": self.category.currentText().strip() or "Uncategorised",
                "tags": [x.strip() for x in self.tags.text().split(",") if x.strip()],
                "desc": self.desc.toPlainText().strip(), "thumb": mode, "image_file": self.image_file,
                "library": self.lib.currentData()}


class SetupLibraryPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(SetupLibraryPanel, self).__init__(parent)
        global _instance
        _instance = self
        self.items = []
        self.icon_cache = {}
        self._build()
        self.reload()

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        top = QtWidgets.QHBoxLayout()
        save = QtWidgets.QPushButton("Save selected nodes…")
        save.setStyleSheet("QPushButton { font-weight: bold; padding: 5px 12px; }")
        save.clicked.connect(self.save_selected)
        top.addWidget(save)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search names, tags, descriptions and node types…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refill)
        self.search.returnPressed.connect(self._insert_current)
        top.addWidget(self.search, 1)
        self.sort = QtWidgets.QComboBox()
        self.sort.addItems(["Name", "Newest", "Recent", "Most used"])
        self.sort.currentIndexChanged.connect(self.refill)
        top.addWidget(self.sort)
        self.size = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.size.setRange(100, 320)
        self.size.setValue(int(load_prefs().get("icon_size", 180)))
        self.size.setFixedWidth(90)
        self.size.setToolTip("Thumbnail size")
        self.size.valueChanged.connect(self._resize_icons)
        top.addWidget(self.size)
        gear = QtWidgets.QToolButton()
        gear.setText("Libraries…")
        gear.clicked.connect(self.edit_libraries)
        top.addWidget(gear)
        root.addLayout(top)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        root.addWidget(split, 1)
        self.views = QtWidgets.QListWidget()
        self.views.setMaximumWidth(220)
        self.views.currentItemChanged.connect(self.refill)
        split.addWidget(self.views)

        self.grid = QtWidgets.QListWidget()
        self.grid.setViewMode(QtWidgets.QListView.IconMode)
        self.grid.setResizeMode(QtWidgets.QListView.Adjust)
        self.grid.setMovement(QtWidgets.QListView.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setWordWrap(True)
        self.grid.setSpacing(8)
        self.grid.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._context_menu)
        self.grid.itemDoubleClicked.connect(lambda it: self.insert(it.data(QtCore.Qt.UserRole)))
        self.grid.currentItemChanged.connect(self._show_details)
        split.addWidget(self.grid)

        side = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(side)
        sl.setContentsMargins(8, 0, 0, 0)
        self.d_thumb = QtWidgets.QLabel()
        self.d_thumb.setMinimumSize(240, 135)
        self.d_thumb.setAlignment(QtCore.Qt.AlignCenter)
        sl.addWidget(self.d_thumb)
        self.d_title = QtWidgets.QLabel()
        f = self.d_title.font()
        f.setPointSize(f.pointSize() + 3)
        f.setBold(True)
        self.d_title.setFont(f)
        self.d_title.setWordWrap(True)
        sl.addWidget(self.d_title)
        self.d_meta = QtWidgets.QLabel()
        self.d_meta.setWordWrap(True)
        self.d_meta.setStyleSheet("color: #a0a0a0;")
        sl.addWidget(self.d_meta)
        self.d_desc = QtWidgets.QLabel()
        self.d_desc.setWordWrap(True)
        self.d_desc.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        sl.addWidget(self.d_desc)
        sl.addStretch(1)
        row = QtWidgets.QHBoxLayout()
        self.b_insert = QtWidgets.QPushButton("Insert")
        self.b_insert.setStyleSheet("QPushButton { font-weight: bold; padding: 5px 14px; }")
        self.b_insert.clicked.connect(self._insert_current)
        row.addWidget(self.b_insert)
        self.b_fav = QtWidgets.QPushButton("☆ Favourite")
        self.b_fav.clicked.connect(self._fav_current)
        row.addWidget(self.b_fav)
        sl.addLayout(row)
        row2 = QtWidgets.QHBoxLayout()
        self.b_edit = QtWidgets.QPushButton("Edit…")
        self.b_edit.clicked.connect(lambda: self.edit(self.current()))
        row2.addWidget(self.b_edit)
        self.b_update = QtWidgets.QPushButton("Replace nodes with selection")
        self.b_update.clicked.connect(lambda: self.replace_nodes(self.current()))
        row2.addWidget(self.b_update)
        sl.addLayout(row2)
        split.addWidget(side)
        split.setStretchFactor(1, 3)
        split.setSizes([170, 600, 280])
        self._resize_icons(self.size.value(), save=False)

    # ---- data
    def reload(self, select_key=None):
        self.items = scan()
        self.icon_cache = {}
        cur_view = self.views.currentItem().text().split("  (")[0] if self.views.currentItem() else "All"
        self.views.blockSignals(True)
        self.views.clear()
        p = load_prefs()
        favs, usage = set(p.get("favourites", [])), p.get("usage", {})
        counts = {}
        for s in self.items:
            counts[s["category"]] = counts.get(s["category"], 0) + 1
        entries = [("All", len(self.items)), ("Favourites", sum(1 for s in self.items if setup_key(s) in favs)),
                   ("Recent", sum(1 for s in self.items if setup_key(s) in usage)),
                   ("Most used", sum(1 for s in self.items if setup_key(s) in usage))]
        entries += sorted(counts.items(), key=lambda kv: (kv[0].startswith(TOOLSETS_CAT), kv[0].lower()))
        for name, n in entries:
            it = QtWidgets.QListWidgetItem("%s  (%d)" % (name, n))
            it.setData(QtCore.Qt.UserRole, name)
            if name in ("All", "Favourites", "Recent", "Most used"):
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            self.views.addItem(it)
            if name == cur_view:
                self.views.setCurrentItem(it)
        if self.views.currentItem() is None:
            self.views.setCurrentRow(0)
        self.views.blockSignals(False)
        self.refill(select_key=select_key)

    def view_name(self):
        it = self.views.currentItem()
        return it.data(QtCore.Qt.UserRole) if it else "All"

    def _icon(self, s):
        key = setup_key(s)
        if key not in self.icon_cache:
            pm = QtGui.QPixmap(s["thumb_path"]) if s.get("thumb_path") else QtGui.QPixmap()
            if pm.isNull():
                pm = placeholder_icon(s)
            self.icon_cache[key] = pm
        return self.icon_cache[key]

    def refill(self, *a, **kw):
        select_key = kw.get("select_key")
        cur = self.current()
        cur_key = select_key or (setup_key(cur) if cur else None)
        self.grid.clear()
        favs = set(load_prefs().get("favourites", []))
        shown = filter_setups(self.items, self.search.text(), self.view_name(), self.sort.currentText())
        for s in shown:
            label = ("★ " if setup_key(s) in favs else "") + s["name"]
            it = QtWidgets.QListWidgetItem(QtGui.QIcon(self._icon(s)), label)
            it.setData(QtCore.Qt.UserRole, s)
            it.setToolTip("%s\n%s" % (s["name"], s.get("desc", "")))
            self.grid.addItem(it)
            if cur_key and setup_key(s) == cur_key:
                self.grid.setCurrentItem(it)
        if self.grid.currentItem() is None and self.grid.count():
            self.grid.setCurrentRow(0)
        if not shown:
            self._show_details(None)

    def _resize_icons(self, v, save=True):
        h = int(v * 9 / 16)
        self.grid.setIconSize(QtCore.QSize(v, h))
        self.grid.setGridSize(QtCore.QSize(v + 16, h + 42))
        if save:
            p = load_prefs()
            p["icon_size"] = v
            save_prefs(p)

    def current(self):
        it = self.grid.currentItem()
        return it.data(QtCore.Qt.UserRole) if it else None

    def _show_details(self, *a):
        s = self.current()
        enabled = s is not None
        for b in (self.b_insert, self.b_fav):
            b.setEnabled(enabled)
        editable = enabled and s.get("writable") and not s.get("toolset")
        self.b_edit.setEnabled(bool(editable))
        self.b_update.setEnabled(bool(editable))
        if not s:
            self.d_title.setText("No setups here yet" if not self.items else "Nothing matches")
            self.d_meta.setText("")
            self.d_desc.setText("Select some nodes and press Save selected nodes…" if not self.items else "Try another word or view.")
            self.d_thumb.clear()
            return
        pm = self._icon(s).scaled(260, 146, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.d_thumb.setPixmap(pm)
        self.d_title.setText(s["name"])
        bits = [s["category"]]
        if s.get("node_count"):
            bits.append("%d nodes" % s["node_count"])
        if s.get("inputs"):
            bits.append("expects %d input%s" % (s["inputs"], "" if s["inputs"] == 1 else "s"))
        if s.get("author"):
            bits.append("by %s" % s["author"])
        if s.get("updated"):
            bits.append(s["updated"][:10])
        bits.append(s.get("lib_label", ""))
        tags = ("\nTags: " + ", ".join(s["tags"])) if s.get("tags") else ""
        classes = ("\nNodes: " + ", ".join(s.get("classes", [])[:12])) if s.get("classes") else ""
        self.d_meta.setText("  ·  ".join(b for b in bits if b) + tags + classes)
        self.d_desc.setText(s.get("desc", ""))
        fav = setup_key(s) in set(load_prefs().get("favourites", []))
        self.b_fav.setText("★ Favourite" if fav else "☆ Favourite")

    # ---- actions
    def insert(self, s):
        if not s:
            return
        try:
            insert(s)
        except Exception as exc:
            nuke.message("Couldn't insert %s:\n%s" % (s["name"], exc))

    def _insert_current(self):
        self.insert(self.current())

    def _fav_current(self):
        s = self.current()
        if s:
            toggle_favourite(s)
            self.reload(select_key=setup_key(s))

    def save_selected(self):
        if not nuke.selectedNodes():
            nuke.message("Select the nodes you want to save first.")
            return
        dlg = SaveDialog([s["category"] for s in self.items], parent=self)
        if _exec(dlg) != QtWidgets.QDialog.Accepted:
            return
        v = dlg.result_values()
        try:
            s = save_selection(v["name"], v["category"], v["tags"], v["desc"], v["thumb"], v["image_file"], v["library"])
        except Exception as exc:
            nuke.message("Couldn't save: %s" % exc)
            return
        p = load_prefs()
        p["save_to"] = v["library"]
        save_prefs(p)
        if s.get("thumb_error"):
            nuke.message("Saved, but the thumbnail couldn't be made: %s\nUse Edit… to add one later." % s["thumb_error"])
        self.reload(select_key=setup_key(s))

    def edit(self, s):
        if not s or s.get("toolset") or not s.get("writable"):
            return
        dlg = SaveDialog([x["category"] for x in self.items], setup=s, parent=self)
        if _exec(dlg) != QtWidgets.QDialog.Accepted:
            return
        v = dlg.result_values()
        try:
            update_info(s, name=v["name"], category=v["category"], tags=v["tags"], desc=v["desc"])
            if v["thumb"] != "keep":
                set_thumbnail(s, v["thumb"], v["image_file"])
        except Exception as exc:
            nuke.message("Couldn't update: %s" % exc)
        self.reload(select_key=setup_key(s))

    def replace_nodes(self, s):
        if not s or not s.get("writable") or s.get("toolset"):
            return
        if not nuke.ask("Replace the nodes in '%s' with the %d selected nodes?" % (s["name"], len(nuke.selectedNodes()))):
            return
        try:
            update_nodes(s)
        except Exception as exc:
            nuke.message(str(exc))
        self.reload(select_key=setup_key(s))

    def _context_menu(self, pos):
        it = self.grid.itemAt(pos)
        if it is None:
            return
        s = it.data(QtCore.Qt.UserRole)
        editable = s.get("writable") and not s.get("toolset")
        m = QtWidgets.QMenu(self)
        m.addAction("Insert", lambda: self.insert(s))
        m.addAction("Toggle favourite", lambda: (toggle_favourite(s), self.reload(select_key=setup_key(s))))
        m.addSeparator()
        for label, fn in (("Edit…", lambda: self.edit(s)), ("Replace nodes with selection", lambda: self.replace_nodes(s)),
                          ("Thumbnail from viewer", lambda: self._thumb(s, "viewer"))):
            a = m.addAction(label, fn)
            a.setEnabled(bool(editable))
        m.addAction("Show in folder", lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(os.path.dirname(s["nk"]))))
        m.addSeparator()
        d = m.addAction("Delete…", lambda: self._delete(s))
        d.setEnabled(bool(editable))
        _exec_menu(m, self.grid.mapToGlobal(pos))

    def _thumb(self, s, mode):
        try:
            set_thumbnail(s, mode)
        except Exception as exc:
            nuke.message("Couldn't make the thumbnail: %s" % exc)
        self.reload(select_key=setup_key(s))

    def _delete(self, s):
        if nuke.ask("Delete '%s'? This removes its folder from %s." % (s["name"], s["lib_label"])):
            try:
                delete_setup(s)
            except Exception as exc:
                nuke.message(str(exc))
            self.reload()

    def edit_libraries(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Setup libraries")
        dlg.setMinimumWidth(520)
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.addWidget(QtWidgets.QLabel("Your own library is always %s.\nAdd shared folders (a team drive, a show folder) here. "
                                       "Folders in the %s environment variable are added too." % (DEFAULT_LIBRARY, ENV_VAR)))
        lst = QtWidgets.QListWidget()
        lst.addItems(load_prefs().get("extra_libraries", []))
        lay.addWidget(lst)
        row = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton("Add folder…")
        rem = QtWidgets.QPushButton("Remove")
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        lay.addLayout(row)
        add.clicked.connect(lambda: (lambda d: d and lst.addItem(d))(QtWidgets.QFileDialog.getExistingDirectory(dlg, "Library folder")))
        rem.clicked.connect(lambda: [lst.takeItem(lst.row(i)) for i in lst.selectedItems()])
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if _exec(dlg) == QtWidgets.QDialog.Accepted:
            p = load_prefs()
            p["extra_libraries"] = [lst.item(i).text() for i in range(lst.count())]
            save_prefs(p)
            self.reload()


# ---------------------------------------------------------------- install
def show():
    if _instance is not None:
        try:
            if _instance.isVisible():
                _instance.raise_()
                _instance.reload()
                _instance.search.setFocus()
                return _instance
        except RuntimeError:
            pass
    if _nkpanels is None:
        raise RuntimeError("Sleepy Library needs Nuke's GUI.")
    panel = _nkpanels.registerWidgetAsPanel("sleepy_library.SetupLibraryPanel", PANEL_TITLE, PANEL_ID, True)
    pane = nuke.getPaneFor("Properties.1") or nuke.getPaneFor("DAG.1")
    if pane is not None:
        panel.addToPane(pane)
    else:
        panel.addToPane()
    return panel


def quick_save():
    """Save selected nodes without opening the panel (menu command / shortcut)."""
    if not nuke.selectedNodes():
        nuke.message("Select the nodes you want to save first.")
        return
    dlg = SaveDialog([s["category"] for s in scan()], parent=QtWidgets.QApplication.activeWindow())
    if _exec(dlg) != QtWidgets.QDialog.Accepted:
        return
    v = dlg.result_values()
    try:
        s = save_selection(v["name"], v["category"], v["tags"], v["desc"], v["thumb"], v["image_file"], v["library"])
    except Exception as exc:
        nuke.message("Couldn't save: %s" % exc)
        return
    if s.get("thumb_error"):
        nuke.message("Saved, but the thumbnail couldn't be made: %s" % s["thumb_error"])
    if _instance is not None:
        try:
            _instance.reload(select_key=setup_key(s))
        except RuntimeError:
            pass


_installed = False


def install(menu="SleepyTools", save_shortcut=""):
    global _installed
    if _installed:
        return
    if getattr(nuke, "_sleepy_setup_library_installed", False):
        _installed = True           # installed by an earlier copy of this module
        return
    if _nkpanels is not None:
        _nkpanels.registerWidgetAsPanel("sleepy_library.SetupLibraryPanel", PANEL_TITLE, PANEL_ID)
    m = nuke.menu("Nuke").addMenu(menu)
    m.addCommand("Setup Library", "sleepy_library.show()")
    m.addCommand("Save selected to Setup Library…", "sleepy_library.quick_save()", save_shortcut)
    nuke.menu("Node Graph").addCommand("Sleepy Save selected to Setup Library…", "sleepy_library.quick_save()")
    nuke._sleepy_setup_library_installed = True
    _installed = True
