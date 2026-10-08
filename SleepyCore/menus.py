"""Menu helpers for the suite.

Provides get-or-create helpers for the single Nuke > SleepyTools home menu.
Tools should use these instead of calling nuke.menu() directly.
"""

from SleepyCore.qt import QtWidgets


def get_sleepy_menu():
    """Get or create the Nuke > SleepyTools home menu."""
    try:
        import nuke
        bar = nuke.menu("Nuke")
        if bar is None:
            return None
        m = bar.findItem("SleepyTools")
        if m is None:
            m = bar.addMenu("SleepyTools")
        return m
    except Exception:
        return None


def add_sleepy_command(label, command, shortcut=None):
    """Add a command to the Nuke > SleepyTools home menu."""
    m = get_sleepy_menu()
    if m is None:
        return
    try:
        if shortcut:
            m.addCommand(label, command, shortcut)
        else:
            m.addCommand(label, command)
    except Exception:
        pass


def add_sleepy_submenu(name):
    """Get or create a submenu under Nuke > SleepyTools."""
    m = get_sleepy_menu()
    if m is None:
        return None
    try:
        sub = m.findItem(name)
        if sub is None:
            sub = m.addMenu(name)
        return sub
    except Exception:
        return None