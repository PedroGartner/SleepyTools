"""Sleepy Doctor 2 for Nuke.

Checks a Nuke script for problems and explains each one: what's wrong, why it matters, how to
fix it, with a link to the Foundry docs. Runs as a floating window or docked next to Properties.

Scans
  Quick scan        whole script, file and graph checks (fast)
  Full scan         adds performance: bounding boxes (grouped back to where they start),
                    big scales, upscales, large filters, heavy nodes, channel load
  Selection / Upstream of selection / Between two selected nodes

Profile tab: measured per-node timings from Nuke's performance timers, top 10, Viewer path only,
baseline compare and disable-and-compare; measurements are shown next to the scan's findings.

Severities: Error, Warning, Performance, Note. Findings you accept can be ignored for this
script (stored in the script). Fixes are explicit, undoable and confirmed.

Install: put the SleepyDoctor folder in ~/.nuke and add to ~/.nuke/init.py:
    nuke.pluginAddPath('./SleepyDoctor')
"""
import json
import os
import re
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

__version__ = "2.0"
TOOL = "Sleepy Doctor"
PANEL_ID = "uk.co.pg.ScriptDoctor"
PREFS_FILE = os.path.join(os.path.expanduser("~"), ".nuke", "sleepy_script_doctor.json")
IGNORE_KNOB = "sleepy_doctor_ignored"
ICON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sleepy_icon.png")

ERROR, WARNING, PERF, NOTE = "Error", "Warning", "Performance", "Note"
SEV_ORDER = {ERROR: 0, WARNING: 1, PERF: 2, NOTE: 3}
SEV_COLORS = {ERROR: ("#5a2525", "#ffd8d8", "#e06060"), WARNING: ("#5a4b20", "#fff0a8", "#e0b040"),
              PERF: ("#55401f", "#ffd59a", "#e08a3a"), NOTE: ("#2b3f4f", "#cfe6f5", "#8fb4cc")}

DOCS = {
    "general": "https://learn.foundry.com/nuke/content/",
    "read": "https://learn.foundry.com/nuke/content/reference_guide/image_nodes/read.html",
    "write": "https://learn.foundry.com/nuke/content/reference_guide/image_nodes/write.html",
    "transform": "https://learn.foundry.com/nuke/content/reference_guide/transform_nodes/transform.html",
    "crop": "https://learn.foundry.com/nuke/content/reference_guide/transform_nodes/crop.html",
    "merge": "https://learn.foundry.com/nuke/content/reference_guide/merge_nodes/merge2.html",
    "reformat": "https://learn.foundry.com/nuke/content/reference_guide/transform_nodes/reformat.html",
    "color": "https://learn.foundry.com/nuke/content/comp_environment/configuring_nuke/using_ocio.html",
    "premult": "https://learn.foundry.com/nuke/content/reference_guide/merge_nodes/premult.html",
    "channels": "https://learn.foundry.com/nuke/content/comp_environment/channels/understanding_channels.html",
    "performance": "https://learn.foundry.com/nuke/content/comp_environment/configuring_nuke/optimizing_scripts.html",
    "expressions": "https://learn.foundry.com/nuke/content/comp_environment/expressions/adding_math_functions.html",
    "roto": "https://learn.foundry.com/nuke/content/reference_guide/draw_nodes/rotopaint.html",
}

DEFAULT_SETTINGS = {
    "bbox_warning_ratio": 3.0,
    "bbox_extreme_ratio": 8.0,
    "scale_warning": 2.5,
    "upscale_warning": 2.25,
    "large_filter": 150.0,
    "channel_warning": 24,
    "roto_size_warning": 250000,
    "check_on_save": False,
    "disabled_categories": [],
}

LOCAL_PATH = re.compile(r"^(?:[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]|/Users/|/home/)|"
                        r"[\\/](?:Desktop|Downloads|Temp|tmp)[\\/]", re.I)
VERSION = re.compile(r"[vV](\d{2,4})")
REF = re.compile(r"(?<![\w.$\]])([A-Za-z_]\w*)\.(?=[A-Za-z_])")
BUILTIN_REFS = {"parent", "root", "this", "input", "topnode", "nuke", "math", "os", "rgba", "rgb", "depth",
                "forward", "backward", "motion", "alpha", "red", "green", "blue", "frame", "x", "y"}
TERMINAL = {"Write", "Viewer", "BackdropNode", "StickyNote", "Output", "Input", "Root", "DeepWrite", "WriteGeo",
            "Group", "LiveGroup", "Camera", "Camera2", "Camera3", "Camera4", "Light", "Light2", "Light3", "Light4",
            "Axis", "Axis2", "Axis3", "Axis4", "Dot", "PostageStamp", "Precomp"}
EXPENSIVE = {"Denoise2": "Denoise", "OFlow2": "OFlow retime", "Kronos": "Kronos retime", "ZDefocus2": "ZDefocus",
             "Defocus": "Defocus", "Convolve2": "Convolve", "RayRender": "RayRender",
             "VectorGenerator": "VectorGenerator", "SmartVector": "SmartVector"}
FILTER_CLASSES = {"Blur", "Defocus", "ZDefocus2", "VectorBlur", "VectorBlur2", "Glow", "Glow2", "Dilate",
                  "Erode", "FilterErode", "EdgeBlur", "Bokeh"}
DISTORT_CLASSES = {"STMap", "IDistort", "LensDistortion", "LensDistortion2", "VectorDistort", "SplineWarp3", "GridWarp3"}
MOVE_CLASSES = {"Transform", "CornerPin2D", "Tracker4", "Card3D", "Reformat"} | DISTORT_CLASSES
TRANSFORM_CLASSES = {"Transform", "CornerPin2D", "Reformat", "Crop", "Tracker4"}
CONCAT_BREAKERS = {"Grade", "ColorCorrect", "Blur", "Defocus", "ZDefocus2", "Glow", "Merge2", "Merge", "RotoPaint",
                   "Roto", "HueCorrect", "Saturation", "Shuffle", "Shuffle2", "Copy"}


# ---------------------------------------------------------------- prefs
def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(PREFS_FILE) as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            s.update(data)
    except (IOError, OSError, ValueError):
        pass
    return s


def save_settings(s):
    folder = os.path.dirname(PREFS_FILE)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(PREFS_FILE, "w") as fh:
        json.dump(s, fh, indent=1)


# ---------------------------------------------------------------- issues
class Issue(object):
    def __init__(self, sev, category, title, node=None, details="", why="", doc="general",
                 fix=None, fix_label=None, data=None):
        self.sev = sev
        self.category = category
        self.title = title
        self.node = node.fullName() if hasattr(node, "fullName") else (node or "")
        self.details = details
        self.why = why
        self.doc = doc
        self.fix = fix
        self.fix_label = fix_label
        self.data = data or {}

    @property
    def signature(self):
        return "%s|%s|%s" % (self.category, self.node, self.title)

    def to_text(self):
        return "%-11s %-16s %-28s %s%s" % (self.sev, self.category, self.node or "(script)", self.title,
                                           (" (%s)" % self.details) if self.details else "")


def get_node(name):
    return nuke.toNode(name) if name else None


# ---------------------------------------------------------------- graph helpers
class Graph(object):
    """Input/output index of the script, built once per scan."""

    def __init__(self, nodes):
        self.nodes = dict((n.fullName(), n) for n in nodes)
        self.inputs, self.outputs = {}, {}
        for name, n in self.nodes.items():
            ins = []
            try:
                for i in range(n.inputs()):
                    src = n.input(i)
                    ins.append(src.fullName() if src is not None else None)
            except Exception:
                pass
            self.inputs[name] = ins
            for s in ins:
                if s:
                    self.outputs.setdefault(s, []).append(name)

    def upstream(self, names, limit=20000, expressions=True):
        seen, queue = set(), list(names)
        while queue and len(seen) < limit:
            cur = queue.pop()
            if cur in seen:
                continue
            seen.add(cur)
            queue.extend(s for s in self.inputs.get(cur, []) if s and s not in seen)
            if expressions:
                n = self.nodes.get(cur)
                try:
                    for d in n.dependencies(nuke.EXPRESSIONS | nuke.HIDDEN_INPUTS):
                        if d.fullName() not in seen:
                            queue.append(d.fullName())
                except Exception:
                    pass
        return seen

    def downstream(self, name, limit=20000):
        seen, queue = set(), list(self.outputs.get(name, []))
        while queue and len(seen) < limit:
            cur = queue.pop()
            if cur in seen:
                continue
            seen.add(cur)
            queue.extend(d for d in self.outputs.get(cur, []) if d not in seen)
        return seen


def _knob(node, name, default=None):
    k = node.knobs().get(name)
    if k is None:
        return default
    try:
        return k.value()
    except Exception:
        return default


def _frame_path(pattern, frame):
    s = re.sub(r"#+", lambda m: str(frame).zfill(len(m.group(0))), pattern)
    return re.sub(r"%0?(\d*)d", lambda m: str(frame).zfill(int(m.group(1) or 0)), s)


def _is_sequence(p):
    return bool(re.search(r"#+|%0?\d*d", p))


def _file_pattern(node):
    try:
        p = nuke.filename(node)
    except Exception:
        p = None
    return p or _knob(node, "file", "") or ""


def _evaluated(node):
    k = node.knobs().get("file")
    if k is None:
        return ""
    try:
        return k.evaluate() or ""
    except Exception:
        return k.value() or ""


def _norm(p):
    return os.path.normcase(os.path.normpath(p.replace("\\", "/"))) if p else ""


def _script_path():
    try:
        return nuke.root().name()
    except Exception:
        return ""


def _expressions(node):
    try:
        text = node.writeKnobs(nuke.WRITE_NON_DEFAULT_ONLY | nuke.TO_SCRIPT)
    except Exception:
        return []
    found = re.findall(r"\{\{(.*?)\}\}", text, re.S)
    found += re.findall(r"\[(?:value|knob)\s+([^\]\s]+)", text)
    return [re.sub(r"\[python[^\]]*\]", "", f) for f in found]


def _resolves(prefix, name):
    for cand in ((prefix + name) if prefix else None, name):
        if cand and nuke.toNode(cand) is not None:
            return cand
    return None


def _bbox(node):
    try:
        b = node.bbox()
        return float(b.w()), float(b.h())
    except Exception:
        return None


# ---------------------------------------------------------------- scanner
class Scanner(object):
    def __init__(self, settings=None):
        self.s = settings or load_settings()
        self.issues = []

    def add(self, *a, **kw):
        self.issues.append(Issue(*a, **kw))

    def scan(self, nodes=None, deep=False, whole=True, progress=None):
        """nodes: scope (None = whole script). whole: run script-wide checks like unused nodes."""
        self.issues = []
        all_nodes = list(nuke.allNodes(recurseGroups=True))
        self.graph = Graph(all_nodes)
        scope = list(nodes) if nodes is not None else all_nodes
        self.scope = scope
        self.whole = whole and nodes is None
        root = nuke.root()
        try:
            self.first, self.last = int(root["first_frame"].value()), int(root["last_frame"].value())
        except Exception:
            self.first = self.last = 1
        try:
            f = root.format()
            self.rw, self.rh = f.width(), f.height()
        except Exception:
            self.rw = self.rh = None
        self.area = float(max(1, (self.rw or 1) * (self.rh or 1)))
        checks = [("Project", self.check_project), ("Files", self.check_reads), ("Render", self.check_writes),
                  ("Expressions", self.check_expressions), ("Node errors", self.check_errors),
                  ("Connections", self.check_connections), ("Premult", self.check_premult),
                  ("Merge", self.check_merges), ("Color", self.check_color), ("Structure", self.check_structure),
                  ("Roto / Paint", self.check_roto)]
        if deep:
            checks += [("Performance", self.check_performance)]
        off = set(self.s.get("disabled_categories", []))
        for label, fn in checks:
            if label in off:
                continue
            if progress:
                try:
                    progress(label)
                except Exception:
                    pass
            try:
                fn()
            except Exception as exc:
                self.add(WARNING, "Scanner", "%s check failed" % label, None, str(exc),
                         "This check was skipped; the rest of the scan continued.")
        self.issues.sort(key=lambda i: (SEV_ORDER.get(i.sev, 9), i.category, i.node))
        return self.issues

    # ---- project
    def check_project(self):
        if not self.whole:
            return
        root = nuke.root()
        sp = _script_path()
        if not sp or sp == "Root":
            self.add(NOTE, "Project", "Script not saved", None, "",
                     "Unsaved scripts can't be version-checked and are lost if Nuke crashes.")
        if _knob(root, "proxy", False):
            self.add(WARNING, "Project", "Proxy mode is on", None, "",
                     "Renders and the viewer use proxy resolution while it's on.", fix="proxy_off", fix_label="Turn proxy off")
        if self.first > self.last:
            self.add(ERROR, "Project", "Frame range is backwards", None, "%d–%d" % (self.first, self.last),
                     "Nothing renders with a backwards range.")

    # ---- reads
    def check_reads(self):
        buckets = {}
        for n in self.scope:
            cls = n.Class()
            if cls not in ("Read", "DeepRead", "ReadGeo2", "ReadGeo") or "file" not in n.knobs():
                continue
            pat = _file_pattern(n)
            if not pat:
                self.add(ERROR, "Files", "Read has no file path", n, "", "A Read without a file can't produce an image.", "read")
                continue
            if LOCAL_PATH.search(pat):
                self.add(WARNING, "Files", "Local path", n, os.path.dirname(pat),
                         "Desktop, Downloads, temp and home folders usually aren't visible to the farm or other artists.", "read")
            first = int(_knob(n, "first", self.first) or self.first)
            last = int(_knob(n, "last", self.last) or self.last)
            if "[" in pat:
                ev = _evaluated(n)
                if ev and not os.path.exists(ev):
                    self.add(ERROR, "Files", "File not found (current frame)", n, ev,
                             "The source for the current frame is offline, moved or missing.", "read", fix="relink", fix_label="Relink…")
            elif _is_sequence(pat):
                frames = sorted({first, (first + last) // 2, last})
                missing = [f for f in frames if not os.path.exists(_frame_path(pat, f))]
                if missing:
                    self.add(ERROR, "Files", "Missing frames", n, "Frame%s %s of %s" % ("s" if len(missing) > 1 else "", ", ".join(map(str, missing)), os.path.basename(pat)),
                             "First, middle and last frames are checked. Missing frames render black or error.", "read", fix="relink", fix_label="Relink…")
            elif not os.path.exists(pat):
                self.add(ERROR, "Files", "File not found", n, pat, "The source is offline, moved or missing.", "read", fix="relink", fix_label="Relink…")
            if cls == "Read":
                if last < self.first or first > self.last:
                    self.add(WARNING, "Frame Range", "Read is outside the project range", n,
                             "Read %d–%d, project %d–%d" % (first, last, self.first, self.last),
                             "This source contributes nothing inside the project range.", "read")
                elif _is_sequence(pat) and (first > self.first or last < self.last):
                    self.add(WARNING, "Frame Range", "Read doesn't cover the whole project range", n,
                             "Read %d–%d, project %d–%d" % (first, last, self.first, self.last),
                             "Outside its range a Read holds a frame or goes black, depending on its before/after settings.", "read")
                try:
                    f = n.format()
                    if self.rw and (f.width(), f.height()) != (self.rw, self.rh):
                        self.add(NOTE, "Format", "Different format from project", n,
                                 "%d×%d vs project %d×%d" % (f.width(), f.height(), self.rw, self.rh),
                                 "Often intended (plates, elements), but worth knowing before a Merge or Write.", "reformat")
                except Exception:
                    pass
                if "colorspace" in n.knobs():
                    raw = str(_knob(n, "file", ""))
                    cs = str(_knob(n, "colorspace", ""))
                    buckets.setdefault((os.path.dirname(raw).lower(), os.path.splitext(raw)[1].lower()), {}).setdefault(cs, []).append(n)
        # colourspace outliers among Reads from the same folder and file type
        for key, profiles in buckets.items():
            total = sum(len(v) for v in profiles.values())
            if total < 3 or len(profiles) < 2:
                continue
            major, mnodes = max(profiles.items(), key=lambda kv: len(kv[1]))
            for cs, outl in profiles.items():
                if cs == major or len(outl) >= len(mnodes):
                    continue
                for n in outl:
                    self.add(WARNING, "Color", "Colourspace differs from related Reads", n,
                             "Uses %s; %d Read(s) from the same folder and type use %s." % (cs, len(mnodes), major),
                             "Reads from one folder and format usually share an interpretation. Check against the show's colour pipeline before changing.",
                             "color", fix="set_colorspace", fix_label="Use %s" % major, data={"colorspace": major})

    # ---- writes
    def check_writes(self):
        read_paths = {}
        for n in self.graph.nodes.values():
            if n.Class() == "Read":
                read_paths[_norm(_file_pattern(n))] = n.fullName()
        sp = _script_path()
        m = VERSION.findall(os.path.basename(sp or ""))
        script_ver = m[-1] if m else None
        outputs = {}
        for n in self.graph.nodes.values():
            if n.Class() in ("Write", "DeepWrite") and not _knob(n, "disable", False):
                outputs.setdefault(_norm(_file_pattern(n)), []).append(n.fullName())
        disabled_feeds = {}
        for n in self.scope:
            if n.Class() not in ("Write", "DeepWrite", "WriteGeo") or _knob(n, "disable", False):
                continue
            pat = _file_pattern(n)
            if not pat:
                self.add(ERROR, "Render", "Write has no output path", n, "", "It can't render.", "write")
                continue
            key = _norm(pat)
            others = [o for o in outputs.get(key, []) if o != n.fullName()]
            if others:
                self.add(ERROR, "Render", "Same output as another Write", n, "Also written by %s" % ", ".join(others),
                         "One render overwrites the other.", "write")
            if key in read_paths:
                self.add(ERROR, "Render", "Write would overwrite a Read", n, "Read: %s" % read_paths[key],
                         "Rendering would replace source media that the script reads.", "write")
            resolved = _evaluated(n) or pat
            folder = os.path.dirname(resolved)
            if folder and "[" not in folder and not os.path.isdir(folder):
                self.add(WARNING, "Render", "Output folder doesn't exist", n, folder,
                         "Some renderers and farms fail instead of creating it.", "write", fix="mkdir", fix_label="Create folder", data={"folder": folder})
            if LOCAL_PATH.search(resolved):
                self.add(WARNING, "Render", "Renders to a local folder", n, folder,
                         "The farm and other machines usually can't write there.", "write")
            wv = VERSION.findall(os.path.basename(resolved)) or VERSION.findall(resolved)
            if script_ver and wv and wv[-1] != script_ver and "[" not in pat:
                self.add(WARNING, "Render", "Write version differs from script", n, "Write v%s, script v%s" % (wv[-1], script_ver),
                         "Easy to overwrite an older version or deliver the wrong one.", "write", fix="match_version", fix_label="Use v%s" % script_ver)
            try:
                if _knob(n, "use_limit", False):
                    wf, wl = int(_knob(n, "first", 0)), int(_knob(n, "last", 0))
                    if (wf, wl) != (self.first, self.last):
                        self.add(NOTE, "Frame Range", "Write uses its own frame range", n,
                                 "Write %d–%d, project %d–%d" % (wf, wl, self.first, self.last),
                                 "Often intended, but check it before final delivery.", "write")
            except Exception:
                pass
            for up in self.graph.upstream([n.fullName()], expressions=False):
                un = self.graph.nodes.get(up)
                if un is not None and un is not n and _knob(un, "disable", False) and un.Class() != "Viewer":
                    disabled_feeds.setdefault(up, []).append(n.name())
        for up, ws in disabled_feeds.items():
            self.add(WARNING, "Render", "Disabled node feeds a Write", up, "Feeds %s" % ", ".join(sorted(set(ws))),
                     "Disabled nodes pass their input through; easy to forget before a render.", "general", fix="enable", fix_label="Enable")

    # ---- expressions
    def check_expressions(self):
        self.referenced = set()
        for n in self.graph.nodes.values():
            own = set(n.knobs().keys())
            full = n.fullName()
            prefix = full.rsplit(".", 1)[0] + "." if "." in full else ""
            in_scope = n in self.scope
            for ex in _expressions(n):
                for ref in set(REF.findall(ex)):
                    if ref in own or ref in BUILTIN_REFS or re.match(r"input\d+$", ref):
                        continue
                    hit = _resolves(prefix, ref)
                    if hit:
                        self.referenced.add(hit)
                    elif in_scope:
                        self.add(ERROR, "Expressions", "Expression points at a missing node", n,
                                 "Refers to '%s'" % ref,
                                 "The node was deleted or renamed. The knob falls back to 0 or errors.", "expressions")

    def check_errors(self):
        for n in self.scope:
            try:
                if n.Class() not in ("Read",) and n.hasError():
                    self.add(ERROR, "Node error", "Node is in an error state", n, "",
                             "It shows red in the Node Graph; downstream renders fail or are wrong.", "general")
            except Exception:
                pass

    # ---- connections
    def check_connections(self):
        for n in self.scope:
            cls = n.Class()
            if cls in ("Merge2", "Merge", "Keymix"):
                need, labels = [0, 1], {0: "B", 1: "A"}
            elif cls in ("Grade", "ColorCorrect", "Blur", "Defocus", "Transform", "Crop", "Premult", "Unpremult",
                         "Reformat", "Shuffle", "Shuffle2", "Write"):
                need, labels = [0], {0: "input"}
            else:
                continue
            for i in need:
                try:
                    if n.input(i) is None:
                        self.add(WARNING, "Connections", "Input %s not connected" % labels[i], n, "",
                                 "An empty main input gives an incomplete or empty branch. Not reconnected automatically: the intended source isn't known.",
                                 "merge" if cls.startswith("Merge") else "general")
                except Exception:
                    pass

    # ---- premult
    def check_premult(self):
        for n in self.scope:
            cls = n.Class()
            if cls not in ("Premult", "Unpremult") or _knob(n, "disable", False):
                continue
            up = n.input(0) if n.inputs() else None
            if up is not None and up.Class() == cls and not _knob(up, "disable", False):
                self.add(WARNING, "Premult", "Double %s" % cls.lower(), n, "Directly after %s" % up.name(),
                         "Premultiplying twice darkens edges; unpremultiplying twice brightens them.", "premult",
                         fix="disable", fix_label="Disable this %s" % cls)
            if cls == "Unpremult":
                found, frontier, seen = False, [n.fullName()], set()
                for _ in range(12):
                    nxt = []
                    for name in frontier:
                        for d in self.graph.outputs.get(name, []):
                            if d in seen:
                                continue
                            seen.add(d)
                            dn = self.graph.nodes.get(d)
                            if dn is not None and dn.Class() == "Premult":
                                found = True
                            nxt.append(d)
                    frontier = nxt
                    if found or not frontier:
                        break
                if not found and seen:
                    self.add(WARNING, "Premult", "Unpremult without a Premult after it", n, "No Premult within 12 nodes downstream.",
                             "Colour work after an Unpremult is normally followed by a Premult before merging.", "premult")

    # ---- merges
    def check_merges(self):
        for n in self.scope:
            if n.Class() not in ("Merge", "Merge2"):
                continue
            mix = _knob(n, "mix", 1.0)
            try:
                if mix is not None and abs(float(mix)) < 1e-8:
                    self.add(WARNING, "Merge", "Merge mix is 0", n, "Operation: %s" % _knob(n, "operation", "?"),
                             "With mix at 0 the Merge does nothing.", "merge")
            except Exception:
                pass

    # ---- colour
    def check_color(self):
        for n in self.scope:
            if n.Class() == "Read" and "colorspace" in n.knobs():
                cs = str(_knob(n, "colorspace", ""))
                if not cs or cs.lower() in ("unknown", "none"):
                    self.add(WARNING, "Color", "Read colourspace unknown", n, "Colourspace: %s" % (cs or "empty"),
                             "Check the source interpretation against the show's colour pipeline.", "color")

    # ---- structure
    def check_structure(self):
        for n in self.scope:
            if _knob(n, "hide_input", False):
                self.add(NOTE, "Structure", "Hidden input line", n, "",
                         "The connection exists but isn't drawn, which is easy to miss when reading the graph.",
                         fix="show_input", fix_label="Show input line")
        if not self.whole:
            return
        referenced = getattr(self, "referenced", set())
        for n in nuke.allNodes():
            cls = n.Class()
            if cls in TERMINAL or cls.startswith("Write"):
                continue
            name = n.fullName()
            if name in self.graph.outputs or name in referenced:
                continue
            self.add(NOTE, "Structure", "Not used downstream", n, "",
                     "Nothing reads from this node. It may be a leftover, or kept on purpose.")

    # ---- roto
    def check_roto(self):
        limit = self.s.get("roto_size_warning", 250000)
        for n in self.scope:
            if n.Class() not in ("Roto", "RotoPaint") or "curves" not in n.knobs():
                continue
            try:
                size = len(n["curves"].toScript())
            except Exception:
                continue
            if size > limit:
                self.add(PERF, "Roto / Paint", "Very large Roto/RotoPaint", n, "%s characters of shape data" % format(size, ","),
                         "Large RotoPaint nodes get slow to edit and evaluate. Consider splitting the work.", "roto")

    # ---- performance (full scan)
    def check_performance(self):
        s = self.s
        warn, extreme = float(s["bbox_warning_ratio"]), float(s["bbox_extreme_ratio"])
        ratios = {}
        for n in self.scope:
            bb = _bbox(n)
            if bb is not None:
                ratios[n.fullName()] = (bb[0] * bb[1] / self.area, bb)
        # oversized bboxes, grouped back to the node where the oversize starts
        big = dict((k, v) for k, v in ratios.items() if v[0] >= warn)
        groups = {}
        for name in big:
            origin, cur, guard = name, name, 0
            while guard < 500:
                guard += 1
                ups = [u for u in self.graph.inputs.get(cur, []) if u and u in big]
                if not ups:
                    break
                cur = max(ups, key=lambda u: big[u][0])
                origin = cur
            groups.setdefault(origin, []).append(name)
        for origin, members in groups.items():
            ratio, (bw, bh) = big[origin]
            down = len(self.graph.downstream(origin))
            sev = ERROR if ratio >= extreme else PERF
            self.add(sev, "Bounding Box", "Oversized bounding box starts here", origin,
                     "%d×%d, %.1f× the project area; %d node(s) inherit it, %d downstream" % (bw, bh, ratio, len(members) - 1, down),
                     "Every node below works on all those extra pixels. A Crop after this point (once overscan isn't needed) can speed up the whole branch.",
                     "crop", fix="crop", fix_label="Add Crop candidate",
                     data={"ratio": ratio, "downstream": down, "affected": sorted(members)})
        for n in self.scope:
            cls = n.Class()
            name = n.fullName()
            if cls == "Transform":
                try:
                    sc = n["scale"].value()
                    vals = sc if isinstance(sc, (list, tuple)) else [sc]
                    mx = max(abs(float(v)) for v in vals)
                    if mx >= float(s["scale_warning"]):
                        self.add(PERF, "Scaling", "Large Transform scale", n, "scale %s; %d downstream" % (sc, len(self.graph.downstream(name))),
                                 "Big upscales grow the processing area, especially with filters or a large bbox.", "transform")
                except Exception:
                    pass
            if cls == "Reformat":
                try:
                    src = n.input(0)
                    if src is not None:
                        r = float(n.width() * n.height()) / max(1, src.width() * src.height())
                        if r >= float(s["upscale_warning"]):
                            self.add(PERF, "Resolution", "Large upscale", n,
                                     "%d×%d → %d×%d (%.1f× pixels)" % (src.width(), src.height(), n.width(), n.height(), r),
                                     "Everything downstream processes the bigger image. Upscale after expensive filters if you can.", "reformat")
                except Exception:
                    pass
            if cls in FILTER_CLASSES:
                for kn in ("size", "defocus", "blur", "amount"):
                    if kn in n.knobs():
                        try:
                            v = n[kn].value()
                            vals = v if isinstance(v, (list, tuple)) else [v]
                            if max(abs(float(x)) for x in vals) >= float(s["large_filter"]):
                                self.add(PERF, "Heavy Nodes", "Large filter size", n, "%s: %s" % (kn, v),
                                         "Large kernels are slow, more so on a large bounding box.", "performance")
                                break
                        except Exception:
                            pass
            if cls in EXPENSIVE and not _knob(n, "disable", False):
                self.add(PERF, "Heavy Nodes", "%s is slow to render" % EXPENSIVE[cls], n, "",
                         "Consider a precomp or DiskCache after it so the rest of the comp stays interactive.", "performance")
            if "channels" in n.knobs() and str(_knob(n, "channels", "")).lower() == "all":
                try:
                    count = len(n.channels())
                except Exception:
                    count = 0
                if count >= int(s["channel_warning"]):
                    self.add(PERF, "Channels", "Processes all %d channels" % count, n, "channels = all",
                             "On AOV-heavy streams this filters every layer. Limit it to rgba if the layers don't need it.", "channels")


# ---------------------------------------------------------------- ignore list (stored in the script)
def ignored():
    k = nuke.root().knobs().get(IGNORE_KNOB)
    if k is None:
        return set()
    try:
        return set(json.loads(k.value() or "[]"))
    except ValueError:
        return set()


def set_ignored(sigs):
    root = nuke.root()
    k = root.knobs().get(IGNORE_KNOB)
    if k is None:
        k = nuke.String_Knob(IGNORE_KNOB, "Script Doctor ignored")
        root.addKnob(k)
        try:
            k.setFlag(nuke.INVISIBLE)
        except Exception:
            pass
    k.setValue(json.dumps(sorted(sigs)))


# ---------------------------------------------------------------- fixes
class _Undo(object):
    def __init__(self, name):
        self.name, self.u = name, None

    def __enter__(self):
        try:
            self.u = nuke.Undo()
            self.u.begin(self.name)
        except Exception:
            self.u = None

    def __exit__(self, *a):
        if self.u is not None:
            try:
                self.u.end()
            except Exception:
                pass
        return False


def relink(issue, folder, max_files=60000):
    n = get_node(issue.node)
    if n is None:
        return False
    pat = _file_pattern(n)
    base = os.path.basename(pat)
    probe = _frame_path(base, int(_knob(n, "first", 1) or 1)) if _is_sequence(base) else base
    seen = 0
    for dirpath, dirnames, filenames in os.walk(folder):
        if probe in filenames:
            with _Undo("Script Doctor: relink"):
                n["file"].setValue(os.path.join(dirpath, base).replace("\\", "/"))
            return True
        seen += len(filenames)
        if seen > max_files:
            break
    return False


def apply_fix(issue):
    """Apply a fix that needs no further input. Returns a short message."""
    fix = issue.fix
    with _Undo("Script Doctor: %s" % (issue.fix_label or fix)):
        if fix == "proxy_off":
            nuke.root()["proxy"].setValue(False)
            return "Proxy turned off"
        n = get_node(issue.node)
        if fix == "mkdir":
            folder = issue.data.get("folder")
            if folder and not os.path.isdir(folder):
                os.makedirs(folder)
            return "Created %s" % folder
        if n is None:
            return "The node no longer exists"
        if fix == "enable":
            n["disable"].setValue(False)
            return "Enabled %s" % n.name()
        if fix == "disable":
            n["disable"].setValue(True)
            return "Disabled %s" % n.name()
        if fix == "show_input":
            n["hide_input"].setValue(False)
            return "Input line shown"
        if fix == "set_colorspace":
            n["colorspace"].setValue(issue.data["colorspace"])
            return "Colourspace set to %s" % issue.data["colorspace"]
        if fix == "match_version":
            m = VERSION.findall(os.path.basename(_script_path()))
            if not m:
                return "The script name has no version"
            ver = m[-1]
            old = n["file"].value()
            n["file"].setValue(re.sub(r"([vV])\d{2,4}", lambda mm: mm.group(1) + ver.zfill(len(mm.group(0)) - 1), old))
            return "Write set to v%s" % ver
        if fix == "crop":
            crop = nuke.nodes.Crop()
            crop.setInput(0, n)
            crop.setXYpos(n.xpos() + 110, n.ypos() + 60)
            try:
                f = nuke.root().format()
                crop["box"].setValue([0, 0, f.width(), f.height()])
                crop["reformat"].setValue(False)
            except Exception:
                pass
            try:
                crop.setName("ScriptDoctor_Crop", uncollide=True)
            except Exception:
                pass
            for s in nuke.selectedNodes():
                s.setSelected(False)
            crop.setSelected(True)
            return "Crop created beside %s (not wired in: insert it where overscan is no longer needed)" % n.name()
    return "No automatic fix"


def select_node(name, zoom=True, panel=False):
    n = get_node(name)
    if n is None:
        return False
    for s in nuke.selectedNodes():
        s.setSelected(False)
    n.setSelected(True)
    if zoom and "." not in name:
        try:
            nuke.zoom(1.5, [n.xpos() + n.screenWidth() // 2, n.ypos() + n.screenHeight() // 2])
        except Exception:
            pass
    if panel:
        n.showControlPanel()
    return True


# ---------------------------------------------------------------- final QC + reports
def final_qc():
    """Delivery checklist: returns (blockers, warnings, passed) as lists of (text, node)."""
    blockers, warnings, passed = [], [], []
    nodes = nuke.allNodes(recurseGroups=True)
    writes = [n for n in nodes if n.Class() in ("Write", "DeepWrite") and not _knob(n, "disable", False)]
    if writes:
        passed.append(("%d active Write node(s)" % len(writes), ""))
    else:
        blockers.append(("No active Write nodes", ""))
    issues = Scanner().scan(deep=False)
    ig = ignored()
    for i in issues:
        if i.signature in ig:
            continue
        if i.sev == ERROR:
            blockers.append(("%s: %s" % (i.title, i.details) if i.details else i.title, i.node))
        elif i.sev == WARNING and i.category in ("Render", "Files", "Color", "Frame Range", "Connections", "Project", "Premult"):
            warnings.append(("%s: %s" % (i.title, i.details) if i.details else i.title, i.node))
    if not _knob(nuke.root(), "proxy", False):
        passed.append(("Proxy mode is off", ""))
    if not any(i.category == "Files" and i.sev == ERROR for i in issues):
        passed.append(("All Read media found (first, middle, last frames)", ""))
    if not any(i.category == "Expressions" for i in issues):
        passed.append(("No broken expressions", ""))
    if not any("local" in i.title.lower() for i in issues):
        passed.append(("No local Desktop/Downloads/temp paths", ""))
    return blockers, warnings, passed


def report_text(issues, scope=""):
    lines = ["%s %s" % (TOOL, __version__), "Script: %s" % (_script_path() or "untitled"),
             "Scan: %s  ·  %s" % (scope or "-", time.strftime("%Y-%m-%d %H:%M")), ""]
    for sev in (ERROR, WARNING, PERF, NOTE):
        group = [i for i in issues if i.sev == sev]
        if group:
            lines.append("%s (%d)" % (sev.upper(), len(group)))
            lines += ["  " + i.to_text() for i in group]
            lines.append("")
    return "\n".join(lines)


def report_html(issues, scope=""):
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    rows = []
    for i in issues:
        bg, fg, accent = SEV_COLORS[i.sev]
        rows.append("<tr><td style='color:%s;font-weight:600'>%s</td><td>%s</td><td><code>%s</code></td><td><b>%s</b><br><span style='color:#888'>%s</span></td></tr>"
                    % (accent, i.sev, esc(i.category), esc(i.node or "(script)"), esc(i.title), esc(i.details)))
    return ("<html><head><meta charset='utf-8'><title>Script Doctor report</title><style>body{font:13px sans-serif;background:#1e1f22;color:#ddd;margin:24px}"
            "table{border-collapse:collapse;width:100%%}td{border-bottom:1px solid #333;padding:6px 8px;vertical-align:top}code{color:#f0a043}</style></head>"
            "<body><h2>%s</h2><p>%s<br>%s · %s</p><table>%s</table></body></html>"
            % (TOOL, esc(_script_path() or "untitled"), esc(scope), time.strftime("%Y-%m-%d %H:%M"), "".join(rows)))


# ---------------------------------------------------------------- inspectors
# Each returns a list of sections: (title, [(label, node_full_name_or_empty, detail), ...])
def _ratio(n, area):
    bb = _bbox(n)
    return (bb[0] * bb[1] / area, bb) if bb else (None, None)


def _area():
    try:
        f = nuke.root().format()
        return float(max(1, f.width() * f.height()))
    except Exception:
        return 1.0


def inspect_node(n):
    g = Graph(nuke.allNodes(recurseGroups=True))
    name = n.fullName()
    rows = [("Class", "", n.Class())]
    try:
        rows.append(("Resolution", "", "%d × %d" % (n.width(), n.height())))
    except Exception:
        pass
    r, bb = _ratio(n, _area())
    if r is not None:
        rows.append(("Bounding box", "", "%d × %d  (%.2f× project area)" % (bb[0], bb[1], r)))
    try:
        ch = list(n.channels())
        rows.append(("Channels", "", "%d in %d layers" % (len(ch), len(set(c.split(".")[0] for c in ch)))))
    except Exception:
        pass
    rows.append(("Upstream nodes", "", str(len(g.upstream([name])) - 1)))
    rows.append(("Downstream nodes", "", str(len(g.downstream(name)))))
    exprs = [k for k, kb in n.knobs().items() if _has_expression(kb)]
    rows.append(("Knobs with expressions", "", ", ".join(exprs) or "none"))
    ins = [(("input %d" % i), s or "", "") for i, s in enumerate(g.inputs.get(name, []))]
    outs = [("output", d, get_node(d).Class() if get_node(d) else "") for d in g.outputs.get(name, [])]
    return [(name, rows), ("Inputs", ins or [("none", "", "")]), ("Connected to", outs or [("nothing", "", "")])]


def _has_expression(k):
    try:
        return k.hasExpression()
    except Exception:
        return False


def where_used(n):
    g = Graph(nuke.allNodes(recurseGroups=True))
    name = n.fullName()
    direct = list(g.outputs.get(name, []))
    try:
        for d in n.dependent(nuke.EXPRESSIONS, forceEvaluate=False):
            if d.fullName() not in direct:
                direct.append(d.fullName() + " (expression)")
    except Exception:
        pass
    down = g.downstream(name)
    writes = [d for d in down if get_node(d) is not None and get_node(d).Class().startswith("Write")]
    return [("Directly used by", [(d, d.replace(" (expression)", ""), "") for d in direct] or [("nothing", "", "")]),
            ("Writes affected (%d of %d downstream nodes)" % (len(writes), len(down)), [(w, w, "") for w in sorted(writes)] or [("none", "", "")])]


def bbox_contributors(n):
    g = Graph(nuke.allNodes(recurseGroups=True))
    area = _area()
    rows = []
    for u in g.upstream([n.fullName()], expressions=False):
        un = get_node(u)
        r, bb = _ratio(un, area) if un is not None else (None, None)
        if r is not None:
            rows.append((r, u, bb, un.Class()))
    rows.sort(key=lambda x: -x[0])
    return [("Largest bounding boxes upstream of %s" % n.name(),
             [("%.2f×" % r, u, "%d × %d  [%s]" % (bb[0], bb[1], c)) for r, u, bb, c in rows[:40]] or [("no bbox data", "", "")])]


def crop_safety(n):
    g = Graph(nuke.allNodes(recurseGroups=True))
    down = [get_node(d) for d in g.downstream(n.fullName())]
    down = [d for d in down if d is not None]
    moving = [d for d in down if d.Class() in MOVE_CLASSES]
    severe = [d for d in down if d.Class() in DISTORT_CLASSES]
    level = "Not recommended" if severe else "Review carefully" if len(moving) > 2 else "Review" if moving else "Low risk"
    r, bb = _ratio(n, _area())
    rows = [("Risk", "", level), ("Downstream nodes", "", str(len(down)))]
    if r is not None:
        rows.append(("Bounding box here", "", "%d × %d (%.2f× project area)" % (bb[0], bb[1], r)))
    advice = {"Not recommended": "Distortion downstream can pull pixels from outside the frame back in. Cropping here would lose them.",
              "Review carefully": "Several nodes move the image later. Check none of them bring overscan back into frame.",
              "Review": "Something moves the image later; check it before cropping.",
              "Low risk": "Nothing downstream moves or distorts the image. A Crop here is a good candidate."}[level]
    rows.append(("Advice", "", advice))
    return [("Crop safety at %s" % n.name(), rows),
            ("Nodes that move or distort the image later", [(d.Class(), d.fullName(), "") for d in moving] or [("none", "", "")])]


def expression_map(selected=None):
    names = set(n.name() for n in selected) if selected else None
    rows = []
    for n in nuke.allNodes(recurseGroups=True):
        for kname, k in n.knobs().items():
            if not _has_expression(k):
                continue
            try:
                exprs = [c.expression() for c in (k.animations() or [])]
            except Exception:
                exprs = []
            for ex in exprs:
                if not ex or ex == "curve":
                    continue
                if names and n.name() not in names and not any(nm in ex for nm in names):
                    continue
                full = n.fullName()
                prefix = full.rsplit(".", 1)[0] + "." if "." in full else ""
                broken = [r for r in set(REF.findall(ex)) if r not in n.knobs() and r not in BUILTIN_REFS
                          and not re.match(r"input\d+$", r) and not _resolves(prefix, r)]
                rows.append(("%s.%s%s" % (n.name(), kname, "  ⚠ broken" if broken else ""), full, ex))
    return [("Expressions%s (%d)" % (" linked to the selection" if names else "", len(rows)), rows or [("none found", "", "")])]


def channel_flow(nodes):
    rows = []
    for n in nodes:
        try:
            ch = list(n.channels())
            layers = sorted(set(c.split(".")[0] for c in ch))
            rows.append(("%d ch / %d layers" % (len(ch), len(layers)), n.fullName(), ", ".join(layers[:30]) + (" …" if len(layers) > 30 else "")))
        except Exception as exc:
            rows.append(("unavailable", n.fullName(), str(exc)))
    return [("Channels per node", rows)]


def merge_explorer():
    merges = [n for n in nuke.allNodes(recurseGroups=True) if n.Class() in ("Merge", "Merge2")]
    ops = {}
    for n in merges:
        ops.setdefault(str(_knob(n, "operation", "?")), []).append(n)
    secs = [("Merge operations (%d merges)" % len(merges), [(op, "", "%d" % len(v)) for op, v in sorted(ops.items(), key=lambda kv: -len(kv[1]))])]
    for op, v in sorted(ops.items(), key=lambda kv: -len(kv[1])):
        secs.append((op, [(n.name(), n.fullName(), "mix %s" % _knob(n, "mix", 1)) for n in v]))
    return secs


def rw_dashboard():
    nodes = nuke.allNodes(recurseGroups=True)
    reads = [n for n in nodes if n.Class() == "Read"]
    writes = [n for n in nodes if n.Class() in ("Write", "DeepWrite")]
    rrows, wrows = [], []
    for n in reads:
        pat = _file_pattern(n)
        ok = (os.path.exists(_frame_path(pat, int(_knob(n, "first", 1) or 1))) if _is_sequence(pat) else os.path.exists(pat)) if pat else False
        rrows.append(("OK" if ok else "MISSING", n.fullName(), "%s  [%s]  %s–%s" % (pat, _knob(n, "colorspace", "?"), _knob(n, "first", "?"), _knob(n, "last", "?"))))
    for n in writes:
        res = _evaluated(n) or _file_pattern(n)
        folder_ok = os.path.isdir(os.path.dirname(res)) if res else False
        wrows.append(("disabled" if _knob(n, "disable", False) else ("ready" if folder_ok else "no folder"), n.fullName(), res))
    return [("Reads (%d)" % len(reads), rrows or [("none", "", "")]), ("Writes (%d)" % len(writes), wrows or [("none", "", "")])]


def concatenation(nodes=None):
    nodes = nodes or nuke.allNodes(recurseGroups=True)
    rows = []
    g = Graph(nuke.allNodes(recurseGroups=True))
    for n in nodes:
        try:
            if n.Class() not in CONCAT_BREAKERS or not n.input(0) or n.input(0).Class() not in TRANSFORM_CLASSES:
                continue
            down = [get_node(d) for d in g.outputs.get(n.fullName(), [])]
            nxt = [d for d in down if d is not None and d.Class() in TRANSFORM_CLASSES]
            if nxt:
                rows.append(("%s → %s → %s" % (n.input(0).name(), n.name(), nxt[0].name()), n.fullName(),
                             "%s between two transforms stops them concatenating (two filter hits instead of one)" % n.Class()))
        except Exception:
            pass
    return [("Transform chains broken by another node", rows or [("none found", "", "")])]


def cleanup():
    nodes = nuke.allNodes(recurseGroups=True)
    g = Graph(nodes)
    disabled = [n for n in nodes if _knob(n, "disable", False)]
    unplugged = [n for n in nodes if n.Class() not in ("Read", "Constant", "Viewer", "BackdropNode", "StickyNote", "Input", "CheckerBoard2", "ColorBars", "Noise", "Ramp", "Radial", "Rectangle", "Text2", "Roto", "RotoPaint")
                 and n.inputs() > 0 and all(n.input(i) is None for i in range(n.inputs()))]
    unused = [n for n in nuke.allNodes() if n.Class() not in TERMINAL and not n.Class().startswith("Write") and n.fullName() not in g.outputs]
    return [("Disabled (%d)" % len(disabled), [(n.Class(), n.fullName(), "") for n in disabled] or [("none", "", "")]),
            ("No inputs connected (%d)" % len(unplugged), [(n.Class(), n.fullName(), "") for n in unplugged] or [("none", "", "")]),
            ("Not used downstream (%d)" % len(unused), [(n.Class(), n.fullName(), "") for n in unused] or [("none", "", "")])]


def plugins_inspector():
    classes = {}
    for n in nuke.allNodes(recurseGroups=True):
        classes.setdefault(n.Class(), []).append(n)
    rows = []
    for c, ns in sorted(classes.items(), key=lambda kv: kv[0].lower()):
        flag = ""
        try:
            if any(x.hasError() for x in ns) and c not in ("Read",):
                flag = "  ⚠ error"
        except Exception:
            pass
        rows.append(("%s%s" % (c, flag), ns[0].fullName(), "%d" % len(ns)))
    return [("Node classes in the script (%d)" % len(classes), rows)]


def font_inspector():
    rows = []
    for n in nuke.allNodes(recurseGroups=True):
        if n.Class() not in ("Text", "Text2"):
            continue
        font = "?"
        for k in ("font", "font_family", "font_path"):
            v = _knob(n, k)
            if v:
                font = str(v)
                break
        rows.append((n.name(), n.fullName(), font))
    return [("Text nodes and fonts", rows or [("none", "", "")])]


def frame_bbox(n):
    root = nuke.root()
    first, last = int(root["first_frame"].value()), int(root["last_frame"].value())
    frames = sorted(set([first, (first + last) // 4, (first + last) // 2, 3 * (first + last) // 4, last, int(nuke.frame())]))
    frames = [f for f in frames if first <= f <= last] or [int(nuke.frame())]
    area, rows, old = _area(), [], nuke.frame()
    try:
        for f in frames:
            nuke.frame(f)
            r, bb = _ratio(n, area)
            rows.append(("frame %d" % f, "", "%d × %d (%.2f×)" % (bb[0], bb[1], r) if r is not None else "unavailable"))
    finally:
        nuke.frame(old)
    return [("Bounding box over time at %s" % n.name(), rows)]


def roto_sizes():
    rows = []
    for n in nuke.allNodes(recurseGroups=True):
        if n.Class() in ("Roto", "RotoPaint") and "curves" in n.knobs():
            try:
                rows.append((len(n["curves"].toScript()), n))
            except Exception:
                pass
    rows.sort(key=lambda x: -x[0])
    return [("Roto / RotoPaint by size", [(format(s, ",") + " chars", n.fullName(), n.Class()) for s, n in rows] or [("none", "", "")])]


# ---------------------------------------------------------------- shared session state (window + docked panel see the same scan)
_STATE = {"issues": [], "previous": None, "scope": "", "heat": {}, "time": ""}
_WIDGETS = []
CATEGORY_CHECKS = ["Project", "Files", "Render", "Expressions", "Node errors", "Connections", "Premult", "Merge",
                   "Color", "Structure", "Roto / Paint", "Performance"]

STYLE = """
QWidget#pgDoctor { background: #282828; color: #d6d6d6; }
QWidget#pgDoctor QLabel#title { font-size: 15px; font-weight: 600; color: #f0a043; letter-spacing: 1px; }
QWidget#pgDoctor QLabel#muted { color: #9a9a9a; }
QWidget#pgDoctor QLabel#detailTitle { font-size: 13px; font-weight: 600; color: #eeeeee; }
QWidget#pgDoctor QPushButton, QWidget#pgDoctor QToolButton { background: #3a3a3a; border: 1px solid #505050; padding: 5px 10px; border-radius: 2px; color: #dddddd; }
QWidget#pgDoctor QPushButton:hover, QWidget#pgDoctor QToolButton:hover { background: #454545; }
QWidget#pgDoctor QPushButton:disabled { color: #6a6a6a; }
QWidget#pgDoctor QPushButton#primary { background: #5a4126; border: 1px solid #a8722f; font-weight: 600; color: #ffe2bd; }
QWidget#pgDoctor QLineEdit, QWidget#pgDoctor QComboBox, QWidget#pgDoctor QDoubleSpinBox, QWidget#pgDoctor QSpinBox { background: #1f1f1f; border: 1px solid #454545; padding: 4px; color: #dddddd; }
QWidget#pgDoctor QTreeWidget, QWidget#pgDoctor QTableWidget, QWidget#pgDoctor QTextBrowser { background: #1f1f1f; alternate-background-color: #242424; border: 1px solid #424242; color: #d6d6d6; }
QWidget#pgDoctor QHeaderView::section { background: #343434; color: #d6d6d6; border: 0; border-right: 1px solid #454545; padding: 5px; }
QWidget#pgDoctor QTabWidget::pane { border: 1px solid #444444; }
QWidget#pgDoctor QTabBar::tab { background: #333333; border: 1px solid #444444; padding: 6px 14px; color: #cfcfcf; }
QWidget#pgDoctor QTabBar::tab:selected { background: #474747; color: #ffffff; }
"""


def _sev_button_style(sev):
    bg, fg, accent = SEV_COLORS[sev]
    return ("QPushButton { background: %s; color: %s; border: 1px solid %s; padding: 3px 9px; font-weight: 600; border-radius: 2px; }"
            "QPushButton:checked { border: 2px solid #ffffff; }" % (bg, fg, accent))


def _exec(obj, *args):
    run = getattr(obj, "exec_", None) or getattr(obj, "exec")
    return run(*args)


class ResultTree(QtWidgets.QTreeWidget):
    """Clickable results: click selects the node, double-click opens its properties."""

    def __init__(self, parent=None):
        super(ResultTree, self).__init__(parent)
        self.setColumnCount(3)
        self.setHeaderLabels(["", "Node", "Details"])
        self.setAlternatingRowColors(True)
        self.itemClicked.connect(lambda it, c: it.data(0, QtCore.Qt.UserRole) and select_node(it.data(0, QtCore.Qt.UserRole)))
        self.itemDoubleClicked.connect(lambda it, c: it.data(0, QtCore.Qt.UserRole) and select_node(it.data(0, QtCore.Qt.UserRole), panel=True))

    def set_sections(self, sections):
        self.clear()
        for title, rows in sections:
            top = QtWidgets.QTreeWidgetItem([title, "", ""])
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            top.setFirstColumnSpanned(True)
            self.addTopLevelItem(top)
            for label, node, detail in rows:
                it = QtWidgets.QTreeWidgetItem([label, node or "", detail or ""])
                it.setData(0, QtCore.Qt.UserRole, node or None)
                it.setToolTip(2, detail or "")
                if "⚠" in label or label in ("MISSING", "no folder"):
                    it.setForeground(0, QtGui.QBrush(QtGui.QColor("#e0b040")))
                top.addChild(it)
            top.setExpanded(True)
        for c in range(2):
            self.resizeColumnToContents(c)


class DoctorWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(DoctorWidget, self).__init__(parent)
        self.setObjectName("pgDoctor")
        self.setStyleSheet(STYLE)
        self.sev_filter = None
        self._build()
        _WIDGETS.append(self)
        self.refresh_all()

    # ---- layout
    def _build(self):
        main = QtWidgets.QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 6)
        main.setSpacing(6)

        head = QtWidgets.QHBoxLayout()
        t = QtWidgets.QLabel("SCRIPT DOCTOR")
        t.setObjectName("title")
        head.addWidget(t)
        self.script_label = QtWidgets.QLabel()
        self.script_label.setObjectName("muted")
        head.addWidget(self.script_label, 1)
        self.mode_btn = QtWidgets.QPushButton("Dock")
        self.mode_btn.clicked.connect(self._switch_mode)
        head.addWidget(self.mode_btn)
        gear = QtWidgets.QPushButton("Settings…")
        gear.clicked.connect(self._settings)
        head.addWidget(gear)
        main.addLayout(head)

        bar = QtWidgets.QHBoxLayout()
        self.count_btns = {}
        for sev in (ERROR, WARNING, PERF, NOTE):
            b = QtWidgets.QPushButton("%s 0" % sev)
            b.setCheckable(True)
            b.setStyleSheet(_sev_button_style(sev))
            b.setToolTip("Show only %s findings" % sev.lower())
            b.clicked.connect(lambda checked, s=sev: self._sev_clicked(s, checked))
            self.count_btns[sev] = b
            bar.addWidget(b)
        bar.addStretch(1)
        q = QtWidgets.QPushButton("Quick scan")
        q.setObjectName("primary")
        q.setToolTip("Whole script: files, renders, expressions, connections, colour, structure")
        q.clicked.connect(lambda: self.run_scan("Quick"))
        bar.addWidget(q)
        f = QtWidgets.QPushButton("Full scan")
        f.setToolTip("Quick scan plus performance: bounding boxes, scaling, heavy nodes, channels")
        f.clicked.connect(lambda: self.run_scan("Full"))
        bar.addWidget(f)
        sc = QtWidgets.QToolButton()
        sc.setText("Scan part ▾")
        sc.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        m = QtWidgets.QMenu(sc)
        m.addAction("Selected nodes", lambda: self.run_scan("Selection"))
        m.addAction("Everything upstream of the selection", lambda: self.run_scan("Upstream"))
        m.addAction("Between two selected nodes", lambda: self.run_scan("Between"))
        sc.setMenu(m)
        bar.addWidget(sc)
        main.addLayout(bar)

        flt = QtWidgets.QHBoxLayout()
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search nodes, findings, categories…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_issues)
        flt.addWidget(self.search, 1)
        self.category = QtWidgets.QComboBox()
        self.category.addItem("All categories")
        self.category.currentIndexChanged.connect(self.refresh_issues)
        flt.addWidget(self.category)
        self.show_ignored = QtWidgets.QCheckBox("Show ignored")
        self.show_ignored.toggled.connect(self.refresh_issues)
        flt.addWidget(self.show_ignored)
        main.addLayout(flt)

        self.tabs = QtWidgets.QTabWidget()
        main.addWidget(self.tabs, 1)
        self._build_overview()
        self._build_issues()
        self._build_performance()
        self._build_color()
        self._build_inspect()
        self.profile = ProfilePanel(lambda text: self.status.setText(text))
        self.tabs.addTab(self.profile, "Profile")

        self.status = QtWidgets.QLabel("Ready. Nothing is scanned until you press a scan button.")
        self.status.setObjectName("muted")
        main.addWidget(self.status)

    def _build_overview(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        self.overview = QtWidgets.QTextBrowser()
        self.overview.setOpenLinks(False)
        self.overview.anchorClicked.connect(self._overview_link)
        self.overview.setMaximumHeight(210)
        lay.addWidget(self.overview)
        row = QtWidgets.QHBoxLayout()
        for label, fn in (("Final QC", self.run_final_qc), ("Compare with previous scan", self.compare),
                          ("Copy report", self.copy_report), ("Save report…", self.save_report)):
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        self.chk_save = QtWidgets.QCheckBox("Warn about errors when saving")
        self.chk_save.setChecked(bool(load_settings().get("check_on_save")))
        self.chk_save.toggled.connect(set_check_on_save)
        row.addWidget(self.chk_save)
        lay.addLayout(row)
        self.overview_results = ResultTree()
        lay.addWidget(self.overview_results, 1)
        self.tabs.addTab(page, "Overview")

    def _build_issues(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        sp = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.table = QtWidgets.QTreeWidget()
        self.table.setHeaderLabels(["Severity", "Category", "Node", "Finding"])
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self.show_issue)
        self.table.itemClicked.connect(lambda it, c: self.current_issue() and select_node(self.current_issue().node))
        self.table.itemDoubleClicked.connect(lambda it, c: self.current_issue() and select_node(self.current_issue().node, panel=True))
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._issue_menu)
        sp.addWidget(self.table)
        side = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(side)
        sl.setContentsMargins(8, 0, 0, 0)
        self.d_title = QtWidgets.QLabel("Select a finding")
        self.d_title.setObjectName("detailTitle")
        self.d_title.setWordWrap(True)
        sl.addWidget(self.d_title)
        self.d_text = QtWidgets.QTextBrowser()
        sl.addWidget(self.d_text, 1)
        g = QtWidgets.QGridLayout()
        self.b_select = QtWidgets.QPushButton("Select node")
        self.b_select.clicked.connect(lambda: self.current_issue() and select_node(self.current_issue().node, panel=True))
        self.b_fix = QtWidgets.QPushButton("Fix")
        self.b_fix.setObjectName("primary")
        self.b_fix.clicked.connect(self.fix_selected)
        self.b_fix_all = QtWidgets.QPushButton("Fix all like this")
        self.b_fix_all.clicked.connect(self.fix_all_like)
        self.b_ignore = QtWidgets.QPushButton("Ignore for this script")
        self.b_ignore.clicked.connect(self.toggle_ignore)
        self.b_trace = QtWidgets.QPushButton("Inspect")
        self.b_trace.setToolTip("Bounding box sources, crop safety or where this node is used")
        self.b_trace.clicked.connect(self.trace)
        self.b_docs = QtWidgets.QPushButton("Foundry docs")
        self.b_docs.clicked.connect(lambda: self.current_issue() and QtGui.QDesktopServices.openUrl(QtCore.QUrl(DOCS.get(self.current_issue().doc, DOCS["general"]))))
        for i, w in enumerate((self.b_select, self.b_fix, self.b_fix_all, self.b_ignore, self.b_trace, self.b_docs)):
            g.addWidget(w, i // 2, i % 2)
        sl.addLayout(g)
        sp.addWidget(side)
        sp.setStretchFactor(0, 3)
        sp.setStretchFactor(1, 2)
        lay.addWidget(sp)
        self.tabs.addTab(page, "Findings")

    def _build_performance(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.addWidget(QtWidgets.QLabel("Performance findings, biggest impact first. Take a snapshot on the Profile tab to add measured times."))
        self.perf_tree = ResultTree()
        lay.addWidget(self.perf_tree, 1)
        row = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton("Select all in Node Graph")
        b.clicked.connect(self.select_perf_nodes)
        row.addWidget(b)
        self.b_heat = QtWidgets.QPushButton("Colour heat map")
        self.b_heat.setCheckable(True)
        self.b_heat.setToolTip("Temporarily colours slow nodes red/orange. Turn it off (or close the tool) to restore the colours.")
        self.b_heat.toggled.connect(self.heat_map)
        row.addWidget(self.b_heat)
        row.addStretch(1)
        lay.addLayout(row)
        self.tabs.addTab(page, "Performance")

    def _build_color(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        top = QtWidgets.QHBoxLayout()
        self.c_scope = QtWidgets.QComboBox()
        self.c_scope.addItems(["All Reads", "Selected Reads"])
        self.c_scope.currentIndexChanged.connect(self.refresh_color)
        self.c_filter = QtWidgets.QComboBox()
        self.c_filter.currentIndexChanged.connect(self._color_filter)
        top.addWidget(QtWidgets.QLabel("Reads"))
        top.addWidget(self.c_scope)
        top.addWidget(QtWidgets.QLabel("currently"))
        top.addWidget(self.c_filter, 1)
        rb = QtWidgets.QPushButton("Refresh")
        rb.clicked.connect(self.refresh_color)
        top.addWidget(rb)
        lay.addLayout(top)
        self.c_table = QtWidgets.QTableWidget(0, 4)
        self.c_table.setHorizontalHeaderLabels(["Use", "Read", "Colourspace", "File"])
        self.c_table.horizontalHeader().setStretchLastSection(True)
        self.c_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.c_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.c_table.verticalHeader().setVisible(False)
        self.c_table.cellDoubleClicked.connect(lambda r, c: select_node(self.c_table.item(r, 1).text(), panel=True))
        lay.addWidget(self.c_table, 1)
        row = QtWidgets.QHBoxLayout()
        self.c_target = QtWidgets.QComboBox()
        row.addWidget(QtWidgets.QLabel("Set ticked Reads to"))
        row.addWidget(self.c_target, 1)
        ab = QtWidgets.QPushButton("Apply")
        ab.setObjectName("primary")
        ab.clicked.connect(self.apply_color)
        row.addWidget(ab)
        lay.addLayout(row)
        self.tabs.addTab(page, "Colour")
        self._color_loaded = False
        self.tabs.currentChanged.connect(lambda i: self.tabs.tabText(i) == "Colour" and not self._color_loaded and self.refresh_color())

    def _build_inspect(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.addWidget(QtWidgets.QLabel("Select a node in the Node Graph, then pick a tool. Results are clickable."))
        g = QtWidgets.QGridLayout()
        tools = [("Node inspector", self._one(inspect_node)), ("Where is it used?", self._one(where_used)),
                 ("Bounding box sources", self._one(bbox_contributors)), ("Crop safety", self._one(crop_safety)),
                 ("Bounding box over time", self._one(frame_bbox)), ("Channel flow", self._many(channel_flow)),
                 ("Expression map", lambda: self._show_inspect(expression_map(nuke.selectedNodes() or None))),
                 ("Transform concatenation", lambda: self._show_inspect(concatenation(self._upstream_of_selection()))),
                 ("Merge explorer", lambda: self._show_inspect(merge_explorer())),
                 ("Read / Write dashboard", lambda: self._show_inspect(rw_dashboard())),
                 ("Cleanup helper", lambda: self._show_inspect(cleanup())),
                 ("Node classes / plugins", lambda: self._show_inspect(plugins_inspector())),
                 ("Roto sizes", lambda: self._show_inspect(roto_sizes())), ("Fonts", lambda: self._show_inspect(font_inspector()))]
        for i, (label, fn) in enumerate(tools):
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(fn)
            g.addWidget(b, i // 4, i % 4)
        lay.addLayout(g)
        self.inspect_tree = ResultTree()
        lay.addWidget(self.inspect_tree, 1)
        self.tabs.addTab(page, "Inspect")

    # ---- inspect helpers
    def _one(self, fn):
        def run():
            sel = nuke.selectedNodes()
            if len(sel) != 1:
                self.status.setText("Select exactly one node for this tool.")
                return
            self._show_inspect(fn(sel[0]))
        return run

    def _many(self, fn):
        def run():
            sel = nuke.selectedNodes()
            if not sel:
                self.status.setText("Select one or more nodes for this tool.")
                return
            self._show_inspect(fn(sel))
        return run

    def _upstream_of_selection(self):
        sel = nuke.selectedNodes()
        if not sel:
            return None
        g = Graph(nuke.allNodes(recurseGroups=True))
        names = g.upstream([n.fullName() for n in sel])
        return [g.nodes[n] for n in names if n in g.nodes]

    def _show_inspect(self, sections):
        self.inspect_tree.set_sections(sections)
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.inspect_tree.parentWidget()))

    # ---- scanning
    def run_scan(self, kind):
        sel = nuke.selectedNodes()
        nodes, deep, label = None, kind != "Quick", kind
        if kind == "Full":
            label = "Full"
        elif kind == "Selection":
            if not sel:
                self.status.setText("Select some nodes first.")
                return
            nodes = sel
            label = "Selection (%d nodes)" % len(sel)
        elif kind == "Upstream":
            if not sel:
                self.status.setText("Select a node (a Write or a Merge, say) first.")
                return
            nodes = self._upstream_of_selection()
            label = "Upstream of %s (%d nodes)" % (", ".join(n.name() for n in sel[:3]), len(nodes))
        elif kind == "Between":
            if len(sel) != 2:
                self.status.setText("Select exactly two nodes on the same branch.")
                return
            g = Graph(nuke.allNodes(recurseGroups=True))
            a, b = sel[0].fullName(), sel[1].fullName()
            up_a, up_b = g.upstream([a], expressions=False), g.upstream([b], expressions=False)
            if a in up_b:
                start, end = a, b
            elif b in up_a:
                start, end = b, a
            else:
                self.status.setText("Those two nodes aren't on the same branch.")
                return
            names = (g.upstream([end], expressions=False) & (g.downstream(start) | {start})) | {end}
            nodes = [g.nodes[n] for n in names if n in g.nodes]
            label = "Between %s and %s (%d nodes)" % (sel[0].name(), sel[1].name(), len(nodes))
        self.heat_off()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            prev = _STATE["issues"]
            issues = Scanner().scan(nodes, deep=deep, whole=nodes is None, progress=self._progress)
            _STATE.update(previous=[i.signature for i in prev] if prev else _STATE.get("previous"),
                          issues=issues, scope=label, time=time.strftime("%H:%M"))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        for w in list(_WIDGETS):
            try:
                w.refresh_all()
            except RuntimeError:
                _WIDGETS.remove(w)
        self.status.setText("%s scan: %d finding(s)." % (label, len(issues)))

    def _progress(self, label):
        self.status.setText("Checking %s…" % label)
        QtWidgets.QApplication.processEvents()

    # ---- refresh
    def visible_issues(self):
        ig = ignored()
        q = self.search.text().lower().split()
        cat = self.category.currentText()
        out = []
        for i in _STATE["issues"]:
            if i.signature in ig and not self.show_ignored.isChecked():
                continue
            if self.sev_filter and i.sev != self.sev_filter:
                continue
            if cat not in ("", "All categories") and i.category != cat:
                continue
            hay = " ".join([i.sev, i.category, i.node, i.title, i.details]).lower()
            if all(w in hay for w in q):
                out.append(i)
        return out

    def refresh_all(self):
        path = _script_path()
        self.script_label.setText("%s%s" % (os.path.basename(path) if path and path != "Root" else "untitled",
                                            ("   ·   %s scan at %s" % (_STATE["scope"], _STATE["time"])) if _STATE["scope"] else ""))
        self.mode_btn.setText("Dock" if self.isWindow() else "Float")
        ig = ignored()
        live = [i for i in _STATE["issues"] if i.signature not in ig]
        for sev, b in self.count_btns.items():
            b.setText("%s %d" % (sev, sum(1 for i in live if i.sev == sev)))
        cats = sorted(set(i.category for i in _STATE["issues"]))
        cur = self.category.currentText()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("All categories")
        self.category.addItems(cats)
        self.category.setCurrentIndex(max(0, self.category.findText(cur)))
        self.category.blockSignals(False)
        self.refresh_issues()
        self.refresh_overview()
        self.refresh_perf()

    def refresh_overview(self):
        ig = ignored()
        issues = [i for i in _STATE["issues"] if i.signature not in ig]
        if not _STATE["scope"]:
            self.overview.setHtml("<h3>No scan yet</h3><p><b>Quick scan</b> checks files, renders, expressions, connections, colour and structure. "
                                  "<b>Full scan</b> adds performance: bounding boxes, scaling, heavy nodes and channels. "
                                  "<b>Scan part</b> checks the selection, everything upstream of it, or the path between two nodes.</p>")
            return
        cats = {}
        for i in issues:
            cats.setdefault(i.category, {}).setdefault(i.sev, 0)
            cats[i.category][i.sev] += 1
        rows = "".join("<tr><td><a href='cat:%s' style='color:#f0a043'>%s</a></td>%s</tr>" % (
            c, c, "".join("<td style='color:%s'>%s</td>" % (SEV_COLORS[s][2], v.get(s, "") or "") for s in (ERROR, WARNING, PERF, NOTE)))
            for c, v in sorted(cats.items()))
        n_ign = sum(1 for i in _STATE["issues"] if i.signature in ig)
        verdict = ("<span style='color:#e06060'>Not ready to deliver</span>" if any(i.sev == ERROR for i in issues)
                   else "<span style='color:#e0b040'>Check the warnings</span>" if any(i.sev == WARNING for i in issues)
                   else "<span style='color:#7cc48a'>Looks healthy</span>")
        self.overview.setHtml("<h3>%s</h3><p>%s scan · %d findings%s</p><table cellpadding='4'><tr><th align='left'>Category</th>"
                              "<th>Errors</th><th>Warnings</th><th>Performance</th><th>Notes</th></tr>%s</table>"
                              % (verdict, _STATE["scope"], len(issues), (" · %d ignored" % n_ign) if n_ign else "", rows))

    def _overview_link(self, url):
        s = url.toString()
        if s.startswith("cat:"):
            i = self.category.findText(s[4:])
            if i >= 0:
                self.category.setCurrentIndex(i)
            self.tabs.setCurrentIndex(1)

    def refresh_issues(self, *a):
        ig = ignored()
        cur = self.current_issue()
        cur_sig = cur.signature if cur else None
        self.table.clear()
        for i in self.visible_issues():
            it = QtWidgets.QTreeWidgetItem([i.sev, i.category, i.node or "(script)", i.title + ("  [ignored]" if i.signature in ig else "")])
            it.setForeground(0, QtGui.QBrush(QtGui.QColor(SEV_COLORS[i.sev][2])))
            if i.signature in ig:
                for c in range(4):
                    it.setForeground(c, QtGui.QBrush(QtGui.QColor("#6f6f6f")))
            it.setData(0, QtCore.Qt.UserRole, i)
            it.setToolTip(3, i.details)
            self.table.addTopLevelItem(it)
            if i.signature == cur_sig:
                self.table.setCurrentItem(it)
        for c in range(3):
            self.table.resizeColumnToContents(c)
        if self.table.currentItem() is None and self.table.topLevelItemCount():
            self.table.setCurrentItem(self.table.topLevelItem(0))
        self.show_issue()

    def refresh_perf(self):
        perf = [i for i in _STATE["issues"] if i.sev == PERF or i.category == "Bounding Box"]

        def impact(i):
            m = measured(i.node)
            return (-(m[0] if m else -1.0), -(i.data.get("ratio", 0) * (1 + i.data.get("downstream", 0))))
        perf.sort(key=impact)
        rows = []
        for i in perf:
            m = measured(i.node)
            rows.append((i.title, i.node, ("measured %.1f ms (%.0f%%) · " % m if m else "") + i.details))
        sections = [("%d performance finding(s)%s" % (len(perf), ", measured ones first" if _PROFILE["data"] else ""),
                     rows or [("none: run a Full scan", "", "")])]
        if _PROFILE["data"] and _PROFILE["total"]:
            flagged = set(i.node for i in perf)
            hot = sorted(_PROFILE["data"].items(), key=lambda kv: -kv[1]["wall_ms"])
            hot = [(n, d) for n, d in hot if d["wall_ms"] / _PROFILE["total"] >= 0.05 and n not in flagged][:15]
            sections.append(("Measured hotspots the scan didn't flag", [
                ("%.1f ms (%.0f%%)" % (d["wall_ms"], d["wall_ms"] / _PROFILE["total"] * 100.0), n, d.get("cls", "")) for n, d in hot]
                or [("none above 5% of the measured time", "", "")]))
        self.perf_tree.set_sections(sections)

    def current_issue(self):
        it = self.table.currentItem()
        return it.data(0, QtCore.Qt.UserRole) if it else None

    def selected_issues(self):
        return [it.data(0, QtCore.Qt.UserRole) for it in self.table.selectedItems()]

    def show_issue(self):
        i = self.current_issue()
        has = i is not None
        m = measured(i.node) if has and i.node else None
        for b in (self.b_select, self.b_trace):
            b.setEnabled(bool(has and i.node))
        self.b_docs.setEnabled(has)
        self.b_ignore.setEnabled(has)
        fixable = bool(has and i.fix)
        self.b_fix.setEnabled(fixable)
        self.b_fix.setText(i.fix_label if fixable else "Fix")
        self.b_fix_all.setEnabled(fixable and i.fix not in ("relink", "crop"))
        if not has:
            self.d_title.setText("No findings" if not _STATE["issues"] else "Select a finding")
            self.d_text.setHtml("")
            return
        self.b_ignore.setText("Stop ignoring" if i.signature in ignored() else "Ignore for this script")
        esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        body = "<p><b>Node:</b> %s<br><b>Category:</b> %s</p>" % (esc(i.node or "(script)"), esc(i.category))
        if i.details:
            body += "<p><b>Details</b><br>%s</p>" % esc(i.details)
        if i.why:
            body += "<p><b>Why it matters</b><br>%s</p>" % esc(i.why)
        if i.data.get("affected") and len(i.data["affected"]) > 1:
            body += "<p><b>Inherited by</b><br>%s</p>" % esc(", ".join(i.data["affected"][:30]))
        if m:
            body += "<p><b>Measured</b><br>%.1f ms, %.0f%% of the profiled time</p>" % m
        if i.fix:
            body += "<p><b>Fix</b><br>%s</p>" % esc(i.fix_label)
        self.d_title.setText("%s · %s" % (i.sev, i.title))
        self.d_text.setHtml(body)

    def _sev_clicked(self, sev, checked):
        for s, b in self.count_btns.items():
            if s != sev:
                b.blockSignals(True)
                b.setChecked(False)
                b.blockSignals(False)
        self.sev_filter = sev if checked else None
        self.tabs.setCurrentIndex(1)
        self.refresh_issues()

    def _issue_menu(self, pos):
        i = self.current_issue()
        if i is None:
            return
        m = QtWidgets.QMenu(self)
        if i.node:
            m.addAction("Select node", lambda: select_node(i.node))
            m.addAction("Open properties", lambda: select_node(i.node, panel=True))
            m.addAction("Inspect", self.trace)
        if i.fix:
            m.addAction(i.fix_label, self.fix_selected)
        m.addAction("Stop ignoring" if i.signature in ignored() else "Ignore for this script", self.toggle_ignore)
        m.addAction("Copy finding", lambda: QtWidgets.QApplication.clipboard().setText(i.to_text()))
        m.addAction("Foundry docs", lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl(DOCS.get(i.doc, DOCS["general"]))))
        _exec(m, self.table.viewport().mapToGlobal(pos))

    # ---- actions
    def fix_selected(self):
        done = []
        for i in self.selected_issues() or [self.current_issue()]:
            if i is None or not i.fix:
                continue
            if i.fix == "relink":
                folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Where is %s now?" % os.path.basename(_file_pattern(get_node(i.node)) or ""))
                if folder:
                    done.append("Relinked %s" % i.node if relink(i, folder) else "Couldn't find the file for %s under %s" % (i.node, folder))
                continue
            try:
                done.append(apply_fix(i))
            except Exception as exc:
                done.append("Couldn't fix %s: %s" % (i.node or "script", exc))
        if done:
            self.status.setText("; ".join(done[:3]) + (" …" if len(done) > 3 else ""))
            self._rescan()

    def fix_all_like(self):
        i = self.current_issue()
        if i is None or not i.fix:
            return
        same = [x for x in _STATE["issues"] if x.fix == i.fix and x.title == i.title and x.signature not in ignored()]
        if QtWidgets.QMessageBox.question(self, TOOL, "%s for %d finding(s)?\n\n%s\n\nThis is one undo step." % (i.fix_label, len(same), i.title)) != QtWidgets.QMessageBox.Yes:
            return
        with _Undo("Script Doctor: %s (%d)" % (i.fix_label, len(same))):
            for x in same:
                try:
                    apply_fix(x)
                except Exception:
                    pass
        self.status.setText("Applied '%s' to %d finding(s)." % (i.fix_label, len(same)))
        self._rescan()

    def _rescan(self):
        scope = _STATE["scope"] or "Quick"
        kind = "Full" if scope.startswith("Full") else "Quick"
        if scope.startswith(("Selection", "Upstream", "Between")):
            kind = "Full"
        self.run_scan(kind)

    def toggle_ignore(self):
        sigs = ignored()
        targets = self.selected_issues() or [self.current_issue()]
        targets = [t for t in targets if t is not None]
        if not targets:
            return
        if all(t.signature in sigs for t in targets):
            sigs -= set(t.signature for t in targets)
        else:
            sigs |= set(t.signature for t in targets)
        set_ignored(sigs)
        for w in list(_WIDGETS):
            try:
                w.refresh_all()
            except RuntimeError:
                _WIDGETS.remove(w)

    def trace(self):
        i = self.current_issue()
        if i is None or not i.node:
            return
        n = get_node(i.node)
        if n is None:
            self.status.setText("That node no longer exists. Run the scan again.")
            return
        if i.category == "Bounding Box":
            self._show_inspect(bbox_contributors(n) + crop_safety(n))
        elif i.category in ("Render", "Files"):
            self._show_inspect(inspect_node(n) + where_used(n))
        else:
            self._show_inspect(inspect_node(n))

    def select_perf_nodes(self):
        names = [i.node for i in _STATE["issues"] if (i.sev == PERF or i.category == "Bounding Box") and i.node]
        for s in nuke.selectedNodes():
            s.setSelected(False)
        for nm in names:
            n = get_node(nm)
            if n is not None:
                n.setSelected(True)
        try:
            nuke.zoomToFitSelected()
        except Exception:
            pass
        self.status.setText("Selected %d slow node(s)." % len(names))

    def heat_map(self, on):
        if not on:
            self.heat_off()
            return
        heat = _STATE["heat"]
        for i in _STATE["issues"]:
            if not i.node or not (i.sev == PERF or i.category == "Bounding Box"):
                continue
            n = get_node(i.node)
            if n is None or "tile_color" not in n.knobs():
                continue
            if i.node not in heat:
                heat[i.node] = int(n["tile_color"].value())
            n["tile_color"].setValue(0xA03A3AFF if i.sev == ERROR or i.data.get("ratio", 0) >= 8 else 0xB0742FFF)
        self.status.setText("Heat map on: %d node(s) coloured. Turn it off to restore their colours." % len(heat))

    def heat_off(self):
        heat = _STATE["heat"]
        for name, col in list(heat.items()):
            n = get_node(name)
            if n is not None and "tile_color" in n.knobs():
                try:
                    n["tile_color"].setValue(col)
                except Exception:
                    pass
        heat.clear()
        for w in list(_WIDGETS):
            try:
                w.b_heat.blockSignals(True)
                w.b_heat.setChecked(False)
                w.b_heat.blockSignals(False)
            except RuntimeError:
                pass

    def run_final_qc(self):
        self.status.setText("Running Final QC…")
        QtWidgets.QApplication.processEvents()
        blockers, warnings, passed = final_qc()
        self.overview_results.set_sections([("Blockers (%d)" % len(blockers), [("⚠ " + t, n, "") for t, n in blockers] or [("none", "", "")]),
                                            ("Warnings (%d)" % len(warnings), [(t, n, "") for t, n in warnings] or [("none", "", "")]),
                                            ("Passed (%d)" % len(passed), [("✓ " + t, n, "") for t, n in passed])])
        self.tabs.setCurrentIndex(0)
        self.status.setText("Final QC: %d blocker(s), %d warning(s)." % (len(blockers), len(warnings)))

    def compare(self):
        prev = _STATE.get("previous")
        if prev is None:
            self.status.setText("Run two scans to compare them; the previous one is kept automatically.")
            return
        cur = dict((i.signature, i) for i in _STATE["issues"])
        prev = set(prev)
        new = [cur[s] for s in cur if s not in prev]
        fixed = sorted(prev - set(cur))
        self.overview_results.set_sections([
            ("New since the previous scan (%d)" % len(new), [(i.title, i.node, i.details) for i in new] or [("none", "", "")]),
            ("Resolved (%d)" % len(fixed), [(s.split("|")[2], s.split("|")[1], s.split("|")[0]) for s in fixed] or [("none", "", "")]),
            ("Unchanged", [("%d finding(s)" % (len(cur) - len(new)), "", "")])])
        self.tabs.setCurrentIndex(0)

    def copy_report(self):
        QtWidgets.QApplication.clipboard().setText(report_text(_STATE["issues"], _STATE["scope"]))
        self.status.setText("Report copied.")

    def save_report(self):
        base = os.path.splitext(os.path.basename(_script_path() or "script"))[0] or "script"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save report", os.path.join(os.path.expanduser("~"), base + "_doctor.html"),
                                                        "HTML (*.html);;Text (*.txt)")
        if not path:
            return
        with open(path, "w") as fh:
            fh.write(report_text(_STATE["issues"], _STATE["scope"]) if path.lower().endswith(".txt") else report_html(_STATE["issues"], _STATE["scope"]))
        self.status.setText("Saved %s" % path)

    # ---- colour manager
    def refresh_color(self, *a):
        self._color_loaded = True
        if self.c_target.count() == 0:
            values = []
            try:
                tmp = nuke.nodes.Read()
                try:
                    values = list(tmp["colorspace"].values())
                finally:
                    nuke.delete(tmp)
            except Exception:
                pass
            self.c_target.addItems(values or ["default"])
        reads = ([n for n in nuke.selectedNodes() if n.Class() == "Read"] if self.c_scope.currentIndex() == 1
                 else [n for n in nuke.allNodes(recurseGroups=True) if n.Class() == "Read"])
        old = self.c_filter.currentText()
        profiles = ["All"] + sorted(set(str(_knob(n, "colorspace", "?")) for n in reads))
        self.c_filter.blockSignals(True)
        self.c_filter.clear()
        self.c_filter.addItems(profiles)
        self.c_filter.setCurrentIndex(max(0, self.c_filter.findText(old)))
        self.c_filter.blockSignals(False)
        self.c_table.setRowCount(0)
        for n in reads:
            r = self.c_table.rowCount()
            self.c_table.insertRow(r)
            chk = QtWidgets.QTableWidgetItem()
            chk.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable)
            chk.setCheckState(QtCore.Qt.Checked)
            self.c_table.setItem(r, 0, chk)
            self.c_table.setItem(r, 1, QtWidgets.QTableWidgetItem(n.fullName()))
            self.c_table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(_knob(n, "colorspace", "?"))))
            self.c_table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(_knob(n, "file", ""))))
        for c in range(3):
            self.c_table.resizeColumnToContents(c)
        self._color_filter()

    def _color_filter(self, *a):
        f = self.c_filter.currentText()
        for r in range(self.c_table.rowCount()):
            self.c_table.setRowHidden(r, f not in ("", "All") and self.c_table.item(r, 2).text() != f)

    def apply_color(self):
        target = self.c_target.currentText()
        names = [self.c_table.item(r, 1).text() for r in range(self.c_table.rowCount())
                 if not self.c_table.isRowHidden(r) and self.c_table.item(r, 0).checkState() == QtCore.Qt.Checked]
        if not names:
            self.status.setText("No Reads are ticked.")
            return
        if QtWidgets.QMessageBox.question(self, TOOL, "Set %d Read(s) to %s?\n\nThis is one undo step." % (len(names), target)) != QtWidgets.QMessageBox.Yes:
            return
        with _Undo("Script Doctor: set Read colourspace"):
            for nm in names:
                n = get_node(nm)
                if n is not None and "colorspace" in n.knobs():
                    try:
                        n["colorspace"].setValue(target)
                    except Exception:
                        pass
        self.refresh_color()
        self.status.setText("Set %d Read(s) to %s." % (len(names), target))

    # ---- settings + mode
    def _settings(self):
        s = load_settings()
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Script Doctor settings")
        form = QtWidgets.QFormLayout(dlg)
        spins = {}
        for key, label in (("bbox_warning_ratio", "Bounding box warning (× project area)"), ("bbox_extreme_ratio", "Bounding box error (× project area)"),
                           ("scale_warning", "Transform scale warning"), ("upscale_warning", "Reformat upscale warning (× pixels)"),
                           ("large_filter", "Large filter size"), ("channel_warning", "Channel count warning"),
                           ("roto_size_warning", "Large Roto (characters)")):
            sp = QtWidgets.QDoubleSpinBox()
            sp.setRange(0, 1e9)
            sp.setDecimals(2)
            sp.setValue(float(s[key]))
            spins[key] = sp
            form.addRow(label, sp)
        form.addRow(QtWidgets.QLabel("<b>Checks to run</b>"))
        boxes = {}
        off = set(s.get("disabled_categories", []))
        for c in CATEGORY_CHECKS:
            cb = QtWidgets.QCheckBox(c)
            cb.setChecked(c not in off)
            boxes[c] = cb
            form.addRow(cb)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if _exec(dlg) == QtWidgets.QDialog.Accepted:
            for k, sp in spins.items():
                s[k] = sp.value()
            s["disabled_categories"] = [c for c, cb in boxes.items() if not cb.isChecked()]
            save_settings(s)
            self.status.setText("Settings saved. They apply to the next scan.")

    def _switch_mode(self):
        s = load_settings()
        if self.isWindow():
            s["mode"] = "docked"
            save_settings(s)
            self.close()
            show_docked()
        else:
            s["mode"] = "window"
            save_settings(s)
            show_window()

    def closeEvent(self, ev):
        if len([w for w in _WIDGETS if _alive(w) and w is not self and w.isVisible()]) == 0:
            self.heat_off()
            restore_compare()
            set_live_reset(False)
        super(DoctorWidget, self).closeEvent(ev)


def _alive(w):
    try:
        w.isVisible()
        return True
    except RuntimeError:
        return False


# ---------------------------------------------------------------- opening: window or docked
_window = None


def _nuke_main_window():
    app = QtWidgets.QApplication.instance()
    for w in app.topLevelWidgets() if app else []:
        if isinstance(w, QtWidgets.QMainWindow):
            return w
    return None


def show_window():
    """Floating window that stays above Nuke."""
    global _window
    if _window is not None and _alive(_window):
        _window.show()
        _window.raise_()
        _window.activateWindow()
        return _window
    _window = DoctorWidget(_nuke_main_window())
    _window.setWindowFlags(QtCore.Qt.Window)
    # without its own icon the window shows its parent's (Nuke's)
    icon = QtGui.QIcon(ICON_FILE)
    if not icon.isNull():
        _window.setWindowIcon(icon)
    _window.setWindowTitle(TOOL)
    _window.resize(1080, 700)
    _window.show()
    _window.refresh_all()
    return _window


def show_docked():
    """Docked tab next to Properties."""
    if _nkpanels is None:
        return show_window()
    panel = _nkpanels.registerWidgetAsPanel("sleepy_doctor.DoctorWidget", TOOL, PANEL_ID, True)
    pane = nuke.getPaneFor("Properties.1") or nuke.getPaneFor("DAG.1")
    if pane is not None:
        panel.addToPane(pane)
    else:
        panel.addToPane()
    return panel


def show():
    """Opens the way you used it last (window by default)."""
    return show_docked() if load_settings().get("mode") == "docked" else show_window()


# ---------------------------------------------------------------- save check + install
def _on_save():
    try:
        ig = ignored()
        errors = [i for i in Scanner().scan(deep=False) if i.sev == ERROR and i.signature not in ig]
    except Exception:
        return
    if errors:
        lines = ["%s: %s" % (i.node or "script", i.title) for i in errors[:12]]
        more = "\n…and %d more" % (len(errors) - 12) if len(errors) > 12 else ""
        nuke.message("Script Doctor found %d error%s:\n\n%s%s\n\n(The script was saved.)"
                     % (len(errors), "s" if len(errors) > 1 else "", "\n".join(lines), more))


def set_check_on_save(on):
    s = load_settings()
    s["check_on_save"] = bool(on)
    save_settings(s)
    try:
        nuke.removeOnScriptSave(_on_save)
    except Exception:
        pass
    if on:
        nuke.addOnScriptSave(_on_save)


_installed = False


def install(menu="SleepyTools"):
    global _installed
    if _installed:
        return
    if getattr(nuke, "_sleepy_script_doctor_installed", False):
        _installed = True           # installed by an earlier copy of this module
        return
    if _nkpanels is not None:
        _nkpanels.registerWidgetAsPanel("sleepy_doctor.DoctorWidget", TOOL, PANEL_ID)
    m = nuke.menu("Nuke").addMenu(menu)
    m.addCommand("Script Doctor", "sleepy_doctor.show()")
    m.addCommand("Script Doctor (window)", "sleepy_doctor.show_window()")
    m.addCommand("Script Doctor (docked)", "sleepy_doctor.show_docked()")
    if load_settings().get("check_on_save"):
        nuke.addOnScriptSave(_on_save)
    nuke._sleepy_script_doctor_installed = True
    _installed = True


# ---------------------------------------------------------------- measured profiling (Nuke performance timers)
_PROFILE = {"data": {}, "total": 0.0, "baseline": {}, "compare": None, "live_cb": False}


def profiling_supported():
    return all(hasattr(nuke, f) for f in ("startPerformanceTimers", "stopPerformanceTimers",
                                            "resetPerformanceTimers", "usingPerformanceTimers"))


def _perf_info(node):
    try:
        info = node.performanceInfo(nuke.PROFILE_ENGINE) if hasattr(nuke, "PROFILE_ENGINE") else node.performanceInfo()
    except Exception:
        return None
    if not isinstance(info, dict):
        return None
    def num(key):
        v = info.get(key, 0)
        return 0.0 if isinstance(v, bool) else float(v or 0)
    return {"calls": int(num("callCount")), "wall_ms": num("timeTakenWall") / 1000.0, "cpu_ms": num("timeTakenCPU") / 1000.0}


def take_snapshot():
    """Read the accumulated timers for every node. Timers are left as they were."""
    data, total = {}, 0.0
    for n in nuke.allNodes(recurseGroups=True):
        info = _perf_info(n)
        if info and (info["calls"] or info["wall_ms"] or info["cpu_ms"]):
            data[n.fullName()] = dict(info, cls=n.Class())
            total += info["wall_ms"]
    _PROFILE["data"], _PROFILE["total"] = data, total
    return data, total


def measured(name):
    """(wall_ms, percent of total) for a node from the last snapshot, or None."""
    d = _PROFILE["data"].get(name)
    if not d or not _PROFILE["total"]:
        return None
    return d["wall_ms"], d["wall_ms"] / _PROFILE["total"] * 100.0


def _live_reset():
    try:
        if nuke.usingPerformanceTimers():
            nuke.resetPerformanceTimers()
    except Exception:
        pass


def set_live_reset(on):
    try:
        if on and not _PROFILE["live_cb"]:
            nuke.addKnobChanged(_live_reset)
            _PROFILE["live_cb"] = True
        elif not on and _PROFILE["live_cb"]:
            nuke.removeKnobChanged(_live_reset)
            _PROFILE["live_cb"] = False
    except Exception:
        pass


def viewer_path():
    """Full names of every node feeding the active Viewer input."""
    try:
        v = nuke.activeViewer()
        seed = v.node().input(v.activeInput() or 0)
    except Exception:
        return set()
    if seed is None:
        return set()
    return Graph(nuke.allNodes(recurseGroups=True)).upstream([seed.fullName()])


def restore_compare():
    """Put back the disable states changed by Disable and compare."""
    c = _PROFILE.get("compare")
    if not c:
        return
    for name, state in c["states"].items():
        n = get_node(name)
        if n is not None:
            try:
                n["disable"].setValue(state)
            except Exception:
                pass
    _PROFILE["compare"] = None


class _Num(QtWidgets.QTableWidgetItem):
    """Sorts by the number stored in UserRole."""

    def __lt__(self, other):
        try:
            return float(self.data(QtCore.Qt.UserRole)) < float(other.data(QtCore.Qt.UserRole))
        except Exception:
            return super(_Num, self).__lt__(other)


class ProfilePanel(QtWidgets.QWidget):
    COLS = ["Node", "Class", "Wall ms", "CPU ms", "Calls", "% of total", "Δ vs baseline", "Notes"]

    def __init__(self, status_fn, parent=None):
        super(ProfilePanel, self).__init__(parent)
        self.status = status_fn
        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel("Measured timings from Nuke's performance timers. Start timing, work and update the Viewer "
                                 "as usual, then take a snapshot. Timing slows Nuke down a little while it's on.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        lay.addWidget(intro)
        r1 = QtWidgets.QHBoxLayout()
        self.b_timing = QtWidgets.QPushButton("Start timing")
        self.b_timing.setObjectName("primary")
        self.b_timing.setCheckable(True)
        self.b_timing.toggled.connect(self.toggle_timing)
        r1.addWidget(self.b_timing)
        for label, fn in (("Snapshot", self.snapshot), ("Reset timers", self.reset)):
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(fn)
            r1.addWidget(b)
        self.top10 = QtWidgets.QCheckBox("Top 10")
        self.top10.toggled.connect(self.refill)
        r1.addWidget(self.top10)
        self.vpath = QtWidgets.QCheckBox("Viewer path only")
        self.vpath.setToolTip("Only nodes feeding the active Viewer input")
        self.vpath.toggled.connect(self._vpath_toggled)
        r1.addWidget(self.vpath)
        self.live = QtWidgets.QCheckBox("Reset on knob change")
        self.live.setToolTip("Zero the timers whenever a knob changes, so each snapshot shows only the latest state")
        self.live.toggled.connect(set_live_reset)
        r1.addWidget(self.live)
        r1.addStretch(1)
        self.summary = QtWidgets.QLabel("No snapshot yet")
        self.summary.setObjectName("muted")
        r1.addWidget(self.summary)
        lay.addLayout(r1)
        r2 = QtWidgets.QHBoxLayout()
        for label, fn, tip in (("Save baseline", self.save_baseline, "Keep this snapshot to compare later changes against"),
                               ("Compare with baseline", self.compare_baseline, "Show what got faster or slower since the baseline"),
                               ("Disable and compare", self.disable_compare, "Disable the selected rows, update the Viewer, then press again to see how much time they cost")):
            b = QtWidgets.QPushButton(label)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            r2.addWidget(b)
            if label.startswith("Disable"):
                self.b_dc = b
        r2.addStretch(1)
        lay.addLayout(r2)
        self.table = QtWidgets.QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellClicked.connect(lambda r, c: select_node(self.table.item(r, 0).data(QtCore.Qt.UserRole)))
        self.table.cellDoubleClicked.connect(lambda r, c: select_node(self.table.item(r, 0).data(QtCore.Qt.UserRole), panel=True))
        lay.addWidget(self.table, 1)
        self.vnames = set()
        try:
            self.b_timing.blockSignals(True)
            self.b_timing.setChecked(profiling_supported() and bool(nuke.usingPerformanceTimers()))
            self.b_timing.setText("Stop timing" if self.b_timing.isChecked() else "Start timing")
            self.b_timing.blockSignals(False)
        except Exception:
            pass
        self.refill()

    def _need(self):
        if not profiling_supported():
            self.status("This Nuke doesn't expose the performance timers to Python.")
            return False
        return True

    def toggle_timing(self, on):
        if not self._need():
            self.b_timing.blockSignals(True)
            self.b_timing.setChecked(False)
            self.b_timing.blockSignals(False)
            return
        try:
            if on and not nuke.usingPerformanceTimers():
                nuke.startPerformanceTimers()
            elif not on and nuke.usingPerformanceTimers():
                nuke.stopPerformanceTimers()
        except Exception as exc:
            self.status("Couldn't change timing: %s" % exc)
        self.b_timing.setText("Stop timing" if on else "Start timing")
        self.status("Timing on: update the Viewer normally, then take a Snapshot." if on else "Timing off. The last snapshot stays visible.")

    def snapshot(self):
        if not self._need():
            return
        data, total = take_snapshot()
        self.refill()
        self.status("Snapshot: %d timed node(s), %.1f ms wall time." % (len(data), total))
        for w in list(_WIDGETS):
            try:
                w.refresh_perf()
            except RuntimeError:
                pass

    def reset(self):
        if not self._need():
            return
        try:
            nuke.resetPerformanceTimers()
        except Exception as exc:
            self.status("Couldn't reset: %s" % exc)
            return
        _PROFILE["data"], _PROFILE["total"] = {}, 0.0
        self.refill()
        self.status("Timers reset to zero.")

    def _vpath_toggled(self, on):
        self.vnames = viewer_path() if on else set()
        if on and not self.vnames:
            self.vpath.blockSignals(True)
            self.vpath.setChecked(False)
            self.vpath.blockSignals(False)
            self.status("No active Viewer input found.")
        self.refill()

    def save_baseline(self):
        if not _PROFILE["data"]:
            self.status("Take a snapshot first.")
            return
        _PROFILE["baseline"] = dict((k, dict(v)) for k, v in _PROFILE["data"].items())
        _PROFILE["baseline_total"] = _PROFILE["total"]
        self.refill()
        self.status("Baseline saved (%.1f ms). Change the comp, reset, update the Viewer, snapshot, then compare." % _PROFILE["total"])

    def compare_baseline(self):
        base = _PROFILE.get("baseline")
        if not base:
            self.status("Save a baseline first.")
            return
        bt, ct = _PROFILE.get("baseline_total", 0.0), _PROFILE["total"]
        self.refill()
        self.table.sortItems(6, QtCore.Qt.DescendingOrder)
        d = ct - bt
        self.status("Baseline %.1f ms → now %.1f ms (%+.1f ms, %+.0f%%). Biggest increases are at the top." % (bt, ct, d, (d / bt * 100.0) if bt else 0.0))

    def disable_compare(self):
        if not self._need():
            return
        c = _PROFILE.get("compare")
        if c:
            take_snapshot()
            after = _PROFILE["total"]
            restore_compare()
            saved = c["before"] - after
            self.b_dc.setText("Disable and compare")
            self.refill()
            self.status("Disable and compare: %.1f ms with the nodes on, %.1f ms with them off. They cost about %.1f ms (%.0f%%). Original states restored."
                        % (c["before"], after, saved, (saved / c["before"] * 100.0) if c["before"] else 0.0))
            return
        names = [self.table.item(i.row(), 0).data(QtCore.Qt.UserRole) for i in self.table.selectionModel().selectedRows()]
        nodes = [get_node(n) for n in names]
        nodes = [n for n in nodes if n is not None and "disable" in n.knobs()]
        if not nodes:
            self.status("Select one or more rows with nodes that can be disabled.")
            return
        take_snapshot()
        if not _PROFILE["total"]:
            self.status("No timing yet: start timing, update the Viewer and take a snapshot first.")
            return
        _PROFILE["compare"] = {"before": _PROFILE["total"], "states": dict((n.fullName(), bool(n["disable"].value())) for n in nodes)}
        for n in nodes:
            n["disable"].setValue(True)
        try:
            nuke.resetPerformanceTimers()
            if not nuke.usingPerformanceTimers():
                nuke.startPerformanceTimers()
        except Exception:
            pass
        self.b_dc.setText("Finish compare and restore")
        self.status("%d node(s) temporarily disabled. Update the Viewer, then press Finish compare and restore." % len(nodes))

    def _note(self, name, d, pct, delta):
        notes = []
        if pct >= 20:
            notes.append("Major bottleneck")
        elif pct >= 5:
            notes.append("Worth a look")
        if d["calls"] >= 100 and d["wall_ms"] / max(1, d["calls"]) < 0.05:
            notes.append("Many small calls")
        if delta is not None and delta > max(2.0, d["wall_ms"] * 0.15):
            notes.append("Slower than baseline")
        elif delta is not None and delta < -2.0:
            notes.append("Faster than baseline")
        for i in _STATE["issues"]:
            if i.node == name and (i.sev == PERF or i.category == "Bounding Box"):
                notes.append("Doctor: " + i.title)
                break
        return " · ".join(notes)

    def refill(self, *a):
        data, total, base = _PROFILE["data"], _PROFILE["total"], _PROFILE.get("baseline") or {}
        names = set(data) | (set(base) if base else set())
        if self.vpath.isChecked():
            names &= self.vnames
        rows = sorted(names, key=lambda n: -data.get(n, {}).get("wall_ms", 0.0))
        if self.top10.isChecked():
            rows = rows[:10]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for name in rows:
            d = data.get(name, {"calls": 0, "wall_ms": 0.0, "cpu_ms": 0.0, "cls": base.get(name, {}).get("cls", "")})
            pct = d["wall_ms"] / total * 100.0 if total else 0.0
            delta = (d["wall_ms"] - base[name]["wall_ms"]) if name in base else (d["wall_ms"] if base else None)
            r = self.table.rowCount()
            self.table.insertRow(r)
            it = QtWidgets.QTableWidgetItem(name)
            it.setData(QtCore.Qt.UserRole, name)
            self.table.setItem(r, 0, it)
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(d.get("cls", "")))
            for c, val, txt in ((2, d["wall_ms"], "%.2f" % d["wall_ms"]), (3, d["cpu_ms"], "%.2f" % d["cpu_ms"]),
                                (4, d["calls"], str(d["calls"])), (5, pct, "%.1f%%" % pct),
                                (6, delta if delta is not None else 0.0, ("%+.2f" % delta) if delta is not None else "-")):
                x = _Num(txt)
                x.setData(QtCore.Qt.UserRole, float(val))
                x.setTextAlignment(int(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter))
                if c == 5:
                    x.setForeground(QtGui.QBrush(QtGui.QColor("#e06060" if pct >= 20 else "#e0b040" if pct >= 5 else "#7cc48a")))
                if c == 6 and delta is not None:
                    x.setForeground(QtGui.QBrush(QtGui.QColor("#e06060" if delta > 0 else "#7cc48a")))
                self.table.setItem(r, c, x)
            note = self._note(name, d, pct, delta)
            ni = QtWidgets.QTableWidgetItem(note)
            ni.setToolTip(note)
            self.table.setItem(r, 7, ni)
        self.table.setSortingEnabled(True)
        for c in range(7):
            self.table.resizeColumnToContents(c)
        heavy = sum(1 for d in data.values() if total and d["wall_ms"] / total >= 0.2)
        self.summary.setText("%d timed · %.1f ms · %d heavy" % (len(data), total, heavy) if data else "No snapshot yet")
