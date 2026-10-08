# Sleepy Scrub

Two small tools that change how Nuke's Properties panel and Node Graph feel.
Nodes, connections and colours are never touched.

## Sleepy Scrub

Flame / Smoke-style value handling for Nuke's native numeric knob fields.

- **Scrub:** press and drag left or right on a numeric field to change the value live.
  `Shift` is coarse (x10), `Ctrl` is fine (x0.1), `Alt` snaps to a step.
- **Reset:** double-click a field that has been scrubbed before to reset its knob to the default.
  Fields driven by an expression are never scrubbed or reset.
- **Calculator:** click without dragging and type `0.75`, `2*3+1`, or a relative edit such as `+5`, `*2` or `/4`.
  Anything that is not plain arithmetic (for example a Nuke expression) is passed to Nuke untouched.
- One whole drag is one undo step. Pen tablets are supported (the cursor stays visible in pen mode).

Menu: `SleepyTools > Scrub Fields` (toggle, mouse / pen mode, snap step, and more).

## Sleepy Node Info

- A crosshair cursor inside Nuke.
- A hover card on nodes showing resolution, format, frame range, layers, file and cook time
  (cook time only while profiling is on).
- `F1` to `F4` view the Front, Back, Matte or Result of the selected node.
- `Alt+Shift+I` saves a numbered copy of the script next to it. `Alt+Shift+C` copies the hovered node's card as text.
- Select exactly two nodes for a side-by-side comparison.

Menu: `SleepyTools > Node Info`.

## Installation

1. Copy this `SleepyScrub` folder into your `.nuke` folder.
2. Add this line to `~/.nuke/init.py`:

   ```python
   nuke.pluginAddPath('./SleepyScrub')
   ```

3. Restart Nuke. Both tools switch themselves on in a Nuke GUI session. Render and terminal sessions are skipped.

`SleepyCore` is optional. When it is installed, the tools use its Qt compatibility layer.

## Settings

Menu choices are remembered in per-user JSON files under `%LOCALAPPDATA%\SleepyTools\`
(`sleepy_scrub.json` and `sleepy_node_info.json`).
