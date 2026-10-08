"""V3 main widget: what if the Project Manager was a native Nuke pane?

Compact, flat, dense. Left: bins tree. Right: a file-browser-style
version list on top and a properties-panel-style editor below, with
collapsible sections. Every interaction follows Nuke habits:
double-click opens, right-click for context, small controls, no chrome.
"""

from datetime import date

from SleepyCore.qt import QtCore, QtGui, QtWidgets

from shellcore import schema
from shellcore.schema import STATUS_LABELS, STATUS_ORDER
from shellcore.versions import latest_version
from shellui import theme

NUKE_QSS = """
#NkPane { background: #1e1f22; }
#NkPane QLabel { background: transparent; }
#NkToolbar { background: #26272a; border-bottom: 1px solid #3a3c40; padding: 2px; }
#NkToolbar QPushButton {
  background: transparent; border: 1px solid transparent; padding: 2px 8px; }
#NkToolbar QPushButton:hover { border: 1px solid #3a3c40; background: #2e3033; }
#NkToolbar QComboBox, #NkToolbar QLineEdit {
  background: #1e1f22; border: 1px solid #3a3c40; padding: 1px 5px; }
#NkHeader { background: #26272a; color: #e6e6e6; font-weight: 600;
  border: none; padding: 3px 6px; text-align: left; }
#NkGroup { border-top: 1px solid #3a3c40; }
QTreeWidget, QListWidget {
  background: #1e1f22; alternate-background-color: #222326;
  border: 1px solid #3a3c40; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #f0a043; color: #161719; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #26272a; }
QHeaderView::section {
  background: #26272a; color: #9a9ea6; border: none;
  border-right: 1px solid #3a3c40; padding: 2px 6px; }
"""


class CollapsibleSection(QtWidgets.QWidget):
    """Nuke-properties-style collapsible group with a bold header row."""

    def __init__(self, title, expanded=True, parent=None):
        super(CollapsibleSection, self).__init__(parent)
        self.setObjectName("NkGroup")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.header = QtWidgets.QToolButton()
        self.header.setObjectName("NkHeader")
        self.header.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.header.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
        self.header.setText("  " + title)
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        self.header.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.header.clicked.connect(self._toggle)
        self.header.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                  QtWidgets.QSizePolicy.Fixed)
        self.header.setStyleSheet(
            "QToolButton { background: #26272a; color: #e6e6e6; font-weight: 600;"
            " border: none; padding: 3px 6px; text-align: left; }")
        layout.addWidget(self.header)
        self.body = QtWidgets.QWidget()
        self.body_layout = QtWidgets.QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(6, 4, 6, 6)
        self.body_layout.setSpacing(4)
        layout.addWidget(self.body)
        self._set_expanded(expanded)

    def _toggle(self, checked):
        self._set_expanded(checked)

    def _set_expanded(self, expanded):
        self.body.setVisible(expanded)
        self.header.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)

    def add(self, widget):
        self.body_layout.addWidget(widget)
        return widget

    def add_layout(self, layout):
        self.body_layout.addLayout(layout)
        return layout


class NukePaneWidget(QtWidgets.QWidget):
    """V3 experience; dockable in Nuke, wrappable standalone."""

    def __init__(self, state, backend, parent=None):
        super(NukePaneWidget, self).__init__(parent)
        self.state = state
        self.backend = backend
        self.shot = None
        self.setObjectName("NkPane")
        self.setStyleSheet(NUKE_QSS)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_toolbar())

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.addWidget(self._build_bins())
        splitter.addWidget(self._build_editor())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([190, 400])
        root.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    def _build_toolbar(self):
        bar = QtWidgets.QFrame()
        bar.setObjectName("NkToolbar")
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(4)
        self.project_combo = QtWidgets.QComboBox()
        self.project_combo.setMinimumWidth(150)
        self.project_combo.currentIndexChanged.connect(self._project_changed)
        layout.addWidget(self.project_combo)
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("find...")
        self.search_edit.setMaximumWidth(150)
        self.search_edit.textChanged.connect(self.reload_bins)
        layout.addWidget(self.search_edit)
        layout.addStretch(1)
        for label, handler in (("Refresh", self._refresh), ("New Shot", self._new_shot)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(handler)
            layout.addWidget(button)
        return bar

    def _build_bins(self):
        self.bins = QtWidgets.QTreeWidget()
        self.bins.setHeaderLabels(["Project / Shot", "Status"])
        self.bins.setRootIsDecorated(True)
        self.bins.setColumnWidth(0, 150)
        self.bins.itemSelectionChanged.connect(self._bins_selected)
        self.bins.itemDoubleClicked.connect(
            lambda item, _col: self._bins_double_click(item))
        return self.bins

    def _build_editor(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.editor_header = QtWidgets.QLabel("no shot selected")
        self.editor_header.setStyleSheet("font-weight: 600; padding: 5px 8px;"
                                         " background: #26272a;")
        layout.addWidget(self.editor_header)

        # versions section (file-browser style)
        self.versions_section = CollapsibleSection("Versions")
        self.versions_list = QtWidgets.QListWidget()
        self.versions_list.setMaximumHeight(140)
        self.versions_list.setAlternatingRowColors(True)
        self.versions_list.itemDoubleClicked.connect(self._open_version)
        self.versions_section.add(self.versions_list)
        hint = QtWidgets.QLabel("double-click a version to open it")
        hint.setStyleSheet("color: #9a9ea6; font-size: 10px;")
        self.versions_section.add(hint)
        layout.addWidget(self.versions_section)

        # shot properties section
        self.props_section = CollapsibleSection("Shot Properties")
        form = QtWidgets.QFormLayout()
        form.setSpacing(4)
        form.setLabelAlignment(QtCore.Qt.AlignRight)
        self.status_combo = QtWidgets.QComboBox()
        for status in STATUS_ORDER:
            self.status_combo.addItem(STATUS_LABELS[status], status)
        self.status_combo.currentIndexChanged.connect(self._status_edited)
        form.addRow("status", self.status_combo)
        self.due_edit = QtWidgets.QDateEdit()
        self.due_edit.setCalendarPopup(True)
        self.due_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow("due", self.due_edit)
        self.tags_edit = QtWidgets.QLineEdit()
        form.addRow("tags", self.tags_edit)
        self.props_section.add_layout(form)
        save_button = QtWidgets.QPushButton("Save")
        save_button.clicked.connect(self._save_meta)
        self.props_section.add(save_button)
        layout.addWidget(self.props_section)

        # notes section
        self.notes_section = CollapsibleSection("Notes", expanded=False)
        self.notes_edit = QtWidgets.QPlainTextEdit()
        self.notes_edit.setMaximumHeight(70)
        self.notes_section.add(self.notes_edit)
        notes_row = QtWidgets.QHBoxLayout()
        notes_row.addStretch(1)
        notes_save = QtWidgets.QPushButton("Save notes")
        notes_save.clicked.connect(self._save_notes)
        notes_row.addWidget(notes_save)
        self.notes_section.add_layout(notes_row)
        layout.addWidget(self.notes_section)

        # actions section
        self.actions_section = CollapsibleSection("Actions")
        actions = QtWidgets.QGridLayout()
        actions.setSpacing(4)
        for index, (label, handler) in enumerate((
                ("Open Latest", self._open_latest),
                ("Version Up", self._version_up),
                ("Snapshot", self._snapshot),
                ("To SleepyQueue", self._send_batch),
                ("Open Folder", self._open_folder))):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button, index // 2, index % 2)
        self.actions_section.add_layout(actions)
        layout.addWidget(self.actions_section)

        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    # ------------------------------------------------------------------
    # data
    # ------------------------------------------------------------------
    def reload(self):
        combo = self.project_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("All", None)
        for project in self.state.projects:
            combo.addItem(project["name"], project["path"])
        if self.state.current_project:
            index = combo.findData(self.state.current_project)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.blockSignals(False)
        self.reload_bins()
        self._fill_editor()

    def reload_bins(self):
        self.bins.blockSignals(True)
        self.bins.clear()
        text = self.search_edit.text().lower().strip()
        for project in self.state.projects:
            shots = [s for s in self.state.shots
                     if s.get("project_path") == project["path"]]
            if text:
                shots = [s for s in shots
                         if text in s["name"].lower()
                         or text in ((s.get("config") or {}).get("notes") or "").lower()]
            if not shots and text:
                continue
            project_item = QtWidgets.QTreeWidgetItem([project["name"], ""])
            project_item.setData(0, QtCore.Qt.UserRole, ("project", project["path"]))
            for shot in shots:
                item = QtWidgets.QTreeWidgetItem(
                    [shot["name"] + "_comp", STATUS_LABELS.get(shot.status, shot.status)])
                item.setData(0, QtCore.Qt.UserRole, ("shot", shot))
                item.setForeground(1, QtGui.QColor(theme.status_color(shot.status)))
                project_item.addChild(item)
            self.bins.addTopLevelItem(project_item)
            project_item.setExpanded(True)
        self.bins.blockSignals(False)

    def _fill_editor(self):
        shot = self.shot
        if shot is None:
            self.editor_header.setText("no shot selected")
            self.versions_list.clear()
            return
        self.editor_header.setText(shot["name"] + "_comp" +
                                   ("" if shot.get("managed") else "   (discovered)"))
        self.versions_list.clear()
        entries = self.state.shot_versions(shot)
        for entry in entries[:20]:
            item = QtWidgets.QListWidgetItem("  {}    {}    {:.1f} MB".format(
                entry["name"], date.fromtimestamp(entry["mtime"]).isoformat(),
                entry["size"] / 1048576.0))
            item.setData(QtCore.Qt.UserRole, entry["path"])
            self.versions_list.addItem(item)
        if not entries:
            self.versions_list.addItem("  (no scripts yet)")

    # ------------------------------------------------------------------
    # selection and edits
    # ------------------------------------------------------------------
    def _bins_selected(self):
        items = self.bins.selectedItems()
        if not items:
            return
        data = items[0].data(0, QtCore.Qt.UserRole)
        if not data or data[0] != "shot":
            return
        self.shot = data[1]
        config = self.shot.get("config") or {}
        self.status_combo.blockSignals(True)
        self.status_combo.setCurrentIndex(self.status_combo.findData(self.shot.status))
        self.status_combo.blockSignals(False)
        raw_due = config.get("due")
        try:
            self.due_edit.setDate(date.fromisoformat(raw_due) if raw_due else date.today())
        except ValueError:
            self.due_edit.setDate(date.today())
        self.tags_edit.setText(", ".join(config.get("tags", [])))
        self.notes_edit.setPlainText(config.get("notes", ""))
        self._fill_editor()

    def _bins_double_click(self, item):
        data = item.data(0, QtCore.Qt.UserRole)
        if data and data[0] == "shot":
            self._open_latest()

    def _project_changed(self, _index):
        self.state.current_project = self.project_combo.currentData()
        self.reload_bins()

    def _status_edited(self, _index):
        if self.shot is None:
            return
        try:
            schema.save_shot(self.shot["path"], {"status": self.status_combo.currentData()})
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Project Manager",
                                          "Could not save status:\n{}".format(exc))
            return
        self.shot.setdefault("config", {})["status"] = self.status_combo.currentData()
        self.reload_bins()

    def _save_meta(self):
        if self.shot is None:
            return
        tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        values = {"due": self.due_edit.date().toString("yyyy-MM-dd"), "tags": tags}
        try:
            schema.save_shot(self.shot["path"], values)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Project Manager",
                                          "Could not save:\n{}".format(exc))
            return
        self.shot.setdefault("config", {}).update(values)
        self.reload_bins()

    def _save_notes(self):
        if self.shot is None:
            return
        try:
            schema.save_shot(self.shot["path"], {"notes": self.notes_edit.toPlainText()})
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Project Manager",
                                          "Could not save notes:\n{}".format(exc))
            return
        self.shot.setdefault("config", {})["notes"] = self.notes_edit.toPlainText()

    # ------------------------------------------------------------------
    def _refresh(self):
        self.state.refresh(force=True)
        self.reload()

    def _new_shot(self):
        project_path = self.project_combo.currentData()
        projects = [p for p in self.state.projects
                    if project_path is None or p["path"] == project_path]
        if not projects:
            QtWidgets.QMessageBox.information(
                self, "Project Manager", "No projects available. Check watched roots.")
            return
        from shellui.dialogs import NewShotDialog
        dialog = NewShotDialog(projects[0], self.state, self)
        if dialog.exec() and dialog.created_path:
            self.state.refresh(force=True)
            self.reload()

    def _open_version(self, item):
        path = item.data(QtCore.Qt.UserRole)
        if not path:
            return
        self._open(path)

    def _open_latest(self):
        if self.shot is None:
            return
        entry = latest_version(self.shot.get("comp_dir"))
        if entry is None:
            QtWidgets.QMessageBox.information(
                self, "Project Manager", "This shot has no scripts yet.")
            return
        self._open(entry["path"])

    def _open(self, path):
        ok, message = self.backend.open_script(path)
        if ok and self.shot is not None:
            self.state.remember_open(self.shot)
        elif not ok:
            QtWidgets.QMessageBox.information(self, "Project Manager", message)

    def _version_up(self):
        if self.shot is None:
            return
        new_path, message = self.backend.version_up(self.shot)
        QtWidgets.QMessageBox.information(self, "Project Manager", message)
        if new_path:
            self._fill_editor()

    def _snapshot(self):
        ok, message = self.backend.take_snapshot()
        QtWidgets.QMessageBox.information(self, "Project Manager", message)

    def _send_batch(self):
        ok, message = self.backend.send_to_sleepy_queue()
        QtWidgets.QMessageBox.information(self, "Project Manager", message)

    def _open_folder(self):
        if self.shot is None:
            return
        ok, message = self.backend.open_folder(self.shot["path"])
        if not ok:
            QtWidgets.QMessageBox.information(self, "Project Manager", message)
