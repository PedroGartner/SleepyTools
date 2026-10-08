"""Sleepy Shell entry point.

Runs inside Nuke (imported by menu.py). Registers the Project Manager
menu (under the suite home menu) and the dockable panel. Safe to call
twice; the install flag is only set after registration succeeds so a
failed install can be retried. No existing tool imports this module,
and nothing here touches any other tool's registration.
"""

import os
import sys

try:
    import nuke
except ImportError:
    nuke = None

PANEL_ID = "com.sleepytools.SleepyShellPanel"
PANEL_TITLE = "Sleepy Project Manager"
PANEL_WIDGET = "__import__('shellui.nukepanel', fromlist=['nukepanel']).ShellPanel"


def _tool_dir():
    here = globals().get("__file__")
    if here:
        return os.path.dirname(os.path.abspath(here))
    return None


def _ensure_paths():
    folder = _tool_dir()
    if folder is None:
        return False
    parent = os.path.dirname(folder)
    for path in (folder, parent):
        if path not in sys.path:
            sys.path.append(path.replace("\\", "/"))
    return True


def show_panel():
    """Open the panel docked next to the Properties pane (idempotent)."""
    import nukescripts
    if nuke.getPaneFor(PANEL_ID) is not None:
        return
    panel = nukescripts.panels.registerWidgetAsPanel(PANEL_WIDGET, PANEL_TITLE, PANEL_ID, True)
    panel.addToPane(nuke.getPaneFor("Properties.1"))


def open_floating():
    """Open the panel as a floating window."""
    import nukescripts
    panel = nukescripts.panels.registerWidgetAsPanel(PANEL_WIDGET, PANEL_TITLE, PANEL_ID, True)
    try:
        panel.setFloating(True)
        panel.show()
    except Exception:
        panel.addToPane(nuke.getPaneFor("Properties.1"))


def _add_suite_submenu(name):
    """Get-or-create a submenu under the suite home menu, whatever flavor
    of SleepyCore is deployed. SleepyCore exposes add_sleepy_submenu()
    (home menu 'SleepyTools'); older cores expose add_submenu(). Last
    resort: find-or-create the home menu directly on the menu bar."""
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
    if getattr(nuke, "_sleepy_shell_installed", False):
        return
    if not _ensure_paths():
        nuke.tprint("Sleepy Shell: could not locate the tool folder")
        return
    try:
        from shellcore import scan as scan_mod
        scan_mod.invalidate_cache()  # a cache from an older run must never mask disk truth
        from shellui.session import get_session
        get_session()

        menu = _add_suite_submenu("Project Manager")
        if menu is not None:
            module = "__import__('sleepy_shell', fromlist=['sleepy_shell'])."
            menu.addCommand("Open Project Manager", module + "show_panel()")
            menu.addCommand("Open Floating Window", module + "open_floating()")
        import nukescripts
        nukescripts.panels.registerWidgetAsPanel(PANEL_WIDGET, PANEL_TITLE, PANEL_ID)
        # flag only after everything above succeeded
        nuke._sleepy_shell_installed = True
        nuke.tprint("Sleepy Shell: installed (Project Manager menu + pane)")
    except Exception as exc:
        import traceback
        nuke.tprint("Sleepy Shell: install failed: {}".format(exc))
        nuke.tprint(traceback.format_exc())
        try:
            import SleepyCore
            SleepyCore.log_exception("Sleepy Shell install")
        except Exception:
            pass


if nuke is not None and nuke.GUI:
    install()
