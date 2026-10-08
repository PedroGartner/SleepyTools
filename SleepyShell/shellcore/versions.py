"""Version and snapshot discovery for a shot.

- Versions: every ``.nk`` in the shot's comp folder that carries a
  ``_v###`` token, sorted newest first.
- Snapshots: read-only, tolerant parsing of SnapshotBrowser's
  ``.snapshots/<base>/*.json`` metadata (format ``snapshot/1``). We
  read the files; we never write into SnapshotBrowser's store from the
  core (the Nuke panel delegates real snapshot creation to
  sleepy_snapshots's own bridge when it is available).
"""

import json
import os

from shellcore.naming import parse_version_number, version_base

SNAPSHOTS_DIR = ".snapshots"


def list_versions(comp_dir):
    """All versioned scripts in a comp folder, newest first.

    Each entry: {path, name, number, mtime, size}. Files without a
    version token are listed with number 0 so they stay visible.
    """
    versions = []
    if not comp_dir or not os.path.isdir(comp_dir):
        return versions
    try:
        names = os.listdir(comp_dir)
    except OSError:
        return versions
    for name in names:
        if not name.lower().endswith(".nk"):
            continue
        path = os.path.join(comp_dir, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        versions.append({
            "path": path,
            "name": name,
            "number": parse_version_number(name) or 0,
            "mtime": stat.st_mtime,
            "size": stat.st_size,
        })
    versions.sort(key=lambda v: (v["number"], v["mtime"]), reverse=True)
    return versions


def latest_version(comp_dir):
    entries = list_versions(comp_dir)
    return entries[0] if entries else None


def _read_snapshot_meta(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("format") not in (None, "snapshot/1"):
        return None
    return {
        "id": data.get("id") or os.path.splitext(os.path.basename(path))[0],
        "kind": data.get("kind", "manual"),
        "created": data.get("created", ""),
        "note": data.get("note", ""),
        "tags": data.get("tags", []) if isinstance(data.get("tags"), list) else [],
        "starred": bool(data.get("starred")),
        "script": data.get("script", ""),
        "thumbnail": data.get("thumbnail"),
        "render": data.get("render") if isinstance(data.get("render"), dict) else None,
    }


def snapshots_for(shot_path, comp_dir):
    """All SnapshotBrowser snapshots belonging to this shot, newest first.

    SnapshotBrowser stores snapshots under ``<comp>/.snapshots/<script
    base without version>/``. All versions of a shot share one base, so
    every snapshot of the shot appears here.
    """
    results = []
    if not comp_dir:
        return results
    snap_root = os.path.join(comp_dir, SNAPSHOTS_DIR)
    if not os.path.isdir(snap_root):
        return results
    bases = set()
    for entry in list_versions(comp_dir):
        bases.add(version_base(entry["name"]))
    for name in os.listdir(snap_root):
        folder = os.path.join(snap_root, name)
        if not os.path.isdir(folder):
            continue
        if bases and name not in bases and not _looks_like_hash(folder):
            continue
        try:
            metas = os.listdir(folder)
        except OSError:
            continue
        for meta_name in metas:
            if not meta_name.endswith(".json"):
                continue
            meta = _read_snapshot_meta(os.path.join(folder, meta_name))
            if meta:
                meta["folder"] = folder
                results.append(meta)
    results.sort(key=lambda m: m.get("created", ""), reverse=True)
    return results


def _looks_like_hash(folder):
    """SnapshotBrowser folder names end with a short random suffix."""
    tail = os.path.basename(folder.rstrip("\\/"))
    return "_" in tail


def thumbnails_for(shot_path, comp_dir, limit=4):
    """Newest snapshot thumbnail images for a shot (absolute paths)."""
    thumbs = []
    for meta in snapshots_for(shot_path, comp_dir):
        thumb = meta.get("thumbnail")
        if not thumb:
            continue
        path = os.path.join(meta.get("folder", ""), thumb)
        if os.path.isfile(path):
            thumbs.append(path)
        if len(thumbs) >= limit:
            break
    return thumbs


def render_records(snapshots):
    """Render-kind snapshot entries (shown as 'recent renders' when present)."""
    return [s for s in snapshots if s.get("kind") == "render" and s.get("render")]
