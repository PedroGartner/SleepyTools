# Sleepy tools - init.py (runs in GUI and render/terminal sessions)
# Install: copy the SleepyTools folder into ~/.nuke and add this line to ~/.nuke/init.py:
#     nuke.pluginAddPath('./SleepyTools')
import os

import nuke


def _sleepy_tools_root():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:  # older Nuke versions run init.py without __file__
        for p in nuke.pluginPath():
            if os.path.isfile(os.path.join(p, 'python', 'sleepy_tools.py')):
                return p
    return None


_root = _sleepy_tools_root()
if _root:
    nuke.pluginAddPath(os.path.join(_root, 'python').replace('\\', '/'))
    import sleepy_tools
    sleepy_tools.add_plugin_paths()
else:
    nuke.tprint('Sleepy tools: could not find the SleepyTools folder')
