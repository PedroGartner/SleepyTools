"""Frame Doctor: quality checks for rendered frame sequences.

The filesystem + math half (no image decoding here): discovers frames,
finds gaps and zero-byte files, aggregates per-frame statistics
produced by a reader, applies thresholds, and builds a verdict.

A *reader* is a callable ``load(path) -> stats`` returning a dict with
``width``, ``height`` and any of ``mean``, ``std``, ``nan_count``,
``hot_fraction`` (fraction of pixels above 1.0). Readers live in
``framedoctor_readers`` (which may import Qt/OpenEXR/PIL behind
function-level imports so this module stays importable everywhere).
"""

import os
import re

_FRAME_RE = re.compile(r"^(?P<base>.*?)(?P<num>\d+)\.(?P<ext>[A-Za-z0-9]+)$")

#: frame-number runs whose gap is at least this size are reported
MIN_GAP = 1

DEFAULTS = {
    "black_mean": 0.005,     # mean luminance below = black frame
    "flat_std": 0.0005,      # std below = flat frame (single color)
    "hot_fraction": 0.5,     # fraction of pixels > 1.0 above = clipped
    "hot_warn": 0.05,
}


def discover(folder):
    """Group frame files in ``folder`` into sequences.

    Returns a list of dicts: {base, ext, frames: [(number, path)], ...}
    sorted by number, largest group first. Non-numbered files are
    ignored.
    """
    groups = {}
    try:
        entries = sorted(os.listdir(folder))
    except OSError:
        return []
    for name in entries:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        m = _FRAME_RE.match(name)
        if not m:
            continue
        key = (m.group("base").lower(), m.group("ext").lower())
        groups.setdefault(key, []).append((int(m.group("num")), path))
    result = []
    for (base, ext), frames in groups.items():
        frames.sort(key=lambda t: t[0])
        result.append({"base": base, "ext": ext, "frames": frames})
    result.sort(key=lambda s: -len(s["frames"]))
    return result


def find_sequence(path):
    """Resolve a user-supplied target to (folder, sequence_dict).

    ``path`` may be a folder, a frame, or a pattern containing ####,
    %04d or *. Returns (folder, sequence) or (None, None).
    """
    path = path or ""
    if os.path.isdir(path):
        seqs = discover(path)
        return (path, seqs[0]) if seqs else (None, None)
    folder = os.path.dirname(path) or "."
    pattern = os.path.basename(path)
    stem = re.split(r"#|%0\dd|\*", pattern)[0]
    for seq in discover(folder):
        if seq["base"].startswith(stem.lower()) or stem.startswith(seq["base"]):
            return folder, seq
    return None, None


def frame_gaps(frames, min_gap=MIN_GAP):
    """Missing numbers inside the found range: [(from, to), ...]."""
    numbers = [n for n, _p in frames]
    if len(numbers) < 2:
        return []
    gaps = []
    run_start = None
    for i in range(1, len(numbers)):
        prev, cur = numbers[i - 1], numbers[i]
        if cur > prev + 1:
            run_start = prev + 1
            run_end = cur - 1
            if run_start <= run_end:
                gaps.append((run_start, run_end))
    return [(a, b) for a, b in gaps if b - a + 1 >= min_gap]


def analyze(frames, load, thresholds=None, sample=1):
    """Scan frames with a reader and build the full report.

    ``load(path)`` returns a stats dict (see module docstring) or None
    when the file cannot be read. ``sample`` N > 1 analyzes every Nth
    frame (first and last are always included).
    """
    t = dict(DEFAULTS)
    t.update(thresholds or {})
    report = {
        "sequence": os.path.basename(frames[0][1]) if frames else "",
        "frame_count": len(frames),
        "first": frames[0][0] if frames else None,
        "last": frames[-1][0] if frames else None,
        "gaps": frame_gaps(frames),
        "zero_byte": [],
        "unreadable": [],
        "black": [],
        "flat": [],
        "hot": [],
        "nan": [],
        "resolution_changes": [],
        "width": None,
        "height": None,
        "scanned": 0,
    }
    base_res = None
    count = len(frames)
    for index, (number, path) in enumerate(frames):
        try:
            if os.path.getsize(path) == 0:
                report["zero_byte"].append(number)
                continue
        except OSError:
            report["unreadable"].append(number)
            continue
        if sample > 1 and 0 < index < count - 1 and index % sample != 0:
            continue
        try:
            stats = load(path)
        except Exception:
            stats = None
        if not stats:
            report["unreadable"].append(number)
            continue
        report["scanned"] += 1
        width, height = stats.get("width"), stats.get("height")
        if width and height:
            if base_res is None:
                base_res = (width, height)
                report["width"], report["height"] = width, height
            elif (width, height) != base_res:
                if number not in report["resolution_changes"]:
                    report["resolution_changes"].append(number)
        mean = stats.get("mean")
        std = stats.get("std")
        if mean is not None and mean <= t["black_mean"] and \
                (std is None or std <= t["flat_std"] * 4):
            report["black"].append(number)
            continue
        if std is not None and std < t["flat_std"]:
            report["flat"].append(number)
        if stats.get("nan_count"):
            report["nan"].append(number)
        hot = stats.get("hot_fraction")
        if hot is not None and hot >= t["hot_fraction"]:
            report["hot"].append(number)
    report["verdict"], report["problems"] = _verdict(report)
    return report


def _verdict(report):
    problems = []
    if report["gaps"]:
        ranges = ", ".join(_range_text(a, b) for a, b in report["gaps"])
        problems.append("missing frames {}".format(ranges))
    if report["zero_byte"]:
        problems.append("{} zero-byte frames".format(len(report["zero_byte"])))
    if report["black"]:
        problems.append("{} black frame(s): {}".format(
            len(report["black"]), _nums(report["black"])))
    if report["flat"]:
        problems.append("{} flat frame(s): {}".format(
            len(report["flat"]), _nums(report["flat"])))
    if report["nan"]:
        problems.append("{} frame(s) with NaN: {}".format(
            len(report["nan"]), _nums(report["nan"])))
    if report["hot"]:
        problems.append("{} clipped frame(s): {}".format(
            len(report["hot"]), _nums(report["hot"])))
    if report["resolution_changes"]:
        problems.append("resolution change at {}".format(
            _nums(report["resolution_changes"])))
    if report["unreadable"]:
        problems.append("{} unreadable frame(s)".format(len(report["unreadable"])))
    return ("OK" if not problems else "PROBLEMS"), problems


def _nums(numbers, limit=8):
    shown = sorted(numbers)[:limit]
    text = ", ".join(str(n) for n in shown)
    if len(numbers) > limit:
        text += ", +{}".format(len(numbers) - limit)
    return text


def _range_text(a, b):
    return "{}-{}".format(a, b) if b > a else str(a)
