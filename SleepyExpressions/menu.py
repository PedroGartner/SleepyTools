# Sleepy Expressions: Nuke runs this file automatically because this folder is on the plugin path.
import traceback
import nuke

try:
    import sleepy_expressions
    sleepy_expressions.install()
except Exception:
    msg = "Sleepy Expressions failed to load:\n" + traceback.format_exc()
    print(msg)
    nuke.tprint(msg)
    try:
        import SleepyCore
        SleepyCore.log_exception("load sleepy_expressions")
    except Exception:
        pass
