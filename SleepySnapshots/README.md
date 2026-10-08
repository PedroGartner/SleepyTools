# Snapshot Browser for Nuke

A dockable panel that shows every version of the current comp and a timeline of
lightweight snapshots. You can go back to any point, see exactly what changed
between two states, and pull single nodes out of the past without versioning up.

![Sleepy Snapshots](SleepySnapshots.png)

## Features

### Timeline
- **Versions and snapshots in one list.** Finds sibling `_v###` scripts and
  lists them with snapshots and Nuke's autosave, newest first.
- **Grouping.** No grouping, by version, by day or by script.
- **Folder scope.** Switch from *This script* to *Whole folder* to see every
  script family next to the current one (comp, precomps, roto...).
- **Script stats.** Node count and file size for every entry. The size turns
  orange when a script suddenly grows (over 50% and over 200 KB since the
  previous entry), which often means something heavy was pasted in.
- **Filters and search.** Filter by versions, snapshots, manual, renders or
  starred, and search across notes, tags and user.

### Snapshots
- **Take a snapshot at any time.** Uses a hotkey (default `Ctrl+Alt+S`), with an
  optional note and a thumbnail of the active viewer.
- **Automatic snapshots.** Taken on a timer (only when the script changed), on
  every save and before every restore. Identical states are stored once.
- **Retention.** Keeps the newest N snapshots of each automatic kind. Manual and
  starred snapshots are never removed.
- **Keep This Snapshot.** Turns an automatic snapshot into a manual one with a
  note, so it is never cleaned up.
- **Notes, tags and stars** on every snapshot.

### Compare
- **Compare With Current Script.** Lists what changed between any entry and the
  script as it is right now, unsaved changes included. On the current version
  this becomes *Compare With Unsaved Changes*.
- **Compare Selected.** Select any two entries to compare them.
- The compare view lists nodes that were added, removed, renamed or changed,
  with every changed knob's old and new value. Position and selection changes
  are ignored by default.
- **Connection changes** are listed too, e.g. *Merge1 input 1 (A): Grade1 →
  Grade2*. Connections are read by replaying the script's `set`/`push` stack.
- **Renamed nodes** are recognised when a removed and an added node have the
  same class, group and knob values. Nodes with no knobs of their own (such as
  Dots) must also be in the same place or have the same inputs.
- **Select In Node Graph.** Selects and frames the changed nodes. Nodes inside a
  group also select the group.
- **Revert.** Writes the older values back onto the live node, for a whole node
  or just the rows you pick. Knobs that were at their default are reset, inputs
  are reconnected and renames are undone. It is one undo step per node.
- **Paste Older Node / Paste Newer Node.** Pastes a node (or a whole group) from
  either side, disconnected, into the right group.
- **Compare Thumbnails.** Shows a wipe or side-by-side view of two snapshot
  thumbnails.

### Node history
- Shows every saved state in which one node changed: when it first appeared,
  every knob and connection change, and when it was removed or came back. It
  covers versions, snapshots, the autosave and, in Nuke, the live script.
- Open it with **Snapshots > Node History (Selected Node)**, *More > Node
  History* in the panel, or the **Node History** button in the compare view.
- **Apply This State.** Sets the live node's knobs and connections to how they
  were at that point. If the node no longer exists, it is pasted instead.
- **Paste This Version.** Pastes the node as it was at that point, disconnected.

### Restore and versions
- **Restore Into Current Script.** Loads a snapshot, version or autosave into
  the open script, keeping its file name. The current state is snapshotted
  first, and nothing touches the disk until you save.
- **Save As Next Version.** Turns any entry into the next free version of the
  shot.

### Housekeeping
- **Clean Up Snapshots.** Deletes snapshots older than N days, optionally
  including manual ones. Starred snapshots are always kept, and it shows how
  much space will be freed.
- **Compressed snapshots.** New snapshots are stored as gzip-compressed
  `.nk.gz` files, usually 5–10× smaller. Everything reads them transparently.
  *More > Compress Old Snapshots* converts snapshots made before this was on.
- **Disk usage** of the snapshot folder is shown in the status bar.
- **Work History.** Estimates your sessions on the shot from snapshot and save
  times: date, start, end and duration, plus a total.

### Standalone mode
Browse, compare, annotate, snapshot, see node history and clean up without
opening Nuke. Features that need a live script (restore, revert, apply state,
paste, select) are Nuke-only.

```
python -m snapbrowser path/to/sh010_comp_v012.nk
```

On Windows, run `SleepySnapshots.bat`. It uses the Python that ships with Nuke,
which already has PySide6; edit the path inside if Nuke is installed elsewhere.
You can also drop a `.nk` file on the window or use *File > Open Script*.

## Install

Copy the `SnapshotBrowser` folder next to your other tools. If the folder is
added to Nuke's plugin path, its `menu.py` loads the tool. To load it by hand,
add this to your own `menu.py`:

```python
import sys
sys.path.append("/path/to/SleepySnapshots")
import sleepy_snapshots
```

This adds **Nuke > Snapshots** and a **Snapshot Browser** entry in the Pane menu.

## Where snapshots live

```
shots/sh010/comp/
  sh010_comp_v012.nk
  .snapshots/
    sh010_comp/
      sh010_comp_20260930_145012_a1b2.nk.gz
      sh010_comp_20260930_145012_a1b2.json
      sh010_comp_20260930_145012_a1b2.jpg
```

The folder is named after the script without its version token, so snapshots
from every version of a shot appear in the same timeline.

## Snapshot format (`snapshot/1`)

Each snapshot is a `.nk` file plus a JSON file. Any tool can write snapshots that
show up in the browser. A render manager, for example, can store the exact
script it rendered, with render details:

```python
from snapbrowser import core

core.create_snapshot(
    script_path, saved_copy_path, kind=core.KIND_RENDER, note="Final",
    extra={"render": {
        "frame_range": "1001-1100",
        "write_node": "Write1",
        "output": "C:/renders/sh010/sh010_comp_v012.####.exr",
        "status": "done",
    }},
)
```

Render snapshots show those details in the panel, with an *Open Render Folder*
button.

| Key | Meaning |
| --- | --- |
| `format` | Always `snapshot/1` |
| `id` | Timestamp plus a short random suffix |
| `kind` | `manual`, `auto`, `save`, `render` or `restore` |
| `created` | ISO 8601 time with offset |
| `note`, `tags`, `starred` | Editable in the panel |
| `script`, `thumbnail` | File names inside the snapshot folder (`.nk` or `.nk.gz`) |
| `compressed` | Whether the script is gzip-compressed |
| `hash` | SHA-1 of the `.nk`, used to skip duplicates |
| `size`, `nodes` | Uncompressed script size and node count |
| `source_script`, `source_version` | The script the snapshot was taken from |
| `frame`, `user`, `host`, `app` | Context at capture time |
| `render` | Optional: `frame_range`, `write_node`, `output`, `status` |

## Settings

Open the settings from *More > Settings*. They are stored in
`~/.nuke/snapshot_browser.json`; set `SNAPSHOT_BROWSER_HOME` to use another
folder. A hotkey change takes effect after restarting Nuke.

| Setting | Default |
| --- | --- |
| Auto snapshot interval | 10 min (0 turns it off) |
| Automatic snapshots kept per kind | 20 |
| Snapshot on save | On |
| Viewer thumbnails | On |
| Ask for a note | On |
| Store snapshots compressed | On |
| Hotkey | `ctrl+alt+s` |

## Limitations

- Connections are only compared when both scripts could be read cleanly. If a
  script's stack can't be replayed, only knobs are compared, and the compare
  view says so.
- A node that was renamed *and* changed shows up as removed plus added.
- Node history follows a node by its name. After a rename, its history
  continues under the new name.
- *Revert* skips user-knob definitions and class changes. Use *Paste Older
  Node* for those.

## Layout

```
SnapshotBrowser/
  menu.py                  loads the tool when the folder is a plugin path
  sleepy_snapshots.py      entry point, registers menus and callbacks
  SleepySnapshots.bat      standalone launcher (Windows)
  snapbrowser/
    core.py                versions, snapshots, metadata, history (no nuke import)
    nkparse.py             .nk reader, connections, node/knob diff (no nuke import)
    nuke_bridge.py         snapshot, thumbnail, restore, revert, paste, callbacks
    standalone.py          backend and window for use outside Nuke
    panel.py               the panel
    dialogs.py             compare, thumbnails, clean up, history, settings
    qt.py                  PySide6 / PySide2 imports
    __main__.py            python -m snapbrowser
```

## Requirements

Nuke 16 or later (PySide6). PySide2 is supported as a fallback.
