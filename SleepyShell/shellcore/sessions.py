"""Session tracking: how much time was actually spent in a script.

The Nuke panel appends one record per work segment (script path, start,
end). The standalone launcher only reads the file. Records live in
%LOCALAPPDATA%\\SleepyTools\\sleepy_shell_sessions.json; entries older
than 90 days are pruned on write.
"""

import datetime
import os
import time

from shellcore.prefs import cache_folder
from shellcore.schema import load_json, save_json_atomic

SESSIONS_FILE = os.path.join(cache_folder(), "sleepy_shell_sessions.json")
_MAX_AGE_DAYS = 90


def _load():
    data = load_json(SESSIONS_FILE)
    if not data or not isinstance(data.get("records"), list):
        return {"records": []}
    return data


def _save(data):
    cutoff = time.time() - _MAX_AGE_DAYS * 86400
    records = [r for r in data.get("records", [])
               if isinstance(r, dict) and float(r.get("end", 0) or 0) >= cutoff]
    save_json_atomic(SESSIONS_FILE, {"records": records})


def add_segment(script_path, start, end, shot_path=None, project_path=None):
    """Record one work segment. Ignores inverted or zero-length input."""
    try:
        start = float(start)
        end = float(end)
    except (TypeError, ValueError):
        return
    if end <= start:
        return
    if end - start > 24 * 3600:  # clock skew / machine slept for days
        end = start + 24 * 3600
    data = _load()
    data["records"].append({
        "script": script_path or "",
        "shot": shot_path or "",
        "project": project_path or "",
        "start": start,
        "end": end,
    })
    _save(data)


def summarize_for_shot(shot_path, comp_dir=None):
    """Time totals for one shot: {total, this_week, by_day}.

    Matches by shot folder path; for records saved before a shot had a
    path, script paths under the shot's comp folder also count.
    """
    data = _load()
    now = time.time()
    week_start = now - 7 * 86400
    total = 0.0
    week = 0.0
    by_day = {}
    comp = os.path.normcase(comp_dir) if comp_dir else None
    for record in data.get("records", []):
        matches = False
        if shot_path and os.path.normcase(record.get("shot") or "") == os.path.normcase(shot_path):
            matches = True
        elif comp and record.get("script"):
            matches = os.path.normcase(os.path.dirname(record["script"])) == comp
        if not matches:
            continue
        seconds = max(0.0, float(record.get("end", 0)) - float(record.get("start", 0)))
        total += seconds
        if float(record.get("end", 0)) >= week_start:
            week += seconds
        day = datetime.datetime.fromtimestamp(float(record.get("start", now))).date().isoformat()
        by_day[day] = by_day.get(day, 0.0) + seconds
    return {"total": total, "this_week": week, "by_day": by_day}


def last_opened(comp_dir):
    """Newest mtime among a shot's comp scripts (derived, not stored)."""
    if not comp_dir or not os.path.isdir(comp_dir):
        return None
    latest = None
    try:
        for name in os.listdir(comp_dir):
            if name.lower().endswith(".nk"):
                try:
                    stamp = os.path.getmtime(os.path.join(comp_dir, name))
                except OSError:
                    continue
                latest = max(latest, stamp) if latest else stamp
    except OSError:
        return None
    return latest
