"""Metadata schemas for Sleepy Shell: shot.json and project.json.

Formats are versioned (``sleepy-shot/1``, ``sleepy-project/1``).
Rules:
- Unknown fields are preserved on rewrite, never dropped.
- Every field is optional and type-checked on load; bad values fall
  back to defaults instead of raising.
- All writes are atomic (temp file + os.replace) and never truncate an
  existing file on failure.
"""

import io
import json
import os
import tempfile

FORMAT_SHOT = "sleepy-shot/1"
FORMAT_PROJECT = "sleepy-project/1"

SHOT_FILE = "shot.json"
PROJECT_FILE = "project.json"

#: Canonical statuses, in board order.
STATUS_WIP = "wip"
STATUS_WAITING = "waiting"
STATUS_REVIEW = "review"
STATUS_APPROVED = "approved"
STATUS_DELIVERED = "delivered"
STATUS_HOLD = "hold"

STATUS_ORDER = (STATUS_WIP, STATUS_WAITING, STATUS_REVIEW, STATUS_APPROVED,
                STATUS_DELIVERED, STATUS_HOLD)

STATUS_LABELS = {
    STATUS_WIP: "WIP",
    STATUS_WAITING: "Waiting client",
    STATUS_REVIEW: "Review",
    STATUS_APPROVED: "Approved",
    STATUS_DELIVERED: "Delivered",
    STATUS_HOLD: "Hold",
}

SHOT_DEFAULTS = {
    "format": FORMAT_SHOT,
    "status": STATUS_WIP,
    "due": None,          # ISO date string "YYYY-MM-DD" or None
    "priority": None,     # small int 1-3 or None
    "tags": [],
    "notes": "",
    "tasks": [],          # [{name: str, done: bool}] - per-shot checklist
}

PROJECT_DEFAULTS = {
    "format": FORMAT_PROJECT,
    "client": "",
    "color": None,        # hex string or None
    "fps": 25,
    "resolution": "",
    "working_space": "",
    "range": "",
    "handles": 8,
    "folder_template": "standard",   # "standard" | "client"
    "comp_template": "",             # path to a template .nk for new shots
    "render_output": "",             # default output dir pattern for SleepyQueue
    "deliverable_naming": "{shot}_{desc}_v###",
    "tags": [],
}


def _coerce(value, default, nullable_type=None):
    """Fall back to ``default`` unless ``value`` has the same JSON type.

    ``nullable_type`` covers fields whose default is None but which
    accept a concrete type too (e.g. priority: int or None).
    """
    if default is None:
        if nullable_type is None:
            return value
        if value is None:
            return None
        if nullable_type is int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        if nullable_type is str:
            return value if isinstance(value, str) else None
        if nullable_type is float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        return value
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    if isinstance(default, str):
        return value if isinstance(value, str) else default
    if isinstance(default, list):
        if isinstance(value, list):
            # dicts allowed so structured items (e.g. tasks) survive;
            # scalar-typed lists simply never contain them
            return [v for v in value if isinstance(v, (str, int, float, dict))]
        return default
    return default


def normalize(data, defaults, nullable=None):
    """Merge stored data over defaults, type-checking known fields.

    Unknown fields survive untouched so future schema versions and
    third-party annotations are never destroyed. ``nullable`` maps a
    field name to the concrete type it accepts besides None.
    """
    nullable = nullable or {}
    result = dict(defaults)
    extra = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if key in defaults:
                result[key] = _coerce(value, defaults[key], nullable.get(key))
            else:
                extra[key] = value
    result.update(extra)
    return result


def load_json(path):
    """Read a JSON file, returning None on any problem (missing, malformed)."""
    try:
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
    except (IOError, OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def save_json_atomic(path, data):
    """Write JSON atomically: write a temp file next to the target, then replace.

    Raises the original error if the write fails, leaving any existing
    file untouched.
    """
    folder = os.path.dirname(path) or "."
    if not os.path.isdir(folder):
        os.makedirs(folder)
    fd, tmp = tempfile.mkstemp(prefix=".sleepy_shell_", suffix=".tmp", dir=folder)
    try:
        with io.open(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        for candidate in (tmp,):
            try:
                if os.path.exists(candidate):
                    os.remove(candidate)
            except OSError:
                pass
        raise


#: Fields whose default is None but which accept a concrete type.
_SHOT_NULLABLE = {"due": str, "priority": int}
_PROJECT_NULLABLE = {"color": str}


def normalize_tasks(items):
    """Coerce a raw tasks list into [{name: str, done: bool}].

    Accepts plain strings (as not-done) and dicts; anything without a
    usable name is dropped, so malformed metadata can never break the
    checklist UI.
    """
    result = []
    for item in items or []:
        if isinstance(item, str):
            name = item.strip()
            if name:
                result.append({"name": name, "done": False})
        elif isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if name:
                result.append({"name": name, "done": bool(item.get("done"))})
    return result


def load_shot(shot_dir):
    """Load and normalize shot.json from a shot folder. Returns (config, error)."""
    path = os.path.join(shot_dir, SHOT_FILE)
    data = load_json(path)
    if data is None:
        return dict(SHOT_DEFAULTS), None if not os.path.isfile(path) else "unreadable shot.json"
    config = normalize(data, SHOT_DEFAULTS, _SHOT_NULLABLE)
    config["tasks"] = normalize_tasks(config.get("tasks"))
    if data.get("format") not in (None, FORMAT_SHOT):
        config["format"] = data.get("format")  # tolerate future versions, keep marker
    return config, None


def save_shot(shot_dir, config):
    """Merge into any existing shot.json and write it atomically.

    Unknown keys already on disk survive the rewrite (read-modify-write),
    so third-party annotations are never destroyed by a partial update.
    """
    path = os.path.join(shot_dir, SHOT_FILE)
    existing = load_json(path) or {}
    merged_input = dict(existing)
    merged_input.update(config or {})
    data = normalize(merged_input, SHOT_DEFAULTS, _SHOT_NULLABLE)
    data["format"] = FORMAT_SHOT if data.get("format") in (None, FORMAT_SHOT) else data["format"]
    save_json_atomic(path, data)
    return data


def load_project(project_dir):
    """Load and normalize project.json from a project folder. Returns (config, error)."""
    path = os.path.join(project_dir, PROJECT_FILE)
    data = load_json(path)
    if data is None:
        return dict(PROJECT_DEFAULTS), None if not os.path.isfile(path) else "unreadable project.json"
    return normalize(data, PROJECT_DEFAULTS, _PROJECT_NULLABLE), None


def save_project(project_dir, config):
    """Merge into any existing project.json and write it atomically."""
    path = os.path.join(project_dir, PROJECT_FILE)
    existing = load_json(path) or {}
    merged_input = dict(existing)
    merged_input.update(config or {})
    data = normalize(merged_input, PROJECT_DEFAULTS, _PROJECT_NULLABLE)
    data["format"] = FORMAT_PROJECT if data.get("format") in (None, FORMAT_PROJECT) else data["format"]
    save_json_atomic(path, data)
    return data


def is_our_shot_config(path):
    """True only if the file exists and carries our shot format marker.

    Used by unmanage so we never delete files we did not write.
    """
    data = load_json(path)
    return bool(data) and data.get("format") == FORMAT_SHOT
