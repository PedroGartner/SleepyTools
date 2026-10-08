"""The Board: every shot across every project, in three view modes.

Views share one filter set (project, text, due window, delivered
visibility) and one data source (AppState). Status changes go through
the context menu; double-click opens the shot. Layout mirrors the
mockup: horizontal mini-cards in columns, grouped list rows with
fixed-width cells, and a gallery with status pills and overlaid chips.
"""

from datetime import date

from SleepyCore.qt import QtCore, QtWidgets

from shellcore import schema
from shellui import theme
from shellui.widgets import (Chip, EmptyState, Thumb, clear_layout, dim_effect,
                             set_section_font, styled)


class BoardPage(QtWidgets.QWidget):
    openShot = QtCore.Signal(object)      # ShotItem
    shotChanged = QtCore.Signal()

    def __init__(self, state, backend, parent=None):
        super(BoardPage, self).__init__(parent)
        self.state = state
        self.backend = backend
        self._shots = []
        self._gallery_active = set(schema.STATUS_ORDER)
        styled(self)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(14)

        root.addLayout(self._build_toolbar())

        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self._build_columns_view())
        self.stack.addWidget(self._build_list_view())
        self.stack.addWidget(self._build_gallery_view())
        root.addWidget(self.stack, 1)

        self._apply_view_mode()

    def resizeEvent(self, event):
        # the gallery reflows by width (mockup: auto-fill minmax(240px, 1fr))
        if hasattr(self, "stack") and self.stack.currentIndex() == 2 \
                and getattr(self, "_shots", None):
            self._fill_gallery()
        super(BoardPage, self).resizeEvent(event)

    # ------------------------------------------------------------------
    # toolbar
    # ------------------------------------------------------------------
    def _build_toolbar(self):
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(10)

        self.project_combo = QtWidgets.QComboBox()
        self.project_combo.setMinimumWidth(190)
        self.project_combo.currentIndexChanged.connect(self._project_changed)
        bar.addWidget(self.project_combo)

        gear = QtWidgets.QToolButton()
        gear.setToolTip("Project settings for the selected project")
        gear.setCursor(QtCore.Qt.PointingHandCursor)
        from shellui import icons
        gear.setIcon(icons.icon("gear"))
        gear.setStyleSheet(
            "QToolButton { background: transparent; border: none; padding: 4px; }"
            "QToolButton:hover { border-radius: 3px; background: #26272a; }")
        gear.clicked.connect(self._open_project_settings)
        bar.addWidget(gear)

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Search shots, notes, tags...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMaximumWidth(260)
        self.search_edit.textChanged.connect(self.refresh_views)
        from SleepyCore.qt import QAction
        search_action = QAction(theme_icon("search"), "", self.search_edit)
        self.search_edit.addAction(search_action, QtWidgets.QLineEdit.LeadingPosition)
        bar.addWidget(self.search_edit)

        # the mockup's board toolbar shows the due filter engaged by default
        self.due_toggle = self._pill("Due in {} days".format(
            self.state.prefs.get("due_days", 7)), checked=True)
        self.due_toggle.toggled.connect(self.refresh_views)
        bar.addWidget(self.due_toggle)
        self.discovered_toggle = self._pill("Include discovered", checked=True)
        self.discovered_toggle.toggled.connect(self.refresh_views)
        bar.addWidget(self.discovered_toggle)
        self.delivered_toggle = self._pill(
            "Delivered/Hold",
            checked=bool(self.state.prefs.get("show_delivered", True)))
        self.delivered_toggle.toggled.connect(self.refresh_views)
        bar.addWidget(self.delivered_toggle)

        bar.addStretch(1)

        # the mockup's segmented view switcher
        seg_group = QtWidgets.QFrame()
        seg_group.setObjectName("ShellSegGroup")
        seg_layout = QtWidgets.QHBoxLayout(seg_group)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(0)
        self.view_buttons = {}
        for view_id, label in (("columns", "Columns"), ("list", "List"),
                               ("gallery", "Gallery")):
            button = QtWidgets.QPushButton(label)
            button.setCheckable(True)
            button.setCursor(QtCore.Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, v=view_id: self.set_view_mode(v))
            self.view_buttons[view_id] = button
            seg_layout.addWidget(button)
        bar.addWidget(seg_group)
        return bar

    def _open_project_settings(self):
        project = None
        path = self.project_combo.currentData()
        for candidate in self.state.projects:
            if candidate["path"] == path:
                project = candidate
                break
        project = project or (self.state.projects[0] if self.state.projects else None)
        if project is None:
            QtWidgets.QMessageBox.information(
                self, "Sleepy Shell", "No projects scanned yet.")
            return
        main = self.window()
        if hasattr(main, "open_project_settings"):
            main.open_project_settings(project)

    @staticmethod
    def _pill(text, checked=False):
        pill = QtWidgets.QToolButton()
        pill.setObjectName("ShellPill")
        pill.setText(text)
        pill.setCheckable(True)
        pill.setChecked(checked)
        pill.setCursor(QtCore.Qt.PointingHandCursor)
        return pill

    # ------------------------------------------------------------------
    # views
    # ------------------------------------------------------------------
    def _build_columns_view(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        container = styled(QtWidgets.QWidget())
        self.columns_layout = QtWidgets.QHBoxLayout(container)
        self.columns_layout.setContentsMargins(0, 0, 6, 0)
        self.columns_layout.setSpacing(12)
        scroll.setWidget(container)
        return scroll

    def _build_list_view(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        container = styled(QtWidgets.QWidget())
        self.list_layout = QtWidgets.QVBoxLayout(container)
        self.list_layout.setContentsMargins(0, 2, 6, 0)
        self.list_layout.setSpacing(2)
        scroll.setWidget(container)
        return scroll

    def _build_gallery_view(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        container = styled(QtWidgets.QWidget())
        outer = QtWidgets.QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 6, 0)
        outer.setSpacing(12)
        # persistent sub-widgets: clear_layout() never deletes these, it
        # only clears their inner layouts (otherwise the grid would be
        # re-parented to a deleted holder and the cards would vanish)
        pills_holder = QtWidgets.QWidget()
        self.gallery_pills_row = QtWidgets.QHBoxLayout(pills_holder)
        self.gallery_pills_row.setContentsMargins(0, 0, 0, 0)
        self.gallery_pills_row.setSpacing(8)
        outer.addWidget(pills_holder)
        grid_holder = QtWidgets.QWidget()
        self.gallery_layout = QtWidgets.QGridLayout(grid_holder)
        self.gallery_layout.setContentsMargins(0, 0, 0, 0)
        self.gallery_layout.setSpacing(14)
        outer.addWidget(grid_holder)
        outer.addStretch(1)
        scroll.setWidget(container)
        return scroll

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------
    def status_hint(self):
        shown = len(self._shots)
        total = len(self.state.shots)
        if not total:
            return "No shots indexed yet"
        hint = "Showing <b>{} of {}</b> shots".format(shown, total)
        if self.due_toggle.isChecked():
            hint += " · due filter on (shots without a due date are hidden)"
        hint += " · right-click = set status · double-click = open latest"
        return hint

    def set_search(self, text):
        """Prefill the board search (used by the home search row)."""
        if text != self.search_edit.text():
            self.search_edit.setText(text)

    def set_view_mode(self, view_id):
        if view_id not in ("columns", "list", "gallery"):
            return
        self.state.prefs["view_mode"] = view_id
        self._apply_view_mode()
        self.state.save_prefs()

    def _apply_view_mode(self):
        view_id = self.state.prefs.get("view_mode", "list")
        index = {"columns": 0, "list": 1, "gallery": 2}[view_id]
        self.stack.setCurrentIndex(index)
        for vid, button in self.view_buttons.items():
            button.setChecked(vid == view_id)

    def _project_changed(self, _index):
        path = self.project_combo.currentData()
        self.state.current_project = path
        self.refresh_views()

    def reload_projects(self):
        combo = self.project_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("All projects", None)
        for project in self.state.projects:
            label = project["name"] + ("" if project["managed"] else "  (discovered)")
            combo.addItem(label, project["path"])
        # keep current selection if still valid
        if self.state.current_project:
            index = combo.findData(self.state.current_project)
            if index >= 0:
                combo.setCurrentIndex(index)
            else:
                self.state.current_project = None
        combo.blockSignals(False)
        self.refresh_views()

    # ------------------------------------------------------------------
    # data
    # ------------------------------------------------------------------
    def refresh_views(self):
        due_days = self.state.prefs.get("due_days", 7) if self.due_toggle.isChecked() else None
        self._shots = self.state.visible_shots(
            text=self.search_edit.text(),
            due_days=due_days,
            include_discovered=self.discovered_toggle.isChecked(),
            include_delivered=self.delivered_toggle.isChecked(),
        )
        groups = self.state.grouped_by_status(self._shots)
        self._fill_list(groups)
        self._fill_columns(groups)
        self._fill_gallery()
        main = self.window()
        if hasattr(main, "_hint_label") and self.isVisible():
            main._hint_label.setText(self.status_hint())

    # ------------------------------------------------------------------
    # list view
    # ------------------------------------------------------------------
    def _fill_list(self, groups):
        clear_layout(self.list_layout)
        any_visible = False
        for status in schema.STATUS_ORDER:
            shots = groups.get(status) or []
            if status in ("delivered", "hold"):
                shots = sorted(shots, key=lambda s: s["name"].lower())
            elif status == schema.STATUS_WIP:
                shots = sorted(shots, key=lambda s: (s.get("config") or {}).get("due") or "9999")
            else:
                shots = sorted(shots, key=lambda s: s["name"].lower())
            if not shots:
                continue
            any_visible = True
            self.list_layout.addWidget(self._group_header(status, len(shots)))
            group_box = QtWidgets.QFrame()
            group_box.setObjectName("ShellGroup")
            rows = QtWidgets.QVBoxLayout(group_box)
            rows.setContentsMargins(4, 4, 4, 4)
            rows.setSpacing(1)
            dim = status in ("delivered", "hold")
            for shot in shots:
                rows.addWidget(self._list_row(shot, dim))
            self.list_layout.addWidget(group_box)
        self.list_layout.addStretch(1)
        if not any_visible:
            self.list_layout.addWidget(EmptyState(
                "No shots match the current filters.\n\nAdd a watched root in "
                "Preferences, create a project, or relax the filters."))

    def _group_header(self, status, count):
        """The mockup's .lhead: dot, colored uppercase title, count, sub note."""
        header = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(header)
        layout.setContentsMargins(2, 10, 2, 6)
        layout.setSpacing(8)
        dot = QtWidgets.QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet("background: {}; border-radius: 4px;".format(
            theme.status_color(status)))
        layout.addWidget(dot)
        label = QtWidgets.QLabel(schema.STATUS_LABELS[status].upper())
        set_section_font(label, size=10.5, spacing=1.2)
        label.setStyleSheet("color: {};".format(theme.status_color(status)))
        layout.addWidget(label)
        count_label = QtWidgets.QLabel(str(count))
        count_label.setObjectName("ShellDim")
        layout.addWidget(count_label)
        if status == schema.STATUS_WIP:
            note = QtWidgets.QLabel("sorted by due date")
            note.setObjectName("ShellDim")
            note.setStyleSheet("font-size: 10.5px; text-transform: none;")
            layout.addSpacing(2)
            layout.addWidget(note)
        if status == "delivered":
            note = QtWidgets.QLabel("kept until you hide them")
            note.setObjectName("ShellDim")
            note.setStyleSheet("font-size: 10.5px;")
            layout.addSpacing(2)
            layout.addWidget(note)
        layout.addStretch(1)
        return header

    def _list_row(self, shot, dim):
        """The mockup's .lrow: 96x54 thumb, name block, fixed cells."""
        row = QtWidgets.QFrame()
        row.setObjectName("ShellRow")
        row.setCursor(QtCore.Qt.PointingHandCursor)
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(12)
        layout.addWidget(Thumb(shot["name"], self._thumb_path(shot), Thumb.SIZE_SMALL,
                               radius=3, font_px=13))

        main = QtWidgets.QVBoxLayout()
        main.setSpacing(2)
        name = QtWidgets.QLabel(shot["name"] + "_comp")
        name.setStyleSheet("font-weight: 600; font-size: 12.5px;")
        main.addWidget(name)
        project_label = QtWidgets.QLabel(shot.get("project_name", ""))
        project_label.setObjectName("ShellDim")
        project_label.setStyleSheet("font-size: 11px;")
        main.addWidget(project_label)
        layout.addLayout(main, 1)

        version = QtWidgets.QLabel("v{:03d}".format(_latest_number(shot)))
        version.setFixedWidth(64)
        version.setStyleSheet("color: {}; font-size: 11.5px;".format(
            theme.DARK["text"]))
        layout.addWidget(version)

        due = (shot.get("config") or {}).get("due")
        due_holder = QtWidgets.QLabel()
        due_holder.setFixedWidth(150)
        due_holder.setStyleSheet("background: transparent;")
        if due:
            try:
                when = date.fromisoformat(due)
                days = (when - date.today()).days
                if days < 0:
                    chip = Chip("due {}d overdue".format(-days), theme.status_color("hold"))
                elif days == 0:
                    chip = Chip("due today", theme.status_color("wip"))
                elif days == 1:
                    chip = Chip("due tomorrow", theme.status_color("wip"))
                elif days <= 7:
                    chip = Chip("due in {}d".format(days), theme.status_color("wip"))
                else:
                    chip = Chip("due " + due, theme.status_color("review"))
            except ValueError:
                chip = Chip(due, theme.status_color("review"))
            due_layout = QtWidgets.QHBoxLayout(due_holder)
            due_layout.setContentsMargins(0, 0, 0, 0)
            due_layout.addWidget(chip)
            due_layout.addStretch(1)
        else:
            dash = QtWidgets.QLabel("—")
            dash.setObjectName("ShellDim")
            dash.setStyleSheet("background: transparent;")
            due_layout = QtWidgets.QHBoxLayout(due_holder)
            due_layout.setContentsMargins(0, 0, 0, 0)
            due_layout.addWidget(dash)
        layout.addWidget(due_holder)

        activity = QtWidgets.QLabel(_activity_text(shot))
        activity.setFixedWidth(150)
        activity.setObjectName("ShellDim")
        activity.setStyleSheet("font-size: 11.5px;")
        layout.addWidget(activity)

        wide = QtWidgets.QLabel(_wide_text(self.state, shot))
        wide.setFixedWidth(250)
        wide.setObjectName("ShellDim")
        wide.setStyleSheet("font-size: 11.5px;")
        layout.addWidget(wide)

        if not shot.get("managed"):
            layout.addWidget(Chip("discovered", theme.status_color("delivered"), dim=True))
        if dim:
            dim_effect(row, 0.55)
        row._shell_shot = shot
        row._shell_dim = dim
        row.installEventFilter(self)
        return row

    # ------------------------------------------------------------------
    # columns view
    # ------------------------------------------------------------------
    def _fill_columns(self, groups):
        clear_layout(self.columns_layout)
        any_visible = False
        for status in schema.STATUS_ORDER:
            shots = groups.get(status) or []
            column = QtWidgets.QFrame()
            column.setObjectName("ShellGroup")
            column.setMinimumWidth(215)
            column.setMinimumHeight(420)
            column_layout = QtWidgets.QVBoxLayout(column)
            column_layout.setContentsMargins(10, 10, 10, 10)
            column_layout.setSpacing(9)
            header = QtWidgets.QHBoxLayout()
            title = QtWidgets.QLabel(schema.STATUS_LABELS[status].upper())
            set_section_font(title, size=10.5, spacing=1.1)
            title.setStyleSheet("color: {};".format(theme.status_color(status)))
            header.addWidget(title)
            header.addStretch(1)
            count = QtWidgets.QLabel(str(len(shots)))
            count.setStyleSheet("color: {}; font-weight: 600;".format(
                theme.DARK["dim"]))
            header.addWidget(count)
            column_layout.addLayout(header)
            dim = status in ("delivered", "hold")
            for shot in shots:
                column_layout.addWidget(self._column_card(shot, dim))
            column_layout.addStretch(1)
            self.columns_layout.addWidget(column)
            if shots:
                any_visible = True
        self.columns_layout.addStretch(1)
        if not any_visible:
            holder = QtWidgets.QWidget()
            holder_layout = QtWidgets.QVBoxLayout(holder)
            holder_layout.addWidget(EmptyState(
                "No shots match the current filters."))
            self.columns_layout.addWidget(holder)

    def _column_card(self, shot, dim):
        """The mockup's .bcard: thumb left, info right, sub line below."""
        from shellui.widgets import ClickableFrame
        card = ClickableFrame()
        card.setObjectName("ShellCard")
        card.setCursor(QtCore.Qt.PointingHandCursor)
        outer = QtWidgets.QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(0)
        top.addWidget(Thumb(shot["name"], self._thumb_path(shot), Thumb.SIZE_CARD,
                            radius=0, font_px=12))
        info = QtWidgets.QVBoxLayout()
        info.setContentsMargins(9, 7, 9, 7)
        info.setSpacing(5)
        name_row = QtWidgets.QHBoxLayout()
        name = QtWidgets.QLabel(shot["name"] + "_comp")
        name.setStyleSheet("font-weight: 600; font-size: 12.5px; background: transparent;")
        name_row.addWidget(name)
        name_row.addStretch(1)
        version = QtWidgets.QLabel("v{:03d}".format(_latest_number(shot)))
        version.setObjectName("ShellDim")
        version.setStyleSheet("font-weight: 400; font-size: 11px; background: transparent;")
        name_row.addWidget(version)
        info.addLayout(name_row)
        meta = QtWidgets.QHBoxLayout()
        meta.setSpacing(6)
        meta.addWidget(Chip(schema.STATUS_LABELS[shot.status],
                            theme.status_color(shot.status), dim=dim))
        meta.addStretch(1)
        due = (shot.get("config") or {}).get("due")
        if due:
            try:
                when = date.fromisoformat(due)
                days = (when - date.today()).days
                if days < 0:
                    meta.addWidget(Chip("due {}d overdue".format(-days),
                                        theme.status_color("hold")))
                elif days <= 3:
                    meta.addWidget(Chip("due in {}d".format(days),
                                        theme.status_color("wip")))
                else:
                    meta.addWidget(Chip("due " + due, theme.status_color("review")))
            except ValueError:
                meta.addWidget(Chip("due " + due, theme.status_color("review")))
        info.addLayout(meta)
        top.addLayout(info, 1)
        outer.addLayout(top)
        sub = QtWidgets.QLabel(_bsub_text(self.state, shot))
        sub.setObjectName("ShellDim")
        sub.setStyleSheet("font-size: 10.5px; padding: 0 9px 7px 9px;"
                          " background: transparent;")
        outer.addWidget(sub)
        if dim:
            dim_effect(card, 0.75)
        card._shell_shot = shot
        card._shell_dim = dim
        card.installEventFilter(self)
        return card

    # ------------------------------------------------------------------
    # gallery view
    # ------------------------------------------------------------------
    def _fill_gallery(self):
        clear_layout(self.gallery_pills_row)
        clear_layout(self.gallery_layout)
        self.gallery_layout.setRowStretch(0, 0)
        self.gallery_layout.setColumnStretch(0, 0)
        # status pills (the mockup's .gpills; click toggles a status filter)
        groups = self.state.grouped_by_status(self._shots)
        pill_count = 0
        for status in schema.STATUS_ORDER:
            shots = groups.get(status) or []
            if not shots:
                continue
            chip = GalleryPill("{} {}".format(schema.STATUS_LABELS[status],
                                              len(shots)),
                               theme.status_color(status))
            active = status in self._gallery_active
            chip.set_active(active)
            chip.clicked.connect(lambda s=status: self._toggle_gallery_status(s))
            self.gallery_pills_row.addWidget(chip)
            pill_count += 1
        self.gallery_pills_row.addStretch(1)

        shots = [s for s in self._shots if s.status in self._gallery_active]
        if not self._shots:
            self.gallery_layout.addWidget(EmptyState(
                "No shots match the current filters."), 0, 0)
            return
        if not shots:
            self.gallery_layout.addWidget(EmptyState(
                "All visible statuses are hidden — click a pill above to show it."),
                0, 0)
            return
        columns = max(2, max(1, self.width()) // 254)
        for index, shot in enumerate(shots):
            card = self._gallery_card(shot)
            self.gallery_layout.addWidget(card, index // columns, index % columns)
        self.gallery_layout.setRowStretch(len(shots) // columns + 1, 1)
        self.gallery_layout.setColumnStretch(columns, 1)

    def _toggle_gallery_status(self, status):
        if status in self._gallery_active:
            self._gallery_active.discard(status)
        else:
            self._gallery_active.add(status)
        self.refresh_views()

    def _gallery_card(self, shot):
        """The mockup's .gcard: 135px thumb with overlaid chips + captions."""
        from shellui.widgets import ClickableFrame
        card = ClickableFrame()
        card.setObjectName("ShellCard")
        card.setCursor(QtCore.Qt.PointingHandCursor)
        card.setMinimumHeight(195)
        card.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Fixed)
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        holder = ThumbOverlay(shot, self._thumb_path(shot), self)
        layout.addWidget(holder)

        cap = QtWidgets.QHBoxLayout()
        cap.setContentsMargins(11, 9, 11, 2)
        name = QtWidgets.QLabel(shot["name"] + "_comp")
        name.setStyleSheet("font-weight: 600; font-size: 12.5px; background: transparent;")
        cap.addWidget(name)
        cap.addStretch(1)
        version = QtWidgets.QLabel("v{:03d}".format(_latest_number(shot)))
        version.setObjectName("ShellDim")
        version.setStyleSheet("background: transparent;")
        cap.addWidget(version)
        layout.addLayout(cap)

        sub = QtWidgets.QLabel("{} · {}".format(shot.get("project_name", ""),
                                                _activity_text(shot)))
        sub.setObjectName("ShellDim")
        sub.setStyleSheet("font-size: 11px; padding: 0 11px 10px 11px;"
                          " background: transparent;")
        layout.addWidget(sub)

        if shot.status in ("delivered", "hold"):
            dim_effect(card, 0.6)
        card._shell_shot = shot
        card._shell_dim = shot.status in ("delivered", "hold")
        # without the filter the gallery cards LOOK clickable (cursor, hover
        # border) but double-click/right-click do nothing
        card.installEventFilter(self)
        return card

    # ------------------------------------------------------------------
    # interaction
    # ------------------------------------------------------------------
    def eventFilter(self, source, event):
        shot = getattr(source, "_shell_shot", None)
        if shot is not None and event.type() == QtCore.QEvent.MouseButtonDblClick:
            self.openShot.emit(shot)
            return True
        if shot is not None and event.type() == QtCore.QEvent.MouseButtonPress:
            pos = event_pos(event)
            if event.button() == QtCore.Qt.RightButton:
                # pos is relative to the card, not to this page
                self._context_menu(shot, source.mapToGlobal(pos))
                return True
        return super(BoardPage, self).eventFilter(source, event)

    def _context_menu(self, shot, global_pos):
        menu = QtWidgets.QMenu(self)
        menu.addAction("Open latest", lambda: self.openShot.emit(shot))
        menu.addSeparator()
        status_menu = menu.addMenu("Set status")
        for status in schema.STATUS_ORDER:
            action = status_menu.addAction(schema.STATUS_LABELS[status])
            action.setCheckable(True)
            action.setChecked(status == shot.status)
            action.triggered.connect(
                lambda _=False, s=status: self._set_status(shot, s))
        menu.addSeparator()
        menu.addAction("Duplicate shot...",
                       lambda: self._duplicate_shot(shot))
        menu.addAction("Open folder", lambda: self._open_folder(shot))
        menu.exec(global_pos)

    def _duplicate_shot(self, shot):
        import os
        from shellcore import naming, ops
        from shellcore.schema import load_project
        main = self.window()
        project = self.state.project_for(shot)
        if project is None:
            QtWidgets.QMessageBox.information(
                self, "Sleepy Shell", "This shot has no project.")
            return
        project_config, _ = load_project(project["path"])
        shots_dir = os.path.join(project["path"], "shots")
        if not os.path.isdir(shots_dir):
            shots_dir = project["path"]
        pattern = project_config.get("shot_pattern") or             self.state.prefs.get("shot_pattern", "sh###")
        highest = naming.highest_shot_number(shots_dir, pattern)
        suggested = naming.expand_shot_name(pattern, highest + 1)
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Duplicate {}".format(shot["name"]),
            "New shot name (comp of {} copied as v001):".format(shot["name"]),
            text=suggested)
        if not ok:
            return
        try:
            new_dir, _script = ops.duplicate_shot(
                shot["path"], name.strip() or None, self.state.prefs,
                project_config)
        except ops.OpError as exc:
            QtWidgets.QMessageBox.warning(self, "Sleepy Shell", str(exc))
            return
        self.state.refresh(force=True)
        self.refresh_views()
        for s in self.state.shots:
            if s["path"] == new_dir:
                self.openShot.emit(s)
                break

    def _set_status(self, shot, status):
        try:
            schema.save_shot(shot["path"], {"status": status})
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Sleepy Shell",
                                          "Could not save status:\n{}".format(exc))
            return
        shot.setdefault("config", {})["status"] = status
        self.shotChanged.emit()
        self.refresh_views()

    def _open_folder(self, shot):
        ok, message = self.backend.open_folder(shot["path"])
        if not ok:
            QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)

    def _thumb_path(self, shot):
        thumbs = self.state.shot_thumbnails(shot, limit=1)
        return thumbs[0] if thumbs else None


class ThumbOverlay(QtWidgets.QFrame):
    """A 135px gallery thumb with status/due chips overlaid at the corners."""

    def __init__(self, shot, thumb_path, board, parent=None):
        super(ThumbOverlay, self).__init__(parent)
        from shellui import theme
        self.setFixedHeight(135)
        self._board = board
        self._thumb = Thumb(shot["name"], thumb_path, (200, 135),
                            expanding=True, radius=0, font_px=22, parent=self)
        self._thumb.lower()
        self._status_chip = Chip(schema.STATUS_LABELS[shot.status],
                                 theme.status_color(shot.status), parent=self)
        self._status_chip.raise_()
        due = (shot.get("config") or {}).get("due")
        self._due_chip = None
        if due:
            try:
                when = date.fromisoformat(due)
                days = (when - date.today()).days
                if days < 0:
                    self._due_chip = Chip("due {}d overdue".format(-days),
                                          theme.status_color("hold"), parent=self)
                elif days <= 3:
                    self._due_chip = Chip("due in {}d".format(days),
                                          theme.status_color("wip"), parent=self)
            except ValueError:
                pass
            if self._due_chip is None:
                self._due_chip = Chip("due " + due, theme.status_color("review"),
                                      parent=self)
            self._due_chip.raise_()

    def resizeEvent(self, event):
        w, h = self.width(), self.height()
        self._thumb.setGeometry(QtCore.QRect(0, 0, w, h))
        self._status_chip.adjustSize()
        self._status_chip.move(w - self._status_chip.width() - 8, 8)
        if self._due_chip is not None:
            self._due_chip.adjustSize()
            self._due_chip.move(8, h - self._due_chip.height() - 8)
        super(ThumbOverlay, self).resizeEvent(event)


class GalleryPill(QtWidgets.QLabel):
    """Clickable status pill for the gallery filter row (.chip / .chip.off)."""

    clicked = QtCore.Signal()

    def __init__(self, text, color, parent=None):
        super(GalleryPill, self).__init__(text, parent)
        self._color = color
        self._active = True
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self._apply()

    def set_active(self, active):
        self._active = active
        self._apply()

    def _apply(self):
        from SleepyCore.qt import QtGui
        c = QtGui.QColor(self._color)
        rgb = "{},{},{}".format(c.red(), c.green(), c.blue())
        if self._active:
            self.setStyleSheet(
                "QLabel {{ background: rgba({rgb},15%); color: {hex};"
                " border: 1px solid rgba({rgb},40%); border-radius: 10px;"
                " padding: 2px 9px; font-size: 11px; font-weight: 600; }}".format(
                    rgb=rgb, hex=self._color))
        else:
            self.setStyleSheet(
                "QLabel {{ background: rgba({rgb},5%); color: rgba({rgb},35%);"
                " border: 1px solid rgba({rgb},15%); border-radius: 10px;"
                " padding: 2px 9px; font-size: 11px; font-weight: 600; }}".format(
                    rgb=rgb))

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super(GalleryPill, self).mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def event_pos(event):
    """Local mouse position (Qt 5 / Qt 6)."""
    if hasattr(event, "position"):
        try:
            return event.position().toPoint()
        except Exception:
            pass
    return event.pos()


def _latest_number(shot):
    from shellcore.versions import latest_version
    entry = latest_version(shot.get("comp_dir"))
    return entry["number"] if entry else 0


def _activity_text(shot):
    from shellcore.sessions import last_opened
    stamp = last_opened(shot.get("comp_dir"))
    if not stamp:
        return "never opened"
    days = (date.today() - date.fromtimestamp(stamp)).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return "{} days ago".format(days)


def _wide_text(state, shot):
    """The wide list cell: snapshot count + render state."""
    try:
        snapshots = state.shot_snapshots(shot)
    except Exception:
        snapshots = []
    from shellcore.versions import render_records
    rendered = any((r.get("render") or {}).get("status") == "done"
                   for r in render_records(snapshots))
    return "{} snapshots · {}".format(
        len(snapshots), "rendered ✓" if rendered else "not rendered yet")


def _bsub_text(state, shot):
    """The bcard sub line: project · when (or idle note)."""
    project = shot.get("project_name", "")
    idle = _idle_note(state, shot)
    if idle:
        return "{} · {}".format(project, idle)
    return "{} · {}".format(project, _activity_text(shot))


def _idle_note(state, shot):
    """Mockup-style 'idle N days' note when the stale check is on."""
    if not state.prefs.get("stale_check", True):
        return ""
    stale_days = state.prefs.get("stale_days", 14)
    from shellcore.sessions import last_opened
    stamp = last_opened(shot.get("comp_dir"))
    if not stamp:
        return ""
    days = (date.today() - date.fromtimestamp(stamp)).days
    if days >= stale_days:
        return "idle {} days".format(days)
    return ""


def theme_icon(name):
    from shellui import icons
    return icons.icon(name)
