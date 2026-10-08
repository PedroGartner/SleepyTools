"""Shot detail page: metadata, notes, versions, snapshots, renders, time.

Layout follows the mockup: breadcrumb, header with status picker and
due/priority/tags chips, a 330px left column with the big thumb and a
2x2 action grid, and stacked panels (notes, versions, snapshots,
renders, time-on-shot with the accent week bars, shot settings).
"""

import os
from datetime import date, timedelta

from SleepyCore.qt import QtCore, QtGui, QtWidgets

from shellcore import schema
from shellcore.schema import STATUS_LABELS, STATUS_ORDER
from shellui import theme
from shellui.widgets import (Chip, EmptyState, MetaChip, NeutralChip, Section,
                             Thumb, WeekBars, clear_layout, styled)


class ShotPage(QtWidgets.QWidget):
    shotChanged = QtCore.Signal()

    def __init__(self, state, backend, parent=None):
        super(ShotPage, self).__init__(parent)
        self.state = state
        self.backend = backend
        self.shot = None
        self._fd_reports = {}
        self._fd_running = False
        styled(self)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        self.content = styled(QtWidgets.QWidget())
        self.layout_root = QtWidgets.QVBoxLayout(self.content)
        self.layout_root.setContentsMargins(20, 16, 20, 16)
        self.layout_root.setSpacing(12)
        scroll.setWidget(self.content)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    def status_hint(self):
        if self.shot is None:
            return "Select a shot from the Board or Home"
        managed = self.shot.get("managed")
        base = ("Managed shot · shot.json v1" if managed
                else "Discovered shot · no shot.json yet")
        versions = len(self.state.shot_versions(self.shot))
        snaps = len(self.state.shot_snapshots(self.shot))
        renders = len(self._render_records(self.shot))
        return ("{} · Derived: {} versions · {} snapshots · {} renders".format(
            base, versions, snaps, renders))

    def set_shot(self, shot):
        self.shot = shot
        self.rebuild()

    def rebuild(self):
        clear_layout(self.layout_root)
        main = self.window()
        if hasattr(main, "_hint_label") and self.isVisible():
            main._hint_label.setText(self.status_hint())
        if self.shot is None:
            self.layout_root.addWidget(EmptyState(
                "Select a shot from the Board or Home."))
            self.layout_root.addStretch(1)
            return
        shot = self.shot
        config = shot.get("config") or {}

        crumb = QtWidgets.QLabel(
            "<b style=\"color:#e6e6e6;\">{}</b> <span style=\"color:#9a9ea6;\">›"
            " shots ›</span> <b style=\"color:#e6e6e6;\">{}</b>".format(
                shot.get("project_name", ""), shot["name"]))
        crumb.setTextFormat(QtCore.Qt.RichText)
        crumb.setStyleSheet("font-size: 11.5px; background: transparent;")
        self.layout_root.addWidget(crumb)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(14)
        title = QtWidgets.QLabel(shot["name"] + "_comp")
        title.setObjectName("ShellH2")
        header.addWidget(title)
        if not shot.get("managed"):
            header.addWidget(Chip("discovered", theme.status_color("delivered"), dim=True))
        header.addStretch(1)
        self.layout_root.addLayout(header)

        # status picker + due/priority/tags chips (the mockup's .dhead row)
        head_row = QtWidgets.QHBoxLayout()
        head_row.setSpacing(14)
        status_row = QtWidgets.QHBoxLayout()
        status_row.setSpacing(5)
        self._status_chips = {}
        accent = self.state.prefs.get("accent", "#f0a043")
        for status in STATUS_ORDER:
            chip = ClickableChip(STATUS_LABELS[status], theme.status_color(status),
                                 active=status == shot.status, accent=accent)
            chip.clicked.connect(lambda s=status: self._set_status(s))
            self._status_chips[status] = chip
            status_row.addWidget(chip)
        head_row.addLayout(status_row)
        head_row.addStretch(1)
        self.layout_root.addLayout(head_row)

        meta_row = QtWidgets.QHBoxLayout()
        meta_row.setSpacing(8)
        due = config.get("due")
        if due:
            try:
                days = (date.fromisoformat(due) - date.today()).days
                if days < 0:
                    meta_row.addWidget(Chip("due {}d overdue".format(-days),
                                            theme.status_color("hold")))
                elif days <= 3:
                    meta_row.addWidget(Chip("due in {}d".format(max(days, 0)),
                                            theme.status_color("wip")))
                else:
                    meta_row.addWidget(Chip("due " + due, theme.status_color("wip")))
            except ValueError:
                meta_row.addWidget(Chip("due " + due, theme.status_color("wip")))
        if config.get("priority"):
            meta_row.addWidget(NeutralChip("priority {}".format(config["priority"])))
        tags = config.get("tags") or []
        if tags:
            meta_row.addWidget(NeutralChip(" · ".join(tags)))
        meta_row.addStretch(1)
        self.layout_root.addLayout(meta_row)

        columns = QtWidgets.QHBoxLayout()
        columns.setSpacing(14)
        columns.addWidget(self._build_left(shot), 0)
        main_column = QtWidgets.QVBoxLayout()
        main_column.setSpacing(12)
        main_column.addWidget(self._build_notes(shot, config), 0)
        main_column.addWidget(self._build_checklist(shot, config), 0)
        main_column.addWidget(self._build_versions(shot), 0)
        main_column.addWidget(self._build_snapshots(shot), 0)
        render_section = self._build_renders(shot)
        if render_section is not None:
            main_column.addWidget(render_section, 0)
        time_section = self._build_time(shot)
        if time_section is not None:
            main_column.addWidget(time_section, 0)
        main_column.addWidget(self._build_settings(shot, config), 0)
        main_column.addStretch(1)
        columns.addLayout(main_column, 1)
        self.layout_root.addLayout(columns)
        self.layout_root.addStretch(1)

    # ------------------------------------------------------------------
    def _build_left(self, shot):
        column = QtWidgets.QVBoxLayout()
        column.setSpacing(8)
        thumb = Thumb(shot["name"], self._thumb_path(shot), (330, 200), radius=5,
                      font_px=30, tag="v{} · viewer grab".format(
                          "{:03d}".format(_latest_number(shot))))
        column.addWidget(thumb)

        open_button = QtWidgets.QPushButton("Open Latest ({})".format(_latest_name(shot)))
        open_button.setProperty("accent", True)
        open_button.clicked.connect(self._open_latest)
        column.addWidget(open_button)
        row1 = QtWidgets.QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(self._button("Version up", "film", self._version_up))
        row1.addWidget(self._button("Send to SleepyQueue", "send", self._send_batch))
        column.addLayout(row1)
        row2 = QtWidgets.QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(self._button("Open Folder", "folder", self._open_folder))
        row2.addWidget(self._button("Snapshot", "camera", self._snapshot))
        column.addLayout(row2)
        if not self.backend.can_nuke:
            hint = QtWidgets.QLabel("Launching Nuke from the launcher; snapshots and "
                                    "SleepyQueue need a running Nuke session.")
            hint.setObjectName("ShellDim")
            hint.setWordWrap(True)
            hint.setStyleSheet("font-size: 11px;")
            column.addWidget(hint)
        column.addStretch(1)
        holder = QtWidgets.QWidget()
        holder.setLayout(column)
        return holder

    def _button(self, label, icon_name, callback):
        from shellui import icons
        button = QtWidgets.QPushButton(" " + label)
        button.setIcon(icons.icon(icon_name))
        button.clicked.connect(callback)
        return button

    def _build_notes(self, shot, config):
        section = Section("Notes", extra=QtWidgets.QLabel("stored in shot.json"))
        self.notes_edit = QtWidgets.QPlainTextEdit(config.get("notes", ""))
        self.notes_edit.setPlaceholderText("Working notes for this shot...")
        self.notes_edit.setMinimumHeight(70)
        self.notes_edit.setMaximumHeight(120)
        section.add(self.notes_edit)
        save_row = QtWidgets.QHBoxLayout()
        self.notes_hint = QtWidgets.QLabel("")
        self.notes_hint.setObjectName("ShellDim")
        save_row.addWidget(self.notes_hint)
        save_row.addStretch(1)
        save_button = QtWidgets.QPushButton("Save notes")
        save_button.clicked.connect(self._save_notes)
        save_row.addWidget(save_button)
        section.add_layout(save_row)
        return section

    def _build_versions(self, shot):
        section = Section("Versions", extra=QtWidgets.QLabel("from disk · .snapshots merged in"))
        entries = self.state.shot_versions(shot)
        if not entries:
            section.add(EmptyState(
                "No scripts yet.\n\nCreate one in Nuke and save it into the shot's "
                "comp folder, or set a comp template in Project Settings."))
            return section
        snapshots = self.state.shot_snapshots(shot)
        renders = self._render_records(shot)
        render_versions = set()
        for record in renders:
            info = record.get("render") or {}
            if info.get("version"):
                render_versions.add(info["version"])
        for index, entry in enumerate(entries[:12]):
            row = QtWidgets.QFrame()
            row.setObjectName("ShellVRow")
            if index == 0:
                row.setProperty("cur", True)
            h = QtWidgets.QHBoxLayout(row)
            h.setContentsMargins(8, 6, 8, 6)
            h.setSpacing(11)
            h.addWidget(Thumb(shot["name"], None, (64, 38), radius=3, font_px=10))
            version_label = QtWidgets.QLabel("v{:03d}".format(entry["number"]))
            version_label.setStyleSheet("font-weight: 600;")
            version_label.setFixedWidth(52)
            h.addWidget(version_label)
            meta_bits = [_datetime_text(entry["mtime"]),
                         _size_text(entry["size"])]
            if entry["number"] in render_versions:
                meta_bits.append("rendered ✓")
            if index == 0 and snapshots:
                meta_bits.append("{} snapshots".format(len(snapshots)))
            meta = QtWidgets.QLabel(" · ".join(meta_bits))
            meta.setObjectName("ShellDim")
            meta.setStyleSheet("font-size: 11px; background: transparent;")
            h.addWidget(meta, 1)
            if index == 0:
                star = QtWidgets.QLabel("★")
                star.setStyleSheet("color: {}; font-size: 12.5px;".format(
                    self.state.prefs.get("accent", "#f0a043")))
                h.addWidget(star)
            open_button = QtWidgets.QPushButton("Open")
            open_button.clicked.connect(
                lambda _=False, path=entry["path"]: self._open_path(path))
            h.addWidget(open_button)
            section.add(row)
        if len(entries) > 12:
            more = QtWidgets.QLabel("+ {} older versions on disk".format(len(entries) - 12))
            more.setObjectName("ShellDim")
            section.add(more)
        return section

    def _build_snapshots(self, shot):
        section = Section("Snapshots", extra=QtWidgets.QLabel("from Snapshot Browser"))
        snapshots = self.state.shot_snapshots(shot)
        if not snapshots:
            section.add(EmptyState(
                "No snapshots for this shot yet.\n\nTake one with the Snapshot "
                "button (needs Snapshot Browser installed)."))
            return section
        for meta in snapshots[:8]:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(10)
            kind_chip = Chip(meta.get("kind", "manual"), theme.status_color("review"))
            row.addWidget(kind_chip)
            note = QtWidgets.QLabel(meta.get("note") or meta.get("created", ""))
            row.addWidget(note, 1)
            if meta.get("starred"):
                star = QtWidgets.QLabel("★")
                star.setStyleSheet("color: {}; font-weight: 700;".format(
                    self.state.prefs.get("accent", "#f0a043")))
                row.addWidget(star)
            section.add_layout(row)
        if len(snapshots) > 8:
            more = QtWidgets.QLabel("+ {} older snapshots".format(len(snapshots) - 8))
            more.setObjectName("ShellDim")
            section.add(more)
        return section

    def _build_checklist(self, shot, config):
        """Per-shot checklist stored as tasks in shot.json."""
        from shellui.widgets import styled
        section = Section("Checklist", extra=QtWidgets.QLabel("stored in shot.json"))
        tasks = config.get("tasks") or []
        if not tasks:
            empty = QtWidgets.QLabel("Nothing planned for this shot yet.")
            empty.setObjectName("ShellDim")
            section.add(empty)
        for index, task in enumerate(tasks):
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(8)
            checkbox = QtWidgets.QCheckBox(task["name"])
            checkbox.setChecked(bool(task.get("done")))
            checkbox.toggled.connect(lambda on, i=index: self._toggle_task(i, on))
            if task.get("done"):
                checkbox.setStyleSheet("QCheckBox {{ color: #9a9ea6;"
                                       " text-decoration: line-through; }}")
            row.addWidget(checkbox, 1)
            remove = QtWidgets.QToolButton()
            remove.setText("x")
            remove.setStyleSheet(
                "QToolButton { background: transparent; border: none;"
                " color: #9a9ea6; padding: 1px 5px; }"
                "QToolButton:hover { color: #d96b5b; }")
            remove.clicked.connect(lambda _=False, i=index: self._remove_task(i))
            row.addWidget(remove)
            section.add_layout(row)

        add_row = QtWidgets.QHBoxLayout()
        self.task_edit = QtWidgets.QLineEdit()
        self.task_edit.setPlaceholderText("Add a step...")
        self.task_edit.returnPressed.connect(self._add_task)
        add_row.addWidget(self.task_edit, 1)
        add_button = QtWidgets.QPushButton("Add")
        add_button.clicked.connect(self._add_task)
        add_row.addWidget(add_button)
        section.add_layout(add_row)
        return section

    def _tasks(self):
        return (self.shot.get("config") or {}).get("tasks") or []

    def _save_tasks(self, tasks):
        from shellcore import schema
        try:
            schema.save_shot(self.shot["path"], {"tasks": tasks})
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Sleepy Shell",
                                          "Could not save checklist: {}".format(exc))
            return False
        self.shot.setdefault("config", {})["tasks"] = tasks
        self.shotChanged.emit()
        return True

    def _add_task(self):
        name = self.task_edit.text().strip()
        if not name or self.shot is None:
            return
        tasks = [dict(t) for t in self._tasks()]
        tasks.append({"name": name, "done": False})
        if self._save_tasks(tasks):
            self.task_edit.clear()

    def _toggle_task(self, index, done):
        tasks = [dict(t) for t in self._tasks()]
        if 0 <= index < len(tasks):
            tasks[index]["done"] = bool(done)
            self._save_tasks(tasks)

    def _remove_task(self, index):
        tasks = [dict(t) for t in self._tasks()]
        if 0 <= index < len(tasks):
            del tasks[index]
            if self._save_tasks(tasks):
                self.rebuild()

    def _build_renders(self, shot):
        renders = self._render_records(shot)
        if not renders:
            return None  # section only exists when there is render data
        section = Section("Recent renders", extra=QtWidgets.QLabel("from SleepyQueue"))
        for record in renders[:6]:
            info = record.get("render") or {}
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(10)
            ok_done = info.get("status") == "done"
            mark = QtWidgets.QLabel("✓" if ok_done else "✗")
            mark.setStyleSheet("color: {}; font-weight: 700;".format(
                theme.STATUS_COLORS["approved"] if ok_done else theme.STATUS_COLORS["hold"]))
            row.addWidget(mark)
            label = QtWidgets.QLabel("{} · {} · {}".format(
                "v{:03d}".format(info.get("version", 0) or 0) if info.get("version")
                else (info.get("script") or "render"),
                info.get("write_node", "?"), info.get("frame_range", "?")))
            row.addWidget(label, 1)
            right = QtWidgets.QLabel(info.get("when", "") or
                                     (info.get("duration") or ""))
            right.setObjectName("ShellDim")
            right.setStyleSheet("font-size: 11px;")
            row.addWidget(right)
            output = info.get("output") or ""
            if output:
                qc = QtWidgets.QPushButton("Frame Doctor")
                qc.setToolTip("QC the rendered frames at {}".format(output))
                qc.clicked.connect(lambda _=False, o=output: self._run_frame_doctor(o))
                row.addWidget(qc)
            section.add_layout(row)
        # last Frame Doctor report for this shot, if any
        report = self._fd_reports.get(shot["path"])
        if report is not None:
            section.add_layout(self._fd_result_rows(report))
        return section

    def _fd_result_rows(self, report):
        """Rows describing a Frame Doctor report."""
        from shellui.widgets import Chip
        rows = QtWidgets.QVBoxLayout()
        rows.setSpacing(4)
        header = QtWidgets.QHBoxLayout()
        verdict_chip = Chip(report["verdict"],
                            theme.status_color("approved" if report["verdict"] == "OK"
                                               else "hold"))
        header.addWidget(verdict_chip)
        header.addWidget(QtWidgets.QLabel("{frame_count} frames ({first}-{last}),"
                                          " scanned {scanned}".format(**report)))
        header.addStretch(1)
        rows.addLayout(header)
        if report["verdict"] == "OK":
            note = QtWidgets.QLabel("No problems found.")
            note.setObjectName("ShellDim")
            rows.addWidget(note)
        for problem in report["problems"]:
            row = QtWidgets.QHBoxLayout()
            mark = QtWidgets.QLabel("!")
            mark.setStyleSheet("color: {}; font-weight: 700;".format(
                theme.STATUS_COLORS["hold"]))
            row.addWidget(mark)
            row.addWidget(QtWidgets.QLabel(problem), 1)
            rows.addLayout(row)
        return rows

    def _run_frame_doctor(self, output):
        """Scan a rendered sequence in a background thread."""
        if hasattr(self, "_fd_running") and self._fd_running:
            return
        self._fd_running = True
        self.status_label = getattr(self, "status_label", None)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        self._fd_worker = FrameDoctorWorker(output)
        self._fd_worker.finishedWithReport.connect(self._frame_doctor_done)
        self._fd_worker.failed.connect(self._frame_doctor_failed)
        self._fd_worker.start()

    def _frame_doctor_done(self, target, report):
        QtWidgets.QApplication.restoreOverrideCursor()
        self._fd_running = False
        if self.shot is None:
            return
        self._fd_reports[self.shot["path"]] = report
        self.rebuild()

    def _frame_doctor_failed(self, target, message):
        QtWidgets.QApplication.restoreOverrideCursor()
        self._fd_running = False
        QtWidgets.QMessageBox.information(self, "Frame Doctor", message)

    def _build_time(self, shot):
        from shellcore import sessions
        summary = sessions.summarize_for_shot(shot["path"], shot.get("comp_dir"))
        if summary["total"] <= 0:
            return None
        section = Section("Time on this shot", extra=QtWidgets.QLabel("from session history"))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(14)
        total = QtWidgets.QLabel("<b style='font-size:15px; color:#e6e6e6;'>{}</b>"
                                 " <span style='color:#9a9ea6; font-size:11.5px;'>"
                                 "total · {} this week</span>".format(
                                     _hours_text(summary["total"]),
                                     _hours_text(summary["this_week"])))
        total.setTextFormat(QtCore.Qt.RichText)
        row.addWidget(total)
        row.addStretch(1)
        bars = WeekBars(_week_values(summary), width=200)
        row.addWidget(bars)
        section.add_layout(row)
        return section

    def _build_settings(self, shot, config):
        section = Section("Shot settings")
        meta = QtWidgets.QHBoxLayout()
        meta.setSpacing(8)
        project = self.state.project_for(shot)
        project_config = project.get("config") if project else {}
        meta.addWidget(MetaChip("fps", project_config.get("fps")))
        if project_config.get("resolution"):
            meta.addWidget(MetaChip("format", project_config["resolution"]))
        if project_config.get("working_space"):
            meta.addWidget(MetaChip("working space", project_config["working_space"]))
        meta.addWidget(MetaChip("status", STATUS_LABELS.get(shot.status, shot.status)))
        if config.get("range") or (project_config or {}).get("range"):
            meta.addWidget(MetaChip("range", config.get("range") or project_config.get("range")))
        meta.addWidget(MetaChip("handles", project_config.get("handles")))
        meta.addStretch(1)
        section.add_layout(meta)

        editor_row = QtWidgets.QHBoxLayout()
        editor_row.setSpacing(8)
        due_label = QtWidgets.QLabel("Due date")
        due_label.setObjectName("ShellDim")
        editor_row.addWidget(due_label)
        self.due_edit = QtWidgets.QDateEdit()
        self.due_edit.setCalendarPopup(True)
        self.due_edit.setDisplayFormat("yyyy-MM-dd")
        raw_due = config.get("due")
        if raw_due:
            try:
                self.due_edit.setDate(date.fromisoformat(raw_due))
            except ValueError:
                self.due_edit.setDate(date.today())
        else:
            self.due_edit.setDate(date.today())
        editor_row.addWidget(self.due_edit)
        prio_label = QtWidgets.QLabel("Priority")
        prio_label.setObjectName("ShellDim")
        editor_row.addWidget(prio_label)
        self.priority_combo = QtWidgets.QComboBox()
        self.priority_combo.addItem("—", None)
        for value in (1, 2, 3):
            self.priority_combo.addItem(str(value), value)
        current_priority = config.get("priority")
        index = self.priority_combo.findData(current_priority)
        self.priority_combo.setCurrentIndex(index if index >= 0 else 0)
        editor_row.addWidget(self.priority_combo)
        tags_label = QtWidgets.QLabel("Tags")
        tags_label.setObjectName("ShellDim")
        editor_row.addWidget(tags_label)
        self.tags_edit = QtWidgets.QLineEdit(", ".join(config.get("tags", [])))
        self.tags_edit.setPlaceholderText("beauty, cleanup")
        editor_row.addWidget(self.tags_edit, 1)
        save_button = QtWidgets.QPushButton("Save")
        save_button.clicked.connect(self._save_meta)
        editor_row.addWidget(save_button)
        section.add_layout(editor_row)
        return section

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def _render_records(self, shot):
        from shellcore.versions import render_records
        try:
            return render_records(self.state.shot_snapshots(shot))
        except Exception:
            return []

    def _set_status(self, status):
        if self.shot is None:
            return
        try:
            schema.save_shot(self.shot["path"], {"status": status})
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Sleepy Shell",
                                          "Could not save status:\n{}".format(exc))
            return
        self.shot.setdefault("config", {})["status"] = status
        self.rebuild()
        self.shotChanged.emit()

    def _save_notes(self):
        if self.shot is None:
            return
        try:
            schema.save_shot(self.shot["path"], {"notes": self.notes_edit.toPlainText()})
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Sleepy Shell",
                                          "Could not save notes:\n{}".format(exc))
            return
        self.shot.setdefault("config", {})["notes"] = self.notes_edit.toPlainText()
        self.notes_hint.setText("saved")

    def _save_meta(self):
        if self.shot is None:
            return
        tags = [tag.strip() for tag in self.tags_edit.text().split(",") if tag.strip()]
        due = self.due_edit.date().toString("yyyy-MM-dd")
        values = {"tags": tags, "due": due,
                  "priority": self.priority_combo.currentData()}
        try:
            schema.save_shot(self.shot["path"], values)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Sleepy Shell",
                                          "Could not save:\n{}".format(exc))
            return
        self.shot.setdefault("config", {}).update(values)
        self.shotChanged.emit()

    def _open_latest(self):
        from shellcore.versions import latest_version
        entry = latest_version(self.shot.get("comp_dir")) if self.shot else None
        if entry is None:
            QtWidgets.QMessageBox.information(
                self, "Sleepy Shell", "This shot has no scripts yet.")
            return
        self._open_path(entry["path"])

    def _open_path(self, path):
        ok, message = self.backend.open_script(path)
        if ok:
            self.state.remember_open(self.shot)
        else:
            QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)

    def _open_folder(self):
        ok, message = self.backend.open_folder(self.shot["path"])
        if not ok:
            QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)

    def _version_up(self):
        new_path, message = self.backend.version_up(self.shot)
        QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)
        if new_path:
            answer = QtWidgets.QMessageBox.question(
                self, "Sleepy Shell", "Open {} now?".format(os.path.basename(new_path)),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if answer == QtWidgets.QMessageBox.Yes:
                ok, open_message = self.backend.open_script(new_path)
                if ok:
                    self.state.remember_open(self.shot)
                else:
                    QtWidgets.QMessageBox.information(self, "Sleepy Shell", open_message)
            self.shotChanged.emit()

    def _snapshot(self):
        ok, message = self.backend.take_snapshot()
        QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)

    def _send_batch(self):
        ok, message = self.backend.send_to_sleepy_queue()
        QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)

    def _thumb_path(self, shot):
        thumbs = self.state.shot_thumbnails(shot, limit=1)
        return thumbs[0] if thumbs else None


class ClickableChip(Chip):
    """Status-picker chip: faded when inactive, accent outline when active."""

    clicked = QtCore.Signal()

    def __init__(self, text, color, active=False, parent=None, accent="#f0a043"):
        super(ClickableChip, self).__init__(text, color, parent=parent)
        self._active = active
        self._accent = accent
        self._apply_active()
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def _apply_active(self):
        from SleepyCore.qt import QtGui
        c = QtGui.QColor(self._color)
        rgb = "{},{},{}".format(c.red(), c.green(), c.blue())
        if self._active:
            self.setStyleSheet(
                "QLabel {{ background: rgba({rgb},15%); color: {hex};"
                " border: 1px solid {accent}; border-radius: 10px;"
                " padding: 1px 9px; font-size: 11px; font-weight: 600; }}".format(
                    rgb=rgb, hex=self._color, accent=self._accent))
        else:
            # the mockup's .statuspick .chip { opacity:.55 }
            self.setStyleSheet(
                "QLabel {{ background: rgba({rgb},8%);"
                " color: rgba({rgb},60%);"
                " border: 1px solid rgba({rgb},22%); border-radius: 10px;"
                " padding: 1px 9px; font-size: 11px; font-weight: 600; }}".format(
                    rgb=rgb))

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super(ClickableChip, self).mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
class FrameDoctorWorker(QtCore.QThread):
    """Scans a rendered sequence off the UI thread."""

    finishedWithReport = QtCore.Signal(str, dict)
    failed = QtCore.Signal(str, str)

    def __init__(self, target, sample=1, parent=None):
        super(FrameDoctorWorker, self).__init__(parent)
        self._target = target
        self._sample = max(1, int(sample))

    def run(self):
        from shellcore import framedoctor, framedoctor_readers
        folder, sequence = framedoctor.find_sequence(self._target)
        if sequence is None:
            self.failed.emit(self._target,
                             "No frame sequence found at " + self._target)
            return
        try:
            report = framedoctor.analyze(sequence["frames"],
                                         framedoctor_readers.load,
                                         sample=self._sample)
        except Exception as exc:
            self.failed.emit(self._target, "Scan failed: {}".format(exc))
            return
        self.finishedWithReport.emit(self._target, report)


def render_records_for(state, shot):
    from shellcore.versions import render_records
    return render_records(state.shot_snapshots(shot))


def _latest_name(shot):
    from shellcore.versions import latest_version
    entry = latest_version(shot.get("comp_dir"))
    return "v{:03d}".format(entry["number"]) if entry else "no scripts yet"


def _latest_number(shot):
    from shellcore.versions import latest_version
    entry = latest_version(shot.get("comp_dir"))
    return entry["number"] if entry else 0


def _node_guess(entry):
    """Node counts are not stored on disk, so the meta line shows real
    file stats instead (size/date); kept for older callers."""
    return "{:.0f} KB".format(entry["size"] / 1024.0)


def _datetime_text(stamp):
    import datetime
    dt = datetime.datetime.fromtimestamp(stamp)
    today = date.today()
    if dt.date() == today:
        return "today {:02d}:{:02d}".format(dt.hour, dt.minute)
    if dt.date() == today - timedelta(days=1):
        return "yesterday"
    return dt.date().isoformat()


def _week_values(summary):
    """Per-day seconds for the last 7 days, oldest first."""
    by_day = summary.get("by_day") or {}
    today = date.today()
    values = []
    for offset in range(6, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        values.append(float(by_day.get(day, 0.0)))
    return values


def _date_text(stamp):
    return date.fromtimestamp(stamp).isoformat()


def _size_text(num_bytes):
    if num_bytes < 0.1 * 1048576:
        return "{:.1f} KB".format(num_bytes / 1024.0)
    return "{:.1f} MB".format(num_bytes / 1048576.0)


def _hours_text(seconds):
    seconds = float(seconds or 0)
    hours = seconds / 3600.0
    if hours < 1:
        return "{}m".format(int(seconds // 60))
    if hours < 10:
        minutes = int((seconds % 3600) // 60)
        return "{}h {:02d}m".format(int(hours), minutes)
    return "{:.1f}h".format(hours)
