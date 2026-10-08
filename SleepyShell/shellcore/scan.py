"""Project and shot discovery.

The filesystem is the database. This module derives the portfolio from
disk:

- A *project* is a folder directly under a watched root that either has
  ``project.json`` (managed) or contains shot folders (discovered).
- A *shot* is a folder with ``shot.json`` (managed) or a ``comp``
  subfolder holding ``.nk`` scripts (discovered).
- Grouping folders (``shots``, episodes, days...) are transparent
  containers: the scanner walks through them up to a bounded depth.

Scanning never raises for a scanned path: unreadable/offline roots come
back with an error string and everything else keeps working. A JSON
cache with a TTL keeps startup fast on big portfolios.
"""

import os
import time

from shellcore.schema import load_json, PROJECT_FILE, SHOT_FILE
from shellcore import prefs as prefs_mod

CACHE_FILE = os.path.join(prefs_mod.PREFS_FOLDER, "sleepy_shell_cache.json")

_MAX_CONTAINER_DEPTH = 3
_SKIP_DIRS = {".snapshots", "__pycache__", "renders", "deliverables", "plates", "ref"}


# ---------------------------------------------------------------------------
# model helpers
# ---------------------------------------------------------------------------

def _is_hidden(name):
    return name.startswith(".") or name.startswith("_")


def _dir_entries(path):
    """List (name, fullpath) of subdirectories; [] on any error."""
    try:
        return [(e.name, os.path.join(path, e.name))
                for e in os.scandir(path) if e.is_dir()]
    except OSError:
        return []


def _dir_files(path):
    try:
        return [e.name for e in os.scandir(path) if e.is_file()]
    except OSError:
        return []


def _subdir(path, name):
    candidate = os.path.join(path, name)
    return candidate if os.path.isdir(candidate) else None


def looks_like_shot(path):
    """A folder is a shot when it has shot.json or a comp folder with .nk files."""
    if os.path.isfile(os.path.join(path, SHOT_FILE)):
        return True
    comp = _subdir(path, "comp")
    if comp:
        for name in _dir_files(comp):
            if name.lower().endswith(".nk"):
                return True
    return False


def _find_shot_dirs(project_path, depth=0):
    """Shot folders under a project, walking through transparent containers."""
    found = []
    if depth > _MAX_CONTAINER_DEPTH:
        return found
    for name, child in _dir_entries(project_path):
        if _is_hidden(name):
            continue
        if looks_like_shot(child):
            found.append(child)
        elif name.lower() in ("shots", "sequences") or not _has_shot_markers(child):
            # containers: walk through unless the folder clearly holds
            # something else entirely (has none of our markers anywhere nearby)
            found.extend(_find_shot_dirs(child, depth + 1))
    return found


def _has_shot_markers(path):
    """Quick test to avoid walking deep into unrelated trees."""
    if os.path.isfile(os.path.join(path, SHOT_FILE)) or _subdir(path, "comp"):
        return True
    shots = _subdir(path, "shots")
    return shots is not None


def _comp_dir(shot_path):
    comp = _subdir(shot_path, "comp")
    if comp:
        return comp
    # tolerate scripts directly in the shot folder (discovered, client style)
    for name in _dir_files(shot_path):
        if name.lower().endswith(".nk"):
            return shot_path
    return comp  # may be None


# ---------------------------------------------------------------------------
# projects / shots
# ---------------------------------------------------------------------------

def find_projects(root):
    """Scan one watched root. Returns (projects, error)."""
    projects = []
    try:
        entries = _dir_entries(root)
    except OSError as exc:
        return [], str(exc)
    for name, path in entries:
        if _is_hidden(name):
            continue
        config_file = os.path.join(path, PROJECT_FILE)
        managed = os.path.isfile(config_file)
        has_shots = bool(_find_shot_dirs(path, depth=0)) or _has_shot_markers(path)
        if not managed and not has_shots:
            continue
        config, error = (load_json(config_file), None) if managed else (None, None)
        projects.append({
            "path": path,
            "name": name,
            "managed": managed,
            "client": (config or {}).get("client", "") if isinstance(config, dict) else "",
            "color": (config or {}).get("color") if isinstance(config, dict) else None,
            "error": error,
            "root": root,
        })
    projects.sort(key=lambda p: p["name"].lower())
    return projects, None


def find_shots(project_path):
    """Scan one project for shots. Returns a list of shot dicts (never raises)."""
    shots = []
    for shot_path in _find_shot_dirs(project_path):
        managed = os.path.isfile(os.path.join(shot_path, SHOT_FILE))
        comp = _comp_dir(shot_path)
        shots.append({
            "path": shot_path,
            "name": os.path.basename(shot_path),
            "project_path": project_path,
            "managed": managed,
            "comp_dir": comp,
            "error": None,
        })
    shots.sort(key=lambda s: s["name"].lower())
    return shots


def scan_roots(roots):
    """Scan every watched root. Returns (projects, root_states).

    root_states maps root -> "ok" | error string, so the UI can flag
    offline or unreadable roots without failing the whole scan.
    """
    projects = []
    states = {}
    seen = set()
    for root in roots:
        root = os.path.normpath(root)
        if root.lower() in seen:
            continue
        seen.add(root.lower())
        if not os.path.isdir(root):
            states[root] = "offline"
            continue
        found, error = find_projects(root)
        if error:
            states[root] = error
        else:
            states[root] = "ok"
        projects.extend(found)
    return projects, states


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------

def load_cache():
    from shellcore.schema import load_json as _lj
    data = _lj(CACHE_FILE)
    return data if isinstance(data, dict) else {}


def save_cache(cache):
    from shellcore.schema import save_json_atomic
    save_json_atomic(CACHE_FILE, cache)


def cached_scan(prefs, force=False):
    """Scan with a TTL cache. Returns (projects, states, from_cache)."""
    ttl = int(prefs.get("cache_ttl_seconds", 120) or 0)
    roots = list(prefs.get("watched_roots", []))
    key = "|".join(sorted(os.path.normpath(r).lower() for r in roots))
    cache = load_cache()
    entry = cache.get(key)
    if not force and entry and isinstance(entry.get("projects"), list):
        age = time.time() - float(entry.get("scanned_at", 0))
        if age < ttl:
            return entry["projects"], entry.get("states", {}), True
    projects, states = scan_roots(roots)
    cache[key] = {"scanned_at": time.time(), "projects": projects, "states": states}
    try:
        save_cache(cache)
    except OSError:
        pass
    return projects, states, False


def scan_shots(project_path):
    """Shots of one project, always read live (cheap, needed for accuracy)."""
    return find_shots(project_path)


def invalidate_cache():
    try:
        if os.path.isfile(CACHE_FILE):
            os.remove(CACHE_FILE)
    except OSError:
        pass
