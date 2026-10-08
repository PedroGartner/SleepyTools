"""V2 inspector: the selected shot's detail panel."""

from datetime import date

from SleepyCore.qt import QtCore, QtWidgets

from shellcore import schema
from shellcore.schema import STATUS_LABELS, STATUS_ORDER
from shellui.widgets import Thumb


class InspectorPanel(QtWidgets.QWidget):
    """Right-hand detail area: thumbnail, status editor, versions, notes, files."""

    statusChanged = QtCore.Signal(object)

    def __init__(self, state, backend, parent=None):
        super(InspectorPanel, self).__init__(parent)
        self.state = state
        self.backend = backend
        self.shot = None
        self.setMinimumWidth(280)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        content = QtWidgets.QWidget()
        self.layout_root = QtWidgets.QVBoxLayout(content)
        self.layout_root.setContentsMargins(12, 10, 12, 10)
        self.layout_root.setSpacing(10)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.set_shot(None)

    def set_shot(self, shot):
        self.shot = shot
        clear = self.layout_root
        while clear.count():
            item = clear.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.hide()
                widget.deleteLater()
        title = QtWidgets.QLabel("INSPECTOR")
        title.setStyleSheet("font-weight: 700; letter-spacing: 1.5px; font-size: 10px;"
                            " color: #9a9ea6;")
        self.layout_root.addWidget(title)

        if shot is None:
            note = QtWidgets.QLabel("Select a shot in the table or the tree.")
            note.setObjectName("ShellDim")
            note.setWordWrap(True)
            self.layout_root.addWidget(note)
            self.layout_root.addStretch(1)
            return

        config = shot.get("config") or {}
        header = QtWidgets.QLabel(shot["name"])
        header.setStyleSheet("font-weight: 700; font-size: 17px;")
        self.layout_root.addWidget(header)
        self.layout_root.addWidget(Thumb(shot["name"], self._thumb_path(shot), (240, 132)))

        status_label = QtWidgets.QLabel("STATUS")
        status_label.setStyleSheet("font-weight: 700; font-size: 10px; color: #9a9ea6;")
        self.layout_root.addWidget(status_label)
        self.status_combo = QtWidgets.QComboBox()
        for status in STATUS_ORDER:
            self.status_combo.addItem(STATUS_LABELS[status], status)
        self.status_combo.setCurrentIndex(self.status_combo.findData(shot.status))
        self.status_combo.currentIndexChanged.connect(self._status_edited)
        self.layout_root.addWidget(self.status_combo)

        fields = QtWidgets.QFormLayout()
        fields.setSpacing(6)
        self.due_edit = QtWidgets.QDateEdit()
        self.due_edit.setCalendarPopup(True)
        self.due_edit.setDisplayFormat("yyyy-MM-dd")
        raw_due = config.get("due")
        try:
            self.due_edit.setDate(date.fromisoformat(raw_due) if raw_due else date.today())
        except ValueError:
            self.due_edit.setDate(date.today())
        fields.addRow("Due", self.due_edit)
        self.tags_edit = QtWidgets.QLineEdit(", ".join(config.get("tags", [])))
        fields.addRow("Tags", self.tags_edit)
        self.layout_root.addLayout(fields)

        save_button = QtWidgets.QPushButton("Save fields")
        save_button.clicked.connect(self._save_fields)
        self.layout_root.addWidget(save_button)

        notes_label = QtWidgets.QLabel("NOTES")
        notes_label.setStyleSheet("font-weight: 700; font-size: 10px; color: #9a9ea6;")
        self.layout_root.addWidget(notes_label)
        self.notes_edit = QtWidgets.QPlainTextEdit(config.get("notes", ""))
        self.notes_edit.setMaximumHeight(90)
        self.layout_root.addWidget(self.notes_edit)
        save_notes = QtWidgets.QPushButton("Save notes")
        save_notes.clicked.connect(self._save_notes)
        self.layout_root.addWidget(save_notes)

        versions_label = QtWidgets.QLabel("VERSIONS")
        versions_label.setStyleSheet("font-weight: 700; font-size: 10px; color: #9a9ea6;")
        self.layout_root.addWidget(versions_label)
        entries = self.state.shot_versions(shot)
        if not entries:
            empty = QtWidgets.QLabel("No scripts yet.")
            empty.setObjectName("ShellDim")
            self.layout_root.addWidget(empty)
        for entry in entries[:10]:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(6)
            name = QtWidgets.QLabel(entry["name"])
            row.addWidget(name, 1)
            open_button = QtWidgets.QToolButton()
            open_button.setText("Open")
            open_button.clicked.connect(
                lambda _=False, path=entry["path"]: self._open_path(path))
            row.addWidget(open_button)
            self.layout_root.addLayout(row)

        files_label = QtWidgets.QLabel("FILES")
        files_label.setStyleSheet("font-weight: 700; font-size: 10px; color: #9a9ea6;")
        self.layout_root.addWidget(files_label)
        for label, path in (
                ("Shot folder", shot["path"]),
                ("Comp folder", shot.get("comp_dir") or "")):
            if not path:
                continue
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(6)
            name = QtWidgets.QLabel(label)
            name.setObjectName("ShellDim")
            row.addWidget(name)
            value = QtWidgets.QLabel(path)
            value.setStyleSheet("font-size: 10px;")
            value.setWordWrap(True)
            row.addWidget(value, 1)
            copy_button = QtWidgets.QToolButton()
            copy_button.setText("Copy")
            copy_button.clicked.connect(
                lambda _=False, p=path: QtWidgets.QApplication.clipboard().setText(p))
            row.addWidget(copy_button)
            self.layout_root.addLayout(row)

        actions = QtWidgets.QHBoxLayout()
        for label, handler in (
                ("Open folder", self._open_folder),
                ("Version up", self._version_up),
                ("Snapshot", self._snapshot),
                ("To Batch", self._send_batch)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button)
        self.layout_root.addLayout(actions)
        self.layout_root.addStretch(1)

    # ------------------------------------------------------------------
    def _status_edited(self, _index):
        if self.shot is None:
            return
        status = self.status_combo.currentData()
        try:
            schema.save_shot(self.shot["path"], {"status": status})
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Project Manager",
                                          "Could not save status:\n{}".format(exc))
            return
        self.shot.setdefault("config", {})["status"] = status
        self.statusChanged.emit(self.shot)

    def _save_fields(self):
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

    def _open_path(self, path):
        ok, message = self.backend.open_script(path)
        if ok:
            self.state.remember_open(self.shot)
        else:
            QtWidgets.QMessageBox.information(self, "Project Manager", message)

    def _open_folder(self):
        ok, message = self.backend.open_folder(self.shot["path"])
        if not ok:
            QtWidgets.QMessageBox.information(self, "Project Manager", message)

    def _version_up(self):
        new_path, message = self.backend.version_up(self.shot)
        QtWidgets.QMessageBox.information(self, "Project Manager", message)
        if new_path:
            self.set_shot(self.shot)

    def _snapshot(self):
        ok, message = self.backend.take_snapshot()
        QtWidgets.QMessageBox.information(self, "Project Manager", message)

    def _send_batch(self):
        ok, message = self.backend.send_to_sleepy_queue()
        QtWidgets.QMessageBox.information(self, "Project Manager", message)

    def _thumb_path(self, shot):
        thumbs = self.state.shot_thumbnails(shot, limit=1)
        return thumbs[0] if thumbs else None
