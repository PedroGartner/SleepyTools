"""SleepyCore - shared infrastructure for the Sleepy Nuke tool suite.

Provides:
- qt: version-aware Qt binding + PySide2/6 helpers
- reload: stale-module detection and reload protection
- settings: shared JSON settings per tool
- crashlog: uncaught exception logging
- themes: shared dark theme palette + QSS
- menus: get-or-create helpers for the single Nuke > SleepyTools menu
- selftest: headless verification harness
"""

import importlib

from .reload import stale_modules, refresh_modules, iter_tool_modules, load_modules

# Re-exported because tools log via SleepyCore.log_exception(...) on the
# package itself (menu.py except blocks), not via the submodule.
from .crashlog import log_exception, install_excepthook

# Qt is deliberately NOT imported here: crash logging, reload protection and
# settings must work without initializing a Qt binding. The binding loads on
# first access of SleepyCore.qt or any Qt re-export below (PEP 562, needs
# Python 3.7+); SleepyCore.qt picks PySide2/PySide6 from the running Nuke
# version BEFORE importing either binding.
_QT_NAMES = frozenset([
    "QtCore", "QtGui", "QtWidgets", "QT6", "Signal", "QShortcut",
    "QAction", "QOpenGLWidget", "qt_exec", "event_pos", "modifier_state",
    "font_families", "format_font_family", "set_format_font_family",
    "SignalBlocker", "parse_shortcut", "binding_name",
])


def __getattr__(name):
    if name == "qt" or name in _QT_NAMES:
        module = importlib.import_module(".qt", __name__)
        globals()["qt"] = module
        return module if name == "qt" else getattr(module, name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


__all__ = [
    "QtCore", "QtGui", "QtWidgets", "QT6", "Signal", "QShortcut",
    "QAction", "QOpenGLWidget", "qt_exec", "event_pos", "modifier_state",
    "font_families", "format_font_family", "set_format_font_family",
    "SignalBlocker", "parse_shortcut", "binding_name",
    "stale_modules", "refresh_modules", "iter_tool_modules", "load_modules",
    "log_exception", "install_excepthook",
]