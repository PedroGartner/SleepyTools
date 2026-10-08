"""Sleepy tools: paths and menus for the whole pack.

Folder layout (everything is found from this file's location):

    SleepyTools/
        init.py, menu.py          <- Nuke runs these
        gizmos/<Category>/*.gizmo <- one folder per category; each becomes Nodes > SleepyTools > Category
        python/                   <- Python tools (this file, command palette, gizmo manager)
        docs/                     <- README, changelog, node-graph previews

Add a gizmo by dropping it into a category folder (or a new folder); the menu picks it up on restart.
"""
import os

import nuke

__version__ = '3.0'
MENU = 'SleepyTools'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIZMO_ROOT = os.path.join(ROOT, 'gizmos')
DOCS = os.path.join(ROOT, 'docs')
# menu order; folders not listed here are added after these, alphabetically
CATEGORY_ORDER = ['Keying', 'Grain', 'Cleanup', 'Lens', 'CG', 'QC']


def categories():
    """[(name, folder)] in menu order."""
    if not os.path.isdir(GIZMO_ROOT):
        return []
    found = sorted(d for d in os.listdir(GIZMO_ROOT)
                   if os.path.isdir(os.path.join(GIZMO_ROOT, d)) and not d.startswith(('.', '_')))
    ordered = [c for c in CATEGORY_ORDER if c in found] + [c for c in found if c not in CATEGORY_ORDER]
    return [(c, os.path.join(GIZMO_ROOT, c)) for c in ordered]


def gizmos(folder):
    return sorted(f[:-6] for f in os.listdir(folder) if f.lower().endswith('.gizmo'))


def add_plugin_paths():
    """Called from init.py: make every category folder a plugin path."""
    for _, folder in categories():
        nuke.pluginAddPath(folder.replace('\\', '/'))


def build_node_menu():
    """Nodes toolbar > SleepyTools > Category > gizmo."""
    toolbar = nuke.menu('Nodes').addMenu(MENU)
    for cat, folder in categories():
        sub = toolbar.addMenu(cat)
        for name in gizmos(folder):
            sub.addCommand(name, "nuke.createNode('%s')" % name)


def open_docs():
    readme = os.path.join(DOCS, 'README.md')
    target = readme if os.path.isfile(readme) else ROOT
    try:
        from SleepyCore.qt import QtCore, QtGui
    except Exception:
        try:
            import nuke
            _major = int(nuke.NUKE_VERSION_MAJOR)
        except Exception:
            _major = None
        if _major is not None and _major >= 16:
            from PySide6 import QtCore, QtGui
        else:
            from PySide2 import QtCore, QtGui
    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(target))


def install():
    """Called from menu.py."""
    try:
        from SleepyCore.reload import refresh_modules
        refresh_modules(['sleepy_command_palette', 'sleepy_gizmo_manager'])
    except Exception:
        pass
    build_node_menu()
    m = nuke.menu('Nuke').addMenu(MENU)
    for module in ('sleepy_command_palette', 'sleepy_gizmo_manager'):
        try:
            __import__(module).install(menu=MENU)
        except Exception as err:   # one broken tool must not stop the others loading
            nuke.tprint('Sleepy tools: %s not loaded: %s' % (module, err))
    m.addMenu('Help').addCommand('Sleepy tools help', 'import sleepy_tools; sleepy_tools.open_docs()')
