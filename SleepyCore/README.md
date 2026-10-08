# SleepyCore

Shared infrastructure for the Sleepy Nuke tool suite.

## Modules

| Module | Purpose |
|--------|---------|
| `qt.py` | Version-aware Qt binding selection + PySide2/6 compatibility helpers |
| `reload.py` | Stale-module detection and reload protection |
| `settings.py` | Shared JSON settings per tool |
| `crashlog.py` | Uncaught exception logging |
| `themes.py` | Shared dark theme palette + QSS |
| `menus.py` | Get-or-create helpers for the single `Nuke > SleepyTools` menu |
| `selftest.py` | Headless verification harness |

## Installation

Drop the `SleepyCore` folder into `~/.nuke` and add to `~/.nuke/init.py`:

```python
nuke.pluginAddPath('./SleepyCore')
```

Or let a tool's `menu.py` import it (tools carry an inline fallback so they work standalone).

## Usage

### Qt Binding (all tools)

```python
# Preferred: use the core if available
try:
    from SleepyCore import qt as _core_qt
    QtCore, QtGui, QtWidgets = _core_qt.QtCore, _core_qt.QtGui, _core_qt.QtWidgets
except Exception:
    # Inline fallback (same logic)
    import sys
    try:
        import nuke
        major = int(nuke.NUKE_VERSION_MAJOR)
    except Exception:
        major = None
    if major is not None and major >= 16:
        from PySide6 import QtCore, QtGui, QtWidgets
    else:
        from PySide2 import QtCore, QtGui, QtWidgets
```

### Reload Protection (multi-file tools)

```python
from SleepyCore.reload import refresh_modules

def install():
    refresh_modules(["my_tool", "my_tool.submodule"])
    # ... rest of install
```

### Reload-Safe Install Guard (all tools)

```python
def install():
    import nuke
    if getattr(nuke, "_my_tool_installed", False):
        return
    nuke._my_tool_installed = True
    # ... rest of install
```

### Crash Logging

```python
from SleepyCore.crashlog import log_exception

try:
    risky_operation()
except Exception:
    log_exception("context description")
```

### Theme

```python
from SleepyCore.themes import apply, widget_style, button_style

apply(my_widget)  # applies dark palette
my_widget.setStyleSheet(widget_style())  # for QSS
```

### Menus

```python
from SleepyCore.menus import get_sleepy_menu, add_sleepy_command

m = get_sleepy_menu()  # Nuke > SleepyTools
add_sleepy_command("My Tool", "my_tool.show()")
```

## Self-Test

Run inside Nuke to verify the install:

```bash
python -c "import SleepyCore.selftest; SleepyCore.selftest.run()"
```

Or from Nuke's Script Editor:

```python
import SleepyCore.selftest
SleepyCore.selftest.run()
```

## Design Principles

1. **No hard dependencies** - every tool carries an inline fallback so it works standalone.
2. **Version-aware Qt** - Nuke version checked BEFORE any Qt import; never both bindings.
3. **Reload-safe** - install guards on `nuke` module survive module reloads; `refresh_modules()` repairs stale classes.
4. **Fail-safe** - all imports wrapped; tools degrade gracefully if core unavailable.
4. **Zero new failure modes** - core introduces no new crash vectors.