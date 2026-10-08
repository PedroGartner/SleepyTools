"""Sleepy Gizmo Manager for Nuke.

Browse your gizmos by category, see what each one does and where it is used in the open
script, and manage those instances:

  * Create a gizmo (double-click, Enter, or the Create button).
  * Select / zoom to its instances in the Node Graph.
  * Swap instances to another gizmo, keeping connections, position, name and every knob
    value whose name exists on the new gizmo (e.g. move old shots onto SleepyGrain_v1).
  * Bake instances to Groups, so the script no longer needs the gizmo file
    (safe for the farm, other artists or other facilities).

Layout: views on the left (Sleepy tools by category, used in this script, Nuke built-in, other
folders), the gizmo list in the middle, details and every action on the right.

Part of Sleepy tools: installed by SleepyTools/menu.py as Nuke > SleepyTools > Gizmo Manager, which opens it as a
tab next to the Properties panel (also in Windows > Custom > Sleepy Gizmo Manager). Drag the tab
anywhere; it is saved with your workspace like any other panel.
"""
import html
import io
import os
import re

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

__version__ = '2.1'
PANEL_ID = 'uk.co.pg.GizmoManager'
PANEL_TITLE = 'Sleepy Gizmo Manager'
ACCENT = '#f0a043'
CATEGORY_ORDER = ['Keying', 'Grain', 'Cleanup', 'Lens', 'CG', 'QC']

SKIP_KNOBS = set(['name', 'xpos', 'ypos', 'selected', 'help', 'onCreate', 'onDestroy', 'knobChanged',
                  'updateUI', 'autolabel', 'panel', 'gizmo_file', 'inputs', 'dope_sheet', 'bookmark',
                  'postage_stamp_frame', 'indicators', 'lifetimeStart', 'lifetimeEnd'])
SKIP_CLASSES = ('Tab_Knob', 'PyScript_Knob', 'PythonCustomKnob', 'Text_Knob', 'Obsolete_Knob', 'Help_Knob')

# views in the left column (fixed ones; categories are added between them)
V_ALL_SLEEPY, V_USED, V_NUKE, V_OTHER = 'All Sleepy tools', 'Used in this script', 'Nuke built-in', 'Other folders'


# ---------------------------------------------------------------------- data
def _norm(p):
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def _sleepy_gizmo_root():
    try:
        import sleepy_tools
        return _norm(sleepy_tools.GIZMO_ROOT)
    except Exception:
        return None


def _nuke_install_dir():
    try:
        return _norm(os.path.dirname(nuke.EXE_PATH))
    except Exception:
        return None


def _unescape_nk(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            out.append('\n' if s[i + 1] == 'n' else s[i + 1])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return ''.join(out)


def _strip_html(s):
    return html.unescape(re.sub(r'<[^>]+>', ' ', s)).replace('\xa0', ' ')


def read_info(path):
    """Version, one-line summary and inputs, read from the gizmo file (Sleepy header or help text)."""
    info = {'version': '', 'summary': '', 'inputs': []}
    try:
        with io.open(path, 'r', encoding='utf-8', errors='replace') as fh:
            head = fh.read(60000)
    except Exception:
        return info
    title = re.search(r'addUserKnob \{26 sleepy_title [^\n]*? T "((?:[^"\\]|\\.)*)"', head)
    if title:
        t = _unescape_nk(title.group(1))
        m = re.search(r'v(\d+(?:\.\d+)*)', t)
        info['version'] = 'v' + m.group(1) if m else ''
        parts = t.split('<br>')
        info['summary'] = _strip_html(parts[1]).strip() if len(parts) > 1 else ''
    about = re.search(r'addUserKnob \{26 sleepy_about_text [^\n]*? T "((?:[^"\\]|\\.)*)"', head)
    if about:
        a = _unescape_nk(about.group(1))
        info['inputs'] = [(_strip_html(n).strip(), _strip_html(d).strip())
                          for n, d in re.findall(r'<tr><td><b>(.*?)</b>.*?</td><td>(.*?)</td></tr>', a)]
    if not info['summary']:
        hm = re.search(r'^\s*help "((?:[^"\\]|\\.)*)"', head, re.M)
        if hm:
            first = _unescape_nk(hm.group(1)).strip().split('\n')[0]
            info['summary'] = first[:220]
    if not info['version']:
        body = head[head.find('Gizmo {'):][:6000]          # skip the 'version 13.2 v4' file header
        vm = re.search(r'\bv(\d+(?:\.\d+)?)\b', body)
        info['version'] = 'v' + vm.group(1) if vm else ''
    return info


def scan():
    """Every gizmo on the plugin path: list of dicts (name, path, source, category, ...)."""
    sleepy_root, nuke_dir = _sleepy_gizmo_root(), _nuke_install_dir()
    seen, items = set(), []
    for folder in nuke.pluginPath():
        if not os.path.isdir(folder):
            continue
        try:
            files = sorted(os.listdir(folder))
        except OSError:
            continue
        nf = _norm(folder)
        if sleepy_root and nf.startswith(sleepy_root):
            source, category = 'pg', os.path.basename(folder.rstrip('/\\'))
        elif nuke_dir and nf.startswith(nuke_dir):
            source, category = 'nuke', V_NUKE
        else:
            source, category = 'other', os.path.basename(folder.rstrip('/\\')) or folder
        for f in files:
            if not f.lower().endswith('.gizmo'):
                continue
            name = f[:-6]
            if name in seen:          # first one on the plugin path wins, like Nuke
                continue
            seen.add(name)
            path = os.path.join(folder, f)
            item = {'name': name, 'path': path, 'folder': folder, 'source': source, 'category': category}
            item.update(read_info(path) if source != 'nuke' else {'version': '', 'summary': '', 'inputs': []})
            items.append(item)
    return items


def usage():
    """{class name: [full node names]} for the open script, including inside groups."""
    out = {}
    for n in nuke.allNodes(recurseGroups=True):
        out.setdefault(n.Class(), []).append(n.fullName())
    return out


# ---------------------------------------------------------------------- swap / bake
def _same(a, b):
    return a is not None and b is not None and a.fullName() == b.fullName()


def _parent_of(node):
    full = node.fullName()
    return nuke.toNode('.'.join(full.split('.')[:-1])) if '.' in full else nuke.root()


def _rewire(old, new):
    """Give `new` the inputs, outputs and position of `old`."""
    for i in range(old.inputs()):
        if i < new.maxInputs():
            new.setInput(i, old.input(i))
    for dep in old.dependent(nuke.INPUTS | nuke.HIDDEN_INPUTS, False):
        for i in range(dep.inputs()):
            if _same(dep.input(i), old):
                dep.setInput(i, new)
    new.setXYpos(old.xpos(), old.ypos())


def _copy_knobs(old, new):
    copied, lost = 0, []
    for name, k in old.knobs().items():
        if name in SKIP_KNOBS or k.Class() in SKIP_CLASSES:
            continue
        try:
            if not k.notDefault():
                continue
        except Exception:
            pass
        if name not in new.knobs():
            lost.append(name)
            continue
        try:
            new[name].fromScript(k.toScript())
            copied += 1
        except Exception:
            lost.append(name)
    return copied, lost


def _finish_replace(old, new):
    name = old.name()
    _rewire(old, new)
    nuke.delete(old)
    try:
        new.setName(name)
    except Exception:
        pass
    return new


def swap(nodes, new_class):
    """Replace each node with a new `new_class` node. Returns a text report."""
    report = []
    undo = nuke.Undo()
    undo.begin('Swap gizmos to %s' % new_class)
    try:
        for old in nodes:
            with _parent_of(old):
                for s in nuke.selectedNodes():
                    s.setSelected(False)
                new = nuke.createNode(new_class, inpanel=False)
                copied, lost = _copy_knobs(old, new)
                old_name = old.fullName()
                _finish_replace(old, new)
                line = '%s -> %s: %d knob values kept' % (old_name, new_class, copied)
                if lost:
                    line += '; not on the new gizmo: ' + ', '.join(sorted(lost))
                report.append(line)
    finally:
        undo.end()
    return '\n'.join(report)


def bake(nodes):
    """Turn gizmo instances into equivalent Group nodes."""
    report = []
    undo = nuke.Undo()
    undo.begin('Bake gizmos to Groups')
    try:
        for old in nodes:
            if not hasattr(old, 'makeGroup'):
                continue
            with _parent_of(old):
                for s in nuke.selectedNodes():
                    s.setSelected(False)
                old_name, cls = old.fullName(), old.Class()
                group = old.makeGroup()
                _finish_replace(old, group)
                report.append('%s (%s) -> Group' % (old_name, cls))
    finally:
        undo.end()
    return '\n'.join(report)


# ---------------------------------------------------------------------- UI helpers
def _exec(obj, *args):
    run = getattr(obj, 'exec_', None) or getattr(obj, 'exec')
    return run(*args)


def _section(text):
    lab = QtWidgets.QLabel(text.upper())
    lab.setStyleSheet('color: #8c8c8c; font-size: 10px; font-weight: bold; letter-spacing: 1px; padding-top: 10px;')
    return lab


def _primary(button):
    button.setStyleSheet('QPushButton { font-weight: bold; padding: 5px 14px; }')
    return button


class GizmoManager(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(GizmoManager, self).__init__(parent)
        self.setWindowTitle(PANEL_TITLE)
        global _instance
        _instance = self
        self.items, self.used = [], {}
        self._build()
        self.reload()

    # ------------------------------------------------------------ layout
    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        top = QtWidgets.QHBoxLayout()
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText('Search gizmos, descriptions and inputs...')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refill)
        self.search.returnPressed.connect(self.create)
        top.addWidget(self.search, 1)
        script_btn = QtWidgets.QToolButton()
        script_btn.setText('Script  ')
        script_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu = QtWidgets.QMenu(script_btn)
        menu.addAction('Bake all Sleepy gizmos in this script to Groups...', lambda: self.bake_all(sleepy_only=True))
        menu.addAction('Bake ALL gizmos in this script to Groups...', lambda: self.bake_all(sleepy_only=False))
        script_btn.setMenu(menu)
        top.addWidget(script_btn)
        refresh = QtWidgets.QToolButton()
        refresh.setText('Refresh')
        refresh.clicked.connect(self.reload)
        top.addWidget(refresh)
        root.addLayout(top)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        root.addWidget(split, 1)

        # left: views
        self.views = QtWidgets.QListWidget()
        self.views.setMinimumWidth(150)
        self.views.setMaximumWidth(230)
        self.views.currentItemChanged.connect(self.refill)
        split.addWidget(self.views)

        # middle: gizmo list
        self.table = QtWidgets.QTreeWidget()
        self.table.setHeaderLabels(['Gizmo', 'Used', 'Version'])
        self.table.setRootIsDecorated(False)
        self.table.setUniformRowHeights(True)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.table.header().setStretchLastSection(False)
        self.table.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.table.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.table.header().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.table.currentItemChanged.connect(self.show_details)
        self.table.itemDoubleClicked.connect(lambda *a: self.create())
        split.addWidget(self.table)

        # right: details + actions
        side = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(side)
        sl.setContentsMargins(10, 0, 0, 0)
        self.d_title = QtWidgets.QLabel()
        f = self.d_title.font()
        f.setPointSize(f.pointSize() + 4)
        f.setBold(True)
        self.d_title.setFont(f)
        sl.addWidget(self.d_title)
        self.d_meta = QtWidgets.QLabel()
        self.d_meta.setStyleSheet('color: #a0a0a0;')
        sl.addWidget(self.d_meta)
        self.d_summary = QtWidgets.QLabel()
        self.d_summary.setWordWrap(True)
        self.d_summary.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        sl.addWidget(self.d_summary)
        self.d_inputs = QtWidgets.QLabel()
        self.d_inputs.setWordWrap(True)
        self.d_inputs.setTextFormat(QtCore.Qt.RichText)
        sl.addWidget(self.d_inputs)
        self.d_path = QtWidgets.QLabel()
        self.d_path.setStyleSheet('color: #7a7a7a; font-size: 10px;')
        self.d_path.setWordWrap(True)
        sl.addWidget(self.d_path)
        row = QtWidgets.QHBoxLayout()
        self.b_create = _primary(QtWidgets.QPushButton('Create'))
        self.b_create.clicked.connect(self.create)
        row.addWidget(self.b_create)
        self.b_folder = QtWidgets.QPushButton('Show in folder')
        self.b_folder.clicked.connect(self.show_folder)
        row.addWidget(self.b_folder)
        row.addStretch(1)
        sl.addLayout(row)

        self.inst_label = _section('In this script')
        sl.addWidget(self.inst_label)
        self.inst = QtWidgets.QListWidget()
        self.inst.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.inst.setMaximumHeight(150)
        self.inst.itemSelectionChanged.connect(self._update_actions)
        self.inst.itemDoubleClicked.connect(lambda *a: self.select_instances(zoom=True))
        sl.addWidget(self.inst)
        row = QtWidgets.QHBoxLayout()
        self.b_select = QtWidgets.QPushButton('Select in Node Graph')
        self.b_select.clicked.connect(lambda: self.select_instances(zoom=False))
        row.addWidget(self.b_select)
        self.b_zoom = QtWidgets.QPushButton('Zoom to')
        self.b_zoom.clicked.connect(lambda: self.select_instances(zoom=True))
        row.addWidget(self.b_zoom)
        row.addStretch(1)
        sl.addLayout(row)

        sl.addWidget(_section('Replace'))
        self.applies = QtWidgets.QLabel()
        self.applies.setStyleSheet('color: #a0a0a0;')
        sl.addWidget(self.applies)
        row = QtWidgets.QHBoxLayout()
        self.target = QtWidgets.QComboBox()
        self.target.setEditable(True)
        self.target.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.target.lineEdit().setPlaceholderText('Swap to gizmo...')
        self.target.currentTextChanged.connect(self._update_actions)
        row.addWidget(self.target, 1)
        self.b_swap = QtWidgets.QPushButton('Swap')
        self.b_swap.setToolTip('Replace with the chosen gizmo. Connections, position, name and matching '
                               'knob values are kept. Undoable.')
        self.b_swap.clicked.connect(self.swap_selected)
        row.addWidget(self.b_swap)
        sl.addLayout(row)
        self.b_bake = QtWidgets.QPushButton('Bake to Group')
        self.b_bake.setToolTip('Turn the instances into plain Groups so the script no longer needs the '
                               'gizmo file. Undoable.')
        self.b_bake.clicked.connect(self.bake_selected)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.b_bake)
        row.addStretch(1)
        sl.addLayout(row)
        sl.addStretch(1)
        side.setMinimumWidth(300)
        split.addWidget(side)
        split.setStretchFactor(1, 2)
        split.setStretchFactor(2, 3)
        split.setSizes([170, 300, 380])

    # ------------------------------------------------------------ data
    def reload(self):
        cur_view = self.view()
        cur_gizmo = self.current()['name'] if self.current() else None
        self.items = scan()
        self.used = usage()
        self.views.blockSignals(True)
        self.views.clear()
        pg = [i for i in self.items if i['source'] == 'pg']
        cats = sorted(set(i['category'] for i in pg),
                      key=lambda c: (CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else 99, c.lower()))
        used_n = sum(1 for i in self.items if self.used.get(i['name']))
        entries = [(V_ALL_SLEEPY, len(pg), True), (V_USED, used_n, True)]
        entries += [(c, sum(1 for i in pg if i['category'] == c), False) for c in cats]
        entries += [(V_NUKE, sum(1 for i in self.items if i['source'] == 'nuke'), True),
                    (V_OTHER, sum(1 for i in self.items if i['source'] == 'other'), True)]
        for name, n, bold in entries:
            if name == V_OTHER and not n:
                continue
            it = QtWidgets.QListWidgetItem(('%s  (%d)' % (name, n)) if bold else ('    %s  (%d)' % (name, n)))
            it.setData(QtCore.Qt.UserRole, name)
            if bold:
                fnt = it.font()
                fnt.setBold(True)
                it.setFont(fnt)
            self.views.addItem(it)
            if name == (cur_view or V_ALL_SLEEPY):
                self.views.setCurrentItem(it)
        if self.views.currentItem() is None:
            self.views.setCurrentRow(0)
        self.views.blockSignals(False)
        names = [i['name'] for i in sorted(self.items, key=lambda i: (i['source'] != 'pg', i['name'].lower()))]
        self.target.blockSignals(True)
        self.target.clear()
        self.target.addItems(names)
        self.target.setCurrentIndex(-1)
        self.target.blockSignals(False)
        self.refill(select=cur_gizmo)

    def view(self):
        it = self.views.currentItem()
        return it.data(QtCore.Qt.UserRole) if it else None

    def visible_items(self):
        v, words = self.view() or V_ALL_SLEEPY, self.search.text().lower().split()
        out = []
        for i in self.items:
            if v == V_ALL_SLEEPY and i['source'] != 'pg':
                continue
            if v == V_USED and not self.used.get(i['name']):
                continue
            if v == V_NUKE and i['source'] != 'nuke':
                continue
            if v == V_OTHER and i['source'] != 'other':
                continue
            if v not in (V_ALL_SLEEPY, V_USED, V_NUKE, V_OTHER) and not (i['source'] == 'pg' and i['category'] == v):
                continue
            text = ' '.join([i['name'], i['category'], i['summary']] + [a + ' ' + b for a, b in i['inputs']]).lower()
            if all(w in text for w in words):
                out.append(i)
        return out

    def refill(self, *args, **kw):
        select = kw.get('select') or (self.current()['name'] if self.current() else None)
        self.table.blockSignals(True)
        self.table.clear()
        bold = QtGui.QFont()
        bold.setBold(True)
        for i in self.visible_items():
            n = len(self.used.get(i['name'], []))
            it = QtWidgets.QTreeWidgetItem([i['name'], str(n) if n else '', i['version']])
            it.setData(0, QtCore.Qt.UserRole, i)
            it.setToolTip(0, i['summary'] or i['path'])
            if n:
                it.setFont(0, bold)
                it.setForeground(1, QtGui.QBrush(QtGui.QColor(ACCENT)))
            self.table.addTopLevelItem(it)
            if i['name'] == select:
                self.table.setCurrentItem(it)
        if self.table.currentItem() is None and self.table.topLevelItemCount():
            self.table.setCurrentItem(self.table.topLevelItem(0))
        self.table.blockSignals(False)
        self.show_details()

    def current(self):
        it = self.table.currentItem() if hasattr(self, 'table') else None
        return it.data(0, QtCore.Qt.UserRole) if it else None

    # ------------------------------------------------------------ details
    def show_details(self, *args):
        g = self.current()
        for w in (self.b_create, self.b_folder):
            w.setEnabled(g is not None)
        self.inst.clear()
        if g is None:
            self.d_title.setText('Nothing here' if self.items else 'No gizmos found')
            self.d_meta.setText('')
            self.d_summary.setText('Try another view or search.' if self.items else
                                   'No .gizmo files were found on the plugin path.')
            self.d_inputs.setText('')
            self.d_path.setText('')
            self.inst_label.setText('IN THIS SCRIPT')
            self._update_actions()
            return
        self.d_title.setText(g['name'])
        where = {'pg': 'Sleepy tools / %s' % g['category'], 'nuke': 'Nuke built-in',
                 'other': 'Other folder: %s' % g['category']}[g['source']]
        self.d_meta.setText('  \u00b7  '.join(x for x in (where, g['version']) if x))
        self.d_summary.setText(g['summary'] or '')
        if g['inputs']:
            rows = ''.join('<tr><td style="padding-right:10px"><b>%s</b></td><td>%s</td></tr>'
                           % (html.escape(a), html.escape(b)) for a, b in g['inputs'])
            self.d_inputs.setText('<span style="color:#8c8c8c">Inputs</span><table>%s</table>' % rows)
        else:
            self.d_inputs.setText('')
        self.d_path.setText(g['path'])
        self.d_path.setToolTip(g['path'])
        names = self.used.get(g['name'], [])
        self.inst_label.setText('IN THIS SCRIPT  (%d)' % len(names))
        for full in names:
            self.inst.addItem(full)
        if not names:
            it = QtWidgets.QListWidgetItem('Not used in this script')
            it.setFlags(QtCore.Qt.NoItemFlags)
            self.inst.addItem(it)
        self._update_actions()

    def chosen_nodes(self):
        g = self.current()
        if g is None:
            return []
        names = [it.text() for it in self.inst.selectedItems()] or list(self.used.get(g['name'], []))
        return [n for n in (nuke.toNode(x) for x in names) if n is not None]

    def _update_actions(self, *args):
        g = self.current()
        total = len(self.used.get(g['name'], [])) if g else 0
        picked = len([i for i in self.inst.selectedItems() if i.flags() & QtCore.Qt.ItemIsSelectable])
        has = total > 0
        for w in (self.b_select, self.b_zoom, self.b_bake, self.target):
            w.setEnabled(has)
        target = self.target.currentText().strip()
        self.b_swap.setEnabled(has and bool(target) and g is not None and target != g['name'])
        if not has:
            self.applies.setText('Nothing to replace: this gizmo is not used in the script.')
        elif picked:
            self.applies.setText('Applies to the %d selected instance%s.' % (picked, '' if picked == 1 else 's'))
        else:
            self.applies.setText('Applies to all %d instance%s (select some above to limit it).'
                                 % (total, '' if total == 1 else 's'))

    # ------------------------------------------------------------ actions
    def create(self):
        g = self.current()
        if g:
            try:
                nuke.createNode(g['name'])
            except Exception as err:
                nuke.message('Could not create %s:\n%s' % (g['name'], err))

    def show_folder(self):
        g = self.current()
        if g:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(g['folder']))

    def select_instances(self, zoom=False):
        nodes = [n for n in self.chosen_nodes() if '.' not in n.fullName()]
        for s in nuke.selectedNodes():
            s.setSelected(False)
        for n in nodes:
            n.setSelected(True)
        if zoom and nodes:
            n = nodes[0]
            nuke.zoom(max(nuke.zoom(), 0.6), [n.xpos() + n.screenWidth() / 2, n.ypos() + n.screenHeight() / 2])
        elif not nodes and self.chosen_nodes():
            nuke.message('These instances are inside Groups; open the Group to see them.')

    def swap_selected(self):
        target = self.target.currentText().strip()
        nodes = self.chosen_nodes()
        if not target or not nodes:
            return
        if target not in [i['name'] for i in self.items] and not nuke.ask(
                '"%s" is not a gizmo on the plugin path. Try anyway?' % target):
            return
        if not nuke.ask('Swap %d node%s to %s?\n\nConnections, position, name and matching knob values are kept. '
                        'You can undo this.' % (len(nodes), '' if len(nodes) == 1 else 's', target)):
            return
        try:
            report = swap(nodes, target)
        except Exception as err:
            nuke.message('Swap failed: %s' % err)
            return
        self.reload()
        nuke.message(report or 'Nothing was swapped.')

    def bake_selected(self):
        nodes = self.chosen_nodes()
        if nodes and nuke.ask('Bake %d node%s to Groups? You can undo this.'
                              % (len(nodes), '' if len(nodes) == 1 else 's')):
            nuke.message(bake(nodes) or 'Nothing was baked.')
            self.reload()

    def bake_all(self, sleepy_only=True):
        names = set(i['name'] for i in self.items if (i['source'] == 'pg' or not sleepy_only))
        nodes = [n for n in nuke.allNodes(recurseGroups=True) if hasattr(n, 'makeGroup') and n.Class() in names]
        if not nodes:
            nuke.message('No %sgizmos in this script.' % ('Sleepy ' if sleepy_only else ''))
            return
        if nuke.ask('Bake all %d %sgizmo instance%s in this script to Groups?\n\n'
                    'The script will no longer need the gizmo files. Save a copy first.'
                    % (len(nodes), 'Sleepy ' if sleepy_only else '', '' if len(nodes) == 1 else 's')):
            nuke.message(bake(nodes))
            self.reload()


# ---------------------------------------------------------------------- install
_instance = None


def _alive(widget):
    try:
        widget.isVisible()
        return True
    except RuntimeError:      # Qt object already deleted (tab was closed)
        return False


def show():
    """Open as a tab docked next to the Properties panel (or bring the open tab to the front)."""
    global _instance
    if _instance is not None and _alive(_instance) and _instance.isVisible():
        _instance.reload()
        _focus_tab(_instance)
        _instance.search.setFocus()
        return _instance
    import nukescripts
    # Self-importing widget string: the panel is saved in .nk layouts as a
    # PyCustom_Knob command that Nuke re-evaluates on script load, when this
    # module has not been imported into the interpreter namespace yet.
    panel = nukescripts.panels.registerWidgetAsPanel("__import__('sleepy_gizmo_manager').GizmoManager", PANEL_TITLE, PANEL_ID, True)
    pane = nuke.getPaneFor('Properties.1') or nuke.getPaneFor('DAG.1')
    if pane is not None:
        panel.addToPane(pane)
    else:
        panel.addToPane()
    return panel


def _focus_tab(widget):
    """Raise the tab that holds the widget inside its pane."""
    w = widget
    while w is not None:
        parent = w.parentWidget()
        if isinstance(parent, QtWidgets.QStackedWidget):
            parent.setCurrentWidget(w)
            tabs = parent.parentWidget()
            if isinstance(tabs, QtWidgets.QTabWidget):
                tabs.setCurrentWidget(w)
        w = parent


_installed = False


def install(menu='SleepyTools'):
    """Register the panel (Windows > Custom) and add Nuke > SleepyTools > Gizmo Manager (opens as a tab)."""
    global _installed
    if _installed:
        return
    _installed = True
    try:
        import nukescripts
        nukescripts.panels.registerWidgetAsPanel("__import__('sleepy_gizmo_manager').GizmoManager", PANEL_TITLE, PANEL_ID)
    except Exception:
        pass
    nuke.menu('Nuke').addMenu(menu).addCommand('Gizmo Manager', 'import sleepy_gizmo_manager; sleepy_gizmo_manager.show()')
