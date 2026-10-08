# Sleepy Shell - GUI sessions only.
# Loads the Project Manager variants. Each one is guarded: a missing or
# broken variant prints a note and the others still load. To stop a
# variant from loading, delete its sleepy_shell*.py entry file and it
# will be skipped on the next start.
import nuke

for _module in ("sleepy_shell", "sleepy_shell_production", "sleepy_shell_nuke"):
    try:
        __import__(_module)
    except Exception as _exc:
        nuke.tprint("Sleepy Shell: couldn't load {}: {}".format(_module, _exc))
        try:
            import SleepyCore
            SleepyCore.log_exception("load {}".format(_module))
        except Exception:
            pass
