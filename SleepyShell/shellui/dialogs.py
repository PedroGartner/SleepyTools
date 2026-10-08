"""Dialogs: New Project, New Shot, Adopt discovered shots."""

import os

from SleepyCore.qt import QtCore, QtWidgets

from shellcore import ops
from shellcore.schema import load_project


class NewProjectDialog(QtWidgets.QDialog):
    """Create a project folder with project.json and a shots/ folder.

    Every field maps to a real project.json value; the defaults come
    from the global preferences so the dialog is normally just a name.
    """

    def __init__(self, state, parent=None):
        super(NewProjectDialog, self).__init__(parent)
        self.state = state
        self.created_path = None
        self.created_shot = None
        self.setWindowTitle("New Project")
        self.setMinimumWidth(470)

        prefs = state.prefs
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setSpacing(8)

        self.root_combo = QtWidgets.QComboBox()
        for root in prefs.get("watched_roots", []):
            self.root_combo.addItem(root, root)
        form.addRow("Location (watched root)", self.root_combo)
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("ClientX_Campaign")
        form.addRow("Project name", self.name_edit)
        self.client_edit = QtWidgets.QLineEdit()
        form.addRow("Client", self.client_edit)
        self.tags_edit = QtWidgets.QLineEdit()
        self.tags_edit.setPlaceholderText("campaign, beauty")
        form.addRow("Tags", self.tags_edit)

        tech_row = QtWidgets.QHBoxLayout()
        tech_row.setSpacing(8)
        self.fps_spin = QtWidgets.QDoubleSpinBox()
        self.fps_spin.setRange(1.0, 240.0)
        self.fps_spin.setValue(25.0)
        tech_row.addWidget(self.fps_spin)
        self.resolution_edit = QtWidgets.QLineEdit("3840x2160")
        tech_row.addWidget(self.resolution_edit, 1)
        form.addRow("Frame rate + format", tech_row)
        tech_row2 = QtWidgets.QHBoxLayout()
        tech_row2.setSpacing(8)
        self.space_edit = QtWidgets.QLineEdit("ACEScg")
        tech_row2.addWidget(self.space_edit, 1)
        self.handles_spin = QtWidgets.QSpinBox()
        self.handles_spin.setRange(0, 240)
        self.handles_spin.setValue(8)
        tech_row2.addWidget(self.handles_spin)
        form.addRow("Working space + handles", tech_row2)

        self.shot_pattern_edit = QtWidgets.QLineEdit(
            prefs.get("shot_pattern", "sh###"))
        form.addRow("Shot name pattern", self.shot_pattern_edit)
        self.script_pattern_edit = QtWidgets.QLineEdit(
            prefs.get("script_pattern", "{shot}_comp_v###.nk"))
        form.addRow("Script name pattern", self.script_pattern_edit)

        structure_row = QtWidgets.QHBoxLayout()
        structure_row.setSpacing(8)
        self.structure_buttons = {}
        for label, value in (("Standard (suite)", "standard"),
                             ("Client structure", "client")):
            chip = QtWidgets.QToolButton()
            chip.setObjectName("ShellPill")
            chip.setText(label)
            chip.setCheckable(True)
            chip.setChecked(value == "standard")
            chip.clicked.connect(lambda _=False, v=value: self._set_structure(v))
            structure_row.addWidget(chip)
            self.structure_buttons[value] = chip
        structure_row.addStretch(1)
        form.addRow("Folder structure", structure_row)

        template_row = QtWidgets.QHBoxLayout()
        template_row.setSpacing(8)
        self.template_edit = QtWidgets.QLineEdit()
        self.template_edit.setPlaceholderText(
            "optional .nk copied as every first version")
        template_row.addWidget(self.template_edit, 1)
        browse = QtWidgets.QPushButton("Browse...")
        browse.clicked.connect(self._browse_template)
        template_row.addWidget(browse)
        form.addRow("Comp template", template_row)

        self.render_edit = QtWidgets.QLineEdit()
        self.render_edit.setPlaceholderText(
            "D:\\...\\renders\\{shot}\\ (SleepyQueue default output)")
        form.addRow("Render output", self.render_edit)

        first_shot = prefs.get("shot_pattern", "sh###").replace("###", "001")
        self.first_shot_check = QtWidgets.QCheckBox(
            "Create the first shot now ({})".format(first_shot))
        self.first_shot_check.setChecked(True)
        layout.addWidget(self.first_shot_check)
        layout.addLayout(form)

        self.message = QtWidgets.QLabel("")
        self.message.setObjectName("ShellDim")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        create = QtWidgets.QPushButton("Create project")
        create.setProperty("accent", True)
        create.clicked.connect(self._create)
        buttons.addWidget(cancel)
        buttons.addWidget(create)
        layout.addLayout(buttons)

        if self.root_combo.count() == 0:
            self.message.setText("No watched roots configured. Add one in "
                                 "Preferences > Scanning first.")
            create.setEnabled(False)

    def _set_structure(self, value):
        for key, chip in self.structure_buttons.items():
            chip.setChecked(key == value)

    def _browse_template(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select a comp template (.nk)", "", "Nuke scripts (*.nk)")
        if path:
            self.template_edit.setText(path)

    def _create(self):
        root = self.root_combo.currentData()
        name = self.name_edit.text().strip()
        if not root or not name:
            self.message.setText("Pick a location and a project name.")
            return
        tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        config = {
            "client": self.client_edit.text().strip(),
            "tags": tags,
            "fps": self.fps_spin.value(),
            "resolution": self.resolution_edit.text().strip(),
            "working_space": self.space_edit.text().strip(),
            "handles": self.handles_spin.value(),
            "shot_pattern": self.shot_pattern_edit.text().strip() or None,
            "script_pattern": self.script_pattern_edit.text().strip() or None,
            "folder_template": ("client"
                                if self.structure_buttons["client"].isChecked()
                                else "standard"),
            "comp_template": self.template_edit.text().strip(),
            "render_output": self.render_edit.text().strip(),
        }
        config = {k: v for k, v in config.items() if v not in (None, "")}
        try:
            self.created_path = ops.create_project(root, name, config)
        except ops.OpError as exc:
            self.message.setText(str(exc))
            return
        if self.first_shot_check.isChecked():
            try:
                project_config, _ = load_project(self.created_path)
                self.created_shot, _ = ops.create_shot(
                    self.created_path, None, self.state.prefs, project_config)
            except ops.OpError as exc:
                self.message.setText("Project created, but the first shot "
                                     "failed: {}".format(exc))
        self.accept()


class NewShotDialog(QtWidgets.QDialog):
    """Create a shot from the template inside an existing project."""

    def __init__(self, project, state, parent=None):
        super(NewShotDialog, self).__init__(parent)
        self.state = state
        self.project = project
        self.created_path = None
        self.created_script = None
        self.setWindowTitle("New Shot in {}".format(project["name"]))
        self.setMinimumWidth(380)

        config, _ = load_project(project["path"])
        prefs = state.prefs
        from shellcore import naming
        shots_dir = os.path.join(project["path"], "shots")
        if not os.path.isdir(shots_dir):
            shots_dir = project["path"]
        pattern = config.get("shot_pattern") or prefs.get("shot_pattern", "sh###")
        highest = naming.highest_shot_number(shots_dir, pattern)
        suggested = naming.expand_shot_name(pattern, highest + 1)

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        self.name_edit = QtWidgets.QLineEdit(suggested)
        form.addRow("Shot name", self.name_edit)
        layout.addLayout(form)
        folders = config.get("folder_template", "standard")
        info = QtWidgets.QLabel(
            "Creates: {}  +  {}".format(
                ", ".join(prefs.get("folder_template", [])) if folders == "standard"
                else "shot folder only (client structure)",
                (config.get("script_pattern") or prefs.get("script_pattern", "{shot}_comp_v###.nk"))
                .replace("{shot}", "<shot>")))
        info.setObjectName("ShellDim")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.message = QtWidgets.QLabel("")
        self.message.setObjectName("ShellDim")
        layout.addWidget(self.message)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        create = QtWidgets.QPushButton("Create shot")
        create.setProperty("accent", True)
        create.clicked.connect(self._create)
        buttons.addWidget(cancel)
        buttons.addWidget(create)
        layout.addLayout(buttons)

    def _create(self):
        config, _ = load_project(self.project["path"])
        try:
            self.created_path, self.created_script = ops.create_shot(
                self.project["path"], self.name_edit.text().strip() or None,
                self.state.prefs, config)
        except ops.OpError as exc:
            self.message.setText(str(exc))
            return
        self.accept()


class AdoptDialog(QtWidgets.QDialog):
    """Adopt discovered shots: writes shot.json only, nothing is moved.

    Styled like the mockup's adopt modal: header strip, dim note with
    accent keywords, checkbox rows with name + path, right-aligned
    footer with the live 'Adopt N shots' primary button.
    """

    def __init__(self, state, parent=None):
        super(AdoptDialog, self).__init__(parent)
        self.state = state
        self.adopted = []
        self.setWindowTitle("Adopt discovered shots")
        self.setFixedWidth(520)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QtWidgets.QLabel("Adopt discovered shots")
        header.setStyleSheet("font-weight: 600; font-size: 13px; padding: 13px 16px;"
                             " border-bottom: 1px solid #2a2c30;")
        layout.addWidget(header)

        body = QtWidgets.QWidget()
        body_layout = QtWidgets.QVBoxLayout(body)
        body_layout.setContentsMargins(16, 14, 16, 14)
        body_layout.setSpacing(4)
        note = QtWidgets.QLabel(
            "These folders contain comp scripts but no "
            "<b style='color:#f0a043;'>shot.json</b> yet.\n"
            "Adopting writes a settings file only — "
            "<b style='color:#f0a043;'>nothing is moved, renamed or opened</b>. "
            "Until adopted they stay visible as read-only, discovered shots.")
        note.setObjectName("ShellDim")
        note.setWordWrap(True)
        note.setTextFormat(QtCore.Qt.RichText)
        note.setStyleSheet("font-size: 11.5px; padding-bottom: 8px;")
        body_layout.addWidget(note)

        self._candidates = []
        for shot in state.shots:
            if not shot.get("managed"):
                self._candidates.append(shot)
        self.checks = []
        if self._candidates:
            for shot in self._candidates:
                row = QtWidgets.QFrame()
                row.setStyleSheet("QFrame { border-radius: 5px; padding: 7px 8px; }"
                                  "QFrame:hover { background: #26272a; }")
                row_layout = QtWidgets.QHBoxLayout(row)
                row_layout.setContentsMargins(8, 4, 8, 4)
                row_layout.setSpacing(10)
                check = QtWidgets.QCheckBox()
                check.setChecked(True)
                check.stateChanged.connect(lambda _s: self._update_count())
                row_layout.addWidget(check)
                name = QtWidgets.QLabel(shot["name"])
                name.setStyleSheet("font-weight: 600; background: transparent;")
                name.setFixedWidth(150)
                row_layout.addWidget(name)
                path = QtWidgets.QLabel("{}  ·  {} versions".format(
                    shot.get("project_name", ""),
                    len(state.shot_versions(shot))))
                path.setObjectName("ShellDim")
                path.setStyleSheet("font-size: 11px; background: transparent;")
                row_layout.addWidget(path, 1)
                body_layout.addWidget(row)
                self.checks.append((shot, check))
        else:
            body_layout.addWidget(QtWidgets.QLabel(
                "Nothing to adopt: every discovered shot is already managed."))
        layout.addWidget(body, 1)

        footer = QtWidgets.QWidget()
        footer.setStyleSheet("border-top: 1px solid #2a2c30;")
        footer_layout = QtWidgets.QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 12, 16, 12)
        footer_layout.addStretch(1)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        footer_layout.addWidget(cancel)
        self.adopt_button = QtWidgets.QPushButton("Adopt selected")
        self.adopt_button.setProperty("accent", True)
        self.adopt_button.clicked.connect(self._adopt)
        footer_layout.addWidget(self.adopt_button)
        layout.addWidget(footer)
        if not self._candidates:
            self.adopt_button.setEnabled(False)
        self._update_count()

    def _update_count(self):
        count = sum(1 for _shot, check in self.checks if check.isChecked())
        self.adopt_button.setText("Adopt {} shot{}".format(
            count, "" if count == 1 else "s"))
        self.adopt_button.setEnabled(count > 0)

    def _adopt(self):
        targets = [shot for shot, check in self.checks if check.isChecked()]
        if not targets:
            self.reject()
            return
        adopted, failures = ops.adopt_shots([shot["path"] for shot in targets])
        self.adopted = adopted
        if failures:
            QtWidgets.QMessageBox.warning(
                self, "Sleepy Shell", "Some shots could not be adopted:\n" + "\n".join(failures))
        self.accept()
