"""Sleepy Command Palette for Nuke.

Fuzzy-search popup for every menu command, every node/gizmo in the Nodes
toolbar, and every node in the current script (jump to it).

Part of Sleepy tools: installed by SleepyTools/menu.py as Nuke > SleepyTools > Command Palette (Ctrl+Alt+Space).

Keys: type to filter, Up/Down to move, Enter to run, Esc to close.
Prefix the search with "@" to search only nodes in the script, ">" for commands only.
"""
import json
import os

import nuke

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

__version__ = '1.1'
SHORTCUT = 'ctrl+alt+space'
MAX_RESULTS = 60
RECENT_FILE = os.path.join(os.path.expanduser('~'), '.nuke', 'sleepy_palette_recent.json')
SKIP_MENUS = ('Recent Files', 'Workspace')

_dialog = None


# ---------------------------------------------------------------------- data
class Entry(object):
    __slots__ = ('label', 'path', 'kind', 'item', 'node_name', 'key')

    def __init__(self, label, path, kind, item=None, node_name=None):
        self.label = label
        self.path = path
        self.kind = kind          # 'cmd', 'node', 'goto'
        self.item = item
        self.node_name = node_name
        self.key = '%s|%s' % (kind, path)


def _clean(name):
    return name.replace('&', '').strip()


def _walk(menu, prefix, kind, out):
    try:
        items = menu.items()
    except Exception:
        return
    for item in items:
        name = _clean(item.name())
        if not name or name.startswith('@') or name in SKIP_MENUS:
            continue
        path = prefix + '/' + name if prefix else name
        if isinstance(item, nuke.Menu):
            _walk(item, path, kind, out)
        else:
            out.append(Entry(name, path, kind, item=item))


def collect_entries():
    out = []
    _walk(nuke.menu('Nodes'), '', 'node', out)
    _walk(nuke.menu('Nuke'), '', 'cmd', out)
    for n in nuke.allNodes(recurseGroups=False):
        out.append(Entry(n.name(), '%s  (%s)' % (n.name(), n.Class()), 'goto', node_name=n.fullName()))
    return out


def load_recent():
    try:
        with open(RECENT_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def save_recent(key):
    recent = [k for k in load_recent() if k != key]
    recent.insert(0, key)
    try:
        folder = os.path.dirname(RECENT_FILE)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(RECENT_FILE, 'w') as f:
            json.dump(recent[:50], f)
    except Exception:
        pass


def fuzzy_score(query, text):
    """Subsequence match. Higher is better, None = no match."""
    if not query:
        return 0
    q = query.lower()
    t = text.lower()
    if q in t:
        score = 200 - t.index(q) - len(t) * 0.1
        if t.startswith(q):
            score += 100
        return score
    score, pos, prev = 0.0, 0, -2
    for ch in q:
        i = t.find(ch, pos)
        if i < 0:
            return None
        if i == prev + 1:
            score += 8                      # consecutive letters
        if i == 0 or t[i - 1] in ' /_-.(':
            score += 10                     # start of a word
        score -= (i - pos) * 0.5            # gap penalty
        prev, pos = i, i + 1
    return score - len(t) * 0.1


# ---------------------------------------------------------------------- UI
class Palette(QtWidgets.QDialog):
    KIND_TAG = dict(cmd='menu', node='create', goto='go to')

    def __init__(self, parent=None):
        super(Palette, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setMinimumWidth(620)
        self.entries = []
        self.recent = []

        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText('Search commands, nodes, gizmos...   (@ = nodes in script, > = menu commands)')
        self.list = QtWidgets.QListWidget()
        self.list.setUniformItemSizes(True)
        self.hint = QtWidgets.QLabel('Enter: run   Esc: close')
        self.hint.setStyleSheet('color: #888; font-size: 10px;')

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self.edit)
        lay.addWidget(self.list)
        lay.addWidget(self.hint)
        self.setStyleSheet('QLineEdit { font-size: 15px; padding: 6px; }'
                           'QListWidget { font-size: 13px; }')

        self.edit.textChanged.connect(self.refresh)
        self.edit.installEventFilter(self)
        self.list.itemActivated.connect(lambda _: self.run_current())

    def open(self):
        self.entries = collect_entries()
        self.recent = load_recent()
        self.edit.clear()
        self.refresh('')
        pos = QtGui.QCursor.pos()
        self.resize(640, 420)
        self.move(pos.x() - 320, pos.y() - 40)
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

    def refresh(self, text):
        text = text.strip()
        kinds = None
        if text.startswith('@'):
            kinds, text = ('goto',), text[1:].strip()
        elif text.startswith('>'):
            kinds, text = ('cmd',), text[1:].strip()
        rank = dict((k, i) for i, k in enumerate(self.recent))
        scored = []
        for e in self.entries:
            if kinds and e.kind not in kinds:
                continue
            s1 = fuzzy_score(text, e.label)
            s2 = fuzzy_score(text, e.path)
            cands = [v for v in (s1, None if s2 is None else s2 - 20) if v is not None]
            if not cands:
                continue
            best = max(cands)
            if e.key in rank:
                best += 60 - min(rank[e.key], 50)
            if not text and e.key not in rank:
                best -= 1000                 # empty query: recent items first
            scored.append((best, e))
        scored.sort(key=lambda x: -x[0])
        self.list.clear()
        for _, e in scored[:MAX_RESULTS]:
            it = QtWidgets.QListWidgetItem('%-8s  %s' % (self.KIND_TAG[e.kind], e.path))
            it.setData(QtCore.Qt.UserRole, e)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def eventFilter(self, obj, event):
        if obj is self.edit and event.type() == QtCore.QEvent.KeyPress:
            key = event.key()
            if key in (QtCore.Qt.Key_Down, QtCore.Qt.Key_Up):
                row = self.list.currentRow() + (1 if key == QtCore.Qt.Key_Down else -1)
                self.list.setCurrentRow(max(0, min(row, self.list.count() - 1)))
                return True
            if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                self.run_current()
                return True
            if key == QtCore.Qt.Key_Escape:
                self.close()
                return True
        return super(Palette, self).eventFilter(obj, event)

    def run_current(self):
        it = self.list.currentItem()
        if it is None:
            return
        e = it.data(QtCore.Qt.UserRole)
        self.close()
        save_recent(e.key)
        # run after the popup is gone so new nodes/panels get focus normally
        QtCore.QTimer.singleShot(0, lambda: _execute(e))


def _execute(e):
    try:
        if e.kind == 'goto':
            n = nuke.toNode(e.node_name)
            if n is None:
                return
            for s in nuke.selectedNodes():
                s.setSelected(False)
            n.setSelected(True)
            nuke.zoom(nuke.zoom(), [n.xpos() + n.screenWidth() / 2, n.ypos() + n.screenHeight() / 2])
            n.showControlPanel()
        else:
            e.item.invoke()
    except Exception as err:
        nuke.message('Command palette: could not run "%s"\n%s' % (e.path, err))


def show():
    global _dialog
    if _dialog is None:
        _dialog = Palette(QtWidgets.QApplication.activeWindow())
    _dialog.open()


_installed = False


def install(menu='SleepyTools', shortcut=SHORTCUT):
    """Add Nuke > SleepyTools > Command Palette (default shortcut Ctrl+Alt+Space)."""
    global _installed
    if _installed:
        return
    _installed = True
    nuke.menu('Nuke').addMenu(menu).addCommand('Command Palette', 'import sleepy_command_palette; sleepy_command_palette.show()',
                                               shortcut)
