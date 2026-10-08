"""Shared JSON settings for the suite.

Each tool gets its own namespace under ~/.nuke/sleepy_core/settings.json.
Tools can still use their own settings files; this is an optional
centralized store for tools that want to adopt it.
"""

import io
import json
import os

SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".nuke", "sleepy_core", "settings.json")


def _load_all():
    try:
        with io.open(SETTINGS_FILE, encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (IOError, OSError, ValueError):
        return {}


def _save_all(data):
    folder = os.path.dirname(SETTINGS_FILE)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    tmp = SETTINGS_FILE + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, SETTINGS_FILE)


def get(tool_name, key, default=None):
    """Get a setting for a tool."""
    data = _load_all()
    return data.get(tool_name, {}).get(key, default)


def set(tool_name, key, value):
    """Set a setting for a tool."""
    data = _load_all()
    if tool_name not in data:
        data[tool_name] = {}
    data[tool_name][key] = value
    _save_all(data)


def get_tool_settings(tool_name, defaults=None):
    """Get all settings for a tool, merged with defaults."""
    data = _load_all()
    tool_data = data.get(tool_name, {})
    if defaults:
        merged = dict(defaults)
        merged.update(tool_data)
        return merged
    return tool_data


def set_tool_settings(tool_name, settings_dict):
    """Replace all settings for a tool."""
    data = _load_all()
    data[tool_name] = settings_dict
    _save_all(data)