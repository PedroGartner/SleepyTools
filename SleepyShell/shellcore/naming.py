"""Naming conventions: shot names, script names, version tokens.

Conventions (extend SnapshotBrowser's, never fight them):
- Shot name pattern like ``sh###`` -> sh001, sh002 ... (### = zero-padded counter).
- Script pattern like ``{shot}_comp_v###.nk`` -> sh035_comp_v001.nk.
- Version tokens are ``_v`` + digits before the extension; padding is
  taken from the pattern but existing files with different padding still parse.
"""

import os
import re

_SHOT_NUM_RE = re.compile(r"^(?P<prefix>[A-Za-z0-9_]*?)(?P<num>\d+)$")
_VERSION_RE = re.compile(r"^(?P<base>.*)_v(?P<num>\d+)$", re.IGNORECASE)

_INVALID_CHARS = '<>:"/\\|?*'


def sanitize_name(name):
    """Make a string safe as a Windows folder/file name."""
    name = "".join("_" if c in _INVALID_CHARS else c for c in name)
    name = name.strip(" .")
    return name


def expand_shot_name(pattern, number):
    """Expand ``sh###`` with a number, zero-padded to the ### width."""
    token = re.search(r"#+", pattern or "")
    if not token:
        return sanitize_name(pattern or "") + str(number)
    width = len(token.group(0))
    return pattern.replace(token.group(0), str(int(number)).zfill(width))


def parse_shot_number(name, pattern="sh###"):
    """Return the counter of ``name`` if it matches ``pattern``, else None."""
    token = re.search(r"#+", pattern or "")
    prefix = pattern[:token.start()] if token else ""
    m = _SHOT_NUM_RE.match(name or "")
    if not m:
        return None
    if not name.startswith(prefix):
        return None
    try:
        return int(m.group("num"))
    except ValueError:
        return None


def next_shot_name(parent_dir, pattern="sh###", start=1):
    """Next free shot name inside ``parent_dir`` following ``pattern``."""
    try:
        existing = set(os.listdir(parent_dir))
    except (OSError, TypeError):
        existing = set()
    number = start
    while expand_shot_name(pattern, number).lower() in {e.lower() for e in existing}:
        number += 1
    return expand_shot_name(pattern, number)


def highest_shot_number(parent_dir, pattern="sh###"):
    """Highest counter currently used under ``parent_dir`` (0 if none)."""
    try:
        entries = os.listdir(parent_dir)
    except OSError:
        return 0
    numbers = [parse_shot_number(e, pattern) for e in entries]
    numbers = [n for n in numbers if n is not None]
    return max(numbers) if numbers else 0


def script_name(pattern, shot, version):
    """Expand ``{shot}_comp_v###.nk`` for a shot name and version number."""
    pattern = pattern or "{shot}_comp_v###.nk"
    token = re.search(r"#+", pattern)
    if token:
        pattern = pattern.replace(token.group(0), str(int(version)).zfill(len(token.group(0))))
    return sanitize_name(pattern.replace("{shot}", shot))


def parse_version_number(filename):
    """Return the version int of ``sh035_comp_v012.nk`` (None if no token)."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    m = _VERSION_RE.match(stem)
    return int(m.group("num")) if m else None


def version_base(filename):
    """Script stem without its version token: sh035_comp_v012 -> sh035_comp."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    m = _VERSION_RE.match(stem)
    return m.group("base") if m else stem


def next_version_file(comp_dir, pattern, shot):
    """Next free version filename for ``shot`` inside ``comp_dir``."""
    existing = set()
    try:
        existing = set(os.listdir(comp_dir))
    except (OSError, TypeError):
        pass
    highest = 0
    for entry in existing:
        if entry.lower().endswith(".nk"):
            number = parse_version_number(entry)
            if number is not None:
                highest = max(highest, number)
    number = highest + 1
    while script_name(pattern, shot, number).lower() in {e.lower() for e in existing}:
        number += 1
    return script_name(pattern, shot, number)
