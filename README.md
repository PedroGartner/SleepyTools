<h1 align="center">SleepyTools</h1>

<p align="center">
  Tools, panels and gizmos for Foundry Nuke / NukeX.<br>
  Queue renders, keep track of versions, catch script problems, and speed up the small things.
</p>

<p align="center">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue">
  <img alt="Nuke 13+" src="https://img.shields.io/badge/Nuke-13%2B-yellow">
  <img alt="PySide2 / PySide6" src="https://img.shields.io/badge/Qt-PySide2%20%7C%20PySide6-green">
</p>

SleepyTools is a set of independent tools for compositing work in Nuke. Each one lives in its own
folder, installs on its own, and adds itself under a single **`Nuke > SleepyTools`** menu. Install
the ones you want and ignore the rest.

**Jump to:** [The tools](#the-tools) · [In detail](#in-detail) · [Requirements](#requirements) · [Installation](#installation) · [Finding things in Nuke](#finding-things-in-nuke) · [License](#license)

---

## The tools

| Tool | Runs as | What it is for |
|---|---|---|
| [**Sleepy Queue**](SleepyQueue) | Standalone app + Nuke menu | A local render queue with resume, crash recovery and a live frame preview. |
| [**Sleepy Shell**](SleepyShell) | Standalone window + Nuke panel | A project manager: browse projects and shots, launch Nuke on the right script. |
| [**Sleepy Snapshots**](SleepySnapshots) | Nuke panel + standalone | A timeline of script versions and snapshots, with compare, revert and node history. |
| [**Sleepy Text**](SleepyText) | Floating window or docked panel | A text and code editor inside Nuke, with notes, tasks, Python and shot checks. |
| [**Sleepy Doctor**](SleepyDoctor) | Floating window or docked panel | Scans a script for problems, explains each one and profiles node timings. |
| [**Sleepy Expressions**](SleepyExpressions) | Docked panel | Expression Lab: 161 ready-made Expression recipes. |
| [**Sleepy Blink**](SleepyBlink) | Docked panel | BlinkScript Lab: 16 ready-made BlinkScript kernels. |
| [**Sleepy Library**](SleepyLibrary) | Docked panel | Save node setups with a thumbnail and tags, and insert them again. |
| [**Sleepy Knobs**](SleepyKnobs) | Right-click menu + window | Ready-made animation expressions for any number knob, with a live curve preview. |
| [**Sleepy Scrub**](SleepyScrub) | Always on in the GUI | Flame-style value scrubbing for numeric fields, plus a hover info card on nodes. |
| [**SleepyTools gizmo pack**](SleepyTools) | Nodes toolbar | 21 gizmos in six categories, a Command Palette and a Gizmo Manager. |
| [**SleepyCore**](SleepyCore) | Library | Shared code: Qt 5/6 compatibility, settings, crash log, theme and menu helpers. |

---

## In detail

### Sleepy Queue: a render queue on your own machine

<img src="SleepyQueue/SleepyQueue.png" alt="Sleepy Queue" width="760">

Rendering from the Nuke GUI blocks your session, and queuing several comps overnight by hand is
fragile. Sleepy Queue renders in the background with Nuke's command line, keeps track of every
frame, and deals with the usual problems. No render farm needed.

- **Send from Nuke or add scripts yourself.** One job per Write node, with priority, dependencies,
  scheduled start and chunking.
- **Renders the version you queued.** Every job renders a snapshot of the script as it was when you
  queued it, even if you keep editing.
- **Resumes after a crash or stop.** It renders only the frames missing on disk, retries briefly
  locked files, and asks before overwriting existing frames.
- **Live monitoring.** Progress, ETA, a built-in frame preview with a scrub slider, a check for
  missing and zero-byte frames, and a CPU / RAM / GPU monitor.
- **Gentle on a workstation.** Render Power and a "Render While I Work" mode, resource protection,
  optional simultaneous renders, and shutdown or sleep when the queue finishes.

[Full documentation](SleepyQueue/README.md)

### Sleepy Shell: a project manager

<img src="SleepyShell/SleepyShell.png" alt="Sleepy Shell" width="760">

Browse your projects and shots, then open Nuke on the right script. It runs as a standalone window
you can open before Nuke starts, and as a docked panel inside Nuke.

- **Derived from disk.** Versions, snapshots, renders and last-opened times are read from your
  folders. Shell only stores status, notes, due date and tags per shot.
- **Home and Board views**, search across shots, notes, tags and node types, and tools to create
  projects or adopt shots it finds.
- **Works with the other tools.** It uses Sleepy Snapshots and Sleepy Queue when they are installed.
  Neither is required.
- **Three interface variants:** the main Project Manager, a Production view and a Nuke-style view.

Requires [SleepyCore](SleepyCore). [Full documentation](SleepyShell/README.md)

### Sleepy Snapshots: every version of a comp on one timeline

<img src="SleepySnapshots/SleepySnapshots.png" alt="Sleepy Snapshots" width="760">

Go back to any point, see exactly what changed between two states, and pull single nodes out of
the past without versioning up.

- **One timeline** of sibling `_v###` scripts, snapshots and Nuke's autosave. Group by version,
  day or script, and filter or search notes, tags and users.
- **Snapshots on a hotkey, a timer, every save and before every restore.** They are stored
  compressed, identical states are kept once, and starred or manual ones are never cleaned up.
- **Compare any two states,** or an entry against the live script, unsaved changes included. It
  lists added, removed, renamed and changed nodes, each knob's old and new value, and connection
  changes.
- **Revert, paste or apply.** Write older values back onto a node, or paste a node from either side.
- **Node History** follows one node across every saved state.
- **Also runs outside Nuke:** `python -m snapbrowser your_script.nk`.

[Full documentation](SleepySnapshots/README.md)

### Sleepy Text: an editor that lives in Nuke

<img src="SleepyText/SleepyText.png" alt="Sleepy Text" width="760">

For compositors and technical artists who want to write notes, edit code and manage scripts
without leaving Nuke.

- **Run Python from the editor.** `Ctrl+Enter` runs the selection or line, tracebacks are
  clickable, and a console and problem checker are built in.
- **Notes that travel with the work.** Node notes stored inside the node, script notes, shared
  shot notes and rich `.tnote` files with formatting, images and Viewer captures.
- **Task lists** in plain text, with people and due dates, collected into a TODO panel.
- **Nuke script tools.** Script outline, node search, editing a Group as `.nk` text, and a viewer
  for the callbacks registered in your session.
- **Shot checks.** Detects newer plate versions, and checks Write nodes before they are sent to
  Sleepy Queue.
- **A full editor.** Syntax highlighting for Python, `.nk`, JSON, Markdown and more, folding,
  multi-cursor, find in files, snippets, templates, split view and three themes.
- **Safe by design.** Crash recovery, local file history, external-change detection and optional
  autosave.

[Full documentation](SleepyText/README.md)

### Sleepy Doctor: find what is wrong with a script

<img src="SleepyDoctor/SleepyDoctor.png" alt="Sleepy Doctor" width="760">

Checks a Nuke script for problems and explains each one: what is wrong, why it matters and how to
fix it, with a link to the Foundry documentation.

- **Quick scan** for files, renders, expressions, connections, colour and structure. **Full scan**
  adds performance: bounding boxes traced back to where they start, big scales, upscales, large
  filters, heavy nodes and channel load. You can also scan only a selection, everything upstream,
  or the nodes between two points.
- **Fixes are explicit, undoable and confirmed.** Findings you accept can be ignored, and that is
  stored in the script so it travels with it.
- **Tabs** for Overview, Findings, Performance, Colour, Inspect and Profile.
- **Profile** uses Nuke's own performance timers per node: top 10, Viewer path only, baseline
  compare, and disable-and-compare.

Nothing is scanned until you press a button. [Full documentation](SleepyDoctor/README.txt)

### Sleepy Expressions: a library of Expression recipes

<img src="SleepyExpressions/SleepyExpressions.png" alt="Sleepy Expressions" width="760">

Pick a recipe and it creates an Expression node, or a small Group when it needs neighbouring pixels
(normals from a 2D image, fake relighting), connected to the selected node. Values become knobs:
sliders, colour pickers and viewer handles.

- **161 recipes in 11 categories:** Normals & relight, Light & glow, Distortion STMaps, Colour,
  Keying & despill, Alpha & mattes, QC & fixes, CG & depth, Generators, Time & animation, and
  Look & overlays.
- **Searchable,** and every recipe is also in the menu, so Tab search finds it too.
- **Save your own** Expression nodes as recipes.

[Folder](SleepyExpressions)

### Sleepy Blink: a library of BlinkScript kernels

<img src="SleepyBlink/SleepyBlink.png" alt="Sleepy Blink" width="760">

BlinkScript can read neighbouring pixels, which plain Expression nodes can't. Pick a kernel, set its
starting values and press Create: you get a BlinkScript node with the kernel compiled and the values
set.

- **16 kernels:** Sobel normals, normal curvature, depth ambient occlusion, bilateral, median and
  Kuwahara filters, bokeh, directional and zoom blur, clarity, chromatic aberration, edge extend,
  stroke from alpha, round erode / dilate, firefly killer, and NaN / inf fixing.
- **Plain `.blink` files** in the `kernels` folder, if you want to load or edit one by hand.
- **Save your own** BlinkScript nodes as kernels.

[Folder](SleepyBlink)

### Sleepy Library: your own setup library

Select nodes, give the setup a name, category, tags and description, and save it with a thumbnail
rendered from the Viewer. Search it later, including the node types inside each setup, and
double-click to insert it connected to your selection.

- **Plain folders** (`setup.nk`, `meta.json`, `thumb.png`), so a library can live on a shared drive.
- **Shared libraries** through the panel's Libraries dialog, or the `SLEEPY_SETUP_LIBRARY`
  environment variable for a whole team.
- **Your Nuke ToolSets** show up too, read-only.

[Folder](SleepyLibrary)

### Sleepy Knobs: ready-made animation for any knob

Right-click any number knob and pick **Sleepy Knob Expressions** to put a ready-made expression on it.

- **Wiggle, jitter, sine, square and saw waves, bounce, spring, ease, flicker,** constant speed,
  random per node, quantise and clamp, plus key-based ones: loop, ping-pong, time offset, stepped
  (on twos), smoothing and speed change.
- **Live curve preview,** and optional slider knobs on a *Sleepy Anim* tab so you can keep tweaking.
- **Bake to keys** when you are done, which is safe for the farm and for exporting.

[Folder](SleepyKnobs)

### Sleepy Scrub: Flame-style value handling

Two small tools that change how Nuke's Properties panel and Node Graph feel. Nodes, connections and
colours are never touched.

- **Scrub:** press and drag on a numeric field to change it live. `Shift` is coarse, `Ctrl` is
  fine and `Alt` snaps. Double-click resets, and one drag is one undo step.
- **Calculator:** click a field and type `0.75`, `2*3+1`, or a relative edit such as `+5` or `*2`.
- **Node Info:** a hover card on nodes with resolution, format, frame range, layers and file,
  `F1` to `F4` to view Front, Back, Matte or Result, and a side-by-side comparison of two nodes.

[Folder](SleepyScrub)

### The gizmo pack, Command Palette and Gizmo Manager

<img src="SleepyTools/SleepyTools.png" alt="Gizmo Manager" width="760">

21 gizmos in six categories (Keying, Grain, Cleanup, Lens, CG and QC), all built to the same
standard: a Controls tab with a header, an About tab with the inputs, a `mix` knob on image tools,
tile colours by category, and a node graph laid out so you can read it.

- **Command Palette** (`Ctrl+Alt+Space`): fuzzy search for commands, nodes, gizmos and nodes in
  your script.
- **Gizmo Manager:** see where each gizmo is used, swap one for another, or bake a gizmo to a Group.
- **Previews** of every gizmo's node graph in `docs/previews`.

[Full documentation](SleepyTools/docs/README.md) · [Changelog](SleepyTools/docs/CHANGELOG.md)

### SleepyCore: the shared layer

Picks the right Qt binding for the running Nuke (PySide2 for Nuke 13-15, PySide6 for 16 and later),
and provides settings, crash logging, a shared theme and menu helpers. Most tools carry an inline
fallback and work without it, but installing it is recommended. Sleepy Shell requires it.

[Folder](SleepyCore)

---

## Requirements

- **Foundry Nuke or NukeX.** The code is written for Nuke 13-15 (PySide2 / Qt 5) and Nuke 16 and
  later (PySide6 / Qt 6), and picks the binding that matches the running Nuke. Not every tool has
  been tested on every Nuke version.
- A few tools have extra requirements:

| Tool | Needs |
|---|---|
| Sleepy Queue | A separate Python 3.9+ with `PySide6`. `psutil` is recommended, and `OpenEXR` + `numpy` are optional (EXR preview). |
| Sleepy Shell | `SleepyCore`. The standalone window needs a Python with PySide6 (or PySide2). |
| Sleepy Snapshots | Nuke 16 or later (PySide6), with PySide2 as a fallback. The standalone mode needs a Python with PySide6, such as the one that ships with Nuke. |
| Sleepy Blink | BlinkScript. If creating a node fails, your Nuke licence may only allow it in NukeX. |
| Gizmo pack | NukeX for SleepyGrain's synthetic mode (F_ReGrain). Everything else uses standard Nuke nodes. |

Developed mainly on Windows.

---

## Installation

1. Copy the folders you want into your `.nuke` folder (`~/.nuke`).
2. Add one line per tool to `~/.nuke/init.py`:

   ```python
   nuke.pluginAddPath('./SleepyCore')
   nuke.pluginAddPath('./SleepyDoctor')
   nuke.pluginAddPath('./SleepyKnobs')
   nuke.pluginAddPath('./SleepyTools')    # the gizmo pack
   ```

3. Restart Nuke and open the **`Nuke > SleepyTools`** menu.

Notes:

- **SleepyShell requires `SleepyCore`.** Install both. The other tools use `SleepyCore` when it is
  present and work without it, but installing it is recommended.
- **SleepyQueue and SleepyText** have their own install steps. See their READMEs.
- Every tool folder has its own README with details.

### Updating

Replace the tool folder with the new version and restart Nuke. Settings are stored outside the tool
folders, so they are kept.

---

## Finding things in Nuke

Panels can also be opened from **Pane menu > Windows > Custom**.

| You want | Where it is |
|---|---|
| Send Write nodes to the render queue | `Nuke > SleepyTools > Sleepy Queue` (`Ctrl+Alt+B` sends the selected Writes) |
| Project manager | `Nuke > SleepyTools > Project Manager` |
| Snapshots | `Nuke > SleepyTools > Snapshots` (`Ctrl+Alt+S` takes a snapshot) |
| The text editor | `Nuke > SleepyTools > Sleepy Text`, and `Sleepy Text Tools` for notes, plates and pre-render checks |
| Script checks | `Nuke > SleepyTools > Script Doctor` |
| Expression recipes | `Nuke > SleepyTools > Expression Lab`, or every recipe under `Expressions` and Tab search |
| BlinkScript kernels | `Nuke > SleepyTools > BlinkScript Lab`, or every kernel under `BlinkScripts` and Tab search |
| Setup library | `Nuke > SleepyTools > Setup Library`, and `Save selected to Setup Library…` |
| Knob expressions | Right-click a number knob, or `Nuke > SleepyTools > Knob Expression Lab` |
| Value scrubbing and node info | `Nuke > SleepyTools > Scrub Fields` and `Node Info` |
| Gizmos | Nodes toolbar > SleepyTools, one submenu per category |
| Command Palette and Gizmo Manager | `Nuke > SleepyTools` (`Ctrl+Alt+Space` opens the palette) |

---

## License

The code in this repository is released under the [MIT License](LICENSE), except
[SleepyText](SleepyText), which keeps its own BSD-style license in
[SleepyText/LICENSE](SleepyText/LICENSE).

## Disclaimer

SleepyTools is an independent project. It is not affiliated with or endorsed by
Foundry. Nuke and NukeX are trademarks of Foundry Visionmongers Ltd.
