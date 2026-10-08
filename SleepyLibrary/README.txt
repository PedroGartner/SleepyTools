Sleepy Library
================

1. Copy this SleepyLibrary folder into your .nuke folder.
2. Add this line to ~/.nuke/init.py:
     nuke.pluginAddPath('./SleepyLibrary')
3. Restart Nuke. You get:
     SleepyTools > Setup Library                       (the browser panel)
     SleepyTools > Save selected to Setup Library…     (also on the Node Graph right-click menu)
     Pane menu > Windows > Custom > Sleepy Library

Saving: select nodes, Save selected nodes…, give it a name, category, tags and a description.
The thumbnail is rendered from what the viewer shows on the current frame.

Using: search (names, tags, descriptions and the node types inside), double-click to insert.
It connects to the selected node, like Ctrl+V. Right-click a setup for more.

Sharing: each setup is a folder (setup.nk, meta.json, thumb.png). Your own library is
~/.nuke/sleepy_setup_library. Add a shared folder with "Libraries…" in the panel, or for a whole
team set the SLEEPY_SETUP_LIBRARY environment variable to one or more folders.
Your Nuke ToolSets appear too (read-only).
