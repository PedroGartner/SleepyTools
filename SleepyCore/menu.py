"""SleepyCore menu.py - runs in GUI sessions only.

Adds a help entry under Nuke > SleepyTools > Help for the suite. Executed by Nuke
(and NukeShared) as a plugin file, outside any package context, so the
package is resolved via sys.path with absolute imports only.
"""

import os
import sys

try:
    _here = os.path.dirname(os.path.abspath(__file__))
    _parent = os.path.dirname(_here)
    for _path in (_parent, _here):
        if _path not in sys.path:
            sys.path.append(_path.replace("\\", "/"))
except Exception:
    _here = None

try:
    import nuke
    from SleepyCore.menus import add_sleepy_submenu

    def _open_help():
        if not _here:
            return
        try:
            from SleepyCore.qt import QtCore, QtGui
            readme = os.path.join(_here, "README.md")
            target = readme if os.path.isfile(readme) else _here
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(target))
        except Exception:
            pass

    _help_menu = add_sleepy_submenu("Help")
    if _help_menu is not None:
        _help_menu.addCommand("Sleepy tools help", _open_help)
    else:
        nuke.tprint("SleepyCore: could not build the Help submenu")

except Exception as _err:
    import nuke
    nuke.tprint('SleepyCore: menu not built: %s' % _err)
