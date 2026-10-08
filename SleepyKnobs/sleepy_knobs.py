"""Sleepy Knobs for Nuke.

Right-click any animatable knob > "Sleepy Knob Expressions…" to put a ready-made expression on it:
wiggle, jitter, sine, square and saw waves, bounce, spring, ease, flicker, constant speed,
random per node, quantise, clamp, and key-based ones like loop, ping-pong, time offset,
stepped (on twos), smoothing and speed change. Each comes with a live curve preview and, if you
like, slider knobs on a "Sleepy Anim" tab so you can keep tweaking it. Bake to keys when you're done
(safe for the farm and for exporting).

Install: put the SleepyKnobs folder in ~/.nuke and add to ~/.nuke/init.py:
    nuke.pluginAddPath('./SleepyKnobs')
"""
import math
import os
import re

import nuke

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
TAB_NAME = "sleepy_anim"
ICON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sleepy_icon.png")

# ---------------------------------------------------------------- presets
# {base} is the knob's own value: a number, 'curve' when it has keys, or its previous expression.
# {name} placeholders are the preset's parameters.
PRESETS = [
    {"id": "wiggle", "group": "Procedural", "title": "Wiggle",
     "desc": "Smooth random motion (fractal noise). Camera shake, floating, handheld drift.",
     "params": [("amplitude", 10.0, 0, 100), ("frequency", 0.15, 0.001, 2), ("octaves", 2, 1, 6), ("seed", 1, 0, 100), ("offset", 0.0, -1000, 1000)],
     "expr": "{base} + {amplitude}*fBm((frame + {offset})*{frequency} + {seed}*17.31 + 0.31, {seed}*7.13 + 0.37, 0.53, {octaves}, 2, 0.5)"},
    {"id": "jitter", "group": "Procedural", "title": "Jitter (random per frame)",
     "desc": "A new random value every 'hold' frames: hard, stepped shake or flicker.",
     "params": [("amplitude", 5.0, 0, 100), ("hold", 1, 1, 24), ("seed", 1, 0, 100), ("offset", 0.0, -1000, 1000)],
     "expr": "{base} + {amplitude}*(random(floor((frame + {offset})/{hold}), {seed}, 0.5)*2 - 1)"},
    {"id": "flicker", "group": "Procedural", "title": "Flicker (multiply)",
     "desc": "Scales the value by a wobbling amount: light flicker, fire, neon. amount 0.2 = ±20%.",
     "params": [("amount", 0.2, 0, 1), ("speed", 0.6, 0.01, 3), ("seed", 1, 0, 100)],
     "expr": "{base}*(1 + {amount}*fBm(frame*{speed} + {seed}*11.7 + 0.29, {seed}*3.1 + 0.41, 0.6, 3, 2, 0.5))"},
    {"id": "sine", "group": "Procedural", "title": "Sine wave",
     "desc": "Smooth back-and-forth. period in frames, phase in degrees.",
     "params": [("amplitude", 10.0, 0, 100), ("period", 48, 1, 500), ("phase", 0.0, -360, 360), ("start", 1001, -10000, 10000)],
     "expr": "{base} + {amplitude}*sin(((frame - {start})/{period} + {phase}/360)*2*pi)"},
    {"id": "square", "group": "Procedural", "title": "Square wave (on/off)",
     "desc": "Switches between base and base + amplitude. duty is the fraction of each period that's on. Blinking lights, strobes.",
     "params": [("amplitude", 1.0, -100, 100), ("period", 12, 1, 500), ("duty", 0.5, 0, 1), ("start", 1001, -10000, 10000)],
     "expr": "{base} + {amplitude}*(1 - step({duty}, fmod(fmod(frame - {start}, {period}) + {period}, {period})/{period}))"},
    {"id": "saw", "group": "Procedural", "title": "Sawtooth (ramp and reset)",
     "desc": "Ramps from base to base + amplitude every period, then jumps back. Scrolling textures, scanning bars.",
     "params": [("amplitude", 100.0, -1000, 1000), ("period", 24, 1, 500), ("start", 1001, -10000, 10000)],
     "expr": "{base} + {amplitude}*fmod(fmod(frame - {start}, {period}) + {period}, {period})/{period}"},
    {"id": "linear", "group": "Procedural", "title": "Constant speed",
     "desc": "Moves at a fixed speed per frame from the start frame. Drifting clouds, conveyor belts.",
     "params": [("speed", 2.0, -100, 100), ("start", 1001, -10000, 10000)],
     "expr": "{base} + {speed}*(frame - {start})"},
    {"id": "bounce", "group": "Procedural", "title": "Bounce",
     "desc": "Bounces up by amplitude from the start frame and loses height each bounce.",
     "params": [("amplitude", 50.0, -500, 500), ("period", 16, 1, 200), ("decay", 0.05, 0, 1), ("start", 1001, -10000, 10000)],
     "expr": "{base} + {amplitude}*abs(sin(max(0, frame - {start})*pi/{period}))*exp(-max(0, frame - {start})*{decay})*step({start}, frame)"},
    {"id": "spring", "group": "Procedural", "title": "Spring settle",
     "desc": "Starts offset by amplitude and wobbles back to the base value. Overshoots, impacts, UI pops.",
     "params": [("amplitude", 30.0, -500, 500), ("period", 10, 1, 200), ("damping", 0.12, 0, 1), ("start", 1001, -10000, 10000)],
     "expr": "{base} + {amplitude}*cos(max(0, frame - {start})*2*pi/{period})*exp(-max(0, frame - {start})*{damping})*step({start}, frame)"},
    {"id": "ease", "group": "Procedural", "title": "Ease between two values",
     "desc": "Smoothly goes from one value to another between two frames, with no keys.",
     "params": [("from_value", 0.0, -1000, 1000), ("to_value", 1.0, -1000, 1000), ("start", 1001, -10000, 10000), ("end", 1025, -10000, 10000)],
     "expr": "{from_value} + ({to_value} - {from_value})*smoothstep({start}, {end}, frame)", "uses_base": False},
    {"id": "random_instance", "group": "Procedural", "title": "Random per node",
     "desc": "A constant random offset that depends on the seed. Copy the node and change the seed to vary each copy.",
     "params": [("amplitude", 10.0, 0, 1000), ("seed", 1, 0, 1000)],
     "expr": "{base} + {amplitude}*(random({seed}, 0.5, 0.5)*2 - 1)"},
    {"id": "quantize", "group": "Procedural", "title": "Quantise (snap)",
     "desc": "Snaps the value to multiples of step size: stepped rotation, pixel-snapped moves.",
     "params": [("step_size", 1.0, 0.001, 100)],
     "expr": "floor({base}/{step_size} + 0.5)*{step_size}"},
    {"id": "clamp", "group": "Procedural", "title": "Clamp",
     "desc": "Keeps the value between a minimum and maximum.",
     "params": [("minimum", 0.0, -1000, 1000), ("maximum", 1.0, -1000, 1000)],
     "expr": "clamp({base}, {minimum}, {maximum})"},
    {"id": "loop", "group": "From keys", "title": "Loop keys", "keys": True,
     "desc": "Repeats the keyed animation between first and last forever (cycle).",
     "params": [("first", 1001, -10000, 10000), ("last", 1025, -10000, 10000)],
     "expr": "curve({first} + fmod(fmod(frame - {first}, {last} - {first}) + ({last} - {first}), {last} - {first}))"},
    {"id": "pingpong", "group": "From keys", "title": "Ping-pong keys", "keys": True,
     "desc": "Plays the keyed animation forward then backward, forever.",
     "params": [("first", 1001, -10000, 10000), ("last", 1025, -10000, 10000)],
     "expr": "curve({first} + ({last} - {first}) - abs(fmod(fmod(frame - {first}, 2*({last} - {first})) + 2*({last} - {first}), 2*({last} - {first})) - ({last} - {first})))"},
    {"id": "time_offset", "group": "From keys", "title": "Time offset (delay)", "keys": True,
     "desc": "Plays the keys later (positive) or earlier (negative), without moving them.",
     "params": [("offset", 5.0, -500, 500)],
     "expr": "curve(frame - {offset})"},
    {"id": "speed_change", "group": "From keys", "title": "Speed change", "keys": True,
     "desc": "Plays the keys faster (above 1) or slower, measured from the start frame.",
     "params": [("speed", 0.5, 0.01, 10), ("start", 1001, -10000, 10000)],
     "expr": "curve({start} + (frame - {start})*{speed})"},
    {"id": "on_twos", "group": "From keys", "title": "Stepped (on twos)", "keys": True,
     "desc": "Holds each value for N frames: stop-motion or animation-on-twos feel.",
     "params": [("step_frames", 2, 1, 24), ("start", 1001, -10000, 10000)],
     "expr": "curve(floor((frame - {start})/{step_frames})*{step_frames} + {start})"},
    {"id": "smooth", "group": "From keys", "title": "Smooth (5-tap average)", "keys": True,
     "desc": "Averages the curve over 5 samples spread frames apart: calms jittery tracks without re-tracking.",
     "params": [("spread", 1.0, 0.25, 10)],
     "expr": "(curve(frame - 2*{spread}) + curve(frame - {spread}) + curve(frame) + curve(frame + {spread}) + curve(frame + 2*{spread}))/5"},
    {"id": "hold", "group": "From keys", "title": "Hold at frame", "keys": True,
     "desc": "Freezes the value at one frame of the existing animation.",
     "params": [("hold_frame", 1001, -10000, 10000)],
     "expr": "curve({hold_frame})"},
    {"id": "link", "group": "Link", "title": "Link to another knob",
     "desc": "Follows another knob (Node.knob or Node.knob.x) with a multiplier, offset and optional delay.",
     "params": [("target", "Transform1.translate.x", None, None), ("multiply", 1.0, -100, 100), ("add", 0.0, -1000, 1000)],
     "expr": "{target}*{multiply} + {add}", "uses_base": False},
]
PRESET_BY_ID = dict((p["id"], p) for p in PRESETS)


# ---------------------------------------------------------------- knob helpers
def channel_names(knob):
    n = knob.arraySize() if hasattr(knob, "arraySize") else 1
    names = []
    for i in range(n):
        try:
            names.append(knob.names(i))
        except Exception:
            names.append(("x", "y", "z", "w")[i] if n <= 4 else str(i))
    return names


def is_animatable(knob):
    return isinstance(knob, nuke.Array_Knob) and not isinstance(knob, (nuke.Boolean_Knob, nuke.Enumeration_Knob)) \
        and hasattr(knob, "setExpression")


def animatable_knobs(node):
    out = []
    for name, k in node.knobs().items():
        try:
            if not is_animatable(k) or name.startswith(TAB_NAME) or "__div" in name:
                continue
            if hasattr(k, "visible") and not k.visible():
                continue
            out.append(name)
        except Exception:
            pass
    return sorted(out)


def has_keys(knob, ch):
    try:
        curve = knob.animation(ch)
        return curve is not None and len(curve.keys()) > 0
    except Exception:
        return False


def key_range(knob, ch):
    try:
        ks = knob.animation(ch).keys()
        if ks:
            return int(ks[0].x), int(ks[-1].x)
    except Exception:
        pass
    return None


def base_of(knob, ch):
    """Expression text for the knob's current value: its expression, 'curve' for keys, or the number."""
    try:
        if knob.hasExpression(ch):
            ex = knob.animation(ch).expression()
            if ex and ex.strip() != "curve":
                return "(%s)" % ex
    except Exception:
        pass
    if has_keys(knob, ch):
        return "curve"
    v = knob.value(ch) if knob.arraySize() > 1 else knob.value()
    return repr(round(float(v), 6))


def _fmt(v):
    if isinstance(v, str):
        return v
    if float(v).is_integer():
        return str(int(v))
    return repr(round(float(v), 6))


def control_prefix(knob, ch):
    names = channel_names(knob)
    field = names[ch] if knob.arraySize() > 1 else ""
    return re.sub(r"\W+", "_", knob.name() + ("_" + field if field else "")).strip("_")


def build_expression(preset, knob, ch, values, controls):
    """The Nuke expression for one channel. With controls, parameters refer to knobs on the node."""
    prefix = control_prefix(knob, ch)
    subs = {"base": base_of(knob, ch)}
    for name, default, lo, hi in preset["params"]:
        v = values.get(name, default)
        if controls and not isinstance(default, str):
            subs[name] = "%s_%s" % (prefix, name)
        else:
            subs[name] = _fmt(v)
        if name == "seed" and ch > 0:  # x, y, z get different random streams from the same seed
            subs[name] = "(%s + %d)" % (subs[name], ch * 101)
    return preset["expr"].format(**subs)


# ---------------------------------------------------------------- apply / bake / remove
def _ensure_tab(node):
    if TAB_NAME not in node.knobs():
        node.addKnob(nuke.Tab_Knob(TAB_NAME, "Sleepy Anim"))


def remove_controls(node, prefix):
    for name in list(node.knobs().keys()):
        if name.startswith(prefix + "_") or name == prefix + "__div":
            try:
                node.removeKnob(node.knobs()[name])
            except Exception:
                pass


def apply(node, knob, channels, preset_id, values=None, controls=True):
    preset = PRESET_BY_ID[preset_id]
    values = values or {}
    undo = nuke.Undo()
    undo.begin("Sleepy Knob Expression: %s" % preset["title"])
    try:
        for ch in channels:
            prefix = control_prefix(knob, ch)
            expr = build_expression(preset, knob, ch, values, controls)
            if controls:
                remove_controls(node, prefix)
                _ensure_tab(node)
                label = "%s · %s" % (prefix.replace("_", "."), preset["title"])
                node.addKnob(nuke.Text_Knob(prefix + "__div", "", "<b>%s</b>" % label))
                for name, default, lo, hi in preset["params"]:
                    if isinstance(default, str):
                        continue
                    v = values.get(name, default)
                    k = nuke.Double_Knob("%s_%s" % (prefix, name), name.replace("_", " "))
                    k.setRange(lo, hi)
                    node.addKnob(k)
                    k.setValue(float(v))
            if knob.arraySize() > 1:
                knob.setExpression(expr, ch)
            else:
                knob.setExpression(expr)
    finally:
        undo.end()


def bake(node, knob, channels, first, last, step=1):
    """Turn the expression into keys over first-last, then remove the expression and its controls."""
    undo = nuke.Undo()
    undo.begin("Sleepy Knob Expression: bake")
    try:
        for ch in channels:
            if not knob.hasExpression(ch):
                continue
            values = [(f, knob.getValueAt(f, ch)) for f in range(int(first), int(last) + 1, max(1, int(step)))]
            curve = knob.animation(ch)
            curve.clear()
            for f, v in values:
                curve.setKey(f, v)
            curve.setExpression("curve")
            remove_controls(node, control_prefix(knob, ch))
        _drop_empty_tab(node)
    finally:
        undo.end()


def remove(node, knob, channels):
    """Remove the expression: back to keys if there are any, otherwise to the current value."""
    undo = nuke.Undo()
    undo.begin("Sleepy Knob Expression: remove")
    try:
        for ch in channels:
            if has_keys(knob, ch):
                knob.animation(ch).setExpression("curve")
            else:
                v = knob.getValueAt(nuke.frame(), ch)
                knob.clearAnimated(ch)
                if knob.arraySize() > 1:
                    knob.setValue(v, ch)
                else:
                    knob.setValue(v)
            remove_controls(node, control_prefix(knob, ch))
        _drop_empty_tab(node)
    finally:
        undo.end()


def _drop_empty_tab(node):
    names = list(node.knobs().keys())
    if TAB_NAME in names and not any("__div" in n for n in names):
        try:
            node.removeKnob(node.knobs()[TAB_NAME])
        except Exception:
            pass


# ---------------------------------------------------------------- preview (approximate, in Python)
def _fract(v):
    return v - math.floor(v)


def _hash(x, y, z):
    return _fract(math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453123)


def _noise(x, y=0.0, z=0.0):
    xi, yi, zi = math.floor(x), math.floor(y), math.floor(z)
    xf, yf, zf = [t * t * (3 - 2 * t) for t in (x - xi, y - yi, z - zi)]
    def h(a, b, c):
        return _hash(xi + a, yi + b, zi + c) * 2 - 1
    def L(a, b, t):
        return a + (b - a) * t
    return L(L(L(h(0, 0, 0), h(1, 0, 0), xf), L(h(0, 1, 0), h(1, 1, 0), xf), yf),
             L(L(h(0, 0, 1), h(1, 0, 1), xf), L(h(0, 1, 1), h(1, 1, 1), xf), yf), zf)


def _fbm(x, y, z, octaves, lac, gain):
    s, amp, f = 0.0, 1.0, 1.0
    for _ in range(int(octaves)):
        s += _noise(x * f, y * f, z * f) * amp
        amp *= gain
        f *= lac
    return s


PREVIEW_FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "abs": abs, "exp": math.exp, "log": math.log,
    "sqrt": math.sqrt, "pow": math.pow, "floor": math.floor, "ceil": math.ceil, "pi": math.pi,
    "min": min, "max": max, "fmod": math.fmod, "atan2": math.atan2,
    "clamp": lambda v, lo=0.0, hi=1.0: min(max(v, lo), hi),
    "lerp": lambda a, b, t: a + (b - a) * t, "mix": lambda a, b, t: a + (b - a) * t,
    "step": lambda e, v: 0.0 if v < e else 1.0,
    "smoothstep": lambda a, b, v: 0.0 if v <= a else 1.0 if v >= b else ((v - a) / (b - a)) ** 2 * (3 - 2 * (v - a) / (b - a)),
    "random": lambda x, y=0.0, z=0.0: _hash(x, y, z), "noise": _noise, "fBm": _fbm,
}


def preview_series(preset, values, frames, base_value, curve_fn, target_fn=None, ch=0):
    """Evaluate a preset over frames. curve_fn(t) samples the original curve; base_value is a number
    or None when the base is the curve. Returns a list of floats (None where it fails)."""
    subs = {"base": "curve(frame)" if base_value is None else repr(float(base_value))}
    for name, default, lo, hi in preset["params"]:
        v = values.get(name, default)
        subs[name] = "target(frame)" if isinstance(default, str) else repr(float(v) + (ch * 101 if name == "seed" else 0))
    py = preset["expr"].format(**subs)
    py = re.sub(r"\bcurve\b(?!\s*\()", "curve(frame)", py)
    code = compile(py, "<preset>", "eval")
    out = []
    for f in frames:
        ns = dict(PREVIEW_FUNCS)
        ns.update({"frame": float(f), "curve": curve_fn, "target": target_fn or (lambda t: 0.0)})
        try:
            v = float(eval(code, {"__builtins__": {}}, ns))
            out.append(v if math.isfinite(v) else None)
        except Exception:
            out.append(None)
    return out


# ---------------------------------------------------------------- dialog
_dialog = None


class _Plot(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(_Plot, self).__init__(parent)
        self.setMinimumHeight(170)
        self.frames, self.before, self.after = [], [], []

    def set_data(self, frames, before, after):
        self.frames, self.before, self.after = frames, before, after
        self.update()

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = self.rect().adjusted(40, 10, -10, -22)
        p.fillRect(self.rect(), QtGui.QColor(34, 35, 38))
        vals = [v for v in self.before + self.after if v is not None]
        if not self.frames or not vals:
            p.setPen(QtGui.QColor(150, 150, 150))
            p.drawText(self.rect(), QtCore.Qt.AlignCenter, "No preview")
            return
        lo, hi = min(vals), max(vals)
        if hi - lo < 1e-9:
            lo, hi = lo - 1, hi + 1
        pad = (hi - lo) * 0.08
        lo, hi = lo - pad, hi + pad
        f0, f1 = self.frames[0], self.frames[-1]

        def pt(f, v):
            x = r.left() + (f - f0) / float(max(1, f1 - f0)) * r.width()
            y = r.bottom() - (v - lo) / (hi - lo) * r.height()
            return QtCore.QPointF(x, y)

        p.setPen(QtGui.QPen(QtGui.QColor(70, 72, 78), 1))
        for i in range(5):
            y = r.top() + i * r.height() / 4.0
            p.drawLine(QtCore.QPointF(r.left(), y), QtCore.QPointF(r.right(), y))
            p.setPen(QtGui.QColor(140, 140, 140))
            p.drawText(QtCore.QRectF(0, y - 8, 36, 16), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, "%.3g" % (hi - i * (hi - lo) / 4))
            p.setPen(QtGui.QPen(QtGui.QColor(70, 72, 78), 1))
        p.setPen(QtGui.QColor(140, 140, 140))
        p.drawText(QtCore.QRectF(r.left(), r.bottom() + 4, 80, 16), QtCore.Qt.AlignLeft, str(f0))
        p.drawText(QtCore.QRectF(r.right() - 80, r.bottom() + 4, 80, 16), QtCore.Qt.AlignRight, str(f1))
        for series, color, width in ((self.before, QtGui.QColor(120, 125, 135), 1.2), (self.after, QtGui.QColor(240, 160, 67), 2.0)):
            path, started = QtGui.QPainterPath(), False
            for f, v in zip(self.frames, series):
                if v is None:
                    started = False
                    continue
                if not started:
                    path.moveTo(pt(f, v))
                    started = True
                else:
                    path.lineTo(pt(f, v))
            p.setPen(QtGui.QPen(color, width))
            p.drawPath(path)


class KnobLabDialog(QtWidgets.QDialog):
    def __init__(self, node, knob_name=None, fields=None, parent=None):
        super(KnobLabDialog, self).__init__(parent)
        self.setWindowTitle("Sleepy Knob Expressions")
        # without its own icon the window shows its parent's (Nuke's)
        icon = QtGui.QIcon(ICON_FILE)
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        self.resize(760, 560)
        self.node = node
        self.fields_wanted = fields
        lay = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("<b>%s</b>" % node.name()))
        self.knob_box = QtWidgets.QComboBox()
        self.knob_box.addItems(animatable_knobs(node))
        if knob_name:
            i = self.knob_box.findText(knob_name)
            if i >= 0:
                self.knob_box.setCurrentIndex(i)
        self.knob_box.currentIndexChanged.connect(self._knob_changed)
        top.addWidget(self.knob_box)
        self.field_row = QtWidgets.QHBoxLayout()
        top.addLayout(self.field_row)
        top.addStretch(1)
        top.addWidget(QtWidgets.QLabel("preview"))
        r0, r1 = self._root_range()
        self.f0, self.f1 = QtWidgets.QSpinBox(), QtWidgets.QSpinBox()
        for s, v in ((self.f0, r0), (self.f1, r1)):
            s.setRange(-100000, 100000)
            s.setValue(v)
            s.valueChanged.connect(self.refresh)
            top.addWidget(s)
        lay.addLayout(top)

        mid = QtWidgets.QHBoxLayout()
        self.list = QtWidgets.QTreeWidget()
        self.list.setHeaderHidden(True)
        self.list.setMaximumWidth(230)
        groups = {}
        for pr in PRESETS:
            g = groups.get(pr["group"])
            if g is None:
                g = QtWidgets.QTreeWidgetItem([pr["group"]])
                g.setFlags(g.flags() & ~QtCore.Qt.ItemIsSelectable)
                f = g.font(0)
                f.setBold(True)
                g.setFont(0, f)
                self.list.addTopLevelItem(g)
                g.setExpanded(True)
                groups[pr["group"]] = g
            it = QtWidgets.QTreeWidgetItem([pr["title"]])
            it.setData(0, QtCore.Qt.UserRole, pr["id"])
            it.setToolTip(0, pr["desc"])
            g.addChild(it)
        self.list.currentItemChanged.connect(self._preset_changed)
        mid.addWidget(self.list)
        right = QtWidgets.QVBoxLayout()
        self.desc = QtWidgets.QLabel()
        self.desc.setWordWrap(True)
        right.addWidget(self.desc)
        self.form = QtWidgets.QFormLayout()
        right.addLayout(self.form)
        self.plot = _Plot()
        right.addWidget(self.plot, 1)
        self.expr_view = QtWidgets.QLineEdit()
        self.expr_view.setReadOnly(True)
        right.addWidget(self.expr_view)
        mid.addLayout(right, 1)
        lay.addLayout(mid, 1)

        bottom = QtWidgets.QHBoxLayout()
        self.chk_controls = QtWidgets.QCheckBox("Add slider knobs (Sleepy Anim tab)")
        self.chk_controls.setChecked(True)
        self.chk_controls.toggled.connect(self.refresh)
        bottom.addWidget(self.chk_controls)
        bottom.addStretch(1)
        for label, fn in (("Remove expression", self._remove), ("Bake to keys", self._bake), ("Apply", self._apply)):
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(fn)
            bottom.addWidget(b)
            if label == "Apply":
                b.setDefault(True)
                b.setStyleSheet("QPushButton { font-weight: bold; padding: 5px 16px; }")
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        lay.addLayout(bottom)

        self.fields = {}
        self.field_checks = []
        self._knob_changed()
        first = self.list.topLevelItem(0).child(0)
        self.list.setCurrentItem(first)

    # ---- state
    def _root_range(self):
        try:
            return int(nuke.root()["first_frame"].value()), int(nuke.root()["last_frame"].value())
        except Exception:
            return 1001, 1100

    def knob(self):
        name = self.knob_box.currentText()
        return self.node.knobs().get(name)

    def channels(self):
        return [i for i, c in enumerate(self.field_checks) if c.isChecked()]

    def preset(self):
        it = self.list.currentItem()
        if it is None or it.parent() is None:
            return None
        return PRESET_BY_ID[it.data(0, QtCore.Qt.UserRole)]

    def values(self):
        out = {}
        for name, w in self.fields.items():
            out[name] = w.text() if isinstance(w, QtWidgets.QLineEdit) else w.value()
        return out

    # ---- UI updates
    def _knob_changed(self, *a):
        while self.field_row.count():
            w = self.field_row.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.field_checks = []
        k = self.knob()
        if k is None:
            return
        names = channel_names(k)
        for i, n in enumerate(names):
            c = QtWidgets.QCheckBox(n if len(names) > 1 else "value")
            c.setChecked(self.fields_wanted is None or n in self.fields_wanted or len(names) == 1)
            c.toggled.connect(self.refresh)
            self.field_row.addWidget(c)
            self.field_checks.append(c)
        self.fields_wanted = None
        self._preset_changed()

    def _preset_changed(self, *a):
        pr = self.preset()
        while self.form.rowCount():
            self.form.removeRow(0)
        self.fields = {}
        if pr is None:
            return
        self.desc.setText(pr["desc"] + ("\n\nNeeds keyframes on this knob." if pr.get("keys") else ""))
        k = self.knob()
        chans = self.channels() or [0]
        kr = key_range(k, chans[0]) if k is not None else None
        r0, r1 = self._root_range()
        for name, default, lo, hi in pr["params"]:
            if isinstance(default, str):
                w = QtWidgets.QLineEdit(default)
                w.textChanged.connect(self.refresh)
            else:
                v = default
                if name in ("start", "first", "hold_frame"):
                    v = kr[0] if (kr and name != "start") else r0
                elif name == "last":
                    v = kr[1] if kr else r1
                elif name == "end":
                    v = r0 + 24
                if isinstance(default, int):
                    w = QtWidgets.QSpinBox()
                    w.setRange(-1000000, 1000000)
                else:
                    w = QtWidgets.QDoubleSpinBox()
                    w.setRange(-1e7, 1e7)
                    w.setDecimals(4)
                    w.setSingleStep(max(1e-4, (hi - lo) / 100.0))
                w.setValue(v)
                w.valueChanged.connect(self.refresh)
            self.fields[name] = w
            self.form.addRow(name.replace("_", " "), w)
        self.refresh()

    def refresh(self, *a):
        pr, k = self.preset(), self.knob()
        if pr is None or k is None:
            return
        chans = self.channels()
        ch = chans[0] if chans else 0
        f0, f1 = self.f0.value(), self.f1.value()
        if f1 <= f0:
            f1 = f0 + 1
        frames = list(range(f0, f1 + 1))
        before = [k.getValueAt(f, ch) for f in frames]
        cache = dict(zip(frames, before))

        def curve_fn(t):
            t0 = int(math.floor(t))
            if t0 in cache and t0 + 1 in cache:
                return cache[t0] + (cache[t0 + 1] - cache[t0]) * (t - t0)
            return k.getValueAt(t, ch)

        def target_fn(t):
            parts = self.values().get("target", "").split(".")
            n = nuke.toNode(parts[0]) if parts and parts[0] else None
            if n is None or len(parts) < 2 or parts[1] not in n.knobs():
                return 0.0
            tk = n[parts[1]]
            idx = 0
            if len(parts) > 2:
                names = channel_names(tk)
                idx = names.index(parts[2]) if parts[2] in names else 0
            return tk.getValueAt(t, idx)

        base = base_of(k, ch)
        base_value = None if (base == "curve" or base.startswith("(")) else float(base)
        after = preview_series(pr, self.values(), frames, base_value, curve_fn, target_fn, ch)
        self.plot.set_data(frames, before, after)
        self.expr_view.setText(build_expression(pr, k, ch, self.values(), self.chk_controls.isChecked()))

    # ---- actions
    def _check(self):
        pr, k = self.preset(), self.knob()
        if pr is None or k is None or not self.channels():
            nuke.message("Pick a knob, at least one field and an expression.")
            return None
        if pr.get("keys") and not any(has_keys(k, c) for c in self.channels()):
            nuke.message("%s works on keyframes, and %s has none. Set some keys first." % (pr["title"], k.name()))
            return None
        return pr, k

    def _apply(self):
        ok = self._check()
        if ok:
            apply(self.node, ok[1], self.channels(), ok[0]["id"], self.values(), self.chk_controls.isChecked())
            self.refresh()

    def _bake(self):
        k = self.knob()
        if k is None:
            return
        bake(self.node, k, self.channels(), self.f0.value(), self.f1.value())
        self.refresh()

    def _remove(self):
        k = self.knob()
        if k is None:
            return
        remove(self.node, k, self.channels())
        self.refresh()


def _show_dialog(node, knob_name=None, fields=None):
    global _dialog
    parent = QtWidgets.QApplication.activeWindow()
    _dialog = KnobLabDialog(node, knob_name, fields, parent)
    _dialog.show()
    _dialog.raise_()
    return _dialog


def open_for_knob():
    """Animation menu entry: open the dialog on the knob that was right-clicked."""
    knob = nuke.thisKnob()
    node = nuke.thisNode()
    if knob is None or node is None or not is_animatable(knob):
        nuke.message("Right-click a number knob (like translate, size or mix) to use Sleepy Knob Expressions.")
        return
    fields = None
    try:
        names = nuke.animations()
        fields = [n.split(".")[-1] for n in names] if names else None
    except Exception:
        fields = None
    return _show_dialog(node, knob.name(), fields)


def open_for_selected():
    try:
        node = nuke.selectedNode()
    except ValueError:
        nuke.message("Select a node first, or right-click any number knob > Sleepy Knob Expressions…")
        return
    return _show_dialog(node)


def bake_this_knob():
    knob, node = nuke.thisKnob(), nuke.thisNode()
    if knob is None or not is_animatable(knob):
        return
    r0 = int(nuke.root()["first_frame"].value())
    r1 = int(nuke.root()["last_frame"].value())
    bake(node, knob, range(knob.arraySize()), r0, r1)


_installed = False


def install(menu="SleepyTools"):
    global _installed
    if _installed:
        return
    if getattr(nuke, "_sleepy_knob_lab_installed", False):
        _installed = True           # installed by an earlier copy of this module
        return
    anim = nuke.menu("Animation")
    anim.addCommand("Sleepy Knob Expressions…", "sleepy_knobs.open_for_knob()")
    anim.addCommand("Sleepy Bake expression to keys", "sleepy_knobs.bake_this_knob()")
    nuke.menu("Nuke").addMenu(menu).addCommand("Knob Expression Lab", "sleepy_knobs.open_for_selected()")
    nuke._sleepy_knob_lab_installed = True
    _installed = True
