# Sleepy Doctor: Nuke runs this file automatically because this folder is on the plugin path.
import traceback
import nuke

try:
    import sleepy_doctor
    sleepy_doctor.install()
except Exception:
    msg = "Sleepy Doctor failed to load:\n" + traceback.format_exc()
    print(msg)
    nuke.tprint(msg)
    try:
        import SleepyCore
        SleepyCore.log_exception("load sleepy_doctor")
    except Exception:
        pass
