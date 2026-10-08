"""
sleepy_scrub.py
================
Flame / Smoke-style value handling for Nuke's *native* knob fields.

The Node Graph is never touched: the plugin only reacts to numeric text
fields (QLineEdit) in the Properties panel and other knob UIs. Nodes,
connections, the DAG, viewer and shortcuts all behave exactly as before.

What you get
------------
1. Scrub any numeric knob field
     press + drag left/right   -> value changes live
     Shift                     -> coarse (x10)
     Ctrl                      -> fine   (x0.1)
     Alt                       -> snap to a step (SETTINGS.snap_step,
                                  whole numbers by default)
   Mouse: the cursor is hidden and locked, so the drag is infinite and the
          pointer reappears exactly where you pressed.
   Pen  : a tablet is absolute, so warping would fight the pen. In pen mode
          the cursor stays visible and moves normally; the value follows it.
   Speed adapts to the value's size (gain 1.0 scrubs finely, a 1920 size
   scrubs in big steps).
   Frame / integer knobs (Int_Knob) scrub in whole steps at about one unit
   per pixel, so a frame field at 1001 still moves one frame per pixel and
   always lands on a whole number.

2. Double-click a field that has been scrubbed before
     resets its knob to the default value (one undo step). Fields whose knob
     was never scrubbed keep the old double-click behaviour. Fields whose
     knob is expression-driven are never scrubbed or reset, so expressions
     are safe.

3. Click without dragging = "calculator" mode
     Field selects all and you type:
       0.75          absolute
       2*3+1         arithmetic
       +5  *2  /4    relative to the value before you started typing
     Anything that isn't plain arithmetic (Nuke expressions etc.) is passed
     to Nuke untouched.

4. Flame-style hover cue: a horizontal-resize cursor over scrubbable fields.

5. One whole drag = one undo step.

Install
-------
The plugin switches itself on when imported in a Nuke GUI session, so it
works with an auto-installer that just imports every .py in a folder
(started by the menu.py in that folder).

Or the standard way: put it in ~/.nuke and add to menu.py

    import sleepy_scrub

(Calling sleepy_scrub.install() again is harmless; it only installs once.
Render farm / terminal sessions are skipped automatically.)

A "SleepyTools > Scrub Fields" menu is added for toggling and choosing
mouse/pen mode. Menu choices are remembered across sessions in a
per-user JSON: %LOCALAPPDATA%\SleepyTools\sleepy_scrub.json
"""

import ast
import json
import math
import operator
import time
import weakref

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

# make "import sleepy_scrub" work however this file was loaded
import os
import sys
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    if _HERE not in sys.path:
        sys.path.append(_HERE)
except NameError:
    pass
if (__name__ != "sleepy_scrub" and "sleepy_scrub" not in sys.modules
        and sys.modules.get(__name__) is not None):
    sys.modules["sleepy_scrub"] = sys.modules[__name__]

_APP_FLAG = "sleepy_scrub_active"     # stops a second copy installing twice


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class Settings(object):
    enabled = True
    calculator = True            # pen-friendly keypad when you click a field
    input_mode = "auto"          # "auto" | "mouse" | "pen"
    sensitivity = 0.005          # per pixel, as a fraction of max(|value|, 1)
    coarse = 10.0                # Shift
    fine = 0.1                   # Ctrl
    drag_threshold = 3           # px before a press becomes a scrub
    commit_interval = 1.0 / 60   # throttle live updates (seconds)
    warp_radius = 150            # px the hidden cursor may drift before re-centring
    # How a scrubbed value is pushed to Nuke:
    #   "knob"   - set the knob directly through Nuke's API (smooth, default).
    #              The first update is typed so Nuke reveals which knob the
    #              field belongs to; after that it's direct.
    #   "type"   - simulate typing the number + Enter on every update
    #   "return" - set the text, mark it edited, press Enter
    #   "signal" - set the text and fire the field's edit signals directly
    commit_method = "knob"
    debug = False                # print every step to the Script Editor
    # Set to e.g. QtCore.Qt.AltModifier to scrub only while Alt is held
    # (leaves plain clicks 100% native). None = plain drag scrubs.
    require_modifier = None

    # Frame / integer knobs scrub in whole steps at a capped speed, so frame
    # fields always land on whole numbers. Class names come from knob.Class().
    int_aware = True
    int_knob_classes = ("Int_Knob",)
    int_step_min = 0.1          # slowest int scrub (units per pixel)
    int_step_max = 1.0          # fastest int scrub (units per pixel)
    # Alt+drag snaps to this increment. None = no snapping.
    snap_step = 1.0

    # ---- cursor look --------------------------------------------------- #
    # "sleepy" = the drawn scrub cursor below, "system" = OS resize arrow
    cursor_style = "sleepy"
    cursor_color = "#f2f2f2"     # fill
    cursor_outline = "#101010"   # outline (keeps it readable on any colour)
    cursor_accent = "#ffb347"    # small centre tick
    cursor_size = 22             # logical px (scaled for hi-DPI screens)
    # Path to your own PNG (hotspot = centre). Overrides cursor_style.
    cursor_image = None


SETTINGS = Settings()


# --------------------------------------------------------------------------- #
# Per-user persistence of the menu choices
# --------------------------------------------------------------------------- #
_SETTINGS_FILE = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "SleepyTools", "sleepy_scrub.json")

_PERSISTED_TYPES = {
    "enabled": bool, "calculator": bool, "input_mode": str,
    "cursor_style": str, "commit_method": str, "int_aware": bool,
    "snap_step": (float, int, type(None)),
}


def load_settings():
    """Apply the saved menu choices (silently skipped when there is none)."""
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
    """Write the current menu choices (atomic temp file + replace)."""
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
        print("sleepy_scrub: couldn't save settings (%s)" % exc)


load_settings()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def safe_eval(text):
    """Plain arithmetic only - no names, no calls, no eval()."""
    def _ev(node):
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_ev(node.left), _ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_ev(node.operand))
        raise ValueError(text)
    return float(_ev(ast.parse(text, mode="eval")))


def _parse_number(text):
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        return None


def _gpos(event):
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


def _is_stylus(event):
    # Qt6: real device info
    try:
        D = QtGui.QInputDevice.DeviceType
        return event.pointingDevice().type() in (D.Stylus, D.Airbrush, D.Puck)
    except AttributeError:
        pass
    # Qt5: mouse events synthesised from tablet events
    try:
        return event.source() == QtCore.Qt.MouseEventSynthesizedByQt
    except AttributeError:
        return False


def _decimals_for(step):
    if step >= 1:
        return 0
    return min(6, int(math.ceil(-math.log10(step))) + 1)


def _fmt(value, decimals):
    s = "%.*f" % (decimals, value)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


_cursor_cache = {}


def _scrub_cursor():
    """The hover / pen-drag cursor: a centre bar with a chevron each side,
    drawn at runtime (no image files), sharp on hi-DPI screens."""
    s = SETTINGS
    key = (s.cursor_style, s.cursor_image, s.cursor_color, s.cursor_outline,
           s.cursor_accent, s.cursor_size)
    if key in _cursor_cache:
        return _cursor_cache[key]

    if s.cursor_image:
        pm = QtGui.QPixmap(s.cursor_image)
        if not pm.isNull():
            cur = QtGui.QCursor(pm, pm.width() // 2, pm.height() // 2)
            _cursor_cache[key] = cur
            return cur
        print("sleepy_scrub: couldn't load cursor_image %r" % s.cursor_image)

    if s.cursor_style == "system":
        cur = QtGui.QCursor(QtCore.Qt.SizeHorCursor)
        _cursor_cache[key] = cur
        return cur

    size = s.cursor_size
    screen = QtGui.QGuiApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0
    pm = QtGui.QPixmap(int(round(size * dpr)), int(round(size * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(QtCore.Qt.transparent)

    c = size / 2.0
    u = size / 22.0                      # design unit (drawn on a 22px grid)
    P = lambda x, y: QtCore.QPointF(c + x * u, c + y * u)

    left = QtGui.QPolygonF([P(-9.5, 0), P(-4.5, -5), P(-4.5, 5)])
    right = QtGui.QPolygonF([P(9.5, 0), P(4.5, -5), P(4.5, 5)])
    fill = QtGui.QColor(s.cursor_color)
    outline = QtGui.QColor(s.cursor_outline)

    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)

    # outline pass: everything slightly fat in the dark colour
    pen = QtGui.QPen(outline, 2.4 * u)
    pen.setJoinStyle(QtCore.Qt.RoundJoin)
    pen.setCapStyle(QtCore.Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(outline)
    p.drawPolygon(left)
    p.drawPolygon(right)
    p.drawLine(P(0, -7.5), P(0, 7.5))

    # fill pass
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(fill)
    p.drawPolygon(left)
    p.drawPolygon(right)
    bar = QtGui.QPen(fill, 1.4 * u)
    bar.setCapStyle(QtCore.Qt.RoundCap)
    p.setPen(bar)
    p.drawLine(P(0, -7.5), P(0, 7.5))

    # accent tick in the middle = the hotspot
    tick = QtGui.QPen(QtGui.QColor(s.cursor_accent), 1.4 * u)
    tick.setCapStyle(QtCore.Qt.RoundCap)
    p.setPen(tick)
    p.drawLine(P(0, -1.6), P(0, 1.6))
    p.end()

    cur = QtGui.QCursor(pm, int(round(c)), int(round(c)))
    _cursor_cache[key] = cur
    return cur


def set_commit_method(method):
    if method not in ("knob", "type", "return", "signal"):
        raise ValueError("method must be 'knob', 'type', 'return' or 'signal'")
    SETTINGS.commit_method = method
    save_settings()
    print("Sleepy Scrub commit method: %s" % method)


def toggle_debug():
    SETTINGS.debug = not SETTINGS.debug
    print("Sleepy Scrub debug log: %s" % ("ON" if SETTINGS.debug else "OFF"))


def set_cursor_style(style):
    """'sleepy' (drawn) or 'system' (OS resize arrow)."""
    if style not in ("sleepy", "system"):
        raise ValueError("style must be 'sleepy' or 'system'")
    SETTINGS.cursor_style = style
    save_settings()
    print("Sleepy Scrub cursor: %s" % style)


def _channel_index(w):
    """Which channel a field edits. One visible field in its group = all
    channels (None); several (e.g. expanded r g b a, or x y) = its position."""
    parent = w.parentWidget()
    if parent is None:
        return None
    fields = [c for c in parent.findChildren(QtWidgets.QLineEdit)
              if c.parentWidget() is parent and c.isVisible()]
    if len(fields) <= 1 or w not in fields:
        return None
    fields.sort(key=lambda c: c.x())
    return fields.index(w)


_IGNORED_KNOBS = {"showPanel", "hidePanel", "selected", "xpos", "ypos",
                  "inputChange", "name", "label", "onCreate"}

# Fields whose knob a scrub has identified (weak: fields die with their
# panel). Enables double-click reset and the expression guard.
_knob_cache = weakref.WeakKeyDictionary()      # QLineEdit -> knob


def _cache_knob(w, knob):
    try:
        _knob_cache[w] = knob
    except TypeError:
        pass              # widget not weakref-able: cache features off


def _on_knob_changed():
    nuke = _nuke()
    if _instance is None or not _instance._learning or nuke is None:
        return
    try:
        k = nuke.thisKnob()
    except Exception:
        return
    if k is None or k.name() in _IGNORED_KNOBS:
        return
    _instance.learn_knob(k)


def _log(msg):
    if SETTINGS.debug:
        print("[sleepy_scrub] %s" % msg)


def _nuke():
    try:
        import nuke
        return nuke
    except ImportError:
        return None


# --------------------------------------------------------------------------- #
# Pen-friendly calculator keypad (Flame style)
# --------------------------------------------------------------------------- #
class _Keypad(QtWidgets.QWidget):
    """Floating keypad that types into the field being edited.
    It never takes keyboard focus, so the field stays in edit mode."""

    KEYS = [("7", "7"), ("8", "8"), ("9", "9"), ("\u00f7", "/"),
            ("4", "4"), ("5", "5"), ("6", "6"), ("\u00d7", "*"),
            ("1", "1"), ("2", "2"), ("3", "3"), ("\u2212", "-"),
            ("0", "0"), (".", "."), ("\u00b1", "neg"), ("+", "+"),
            ("C", "clear"), ("\u232b", "back"), ("=", "enter")]

    def __init__(self):
        flags = (QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint
                 | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.WindowDoesNotAcceptFocus)
        super(_Keypad, self).__init__(None, flags)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.field = None
        self.setStyleSheet(
            "QWidget#pad { background:#161719; border:1px solid #36383c; border-radius:6px; }"
            "QPushButton { background:#26272a; color:#e6e6e6; border:none; border-radius:4px;"
            " font-size:14px; min-width:40px; min-height:34px; }"
            "QPushButton:hover { background:#323438; }"
            "QPushButton:pressed { background:#3d4045; }"
            "QPushButton[op=\"true\"] { color:#f5c518; }"
            "QPushButton[eq=\"true\"] { background:#f5c518; color:#161719; font-weight:600; }"
            "QPushButton[eq=\"true\"]:hover { background:#ffd84d; }")
        frame = QtWidgets.QWidget(self)
        frame.setObjectName("pad")
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        grid = QtWidgets.QGridLayout(frame)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setSpacing(4)
        for i, (label, action) in enumerate(self.KEYS):
            b = QtWidgets.QPushButton(label)
            b.setFocusPolicy(QtCore.Qt.NoFocus)
            if action in ("/", "*", "-", "+", "neg"):
                b.setProperty("op", True)
            if action == "enter":
                b.setProperty("eq", True)
            b.clicked.connect(lambda checked=False, a=action: self._press(a))
            row, col = divmod(i, 4)
            if action == "enter":
                grid.addWidget(b, row, col, 1, 2)      # wide "="
            else:
                grid.addWidget(b, row, col)

    def show_for(self, field):
        self.field = field
        self.adjustSize()
        pos = field.mapToGlobal(QtCore.QPoint(0, field.height() + 4))
        screen = QtGui.QGuiApplication.screenAt(pos)
        if screen is not None:
            area = screen.availableGeometry()
            if pos.y() + self.height() > area.bottom():
                pos.setY(field.mapToGlobal(QtCore.QPoint(0, 0)).y() - self.height() - 4)
            if pos.x() + self.width() > area.right():
                pos.setX(area.right() - self.width())
        self.move(pos)
        self.show()
        self.raise_()

    def _press(self, action):
        f = self.field
        try:
            f.isVisible()
        except (RuntimeError, AttributeError):
            self.hide()
            return
        if action == "clear":
            f.clear()
        elif action == "back":
            f.backspace()
        elif action == "neg":
            t = f.text()
            f.setText(t[1:] if t.startswith("-") else "-" + t)
        elif action == "enter":
            for t in (E.KeyPress, E.KeyRelease):
                QtWidgets.QApplication.sendEvent(
                    f, QtGui.QKeyEvent(t, QtCore.Qt.Key_Return, QtCore.Qt.NoModifier))
            self.hide()
            f.clearFocus()
        else:
            f.insert(action)


_keypad = None


def _show_keypad(field):
    global _keypad
    if not SETTINGS.calculator:
        return
    if _keypad is None:
        _keypad = _Keypad()
    _keypad.show_for(field)


def _hide_keypad():
    if _keypad is not None:
        _keypad.hide()


def toggle_calculator():
    SETTINGS.calculator = not SETTINGS.calculator
    if not SETTINGS.calculator:
        _hide_keypad()
    save_settings()
    print("Sleepy Scrub calculator: %s" % ("ON" if SETTINGS.calculator else "OFF"))


# --------------------------------------------------------------------------- #
# The app-wide event filter
# --------------------------------------------------------------------------- #
E = QtCore.QEvent
_WATCHED = {
    E.Enter, E.MouseButtonPress, E.MouseButtonDblClick, E.MouseMove,
    E.MouseButtonRelease, E.KeyPress, E.FocusOut,
}


class _Scrubber(QtCore.QObject):

    def __init__(self, parent=None):
        super(_Scrubber, self).__init__(parent)
        self._edit_widget = None
        self._edit_start = None
        self._override = False
        self._undo_open = False
        self._reset_drag()

    def _reset_drag(self):
        self._w = None
        self._press = None
        self._last_x = 0
        self._start = None
        self._value = None
        self._decimals = 3
        self._dragging = False
        self._pen = False
        self._last_commit = 0.0
        self._knob = None        # Nuke knob found for this drag
        self._knob_index = None  # channel index, None = all channels
        self._learning = False   # waiting for knobChanged to tell us the knob
        self._int_mode = False   # learned knob is a frame / integer knob
        self._snap = False       # Alt held: snap to SETTINGS.snap_step

    # -- filter entry point ------------------------------------------------ #
    def eventFilter(self, obj, event):
        if event.type() not in _WATCHED or not isinstance(obj, QtWidgets.QLineEdit):
            return False
        try:
            return self._filter(obj, event)
        except Exception as exc:          # never break Nuke's UI
            self._abort()
            import traceback
            print("sleepy_scrub error:")
            traceback.print_exc()
            return False

    def _eligible(self, w):
        return (SETTINGS.enabled and w.isEnabled() and not w.isReadOnly()
                and _parse_number(w.text()) is not None)

    def _filter(self, obj, event):
        et = event.type()

        # ---- hover cue ---------------------------------------------------- #
        if et == E.Enter:
            if self._eligible(obj) and not obj.hasFocus():
                obj.setCursor(_scrub_cursor())
            return False

        # ---- calculator mode: Enter commits, relative math ----------------- #
        if et == E.KeyPress:
            if (obj is self._edit_widget
                    and event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter)):
                new = self._evaluate(obj.text().strip(), self._edit_start)
                if new is not None:
                    obj.setText(_fmt(new, 6))
                _hide_keypad()
            elif obj is self._edit_widget and event.key() == QtCore.Qt.Key_Escape:
                _hide_keypad()
            return False  # Nuke still gets the Enter and commits as usual

        if et == E.FocusOut:
            if obj is self._edit_widget:
                self._edit_widget = None
                self._edit_start = None
                _hide_keypad()
            return False

        # ---- double-click: reset to default (Flame style) -------------------- #
        if et == E.MouseButtonDblClick:
            if (self._w is None and event.button() == QtCore.Qt.LeftButton
                    and self._eligible(obj) and self._modifier_ok(event)
                    and self._reset_to_default(obj)):
                return True
            # not ours to reset: fall through, the second click just re-enters
            # calculator mode as before

        # ---- press: start tracking, decide later ---------------------------- #
        if et in (E.MouseButtonPress, E.MouseButtonDblClick):
            if (self._w is None and event.button() == QtCore.Qt.LeftButton
                    and not obj.hasFocus() and self._eligible(obj)
                    and self._modifier_ok(event)
                    and not self._expression_locked(obj)):
                self._w = obj
                self._press = _gpos(event)
                self._last_x = self._press.x()
                self._start = self._value = _parse_number(obj.text())
                self._pen = self._detect_pen(event)
                _log("press on %s value=%r pen=%s" % (
                    obj.metaObject().className(), self._start, self._pen))
                return True       # swallowed; a click or drag decides later
            return False

        if obj is not self._w:
            return False

        # ---- move: scrub ---------------------------------------------------- #
        if et == E.MouseMove:
            if not (event.buttons() & QtCore.Qt.LeftButton):
                self._finish()    # release got lost somewhere: clean up
                return True
            x = _gpos(event).x()
            if not self._dragging:
                if abs(x - self._press.x()) < SETTINGS.drag_threshold:
                    return True
                self._begin_drag()
            delta = x - self._last_x
            if delta:
                base = SETTINGS.sensitivity * max(abs(self._start), 1.0)
                if self._int_mode:
                    # whole units at a sane speed however big the value is
                    base = max(min(base, SETTINGS.int_step_max),
                               SETTINGS.int_step_min)
                    self._decimals = 0
                else:
                    # fixed precision for the whole drag, so the number doesn't
                    # change width / jump between 2 and 4 decimals
                    self._decimals = _decimals_for(base * SETTINGS.fine)
                self._value += delta * base * self._speed(event.modifiers())
                self._last_x = x
                self._snap = self._snap_ok(event.modifiers())
                # Mouse: only warp back when the hidden cursor drifts far
                # away. Warping on every move double-counts movement on
                # Windows and makes the speed jerky.
                if (not self._pen
                        and abs(x - self._press.x()) > SETTINGS.warp_radius):
                    QtGui.QCursor.setPos(self._press)
                    self._last_x = self._press.x()
                self._commit()
            return True

        # ---- release ------------------------------------------------------- #
        if et == E.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton:
            self._finish()
            return True

        return False

    # -- drag lifecycle ----------------------------------------------------- #
    def _begin_drag(self):
        self._dragging = True
        self._learning = SETTINGS.commit_method == "knob"
        self._knob_index = _channel_index(self._w)
        _log("drag started (channel index %s)" % self._knob_index)
        nuke = _nuke()
        if nuke:
            nuke.Undo.begin("Scrub value")
            self._undo_open = True
        # mouse: hidden (infinite drag); pen: keep the scrub cursor visible
        QtWidgets.QApplication.setOverrideCursor(
            _scrub_cursor() if self._pen else QtGui.QCursor(QtCore.Qt.BlankCursor))
        self._override = True

    def _finish(self):
        w = self._w
        if self._dragging:
            self._commit(force=True)
            self._end_drag()
            w.deselect()
            _log("drag finished, final %r" % w.text())
        else:
            _log("click -> calculator mode")
            self._enter_edit(w)
        self._reset_drag()

    def _end_drag(self):
        if self._override:
            if not self._pen:
                QtGui.QCursor.setPos(self._press)
            QtWidgets.QApplication.restoreOverrideCursor()
            self._override = False
        if self._undo_open:
            nuke = _nuke()
            if nuke:
                nuke.Undo.end()
            self._undo_open = False

    def _abort(self):
        try:
            self._end_drag()
        finally:
            self._reset_drag()

    # -- pushing values into Nuke ------------------------------------------- #
    def _commit(self, force=False):
        now = time.perf_counter()
        if not force and now - self._last_commit < SETTINGS.commit_interval:
            return
        w = self._w
        v = self._effective_value()
        decimals = self._decimals
        if self._snap and not self._int_mode:
            st = SETTINGS.snap_step
            if st:
                decimals = min(decimals, _decimals_for(st))
        v = round(v, decimals)
        txt = _fmt(v, decimals)

        # Smooth path: we already know the knob -> set it directly.
        if self._knob is not None:
            if self._set_knob(v):
                self._last_commit = now
                return
            self._knob = None            # failed: fall back to typing

        if txt == w.text():
            return                       # nothing new: don't make Nuke re-cook
        method = SETTINGS.commit_method
        if method == "knob":
            method = "type"              # first update is typed (learning)
        send = QtWidgets.QApplication.sendEvent
        NoMod = QtCore.Qt.NoModifier

        if method == "type":
            w.selectAll()
            send(w, QtGui.QKeyEvent(E.KeyPress, QtCore.Qt.Key_unknown, NoMod, txt))
        else:
            w.setText(txt)
            w.setModified(True)

        if method == "signal":
            w.textEdited.emit(txt)
            w.returnPressed.emit()
            w.editingFinished.emit()
        else:
            for t in (E.KeyPress, E.KeyRelease):
                send(w, QtGui.QKeyEvent(t, QtCore.Qt.Key_Return, NoMod))

        w.deselect()                     # no flashing selection while dragging
        _log("commit %s via %s -> field now %r" % (txt, method, w.text()))
        self._last_commit = now

    def _set_knob(self, v):
        k, idx = self._knob, self._knob_index
        try:
            try:
                k.setValue(v) if idx is None else k.setValue(v, idx)
            except TypeError:            # int knobs
                iv = int(round(v))
                k.setValue(iv) if idx is None else k.setValue(iv, idx)
            return True
        except Exception as exc:
            _log("direct set failed on %s: %s" % (k.name(), exc))
            return False

    def _effective_value(self):
        """The value to show / push: whole units on int knobs, Alt snapping."""
        if self._int_mode:
            return float(round(self._value))
        st = SETTINGS.snap_step
        if self._snap and st:
            return round(self._value / st) * st
        return self._value

    @staticmethod
    def _snap_ok(mods):
        st = SETTINGS.snap_step
        if not st or SETTINGS.require_modifier == QtCore.Qt.AltModifier:
            return False                 # Alt is the scrub key itself
        return bool(mods & QtCore.Qt.AltModifier)

    @staticmethod
    def _expression_locked(w):
        """True when a previous scrub learned this field's knob is
        expression-driven: scrubbing would overwrite the expression."""
        knob = _knob_cache.get(w)
        if knob is None:
            return False
        try:
            return bool(knob.hasExpression())
        except Exception:                # node gone or knob unusable
            try:
                del _knob_cache[w]
            except Exception:
                pass
            return False

    def _reset_to_default(self, w):
        """Double-click reset. Only when a scrub already identified the knob;
        returns True when the click was consumed."""
        entry = _knob_cache.get(w)
        if entry is None:
            return False
        knob = entry
        nuke = _nuke()
        if nuke is None:
            return False
        try:
            if knob.hasExpression():
                _log("no reset: %s is expression-driven" % knob.name())
                return False
        except Exception:
            return False                 # knob's node is gone
        idx = _channel_index(w)
        try:
            try:
                dflt = (knob.defaultValue(idx) if idx is not None
                        else knob.defaultValue())
            except TypeError:            # docs: defaultValue() takes no index
                dflt = knob.defaultValue()
            if isinstance(dflt, (list, tuple)) and idx is not None:
                dflt = dflt[idx]
        except Exception as exc:
            _log("no default for %s: %s" % (knob.name(), exc))
            return False

        _hide_keypad()
        if self._edit_widget is w:
            self._edit_widget = None
            self._edit_start = None
        w.clearFocus()
        w.deselect()
        w.setCursor(_scrub_cursor())    # back to the hover cue, not I-beam
        try:
            nuke.Undo.begin("Reset value")
            try:
                if idx is None:
                    try:
                        knob.setValue(dflt)
                    except TypeError:    # int knobs
                        knob.setValue(int(round(dflt)))
                else:
                    try:
                        knob.setValue(dflt, idx)
                    except TypeError:
                        knob.setValue(int(round(dflt)), idx)
            finally:
                nuke.Undo.end()
        except Exception as exc:
            _log("reset failed on %s: %s" % (knob.name(), exc))
            return False
        _log("reset %s to default %r" % (knob.name(), dflt))
        return True

    def learn_knob(self, knob):
        """Called from Nuke's knobChanged while a drag is learning."""
        if not self._learning:
            return
        self._learning = False
        self._knob = knob
        _cache_knob(self._w, knob)
        _log("drag is driving %s.%s directly" % (knob.node().name(), knob.name()))
        try:
            if knob.hasExpression():
                print("sleepy_scrub: %s.%s is expression-driven - scrub "
                      "stopped to protect the expression"
                      % (knob.node().name(), knob.name()))
                self._abort()
                return
        except Exception:
            pass
        try:
            self._int_mode = (SETTINGS.int_aware
                              and knob.Class() in SETTINGS.int_knob_classes)
        except Exception:
            self._int_mode = False
        if self._int_mode:
            self._decimals = 0
            self._last_commit = 0.0      # next move writes a whole number

    # -- calculator mode ---------------------------------------------------- #
    def _enter_edit(self, w):
        w.setFocus(QtCore.Qt.MouseFocusReason)
        w.selectAll()
        w.setCursor(QtCore.Qt.IBeamCursor)
        self._edit_widget = w
        self._edit_start = _parse_number(w.text())
        _show_keypad(w)

    @staticmethod
    def _evaluate(text, start):
        """Returns a float to write back, or None to leave the text to Nuke."""
        if not text or _parse_number(text) is not None:
            return None                      # plain number: nothing to do
        try:
            if text[0] in "+*/" and len(text) > 1 and start is not None:
                return safe_eval("(%r)%s" % (start, text))   # relative
            return safe_eval(text)                           # arithmetic
        except Exception:
            return None                      # e.g. a Nuke expression

    # -- input helpers ------------------------------------------------------ #
    def _detect_pen(self, event):
        if SETTINGS.input_mode == "pen":
            return True
        if SETTINGS.input_mode == "mouse":
            return False
        return _is_stylus(event)

    @staticmethod
    def _modifier_ok(event):
        req = SETTINGS.require_modifier
        return req is None or bool(event.modifiers() & req)

    @staticmethod
    def _speed(mods):
        req = SETTINGS.require_modifier
        if mods & QtCore.Qt.ShiftModifier and req != QtCore.Qt.ShiftModifier:
            return SETTINGS.coarse
        if mods & QtCore.Qt.ControlModifier and req != QtCore.Qt.ControlModifier:
            return SETTINGS.fine
        return 1.0


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
_instance = None


_menu_added = False


def install():
    global _instance
    if _instance is None:
        app = QtWidgets.QApplication.instance()
        if app is None:
            raise RuntimeError("sleepy_scrub needs a running Qt application (Nuke GUI).")
        if app.property(_APP_FLAG):
            return None                    # another copy is already running
        app.setProperty(_APP_FLAG, True)
        _instance = _Scrubber(app)
        app.installEventFilter(_instance)
        nuke = _nuke()
        if nuke:
            try:
                nuke.addKnobChanged(_on_knob_changed)
            except Exception as exc:
                print("sleepy_scrub: couldn't hook knobChanged (%s); "
                      "falling back to typed updates" % exc)
    _ensure_menu()
    return _instance


def _ensure_menu(tries=20):
    """Add the menu now, or retry shortly if Nuke's menu bar isn't built yet
    (happens when this is imported early, e.g. from an auto-installer)."""
    global _menu_added
    if _menu_added:
        return
    try:
        _add_menu()
        _menu_added = True
    except Exception:
        if tries > 0:
            QtCore.QTimer.singleShot(500, lambda: _ensure_menu(tries - 1))
        else:
            print("sleepy_scrub: couldn't add the menu (scrubbing still works).")


def uninstall():
    global _instance
    if _instance is None:
        return
    QtWidgets.QApplication.instance().removeEventFilter(_instance)
    QtWidgets.QApplication.instance().setProperty(_APP_FLAG, False)
    nuke = _nuke()
    if nuke:
        try:
            nuke.removeKnobChanged(_on_knob_changed)
        except Exception:
            pass
    _instance.deleteLater()
    _instance = None


def toggle():
    SETTINGS.enabled = not SETTINGS.enabled
    save_settings()
    print("Sleepy Scrub: %s" % ("ON" if SETTINGS.enabled else "OFF"))


def set_input_mode(mode):
    if mode not in ("auto", "mouse", "pen"):
        raise ValueError("mode must be 'auto', 'mouse' or 'pen'")
    SETTINGS.input_mode = mode
    save_settings()
    print("Sleepy Scrub input mode: %s" % mode)


def toggle_int_mode():
    """Frame / integer knobs scrub in whole steps (on by default)."""
    SETTINGS.int_aware = not SETTINGS.int_aware
    save_settings()
    print("Sleepy Scrub frame/int steps: %s"
          % ("ON" if SETTINGS.int_aware else "OFF"))


def set_snap_step(step):
    """The increment Alt+drag snaps to; None turns snapping off."""
    if step is not None:
        try:
            step = float(step)
        except (TypeError, ValueError):
            raise ValueError("step must be a positive number or None")
        if step <= 0:
            raise ValueError("step must be a positive number or None")
    SETTINGS.snap_step = step
    save_settings()
    print("Sleepy Scrub snap step (Alt+drag): %s"
          % ("off" if step is None else step))


def open_settings_folder():
    folder = os.path.dirname(_SETTINGS_FILE)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))


def _add_menu():
    nuke = _nuke()
    if not nuke or not nuke.GUI:
        return
    bar = nuke.menu("Nuke")
    if bar is None:
        raise RuntimeError("menu bar not ready")
    m = bar.addMenu("SleepyTools").addMenu("Scrub Fields")
    m.addCommand("Toggle On - Off", "import sleepy_scrub; sleepy_scrub.toggle()")
    m.addCommand("Calculator On - Off", "import sleepy_scrub; sleepy_scrub.toggle_calculator()")
    m.addSeparator()
    for mode in ("auto", "mouse", "pen"):
        m.addCommand("Input: %s" % mode.capitalize(),
                     "import sleepy_scrub; sleepy_scrub.set_input_mode(%r)" % mode)
    m.addSeparator()
    m.addCommand("Int Steps On - Off", "import sleepy_scrub; sleepy_scrub.toggle_int_mode()")
    for label, value in (("Off", None), ("Whole", 1.0), ("0.1", 0.1), ("0.01", 0.01)):
        m.addCommand("Snap: %s" % label,
                     "import sleepy_scrub; sleepy_scrub.set_snap_step(%r)" % value)
    m.addSeparator()
    for style in ("sleepy", "system"):
        m.addCommand("Cursor: %s" % style.capitalize(),
                     "import sleepy_scrub; sleepy_scrub.set_cursor_style(%r)" % style)
    m.addSeparator()
    for method in ("knob", "type", "return", "signal"):
        m.addCommand("Commit: %s" % method.capitalize(),
                     "import sleepy_scrub; sleepy_scrub.set_commit_method(%r)" % method)
    m.addCommand("Debug Log On - Off", "import sleepy_scrub; sleepy_scrub.toggle_debug()")
    m.addCommand("Open Settings Folder", "import sleepy_scrub; sleepy_scrub.open_settings_folder()")


# --------------------------------------------------------------------------- #
# Auto-install when imported inside a Nuke GUI session
# --------------------------------------------------------------------------- #
try:
    import nuke as _nuke_mod
    if _nuke_mod.GUI:
        install()
except ImportError:
    pass      # not running inside Nuke
except Exception as _exc:
    print("sleepy_scrub: auto-install failed: %s" % _exc)
