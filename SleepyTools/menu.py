# Sleepy tools - menu.py (GUI sessions only)
# Builds Nodes > SleepyTools > <Category> from the gizmo folders, and Nuke > SleepyTools for the Python tools.
try:
    import sleepy_tools
    sleepy_tools.install()
except Exception as _err:
    import nuke
    nuke.tprint('Sleepy tools: menus not built: %s' % _err)
    try:
        import SleepyCore
        SleepyCore.log_exception("load sleepy_tools")
    except Exception:
        pass
