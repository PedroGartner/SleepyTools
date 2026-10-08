"""Global preferences for Sleepy Shell.

Stored in %LOCALAPPDATA%\\SleepyTools\\sleepy_shell_prefs.json (the same
folder the other Sleepy tools use for per-user persistence). Atomic
writes; unknown keys preserved; type-checked merge over defaults.
"""

import os

from shellcore.schema import load_json, save_json_atomic, normalize

PREFS_FOLDER = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SleepyTools")
PREFS_FILE = os.path.join(PREFS_FOLDER, "sleepy_shell_prefs.json")

PREFS_DEFAULTS = {
    "format": "sleepy-shell-prefs/1",
    # scanning
    "watched_roots": [],
    "cache_ttl_seconds": 120,
    # appearance
    "accent": "#f0a043",
    "theme_mode": "dark",       # "dark" | "light" | "nuke" (nuke = follow host)
    "density": "comfortable",   # "comfortable" | "compact"
    "font_size": 12,
    "ui_scale": 1.0,          # interface zoom (QT_SCALE_FACTOR), 1.0 = 100%
    # new shot rules
    "shot_pattern": "sh###",
    "script_pattern": "{shot}_comp_v###.nk",
    "folder_template": ["comp", "plates", "ref", "renders", "deliverables"],
    # launching (standalone)
    "nuke_executable": "",
    # board
    "view_mode": "list",        # "columns" | "list" | "gallery"
    "due_days": 7,
    # behaviour
    "show_on_launch": True,     # standalone: open the launcher (vs the Board)
    "resume_card": True,        # home: show the continue-where-you-left-off hero
    "stale_check": True,        # board: flag shots idle 14+ days
    "stale_days": 14,
    "show_delivered": True,
}


def prefs_path():
    return PREFS_FILE


def load():
    data = load_json(PREFS_FILE)
    prefs = normalize(data, PREFS_DEFAULTS)
    prefs["watched_roots"] = [r for r in prefs.get("watched_roots", []) if isinstance(r, str) and r.strip()]
    prefs["folder_template"] = [f for f in prefs.get("folder_template", []) if isinstance(f, str) and f.strip()]
    if not prefs["folder_template"]:
        prefs["folder_template"] = list(PREFS_DEFAULTS["folder_template"])
    return prefs


def save(prefs):
    data = normalize(prefs, PREFS_DEFAULTS)
    data["watched_roots"] = [r for r in data.get("watched_roots", [])
                             if isinstance(r, str) and r.strip()]
    data["folder_template"] = [f for f in data.get("folder_template", [])
                               if isinstance(f, str) and f.strip()]
    if not data["folder_template"]:
        data["folder_template"] = list(PREFS_DEFAULTS["folder_template"])
    save_json_atomic(PREFS_FILE, data)
    return data


def cache_folder():
    folder = os.path.join(PREFS_FOLDER)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return folder
