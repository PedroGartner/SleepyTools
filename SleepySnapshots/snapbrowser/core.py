"""Filesystem layer: script versions, snapshots and their metadata.

This module never imports nuke, so it can be used by a standalone app or by
other tools that want to write snapshots in the same format.

Snapshot layout, next to the script:

    <script dir>/.snapshots/<shot key>/<shot key>_<id>.nk
    <script dir>/.snapshots/<shot key>/<shot key>_<id>.json
    <script dir>/.snapshots/<shot key>/<shot key>_<id>.jpg   (optional)

The shot key is the script name without its version token, so snapshots of
v010, v011 and v012 all live in the same folder and show up in one timeline.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import getpass
import gzip
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from snapbrowser import nkparse
from snapbrowser.nkparse import count_nodes, read_text as read_script_text

FORMAT = "snapshot/1"
SNAPSHOT_DIR = ".snapshots"

KIND_MANUAL = "manual"
KIND_AUTO = "auto"
KIND_SAVE = "save"
KIND_RENDER = "render"
KIND_RESTORE = "restore"

#: Kinds created without the user asking; these are subject to retention.
AUTOMATIC_KINDS = (KIND_AUTO, KIND_SAVE, KIND_RENDER, KIND_RESTORE)

KIND_LABELS = {
    KIND_MANUAL: "Snapshot",
    KIND_AUTO: "Auto",
    KIND_SAVE: "On save",
    KIND_RENDER: "Render",
    KIND_RESTORE: "Before restore",
}

ENTRY_VERSION = "version"
ENTRY_SNAPSHOT = "snapshot"
ENTRY_AUTOSAVE = "autosave"

# Greedy base so the last v### token in the name is the version.
_VERSION_RE = re.compile(
    r"^(?P<base>.*)(?P<letter>[vV])(?P<num>\d+)(?P<tail>[^\\/]*)\.nk$"
)
_SEPARATORS = "._- "


# --------------------------------------------------------------------------
# Versions
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class VersionInfo:
    base: str
    letter: str
    number: int
    padding: int
    tail: str

    def filename(self, number: Optional[int] = None) -> str:
        num = self.number if number is None else number
        return "{}{}{:0{}d}{}.nk".format(
            self.base, self.letter, num, self.padding, self.tail
        )


def parse_version(path: str) -> Optional[VersionInfo]:
    """Split a script file name into base, version number and tail."""
    match = _VERSION_RE.match(os.path.basename(path))
    if not match:
        return None
    num = match.group("num")
    return VersionInfo(
        base=match.group("base"),
        letter=match.group("letter"),
        number=int(num),
        padding=len(num),
        tail=match.group("tail"),
    )


def shot_key(script_path: str) -> str:
    """Name of the snapshot folder for a script, shared by all its versions."""
    info = parse_version(script_path)
    if info:
        key = info.base.rstrip(_SEPARATORS) + info.tail
    else:
        key = os.path.splitext(os.path.basename(script_path))[0]
    key = re.sub(r"[^\w.-]+", "_", key).strip("._")
    return key or "untitled"


def _same_file(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _is_candidate(name: str) -> bool:
    return name.lower().endswith(".nk") and not name.startswith(".")


def find_versions(script_path: str) -> List[str]:
    """Sibling scripts that share this script's base and tail, oldest first."""
    folder = os.path.dirname(os.path.abspath(script_path))
    info = parse_version(script_path)
    if info is None:
        return [script_path] if os.path.isfile(script_path) else []

    base = os.path.normcase(info.base)
    tail = os.path.normcase(info.tail)
    found = []
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    for name in names:
        if not _is_candidate(name):
            continue
        other = parse_version(name)
        if other is None:
            continue
        if os.path.normcase(other.base) == base and os.path.normcase(other.tail) == tail:
            found.append((other.number, os.path.join(folder, name)))
    found.sort()
    return [path for _, path in found]


def next_version_path(script_path: str) -> str:
    """Path for the next free version of this script."""
    folder = os.path.dirname(os.path.abspath(script_path))
    info = parse_version(script_path)
    if info is None:
        stem = os.path.splitext(os.path.basename(script_path))[0]
        info = VersionInfo(base=stem + "_", letter="v", number=0, padding=3, tail="")

    highest = info.number
    padding = info.padding
    for path in find_versions(script_path):
        other = parse_version(path)
        if other:
            highest = max(highest, other.number)
            padding = max(padding, other.padding)

    number = highest + 1
    while True:
        candidate = os.path.join(
            folder,
            VersionInfo(info.base, info.letter, number, padding, info.tail).filename(),
        )
        if not os.path.exists(candidate):
            return candidate
        number += 1


# --------------------------------------------------------------------------
# Snapshots
# --------------------------------------------------------------------------

def _now() -> _dt.datetime:
    return _dt.datetime.now().astimezone()


def _file_hash(path: str) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _parse_time(value: str) -> _dt.datetime:
    try:
        stamp = _dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return _dt.datetime.fromtimestamp(0).astimezone()
    if stamp.tzinfo is None:
        stamp = stamp.astimezone()
    return stamp


@dataclass
class Snapshot:
    folder: str
    meta: dict
    meta_path: str

    @property
    def id(self) -> str:
        return self.meta.get("id", "")

    @property
    def kind(self) -> str:
        return self.meta.get("kind", KIND_MANUAL)

    @property
    def created(self) -> _dt.datetime:
        return _parse_time(self.meta.get("created", ""))

    @property
    def note(self) -> str:
        return self.meta.get("note", "")

    @property
    def tags(self) -> List[str]:
        return list(self.meta.get("tags") or [])

    @property
    def starred(self) -> bool:
        return bool(self.meta.get("starred"))

    @property
    def script_path(self) -> str:
        return os.path.join(self.folder, self.meta.get("script", ""))

    @property
    def thumbnail_path(self) -> Optional[str]:
        name = self.meta.get("thumbnail")
        if not name:
            return None
        path = os.path.join(self.folder, name)
        return path if os.path.isfile(path) else None

    @property
    def is_automatic(self) -> bool:
        return self.kind in AUTOMATIC_KINDS

    def files(self) -> List[str]:
        paths = [self.meta_path, self.script_path]
        thumb = self.meta.get("thumbnail")
        if thumb:
            paths.append(os.path.join(self.folder, thumb))
        return paths


class SnapshotStore:
    """Snapshots for one shot, stored in a sidecar folder next to the script."""

    def __init__(self, script_path: str, folder: Optional[str] = None):
        self.script_path = os.path.abspath(script_path)
        self.key = shot_key(script_path)
        self.folder = folder or os.path.join(
            os.path.dirname(self.script_path), SNAPSHOT_DIR, self.key
        )

    # -- reading ----------------------------------------------------------

    def list(self) -> List[Snapshot]:
        """All valid snapshots, newest first."""
        if not os.path.isdir(self.folder):
            return []
        snapshots = []
        for name in os.listdir(self.folder):
            if not name.endswith(".json"):
                continue
            meta_path = os.path.join(self.folder, name)
            try:
                with open(meta_path, "r", encoding="utf-8") as handle:
                    meta = json.load(handle)
            except (OSError, ValueError):
                continue
            if not isinstance(meta, dict) or not str(meta.get("format", "")).startswith("snapshot/"):
                continue
            snap = Snapshot(self.folder, meta, meta_path)
            if os.path.isfile(snap.script_path):
                snapshots.append(snap)
        snapshots.sort(key=lambda s: (s.created, s.id), reverse=True)
        return snapshots

    def latest(self) -> Optional[Snapshot]:
        items = self.list()
        return items[0] if items else None

    # -- writing ----------------------------------------------------------

    def temp_path(self, extension: str = ".nk") -> str:
        """A unique scratch path inside the store, e.g. for scriptSaveToTemp."""
        os.makedirs(self.folder, exist_ok=True)
        return os.path.join(self.folder, ".incoming_{}{}".format(uuid.uuid4().hex, extension))

    def add(
        self,
        script_file: str,
        kind: str = KIND_MANUAL,
        note: str = "",
        tags: Optional[Iterable[str]] = None,
        thumbnail_file: Optional[str] = None,
        frame: Optional[int] = None,
        source_script: Optional[str] = None,
        app: str = "",
        move: bool = True,
        dedupe: bool = True,
        extra: Optional[dict] = None,
        compress: bool = True,
    ) -> Optional[Snapshot]:
        """Store a saved .nk as a snapshot.

        With ``dedupe`` the snapshot is skipped (and None returned) when its
        content matches the most recent snapshot. With ``move`` the source
        files are moved into the store instead of copied. With ``compress``
        the script is stored gzip-compressed as .nk.gz.
        """
        os.makedirs(self.folder, exist_ok=True)
        content_hash = _file_hash(script_file)

        if dedupe:
            latest = self.latest()
            if latest and latest.meta.get("hash") == content_hash:
                if move:
                    _remove_quietly(script_file)
                    if thumbnail_file:
                        _remove_quietly(thumbnail_file)
                return None

        created = _now()
        snap_id = "{}_{}".format(created.strftime("%Y%m%d_%H%M%S"), uuid.uuid4().hex[:4])
        stem = "{}_{}".format(self.key, snap_id)
        transfer = shutil.move if move else shutil.copy2

        size = os.path.getsize(script_file)
        nodes = count_nodes(script_file)
        script_name = stem + (".nk.gz" if compress else ".nk")
        stored_script = os.path.join(self.folder, script_name)
        if compress:
            _gzip_file(script_file, stored_script)
            if move:
                _remove_quietly(script_file)
        else:
            transfer(script_file, stored_script)

        thumb_name = None
        if thumbnail_file and os.path.isfile(thumbnail_file):
            thumb_name = stem + os.path.splitext(thumbnail_file)[1].lower()
            transfer(thumbnail_file, os.path.join(self.folder, thumb_name))

        source = os.path.abspath(source_script or self.script_path)
        info = parse_version(source)
        meta = {
            "format": FORMAT,
            "id": snap_id,
            "kind": kind,
            "created": created.isoformat(timespec="milliseconds"),
            "note": note,
            "tags": list(tags or []),
            "starred": False,
            "script": script_name,
            "thumbnail": thumb_name,
            "hash": content_hash,
            "source_script": source.replace("\\", "/"),
            "source_version": info.number if info else None,
            "frame": frame,
            "user": _user(),
            "host": socket.gethostname(),
            "app": app,
            "size": size,
            "nodes": nodes,
            "compressed": compress,
        }
        if extra:
            meta.update(extra)
        meta_path = os.path.join(self.folder, stem + ".json")
        _write_json(meta_path, meta)
        return Snapshot(self.folder, meta, meta_path)

    def update(self, snapshot: Snapshot, **fields) -> Snapshot:
        """Change editable fields (note, tags, starred, kind) and save."""
        allowed = {"note", "tags", "starred", "kind"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError("Cannot edit field(s): " + ", ".join(sorted(unknown)))
        snapshot.meta.update(fields)
        _write_json(snapshot.meta_path, snapshot.meta)
        return snapshot

    def promote(self, snapshot: Snapshot, note: Optional[str] = None) -> Snapshot:
        """Turn an automatic snapshot into a manual one so it is always kept."""
        fields = {"kind": KIND_MANUAL}
        if note is not None:
            fields["note"] = note
        return self.update(snapshot, **fields)

    def delete(self, snapshot: Snapshot) -> None:
        for path in snapshot.files():
            _remove_quietly(path)

    def prune(self, keep: int) -> List[Snapshot]:
        """Keep only the newest ``keep`` snapshots of each automatic kind.

        Manual and starred snapshots are never removed. Returns the removed
        snapshots.
        """
        if keep < 1:
            return []
        removed = []
        counts = {}
        for snap in self.list():
            if not snap.is_automatic or snap.starred:
                continue
            counts[snap.kind] = counts.get(snap.kind, 0) + 1
            if counts[snap.kind] > keep:
                self.delete(snap)
                removed.append(snap)
        self.clean_incoming()
        return removed

    def cleanup(self, older_than_days: float, include_manual: bool = False) -> List[Snapshot]:
        """Delete snapshots older than a number of days. Starred ones are kept."""
        limit = _now() - _dt.timedelta(days=older_than_days)
        removed = []
        for snap in self.list():
            if snap.starred or snap.created >= limit:
                continue
            if not include_manual and not snap.is_automatic:
                continue
            self.delete(snap)
            removed.append(snap)
        return removed

    def compress_all(self):
        """Compress every uncompressed snapshot. Returns (count, bytes saved)."""
        count = 0
        saved = 0
        for snap in self.list():
            source = snap.script_path
            if source.lower().endswith(".gz"):
                continue
            target = source + ".gz"
            before = os.path.getsize(source)
            _gzip_file(source, target)
            snap.meta["script"] = os.path.basename(target)
            snap.meta["compressed"] = True
            snap.meta.setdefault("size", before)
            _write_json(snap.meta_path, snap.meta)
            _remove_quietly(source)
            saved += before - os.path.getsize(target)
            count += 1
        return count, saved

    def disk_usage(self) -> int:
        """Bytes used by this shot's snapshot folder."""
        return folder_size(self.folder)

    def clean_incoming(self, older_than_seconds: int = 3600) -> None:
        """Remove scratch files left behind by interrupted snapshots."""
        if not os.path.isdir(self.folder):
            return
        limit = _dt.datetime.now().timestamp() - older_than_seconds
        for name in os.listdir(self.folder):
            if name.startswith(".incoming_") or name.endswith((".json.tmp", ".gz.tmp")):
                path = os.path.join(self.folder, name)
                try:
                    if os.path.getmtime(path) < limit:
                        os.remove(path)
                except OSError:
                    pass


def create_snapshot(script_path: str, nk_file: str, kind: str = KIND_MANUAL, **kwargs) -> Optional[Snapshot]:
    """Convenience for other tools: store ``nk_file`` as a snapshot of ``script_path``."""
    kwargs.setdefault("move", False)
    return SnapshotStore(script_path).add(nk_file, kind=kind, source_script=script_path, **kwargs)


def _gzip_file(source: str, target: str) -> None:
    temp = target + ".tmp"
    with open(source, "rb") as reader, gzip.open(temp, "wb", compresslevel=6) as writer:
        shutil.copyfileobj(reader, writer)
    os.replace(temp, target)


@contextlib.contextmanager
def plain_script(path: str):
    """Path to an uncompressed copy of a script, for tools that need a real .nk."""
    if not path.lower().endswith(".gz"):
        yield path
        return
    handle, temp = tempfile.mkstemp(suffix=".nk", prefix="snapshot_browser_")
    try:
        with os.fdopen(handle, "wb") as writer, gzip.open(path, "rb") as reader:
            shutil.copyfileobj(reader, writer)
        yield temp
    finally:
        _remove_quietly(temp)


def folder_size(folder: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def format_size(size: Optional[int]) -> str:
    if size is None:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return "{:.0f} {}".format(value, unit) if unit == "B" else "{:.1f} {}".format(value, unit)
        value /= 1024
    return ""


def _user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------------

@dataclass
class Entry:
    type: str
    path: str
    time: _dt.datetime
    title: str
    kind: str = ""
    version: Optional[int] = None
    note: str = ""
    tags: List[str] = field(default_factory=list)
    starred: bool = False
    thumbnail: Optional[str] = None
    user: str = ""
    frame: Optional[int] = None
    is_current: bool = False
    snapshot: Optional[Snapshot] = None
    family: str = ""
    size: Optional[int] = None
    nodes: Optional[int] = None

    @property
    def meta(self) -> dict:
        return self.snapshot.meta if self.snapshot is not None else {}

    @property
    def render(self) -> dict:
        info = self.meta.get("render")
        return info if isinstance(info, dict) else {}

    @property
    def label(self) -> str:
        if self.type == ENTRY_VERSION or self.kind == KIND_MANUAL:
            return self.title
        return "{} ({})".format(self.title, self.type_label.lower())

    @property
    def type_label(self) -> str:
        if self.type == ENTRY_VERSION:
            return "Version"
        if self.type == ENTRY_AUTOSAVE:
            return "Autosave"
        return KIND_LABELS.get(self.kind, self.kind.title())

    def matches(self, text: str) -> bool:
        text = text.strip().lower()
        if not text:
            return True
        haystack = " ".join(
            [self.title, self.note, self.user, self.type_label] + self.tags
        ).lower()
        return all(word in haystack for word in text.split())


def _mtime(path: str) -> _dt.datetime:
    try:
        return _dt.datetime.fromtimestamp(os.path.getmtime(path)).astimezone()
    except OSError:
        return _dt.datetime.fromtimestamp(0).astimezone()


_NODE_COUNT_CACHE: Dict[tuple, Optional[int]] = {}


def cached_node_count(path: str) -> Optional[int]:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    key = (os.path.normcase(os.path.abspath(path)), stat.st_mtime, stat.st_size)
    if key not in _NODE_COUNT_CACHE:
        _NODE_COUNT_CACHE[key] = count_nodes(path)
    return _NODE_COUNT_CACHE[key]


def _size(path: str) -> Optional[int]:
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def build_timeline(script_path: str, store: Optional[SnapshotStore] = None,
                   current: Optional[str] = None) -> List[Entry]:
    """Versions, snapshots and the Nuke autosave for a script, newest first.

    ``current`` is the script open in Nuke, if different from ``script_path``.
    """
    current = current or script_path
    entries: List[Entry] = []
    family = shot_key(script_path)

    for path in find_versions(script_path):
        info = parse_version(path)
        entries.append(Entry(
            type=ENTRY_VERSION,
            path=path,
            time=_mtime(path),
            title=os.path.basename(path),
            version=info.number if info else None,
            is_current=_same_file(path, current),
            family=family,
            size=_size(path),
            nodes=cached_node_count(path),
        ))

    autosave = script_path + ".autosave"
    if os.path.isfile(autosave) and _mtime(autosave) > _mtime(script_path):
        entries.append(Entry(
            type=ENTRY_AUTOSAVE,
            path=autosave,
            time=_mtime(autosave),
            title=os.path.basename(autosave),
            family=family,
            size=_size(autosave),
        ))

    store = store or SnapshotStore(script_path)
    for snap in store.list():
        version = snap.meta.get("source_version")
        title = "v{:03d} snapshot".format(version) if isinstance(version, int) else "Snapshot"
        entries.append(Entry(
            type=ENTRY_SNAPSHOT,
            path=snap.script_path,
            time=snap.created,
            title=title,
            kind=snap.kind,
            version=version,
            note=snap.note,
            tags=snap.tags,
            starred=snap.starred,
            thumbnail=snap.thumbnail_path,
            user=snap.meta.get("user", ""),
            frame=snap.meta.get("frame"),
            snapshot=snap,
            family=family,
            size=snap.meta.get("size") or _size(snap.script_path),
            nodes=snap.meta.get("nodes") if snap.meta.get("nodes") is not None
            else cached_node_count(snap.script_path),
        ))

    entries.sort(key=lambda e: e.time, reverse=True)
    return entries


def script_families(folder: str) -> Dict[str, List[str]]:
    """Scripts in a folder grouped by shot key, each list oldest version first."""
    families: Dict[str, List[str]] = {}
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return families
    for name in names:
        path = os.path.join(folder, name)
        if _is_candidate(name) and os.path.isfile(path):
            families.setdefault(shot_key(path), []).append(path)
    for key, paths in families.items():
        paths.sort(key=lambda p: (parse_version(p).number if parse_version(p) else -1, p))
    return families


def build_folder_timeline(script_path: str) -> List[Entry]:
    """Timeline for every script family in the folder of ``script_path``."""
    folder = os.path.dirname(os.path.abspath(script_path))
    entries: List[Entry] = []
    for paths in script_families(folder).values():
        reference = next((p for p in paths if _same_file(p, script_path)), paths[-1])
        entries.extend(build_timeline(reference, current=script_path))

    unique: Dict[str, Entry] = {}
    for entry in entries:
        unique.setdefault(os.path.normcase(os.path.abspath(entry.path)), entry)
    result = list(unique.values())
    result.sort(key=lambda e: e.time, reverse=True)
    return result


# --------------------------------------------------------------------------
# Work history
# --------------------------------------------------------------------------

@dataclass
class Session:
    start: _dt.datetime
    end: _dt.datetime
    events: int

    @property
    def duration(self) -> _dt.timedelta:
        return self.end - self.start


def work_sessions(times: Iterable[_dt.datetime], gap_minutes: float = 30,
                  minimum_minutes: float = 5) -> List[Session]:
    """Group timestamps into sessions separated by gaps longer than ``gap_minutes``.

    Each session is padded to at least ``minimum_minutes`` so a single save
    still counts as some work. Newest session first.
    """
    stamps = sorted(t.astimezone() for t in times)
    if not stamps:
        return []
    gap = _dt.timedelta(minutes=gap_minutes)
    minimum = _dt.timedelta(minutes=minimum_minutes)
    sessions = []
    start = end = stamps[0]
    count = 1
    for stamp in stamps[1:]:
        if stamp - end > gap:
            sessions.append(Session(start, max(end, start + minimum), count))
            start = stamp
            count = 0
        end = stamp
        count += 1
    sessions.append(Session(start, max(end, start + minimum), count))
    sessions.reverse()
    return sessions


# --------------------------------------------------------------------------
# Node history
# --------------------------------------------------------------------------

HISTORY_FIRST = "first"


@dataclass
class HistorySource:
    label: str
    time: _dt.datetime
    path: Optional[str] = None
    text: Optional[str] = None
    note: str = ""

    def read(self) -> str:
        return self.text if self.text is not None else read_script_text(self.path)


@dataclass
class HistoryEvent:
    source: HistorySource
    status: str
    changes: list = field(default_factory=list)
    #: The node as it was at this source (None when it was removed).
    node: Optional[nkparse.Node] = None
    #: The node just before this source.
    previous: Optional[nkparse.Node] = None


def history_sources(entries: Iterable[Entry], live_text: Optional[str] = None,
                    live_label: str = "Current script") -> List[HistorySource]:
    """Saved states in time order, oldest first, optionally ending with the live script."""
    sources = [HistorySource(e.label, e.time, path=e.path, note=e.note)
               for e in sorted(entries, key=lambda e: e.time)]
    if live_text is not None:
        sources.append(HistorySource(live_label, _now(), text=live_text))
    return sources


_STATE_CACHE: Dict[tuple, tuple] = {}
_PARSE_CACHE: "OrderedDict[str, nkparse.Script]" = OrderedDict()


def _node_state(text: str, path: str):
    """(node or None, connections readable) for ``path`` in script ``text``."""
    digest = hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()
    key = (digest, path)
    if key in _STATE_CACHE:
        return _STATE_CACHE[key]

    short = path.rsplit(".", 1)[-1]
    if short not in text:
        state = (None, True)
    else:
        script = _PARSE_CACHE.get(digest)
        if script is None:
            script = nkparse.parse(text)
            _PARSE_CACHE[digest] = script
            while len(_PARSE_CACHE) > 6:
                _PARSE_CACHE.popitem(last=False)
        else:
            _PARSE_CACHE.move_to_end(digest)
        state = (script.get(path), script.connections_ok)

    if len(_STATE_CACHE) > 5000:
        _STATE_CACHE.clear()
    _STATE_CACHE[key] = state
    return state


def node_history(sources: List[HistorySource], path: str, ignore=nkparse.LAYOUT_KNOBS,
                 progress=None) -> List[HistoryEvent]:
    """How one node changed across ``sources`` (oldest first).

    Returns events oldest first: its earliest state, then every addition,
    removal and change. ``progress(done, total)`` is called before each
    source and may return False to stop early.
    """
    events: List[HistoryEvent] = []
    previous = None
    previous_ok = True
    first_read = True
    total = len(sources)

    for index, source in enumerate(sources):
        if progress is not None and progress(index, total) is False:
            break
        try:
            text = source.read()
        except (OSError, EOFError):
            continue
        node, ok = _node_state(text, path)

        if node is not None and previous is None:
            status = HISTORY_FIRST if first_read else nkparse.ADDED
            events.append(HistoryEvent(source, status, node=node))
        elif node is None and previous is not None:
            events.append(HistoryEvent(source, nkparse.REMOVED, previous=previous))
        elif node is not None and previous is not None:
            changes = nkparse.node_changes(previous, node, ignore, ok and previous_ok)
            if changes:
                events.append(HistoryEvent(source, nkparse.CHANGED, changes, node, previous))
        first_read = False
        previous, previous_ok = node, ok

    if progress is not None:
        progress(total, total)
    return events


# --------------------------------------------------------------------------
# Script text helpers
# --------------------------------------------------------------------------

def _tcl_quote(value: str) -> str:
    value = value.replace("\\", "/")
    if re.search(r"[\s\"\[\]{}$;]", value):
        return '"' + re.sub(r'(["\[\]$\\])', r"\\\1", value) + '"'
    return value


def set_root_name(text: str, path: str) -> str:
    """Point the Root node's ``name`` knob of a script at ``path``."""
    lines = text.splitlines(keepends=True)
    in_root = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not in_root:
            if stripped.startswith("Root {"):
                in_root = True
            continue
        if stripped == "}":
            lines.insert(index, " name {}\n".format(_tcl_quote(path)))
            break
        if re.match(r"^\s*name\s", line):
            newline = "\n" if line.endswith("\n") else ""
            lines[index] = " name {}{}".format(_tcl_quote(path), newline)
            break
    return "".join(lines)


def copy_as_version(source: str, destination: str) -> str:
    """Write ``source`` (.nk or .nk.gz) to ``destination`` with the Root name updated."""
    if os.path.exists(destination):
        raise FileExistsError(destination)
    text = set_root_name(read_script_text(source), os.path.abspath(destination))
    with open(destination, "x", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return destination


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "auto_interval_minutes": 10,
    "keep_automatic": 20,
    "snapshot_on_save": True,
    "thumbnails": True,
    "ask_note": True,
    "hotkey": "ctrl+alt+s",
    "compress_snapshots": True,
}


def settings_path() -> str:
    folder = os.environ.get("SNAPSHOT_BROWSER_HOME") or os.path.join(os.path.expanduser("~"), ".nuke")
    return os.path.join(folder, "snapshot_browser.json")


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(settings_path(), "r", encoding="utf-8") as handle:
            stored = json.load(handle)
        if isinstance(stored, dict):
            settings.update({k: v for k, v in stored.items() if k in DEFAULT_SETTINGS})
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings: dict) -> None:
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write_json(path, {k: settings.get(k, v) for k, v in DEFAULT_SETTINGS.items()})


# --------------------------------------------------------------------------
# OS helpers
# --------------------------------------------------------------------------

def open_folder(path: str) -> None:
    path = os.path.abspath(path)
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def reveal_in_file_browser(path: str) -> None:
    path = os.path.abspath(path)
    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])
