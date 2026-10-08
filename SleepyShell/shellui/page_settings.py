"""Preferences (global) and Project Settings (per project) pages.

Both follow the mockup's settings layout: a left navigation column
(#ShellSetNav with accent-bordered active rows) and group cards
(.setgroup) holding label/control rows (.frow: 230px label column with
a bold title and dim description, controls on the right).

Every control is wired: appearance applies live, watched roots and the
folder template edit the real prefs, project settings write
project.json, and the danger zone actions do exactly what their labels
say with confirmations.
"""

import os

from SleepyCore.qt import QtCore, QtWidgets

from shellcore import prefs as prefs_mod, scan as scan_mod
from shellcore.schema import load_project, save_project
from shellui import theme
from shellui.widgets import (Chip, ClickableFrame, NeutralChip, Toggle,
                             set_section_font, styled)


# ---------------------------------------------------------------------------
# shared building blocks (the mockup's setgroup / frow / sel2 / swatch)
# ---------------------------------------------------------------------------

def _setgroup(title):
    group = QtWidgets.QFrame()
    group.setObjectName("ShellSection")
    layout = QtWidgets.QVBoxLayout(group)
    layout.setContentsMargins(16, 4, 16, 8)
    layout.setSpacing(0)
    heading = QtWidgets.QLabel(title.upper())
    set_section_font(heading, size=10.5, spacing=1.1)
    heading.setStyleSheet("color: {};".format(theme.DARK["dim"]))
    layout.addWidget(heading)
    return group, layout


def _frow(title, description=None, control=None):
    """One .frow: 230px label column (bold + dim description) + controls."""
    row = QtWidgets.QHBoxLayout()
    row.setContentsMargins(0, 11, 0, 11)
    row.setSpacing(14)
    fl = QtWidgets.QVBoxLayout()
    fl.setSpacing(2)
    title_label = QtWidgets.QLabel(title)
    title_label.setStyleSheet("font-weight: 600; font-size: 12.5px;"
                              " background: transparent;")
    fl.addWidget(title_label)
    if description:
        desc = QtWidgets.QLabel(description)
        desc.setObjectName("ShellDim")
        desc.setStyleSheet("font-size: 11px;")
        desc.setWordWrap(True)
        fl.addWidget(desc)
    fl_holder = QtWidgets.QWidget()
    fl_holder.setLayout(fl)
    fl_holder.setFixedWidth(230)
    row.addWidget(fl_holder)
    fc = QtWidgets.QHBoxLayout()
    fc.setSpacing(8)
    if control is not None:
        if isinstance(control, QtWidgets.QWidget):
            fc.addWidget(control)
        else:  # a nested layout
            fc.addLayout(control)
    row.addLayout(fc, 1)
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.HLine)
    line.setStyleSheet("background: {}; max-height: 1px; border: none;".format(
        theme.DARK["line_soft"]))
    return row, line, fc


def _finish_frow(layout, row, line):
    layout.addLayout(row)
    if line is not None:
        layout.addWidget(line)


def _end_group(group_layout):
    """Drop the trailing separator so the last row has no bottom border."""
    for i in reversed(range(group_layout.count())):
        item = group_layout.itemAt(i)
        widget = item.widget() if item is not None else None
        if widget is None:
            continue
        if isinstance(widget, QtWidgets.QFrame) and \
                widget.frameShape() == QtWidgets.QFrame.HLine:
            group_layout.removeItem(item)
            widget.deleteLater()
        break
    group_layout.addStretch(1)


def _sel2(text, checked=False):
    """The mockup's .sel2 pill: window bg, line border; active = accent.

    Styled via the app stylesheet (property sel2=true) so accent changes
    recolor it without rebuilding the page.
    """
    button = QtWidgets.QPushButton(text)
    button.setProperty("sel2", True)
    button.setCheckable(True)
    button.setChecked(checked)
    button.setCursor(QtCore.Qt.PointingHandCursor)
    return button


def _swatch(color, checked=False):
    button = QtWidgets.QPushButton()
    button.setObjectName("ShellSwatch")
    button.setFixedSize(22, 22)
    button.setCheckable(True)
    button.setChecked(checked)
    button.setCursor(QtCore.Qt.PointingHandCursor)
    # only the fill is inline; the border comes from #ShellSwatch QSS
    button.setStyleSheet("background-color: {};".format(color))
    return button


def _heading_block(layout, title, description):
    heading = QtWidgets.QLabel(title)
    heading.setStyleSheet("font-size: 16px; font-weight: 600;"
                          " background: transparent;")
    layout.addWidget(heading)
    desc = QtWidgets.QLabel(description)
    desc.setObjectName("ShellDim")
    desc.setStyleSheet("font-size: 11.5px;")
    desc.setWordWrap(True)
    layout.addWidget(desc)
    layout.addSpacing(10)


# ---------------------------------------------------------------------------
# Preferences (global)
# ---------------------------------------------------------------------------

class PreferencesPage(QtWidgets.QWidget):
    def __init__(self, state, parent=None):
        super(PreferencesPage, self).__init__(parent)
        self.state = state
        self._folder_list = []
        self._loading = False
        styled(self)
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.nav = self._build_nav()
        outer.addWidget(self.nav)

        self.stack = QtWidgets.QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_appearance())
        self.stack.addWidget(self._build_rules())
        self.stack.addWidget(self._build_scanning())
        self.stack.addWidget(self._build_startup())
        self.stack.addWidget(self._build_advanced())
        self._nav_buttons[0].setChecked(True)
        self.load()

    def status_hint(self):
        return "Global preferences: <b>{}</b>".format(prefs_mod.PREFS_FILE)

    # -- nav --------------------------------------------------------------
    def _build_nav(self):
        nav = QtWidgets.QFrame()
        nav.setObjectName("ShellSetNav")
        nav.setFixedWidth(200)
        layout = QtWidgets.QVBoxLayout(nav)
        layout.setContentsMargins(0, 14, 0, 14)
        layout.setSpacing(0)
        self._nav_buttons = []
        entries = (
            ("Appearance", "accent, theme, density"),
            ("New Shot Rules", "folders & naming templates"),
            ("Scanning", "watched roots, cache"),
            ("Startup", "resume card, stale check"),
            ("Advanced", "schema versions, logs"),
        )
        for index, (label, sub) in enumerate(entries):
            button = QtWidgets.QPushButton("  " + label)
            button.setObjectName("ShellSNav")
            button.setCheckable(True)
            button.setCursor(QtCore.Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, i=index: self._goto(i))
            wrap = QtWidgets.QVBoxLayout()
            wrap.setContentsMargins(0, 0, 0, 0)
            wrap.setSpacing(0)
            wrap.addWidget(button)
            small = QtWidgets.QLabel("    " + sub)
            small.setObjectName("ShellDim")
            small.setStyleSheet("font-size: 10.5px; padding: 0 0 4px 0;")
            wrap.addWidget(small)
            layout.addLayout(wrap)
            self._nav_buttons.append(button)
        layout.addStretch(1)
        return nav

    def _goto(self, index):
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self._nav_buttons):
            button.setChecked(i == index)

    # -- body helper -------------------------------------------------------
    def _body(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        content = styled(QtWidgets.QWidget())
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)
        scroll.setWidget(content)
        return scroll, layout

    # -- appearance ----------------------------------------------------------
    def _build_appearance(self):
        scroll, layout = self._body()
        _heading_block(layout, "Appearance",
                       "Global settings apply to the whole Sleepy suite — tools "
                       "pick the accent up from SleepyCore.themes automatically.")

        group, group_layout = _setgroup("Theme")

        # accent color
        accent_control = QtWidgets.QWidget()
        accent_row = QtWidgets.QHBoxLayout(accent_control)
        accent_row.setContentsMargins(0, 0, 0, 0)
        accent_row.setSpacing(8)
        self._accent_buttons = []
        for accent in theme.ACCENTS:
            button = _swatch(accent)
            button.clicked.connect(lambda _=False, c=accent: self._set_accent(c))
            accent_row.addWidget(button)
            self._accent_buttons.append((accent, button))
        self._accent_name = QtWidgets.QLabel("")
        self._accent_name.setObjectName("ShellDim")
        self._accent_name.setStyleSheet("font-size: 11px;")
        accent_row.addWidget(self._accent_name)
        accent_row.addStretch(1)
        row, line, _fc = _frow(
            "Accent color",
            "Used for selections, primary buttons and highlights in every "
            "Sleepy tool.", accent_control)
        _finish_frow(group_layout, row, line)

        # theme mode chips
        mode_control = QtWidgets.QWidget()
        mode_row = QtWidgets.QHBoxLayout(mode_control)
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(8)
        self.mode_buttons = {}
        for label, value in (("Follow Nuke", "nuke"), ("Sleepy Dark", "dark"),
                             ("Light", "light")):
            chip = _sel2(label + ("  exp." if value == "light" else ""))
            chip.clicked.connect(lambda _=False, v=value: self._set_mode(v))
            mode_row.addWidget(chip)
            self.mode_buttons[value] = chip
        mode_row.addStretch(1)
        row, line, _fc = _frow(
            "Theme mode",
            "Light mode is experimental; Nuke 14+ native theming is respected.",
            mode_control)
        _finish_frow(group_layout, row, line)

        # density + font
        density_control = QtWidgets.QWidget()
        density_row = QtWidgets.QHBoxLayout(density_control)
        density_row.setContentsMargins(0, 0, 0, 0)
        density_row.setSpacing(8)
        self.density_buttons = {}
        for label, value in (("Comfortable", "comfortable"), ("Compact", "compact")):
            chip = _sel2(label)
            chip.clicked.connect(lambda _=False, v=value: self._set_density(v))
            density_row.addWidget(chip)
            self.density_buttons[value] = chip
        density_row.addSpacing(8)
        self.font_spin = QtWidgets.QSpinBox()
        self.font_spin.setRange(8, 18)
        self.font_spin.setSuffix(" px")
        self.font_spin.valueChanged.connect(self._changed)
        density_row.addWidget(self.font_spin)
        density_row.addStretch(1)
        row, line, _fc = _frow(
            "Density & font",
            "Comfortable for solo review, Compact fits small panels.",
            density_control)
        _finish_frow(group_layout, row, line)

        # interface zoom (whole-UI, applied on restart)
        zoom_control = QtWidgets.QWidget()
        zoom_row = QtWidgets.QHBoxLayout(zoom_control)
        zoom_row.setContentsMargins(0, 0, 0, 0)
        zoom_row.setSpacing(8)
        self.zoom_buttons = {}
        for label, value in (("100%", 1.0), ("110%", 1.1), ("125%", 1.25),
                             ("150%", 1.5)):
            chip = _sel2(label)
            chip.clicked.connect(lambda _=False, v=value: self._set_zoom(v))
            zoom_row.addWidget(chip)
            self.zoom_buttons[value] = chip
        zoom_row.addStretch(1)
        row, line, _fc = _frow(
            "Interface zoom",
            "Scales the entire interface. Applies the next time the "
            "launcher starts.",
            zoom_control)
        _finish_frow(group_layout, row, line)
        _end_group(group_layout)
        layout.addWidget(group)
        layout.addStretch(1)
        return scroll

    # -- new shot rules -------------------------------------------------------
    def _build_rules(self):
        from shellcore import naming
        scroll, layout = self._body()
        _heading_block(layout, "New Shot Rules",
                       "The template used when creating shots. Each project can "
                       "override this in Project Settings.")

        group, group_layout = _setgroup("Folder template")
        folders_control = QtWidgets.QWidget()
        folders_col = QtWidgets.QVBoxLayout(folders_control)
        folders_col.setContentsMargins(0, 0, 0, 0)
        folders_col.setSpacing(6)
        self._folder_items = QtWidgets.QVBoxLayout()
        self._folder_items.setSpacing(6)
        folders_col.addLayout(self._folder_items)
        add_item = QtWidgets.QPushButton("+ Add folder…")
        add_item.setStyleSheet("QPushButton { background: transparent;"
                               " border: 1px dashed #3a3c40; border-radius: 4px;"
                               " padding: 5px 10px; color: #9a9ea6; text-align: left; }"
                               "QPushButton:hover { color: #e6e6e6; }")
        add_item.clicked.connect(self._add_folder)
        folders_col.addWidget(add_item)
        buttons_row = QtWidgets.QHBoxLayout()
        buttons_row.setSpacing(6)
        up_button = QtWidgets.QPushButton("Up")
        up_button.clicked.connect(lambda: self._move_folder(-1))
        down_button = QtWidgets.QPushButton("Down")
        down_button.clicked.connect(lambda: self._move_folder(1))
        remove_button = QtWidgets.QPushButton("Remove")
        remove_button.clicked.connect(self._remove_folder)
        for button in (up_button, down_button, remove_button):
            buttons_row.addWidget(button)
        buttons_row.addStretch(1)
        folders_col.addLayout(buttons_row)
        row, line, _fc = _frow(
            "Folders per shot",
            "Created for every new shot; comp cannot be removed.",
            folders_control)
        _finish_frow(group_layout, row, line)
        _end_group(group_layout)
        layout.addWidget(group)

        group, group_layout = _setgroup("Naming")
        self.shot_pattern_edit = QtWidgets.QLineEdit()
        self.shot_pattern_edit.setFixedWidth(160)
        self.shot_pattern_edit.textChanged.connect(lambda _t: self._update_preview())
        row, line, _fc = _frow(
            "Shot name pattern", "### counts up per project; sequences stay part "
            "of the name.", self.shot_pattern_edit)
        _finish_frow(group_layout, row, line)
        self.script_pattern_edit = QtWidgets.QLineEdit()
        self.script_pattern_edit.textChanged.connect(lambda _t: self._update_preview())
        row, line, _fc = _frow(
            "Script name pattern", "{shot} and version tokens are filled "
            "automatically.", self.script_pattern_edit)
        _finish_frow(group_layout, row, line)
        self.preview = QtWidgets.QLabel("")
        self.preview.setObjectName("ShellPreview")
        self.preview.setTextFormat(QtCore.Qt.RichText)
        self.preview.setWordWrap(True)
        row, line, _fc = _frow(
            "Preview", "What the next new shot will look like on disk.",
            self.preview)
        _finish_frow(group_layout, row, line)
        _end_group(group_layout)
        layout.addWidget(group)
        self._preview_builder = naming
        layout.addStretch(1)
        return scroll

    def _update_preview(self):
        if self.preview is None:
            return
        pattern = self.shot_pattern_edit.text().strip() or "sh###"
        script = self.script_pattern_edit.text().strip() or "{shot}_comp_v###.nk"
        try:
            shot_name = self._preview_builder.expand_shot_name(pattern, 1)
            script_name = self._preview_builder.script_name(script, shot_name, 1)
        except Exception:
            shot_name, script_name = pattern, script
        folders = " ".join(self._folder_list)
        self.preview.setText(
            "creating <b style='color:#f0a043; font-family:Consolas,monospace;'>{shot}"
            "</b> <span style='color:#9a9ea6;'>→</span> shots/<b style='color:#f0a043;'>"
            "{shot}</b>/ {folders} &nbsp;+&nbsp; <b style='color:#f0a043;'>"
            "{script}</b>".format(shot=shot_name, folders=folders,
                                  script=script_name))

    def _rebuild_folder_items(self):
        while self._folder_items.count():
            item = self._folder_items.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._current_folder = None
        for index, name in enumerate(self._folder_list):
            frame = ClickableFrame()
            frame.setObjectName("ShellFItem")
            frame.setFixedWidth(320)
            frame.setCursor(QtCore.Qt.PointingHandCursor)
            row = QtWidgets.QHBoxLayout(frame)
            row.setContentsMargins(10, 5, 10, 5)
            row.setSpacing(9)
            grip = QtWidgets.QLabel("⋮⋮")
            grip.setObjectName("ShellDim")
            grip.setStyleSheet("letter-spacing: 2px; background: transparent;")
            row.addWidget(grip)
            name_label = QtWidgets.QLabel(name)
            name_label.setStyleSheet("background: transparent;")
            row.addWidget(name_label, 1)
            if name.lower() == "comp":
                badge = QtWidgets.QLabel("locked")
                badge.setObjectName("ShellBadge")
                row.addWidget(badge)
            else:
                remove = QtWidgets.QLabel("✕")
                remove.setObjectName("ShellDim")
                remove.setStyleSheet("background: transparent;")
                remove.setCursor(QtCore.Qt.PointingHandCursor)
                def _remove(event, i=index):
                    self._remove_folder_at(i)
                remove.mouseReleaseEvent = _remove
                row.addWidget(remove)
            frame.leftClicked.connect(lambda i=index: self._select_folder(i))
            self._folder_items.addWidget(frame)
        self._update_preview()

    def _select_folder(self, index):
        self._current_folder = index
        for i in range(self._folder_items.count()):
            widget = self._folder_items.itemAt(i).widget()
            if widget is not None:
                widget.setStyleSheet(
                    "border: 1px solid {};".format(
                        "#f0a043" if i == index else "#2a2c30"))

    # -- scanning ---------------------------------------------------------------
    def _build_scanning(self):
        scroll, layout = self._body()
        _heading_block(layout, "Scanning",
                       "Watched roots are the parent folders that hold your "
                       "projects; the scan cache keeps startup fast.")
        group, group_layout = _setgroup("Watched roots")
        self.roots_list = QtWidgets.QListWidget()
        self.roots_list.setMaximumHeight(140)
        group_layout.addSpacing(8)
        group_layout.addWidget(self.roots_list)
        roots_row = QtWidgets.QHBoxLayout()
        roots_row.setSpacing(8)
        add_root = QtWidgets.QPushButton("Add folder...")
        add_root.clicked.connect(self._add_root)
        remove_root = QtWidgets.QPushButton("Remove")
        remove_root.clicked.connect(self._remove_root)
        rescan = QtWidgets.QPushButton("Rescan now")
        rescan.clicked.connect(self._rescan)
        roots_row.addWidget(add_root)
        roots_row.addWidget(remove_root)
        roots_row.addSpacing(12)
        roots_row.addWidget(rescan)
        roots_row.addStretch(1)
        group_layout.addSpacing(10)
        group_layout.addLayout(roots_row)
        _end_group(group_layout)
        layout.addWidget(group)
        layout.addStretch(1)
        return scroll

    # -- startup ------------------------------------------------------------------
    def _build_startup(self):
        scroll, layout = self._body()
        _heading_block(layout, "Startup",
                       "What the launcher opens and which hints it computes on "
                       "startup.")

        group, group_layout = _setgroup("Behaviour")
        self.launch_toggle = Toggle()
        self.launch_toggle.toggled.connect(self._changed)
        row, line, fc = _frow(
            "Show Shell on launch",
            "Open the launcher window when the app starts (instead of the Board).")
        fc.addWidget(self.launch_toggle)
        fc.addStretch(1)
        _finish_frow(group_layout, row, line)
        self.resume_toggle = Toggle()
        self.resume_toggle.toggled.connect(self._changed)
        row, line, fc = _frow(
            "Resume card",
            "Offer \u201ccontinue where you left off\u201d as the primary action.")
        fc.addWidget(self.resume_toggle)
        fc.addStretch(1)
        _finish_frow(group_layout, row, line)
        self.stale_toggle = Toggle()
        self.stale_toggle.toggled.connect(self._changed)
        row, line, fc = _frow(
            "Stale-shot check",
            "Flag shots untouched for {}+ days on the Board.".format(
                self.state.prefs.get("stale_days", 14)))
        fc.addWidget(self.stale_toggle)
        fc.addStretch(1)
        _finish_frow(group_layout, row, line)
        _end_group(group_layout)
        layout.addWidget(group)

        group, group_layout = _setgroup("Launching")
        exe_control = QtWidgets.QWidget()
        exe_row = QtWidgets.QHBoxLayout(exe_control)
        exe_row.setContentsMargins(0, 0, 0, 0)
        exe_row.setSpacing(8)
        self.exe_edit = QtWidgets.QLineEdit()
        exe_row.addWidget(self.exe_edit, 1)
        browse = QtWidgets.QPushButton("Browse...")
        browse.clicked.connect(self._browse_exe)
        exe_row.addWidget(browse)
        detect = QtWidgets.QPushButton("Detect")
        detect.clicked.connect(self._detect_exe)
        exe_row.addWidget(detect)
        row, line, _fc = _frow(
            "Nuke executable", "Used by the standalone launcher; detection scans "
            "the usual install folders.", exe_control)
        _finish_frow(group_layout, row, line)
        _end_group(group_layout)
        layout.addWidget(group)
        layout.addStretch(1)
        return scroll

    # -- advanced -------------------------------------------------------------------
    def _build_advanced(self):
        from shellcore.schema import FORMAT_PROJECT, FORMAT_SHOT
        scroll, layout = self._body()
        _heading_block(layout, "Advanced",
                       "Schema versions and on-disk locations. Everything here is "
                       "informational.")
        group, group_layout = _setgroup("Schemas")
        row, line, _fc = _frow(
            "Metadata formats",
            "Written into shot.json / project.json and checked on load.",
            QtWidgets.QLabel("<b>{}</b> · <b>{}</b>".format(FORMAT_SHOT, FORMAT_PROJECT)))
        _finish_frow(group_layout, row, line)
        row, line, _fc = _frow(
            "Global preferences", "Per-user file; unknown keys are preserved.",
            QtWidgets.QLabel("<b style='font-family:Consolas,monospace; font-size:11px;'>"
                             "{}</b>".format(prefs_mod.PREFS_FILE)))
        _finish_frow(group_layout, row, line)
        logs_row = QtWidgets.QHBoxLayout()
        logs_row.setSpacing(8)
        open_logs = QtWidgets.QPushButton("Open crash-log folder")
        open_logs.clicked.connect(self._open_logs)
        logs_row.addWidget(open_logs)
        logs_row.addStretch(1)
        row, line, _fc = _frow(
            "Crash logs", "SleepyCore writes one log per crash; the 50 newest "
            "are kept.", logs_row)
        _finish_frow(group_layout, row, line)
        _end_group(group_layout)
        layout.addWidget(group)
        layout.addStretch(1)
        return scroll

    # ------------------------------------------------------------------
    def load(self):
        self._loading = True
        try:
            self._load_values()
        finally:
            self._loading = False

    def _load_values(self):
        prefs = self.state.prefs
        accent = prefs.get("accent", "#f0a043")
        for value, button in self._accent_buttons:
            button.setChecked(value == accent)
        self._accent_name.setText(theme.ACCENT_NAMES.get(accent, accent))
        for value, chip in self.mode_buttons.items():
            chip.setChecked(prefs.get("theme_mode", "dark") == value)
        for value, chip in self.density_buttons.items():
            chip.setChecked(prefs.get("density", "comfortable") == value)
        try:
            current_zoom = float(prefs.get("ui_scale", 1.0) or 1.0)
        except (TypeError, ValueError):
            current_zoom = 1.0
        for value, chip in self.zoom_buttons.items():
            chip.setChecked(abs(value - current_zoom) < 0.01)
        self.font_spin.setValue(int(prefs.get("font_size", 12) or 12))
        self.shot_pattern_edit.setText(prefs.get("shot_pattern", "sh###"))
        self.script_pattern_edit.setText(prefs.get("script_pattern", "{shot}_comp_v###.nk"))
        self._folder_list = list(prefs.get("folder_template", []))
        self._rebuild_folder_items()
        self.roots_list.clear()
        self.roots_list.addItems(prefs.get("watched_roots", []))
        self.exe_edit.setText(prefs.get("nuke_executable", ""))
        self.launch_toggle.setChecked(bool(prefs.get("show_on_launch", True)))
        self.resume_toggle.setChecked(bool(prefs.get("resume_card", True)))
        self.stale_toggle.setChecked(bool(prefs.get("stale_check", True)))

    def _set_accent(self, color):
        self.state.prefs["accent"] = color
        for value, button in self._accent_buttons:
            button.setChecked(value == color)
        self._accent_name.setText(theme.ACCENT_NAMES.get(color, color))
        self.save()

    def _set_mode(self, value):
        self.state.prefs["theme_mode"] = value
        for key, chip in self.mode_buttons.items():
            chip.setChecked(key == value)
        self._changed()

    def _set_zoom(self, value):
        self.state.prefs["ui_scale"] = value
        for key, chip in self.zoom_buttons.items():
            chip.setChecked(abs(key - value) < 0.01)
        self._changed()

    def _set_density(self, value):
        self.state.prefs["density"] = value
        for key, chip in self.density_buttons.items():
            chip.setChecked(key == value)
        self._changed()

    def _changed(self, _index=None):
        if self._loading:
            return
        # appearance changes apply immediately for feedback; persisted on save
        prefs = dict(self.state.prefs)
        prefs["theme_mode"] = self._mode_value()
        prefs["density"] = self._density_value()
        prefs["font_size"] = self.font_spin.value()
        prefs["show_on_launch"] = self.launch_toggle.isChecked()
        prefs["resume_card"] = self.resume_toggle.isChecked()
        prefs["stale_check"] = self.stale_toggle.isChecked()
        self.state.prefs.update(prefs)
        theme.apply(QtWidgets.QApplication.instance(), self.state.prefs)
        self.state.save_prefs()

    def _mode_value(self):
        for value, chip in self.mode_buttons.items():
            if chip.isChecked():
                return value
        return "dark"

    def _density_value(self):
        for value, chip in self.density_buttons.items():
            if chip.isChecked():
                return value
        return "comfortable"

    def _add_folder(self):
        dialog = QtWidgets.QInputDialog(self)
        dialog.setWindowTitle("Sleepy Shell")
        dialog.setLabelText("Folder name to create in every new shot:")
        if dialog.exec():
            name = dialog.textValue().strip()
            if name and name.lower() not in [f.lower() for f in self._folder_list]:
                self._folder_list.append(name)
                self._rebuild_folder_items()

    def _move_folder(self, delta):
        current = getattr(self, "_current_folder", None)
        if current is None:
            return
        target = current + delta
        if 0 <= target < len(self._folder_list):
            self._folder_list[current], self._folder_list[target] = \
                self._folder_list[target], self._folder_list[current]
            self._rebuild_folder_items()
            self._select_folder(target)

    def _remove_folder(self):
        current = getattr(self, "_current_folder", None)
        if current is None:
            return
        self._remove_folder_at(current)

    def _remove_folder_at(self, index):
        if not (0 <= index < len(self._folder_list)):
            return
        name = self._folder_list[index]
        if name.lower() == "comp":
            QtWidgets.QMessageBox.information(
                self, "Sleepy Shell", "comp cannot be removed: shots need "
                "somewhere to save scripts.")
            return
        del self._folder_list[index]
        self._rebuild_folder_items()

    def _add_root(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Add watched root (parent folder that holds projects)")
        if path:
            self.roots_list.addItem(os.path.normpath(path))

    def _remove_root(self):
        row = self.roots_list.currentRow()
        if row >= 0:
            self.roots_list.takeItem(row)

    def _rescan(self):
        self.save(silent=True)
        scan_mod.invalidate_cache()
        self.state.refresh(force=True)

    def _browse_exe(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select the Nuke executable")
        if path:
            self.exe_edit.setText(path)

    def _detect_exe(self):
        from shellcore import launch
        found = launch.find_nuke_executables()
        if not found:
            QtWidgets.QMessageBox.information(
                self, "Sleepy Shell", "No Nuke executables found automatically.")
            return
        choice, _ = QtWidgets.QInputDialog.getItem(
            self, "Sleepy Shell", "Found Nuke installations:", found, 0, False)
        if choice:
            self.exe_edit.setText(choice)

    def _open_logs(self):
        from shellcore.launch import open_in_explorer
        try:
            from SleepyCore import crashlog
            folder = crashlog.LOG_DIR
        except Exception:
            folder = None
        if not folder or not os.path.isdir(folder):
            QtWidgets.QMessageBox.information(
                self, "Sleepy Shell",
                "No crash-log folder yet ({}).".format(folder or "unknown"))
            return
        open_in_explorer(folder)

    def save(self, silent=False):
        prefs = self.state.prefs
        prefs["shot_pattern"] = self.shot_pattern_edit.text().strip() or "sh###"
        prefs["script_pattern"] = self.script_pattern_edit.text().strip() or "{shot}_comp_v###.nk"
        prefs["folder_template"] = list(self._folder_list)
        if "comp" not in [f.lower() for f in prefs["folder_template"]]:
            prefs["folder_template"] = ["comp"] + prefs["folder_template"]
        prefs["watched_roots"] = [self.roots_list.item(i).text()
                                  for i in range(self.roots_list.count())]
        prefs["nuke_executable"] = self.exe_edit.text().strip()
        prefs["theme_mode"] = self._mode_value()
        prefs["density"] = self._density_value()
        prefs["font_size"] = self.font_spin.value()
        prefs["show_on_launch"] = self.launch_toggle.isChecked()
        prefs["resume_card"] = self.resume_toggle.isChecked()
        prefs["stale_check"] = self.stale_toggle.isChecked()
        self.state.save_prefs()
        theme.apply(QtWidgets.QApplication.instance(), prefs)
        if not silent:
            self.prefs_hint = "saved"


# ---------------------------------------------------------------------------
# Project Settings (per project)
# ---------------------------------------------------------------------------

class ProjectSettingsPage(QtWidgets.QWidget):
    """Editor for one project's project.json plus danger-zone actions."""

    projectChanged = QtCore.Signal()
    backToBoard = QtCore.Signal()

    def __init__(self, state, parent=None):
        super(ProjectSettingsPage, self).__init__(parent)
        self.state = state
        self.project = None
        self.config = {}
        styled(self)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        content = styled(QtWidgets.QWidget())
        self.layout_root = QtWidgets.QVBoxLayout(content)
        self.layout_root.setContentsMargins(20, 16, 20, 16)
        self.layout_root.setSpacing(12)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def status_hint(self):
        if self.project is None:
            return "No project selected"
        return ("Project settings: <b>project.json</b> (sleepy-project/1) — "
                "travels with the project folder · per-project overrides, "
                "global prefs fill anything left empty")

    def set_project(self, project):
        self.project = project
        self.rebuild()

    def rebuild(self):
        while self.layout_root.count():
            item = self.layout_root.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        if self.project is None:
            note = QtWidgets.QLabel("No project selected.")
            note.setObjectName("ShellDim")
            self.layout_root.addWidget(note)
            return
        self.config, error = load_project(self.project["path"])
        if error:
            QtWidgets.QMessageBox.warning(
                self, "Sleepy Shell",
                "project.json could not be read:\n{}\n\nShowing defaults; "
                "saving will overwrite the broken file.".format(error))

        crumb = QtWidgets.QLabel(
            "<b style=\"color:#e6e6e6;\">{}</b> <span style=\"color:#9a9ea6;\">›"
            "</span> <span style=\"color:#9a9ea6;\">project settings</span>".format(
                self.project["name"]))
        crumb.setTextFormat(QtCore.Qt.RichText)
        crumb.setStyleSheet("font-size: 11.5px;")
        self.layout_root.addWidget(crumb)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(14)
        title = QtWidgets.QLabel(self.project["name"])
        title.setObjectName("ShellH2")
        header.addWidget(title)
        if self.project["managed"]:
            header.addWidget(Chip("managed", theme.STATUS_COLORS["approved"]))
            shots_here = [s for s in self.state.shots
                          if s.get("project_path") == self.project["path"]]
            sequences = len({os.path.basename(os.path.dirname(s["path"]))
                             for s in shots_here})
            header.addWidget(NeutralChip(
                "{} shots · {} sequences".format(len(shots_here), sequences)))
        else:
            header.addWidget(Chip("discovered", theme.status_color("delivered"), dim=True))
        header.addStretch(1)
        back = QtWidgets.QPushButton("Back to Board")
        back.clicked.connect(self.backToBoard.emit)
        header.addWidget(back)
        self.layout_root.addLayout(header)

        warn = QtWidgets.QFrame()
        warn.setObjectName("ShellNoteWarn")
        warn_layout = QtWidgets.QHBoxLayout(warn)
        warn_layout.setContentsMargins(12, 9, 12, 9)
        warn_label = QtWidgets.QLabel(
            "<b style='color:#d96b5b;'>Defaults apply to new shots only.</b> "
            "Existing shots and comps are never rewritten — a shot keeps the "
            "settings it was created with unless you change it on the shot itself.")
        warn_label.setWordWrap(True)
        warn_label.setTextFormat(QtCore.Qt.RichText)
        warn_label.setStyleSheet("font-size: 11.5px;")
        warn_layout.addWidget(warn_label)
        self.layout_root.addWidget(warn)

        # identity
        group, group_layout = _setgroup("Identity")
        self.client_edit = QtWidgets.QLineEdit(self.config.get("client", ""))
        row, line, fc = _frow("Client", "Shown on the Board, slates and contact "
                              "sheets.")
        fc.addWidget(self.client_edit)
        _finish_frow(group_layout, row, line)
        color_control = QtWidgets.QWidget()
        color_row = QtWidgets.QHBoxLayout(color_control)
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(8)
        self._color_buttons = []
        for accent in theme.ACCENTS:
            button = _swatch(accent, checked=self.config.get("color") == accent)
            button.clicked.connect(lambda _=False, c=accent: self._set_color(c))
            color_row.addWidget(button)
            self._color_buttons.append((accent, button))
        color_row.addStretch(1)
        row, line, _fc = _frow(
            "Project color", "Dot color on cards and lists, so projects are "
            "told apart at a glance.", color_control)
        _finish_frow(group_layout, row, line)
        self.tags_edit = QtWidgets.QLineEdit(", ".join(self.config.get("tags", [])))
        row, line, fc = _frow("Tags", "Free-form, used by global search.")
        fc.addWidget(self.tags_edit)
        _finish_frow(group_layout, row, line)
        _end_group(group_layout)
        self.layout_root.addWidget(group)

        # technical defaults
        group, group_layout = _setgroup("Technical defaults — new shots")
        fps_control = QtWidgets.QWidget()
        fps_row = QtWidgets.QHBoxLayout(fps_control)
        fps_row.setContentsMargins(0, 0, 0, 0)
        fps_row.setSpacing(8)
        self.fps_spin = QtWidgets.QDoubleSpinBox()
        self.fps_spin.setRange(1.0, 240.0)
        self.fps_spin.setSuffix(" fps")
        self.fps_spin.setValue(float(self.config.get("fps", 25) or 25))
        fps_row.addWidget(self.fps_spin)
        self.resolution_edit = QtWidgets.QLineEdit(self.config.get("resolution", ""))
        self.resolution_edit.setPlaceholderText("3840x2160")
        fps_row.addWidget(self.resolution_edit)
        row, line, fc = _frow("Frame rate & format", "")
        fc.addWidget(fps_control)
        _finish_frow(group_layout, row, line)
        self.space_edit = QtWidgets.QLineEdit(self.config.get("working_space", ""))
        self.space_edit.setPlaceholderText("ACEScg, linear...")
        row, line, fc = _frow("Working color space", "")
        fc.addWidget(self.space_edit)
        _finish_frow(group_layout, row, line)
        range_control = QtWidgets.QWidget()
        range_row = QtWidgets.QHBoxLayout(range_control)
        range_row.setContentsMargins(0, 0, 0, 0)
        range_row.setSpacing(8)
        self.range_edit = QtWidgets.QLineEdit(self.config.get("range", ""))
        self.range_edit.setPlaceholderText("1001-####")
        range_row.addWidget(self.range_edit)
        self.handles_spin = QtWidgets.QSpinBox()
        self.handles_spin.setRange(0, 240)
        self.handles_spin.setPrefix("handles: ")
        self.handles_spin.setValue(int(self.config.get("handles", 8) or 0))
        range_row.addWidget(self.handles_spin)
        row, line, fc = _frow("Range & handles", "")
        fc.addWidget(range_control)
        _finish_frow(group_layout, row, line)
        self.shot_pattern_edit = QtWidgets.QLineEdit(self.config.get("shot_pattern", ""))
        self.shot_pattern_edit.setPlaceholderText("global default (sh###)")
        row, line, fc = _frow("Shot name pattern",
                              "Empty = the global pattern from Preferences.")
        fc.addWidget(self.shot_pattern_edit)
        _finish_frow(group_layout, row, line)
        self.script_pattern_edit = QtWidgets.QLineEdit(
            self.config.get("script_pattern", ""))
        self.script_pattern_edit.setPlaceholderText("global default ({shot}_comp_v###.nk)")
        row, line, fc = _frow("Script name pattern", "")
        fc.addWidget(self.script_pattern_edit)
        _finish_frow(group_layout, row, line)
        _end_group(group_layout)
        self.layout_root.addWidget(group)

        # folders & templates
        group, group_layout = _setgroup("Folders & templates — this project")
        structure_control = QtWidgets.QWidget()
        structure_row = QtWidgets.QHBoxLayout(structure_control)
        structure_row.setContentsMargins(0, 0, 0, 0)
        structure_row.setSpacing(8)
        current = self.config.get("folder_template", "standard")
        self.structure_buttons = {}
        for label, value in (("Standard (suite)", "standard"),
                             ("Client structure", "client")):
            chip = _sel2(label, checked=current == value)
            chip.clicked.connect(lambda _=False, v=value: self._set_structure(v))
            structure_row.addWidget(chip)
            self.structure_buttons[value] = chip
        structure_row.addStretch(1)
        row, line, _fc = _frow(
            "Folder structure",
            "\u201cClient structure\u201d keeps their layout as-is: the project "
            "stays in discovered (read-only) mode and nothing is ever written.",
            structure_control)
        _finish_frow(group_layout, row, line)
        template_control = QtWidgets.QWidget()
        template_row = QtWidgets.QHBoxLayout(template_control)
        template_row.setContentsMargins(0, 0, 0, 0)
        template_row.setSpacing(8)
        self.template_edit = QtWidgets.QLineEdit(self.config.get("comp_template", ""))
        template_row.addWidget(self.template_edit, 1)
        browse = QtWidgets.QPushButton("Browse...")
        browse.clicked.connect(self._browse_template)
        template_row.addWidget(browse)
        row, line, fc = _frow("Comp template", "Copied as v001 when a new shot starts.")
        fc.addWidget(template_control)
        _finish_frow(group_layout, row, line)
        if "slate_preset" in self.config or self.config.get("slate_preset"):
            self.slate_edit = QtWidgets.QLineEdit(self.config.get("slate_preset", ""))
            row, line, fc = _frow("Slate preset", "Used by the delivery contact sheet.")
            fc.addWidget(self.slate_edit)
            _finish_frow(group_layout, row, line)
        else:
            self.slate_edit = None
        _end_group(group_layout)
        self.layout_root.addWidget(group)

        # rendering & delivery
        group, group_layout = _setgroup("Rendering & delivery")
        self.render_edit = QtWidgets.QLineEdit(self.config.get("render_output", ""))
        self.render_edit.setPlaceholderText(
            r"D:\Projects\<name>\renders\{shot}\ (SleepyQueue)")
        row, line, fc = _frow("Default render output",
                              "Pre-filled when sending Writes to SleepyQueue.")
        fc.addWidget(self.render_edit)
        _finish_frow(group_layout, row, line)
        self.naming_edit = QtWidgets.QLineEdit(self.config.get("deliverable_naming", ""))
        row, line, fc = _frow("Deliverable naming", "")
        fc.addWidget(self.naming_edit)
        _finish_frow(group_layout, row, line)
        _end_group(group_layout)
        self.layout_root.addWidget(group)

        # danger zone
        group, group_layout = _setgroup("Danger zone")
        maintenance = QtWidgets.QWidget()
        maint_row = QtWidgets.QHBoxLayout(maintenance)
        maint_row.setContentsMargins(0, 0, 0, 0)
        maint_row.setSpacing(8)
        rescan = QtWidgets.QPushButton("Re-scan now")
        rescan.clicked.connect(self._rescan)
        maint_row.addWidget(rescan)
        clear_cache = QtWidgets.QPushButton("Clear local cache")
        clear_cache.clicked.connect(self._clear_cache)
        maint_row.addWidget(clear_cache)
        forget = QtWidgets.QPushButton("Unmanage project…")
        forget.setProperty("danger", True)
        forget.clicked.connect(self._forget)
        maint_row.addWidget(forget)
        maint_row.addStretch(1)
        row, line, fc = _frow(
            "Maintenance",
            "Unmanage only removes the project.json — every comp, render and "
            "snapshot stays on disk.", maintenance)
        _finish_frow(group_layout, row, line)
        _end_group(group_layout)
        self.layout_root.addWidget(group)

        save_row = QtWidgets.QHBoxLayout()
        self.hint = QtWidgets.QLabel("")
        self.hint.setObjectName("ShellDim")
        save_row.addWidget(self.hint)
        save_row.addStretch(1)
        save = QtWidgets.QPushButton("Save project settings")
        save.setProperty("accent", True)
        save.clicked.connect(self._save)
        save_row.addWidget(save)
        self.layout_root.addLayout(save_row)
        self.layout_root.addStretch(1)

    def _set_color(self, color):
        self.config["color"] = color
        for value, button in self._color_buttons:
            button.setChecked(value == color)

    def _set_structure(self, value):
        self.config["folder_template"] = value
        for key, chip in self.structure_buttons.items():
            chip.setChecked(key == value)

    def _browse_template(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select a comp template (.nk)", "", "Nuke scripts (*.nk)")
        if path:
            self.template_edit.setText(path)

    def _rescan(self):
        scan_mod.invalidate_cache()
        self.state.refresh(force=True)
        self.hint.setText("rescanned")

    def _clear_cache(self):
        scan_mod.invalidate_cache()
        try:
            if os.path.isfile(scan_mod.CACHE_FILE):
                os.remove(scan_mod.CACHE_FILE)
        except OSError:
            pass
        self.state.refresh(force=True)
        self.hint.setText("cache cleared")

    def _forget(self):
        if self.project is None:
            return
        answer = QtWidgets.QMessageBox.question(
            self, "Sleepy Shell",
            "Remove project.json for {}?\n\nNo comps, renders or other files are "
            "touched - the project becomes a discovered folder again.".format(
                self.project["name"]),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel)
        if answer != QtWidgets.QMessageBox.Yes:
            return
        path = os.path.join(self.project["path"], "project.json")
        try:
            os.remove(path)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Sleepy Shell",
                                          "Could not remove project.json:\n{}".format(exc))
            return
        self.state.refresh(force=True)
        self.projectChanged.emit()
        self.backToBoard.emit()

    def _save(self):
        if self.project is None:
            return
        values = {
            "client": self.client_edit.text().strip(),
            "color": self.config.get("color"),
            "tags": [t.strip() for t in self.tags_edit.text().split(",") if t.strip()],
            "fps": self.fps_spin.value(),
            "resolution": self.resolution_edit.text().strip(),
            "working_space": self.space_edit.text().strip(),
            "range": self.range_edit.text().strip(),
            "handles": self.handles_spin.value(),
            "shot_pattern": self.shot_pattern_edit.text().strip(),
            "script_pattern": self.script_pattern_edit.text().strip(),
            "folder_template": self.config.get("folder_template", "standard"),
            "render_output": self.render_edit.text().strip(),
            "deliverable_naming": self.naming_edit.text().strip(),
            "comp_template": self.template_edit.text().strip(),
        }
        if self.slate_edit is not None:
            values["slate_preset"] = self.slate_edit.text().strip()
        try:
            self.config = save_project(self.project["path"], values)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Sleepy Shell",
                                          "Could not write project.json:\n{}".format(exc))
            return
        self.hint.setText("saved")
        self.state.refresh(force=True)
        self.projectChanged.emit()

