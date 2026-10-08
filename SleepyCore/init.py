"""SleepyCore init.py - runs in GUI and render/terminal sessions.

Nuke (and NukeShared) execute this file as a plugin file, outside any
package context: relative imports can never work here. The SleepyCore
package lives one level up from this file, so that parent folder is put
on sys.path first, then the crash logger excepthook is installed via
the package.
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

# Install the crash logger excepthook (absolute import: works in plugin context)
try:
    import SleepyCore
    SleepyCore.install_excepthook()
except Exception:
    pass

# Make the folder itself available as a plugin path (kept from earlier versions)
try:
    if _here:
        import nuke
        _plugin = _here.replace("\\", "/")
        if _plugin not in nuke.pluginPath():
            nuke.pluginAddPath(_plugin)
except Exception:
    pass
