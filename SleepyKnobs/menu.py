# Sleepy Knobs: Nuke runs this file automatically because this folder is on the plugin path.
import traceback
import nuke

try:
    import sleepy_knobs
    sleepy_knobs.install()
except Exception:
    msg = "Sleepy Knobs failed to load:\n" + traceback.format_exc()
    print(msg)
    nuke.tprint(msg)
    try:
        import SleepyCore
        SleepyCore.log_exception("load sleepy_knobs")
    except Exception:
        pass
