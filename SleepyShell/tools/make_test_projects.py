"""Generate a realistic fake portfolio for testing Sleepy Shell's layout.

    python tools/make_test_projects.py [root] [--force]

Default root: ~/SleepyTestProjects

Creates three projects using the suite's own creation code (ops.py), so
the generated tree is exactly what Sleepy Shell writes in production:

- ClientX_Campaign    managed, 6 shots, mixed statuses, versions,
                      snapshots with REAL thumbnail JPEGs, render
                      records and session time
- MuseumRide_Fulldome managed, 3 shots, delivered/approved heavy
- ClientY_Legacy      DISCOVERED (no project.json / shot.json) —
                      exercises the "discovered" chip and Adopt dialog

The fixture .nk files are plain-text placeholders, deliberately NOT
valid Nuke scripts (they are marked as such inside); they exist so the
version lists have realistic sizes and dates. Do not open them in Nuke.

Also writes session segments and recents into the local per-user
SleepyTools caches so "Time on this shot" and the home hero show —
delete %LOCALAPPDATA%\\SleepyTools\\sleepy_shell_sessions.json /
sleepy_shell_recents.json to remove those again.
"""

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOL_DIR = os.path.dirname(_HERE)
_SUITE_PARENT = os.path.dirname(_TOOL_DIR)
for _path in (_TOOL_DIR, _SUITE_PARENT):
    if _path not in sys.path:
        sys.path.append(_path.replace("\\", "/"))

DEFAULT_ROOT = os.path.join(os.path.expanduser("~"), "SleepyTestProjects")

FIXTURE_HEADER = (
    "# Sleepy Shell layout-test fixture.\n"
    "# NOT a real Nuke script - do not open this in Nuke.\n")

_now = time.time()
_DAY = 86400.0


def _fixture(path, days_ago, size_kb):
    """Write a placeholder script with a specific age and size."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = FIXTURE_HEADER + ("# padding line for size\n" * max(1, int(size_kb * 40)))
    with open(path, "w", encoding="ascii") as fh:
        fh.write(body)
    stamp = _now - days_ago * _DAY
    os.utime(path, (stamp, stamp))


def _thumb_jpeg(path, label, hue):
    """Render a real small JPEG thumbnail via Qt (offscreen)."""
    try:
        from SleepyCore.qt import QtWidgets, QtGui, QtCore
    except Exception:
        return False
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    pix = QtGui.QPixmap(320, 180)
    pix.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pix)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    gradient = QtGui.QLinearGradient(0, 0, 320, 180)
    gradient.setColorAt(0, QtGui.QColor.fromHsl(hue, 110, 42))
    gradient.setColorAt(1, QtGui.QColor.fromHsl((hue + 40) % 360, 90, 72))
    path_item = QtGui.QPainterPath()
    path_item.addRect(0, 0, 320, 180)
    painter.fillPath(path_item, gradient)
    painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 200)))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(44)
    painter.setFont(font)
    painter.drawText(pix.rect(), QtCore.Qt.AlignCenter, label)
    painter.end()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return pix.save(path, "JPG", 85)


def _snapshot(shot_dir, comp_dir, base, when_days_ago, note, kind, label,
              hue, render=None, starred=False):
    """Write one snapshot/1 fixture: meta.json + thumbnail + script copy."""
    from shellcore.schema import save_json_atomic
    snap_root = os.path.join(comp_dir, ".snapshots")
    folder = os.path.join(
        snap_root, "{}_{:08d}_{:04d}".format(base, int(when_days_ago * 24), hue % 10000))
    os.makedirs(folder, exist_ok=True)
    thumb = os.path.join(folder, "thumb.jpg")
    have_thumb = _thumb_jpeg(thumb, label, hue)
    script_copy = os.path.join(folder, base + "_v999.nk")
    with open(script_copy, "w", encoding="ascii") as fh:
        fh.write(FIXTURE_HEADER)
    meta = {
        "format": "snapshot/1",
        "id": "{:08d}{:04d}".format(int(when_days_ago * 24), hue % 10000),
        "kind": kind,
        "created": time.strftime(
            "%Y-%m-%dT%H:%M:%S+02:00", time.localtime(_now - when_days_ago * _DAY)),
        "note": note,
        "tags": [],
        "starred": bool(starred),
        "script": os.path.basename(script_copy),
        "thumbnail": "thumb.jpg" if have_thumb else None,
        "compressed": False,
        "hash": "fixture{:04d}".format(hue % 10000),
        "size": os.path.getsize(script_copy),
        "nodes": 42 + (hue % 180),
        "source_script": os.path.join(comp_dir, base + "_v001.nk"),
        "source_version": "v001",
        "frame": 1001,
        "user": os.environ.get("USERNAME", "test"),
        "host": "fixture",
        "app": "Sleepy Shell fixture",
    }
    if render:
        meta["render"] = render
    save_json_atomic(os.path.join(folder, "meta.json"), meta)
    stamp = _now - when_days_ago * _DAY
    os.utime(os.path.join(folder, "meta.json"), (stamp, stamp))
    return meta


def _versions(comp_dir, base, pattern, versions):
    """versions: list of (number, days_ago, size_kb)."""
    from shellcore.naming import script_name
    for number, days_ago, size_kb in versions:
        name = script_name(pattern, base, number)
        _fixture(os.path.join(comp_dir, name), days_ago, size_kb)


def make(root, sessions=True, recents=True):
    from shellcore import ops
    from shellcore.schema import save_shot
    from shellcore import sessions as sessions_mod, recents as recents_mod

    if os.path.isdir(root) and os.listdir(root):
        print("ABORT: {} exists and is not empty (use --force to wipe).".format(root))
        return False
    os.makedirs(root, exist_ok=True)

    # -- Project 1: ClientX_Campaign (managed, rich) ----------------------
    p1 = ops.create_project(root, "ClientX_Campaign", {
        "client": "ClientX Studios", "fps": 25, "resolution": "3840x2160",
        "working_space": "ACEScg", "handles": 8,
        "render_output": "D:\\Projects\\ClientX_Campaign\\renders\\{shot}\\",
    })
    shots = {}

    def new_shot(name, status=None, due=None, priority=None, tags=None, notes=None):
        shot_dir, _ = ops.create_shot(p1, name, {}, {"comp_template": ""})
        config = {}
        if status:
            config["status"] = status
        if due:
            config["due"] = due
        if priority:
            config["priority"] = priority
        if tags:
            config["tags"] = tags
        if notes:
            config["notes"] = notes
        if config:
            save_shot(shot_dir, config)
        shots[name] = shot_dir
        return shot_dir

    new_shot("sh010", status="delivered",
             tags=["beauty"], notes="Delivered EXR + ProRes on Oct 1.")
    new_shot("sh012", status="review", due=_iso(2), tags=["review"],
             notes="Sent to client Monday, waiting for notes.")
    new_shot("sh031", status="wip", due=_iso(4), priority=1,
             tags=["beauty", "keying"],
             notes="Waiting for updated plates from client (v3 expected Friday).\n"
                   "Keep the keying setup from v014 - client approved that despill.")
    new_shot("sh034", status="wip", due=_iso(6), priority=2,
             tags=["cleanup"], notes="Beer can cleanup, use the new denoiser.")
    new_shot("sh045", status="approved", tags=["approved"],
             notes="Signed off by supervisor.")
    new_shot("sh052", status="hold", notes="Waiting on client decision.")

    import datetime
    p1_config, _ = load_project(p1)
    pattern = p1_config.get("script_pattern") or "{shot}_comp_v###.nk"

    def comp(name):
        return os.path.join(shots[name], "comp")

    # sh031: three versions, snapshots with thumbs, one render record
    _versions(comp("sh031"), "sh031", pattern,
              [(1, 9, 1.4), (2, 4, 1.8), (3, 1, 2.1)])
    _snapshot(shots["sh031"], comp("sh031"), "sh031_comp", 4.2,
              "despill rework", "manual", "sh031", 30, starred=True)
    _snapshot(shots["sh031"], comp("sh031"), "sh031_comp", 1.1,
              "before plate update", "auto", "sh031", 31)
    _snapshot(shots["sh031"], comp("sh031"), "sh031_comp", 2.0,
              "final v002", "render", "sh031", 32,
              render={"frame_range": "1001-1148", "write_node": "Write_beauty",
                      "output": r"D:\Projects\ClientX_Campaign\renders\sh031\sh031_comp_v002.####.exr",
                      "status": "done"})
    _snapshot(shots["sh031"], comp("sh031"), "sh031_comp", 2.05,
              "matte pass", "render", "sh031", 33,
              render={"frame_range": "1001-1148", "write_node": "Write_matte",
                      "output": r"D:\Projects\ClientX_Campaign\renders\sh031\matte\sh031_matte_v002.####.exr",
                      "status": "done"})

    # sh034: two versions + an auto snapshot
    _versions(comp("sh034"), "sh034", pattern, [(1, 6, 1.1), (2, 2, 1.3)])
    _snapshot(shots["sh034"], comp("sh034"), "sh034_comp", 2.2,
              "before roto redo", "auto", "sh034", 40)

    # sh010: one old version (delivered)
    _versions(comp("sh010"), "sh010", pattern, [(1, 21, 2.6)])

    # sh045: two versions
    _versions(comp("sh045"), "sh045", pattern, [(1, 8, 1.5), (2, 5, 1.7)])

    # sh052 / sh012: empty comps (show the no-scripts states)

    # -- Project 2: MuseumRide_Fulldome (managed, delivery-heavy) ---------
    p2 = ops.create_project(root, "MuseumRide_Fulldome", {
        "client": "Naturkundemuseum", "fps": 30, "resolution": "4096x4096",
        "working_space": "ACEScg",
    })
    for name, status, days in (("mr080", "delivered", 14), ("mr085", "approved", 9),
                               ("mr090", "review", 2)):
        shot_dir, _ = ops.create_shot(p2, name, {}, {"comp_template": ""})
        save_shot(shot_dir, {"status": status,
                             "notes": "Fulldome {} shot.".format(name)})
        _versions(os.path.join(shot_dir, "comp"), name, "{shot}_comp_v###.nk",
                  [(1, days + 4, 2.2), (2, days + 1, 2.8)])

    # -- Project 3: ClientY_Legacy (DISCOVERED: no metadata at all) -------
    p3 = os.path.join(root, "ClientY_Legacy")
    for name, days in (("ly010", 30), ("ly020", 12)):
        comp_dir = os.path.join(p3, name, "comp")
        _fixture(os.path.join(comp_dir, "{}_comp_v001.nk".format(name)),
                 days, 1.2)
    # a stray folder that must be ignored by the scanner
    os.makedirs(os.path.join(root, "ClientY_Legacy", "docs"))

    # -- sessions + recents (local caches, disclosed) ----------------------
    if sessions:
        for name in ("sh031", "sh034", "sh012"):
            for days_ago, hours in ((0, 2.5), (1, 1.8), (3, 3.2)):
                start = _now - days_ago * _DAY - hours * 3600
                sessions_mod.add_segment(
                    os.path.join(comp(name) if name != "sh012" else
                                 os.path.join(shots[name], "comp"),
                                 "{}_comp_v001.nk".format(name)),
                    start, start + hours * 3600,
                    shot_path=shots[name], project_path=p1)
    if recents:
        for name in ("sh034", "sh031", "sh012"):
            recents_mod.remember(shots[name],
                                 comp(name) if name != "sh012" else
                                 os.path.join(shots[name], "comp"))

    print("Portfolio created at", root)
    print("  ClientX_Campaign   managed · 6 shots (versions, snapshots, renders, sessions)")
    print("  MuseumRide_Fulldome managed · 3 shots (delivery-heavy)")
    print("  ClientY_Legacy     discovered · 2 shots (no metadata -> try Adopt)")
    return True


def _iso(days_from_now):
    import datetime
    return (datetime.date.today() +
            datetime.timedelta(days=days_from_now)).isoformat()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = args[0] if args else DEFAULT_ROOT
    if "--force" in sys.argv[1:] and os.path.isdir(root):
        import shutil
        shutil.rmtree(root)
    sys.exit(0 if make(root) else 1)
