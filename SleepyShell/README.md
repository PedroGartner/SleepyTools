# Sleepy Shell

A project manager for Nuke work: browse projects and shots, and launch Nuke on the right script.
It runs as a dockable Nuke panel and as a standalone window that you can open before Nuke starts.

![Sleepy Shell](SleepyShell.png)

## Variants

| Entry file | Panel title | Purpose |
|---|---|---|
| `sleepy_shell.py` | Sleepy Project Manager | The main Project Manager. |
| `sleepy_shell_production.py` | Project Manager - Production | The "Production" variant of the interface. |
| `sleepy_shell_nuke.py` | Project Manager - Nuke | The "Nuke" variant of the interface. |

Each variant is loaded on its own. If one fails to load, the others still do. To stop a variant
from loading, delete its `sleepy_shell*.py` entry file.

## Installation (inside Nuke)

1. Copy the `SleepyShell` **and** `SleepyCore` folders into your `.nuke` folder. Sleepy Shell requires `SleepyCore`.
2. Add these lines to `~/.nuke/init.py`:

   ```python
   nuke.pluginAddPath('./SleepyCore')
   nuke.pluginAddPath('./SleepyShell')
   ```

3. Restart Nuke. Open it from `Nuke > SleepyTools > Project Manager`
   (`Open Project Manager` for the docked panel, `Open Floating Window` for a window).

## Standalone

With a Python that has PySide6 (or PySide2) installed, and the `SleepyCore` folder next to `SleepyShell`:

```bash
python standalone.py
```

On Windows you can use `SleepyShell.bat`. Edit the `PYTHON` line at the top to point at your Python.

## Integrations

Sleepy Shell uses `SleepySnapshots` and `SleepyQueue` through their public APIs when they are installed.
Neither is required.

## Settings

Preferences, recent projects and session times are stored under `%LOCALAPPDATA%\SleepyTools\`.

## Development

Tests are in `tests/` (`python -m pytest tests`). `tools/make_test_projects.py` builds a fake project
portfolio for checking the layout. It writes to `~/SleepyTestProjects` unless you pass a folder.

See `CHANGES.md` for the history of the interface.
