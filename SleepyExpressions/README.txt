Sleepy Expressions
=================

1. Copy this whole SleepyExpressions folder into your .nuke folder:
     Windows: C:\Users\<you>\.nuke\SleepyExpressions
     Mac:     /Users/<you>/.nuke/SleepyExpressions
     Linux:   ~/.nuke/SleepyExpressions

2. Open ~/.nuke/init.py and add this line:
     nuke.pluginAddPath('./SleepyExpressions')

3. Restart Nuke. You get:
     SleepyTools > Expression Lab              (top menu bar, opens the panel)
     SleepyTools > Expressions > ...           (every recipe, also found with Tab)
     Pane menu > Windows > Custom > Sleepy Expressions

If nothing appears, look in the terminal / Script Editor output for
"Sleepy Expressions failed to load" and send the error.
