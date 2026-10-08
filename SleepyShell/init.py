# Sleepy Shell - Nuke runs this file automatically when the folder is a
# plugin path. Path setup only; nothing that can fail Nuke startup.
import os
import sys

try:
    _here = os.path.dirname(os.path.abspath(__file__))
    _parent = os.path.dirname(_here)
    for _path in (_here, _parent):
        if _path not in sys.path:
            sys.path.append(_path.replace("\\", "/"))
except Exception:
    pass
