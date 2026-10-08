"""Version 3 (Nuke-inspired) Nuke entry point.

Same install pattern as Version 1's entry: safe to call twice, flag set
only after success, no existing tool imports this module.
"""

import os
import sys

try:
    import nuke
except ImportError:
    nuke = None

PANEL_ID = "com.sleepytools.SleepyShellNukePanel"
PANEL_TITLE = "Project Manager — Nuke"
PANEL_WIDGET = "__import__('shellui_nuke.nuke_pane', fromlist=['nuke_pane']).NukePaneWidget"


def _ensure_paths():
    here = globals().get("__file__")
    if not here:
        return False
    folder = os.path.dirname(os.path.abspath(here))
    parent = os.path.dirname(folder)
    for path in (folder, parent):
        if path not in sys.path:
            sys.path.append(path.replace("\\", "/"))
    return True


def show_panel():
    import nukescripts
    if nuke.getPaneFor(PANEL_ID) is not None:
        return
    panel = nukescripts.panels.registerWidgetAsPanel(PANEL_WIDGET, PANEL_TITLE, PANEL_ID, True)
    panel.addToPane(nuke.getPaneFor("Properties.1"))


def _add_suite_submenu(name):
    """Get-or-create a submenu under the suite home menu, whatever flavor
    of SleepyCore is deployed (add_sleepy_submenu / home 'SleepyTools', or
    add_submenu / home 'Sleepy'). Last resort: find-or-create the home
    menu directly on the menu bar."""
    try:
        from SleepyCore.menus import add_sleepy_submenu
        menu = add_sleepy_submenu(name)
        if menu is not None:
            return menu
    except Exception:
        pass
    try:
        from SleepyCore.menus import add_submenu as add_home_submenu
        menu = add_home_submenu(name)
        if menu is not None:
            return menu
    except Exception:
        pass
    try:
        bar = nuke.menu("Nuke")
        if bar is None:
            return None
        root = bar.findItem("SleepyTools")
        if root is None:
            root = bar.addMenu("SleepyTools")
        menu = root.findItem(name)
        if menu is None:
            menu = root.addMenu(name)
        return menu
    except Exception:
        return None


def install():
    if nuke is None or not nuke.GUI:
        return
    if getattr(nuke, "_sleepy_shell_nuke_installed", False):
        return
    if not _ensure_paths():
        nuke.tprint("Project Manager (Nuke): could not locate the tool folder")
        return
    try:
        from shellui.session import get_session
        get_session()
        menu = _add_suite_submenu("Project Manager (Nuke)")
        if menu is not None:
            module = "__import__('sleepy_shell_nuke', fromlist=['x'])."
            menu.addCommand("Open Nuke Pane", module + "show_panel()")
        import nukescripts
        nukescripts.panels.registerWidgetAsPanel(PANEL_WIDGET, PANEL_TITLE, PANEL_ID)
        nuke._sleepy_shell_nuke_installed = True
        nuke.tprint("Project Manager (Nuke): installed")
    except Exception as exc:
        import traceback
        nuke.tprint("Project Manager (Nuke): install failed: {}".format(exc))
        nuke.tprint(traceback.format_exc())
        try:
            import SleepyCore
            SleepyCore.log_exception("Project Manager (Nuke) install")
        except Exception:
            pass


if nuke is not None and nuke.GUI:
    install()
