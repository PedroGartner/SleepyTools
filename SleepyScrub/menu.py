# Sleepy tools - Nuke runs this file automatically for every plugin folder.
# Each tool switches itself on when imported.
import nuke

for _tool in ("sleepy_scrub", "sleepy_node_info"):
    try:
        __import__(_tool)
    except Exception as _exc:
        nuke.tprint("Sleepy: couldn't load %s: %s" % (_tool, _exc))
        try:
            import SleepyCore
            SleepyCore.log_exception("load %s" % _tool)
        except Exception:
            pass
