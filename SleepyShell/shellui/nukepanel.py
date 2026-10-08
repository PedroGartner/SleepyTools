"""Sleepy Shell panel for Nuke (docked or floating).

Compact view of the current shot plus the actions that make sense
inside Nuke, laid out like the mockup's Nuke panel: a header strip
with logo + shot + project + status chip, a due/format chip row, a
versions box, a 2-column action grid, the other-shots list and the
notes footer. A guarded 60s timer records work sessions (script path
changes create a new segment); the timer is parented to the panel so a
destroyed panel cannot leave a timer behind.
"""

import os
import time

from SleepyCore.qt import QtCore, QtWidgets

from shellcore import schema
from shellcore.sessions import add_segment
from shellui import theme
from shellui.widgets import Chip, NeutralChip, Thumb, clear_layout


class ShellPanel(QtWidgets.QWidget):
    PANEL_TITLE = "Sleepy Project Manager"

    def __init__(self, parent=None):
        # registerWidgetAsPanel constructs this class with no arguments,
        # so state/backend come from the per-process session singleton.
        super(ShellPanel, self).__init__(parent)
        from shellui.session import get_session
        self.state, self.backend = get_session()
        self._segment_script = None
        self._segment_start = None
        self._current_shot = None
        # the pane root must paint the Shell palette itself: inside Nuke
        # no application stylesheet exists (theme.apply only runs in the
        # standalone launcher), so objectName rules like #ShellPanel and
        # #ShellVersionBox would silently not exist and the panel showed
        # Nuke's colors through — the "transparent panel" bug. The Shell
        # QSS is therefore applied to the panel widget itself; it scopes
        # to this panel's children and never leaks into the host. The
        # "Follow Nuke" theme mode intentionally skips it.
        self.setObjectName("ShellPanel")
        mode = self.state.prefs.get("theme_mode", "dark")
        if mode != "nuke":
            self.setStyleSheet(theme.build_qss(
                self.state.prefs.get("accent", "#f0a043"), mode,
                self.state.prefs.get("density", "comfortable"),
                int(self.state.prefs.get("font_size", 12) or 12)))

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.current_box = QtWidgets.QVBoxLayout()
        self.current_box.setSpacing(8)
        layout.addLayout(self.current_box)

        self.actions_box = QtWidgets.QGridLayout()
        self.actions_box.setSpacing(7)
        layout.addLayout(self.actions_box)

        self.other_box = QtWidgets.QVBoxLayout()
        self.other_box.setSpacing(2)
        layout.addLayout(self.other_box, 1)

        self.refresh_timer = QtCore.QTimer(self)   # parented: dies with the panel
        self.refresh_timer.setInterval(60 * 1000)
        self.refresh_timer.timeout.connect(self._on_tick)
        self.refresh_timer.start()

        self.reload()

    # ------------------------------------------------------------------
    # session recording
    # ------------------------------------------------------------------
    def _on_tick(self):
        self._record_segment()
        self.reload(lights=True)

    def _record_segment(self):
        script = self._current_script()
        now = time.time()
        if self._segment_script and self._segment_script != script:
            add_segment(self._segment_script, self._segment_start or now, now)
            self._segment_start = now
        elif self._segment_script is None:
            self._segment_start = now
        self._segment_script = script

    def _current_script(self):
        try:
            import nuke
            name = nuke.root().name() or ""
        except Exception:
            return None
        if not name or name == "Root":
            return None
        return os.path.abspath(name)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def reload(self, lights=False):
        if not lights:
            clear_layout(self.current_box)
            self._fill_current()
            self._fill_actions()
        self._fill_others()

    def _shot_for_script(self, script):
        if not script:
            return None
        if not self.state.shots:
            self.state.refresh(force=False)
        for shot in self.state.shots:
            comp = shot.get("comp_dir") or ""
            if comp and script.lower().startswith(comp.lower() + os.sep):
                return shot
        return None

    def _fill_current(self):
        script = self._current_script()
        shot = self._shot_for_script(script)
        if shot is None:
            note = QtWidgets.QLabel(
                "The current script is not inside a managed or discovered shot.\n\n"
                "Open a shot from the Board, or move this script into a shot's "
                "comp folder (project folder structure: <project>/shots/<shot>/comp).")
            note.setObjectName("ShellDim")
            note.setWordWrap(True)
            self.current_box.addWidget(note)
            return
        # header strip: logo + shot name + project + status chip
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)
        logo = QtWidgets.QLabel("G")
        logo.setFixedSize(16, 16)
        logo.setAlignment(QtCore.Qt.AlignCenter)
        logo.setStyleSheet(
            "background: {}; color: #161719; font-weight: 700; font-size: 10px;"
            " border-radius: 3px;".format(self.state.prefs.get("accent", "#f0a043")))
        header.addWidget(logo)
        title = QtWidgets.QLabel(shot["name"] + "_comp")
        title.setStyleSheet("font-weight: 600; font-size: 12.5px; background: transparent;")
        header.addWidget(title)
        project = QtWidgets.QLabel(shot.get("project_name", ""))
        project.setObjectName("ShellDim")
        project.setStyleSheet("font-size: 11px; background: transparent;")
        header.addWidget(project)
        header.addStretch(1)
        header.addWidget(Chip(schema.STATUS_LABELS.get(shot.status, shot.status),
                              theme.status_color(shot.status)))
        self.current_box.addLayout(header)

        # due / format chip row
        meta = QtWidgets.QHBoxLayout()
        meta.setSpacing(7)
        due = (shot.get("config") or {}).get("due")
        if due:
            from datetime import date
            try:
                days = (date.fromisoformat(due) - date.today()).days
                if days < 0:
                    meta.addWidget(Chip("due {}d overdue".format(-days),
                                        theme.status_color("hold")))
                elif days <= 3:
                    meta.addWidget(Chip("due in {}d".format(max(days, 0)),
                                        theme.status_color("wip")))
                else:
                    meta.addWidget(Chip("due " + due, theme.status_color("wip")))
            except ValueError:
                meta.addWidget(Chip("due " + due, theme.status_color("wip")))
        project_cfg = (self.state.project_for(shot) or {}).get("config") or {}
        bits = []
        if project_cfg.get("fps"):
            bits.append("{} fps".format(project_cfg["fps"]))
        if project_cfg.get("working_space"):
            bits.append(project_cfg["working_space"])
        if bits:
            meta.addWidget(NeutralChip(" · ".join(bits)))
        meta.addStretch(1)
        self.current_box.addLayout(meta)

        # versions box (nkvers)
        from shellcore.versions import latest_version
        entries = self.state.shot_versions(shot)
        if entries:
            label = QtWidgets.QLabel("VERSIONS")
            label.setObjectName("ShellDim")
            from shellui.widgets import set_section_font
            set_section_font(label, size=9.5, spacing=1.1)
            self.current_box.addWidget(label)
            box = QtWidgets.QFrame()
            box.setObjectName("ShellVersionBox")
            box_layout = QtWidgets.QVBoxLayout(box)
            box_layout.setContentsMargins(4, 4, 4, 4)
            box_layout.setSpacing(1)
            for index, entry in enumerate(entries[:3]):
                row = QtWidgets.QFrame()
                row.setObjectName("ShellVRow")
                if index == 0:
                    row.setProperty("cur", True)
                h = QtWidgets.QHBoxLayout(row)
                h.setContentsMargins(6, 4, 6, 4)
                h.setSpacing(9)
                h.addWidget(Thumb(shot["name"], None, (64, 30), radius=3, font_px=9))
                version_label = QtWidgets.QLabel("v{:03d}".format(entry["number"]))
                version_label.setStyleSheet("font-weight: 600; background: transparent;")
                version_label.setFixedWidth(48)
                h.addWidget(version_label)
                vm_bits = []
                if index == 0:
                    vm_bits.append("open")
                from shellcore.versions import render_records
                if any((r.get("render") or {}).get("status") == "done"
                       for r in render_records(self.state.shot_snapshots(shot))
                       if (r.get("render") or {}).get("version") == entry["number"]):
                    vm_bits.append("rendered ✓")
                vm = QtWidgets.QLabel(" · ".join(vm_bits) or
                                      _panel_rel_time(entry["mtime"]))
                vm.setObjectName("ShellDim")
                vm.setStyleSheet("font-size: 11px; background: transparent;")
                h.addWidget(vm, 1)
                box_layout.addWidget(row)
            self.current_box.addWidget(box)

        notes = (shot.get("config") or {}).get("notes")
        if notes:
            note_label = QtWidgets.QLabel(
                "<b style='color:#e6e6e6;'>Notes:</b> "
                "<span style='color:#9a9ea6;'>{}</span>".format(_escape(notes[:160])))
            note_label.setTextFormat(QtCore.Qt.RichText)
            note_label.setWordWrap(True)
            note_label.setStyleSheet("font-size: 11px; background: transparent;"
                                     " border-top: 1px solid #2a2c30;"
                                     " padding-top: 8px;")
            self.current_box.addWidget(note_label)
        self._current_shot = shot

    def _fill_actions(self):
        from shellui import icons
        shot = getattr(self, "_current_shot", None)
        if shot is None:
            return
        actions = (
            ("Open Latest", "open", self._open_latest),
            ("Version Up", "film", self._version_up),
            ("To SleepyQueue", "send", self._send_batch),
            ("Snapshot", "camera", self._snapshot),
            ("Folder", "folder", self._open_folder),
        )
        for index, (label, icon_name, handler) in enumerate(actions):
            button = QtWidgets.QPushButton(" " + label)
            button.setIcon(icons.icon(icon_name, size=12))
            button.setStyleSheet("font-size: 11px; padding: 4px 9px;")
            button.clicked.connect(handler)
            self.actions_box.addWidget(button, index // 2, index % 2)
        self.actions_box.setColumnStretch(0, 1)
        self.actions_box.setColumnStretch(1, 1)

    def _fill_others(self):
        clear_layout(self.other_box)
        script = self._current_script()
        current = self._shot_for_script(script)
        label = QtWidgets.QLabel("OTHER SHOTS · {}".format(
            (current or {}).get("project_name", "all projects")))
        label.setObjectName("ShellDim")
        from shellui.widgets import set_section_font
        set_section_font(label, size=9.5, spacing=1.1)
        self.other_box.addWidget(label)
        shown = 0
        for shot in self.state.shots:
            if current is not None and shot["path"] == current["path"]:
                continue
            if shot.status in ("delivered",) and not self.state.prefs.get("show_delivered", True):
                continue
            row = QtWidgets.QFrame()
            row.setObjectName("ShellRow")
            row.setCursor(QtCore.Qt.PointingHandCursor)
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(6, 3, 6, 3)
            row_layout.setSpacing(8)
            row_layout.addWidget(Thumb(shot["name"], None, (40, 24), radius=2,
                                       font_px=8))
            name = QtWidgets.QLabel(shot["name"] + "_comp")
            name.setStyleSheet("font-weight: 600; font-size: 11.5px;"
                               " background: transparent;")
            row_layout.addWidget(name, 1)
            row_layout.addWidget(Chip(schema.STATUS_LABELS.get(shot.status, shot.status),
                                      theme.status_color(shot.status)))
            version = QtWidgets.QLabel("v{:03d}".format(_panel_version(shot)))
            version.setObjectName("ShellDim")
            version.setStyleSheet("font-size: 10.5px; background: transparent;")
            row_layout.addWidget(version)
            row._shell_shot = shot
            row.installEventFilter(self)
            self.other_box.addWidget(row)
            shown += 1
            if shown >= 12:
                break
        self.other_box.addStretch(1)

    def eventFilter(self, source, event):
        shot = getattr(source, "_shell_shot", None)
        if shot is not None and event.type() == QtCore.QEvent.MouseButtonDblClick:
            self.state.remember_open(shot)
            ok, message = self.backend.open_script(_latest_path(shot))
            if not ok:
                QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)
            return True
        return super(ShellPanel, self).eventFilter(source, event)

    # ------------------------------------------------------------------
    def _open_latest(self):
        shot = getattr(self, "_current_shot", None)
        if shot is None:
            return
        from shellcore.versions import latest_version
        entry = latest_version(shot.get("comp_dir"))
        if entry is None:
            QtWidgets.QMessageBox.information(
                self, "Sleepy Shell", "This shot has no scripts yet.")
            return
        self.state.remember_open(shot)
        ok, message = self.backend.open_script(entry["path"])
        if not ok:
            QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)

    def _version_up(self):
        shot = getattr(self, "_current_shot", None)
        if shot is None:
            return
        new_path, message = self.backend.version_up(shot)
        QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)

    def _snapshot(self):
        ok, message = self.backend.take_snapshot()
        QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)

    def _send_batch(self):
        ok, message = self.backend.send_to_sleepy_queue()
        QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)

    def _open_folder(self):
        shot = getattr(self, "_current_shot", None)
        if shot is None:
            return
        ok, message = self.backend.open_folder(shot["path"])
        if not ok:
            QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)


def _latest_path(shot):
    from shellcore.versions import latest_version
    entry = latest_version(shot.get("comp_dir"))
    return entry["path"] if entry else None


def _panel_version(shot):
    from shellcore.versions import latest_version
    entry = latest_version(shot.get("comp_dir"))
    return entry["number"] if entry else 0


def _panel_rel_time(stamp):
    from datetime import date
    if not stamp:
        return ""
    days = (date.today() - date.fromtimestamp(stamp)).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return "{} days ago".format(days)


def _escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))
