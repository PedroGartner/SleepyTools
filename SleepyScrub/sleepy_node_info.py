"""
sleepy_node_info.py  -  Sleepy Node Info
==========================================
Two things for Nuke's Node Graph, nothing else:

1. Crosshair cursor   a yellow gapped crosshair with a centre dot as the
                      cursor everywhere inside Nuke.
2. Hover info card    rest the mouse on a node and a small card shows its
                      resolution, format, frame range, layers, file and
                      cook time (cook time only when profiling is on).

3. View keys         F1 Front (A) / F2 Back (B) / F3 Matte (mask) / F4 Result
                      of the selected node, Flame style.
4. Iterations         Alt+Shift+I saves a numbered copy beside the script
                      (<script>_iterations/<script>_it001.nk), script untouched.
5. Copy info          Alt+Shift+C copies the hovered (or selected) node's
                      card as plain text.
6. Compare            select exactly two nodes for a side-by-side diff
                      toast: resolution, format, frames, layers, colorspace.
                      Mismatches are highlighted.

Nodes, connections and colours are never touched.

Menu: SleepyTools > Node Info. Menu toggles are remembered across launches in a
per-user JSON: %LOCALAPPDATA%\SleepyTools\sleepy_node_info.json

Install: keep it next to the menu.py that imports it (it switches itself
on when imported), or put it in ~/.nuke and add to menu.py:
    import sleepy_node_info
"""

import html
import json
import os
import re
import sys
import time

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

try:
    import nuke
except ImportError:
    nuke = None

# make "import sleepy_node_info" work when an auto-installer exec's the file
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    if _HERE not in sys.path:
        sys.path.append(_HERE)
except NameError:
    pass
if (__name__ != "sleepy_node_info" and "sleepy_node_info" not in sys.modules
        and sys.modules.get(__name__) is not None):
    sys.modules["sleepy_node_info"] = sys.modules[__name__]


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class Settings(object):
    cursor = True
    card = True
    yellow = "#f5c518"      # idle (also the card accent)
    color_node = "#ffffff"  # resting on a node in the Node Graph
    color_drag = "#ff8c1a"  # left button held: moving nodes, box select...
    color_pan = "#4fc3f7"   # middle button or Alt+drag: pan / zoom
    color_busy = "#ff5c5c"  # Nuke is loading / computing
    card_delay = 0.5        # seconds the mouse rests on a node before the card
    card_max_changed = 8    # how many changed knobs the card lists

    # Node Graph / Viewer helpers
    selection_summary = True   # label near the cursor when you select 2+ nodes
    problem_badge = True       # corner badge: errors / missing frames / disabled
    badge_disabled = True      # count disabled nodes in the badge too
    badge_position = "bottom-left"   # top-left, top-center, top-right,
                                     # bottom-left, bottom-center, bottom-right
    hud_font_size = 14         # badge + viewer label text size (px)
    pipe_info = True           # rest on a pipe: from -> to, which input
    viewer_label = True        # corner label in the Viewer: what you're viewing
    cursor_arm = 6          # px, length of each arm
    cursor_gap = 3          # px, gap between centre and arms
    cursor_thickness = 2    # px
    cursor_outline = "#0b0b0b"  # outline colour
    cursor_outline_width = 1    # px, 0 = no outline
    cursor_always = True    # also replace Nuke's busy / special cursors
    modifier_badges = True  # small marks on the crosshair while Ctrl / Shift
                            # are held in the Node Graph

    # Flame-style view keys: show a node's inputs in the Viewer
    view_slot = 0           # Viewer input they use (0 = the "1" key input)
    view_keys = {"front": "F1", "back": "F2", "matte": "F3", "result": "F4"}

    # iterations (versions of the script saved beside it, script untouched)
    iteration_key = "Alt+Shift+I"
    copy_key = "Alt+Shift+C"    # copy node info as text
    view_scale = 1.0        # Node Graph pixel scale (only change if the card
                            # picks the wrong node - see debug_mapping())


SETTINGS = Settings()


# --------------------------------------------------------------------------- #
# Per-user persistence of the menu toggles
# --------------------------------------------------------------------------- #
_SETTINGS_FILE = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "SleepyTools", "sleepy_node_info.json")

_PERSISTED_TYPES = {
    "cursor": bool, "card": bool, "pipe_info": bool, "selection_summary": bool,
    "problem_badge": bool, "viewer_label": bool,
}


def load_settings():
    """Apply the saved menu toggles (silently skipped when there is none)."""
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    for key, typ in _PERSISTED_TYPES.items():
        try:
            if isinstance(data.get(key), typ):
                setattr(SETTINGS, key, data[key])
        except Exception:
            pass


def save_settings():
    """Write the current menu toggles (atomic temp file + replace)."""
    try:
        folder = os.path.dirname(_SETTINGS_FILE)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        data = {k: getattr(SETTINGS, k) for k in _PERSISTED_TYPES}
        tmp = _SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, _SETTINGS_FILE)
    except Exception as exc:
        print("sleepy_node_info: couldn't save settings (%s)" % exc)


load_settings()


# --------------------------------------------------------------------------- #
# 1. Crosshair cursor
# --------------------------------------------------------------------------- #
_cursor_cache = {}


def _badge_rects(c, gap):
    """Little squares in the empty corners: Ctrl = bottom-right, Shift = top-right."""
    R = QtCore.QRectF
    return {"ctrl": R(c + gap + 1, c + gap + 1, 3, 3),
            "shift": R(c + gap + 1, c - gap - 4, 3, 3)}


def crosshair_cursor(color=None, badges=()):
    s = SETTINGS
    color = color or s.yellow
    ow = s.cursor_outline_width
    badges = tuple(sorted(badges))
    key = (color, s.cursor_arm, s.cursor_gap, s.cursor_thickness,
           s.cursor_outline, ow, badges)
    if key in _cursor_cache:
        return _cursor_cache[key]

    arm, gap, t = s.cursor_arm, s.cursor_gap, s.cursor_thickness
    half = gap + arm + 1 + ow
    size = half * 2 + 1                       # odd size -> exact centre pixel
    screen = QtGui.QGuiApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0

    pm = QtGui.QPixmap(int(round(size * dpr)), int(round(size * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setPen(QtCore.Qt.NoPen)

    c = half + 0.5                            # centre of the middle pixel
    o = t / 2.0
    R = QtCore.QRectF
    shapes = [R(c - o, c - gap - arm, t, arm),    # top
              R(c - o, c + gap, t, arm),          # bottom
              R(c - gap - arm, c - o, arm, t),    # left
              R(c + gap, c - o, arm, t),          # right
              R(c - o, c - o, t, t)]              # centre dot
    corner = _badge_rects(c, gap)
    shapes += [corner[b] for b in badges]

    if ow > 0:                                # dark outline first
        p.setBrush(QtGui.QColor(s.cursor_outline))
        for r in shapes:
            p.drawRect(r.adjusted(-ow, -ow, ow, ow))
    p.setBrush(QtGui.QColor(color))           # colour on top
    for r in shapes:
        p.drawRect(r)
    p.end()

    cur = QtGui.QCursor(pm, half, half)
    _cursor_cache[key] = cur
    return cur


def _dag_widgets():
    """Every Node Graph widget (root and open Group graphs) and its children."""
    out = []
    for w in QtWidgets.QApplication.instance().allWidgets():
        if w.objectName().startswith("DAG"):
            out.append(w)
            out.extend(w.findChildren(QtWidgets.QWidget))
    return out


def _root_dag():
    for w in QtWidgets.QApplication.instance().allWidgets():
        if w.objectName() == "DAG.1":
            return w
    return None


def _view_widget(dag):
    """The part of the panel that actually shows the graph. In Nuke 16 that's
    a QWindowContainer holding a native window (not the whole panel, which
    also has the tab/toolbar area)."""
    best, area = None, 0
    for c in dag.findChildren(QtWidgets.QWidget):
        if c.metaObject().className() == "QWindowContainer" and c.isVisible():
            a = c.width() * c.height()
            if a > area:
                best, area = c, a
    return best or dag


def _embedded_window(container):
    """The native QWindow inside a QWindowContainer (where cursors must go)."""
    if container.metaObject().className() != "QWindowContainer":
        return None
    top_left = container.mapToGlobal(QtCore.QPoint(0, 0))
    for w in QtGui.QGuiApplication.allWindows():
        try:
            if (w.parent() is not None and w.isVisible()
                    and w.mapToGlobal(QtCore.QPoint(0, 0)) == top_left):
                return w
        except Exception:
            pass
    return None


_reported = set()


def _report(where, exc):
    """Print each distinct error once instead of hiding it."""
    msg = "%s: %s" % (where, exc)
    if msg not in _reported:
        _reported.add(msg)
        print("sleepy_node_info error | %s" % msg)


_sig_cache = {}


def _signature(cur, cache=False):
    """Identity of a cursor image: size, hotspot and centre colour."""
    if cache and id(cur) in _sig_cache:
        return _sig_cache[id(cur)][1]
    sig = _compute_signature(cur)
    if cache:
        _sig_cache[id(cur)] = (cur, sig)       # keep cur alive so id stays valid
    return sig


def _compute_signature(cur):
    try:
        if cur.shape() != QtCore.Qt.BitmapCursor:
            return None
        img = cur.pixmap().toImage()
        sig = [img.width(), img.height(), cur.hotSpot().x(), cur.hotSpot().y(),
               img.pixelColor(img.width() // 2, img.height() // 2).name()]
        # badge corners (scaled for hi-DPI)
        s = SETTINGS
        half = s.cursor_gap + s.cursor_arm + 1 + s.cursor_outline_width
        scale = img.width() / float(half * 2 + 1)
        for r in _badge_rects(half + 0.5, s.cursor_gap).values():
            x = int(r.center().x() * scale)
            y = int(r.center().y() * scale)
            if 0 <= x < img.width() and 0 <= y < img.height():
                sig.append(img.pixelColor(x, y).name())
        return tuple(sig)
    except Exception:
        return None


def _cursor_color(cur):
    try:
        img = cur.pixmap().toImage()
        return img.pixelColor(img.width() // 2, img.height() // 2).name()
    except Exception:
        return None


def _same_cursor(a, b):
    try:
        return (a.shape() == QtCore.Qt.BitmapCursor
                and a.hotSpot() == b.hotSpot()
                and a.pixmap().size() == b.pixmap().size())
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# 2. Hover info card
# --------------------------------------------------------------------------- #
class _InfoCard(QtWidgets.QWidget):
    def __init__(self):
        flags = (QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint
                 | QtCore.Qt.WindowStaysOnTopHint)
        super(_InfoCard, self).__init__(None, flags)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.frame = QtWidgets.QFrame()
        self.frame.setObjectName("card")
        inner = QtWidgets.QVBoxLayout(self.frame)
        inner.setContentsMargins(12, 9, 14, 10)
        self.label = QtWidgets.QLabel()
        self.label.setTextFormat(QtCore.Qt.RichText)
        inner.addWidget(self.label)
        lay.addWidget(self.frame)
        self.restyle()

    def restyle(self):
        self.frame.setStyleSheet(
            "#card { background: rgba(22, 23, 25, 240);"
            " border: 1px solid #36383c; border-left: 3px solid %s;"
            " border-radius: 6px; }"
            "QLabel { color: #d9d9d9; font-size: 11px; background: transparent; }"
            % SETTINGS.yellow)

    def show_for(self, node, gpos):
        if isinstance(node, tuple):                # ("pipe", src, dst, index)
            self.label.setText(_pipe_html(*node[1:]))
        else:
            self.label.setText(_card_html(node))
        self.adjustSize()
        self._place(gpos)
        self.show()

    def _place(self, gpos):
        pos = gpos + QtCore.QPoint(20, 22)
        screen = QtGui.QGuiApplication.screenAt(gpos)
        if screen is not None:                     # keep it on screen
            area = screen.availableGeometry()
            if pos.x() + self.width() > area.right():
                pos.setX(gpos.x() - self.width() - 12)
            if pos.y() + self.height() > area.bottom():
                pos.setY(gpos.y() - self.height() - 12)
        self.move(pos)


# knobs that are UI / bookkeeping, never interesting in "Changed"
_SKIP_KNOBS = {
    "xpos", "ypos", "selected", "name", "tile_color", "gl_color", "label",
    "note_font", "note_font_size", "note_font_color", "hide_input",
    "postage_stamp", "postage_stamp_frame", "cached", "indicators",
    "dope_sheet", "bookmark", "help", "onCreate", "onDestroy", "knobChanged",
    "updateUI", "autolabel", "panel", "lifetimeStart", "lifetimeEnd",
    "useLifetime", "icon", "window", "disable", "file", "proxy", "selectable",
    "process_mask", "z_order", "bdwidth", "bdheight", "appearance", "border_width",
}
_SKIP_CLASSES = {"Tab_Knob", "Text_Knob", "Obsolete_Knob", "PyScript_Knob",
                 "Help_Knob", "Link_Knob", "PyCustom_Knob", "Script_Knob"}

GREY = "#85888d"
RED = "#ff6b6b"


def _short(text, limit=44):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit // 2 - 1] + "…" + text[-(limit // 2 - 1):]


def _knob_value(k):
    try:
        if k.isAnimated():
            return "<span style='color:%s'>animated</span>" % SETTINGS.color_pan
    except Exception:
        pass
    try:
        if k.hasExpression():
            return "<span style='color:%s'>expression</span>" % SETTINGS.color_pan
    except Exception:
        pass
    try:
        v = k.toScript()
    except Exception:
        v = k.value()
    v = str(v).strip().strip("{}").strip()
    return html.escape(_short(v, 28))


def _changed_knobs(n):
    out = []
    for name, k in n.knobs().items():
        if name in _SKIP_KNOBS or name.startswith(("gl_", "_")):
            continue
        try:
            if k.Class() in _SKIP_CLASSES or not k.notDefault():
                continue
        except Exception:
            continue
        out.append((name, _knob_value(k)))
    return out


def _warnings(n):
    w = []
    try:
        if n.hasError():
            w.append("Node has an error")
    except Exception:
        pass
    if n.Class() in ("Read", "DeepRead") and "file" in n.knobs():
        try:
            path = n["file"].evaluate()
            if path and not os.path.exists(path):
                w.append("Missing file on frame %d" % nuke.frame())
        except Exception:
            pass
    try:
        if n["disable"].value():
            w.append("Disabled")
    except Exception:
        pass
    return w


def _type_rows(n, row):
    """A few rows that matter for this kind of node."""
    e = html.escape
    cls = n.Class()
    knobs = n.knobs()

    def val(name):
        return knobs[name].value() if name in knobs else None

    if cls in ("Read", "DeepRead"):
        if val("colorspace") is not None:
            row("Colorspace", e(str(val("colorspace"))))
        if val("first") is not None and val("last") is not None:
            row("On disk", "%d &ndash; %d" % (val("first"), val("last")))
        if val("file"):
            row("File", e(_short(os.path.basename(val("file")))))
    elif cls in ("Write", "DeepWrite"):
        path = val("file") or ""
        if path:
            row("Output", e(_short(os.path.basename(path))))
            row("Folder", "<span style='color:%s'>%s</span>"
                % (GREY, e(_short(os.path.dirname(path), 48))))
        if val("file_type"):
            row("Type", e(str(val("file_type"))))
        if val("colorspace") is not None:
            row("Colorspace", e(str(val("colorspace"))))
    elif cls.startswith("Merge"):
        if val("operation"):
            row("Operation", "<b>%s</b>" % e(str(val("operation"))))
        a, b = n.input(1), n.input(0)
        row("A", e(a.name()) if a else "<span style='color:%s'>&ndash;</span>" % GREY)
        row("B", e(b.name()) if b else "<span style='color:%s'>&ndash;</span>" % GREY)
    elif isinstance(n, nuke.Group):
        try:
            row("Inside", "%d nodes" % len(n.nodes()))
        except Exception:
            pass
        try:
            f = n.filename()
            if f:
                row("Gizmo", e(_short(os.path.basename(f))))
        except Exception:
            pass


def _backdrop_html(n):
    e = html.escape
    label = (n["label"].value() or "").strip()
    try:
        count = len(n.getNodes())
    except Exception:
        count = None
    head = ("<span style='font-size:13px; font-weight:600; color:#f2f2f2'>%s</span>"
            "&nbsp;&nbsp;<span style='color:%s'>Backdrop</span>"
            % (e(_short(label.splitlines()[0] if label else n.name(), 40)), GREY))
    rows = ""
    if count is not None:
        rows += ("<tr><td style='color:%s; padding:1px 14px 1px 0'>Contains</td>"
                 "<td>%d nodes</td></tr>" % (GREY, count))
    return "%s<table style='margin-top:6px'>%s</table>" % (head, rows)


def _card_html(n):
    if n.Class() == "BackdropNode":
        return _backdrop_html(n)

    e = html.escape
    rows = []

    def row(label, value, color=None):
        rows.append(
            "<tr><td style='color:%s; padding:1px 14px 1px 0'>%s</td>"
            "<td style='padding:1px 0%s'>%s</td></tr>"
            % (color or GREY, label, "; color:%s" % color if color else "", value))

    def section(title):
        rows.append("<tr><td colspan='2' style='padding:7px 0 2px 0; color:%s;"
                    " font-size:10px; letter-spacing:1px'>%s</td></tr>"
                    % (SETTINGS.yellow, title))

    head = ("<span style='font-size:13px; font-weight:600; color:#f2f2f2'>%s</span>"
            "&nbsp;&nbsp;<span style='color:%s'>%s</span>" % (e(n.name()), GREY, e(n.Class())))

    # 1. warnings first
    for w in _warnings(n):
        row("&#9888;", "<b>%s</b>" % e(w), RED)

    # 2. what matters for this node type
    _type_rows(n, row)

    # 3. image info
    try:
        res = "%d &times; %d" % (n.width(), n.height())
        fmt = n.format().name()
        if fmt:
            res += "&nbsp;&nbsp;<span style='color:%s'>%s</span>" % (GREY, e(fmt))
        row("Resolution", res)
    except Exception:
        pass
    try:
        first, last = n.firstFrame(), n.lastFrame()
        row("Frames", "%d &ndash; %d&nbsp;&nbsp;<span style='color:%s'>(%d)</span>"
            % (first, last, GREY, last - first + 1))
    except Exception:
        pass
    try:
        bb = n.bbox()
        fw, fh = n.width(), n.height()
        if bb.x() < 0 or bb.y() < 0 or bb.x() + bb.w() > fw or bb.y() + bb.h() > fh:
            row("BBox", "%d &times; %d&nbsp;&nbsp;bigger than format"
                % (bb.w(), bb.h()), SETTINGS.color_drag)
    except Exception:
        pass
    try:
        chans = n.channels()
        layers = []
        for c in chans:
            layer = c.split(".")[0]
            if layer not in layers:
                layers.append(layer)
        shown = ", ".join(layers[:5])
        if len(layers) > 5:
            shown += "&nbsp;<span style='color:%s'>+%d</span>" % (GREY, len(layers) - 5)
        row("Layers", "%s&nbsp;&nbsp;<span style='color:%s'>%d ch</span>"
            % (shown, GREY, len(chans)))
    except Exception:
        pass
    if "premultiplied" in n.knobs():
        try:
            row("Premult", "yes" if n["premultiplied"].value() else "no")
        except Exception:
            pass
    try:
        if nuke.usingPerformanceTimers():
            info = n.performanceInfo()
            row("Cook", "%.1f ms" % (info.get("timeTakenWall", 0) / 1000.0), SETTINGS.yellow)
    except Exception:
        pass
    try:
        row("Downstream", "%d nodes" % _downstream_count(n))
    except Exception:
        pass

    # 4. what you changed on this node
    try:
        changed = _changed_knobs(n)
        if n.Class().startswith("Merge"):
            changed = [c for c in changed if c[0] != "operation"]   # shown above
        if changed:
            section("CHANGED")
            for name, value in changed[:SETTINGS.card_max_changed]:
                row(e(name), value)
            if len(changed) > SETTINGS.card_max_changed:
                row("", "<span style='color:%s'>+%d more</span>"
                    % (GREY, len(changed) - SETTINGS.card_max_changed))
    except Exception:
        pass

    return "%s<table style='margin-top:6px'>%s</table>" % (head, "".join(rows))


def _downstream_count(node, limit=5000):
    mask = nuke.INPUTS | nuke.HIDDEN_INPUTS
    seen, stack = set(), [node]
    while stack and len(seen) < limit:
        for d in stack.pop().dependent(mask, forceEvaluate=False):
            name = d.fullName()
            if name not in seen:
                seen.add(name)
                stack.append(d)
    return len(seen)


# --------------------------------------------------------------------------- #
# Controller (one light timer)
# --------------------------------------------------------------------------- #
class _Controller(QtCore.QObject):
    TICK_MS = 100

    def __init__(self, parent=None):
        super(_Controller, self).__init__(parent)
        self.card = _InfoCard()
        self._hover_name = None
        self._hover_node = None
        self._since = 0.0
        self._last_pos = None
        self._overriding = False
        self._in_dag = False
        self._dag = None
        self._view = None
        self._dag_found_at = 0.0
        self._last_sel = None
        self._problems = []
        self._problem_i = -1
        self._problems_at = 0.0
        self._viewer_at = 0.0
        self._badge = None
        self._vlabel = None
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self.TICK_MS)
        # fast, very cheap timer just for the cursor so it reacts instantly
        self._cursor_timer = QtCore.QTimer(self)
        self._cursor_timer.timeout.connect(self._tick_cursor)
        self._cursor_timer.start(30)

    def stop(self):
        self._timer.stop()
        self._cursor_timer.stop()
        self.card.hide()
        self.clear_cursor()
        for w in (self._badge, self._vlabel):
            try:
                if w is not None:
                    w.hide()
                    w.deleteLater()
            except RuntimeError:
                pass

    # -- graph lookup (cached, refreshed every 2 s) -------------------------- #
    def _graph(self):
        now = time.time()
        alive = True
        try:
            if self._view is not None:
                self._view.isVisible()            # raises if Qt deleted it
        except RuntimeError:
            alive = False
        if not alive or self._dag is None or now - self._dag_found_at > 2.0:
            self._dag = _root_dag()
            self._view = _view_widget(self._dag) if self._dag is not None else None
            self._dag_found_at = now
        return self._dag, self._view

    # -- cursor ------------------------------------------------------------- #
    # The crosshair is pushed as Qt's application override cursor, so it is
    # THE cursor everywhere inside Nuke (other apps are unaffected). If Nuke
    # pushes its own override on top (e.g. the busy wheel), it gets swapped
    # for the crosshair too. Only a hidden cursor (Sleepy Scrub's infinite
    # drag) is left alone.
    def clear_cursor(self):
        if self._overriding:
            QtWidgets.QApplication.restoreOverrideCursor()
            self._overriding = False

    def _state_color(self):
        app = QtWidgets.QApplication
        buttons = app.mouseButtons()
        mods = app.keyboardModifiers()
        if (buttons & QtCore.Qt.MiddleButton
                or (buttons & QtCore.Qt.LeftButton and mods & QtCore.Qt.AltModifier)):
            return SETTINGS.color_pan
        if buttons & QtCore.Qt.LeftButton:
            return SETTINGS.color_drag
        if self._hover_name:
            return SETTINGS.color_node
        return SETTINGS.yellow

    def _scrub_field_cursor(self):
        """Sleepy Scrub's cursor if the mouse is over a field it can scrub."""
        gs = sys.modules.get("sleepy_scrub")
        if gs is None or getattr(gs, "_instance", None) is None:
            return None
        try:
            if not gs.SETTINGS.enabled:
                return None
            w = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
            if (isinstance(w, QtWidgets.QLineEdit) and not w.hasFocus()
                    and gs._instance._eligible(w)):
                return gs._scrub_cursor()
        except Exception:
            pass
        return None

    def _tick_cursor(self):
        try:
            app = QtWidgets.QApplication
            if not SETTINGS.cursor:
                self.clear_cursor()
                return

            wanted = (self._scrub_field_cursor()
                      or crosshair_cursor(self._state_color(), self._badges()))
            top = app.overrideCursor()
            if top is None:                        # ours got popped: push again
                app.setOverrideCursor(wanted)
                self._overriding = True
                return
            if top.shape() == QtCore.Qt.BlankCursor:
                return                             # Sleepy Scrub mid-drag

            top_sig = _signature(top)
            if top_sig == _signature(wanted, cache=True):
                return                             # already right
            if top_sig == _signature(crosshair_cursor(SETTINGS.color_busy), cache=True):
                return                             # stays red until Nuke is done
            if not self._is_ours(top_sig):         # someone else's cursor
                if not SETTINGS.cursor_always:
                    return
                if top.shape() in (QtCore.Qt.WaitCursor, QtCore.Qt.BusyCursor):
                    app.changeOverrideCursor(crosshair_cursor(SETTINGS.color_busy))
                    return
            app.changeOverrideCursor(wanted)
        except Exception as exc:
            _report("cursor", exc)

    def _badges(self):
        if not (SETTINGS.modifier_badges and self._in_dag):
            return ()
        mods = QtWidgets.QApplication.keyboardModifiers()
        out = []
        if mods & QtCore.Qt.ControlModifier:
            out.append("ctrl")
        if mods & QtCore.Qt.ShiftModifier:
            out.append("shift")
        return out

    def _is_ours(self, sig):
        if sig is None:
            return False
        base = _signature(crosshair_cursor(), cache=True)
        if base is not None and sig[:4] == base[:4]:
            return True                            # any colour / badge of ours
        gs = sys.modules.get("sleepy_scrub")
        if gs is not None:
            try:
                return sig == _signature(gs._scrub_cursor(), cache=True)
            except Exception:
                pass
        return False

    # -- tick --------------------------------------------------------------- #
    def _tick(self):
        try:
            self._tick_card()                      # also feeds the "over node" colour
            if not SETTINGS.card:
                self.card.hide()
        except Exception as exc:
            _report("tick", exc)
        for name, fn in (("selection", self._tick_selection),
                         ("badge", self._tick_badge),
                         ("viewer", self._tick_viewer_label)):
            try:
                fn()
            except Exception as exc:
                _report(name, exc)

    # -- selection summary -------------------------------------------------- #
    def _tick_selection(self):
        if not SETTINGS.selection_summary:
            return
        sel = nuke.selectedNodes()
        key = tuple(sorted(n.fullName() for n in sel))
        if key == self._last_sel:
            return
        first_time = self._last_sel is None
        self._last_sel = key
        if first_time or len(sel) < 2 or not self._in_dag:
            return
        if len(sel) == 2 and all(n.Class() != "BackdropNode" for n in sel):
            toast(_diff_html(sel[0], sel[1]), SETTINGS.yellow, 4000)
        else:
            toast(_selection_html(sel), SETTINGS.yellow, 2500)

    # -- problem badge ------------------------------------------------------ #
    def _tick_badge(self):
        dag, view = self._graph()
        show = (SETTINGS.problem_badge and view is not None and view.isVisible()
                and QtWidgets.QApplication.applicationState() == QtCore.Qt.ApplicationActive)
        if not show:
            if self._badge is not None:
                self._badge.hide()
            return
        now = time.time()
        if now - self._problems_at > 2.0:           # rescan every 2 s
            self._problems_at = now
            self._problems, counts = _scan_problems()
            if self._badge is None:
                self._badge = _Hud(_main_window() or dag.window(), clickable=True)
                self._badge.clicked.connect(self._next_problem)
            self._badge.set_html(_badge_html(counts), SETTINGS.color_busy)
        if self._badge is None:
            return
        if not self._problems:
            self._badge.hide()
            return
        self._badge.move(_corner_pos(view, self._badge, SETTINGS.badge_position))
        if not self._badge.isVisible():
            self._badge.show()

    def _next_problem(self):
        if not self._problems:
            return
        self._problem_i = (self._problem_i + 1) % len(self._problems)
        node, why = self._problems[self._problem_i]
        try:
            for n in nuke.selectedNodes():
                n.setSelected(False)
            node.setSelected(True)
            nuke.zoom(nuke.zoom(), [node.xpos() + node.screenWidth() / 2.0,
                                    node.ypos() + node.screenHeight() / 2.0])
            toast("<b>%d / %d</b>&nbsp;&nbsp;%s&nbsp;&nbsp;<span style='color:%s'>%s</span>"
                  % (self._problem_i + 1, len(self._problems), html.escape(node.name()),
                     GREY, html.escape(why)), SETTINGS.color_busy, 1800)
        except Exception:
            self._problems_at = 0.0                  # node gone: rescan next tick

    # -- viewer label ------------------------------------------------------- #
    def _tick_viewer_label(self):
        now = time.time()
        if now - self._viewer_at < 0.25:
            return
        self._viewer_at = now
        container = _viewer_view() if SETTINGS.viewer_label else None
        active = QtWidgets.QApplication.applicationState() == QtCore.Qt.ApplicationActive
        v = nuke.activeViewer() if container is not None else None
        if v is None or not active or not container.isVisible():
            if self._vlabel is not None:
                self._vlabel.hide()
            return
        idx = v.activeInput()
        node = v.node().input(idx) if idx is not None else None
        if node is None:
            if self._vlabel is not None:
                self._vlabel.hide()
            return
        mode, color = "VIEW %d" % (idx + 1), GREY
        if _last_view and _last_view[1] == node.fullName():
            mode = _last_view[0].upper()
            color = {"front": SETTINGS.color_drag, "back": SETTINGS.color_pan,
                     "matte": SETTINGS.color_node}.get(_last_view[0], SETTINGS.yellow)
        if self._vlabel is None:
            self._vlabel = _Hud(_main_window() or container.window())
        self._vlabel.set_html("<b style='color:%s'>%s</b>&nbsp;&nbsp;%s"
                              % (color, mode, html.escape(node.name())), color)
        top_left = container.mapToGlobal(QtCore.QPoint(0, 0))
        self._vlabel.move(top_left.x() + 10, top_left.y() + 10)
        if not self._vlabel.isVisible():
            self._vlabel.show()

    def _tick_card(self):
        dag, view = self._graph()
        if dag is None or not dag.isVisible():
            self._in_dag = False
            self.card.hide()
            return
        gpos = QtGui.QCursor.pos()
        under = QtWidgets.QApplication.widgetAt(gpos)
        inside = under is not None and (under is dag or dag.isAncestorOf(under))
        self._in_dag = inside
        if not inside or QtWidgets.QApplication.mouseButtons() != QtCore.Qt.NoButton:
            self._hover_name = None
            self.card.hide()
            return

        now = time.time()
        if gpos != self._last_pos:
            self._last_pos = QtCore.QPoint(gpos)
            hit = self._node_at(dag, gpos)
            if isinstance(hit, tuple):
                name = "pipe:%s>%s:%d" % (hit[1].fullName(), hit[2].fullName(), hit[3])
            else:
                name = hit.fullName() if hit is not None else None
            if name != self._hover_name:
                self._hover_name, self._hover_node, self._since = name, hit, now
                self.card.hide()
            elif self.card.isVisible():
                self.card._place(gpos)

        if (SETTINGS.card and self._hover_name and not self.card.isVisible()
                and now - self._since >= SETTINGS.card_delay):
            try:
                self.card.show_for(self._hover_node, gpos)
            except Exception as exc:
                _report("card", exc)
                self._hover_name = None

    @staticmethod
    def _node_at(dag, gpos):
        x, y = _graph_point(dag, gpos)
        hit, backdrop = None, None
        for n in nuke.allNodes():
            inside_x = n.xpos() <= x <= n.xpos() + n.screenWidth()
            if n.Class() == "BackdropNode":
                # only the title strip, so crossing a big backdrop stays quiet
                if inside_x and n.ypos() <= y <= n.ypos() + 40:
                    backdrop = n
                continue
            if inside_x and n.ypos() <= y <= n.ypos() + n.screenHeight():
                hit = n                            # last = drawn on top
        if hit is None and SETTINGS.pipe_info:
            pipe = _pipe_at(x, y, 6.0 / max(nuke.zoom(), 0.05))
            if pipe is not None:
                return pipe
        return hit or backdrop


def _graph_point(dag, gpos):
    """Screen position -> Node Graph coordinates."""
    view = _view_widget(dag)
    local = view.mapFromGlobal(gpos)
    z = nuke.zoom() * SETTINGS.view_scale
    cx, cy = nuke.center()
    x = cx + (local.x() - view.width() / 2.0) / z
    y = cy + (local.y() - view.height() / 2.0) / z
    return x, y


def debug_mapping(delay_ms=4000):
    """Select ONE node, run this, then put the mouse on the CENTRE of that
    node and keep it still. Prints the numbers needed to fix the maths."""
    def run():
        try:
            dag = _root_dag()
            view = _view_widget(dag)
            gpos = QtGui.QCursor.pos()
            local = view.mapFromGlobal(gpos)
            print("view: %s %dx%d | dpr %.2f" % (view.metaObject().className(),
                  view.width(), view.height(), view.devicePixelRatioF()))
            print("mouse local: %d, %d" % (local.x(), local.y()))
            print("zoom: %s | center: %s" % (nuke.zoom(), nuke.center()))
            print("mouse -> graph: %.1f, %.1f" % _graph_point(dag, gpos))
            for n in nuke.selectedNodes()[:1]:
                print("node %s centre in graph: %.1f, %.1f" % (
                    n.name(), n.xpos() + n.screenWidth() / 2.0,
                    n.ypos() + n.screenHeight() / 2.0))
            print("node under mouse: %s" % _Controller._node_at(dag, gpos))
        except Exception:
            import traceback
            traceback.print_exc()
    QtCore.QTimer.singleShot(delay_ms, run)
    print("Mouse on the CENTRE of the selected node, keep still %.0f s..." % (delay_ms / 1000.0))


# --------------------------------------------------------------------------- #
# Helpers for the Node Graph / Viewer extras
# --------------------------------------------------------------------------- #
_last_view = None          # (mode, node fullName) set by the F1-F4 keys


def _main_window():
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.metaObject().className() == "Foundry::UI::DockMainWindow":
            return w
    return None


_viewer_cache = {"w": None, "at": 0.0}


def _viewer_view():
    """The Viewer's drawing area (cached, refreshed every 2 s)."""
    now = time.time()
    w = _viewer_cache["w"]
    try:
        if w is not None and now - _viewer_cache["at"] < 2.0 and w.isVisible():
            return w
    except RuntimeError:
        pass
    best, area = None, 0
    for panel in QtWidgets.QApplication.instance().allWidgets():
        if not panel.objectName().startswith("Viewer.") or not panel.isVisible():
            continue
        for c in [panel] + panel.findChildren(QtWidgets.QWidget):
            if c.metaObject().className() == "QWindowContainer" and c.isVisible():
                a = c.width() * c.height()
                if a > area:
                    best, area = c, a
    _viewer_cache["w"], _viewer_cache["at"] = best, now
    return best


def _corner_pos(view, widget, where, margin=14):
    """Global position for `widget` in a corner (or centre edge) of `view`."""
    tl = view.mapToGlobal(QtCore.QPoint(0, 0))
    vw, vh, ww, wh = view.width(), view.height(), widget.width(), widget.height()
    vert, _, horiz = where.partition("-")
    x = {"left": margin, "center": (vw - ww) // 2,
         "right": vw - ww - margin}.get(horiz, margin)
    y = margin if vert == "top" else vh - wh - margin
    return QtCore.QPoint(tl.x() + x, tl.y() + y)


class _Hud(QtWidgets.QLabel):
    """Small floating label (badge / viewer label). Never takes focus."""
    clicked = QtCore.Signal()

    def __init__(self, parent=None, clickable=False):
        flags = (QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint
                 | QtCore.Qt.WindowDoesNotAcceptFocus)
        super(_Hud, self).__init__(parent, flags)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        if not clickable:
            self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setTextFormat(QtCore.Qt.RichText)
        self._html = None

    def set_html(self, text, accent):
        if text == self._html:
            return
        self._html = text
        fs = SETTINGS.hud_font_size
        self.setStyleSheet(
            "QLabel { background: rgba(22, 23, 25, 240); color:#e6e6e6;"
            " border:1px solid #3a3c40; border-left:5px solid %s;"
            " padding:%dpx %dpx; font-size:%dpx; }"
            % (accent, int(fs * 0.55), int(fs * 1.0), fs))
        self.setText(text)
        self.adjustSize()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()


def _selection_html(sel):
    counts = {}
    for n in sel:
        counts[n.Class()] = counts.get(n.Class(), 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: -kv[1])
    kinds = ", ".join("%d %s" % (c, html.escape(k)) for k, c in ordered[:3])
    if len(ordered) > 3:
        kinds += " <span style='color:%s'>+%d</span>" % (GREY, len(ordered) - 3)
    parts = ["<b>%d nodes</b>" % len(sel), kinds]
    try:
        firsts = [n.firstFrame() for n in sel if n.Class() != "BackdropNode"]
        lasts = [n.lastFrame() for n in sel if n.Class() != "BackdropNode"]
        if firsts:
            parts.append("%d&ndash;%d" % (min(firsts), max(lasts)))
    except Exception:
        pass
    try:
        if nuke.usingPerformanceTimers():
            total = sum(n.performanceInfo().get("timeTakenWall", 0) for n in sel)
            parts.append("<span style='color:%s'>%.1f ms</span>" % (SETTINGS.yellow, total / 1000.0))
    except Exception:
        pass
    sep = "&nbsp;<span style='color:%s'>&middot;</span>&nbsp;" % GREY
    return sep.join(parts)


def _node_layers(n):
    try:
        layers = []
        for c in n.channels():
            layer = c.split(".")[0]
            if layer not in layers:
                layers.append(layer)
        return layers
    except Exception:
        return None


def _knob_text(n, name):
    try:
        if name in n.knobs():
            return str(n[name].value())
    except Exception:
        pass
    return None


def _diff_html(a, b):
    """Two selected nodes side by side. Matching rows stay grey, mismatches
    are highlighted in the drag colour."""
    e = html.escape
    rows = []

    def row(label, va, vb, same):
        mark = "" if same else " style='color:%s'" % SETTINGS.color_drag
        rows.append("<tr><td style='color:%s; padding:1px 12px 1px 0'>%s</td>"
                    "<td style='padding:1px 12px 1px 0%s'>%s</td>"
                    "<td style='padding:1px 0%s'>%s</td></tr>"
                    % (GREY, label, mark, va, mark, vb))

    def txt(v):
        if v is None:
            return "<span style='color:%s'>&ndash;</span>" % GREY
        return e(_short(v, 22))

    def cmp(label, va, vb):
        row(label, txt(va), txt(vb), va is not None and va == vb)

    head = ("<span style='font-size:13px; font-weight:600; color:#f2f2f2'>%s</span>"
            "&nbsp;<span style='color:%s'>&#8646;</span>&nbsp;"
            "<span style='font-size:13px; font-weight:600; color:#f2f2f2'>%s</span>"
            "&nbsp;&nbsp;<span style='color:%s'>%s / %s</span>"
            % (e(_short(a.name(), 20)), SETTINGS.yellow, e(_short(b.name(), 20)),
               GREY, e(a.Class()), e(b.Class())))
    try:
        cmp("Resolution", "%d x %d" % (a.width(), a.height()),
            "%d x %d" % (b.width(), b.height()))
    except Exception:
        pass
    try:
        cmp("Format", a.format().name(), b.format().name())
    except Exception:
        pass
    try:
        cmp("Frames", "%d - %d" % (a.firstFrame(), a.lastFrame()),
            "%d - %d" % (b.firstFrame(), b.lastFrame()))
    except Exception:
        pass
    la, lb = _node_layers(a), _node_layers(b)
    if la is not None and lb is not None:
        row("Layers", txt("%d layers" % len(la)), txt("%d layers" % len(lb)),
            set(la) == set(lb))
    ca, cb = _knob_text(a, "colorspace"), _knob_text(b, "colorspace")
    if ca is not None or cb is not None:
        cmp("Colorspace", ca, cb)
    fa, fb = _knob_text(a, "file_type"), _knob_text(b, "file_type")
    if fa is not None or fb is not None:
        cmp("File type", fa, fb)
    return "%s<table style='margin-top:6px'>%s</table>" % (head, "".join(rows))


# --------------------------------------------------------------------------- #
# Copy node info as plain text
# --------------------------------------------------------------------------- #
_ENTITY_TEXT = {"&times;": "x", "&ndash;": "-", "&rarr;": "->",
                "&middot;": "*", "&#9888;": "!", "&nbsp;": " "}


def _card_text(node):
    """The info card's HTML as plain text, one row per line."""
    text = _card_html(node)
    for old, new in _ENTITY_TEXT.items():
        text = text.replace(old, new)
    text = re.sub(r"<table[^>]*>", "\n", text)
    text = re.sub(r"</td>\s*<td[^>]*>", "   ", text)
    text = re.sub(r"</tr>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def copy_node_info():
    """Copy the hovered node's card (or the selected node's) as plain text."""
    node = None
    ctrl = _controller
    if (ctrl is not None and ctrl._hover_name
            and not isinstance(ctrl._hover_node, tuple)):
        node = ctrl._hover_node
    if node is None:
        try:
            node = nuke.selectedNode()
        except ValueError:
            node = None
    if node is None:
        toast("Hover a node or select one first", SETTINGS.color_busy)
        return
    try:
        text = _card_text(node)
    except Exception:
        toast("Couldn't read that node", SETTINGS.color_busy)
        return
    QtWidgets.QApplication.clipboard().setText(text)
    toast("<b>COPIED</b>&nbsp;&nbsp;%s" % html.escape(node.name()), SETTINGS.yellow)


def open_settings_folder():
    folder = os.path.dirname(_SETTINGS_FILE)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))


def _scan_problems():
    """[(node, reason)] errors first, then missing frames, then disabled."""
    errors, missing, disabled = [], [], []
    seen = set()
    for n in nuke.allNodes():
        name = n.fullName()
        try:
            if n.Class() in ("Read", "DeepRead") and "file" in n.knobs():
                path = n["file"].evaluate()
                if path and not os.path.exists(path):
                    missing.append((n, "missing file on frame %d" % nuke.frame()))
                    seen.add(name)
                    continue
            if n.hasError():
                errors.append((n, "error"))
                seen.add(name)
                continue
            if SETTINGS.badge_disabled and "disable" in n.knobs() and n["disable"].value():
                disabled.append((n, "disabled"))
        except Exception:
            pass
    counts = (len(errors), len(missing), len(disabled))
    return errors + missing + disabled, counts


def _badge_html(counts):
    errors, missing, disabled = counts
    parts = []
    if errors:
        parts.append("<span style='color:%s'><b>%d</b> error%s</span>"
                     % (RED, errors, "" if errors == 1 else "s"))
    if missing:
        parts.append("<span style='color:%s'><b>%d</b> missing</span>"
                     % (SETTINGS.color_drag, missing))
    if disabled:
        parts.append("<span style='color:%s'><b>%d</b> disabled</span>" % (GREY, disabled))
    sep = "&nbsp;<span style='color:%s'>&middot;</span>&nbsp;" % GREY
    return "&#9888;&nbsp;&nbsp;" + sep.join(parts) if parts else ""


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _pipe_at(x, y, tolerance):
    """Closest visible pipe to (x, y) in graph units, as ("pipe", src, dst, i)."""
    best, best_d = None, tolerance
    for dst in nuke.allNodes():
        if dst.Class() == "BackdropNode":
            continue
        try:
            if "hide_input" in dst.knobs() and dst["hide_input"].value():
                continue
            n_in = dst.inputs()
        except Exception:
            continue
        bx = dst.xpos() + dst.screenWidth() / 2.0
        by = dst.ypos() + dst.screenHeight() / 2.0
        for i in range(n_in):
            src = dst.input(i)
            if src is None:
                continue
            ax = src.xpos() + src.screenWidth() / 2.0
            ay = src.ypos() + src.screenHeight() / 2.0
            d = _seg_dist(x, y, ax, ay, bx, by)
            if d < best_d:
                best, best_d = ("pipe", src, dst, i), d
    return best


def _input_name(node, i):
    if node.Class().startswith("Merge") or node.Class() in ("Copy", "Keymix", "Dissolve"):
        if i == 0:
            return "B"
        if i == 1:
            return "A"
    try:
        if node.optionalInput() == i:
            return "mask"
    except Exception:
        pass
    return "input %d" % (i + 1)


def _pipe_html(src, dst, i):
    e = html.escape
    head = ("<span style='font-size:13px; font-weight:600; color:#f2f2f2'>%s</span>"
            "&nbsp;<span style='color:%s'>&rarr;</span>&nbsp;"
            "<span style='font-size:13px; font-weight:600; color:#f2f2f2'>%s</span>"
            % (e(src.name()), SETTINGS.yellow, e(dst.name())))
    rows = []

    def row(label, value):
        rows.append("<tr><td style='color:%s; padding:1px 14px 1px 0'>%s</td>"
                    "<td style='padding:1px 0'>%s</td></tr>" % (GREY, label, value))

    row("Input", "<b>%s</b>" % e(_input_name(dst, i)))
    try:
        row("Resolution", "%d &times; %d" % (src.width(), src.height()))
    except Exception:
        pass
    try:
        chans = src.channels()
        layers = []
        for c in chans:
            layer = c.split(".")[0]
            if layer not in layers:
                layers.append(layer)
        row("Layers", "%s&nbsp;&nbsp;<span style='color:%s'>%d ch</span>"
            % (e(", ".join(layers[:5])), GREY, len(chans)))
    except Exception:
        pass
    return "%s<table style='margin-top:6px'>%s</table>" % (head, "".join(rows))


# --------------------------------------------------------------------------- #
# Toast: a short message next to the cursor
# --------------------------------------------------------------------------- #
class _Toast(QtWidgets.QLabel):
    def __init__(self):
        super(_Toast, self).__init__(None, QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setTextFormat(QtCore.Qt.RichText)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def flash(self, html_text, color=None, ms=1100):
        color = color or SETTINGS.yellow
        self.setStyleSheet(
            "QLabel { background:#161719; color:#e6e6e6; border:1px solid #36383c;"
            " border-left:3px solid %s; padding:5px 10px; font-size:11px; }" % color)
        self.setText(html_text)
        self.adjustSize()
        self.move(QtGui.QCursor.pos() + QtCore.QPoint(20, -self.height() - 8))
        self.show()
        self.raise_()
        self._timer.start(ms)


_toast_widget = None


def toast(html_text, color=None, ms=1100):
    global _toast_widget
    if _toast_widget is None:
        _toast_widget = _Toast()
    _toast_widget.flash(html_text, color, ms)


# --------------------------------------------------------------------------- #
# Flame-style view keys: Front / Back / Matte / Result
# --------------------------------------------------------------------------- #
def _mask_index(n):
    try:
        i = n.optionalInput()
        if i is not None and i >= 0:
            return i
    except Exception:
        pass
    return None


def view(which):
    """front = A (foreground), back = B (background), matte = mask input,
    result = the node itself. Single-input nodes: front = their input."""
    try:
        n = nuke.selectedNode()
    except ValueError:
        toast("Select a node first", SETTINGS.color_busy)
        return

    target = None
    if which == "result":
        target = n
    elif which == "front":
        target = n.input(1) if n.maxInputs() >= 2 else n.input(0)
    elif which == "back":
        target = n.input(0) if n.maxInputs() >= 2 else None
    elif which == "matte":
        i = _mask_index(n)
        target = n.input(i) if i is not None else None

    label = which.upper()
    if target is None:
        toast("<b>%s</b>&nbsp;&nbsp;<span style='color:#85888d'>nothing connected on %s</span>"
              % (label, html.escape(n.name())), SETTINGS.color_busy)
        return
    nuke.connectViewer(SETTINGS.view_slot, target)
    global _last_view
    _last_view = (which, target.fullName())
    color = {"front": SETTINGS.color_drag, "back": SETTINGS.color_pan,
             "matte": SETTINGS.color_node}.get(which, SETTINGS.yellow)
    toast("<b>%s</b>&nbsp;&nbsp;%s" % (label, html.escape(target.name())), color)


# --------------------------------------------------------------------------- #
# Iterations
# --------------------------------------------------------------------------- #
def _iteration_dir():
    path = nuke.root().name()
    if not path or path == "Root":
        return None, None
    base = os.path.splitext(os.path.basename(path))[0]
    return os.path.join(os.path.dirname(path), base + "_iterations"), base


def save_iteration():
    """Save a numbered copy of the current state next to the script.
    Your script file, its name and its 'modified' state are untouched."""
    folder, base = _iteration_dir()
    if folder is None:
        toast("Save the script once first", SETTINGS.color_busy)
        return
    os.makedirs(folder, exist_ok=True)
    nums = []
    for f in os.listdir(folder):
        stem = os.path.splitext(f)[0]
        if stem.startswith(base + "_it") and stem[len(base) + 3:].isdigit():
            nums.append(int(stem[len(base) + 3:]))
    num = max(nums) + 1 if nums else 1
    path = os.path.join(folder, "%s_it%03d.nk" % (base, num))
    nuke.scriptSaveToTemp(path)
    toast("<b>ITERATION %03d</b>&nbsp;&nbsp;saved" % num)
    print("Sleepy iteration saved: %s" % path)


def open_iterations_folder():
    folder, base = _iteration_dir()
    if folder is None or not os.path.isdir(folder):
        toast("No iterations yet", SETTINGS.color_busy)
        return
    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))


# --------------------------------------------------------------------------- #
# Menu + install
# --------------------------------------------------------------------------- #
def toggle_cursor():
    SETTINGS.cursor = not SETTINGS.cursor
    if not SETTINGS.cursor and _controller is not None:
        _controller.clear_cursor()
    save_settings()
    print("Sleepy Node Info cursor: %s" % ("ON" if SETTINGS.cursor else "OFF"))


def toggle_card():
    SETTINGS.card = not SETTINGS.card
    save_settings()
    print("Sleepy Node Info card: %s" % ("ON" if SETTINGS.card else "OFF"))


def toggle(name):
    """toggle('selection_summary' | 'problem_badge' | 'pipe_info' | 'viewer_label')"""
    setattr(SETTINGS, name, not getattr(SETTINGS, name))
    save_settings()
    print("Sleepy Node Info %s: %s" % (name, "ON" if getattr(SETTINGS, name) else "OFF"))


_controller = None
_menu_added = False


def install():
    global _controller
    if nuke is None or not nuke.GUI:
        return
    app = QtWidgets.QApplication.instance()
    if _controller is None and app is not None:
        if app.property("sleepy_node_info_active"):
            return                         # another copy is already running
        app.setProperty("sleepy_node_info_active", True)
        _controller = _Controller(app)
    _ensure_menu()


def uninstall():
    global _controller
    if _controller is not None:
        _controller.stop()
        _controller.deleteLater()
        _controller = None
        QtWidgets.QApplication.instance().setProperty("sleepy_node_info_active", False)


def _ensure_menu(tries=20):
    global _menu_added
    if _menu_added:
        return
    try:
        bar = nuke.menu("Nuke")
        if bar is None:
            raise RuntimeError("menu bar not ready")
        m = bar.addMenu("SleepyTools").addMenu("Node Info")
        c = "import sleepy_node_info as g; g."
        m.addCommand("Crosshair Cursor On - Off", c + "toggle_cursor()")
        m.addCommand("Hover Card On - Off", c + "toggle_card()")
        m.addCommand("Pipe Info On - Off", c + "toggle('pipe_info')")
        m.addCommand("Selection Summary On - Off", c + "toggle('selection_summary')")
        m.addCommand("Problem Badge On - Off", c + "toggle('problem_badge')")
        m.addCommand("Viewer Label On - Off", c + "toggle('viewer_label')")
        m.addSeparator()
        for which in ("front", "back", "matte", "result"):
            m.addCommand("View %s" % which.capitalize(), c + "view(%r)" % which,
                         SETTINGS.view_keys.get(which, ""))
        m.addSeparator()
        m.addCommand("Save Iteration", c + "save_iteration()", SETTINGS.iteration_key)
        m.addCommand("Open Iterations Folder", c + "open_iterations_folder()")
        m.addSeparator()
        m.addCommand("Copy Node Info", c + "copy_node_info()", SETTINGS.copy_key)
        m.addCommand("Open Settings Folder", c + "open_settings_folder()")
        _menu_added = True
    except Exception:
        if tries > 0:
            QtCore.QTimer.singleShot(500, lambda: _ensure_menu(tries - 1))


try:
    install()
except Exception as _exc:
    print("sleepy_node_info: auto-install failed: %s" % _exc)
