"""Reload protection for tools that get reloaded by auto-installers.

The problem: Nuke tool loaders that re-execute every .py file in folder
order (or an importlib.reload() during development) leave a package in a
half-reloaded state. Module A is reloaded, so it holds NEW class objects,
while module B still holds the OLD versions of those classes. Any old
instance that then calls super(OldClass, self) - or any new code that
mixes old and new classes - dies with:

    TypeError: super(type, obj): obj must be an instance of type

The fix (proven in the Text Editor): detect modules that hold classes or
functions belonging to an older copy of another module, and reload them
until nobody sees a stale version any more. Detection instead of a fixed
load order makes it work no matter what order the loader chose.
"""

import importlib
import sys
import types

__all__ = ["stale_modules", "refresh_modules", "iter_tool_modules"]


def _matches(name, prefixes):
    if prefixes is None:
        return True
    if isinstance(prefixes, str):
        prefixes = (prefixes,)
    return any(name == p or name.startswith(p if p.endswith(".") else p + ".")
               or name.split(".")[0] == p for p in prefixes)


def iter_tool_modules(prefixes=None):
    """Loaded modules whose name starts with one of prefixes (top-level
    names match too: 'sleepy_tools' matches 'sleepy_tools' and 'sleepy_tools.x')."""
    found = []
    for name, module in list(sys.modules.items()):
        if module is None or not _matches(name, prefixes):
            continue
        found.append(module)
    return found


def stale_modules(prefixes=None):
    """Modules (within prefixes) that still hold classes or functions from
    an older copy of another module.

    Tool loaders that reload every .py file (in folder order) leave the
    package in that state: 'dialogs' keeps the HoverButton of the
    'widgets' module as it was before 'widgets' was reloaded.
    """
    stale = []
    tracked = set()
    for name, module in list(sys.modules.items()):
        if module is None or not _matches(name, prefixes):
            continue
        tracked.add(name)
    for name, module in list(sys.modules.items()):
        if module is None or not _matches(name, prefixes):
            continue
        for attr, value in list(vars(module).items()):
            if attr.startswith("__") or isinstance(value, types.ModuleType):
                continue
            source_name = getattr(value, "__module__", None)
            if not isinstance(source_name, str) or source_name == name:
                continue
            if not _matches(source_name, prefixes):
                continue
            if source_name not in tracked:
                continue
            if not isinstance(value, (type, types.FunctionType)):
                continue
            source = sys.modules.get(source_name)
            current = getattr(source, getattr(value, "__name__", attr), None) if source is not None else None
            if current is not None and current is not value and type(current) is type(value):
                stale.append(module)
                break
    return stale


def refresh_modules(prefixes=None, max_passes=12, verbose=False):
    """Reload stale modules until every module sees the current version
    of the others. Returns the number of reloads.

    prefixes: a module/package name, or a list of them. None refreshes
    every module Python currently holds - too broad for normal use, so
    tools pass their own names, e.g. refresh_modules(["sleepy_tools",
    "sleepy_command_palette", "sleepy_gizmo_manager"]).
    """
    reloads = 0
    for _ in range(max_passes):
        stale = stale_modules(prefixes)
        if not stale:
            break
        for module in stale:
            try:
                importlib.reload(module)
                reloads += 1
                if verbose:
                    print("[SleepyCore] refreshed stale module %s" % getattr(module, "__name__", module))
            except Exception as exc:
                if verbose:
                    print("[SleepyCore] could not refresh %s: %s" % (getattr(module, "__name__", module), exc))
    return reloads


def load_modules(names, verbose=False):
    """Import (or re-import cleanly) the named top-level modules after
    refreshing stale copies. Used by entry points so an auto-installer's
    out-of-order reload cannot leave mixed old/new classes behind:

        SleepyCore.reload.load_modules(["sleepy_scrub", "sleepy_node_info"])
    """
    refresh_modules(names, verbose=verbose)
    loaded = []
    for name in names:
        try:
            loaded.append(__import__(name))
        except Exception as exc:
            if verbose:
                print("[SleepyCore] %s could not be imported: %s" % (name, exc))
    return loaded