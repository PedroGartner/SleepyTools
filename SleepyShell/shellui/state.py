"""Application state for Sleepy Shell.

One object holding prefs, the scanned portfolio and the current
selection, with Qt signals so pages stay in sync. All filesystem work
delegates to shellcore.
"""

from SleepyCore.qt import QtCore

from shellcore import prefs as prefs_mod
from shellcore import recents, scan, search, versions
from shellcore.schema import STATUS_ORDER


class ShotItem(dict):
    """A shot dict enriched with project info and derived data.

    Regular dict so the core stays serializable; the UI only reads.
    """

    @property
    def status(self):
        return (self.get("config") or {}).get("status", "wip")


class AppState(QtCore.QObject):
    projectsChanged = QtCore.Signal()
    prefsChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super(AppState, self).__init__(parent)
        self.prefs = prefs_mod.load()
        self.projects = []
        self.root_states = {}
        self.from_cache = False
        self.shots = []          # flattened ShotItems with project info attached
        self.current_project = None   # project path filter, None = all
        self.last_error = None

    # -- prefs ------------------------------------------------------------
    def save_prefs(self):
        prefs_mod.save(self.prefs)
        self.prefsChanged.emit()

    # -- scanning -----------------------------------------------------------
    def refresh(self, force=False):
        try:
            projects, states, from_cache = scan.cached_scan(self.prefs, force=force)
        except Exception as exc:  # never let a scan kill the UI
            self.projects, self.root_states, self.from_cache = [], {}, False
            self.last_error = str(exc)
            self.projectsChanged.emit()
            return
        self.projects = projects
        self.root_states = states
        self.from_cache = from_cache
        self.last_error = None
        self._reload_shots()
        self.projectsChanged.emit()

    def _reload_shots(self):
        from shellcore.schema import load_shot, load_project
        items = []
        for project in self.projects:
            config, error = load_project(project["path"])
            if error:
                project["error"] = error
            project["config"] = config
            for shot in scan.scan_shots(project["path"]):
                shot_config, shot_error = load_shot(shot["path"])
                if shot_error:
                    shot["error"] = shot_error
                item = ShotItem(shot)
                item["config"] = shot_config
                item["project_name"] = project["name"]
                item["project_client"] = config.get("client", "")
                item["project_color"] = config.get("color")
                item["project_managed"] = project["managed"]
                # project-level settings (naming overrides etc.) travel with
                # every shot item so backends can honor them per project
                item["project_config"] = config
                items.append(item)
        self.shots = items

    # -- lookups ------------------------------------------------------------
    def project_for(self, shot):
        path = shot.get("project_path")
        for project in self.projects:
            if project["path"] == path:
                return project
        return None

    def shot_by_path(self, path):
        norm = (path or "").lower()
        for shot in self.shots:
            if shot["path"].lower() == norm:
                return shot
        return None

    def visible_shots(self, text="", due_days=None, include_discovered=True,
                      include_delivered=True):
        from datetime import date, timedelta
        results = search.search_shots(self.shots, text, project=self.current_project)
        if not include_discovered:
            results = [s for s in results if s.get("managed")]
        if not include_delivered:
            results = [s for s in results
                       if s.status not in ("delivered",)]
        if due_days is not None:
            today = date.today()
            horizon = today + timedelta(days=due_days)
            def due_ok(shot):
                raw = (shot.get("config") or {}).get("due")
                if not raw:
                    return False
                try:
                    when = date.fromisoformat(raw)
                except ValueError:
                    return False
                return when <= horizon
            results = [s for s in results if due_ok(s)]
        return results

    def due_sort_key(self, shot):
        raw = (shot.get("config") or {}).get("due")
        try:
            return (0, raw or "9999-99-99")
        except TypeError:
            return (1, "")

    # -- recents ------------------------------------------------------------
    def recent_shots(self, limit=8):
        entries = recents.list_recents(limit=limit)
        items = []
        for entry in entries:
            shot = self.shot_by_path(entry["path"])
            if shot is not None:
                items.append(shot)
        return items

    def remember_open(self, shot):
        recents.remember(shot["path"], shot.get("comp_dir") or "")

    # -- per-shot data ------------------------------------------------------
    def shot_versions(self, shot):
        return versions.list_versions(shot.get("comp_dir"))

    def shot_snapshots(self, shot):
        return versions.snapshots_for(shot["path"], shot.get("comp_dir"))

    def shot_thumbnails(self, shot, limit=3):
        return versions.thumbnails_for(shot["path"], shot.get("comp_dir"), limit=limit)

    def grouped_by_status(self, shots):
        groups = {}
        for status in STATUS_ORDER:
            groups[status] = []
        for shot in shots:
            groups.setdefault(shot.status, []).append(shot)
        return groups
