"""Recently opened shots (derived from actual opens, never guessed).

Stored alongside prefs in %LOCALAPPDATA%\\SleepyTools\\. Entries point
at shot folders; missing folders are dropped on read so the list never
shows dead entries.
"""

import os
import time

from shellcore.prefs import cache_folder
from shellcore.schema import load_json, save_json_atomic

RECENTS_FILE = os.path.join(cache_folder(), "sleepy_shell_recents.json")
_MAX_ENTRIES = 30


def _load():
    data = load_json(RECENTS_FILE)
    if not data or not isinstance(data.get("entries"), list):
        return {"entries": []}
    return data


def remember(shot_path, comp_dir=None):
    """Record a shot open, newest first, deduplicated (max 30 entries)."""
    if not shot_path:
        return
    data = _load()
    norm = os.path.normcase(os.path.normpath(shot_path))
    entries = [e for e in data["entries"]
               if isinstance(e, dict) and os.path.normcase(os.path.normpath(e.get("path", ""))) != norm]
    entries.insert(0, {"path": shot_path, "comp_dir": comp_dir or "",
                       "ts": time.time()})
    data["entries"] = entries[:_MAX_ENTRIES]
    save_json_atomic(RECENTS_FILE, data)


def list_recents(limit=12):
    """Newest entries whose folder still exists: [{path, comp_dir, ts}]."""
    data = _load()
    result = []
    for entry in data["entries"]:
        path = entry.get("path", "")
        if not path or not os.path.isdir(path):
            continue
        result.append(entry)
        if len(result) >= limit:
            break
    return result
