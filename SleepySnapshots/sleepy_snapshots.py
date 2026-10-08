"""Snapshot Browser entry point.

Import this file from menu.py (or drop the folder into an auto-installer that
imports its .py files). It makes the snapbrowser package importable and, in a
GUI session, registers the Snapshots menu, the dockable panel and the
callbacks. Errors are printed instead of stopping Nuke's startup.
"""

import os
import sys
import traceback

try:
    import nuke
except ImportError:
    nuke = None


def _find_tool_dir():
    """Folder that contains the snapbrowser package."""
    here = globals().get("__file__")
    candidates = []
    if here:
        candidates.append(os.path.dirname(os.path.abspath(here)))
    search = list(sys.path)
    if nuke is not None:
        try:
            search += list(nuke.pluginPath())
        except Exception:
            pass
    for base in search:
        if base:
            candidates.append(base)
            candidates.append(os.path.join(base, "SleepySnapshots"))
    for folder in candidates:
        if os.path.isfile(os.path.join(folder, "snapbrowser", "__init__.py")):
            return folder
    return None


def _load():
    folder = _find_tool_dir()
    if folder is None:
        print("[Snapshot Browser] Could not find the snapbrowser folder.")
        return
    if folder not in sys.path:
        sys.path.insert(0, folder)
    try:
        from SleepyCore.reload import refresh_modules
        refresh_modules(["snapbrowser"])
    except Exception:
        pass
    from snapbrowser import nuke_bridge

    nuke_bridge.install()


if nuke is not None and nuke.GUI:
    try:
        _load()
    except Exception:
        print("[Snapshot Browser] Failed to load:")
        traceback.print_exc()
