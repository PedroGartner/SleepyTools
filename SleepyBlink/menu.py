# Sleepy Blink: Nuke runs this file automatically because this folder is on the plugin path.
import traceback
import nuke

try:
    import sleepy_blink
    sleepy_blink.install()
except Exception:
    msg = "Sleepy Blink failed to load:\n" + traceback.format_exc()
    print(msg)
    nuke.tprint(msg)
    try:
        import SleepyCore
        SleepyCore.log_exception("load sleepy_blink")
    except Exception:
        pass
