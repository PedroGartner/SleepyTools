"""Write operations: create projects/shots, adopt, unmanage.

Data-safety rules:
- Create never overwrites: an existing project/shot folder aborts the
  operation with FileExistsError instead of merging into it.
- Adopt writes one shot.json and nothing else - no moves, no renames.
- Unmanage deletes ONLY shot.json files that carry our own format
  marker, verified by reading each file before deleting.
- All metadata writes go through schema.save_* (atomic).
"""

import os
import shutil

from shellcore import naming
from shellcore import prefs as prefs_mod
from shellcore.schema import (SHOT_FILE, PROJECT_FILE,
                              load_json, save_shot, save_project, is_our_shot_config)


class OpError(Exception):
    """User-presentable operation failure."""


def _ensure_absent(path, label):
    if os.path.exists(path):
        raise OpError("{} already exists: {}".format(label, path))


def create_project(root, name, config=None, folder_template=None):
    """Create <root>/<name>/ with project.json and a shots/ folder."""
    name = naming.sanitize_name(name or "").strip()
    if not name:
        raise OpError("Project name is empty")
    _ensure_absent(os.path.join(root, name), "Project folder")
    project_dir = os.path.join(root, name)
    try:
        os.makedirs(os.path.join(project_dir, "shots"))
    except OSError as exc:
        raise OpError("Could not create project folder: {}".format(exc))
    data = dict(config or {})
    data["name"] = name
    try:
        save_project(project_dir, data)
    except OSError as exc:
        raise OpError("Could not write project.json: {}".format(exc))
    return project_dir


def create_shot(project_path, shot_name=None, prefs=None, project_config=None):
    """Create a new shot folder from the template, with v001 if a comp template exists.

    Returns (shot_dir, script_path_or_None). Without an explicit name the
    next free name follows the shot pattern.
    """
    prefs = prefs or {}
    project_config = project_config or {}
    shot_pattern = project_config.get("shot_pattern") or prefs.get("shot_pattern", "sh###")
    script_pattern = project_config.get("script_pattern") or prefs.get("script_pattern",
                                                                       "{shot}_comp_v###.nk")
    shots_dir = os.path.join(project_path, "shots")
    if not os.path.isdir(shots_dir):
        shots_dir = project_path  # projects created outside the suite may have no shots/ layer
    if not shot_name:
        highest = naming.highest_shot_number(shots_dir, shot_pattern)
        shot_name = naming.expand_shot_name(shot_pattern, highest + 1)
    else:
        shot_name = naming.sanitize_name(shot_name)
    shot_dir = os.path.join(shots_dir, shot_name)
    _ensure_absent(shot_dir, "Shot folder")
    try:
        os.makedirs(shot_dir)
    except OSError as exc:
        raise OpError("Could not create shot folder: {}".format(exc))

    template = project_config.get("folder_template", "standard")
    if template == "standard":
        folders = (prefs.get("folder_template")
                   or prefs_mod.PREFS_DEFAULTS["folder_template"])
    else:
        folders = []  # client structure: only the shot folder itself
    for folder in folders:
        try:
            os.makedirs(os.path.join(shot_dir, folder))
        except OSError as exc:
            raise OpError("Could not create {}: {}".format(folder, exc))

    script_path = None
    if folders and "comp" in folders:
        comp_dir = os.path.join(shot_dir, "comp")
        template_nk = project_config.get("comp_template") or ""
        if template_nk and os.path.isfile(template_nk):
            # Only copy a user-provided template; we never fabricate .nk
            # content ourselves, because the on-disk script format belongs
            # to Nuke. Shots without a template simply start with an
            # empty comp folder.
            target = os.path.join(comp_dir, naming.script_name(script_pattern, shot_name, 1))
            try:
                shutil.copyfile(template_nk, target)
                script_path = target
            except OSError as exc:
                raise OpError("Could not copy comp template: {}".format(exc))

    # seed shot.json so the new shot is managed from birth
    try:
        save_shot(shot_dir, {"status": "wip"})
    except OSError as exc:
        raise OpError("Could not write shot.json: {}".format(exc))
    return shot_dir, script_path


def duplicate_shot(source_shot_dir, new_name=None, prefs=None,
                   project_config=None):
    """Create a new shot from an existing one: same folder template, the
    source's latest comp copied in as v001 (fresh file), tags carried
    over, status reset to wip, notes recording the origin.

    Returns (shot_dir, script_path). Never touches the source.
    """
    prefs = prefs or {}
    project_config = project_config or {}
    parent = os.path.dirname(os.path.abspath(source_shot_dir))
    from shellcore.schema import load_shot
    source_config, _ = load_shot(source_shot_dir)

    if not new_name:
        shot_pattern = project_config.get("shot_pattern") or prefs.get(
            "shot_pattern", "sh###")
        # start from highest+1 (next_shot_name is collision-only and would
        # happily return sh001 next to sh010)
        highest = naming.highest_shot_number(parent, shot_pattern)
        new_name = naming.expand_shot_name(shot_pattern, highest + 1)
    else:
        new_name = naming.sanitize_name(new_name)

    shot_dir, script_path = create_shot(
        parent, new_name, prefs, project_config)

    # copy the source's latest version in as the new shot's v001
    source_comp = os.path.join(source_shot_dir, "comp")
    latest, latest_key = None, (-1, -1)
    if os.path.isdir(source_comp):
        for entry in os.listdir(source_comp):
            if not entry.lower().endswith(".nk"):
                continue
            number = naming.parse_version_number(entry) or 0
            path = os.path.join(source_comp, entry)
            try:
                stamp = os.path.getmtime(path)
            except OSError:
                stamp = 0
            if (number, stamp) > latest_key:
                latest, latest_key = path, (number, stamp)
    new_comp = os.path.join(shot_dir, "comp")
    if latest and os.path.isdir(new_comp):
        target = os.path.join(new_comp, naming.script_name(
            project_config.get("script_pattern") or prefs.get(
                "script_pattern", "{shot}_comp_v###.nk"), new_name, 1))
        try:
            shutil.copyfile(latest, target)  # fresh mtime: newest stays newest
            script_path = target
        except OSError as exc:
            raise OpError("Could not copy the comp: {}".format(exc))

    carried = {
        "tags": list(source_config.get("tags", [])),
        "notes": "Duplicated from {}".format(os.path.basename(source_shot_dir)),
    }
    try:
        save_shot(shot_dir, carried)
    except OSError as exc:
        raise OpError("Could not write shot.json: {}".format(exc))
    return shot_dir, script_path


def adopt_shot(shot_dir, defaults=None):
    """Write a shot.json into a discovered shot folder. Nothing else changes."""
    if not os.path.isdir(shot_dir):
        raise OpError("Shot folder not found: {}".format(shot_dir))
    config = dict(defaults or {})
    try:
        save_shot(shot_dir, config)
    except OSError as exc:
        raise OpError("Could not write shot.json: {}".format(exc))
    return os.path.join(shot_dir, SHOT_FILE)


def adopt_shots(shot_dirs, defaults=None):
    """Adopt many shots; returns (adopted, failures)."""
    adopted, failures = [], []
    for shot_dir in shot_dirs:
        try:
            adopt_shot(shot_dir, defaults)
            adopted.append(shot_dir)
        except OpError as exc:
            failures.append(str(exc))
    return adopted, failures


def unmanage_project(project_path, delete_project_json=False):
    """Remove PM metadata from a project.

    Deletes every shot.json that carries our format marker (verified by
    reading the file). Anything else on disk is untouched. When
    ``delete_project_json`` is set, project.json is removed the same
    verified way.
    """
    removed = 0
    for dirpath, dirnames, filenames in os.walk(project_path):
        if SHOT_FILE in filenames:
            path = os.path.join(dirpath, SHOT_FILE)
            if is_our_shot_config(path):
                try:
                    os.remove(path)
                except OSError as exc:
                    raise OpError("Could not remove {}: {}".format(path, exc))
                removed += 1
    if delete_project_json:
        path = os.path.join(project_path, PROJECT_FILE)
        data = load_json(path)
        if data and data.get("format") == "sleepy-project/1":
            try:
                os.remove(path)
            except OSError as exc:
                raise OpError("Could not remove {}: {}".format(path, exc))
    return removed
