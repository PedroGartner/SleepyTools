# Sleepy Library: Nuke runs this file automatically because this folder is on the plugin path.
import traceback
import nuke

try:
    import sleepy_library
    # To add a shortcut for saving, e.g.: sleepy_library.install(save_shortcut="ctrl+alt+shift+s")
    sleepy_library.install()
except Exception:
    msg = "Sleepy Library failed to load:\n" + traceback.format_exc()
    print(msg)
    nuke.tprint(msg)
    try:
        import SleepyCore
        SleepyCore.log_exception("load sleepy_library")
    except Exception:
        pass
