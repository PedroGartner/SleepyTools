"""Version 2 main widget: production tracker layout.

Original design inspired by production-tracking workflow concepts:
entity hierarchy (project -> sequences -> shots), a dense sortable shot
table, and a right-hand detail inspector. Task information is the
shot's own status (the comp task) — no second data model is invented,
so all three versions share identical project data.
"""

from datetime import date

from SleepyCore.qt import QtCore, QtGui, QtWidgets

from shellcore import grouping, schema
from shellcore.schema import STATUS_LABELS, STATUS_ORDER
from shellcore.versions import latest_version
from shellui import theme


class ProductionWidget(QtWidgets.QWidget):
    """The whole V2 experience; works standalone or docked in Nuke."""

    openScriptRequested = QtCore.Signal(str)

    def __init__(self, state, backend, parent=None):
        super(ProductionWidget, self).__init__(parent)
        self.state = state
        self.backend = backend
        self._current_shot = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top_bar())
        self.dashboard = QtWidgets.QLabel("")
        self.dashboard.setStyleSheet(
            "padding: 5px 14px; background: #1a1b1d; color: #9a9ea6; font-size: 11px;")
        root.addWidget(self.dashboard)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.addWidget(self._build_tree())
        splitter.addWidget(self._build_table())
        splitter.addWidget(self._build_inspector())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([200, 620, 320])
        root.addWidget(splitter, 1)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet(
            "padding: 3px 14px; background: #1a1b1d; color: #9a9ea6; font-size: 11px;")
        root.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # top bar
    # ------------------------------------------------------------------
    def _build_top_bar(self):
        bar = QtWidgets.QFrame()
        bar.setStyleSheet("background: #1a1b1d; border-bottom: 1px solid #2a2c30;")
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        title = QtWidgets.QLabel("PRODUCTION")
        title.setStyleSheet("font-weight: 700; letter-spacing: 1.5px; font-size: 11px;")
        layout.addWidget(title)

        self.project_combo = QtWidgets.QComboBox()
        self.project_combo.setMinimumWidth(190)
        self.project_combo.currentIndexChanged.connect(self._project_changed)
        layout.addWidget(self.project_combo)

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Search shots, notes, tags...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMaximumWidth(240)
        self.search_edit.textChanged.connect(self.refresh_table)
        layout.addWidget(self.search_edit)

        self.status_filter = QtWidgets.QComboBox()
        self.status_filter.addItem("All statuses", None)
        for status in STATUS_ORDER:
            self.status_filter.addItem(STATUS_LABELS[status], status)
        self.status_filter.currentIndexChanged.connect(self.refresh_table)
        layout.addWidget(self.status_filter)

        self.due_check = QtWidgets.QCheckBox("Due")
        self.due_check.toggled.connect(self.refresh_table)
        layout.addWidget(self.due_check)

        layout.addStretch(1)
        refresh = QtWidgets.QPushButton("Refresh")
        refresh.clicked.connect(lambda: self.state.refresh(force=True))
        layout.addWidget(refresh)
        new_shot = QtWidgets.QPushButton("New Shot")
        new_shot.setProperty("accent", True)
        new_shot.clicked.connect(self._new_shot)
        layout.addWidget(new_shot)
        return bar

    # ------------------------------------------------------------------
    # left tree: project -> sequences -> shots
    # ------------------------------------------------------------------
    def _build_tree(self):
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(170)
        self.tree.itemSelectionChanged.connect(self._tree_selected)
        return self.tree

    def reload_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        for project in self.state.projects:
            project_item = QtWidgets.QTreeWidgetItem(
                [project["name"] + ("" if project["managed"] else "  (discovered)")])
            project_item.setData(0, QtCore.Qt.UserRole, ("project", project["path"]))
            project_item.setForeground(
                0, QtGui.QColor(theme.status_color("wip")) if project["managed"]
                else QtGui.QColor("#8a8f98"))
            self.tree.addTopLevelItem(project_item)
            shots = [s for s in self.state.shots if s.get("project_path") == project["path"]]
            groups = grouping.group_shots(shots)
            for seq_key, seq_shots in groups.items():
                seq_item = QtWidgets.QTreeWidgetItem(
                    ["{}   ({})".format(grouping.sequence_label(seq_key), len(seq_shots))])
                seq_item.setData(0, QtCore.Qt.UserRole, ("sequence", project["path"], seq_key))
                project_item.addChild(seq_item)
                for shot in seq_shots:
                    shot_item = QtWidgets.QTreeWidgetItem([shot["name"]])
                    shot_item.setData(0, QtCore.Qt.UserRole, ("shot", shot))
                    color = theme.status_color(shot.status)
                    shot_item.setForeground(0, QtGui.QColor(color))
                    seq_item.addChild(shot_item)
            project_item.setExpanded(True)
        self.tree.blockSignals(False)

    def _tree_selected(self):
        items = self.tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, QtCore.Qt.UserRole)
        if not data:
            return
        kind = data[0]
        if kind == "shot":
            self.select_shot(data[1])
        elif kind == "sequence":
            project_path, seq_key = data[1], data[2]
            self._filter_sequence = (project_path, seq_key)
            self.refresh_table()
        elif kind == "project":
            self._filter_sequence = None
            index = self.project_combo.findData(data[1])
            if index >= 0:
                self.project_combo.setCurrentIndex(index)

    # ------------------------------------------------------------------
    # center: sortable shot table
    # ------------------------------------------------------------------
    def _build_table(self):
        self.table = QtWidgets.QTreeWidget()
        self.table.setHeaderLabels(
            ["", "Shot", "Sequence", "Task", "Status", "Version", "Due", "Modified", "Notes"])
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(1, QtCore.Qt.AscendingOrder)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self._table_selected)
        self.table.itemDoubleClicked.connect(
            lambda item, _col: self._open_latest(item))
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        self.table.setColumnWidth(0, 62)
        self.table.setColumnWidth(4, 108)
        return self.table

    def reload_table(self):
        self.table.blockSignals(True)
        self.table.clear()
        shots = self._filtered_shots()
        for shot in shots:
            item = QtWidgets.QTreeWidgetItem()
            item.setData(0, QtCore.Qt.UserRole, shot)
            item.setText(1, shot["name"])
            item.setText(2, grouping.sequence_label(grouping.sequence_key(shot["name"])))
            item.setText(3, "comp")
            item.setForeground(3, QtGui.QColor("#9a9ea6"))
            item.setText(4, STATUS_LABELS.get(shot.status, shot.status))
            item.setForeground(4, QtGui.QColor(theme.status_color(shot.status)))
            entry = latest_version(shot.get("comp_dir"))
            item.setText(5, "v{:03d}".format(entry["number"]) if entry else "—")
            due = (shot.get("config") or {}).get("due")
            item.setText(6, self._due_text(due))
            if due:
                try:
                    overdue = date.fromisoformat(due) < date.today()
                except ValueError:
                    overdue = False
                item.setForeground(6, QtGui.QColor(
                    theme.status_color("hold" if overdue else "wip")))
            stamp = shot.get("_modified") or ""
            item.setText(7, stamp)
            notes = (shot.get("config") or {}).get("notes", "")
            item.setText(8, notes.split("\n")[0][:60] if notes else "")
            item.setForeground(8, QtGui.QColor("#9a9ea6"))
            if not shot.get("managed"):
                item.setText(0, "disc")
                item.setForeground(0, QtGui.QColor("#8a8f98"))
            self.table.addTopLevelItem(item)
        self.table.blockSignals(False)
        count_text = "{} shots".format(len(shots))
        if self.state.from_cache:
            count_text += " (cached)"
        self.status_label.setText(count_text)

    @staticmethod
    def _due_text(due):
        if not due:
            return "—"
        try:
            days = (date.fromisoformat(due) - date.today()).days
        except ValueError:
            return due
        if days < 0:
            return "{}d overdue".format(-days)
        if days == 0:
            return "today"
        return "in {}d".format(days)

    def _filtered_shots(self):
        text = self.search_edit.text()
        results = self.state.visible_shots(text=text, include_delivered=True)
        project_path = self.project_combo.currentData()
        if project_path:
            results = [s for s in results if s.get("project_path") == project_path]
        status = self.status_filter.currentData()
        if status:
            results = [s for s in results if s.status == status]
        if self.due_check.isChecked():
            results = [s for s in results if (s.get("config") or {}).get("due")]
        seq = getattr(self, "_filter_sequence", None)
        if seq:
            project_path, seq_key = seq
            results = [s for s in results
                       if s.get("project_path") == project_path
                       and grouping.sequence_key(s["name"]) == seq_key]
        return results

    def _table_selected(self):
        items = self.table.selectedItems()
        if not items:
            return
        shot = items[0].data(0, QtCore.Qt.UserRole)
        if shot is not None:
            self._current_shot = shot
            self.inspector.set_shot(shot)

    def _table_menu(self, pos):
        item = self.table.itemAt(pos)
        if item is None:
            return
        shot = item.data(0, QtCore.Qt.UserRole)
        menu = QtWidgets.QMenu(self)
        menu.addAction("Open latest version", lambda: self._open_latest(item))
        status_menu = menu.addMenu("Set status")
        for status in STATUS_ORDER:
            action = status_menu.addAction(STATUS_LABELS[status])
            action.setCheckable(True)
            action.setChecked(status == shot.status)
            action.triggered.connect(lambda _=False, s=status: self._set_status(shot, s))
        menu.addSeparator()
        menu.addAction("Show in inspector", lambda: self.select_shot(shot))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------
    # right: inspector
    # ------------------------------------------------------------------
    def _build_inspector(self):
        from shellui_production.inspector import InspectorPanel
        self.inspector = InspectorPanel(self.state, self.backend)
        self.inspector.statusChanged.connect(self._on_status_changed)
        return self.inspector

    # ------------------------------------------------------------------
    # data flow
    # ------------------------------------------------------------------
    def reload(self):
        combo = self.project_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("All projects", None)
        for project in self.state.projects:
            combo.addItem(project["name"], project["path"])
        if self.state.current_project:
            index = combo.findData(self.state.current_project)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.blockSignals(False)
        self.reload_tree()
        self.reload_table()
        counts = {}
        for shot in self.state.shots:
            counts[shot.status] = counts.get(shot.status, 0) + 1
        self.dashboard.setText("   ".join(
            "{}: {}".format(STATUS_LABELS[s], counts.get(s, 0)) for s in STATUS_ORDER
            if counts.get(s)))
        if self._current_shot is not None:
            updated = self.state.shot_by_path(self._current_shot["path"])
            if updated is not None:
                self._current_shot = updated
                self.inspector.set_shot(updated)

    def refresh_table(self):
        self.reload_table()

    def _project_changed(self, _index):
        path = self.project_combo.currentData()
        self.state.current_project = path
        self._filter_sequence = None
        self.reload_tree()
        self.refresh_table()

    def select_shot(self, shot):
        self._current_shot = shot
        self.inspector.set_shot(shot)
        # also highlight it in the table
        for i in range(self.table.topLevelItemCount()):
            item = self.table.topLevelItem(i)
            data = item.data(0, QtCore.Qt.UserRole)
            if data is not None and data.get("path") == shot.get("path"):
                self.table.setCurrentItem(item)
                break

    def _set_status(self, shot, status):
        try:
            schema.save_shot(shot["path"], {"status": status})
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Project Manager",
                                          "Could not save status:\n{}".format(exc))
            return
        shot.setdefault("config", {})["status"] = status
        self.reload()
        self._on_status_changed(shot)

    def _on_status_changed(self, shot):
        self.reload()
        self.select_shot(shot)

    def _open_latest(self, item):
        shot = item.data(0, QtCore.Qt.UserRole)
        if shot is None:
            return
        entry = latest_version(shot.get("comp_dir"))
        if entry is None:
            QtWidgets.QMessageBox.information(
                self, "Project Manager", "This shot has no scripts yet.")
            return
        self.state.remember_open(shot)
        self.openScriptRequested.emit(entry["path"])

    def _new_shot(self):
        project_path = self.project_combo.currentData()
        projects = [p for p in self.state.projects
                    if project_path is None or p["path"] == project_path]
        if not projects:
            QtWidgets.QMessageBox.information(
                self, "Project Manager", "No projects available. Check watched roots.")
            return
        project = projects[0]
        from shellui.dialogs import NewShotDialog
        dialog = NewShotDialog(project, self.state, self)
        if dialog.exec() and dialog.created_path:
            self.state.refresh(force=True)
            self.reload()
