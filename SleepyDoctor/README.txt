Sleepy Doctor 2
==================

Install: copy this SleepyDoctor folder into .nuke (replace the old one) and keep this line
in ~/.nuke/init.py:
    nuke.pluginAddPath('./SleepyDoctor')

Open: SleepyTools > Script Doctor (opens the way you used it last), or
      SleepyTools > Script Doctor (window) / SleepyTools > Script Doctor (docked).
      The Dock / Float button in the tool switches between them; both show the same scan.

Scanning
  Quick scan   files, renders, expressions, connections, colour, structure (fast)
  Full scan    adds performance: bounding boxes grouped to where they start, scaling,
               upscales, large filters, heavy nodes, channel load
  Scan part    selected nodes, everything upstream of the selection, or between two nodes
Nothing is scanned until you press a button.

Tabs
  Overview     verdict, findings per category (click to filter), Final QC, compare scans, reports
  Findings     every finding with why it matters, a fix where one is safe, ignore, Foundry docs
  Performance  slow nodes, measured times first once you've profiled; select all, heat map
  Colour       Read colourspaces: filter, tick and change in one undo step
  Inspect      node inspector, where used, bbox sources, crop safety, bbox over time, channels,
               expression map, concatenation, merges, Read/Write dashboard, cleanup, classes,
               roto sizes, fonts. Results are clickable.
  Profile      Nuke's performance timers per node: top 10, Viewer path only, baseline compare,
               disable and compare.

Ignored findings are stored in the script, so they travel with it.
Settings: thresholds and which checks run.
