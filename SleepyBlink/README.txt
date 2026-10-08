Sleepy Blink
==================

1. Copy this SleepyBlink folder into your .nuke folder.
2. Add this line to ~/.nuke/init.py:
     nuke.pluginAddPath('./SleepyBlink')
3. Restart Nuke. You get:
     SleepyTools > BlinkScript Lab        (opens the panel)
     SleepyTools > BlinkScripts > ...     (every kernel, also found with Tab)
     Pane menu > Windows > Custom > Sleepy Blink

The kernels folder has every kernel as a plain .blink file, in case you want to load
or edit one by hand. The tool itself doesn't need them.

Kernels use the CPU or GPU like any BlinkScript node ("Use GPU if available").
If creating a node fails, your Nuke licence may only allow BlinkScript in NukeX.
