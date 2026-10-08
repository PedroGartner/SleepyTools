"""Backends: what Shell does when you "open" or "integrate".

StandaloneBackend launches Nuke executables; NukeBackend talks to the
running session (and to SnapshotBrowser / SleepyQueue when those tools
are importable). Every integration is optional and fails with a
readable message instead of an exception.
"""

import shutil
import os

from shellcore import launch, naming


class BaseBackend(object):
    can_nuke = False

    def open_script(self, path):
        raise NotImplementedError

    def take_snapshot(self, note=""):
        return False, "Snapshots need a running Nuke session (Snapshot Browser installed)."

    def send_to_sleepy_queue(self):
        return False, "Sending to Sleepy Queue needs a running Nuke session."

    def launch_app(self):
        """'Open Nuke…' on the home screen (standalone launcher only)."""
        executable = _configured_executable()
        if not executable:
            found = launch.find_nuke_executables()
            if not found:
                return False, ("No Nuke executable found. Set it under "
                               "Preferences > Startup > Launching.")
            executable = found[0]
        try:
            launch.launch_nuke_app(executable)
        except (OSError, FileNotFoundError) as exc:
            return False, "Could not launch Nuke: {}".format(exc)
        return True, "Launching Nuke"

    def open_snapshot_browser(self, shot=None):
        """Hand the shot over to the Snapshot Browser tool when available."""
        return False, ("Snapshot Browser runs inside Nuke. Open the shot there "
                       "and use Nuke > Sleepy > Snapshots.")

    def version_up(self, shot):
        """Copy the newest version to the next free one. Pure file work.

        Returns (new_path_or_None, message).
        """
        comp_dir = shot.get("comp_dir")
        latest = _latest_path(comp_dir)
        if not latest:
            return None, "No script to version up yet."
        pattern = _script_pattern(shot)
        next_name = naming.next_version_file(comp_dir, pattern, shot["name"])
        target = os.path.join(comp_dir, next_name)
        try:
            shutil.copyfile(latest, target)  # fresh mtime: newest stays newest
        except OSError as exc:
            return None, "Could not write {}: {}".format(next_name, exc)
        return target, "Saved {}".format(next_name)


class StandaloneBackend(BaseBackend):
    can_nuke = False

    def open_script(self, path):
        executable = _configured_executable()
        if not executable:
            found = launch.find_nuke_executables()
            if not found:
                return False, ("No Nuke executable found. Set it under "
                               "Preferences > Launching.")
            executable = found[0]
        try:
            launch.launch_nuke_with(executable, path)
        except (OSError, FileNotFoundError) as exc:
            return False, "Could not launch Nuke: {}".format(exc)
        return True, "Launching {}".format(os.path.basename(path))

    def open_folder(self, path):
        return launch.open_in_explorer(path)


class NukeBackend(BaseBackend):
    can_nuke = True

    def open_script(self, path):
        import nuke
        current = None
        try:
            current = nuke.root().name()
        except Exception:
            current = None
        if current and current != "Root" and os.path.abspath(current) != os.path.abspath(path):
            dirty = False
            try:
                dirty = bool(nuke.scriptDirty())
            except Exception:
                dirty = True  # unknown state: safer to ask
            if dirty:
                answer = nuke.ask(
                    "The current script has unsaved changes.\n\n"
                    "Save it before opening {}?".format(os.path.basename(path)))
                if answer:
                    nuke.scriptSave()
                # if not answered/declined we continue: Nuke keeps changes in memory
        try:
            nuke.scriptOpen(path)
        except Exception as exc:
            return False, "Could not open script: {}".format(exc)
        return True, "Opened {}".format(os.path.basename(path))

    def open_folder(self, path):
        return launch.open_in_explorer(path)

    def take_snapshot(self, note=""):
        try:
            from snapbrowser import nuke_bridge  # Snapshot Browser installed
        except Exception:
            return False, ("Snapshot Browser is not installed, so snapshots "
                           "cannot be taken from here.")
        try:
            snapshot = nuke_bridge.take_snapshot(note=note, quiet=True)
        except Exception as exc:
            return False, "Snapshot failed: {}".format(exc)
        if snapshot is None:
            return False, "Snapshot was cancelled."
        return True, "Snapshot taken."

    def send_to_sleepy_queue(self):
        try:
            import sleepy_queue_nuke_integration as batch  # installed into ~/.nuke
        except Exception:
            return False, ("Sleepy Queue integration is not installed "
                           "(run its installer once).")
        try:
            batch.send_selected_writes()
        except Exception as exc:
            return False, "Sending to Sleepy Queue failed: {}".format(exc)
        return True, "Selected Write nodes sent to Sleepy Queue."

    def open_snapshot_browser(self, shot=None):
        """Open Snapshot Browser's dockable panel (its public API)."""
        try:
            from snapbrowser import nuke_bridge  # Snapshot Browser installed
        except Exception:
            return False, ("Snapshot Browser is not installed, so it cannot "
                           "be opened from here.")
        try:
            nuke_bridge.show_panel()
        except Exception as exc:
            return False, "Could not open Snapshot Browser: {}".format(exc)
        return True, "Snapshot Browser opened (Nuke > Sleepy > Snapshots)."


# ---------------------------------------------------------------------------
# helpers shared by backends
# ---------------------------------------------------------------------------

def _configured_executable():
    from shellcore import prefs as prefs_mod
    prefs = prefs_mod.load()
    path = prefs.get("nuke_executable", "")
    return path if path and os.path.isfile(path) else None


def _latest_path(comp_dir):
    if not comp_dir or not os.path.isdir(comp_dir):
        return None
    best, best_key = None, (-1, -1)
    try:
        names = os.listdir(comp_dir)
    except OSError:
        return None
    for name in names:
        if not name.lower().endswith(".nk"):
            continue
        number = naming.parse_version_number(name) or 0
        try:
            stamp = os.path.getmtime(os.path.join(comp_dir, name))
        except OSError:
            stamp = 0
        if (number, stamp) > best_key:
            best, best_key = os.path.join(comp_dir, name), (number, stamp)
    return best


def _script_pattern(shot):
    try:
        from shellcore import prefs as prefs_mod
        pattern = prefs_mod.load().get("script_pattern", "{shot}_comp_v###.nk")
    except Exception:
        pattern = "{shot}_comp_v###.nk"
    project_config = shot.get("project_config") or {}
    return project_config.get("script_pattern") or pattern


def make_backend():
    """Pick the backend from the environment (Nuke present or not)."""
    try:
        import nuke  # noqa: F401
        return NukeBackend()
    except ImportError:
        return StandaloneBackend()
