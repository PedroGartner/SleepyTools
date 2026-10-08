"""Sequence grouping derived from shot names (presentation logic).

Sleepy Shell's data model has no stored sequence entity: sequence
grouping is DERIVED from shot names so every frontend can group shots
without changing any project data.

Rule: a shot name like ``sh0134`` splits into a leading alphabetical
prefix (``sh``) and a counter (134). The sequence is the prefix plus
the counter bucketed to the nearest lower hundred (``sh0100``), so
sh0100-sh0199 group together. Names without digits group under
``misc``; names without a prefix group under the bucket alone.
"""

import re

_NAME_RE = re.compile(r"^(?P<prefix>[A-Za-z_]*)\s*(?P<num>\d+)$")
_BUCKET = 100


def sequence_key(shot_name, bucket=_BUCKET):
    """Stable grouping key for a shot name ('sh0134' -> 'sh0100')."""
    name = (shot_name or "").strip()
    m = _NAME_RE.match(name)
    if not m:
        return "misc"
    prefix = m.group("prefix").lower()
    num = int(m.group("num"))
    start = (num // bucket) * bucket
    width = len(m.group("num"))
    label_num = str(start).zfill(min(width, 4)) if width >= 3 else str(start)
    return "{}{}".format(prefix, label_num)


def sequence_label(key):
    """Human label for a sequence key ('sh0100' -> 'SH0100')."""
    return (key or "misc").upper()


def group_shots(shots, key_func=sequence_key):
    """Group shot items into an ordered {key: [shot, ...]} mapping."""
    groups = {}
    for shot in shots:
        key = key_func(shot.get("name", ""))
        groups.setdefault(key, []).append(shot)
    for key in groups:
        groups[key].sort(key=lambda s: s.get("name", "").lower())
    return dict(sorted(groups.items(), key=lambda kv: kv[0]))
