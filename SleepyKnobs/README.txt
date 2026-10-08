Sleepy Knobs
======================

1. Copy this SleepyKnobs folder into your .nuke folder.
2. Add this line to ~/.nuke/init.py:
     nuke.pluginAddPath('./SleepyKnobs')
3. Restart Nuke. Then:
     Right-click any number knob (translate, size, mix, ...) > Sleepy Knob Expressions…
     Right-click a knob with an expression > Sleepy Bake expression to keys
     SleepyTools > Knob Expression Lab   (opens it for the selected node)

The orange line in the preview is the result, the grey line the current value.
With "Add slider knobs" ticked, the settings become sliders on a Sleepy Anim tab of the node.
Bake to keys turns the expression into keyframes and removes the sliders.
The preview's noise is close to Nuke's but not identical; the curve shape matches.
