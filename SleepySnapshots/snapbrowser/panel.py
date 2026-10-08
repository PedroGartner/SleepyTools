"""Snapshot Browser panel: the timeline of versions and snapshots."""

from __future__ import annotations

import datetime as _dt
import os
from collections import OrderedDict

from snapbrowser import core
from snapbrowser import nkparse
from snapbrowser.dialogs import (CleanupDialog, CompareDialog, HistoryDialog,
                                 ImageCompareDialog, SettingsDialog, open_node_history)
from snapbrowser.qt import QShortcut, QtCore, QtGui, QtWidgets

THUMB_SIZE = QtCore.QSize(64, 36)
DETAIL_THUMB = QtCore.QSize(320, 180)
ROLE_INDEX = getattr(QtCore.Qt.UserRole, "value", QtCore.Qt.UserRole) + 1

COLUMNS = ["Name", "Type", "Created", "Frame", "Nodes", "Size", "User", "Note"]
(COL_NAME, COL_TYPE, COL_TIME, COL_FRAME, COL_NODES, COL_SIZE, COL_USER, COL_NOTE) = range(len(COLUMNS))

KIND_COLORS = {
    core.KIND_MANUAL: "#7fb2ff",
    core.KIND_AUTO: "#9a9a9a",
    core.KIND_SAVE: "#9ccc65",
    core.KIND_RENDER: "#ffb74d",
    core.KIND_RESTORE: "#e57373",
    core.ENTRY_AUTOSAVE: "#ce93d8",
}
SIZE_JUMP_COLOR = "#ffb74d"

FILTERS = [
    ("All", lambda e: True),
    ("Versions", lambda e: e.type == core.ENTRY_VERSION),
    ("Snapshots", lambda e: e.type != core.ENTRY_VERSION),
    ("Manual snapshots", lambda e: e.type == core.ENTRY_SNAPSHOT and e.kind == core.KIND_MANUAL),
    ("Renders", lambda e: e.kind == core.KIND_RENDER),
    ("Starred", lambda e: e.starred),
]

GROUPINGS = ["No grouping", "By version", "By day", "By script"]
SCOPES = ["This script", "Whole folder"]


def format_time(stamp: _dt.datetime) -> str:
    now = _dt.datetime.now().astimezone()
    local = stamp.astimezone()
    if local.date() == now.date():
        return "Today " + local.strftime("%H:%M")
    if local.date() == (now - _dt.timedelta(days=1)).date():
        return "Yesterday " + local.strftime("%H:%M")
    if local.year == now.year:
        return local.strftime("%d %b %H:%M")
    return local.strftime("%Y-%m-%d %H:%M")


def format_day(stamp: _dt.datetime) -> str:
    local = stamp.astimezone()
    today = _dt.datetime.now().astimezone().date()
    if local.date() == today:
        return "Today"
    if local.date() == today - _dt.timedelta(days=1):
        return "Yesterday"
    return local.strftime("%a %d %b %Y")


def _entry_label(entry) -> str:
    if entry.type == core.ENTRY_VERSION:
        return entry.title
    return "{} ({}, {})".format(entry.title, entry.type_label.lower(), format_time(entry.time))


def _default_backend():
    from snapbrowser import nuke_bridge
    return nuke_bridge


class SnapshotBrowserPanel(QtWidgets.QWidget):
    def __init__(self, parent=None, backend=None):
        super().__init__(parent)
        self.setObjectName("SnapshotBrowserPanel")
        self.backend = backend or _default_backend()
        self.in_nuke = bool(getattr(self.backend, "IN_NUKE", False))
        self._script = None
        self._store = None
        self._entries = []
        self._pixmaps = {}
        self._size_jumps = {}

        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(250)
        self._refresh_timer.timeout.connect(self.refresh)

        self._watcher = QtCore.QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._schedule_refresh)

        self._build_ui()

        events = self.backend.events()
        events.changed.connect(self._schedule_refresh)
        events.script_changed.connect(self._schedule_refresh)

        self.refresh()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.script_label = QtWidgets.QLabel()
        self.script_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        font = self.script_label.font()
        font.setBold(True)
        self.script_label.setFont(font)

        self.scope_combo = QtWidgets.QComboBox()
        self.scope_combo.addItems(SCOPES)
        self.scope_combo.setToolTip("Show this script's versions, or every script in its folder")
        self.scope_combo.currentIndexChanged.connect(self.refresh)

        self.group_combo = QtWidgets.QComboBox()
        self.group_combo.addItems(GROUPINGS)
        self.group_combo.currentIndexChanged.connect(lambda *args: self._fill_tree())

        self.filter_combo = QtWidgets.QComboBox()
        self.filter_combo.addItems([name for name, _ in FILTERS])
        self.filter_combo.currentIndexChanged.connect(self._apply_filter)

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Search notes, tags, user...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)

        self.snapshot_button = QtWidgets.QPushButton("Take Snapshot")
        self.snapshot_button.setToolTip("Save the current state with an optional note")
        self.snapshot_button.clicked.connect(self._take_snapshot)

        more_button = QtWidgets.QToolButton()
        more_button.setText("More")
        more_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        more_menu = QtWidgets.QMenu(more_button)
        more_menu.addAction("Refresh", self.refresh)
        if self.in_nuke:
            more_menu.addAction("Compare Current Script With Last Save", self._compare_unsaved)
        more_menu.addAction("Node History...", self._node_history)
        more_menu.addSeparator()
        more_menu.addAction("Work History...", self._show_history)
        more_menu.addAction("Clean Up Snapshots...", self._clean_up)
        more_menu.addAction("Compress Old Snapshots", self._compress_old)
        more_menu.addSeparator()
        more_menu.addAction("Settings...", self._open_settings)
        more_button.setMenu(more_menu)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.script_label, 1)
        top.addWidget(self.snapshot_button)
        top.addWidget(more_button)

        options = QtWidgets.QHBoxLayout()
        options.addWidget(self.scope_combo)
        options.addWidget(self.group_combo)
        options.addWidget(self.filter_combo)
        options.addWidget(self.search_edit, 1)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(COLUMNS)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setIconSize(THUMB_SIZE)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemSelectionChanged.connect(self._on_selection)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        widths = {COL_NAME: 250, COL_TYPE: 95, COL_TIME: 105, COL_FRAME: 50,
                  COL_NODES: 50, COL_SIZE: 70, COL_USER: 75}
        for column, width in widths.items():
            self.tree.setColumnWidth(column, width)

        delete_shortcut = QShortcut(QtGui.QKeySequence.Delete, self.tree)
        delete_shortcut.setContext(QtCore.Qt.WidgetShortcut)
        delete_shortcut.activated.connect(self._delete_selected)

        self.empty_label = QtWidgets.QLabel()
        self.empty_label.setAlignment(QtCore.Qt.AlignCenter)
        self.empty_label.setWordWrap(True)

        self.list_stack = QtWidgets.QStackedWidget()
        self.list_stack.addWidget(self.tree)
        self.list_stack.addWidget(self.empty_label)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self.list_stack)
        splitter.addWidget(self._build_details())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([760, 340])

        self.status_label = QtWidgets.QLabel()
        self.status_label.setStyleSheet("color: #8a8a8a;")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(top)
        layout.addLayout(options)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.status_label)

    def _build_details(self):
        panel = QtWidgets.QWidget()
        panel.setMinimumWidth(260)

        self.detail_thumb = QtWidgets.QLabel("No preview")
        self.detail_thumb.setAlignment(QtCore.Qt.AlignCenter)
        self.detail_thumb.setMinimumSize(DETAIL_THUMB.width() * 3 // 4, DETAIL_THUMB.height() * 3 // 4)
        self.detail_thumb.setStyleSheet("background: #1e1e1e; color: #666; border-radius: 3px;")

        self.detail_title = QtWidgets.QLabel()
        font = self.detail_title.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.15)
        self.detail_title.setFont(font)
        self.detail_title.setWordWrap(True)

        self.detail_info = QtWidgets.QLabel()
        self.detail_info.setWordWrap(True)
        self.detail_info.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        self.star_check = QtWidgets.QCheckBox("Starred (never removed automatically)")
        self.star_check.toggled.connect(self._commit_star)

        self.note_edit = QtWidgets.QLineEdit()
        self.note_edit.setPlaceholderText("Add a note...")
        self.note_edit.editingFinished.connect(self._commit_note)

        self.tags_edit = QtWidgets.QLineEdit()
        self.tags_edit.setPlaceholderText("Tags, comma separated")
        self.tags_edit.editingFinished.connect(self._commit_tags)

        self.edit_box = QtWidgets.QWidget()
        edit_layout = QtWidgets.QVBoxLayout(self.edit_box)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        edit_layout.addWidget(self.note_edit)
        edit_layout.addWidget(self.tags_edit)
        edit_layout.addWidget(self.star_check)

        def button(text, slot, tip=""):
            widget = QtWidgets.QPushButton(text)
            widget.clicked.connect(slot)
            if tip:
                widget.setToolTip(tip)
            return widget

        self.compare_pair_button = button("Compare Selected", self._compare_selected,
                                          "Node and knob differences between the two selected entries")
        self.compare_images_button = button("Compare Thumbnails", self._compare_images)
        self.open_button = button("Open", self._open_selected)
        self.restore_button = button("Restore Into Current Script", self._restore_selected)
        self.compare_button = button("Compare With Current Script", self._compare_with_current,
                                     "What changed between this entry and the script as it is now")
        self.version_button = button("Save As Next Version", self._version_selected)
        self.promote_button = button("Keep This Snapshot", self._promote_selected,
                                     "Turn it into a manual snapshot so it is never removed automatically")
        self.render_button = button("Open Render Folder", self._open_render_folder)
        self.reveal_button = button("Reveal In Folder", self._reveal_selected)
        self.delete_button = button("Delete Snapshot", self._delete_selected)
        self._action_buttons = [
            self.compare_pair_button, self.compare_images_button, self.open_button,
            self.restore_button, self.compare_button, self.version_button, self.promote_button,
            self.render_button, self.reveal_button, self.delete_button,
        ]

        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.addWidget(self.detail_thumb)
        layout.addWidget(self.detail_title)
        layout.addWidget(self.detail_info)
        layout.addWidget(self.edit_box)
        for widget in self._action_buttons:
            layout.addWidget(widget)
        layout.addStretch(1)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(panel)

        self._show_details([])
        return scroll

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    @property
    def folder_scope(self) -> bool:
        return self.scope_combo.currentIndex() == 1

    def _schedule_refresh(self, *args):
        self._refresh_timer.start()

    def refresh(self, *args):
        selected_paths = [e.path for e in self._selected_entries()]

        script = self.backend.current_script()
        if script != self._script:
            self._script = script
            self._store = core.SnapshotStore(script) if script else None
            self._pixmaps.clear()

        self._update_watcher()

        if not script:
            self._entries = []
            self.script_label.setText("No script")
            self.snapshot_button.setEnabled(False)
            self.tree.clear()
            self._show_empty(getattr(self.backend, "EMPTY_HINT",
                                     "Save the script to start taking snapshots.\n"
                                     "Snapshots are stored in a .snapshots folder next to it."))
            self.status_label.clear()
            self._show_details([])
            return

        self.script_label.setText(os.path.basename(script))
        self.script_label.setToolTip(script)
        self.snapshot_button.setEnabled(True)
        if self.folder_scope:
            self._entries = core.build_folder_timeline(script)
        else:
            self._entries = core.build_timeline(script, self._store)
        self._size_jumps = self._find_size_jumps()
        self._fill_tree(selected_paths)
        self._update_status()

    def _update_watcher(self):
        wanted = []
        if self._script:
            folder = os.path.dirname(os.path.abspath(self._script))
            wanted.append(folder)
            snapshots_root = os.path.join(folder, core.SNAPSHOT_DIR)
            if self.folder_scope and os.path.isdir(snapshots_root):
                wanted.extend(os.path.join(snapshots_root, name) for name in os.listdir(snapshots_root)
                              if os.path.isdir(os.path.join(snapshots_root, name)))
            elif os.path.isdir(self._store.folder):
                wanted.append(self._store.folder)
        current = self._watcher.directories()
        if sorted(current) != sorted(wanted):
            if current:
                self._watcher.removePaths(current)
            if wanted:
                self._watcher.addPaths(wanted)

    def _find_size_jumps(self):
        """Entries whose script grew a lot compared to the previous entry of the same shot."""
        jumps = {}
        previous = {}
        for entry in sorted(self._entries, key=lambda e: e.time):
            if entry.size is None or entry.type == core.ENTRY_AUTOSAVE:
                continue
            before = previous.get(entry.family)
            if before and before.size and entry.size > before.size * 1.5 \
                    and entry.size - before.size > 200 * 1024:
                jumps[id(entry)] = before
            previous[entry.family] = entry
        return jumps

    def _version_thumbnails(self):
        """Newest snapshot thumbnail per (shot, version), used as a preview for version rows."""
        result = {}
        for entry in self._entries:
            if entry.type == core.ENTRY_SNAPSHOT and entry.thumbnail and entry.version is not None:
                result.setdefault((entry.family, entry.version), entry.thumbnail)
        return result

    def _thumbnail_for(self, entry, version_thumbs=None):
        if entry.thumbnail:
            return entry.thumbnail
        if entry.type == core.ENTRY_VERSION:
            if version_thumbs is None:
                version_thumbs = self._version_thumbnails()
            return version_thumbs.get((entry.family, entry.version))
        return None

    def _pixmap(self, path, size):
        if not path:
            return None
        key = (path, size.width(), size.height())
        if key not in self._pixmaps:
            pixmap = QtGui.QPixmap(path)
            self._pixmaps[key] = None if pixmap.isNull() else pixmap.scaled(
                size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        return self._pixmaps[key]

    # ------------------------------------------------------------------
    # Tree
    # ------------------------------------------------------------------

    def _group_key(self, entry):
        mode = self.group_combo.currentIndex()
        if mode == 1:
            label = "v{:03d}".format(entry.version) if entry.version is not None else "No version"
            return "{}  {}".format(entry.family, label) if self.folder_scope else label
        if mode == 2:
            return format_day(entry.time)
        if mode == 3:
            return entry.family or "Other"
        return None

    def _make_item(self, index, entry, version_thumbs):
        item = QtWidgets.QTreeWidgetItem()
        item.setData(0, ROLE_INDEX, index)

        title = entry.title
        if self.folder_scope and entry.type != core.ENTRY_VERSION and self.group_combo.currentIndex() != 3:
            title = "{}  {}".format(entry.family, title)
        if entry.starred:
            title = "★ " + title
        if entry.is_current:
            title += "  (current)"
            font = item.font(COL_NAME)
            font.setBold(True)
            item.setFont(COL_NAME, font)
        item.setText(COL_NAME, title)
        item.setToolTip(COL_NAME, entry.path)

        item.setText(COL_TYPE, entry.type_label)
        color = KIND_COLORS.get(entry.kind or entry.type)
        if color:
            item.setForeground(COL_TYPE, QtGui.QBrush(QtGui.QColor(color)))

        item.setText(COL_TIME, format_time(entry.time))
        item.setToolTip(COL_TIME, entry.time.strftime("%Y-%m-%d %H:%M:%S"))
        item.setText(COL_FRAME, "" if entry.frame is None else str(entry.frame))
        item.setText(COL_NODES, "" if entry.nodes is None else str(entry.nodes))
        item.setText(COL_SIZE, core.format_size(entry.size))
        item.setTextAlignment(COL_NODES, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        item.setTextAlignment(COL_SIZE, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        before = self._size_jumps.get(id(entry))
        if before is not None:
            item.setForeground(COL_SIZE, QtGui.QBrush(QtGui.QColor(SIZE_JUMP_COLOR)))
            item.setToolTip(COL_SIZE, "Grew from {} to {} since {}".format(
                core.format_size(before.size), core.format_size(entry.size), _entry_label(before)))
        item.setText(COL_USER, entry.user)

        note = entry.note
        if entry.tags:
            note = (note + "  " if note else "") + " ".join("#" + t for t in entry.tags)
        item.setText(COL_NOTE, note)
        item.setToolTip(COL_NOTE, note)

        pixmap = self._pixmap(self._thumbnail_for(entry, version_thumbs), THUMB_SIZE)
        if pixmap is not None:
            item.setIcon(COL_NAME, QtGui.QIcon(pixmap))
        return item

    def _fill_tree(self, selected_paths=None):
        if selected_paths is None:
            selected_paths = [e.path for e in self._selected_entries()]
        selected_paths = set(selected_paths)

        self.tree.blockSignals(True)
        self.tree.clear()
        version_thumbs = self._version_thumbnails()
        grouped = self.group_combo.currentIndex() != 0
        self.tree.setRootIsDecorated(grouped)

        groups = OrderedDict()
        items = []
        for index, entry in enumerate(self._entries):
            item = self._make_item(index, entry, version_thumbs)
            items.append((entry, item))
            if grouped:
                key = self._group_key(entry)
                if key not in groups:
                    header = QtWidgets.QTreeWidgetItem([key])
                    header.setData(0, ROLE_INDEX + 1, key)
                    font = header.font(0)
                    font.setBold(True)
                    header.setFont(0, font)
                    header.setFlags(QtCore.Qt.ItemIsEnabled)
                    groups[key] = header
                    self.tree.addTopLevelItem(header)
                groups[key].addChild(item)
            else:
                self.tree.addTopLevelItem(item)

        for header in groups.values():
            has_current = any(
                self._entries[header.child(i).data(0, ROLE_INDEX)].is_current
                for i in range(header.childCount()))
            header.setExpanded(has_current or len(groups) <= 6)

        reselect = [item for entry, item in items if entry.path in selected_paths]
        for item in reselect:
            item.setSelected(True)
        self.tree.blockSignals(False)

        self._apply_filter()
        if reselect:
            self.tree.scrollToItem(reselect[0])
        self._on_selection()

    def _iter_entry_items(self):
        for row in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(row)
            if top.data(0, ROLE_INDEX) is not None:
                yield top
            for child in range(top.childCount()):
                yield top.child(child)

    def _apply_filter(self, *args):
        _, accept = FILTERS[self.filter_combo.currentIndex()]
        text = self.search_edit.text()
        visible = 0
        for item in self._iter_entry_items():
            entry = self._entries[item.data(0, ROLE_INDEX)]
            shown = accept(entry) and entry.matches(text)
            item.setHidden(not shown)
            visible += shown

        for row in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(row)
            if top.data(0, ROLE_INDEX) is None:
                shown = sum(not top.child(i).isHidden() for i in range(top.childCount()))
                top.setHidden(not shown)
                top.setText(0, "{}   ({})".format(top.data(0, ROLE_INDEX + 1), shown))

        if not self._entries:
            self._show_empty("No versions or snapshots yet.\nUse Take Snapshot to save the current state.")
        elif not visible:
            self._show_empty("Nothing matches the current filter.")
        else:
            self.list_stack.setCurrentWidget(self.tree)

    def _show_empty(self, text):
        self.empty_label.setText(text)
        self.list_stack.setCurrentWidget(self.empty_label)

    def _update_status(self):
        versions = sum(e.type == core.ENTRY_VERSION for e in self._entries)
        snapshots = sum(e.type == core.ENTRY_SNAPSHOT for e in self._entries)
        parts = ["{} versions".format(versions), "{} snapshots".format(snapshots)]
        if self._script:
            if self.folder_scope:
                folder = os.path.join(os.path.dirname(os.path.abspath(self._script)), core.SNAPSHOT_DIR)
                usage = core.folder_size(folder)
            else:
                usage = self._store.disk_usage()
            parts.append("{} on disk".format(core.format_size(usage)))
        if self.in_nuke:
            minutes = int(self.backend.settings().get("auto_interval_minutes") or 0)
            parts.append("auto every {} min".format(minutes) if minutes else "auto snapshots off")
        self.status_label.setText("  ·  ".join(parts))

    # ------------------------------------------------------------------
    # Selection and details
    # ------------------------------------------------------------------

    def _selected_entries(self):
        if not hasattr(self, "tree"):
            return []
        result = []
        for item in self.tree.selectedItems():
            index = item.data(0, ROLE_INDEX)
            if index is not None and index < len(self._entries):
                result.append(self._entries[index])
        return result

    def _selected_entry(self):
        entries = self._selected_entries()
        return entries[0] if entries else None

    def _on_selection(self):
        self._show_details(self._selected_entries())

    def _store_for(self, entry):
        if entry.snapshot is None:
            return self._store
        if self._store is not None and os.path.normcase(entry.snapshot.folder) == \
                os.path.normcase(self._store.folder):
            return self._store
        return core.SnapshotStore(self._script or entry.path, folder=entry.snapshot.folder)

    def _show_details(self, entries):
        for widget in self._action_buttons:
            widget.setVisible(False)
        self.edit_box.setVisible(False)

        if len(entries) == 2:
            older, newer = sorted(entries, key=lambda e: e.time)
            self.detail_title.setText("Two entries selected")
            self.detail_info.setText("{}<br>{}".format(_escape(_entry_label(older)),
                                                      _escape(_entry_label(newer))))
            self._set_thumb(self._thumbnail_for(newer))
            self.compare_pair_button.setVisible(True)
            self.compare_images_button.setVisible(
                bool(self._thumbnail_for(older) and self._thumbnail_for(newer)))
            return

        if len(entries) != 1:
            self.detail_title.setText("{} entries selected".format(len(entries)) if entries else "")
            self.detail_info.setText("Select two entries to compare them." if entries
                                     else "Select a version or snapshot.")
            self._set_thumb(None)
            self.delete_button.setVisible(any(e.snapshot is not None for e in entries))
            return

        entry = entries[0]
        is_snapshot = entry.type == core.ENTRY_SNAPSHOT
        is_version = entry.type == core.ENTRY_VERSION
        is_current = is_version and entry.is_current

        self.detail_title.setText(entry.title)
        self._set_thumb(self._thumbnail_for(entry))

        rows = [("Type", entry.type_label), ("Created", entry.time.strftime("%Y-%m-%d %H:%M:%S"))]
        if self.folder_scope and entry.family:
            rows.append(("Shot", entry.family))
        if entry.version is not None:
            rows.append(("Version", "v{:03d}".format(entry.version)))
        if entry.frame is not None:
            rows.append(("Frame", str(entry.frame)))
        if entry.nodes is not None:
            rows.append(("Nodes", str(entry.nodes)))
        if entry.size is not None:
            rows.append(("Size", core.format_size(entry.size)))
        meta = entry.meta
        if meta.get("user"):
            rows.append(("User", "{} @ {}".format(meta.get("user"), meta.get("host", ""))))
        if meta.get("app"):
            rows.append(("Nuke", meta["app"]))
        render = entry.render
        for key, label in (("frame_range", "Frames"), ("write_node", "Write"),
                           ("output", "Output"), ("status", "Render status")):
            if render.get(key):
                rows.append((label, str(render[key])))
        rows.append(("File", os.path.basename(entry.path)))
        self.detail_info.setText("<br>".join(
            "<span style='color:#8a8a8a'>{}:</span> {}".format(label, _escape(value))
            for label, value in rows))

        self.open_button.setVisible(is_version and not is_current)
        self.restore_button.setVisible(self.in_nuke and not is_current)
        self.compare_button.setVisible(self.in_nuke or not is_current)
        self.compare_button.setText("Compare With Unsaved Changes" if is_current
                                    else "Compare With Current Script")
        self.version_button.setVisible(not is_current)
        self.promote_button.setVisible(is_snapshot and entry.kind != core.KIND_MANUAL)
        self.render_button.setVisible(bool(render.get("output")))
        self.reveal_button.setVisible(True)
        self.delete_button.setVisible(is_snapshot)

        self.edit_box.setVisible(is_snapshot)
        if is_snapshot:
            self._set_quietly(self.note_edit, entry.note)
            self._set_quietly(self.tags_edit, ", ".join(entry.tags))
            self.star_check.blockSignals(True)
            self.star_check.setChecked(entry.starred)
            self.star_check.blockSignals(False)

    def _set_thumb(self, path):
        pixmap = self._pixmap(path, DETAIL_THUMB)
        if pixmap is not None:
            self.detail_thumb.setPixmap(pixmap)
        else:
            self.detail_thumb.setPixmap(QtGui.QPixmap())
            self.detail_thumb.setText("No preview")

    @staticmethod
    def _set_quietly(edit, text):
        if edit.hasFocus() and edit.isModified():
            return
        edit.blockSignals(True)
        edit.setText(text)
        edit.setModified(False)
        edit.blockSignals(False)

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------

    def _update_entry(self, entry, **fields):
        if entry is None or entry.snapshot is None:
            return
        try:
            self._store_for(entry).update(entry.snapshot, **fields)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Snapshot Browser", "Could not save:\n{}".format(exc))
            return
        self._schedule_refresh()

    def _commit_note(self):
        entry = self._selected_entry()
        if entry is not None and self.note_edit.text().strip() != entry.note:
            self._update_entry(entry, note=self.note_edit.text().strip())
        self.note_edit.setModified(False)

    def _commit_tags(self):
        entry = self._selected_entry()
        tags = [t.strip().lstrip("#") for t in self.tags_edit.text().split(",") if t.strip()]
        if entry is not None and tags != entry.tags:
            self._update_entry(entry, tags=tags)
        self.tags_edit.setModified(False)

    def _commit_star(self, checked):
        self._update_entry(self._selected_entry(), starred=bool(checked))

    def _promote_selected(self):
        entry = self._selected_entry()
        if entry is None or entry.snapshot is None:
            return
        note, accepted = QtWidgets.QInputDialog.getText(
            self, "Keep This Snapshot", "Note:", text=entry.note)
        if accepted:
            self._store_for(entry).promote(entry.snapshot, note.strip())
            self.refresh()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _take_snapshot(self):
        self.backend.take_snapshot_interactive()
        self.refresh()

    def _open_selected(self):
        entry = self._selected_entry()
        if entry is not None and entry.type == core.ENTRY_VERSION:
            self.backend.open_script(entry.path)

    def _restore_selected(self):
        entry = self._selected_entry()
        if entry is not None and self.in_nuke:
            self.backend.restore(entry.path, _entry_label(entry))

    def _version_selected(self):
        entry = self._selected_entry()
        if entry is None:
            return
        reference = self._script
        if self.folder_scope and entry.family != core.shot_key(self._script):
            source = entry.meta.get("source_script")
            reference = source if source and entry.type == core.ENTRY_SNAPSHOT else entry.path
        self.backend.save_as_next_version(entry.path, reference)

    def _reveal_selected(self):
        entry = self._selected_entry()
        if entry is not None:
            core.reveal_in_file_browser(entry.path)

    def _open_render_folder(self):
        entry = self._selected_entry()
        output = entry.render.get("output") if entry else None
        if not output:
            return
        folder = os.path.dirname(output)
        if os.path.isdir(folder):
            core.open_folder(folder)
        else:
            QtWidgets.QMessageBox.information(self, "Open Render Folder",
                                              "The render folder does not exist:\n{}".format(folder))

    def _delete_selected(self):
        entries = [e for e in self._selected_entries() if e.snapshot is not None]
        if not entries:
            return
        if len(entries) == 1:
            text = "Delete this snapshot?\n\n{}".format(_entry_label(entries[0]))
        else:
            text = "Delete {} snapshots?".format(len(entries))
        if QtWidgets.QMessageBox.question(self, "Delete Snapshot", text) != QtWidgets.QMessageBox.Yes:
            return
        for entry in entries:
            self._store_for(entry).delete(entry.snapshot)
        self.refresh()

    # -- comparing --------------------------------------------------------

    @staticmethod
    def _read(path):
        return core.read_script_text(path)

    def _open_history(self, node_path):
        if self._script and node_path:
            open_node_history(self.backend, self._script, node_path, self)

    def _node_history(self):
        if not self._script:
            return
        path = self.backend.selected_node_path() if self.in_nuke else None
        if not path:
            try:
                script = nkparse.parse(self.backend.current_state_text())
            except OSError as exc:
                QtWidgets.QMessageBox.warning(self, "Node History", str(exc))
                return
            names = [p for p in script.nodes if p != "Root"]
            path, accepted = QtWidgets.QInputDialog.getItem(
                self, "Node History", "Node (select one in the node graph to skip this):",
                names, 0, True)
            if not accepted:
                return
        self._open_history(path.strip())

    def _compare_with_current(self):
        entry = self._selected_entry()
        if entry is None:
            return
        try:
            older_text = self._read(entry.path)
            newer_text = self.backend.current_state_text()
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Compare", str(exc))
            return
        if self.in_nuke:
            newer_label = "Current script (unsaved changes included)"
        else:
            newer_label = os.path.basename(self._script)
        older_label = "Last save of " + entry.title if entry.is_current else _entry_label(entry)
        CompareDialog(self.backend, older_label, older_text, newer_label, newer_text,
                      newer_is_live=self.in_nuke, parent=self, on_history=self._open_history).exec()

    def _compare_unsaved(self):
        if not self._script or not os.path.isfile(self._script):
            return
        CompareDialog(self.backend, "Last save of " + os.path.basename(self._script),
                      self._read(self._script), "Current script (unsaved changes included)",
                      self.backend.current_state_text(), newer_is_live=True, parent=self,
                      on_history=self._open_history).exec()

    def _compare_selected(self):
        entries = self._selected_entries()
        if len(entries) != 2:
            return
        older, newer = sorted(entries, key=lambda e: e.time)
        try:
            older_text, newer_text = self._read(older.path), self._read(newer.path)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Compare", str(exc))
            return
        CompareDialog(self.backend, _entry_label(older), older_text, _entry_label(newer), newer_text,
                      newer_is_live=False, parent=self, on_history=self._open_history).exec()

    def _compare_images(self):
        entries = self._selected_entries()
        if len(entries) != 2:
            return
        older, newer = sorted(entries, key=lambda e: e.time)
        a, b = self._thumbnail_for(older), self._thumbnail_for(newer)
        if a and b:
            ImageCompareDialog(a, _entry_label(older), b, _entry_label(newer), self).exec()

    # -- menus and dialogs ------------------------------------------------

    def _on_double_click(self, item, column):
        index = item.data(0, ROLE_INDEX)
        if index is None:
            return
        entry = self._entries[index]
        if entry.type == core.ENTRY_VERSION:
            if not entry.is_current:
                self.backend.open_script(entry.path)
        elif self.in_nuke:
            self._restore_selected()
        else:
            self._compare_with_current()

    def _context_menu(self, position):
        item = self.tree.itemAt(position)
        if item is None or item.data(0, ROLE_INDEX) is None:
            return
        if not item.isSelected():
            self.tree.setCurrentItem(item)
        entries = self._selected_entries()
        menu = QtWidgets.QMenu(self)

        if len(entries) == 2:
            menu.addAction("Compare Selected", self._compare_selected)
            if self.compare_images_button.isVisible():
                menu.addAction("Compare Thumbnails", self._compare_images)
        elif len(entries) == 1:
            entry = entries[0]
            is_current = entry.type == core.ENTRY_VERSION and entry.is_current
            if entry.type == core.ENTRY_VERSION and not is_current:
                menu.addAction("Open", self._open_selected)
            if self.in_nuke and not is_current:
                menu.addAction("Restore Into Current Script", self._restore_selected)
            if self.in_nuke or not is_current:
                menu.addAction(self.compare_button.text(), self._compare_with_current)
            if not is_current:
                menu.addAction("Save As Next Version", self._version_selected)
            menu.addSeparator()
            if entry.type == core.ENTRY_SNAPSHOT:
                star = menu.addAction("Unstar" if entry.starred else "Star")
                star.triggered.connect(lambda: self._update_entry(entry, starred=not entry.starred))
                if entry.kind != core.KIND_MANUAL:
                    menu.addAction("Keep This Snapshot...", self._promote_selected)
            if entry.render.get("output"):
                menu.addAction("Open Render Folder", self._open_render_folder)
            menu.addAction("Reveal In Folder", self._reveal_selected)
            menu.addAction("Copy Path", lambda: QtWidgets.QApplication.clipboard().setText(entry.path))

        if any(e.snapshot is not None for e in entries):
            menu.addSeparator()
            menu.addAction("Delete Snapshot" if len(entries) == 1 else "Delete Snapshots",
                           self._delete_selected)
        if not menu.isEmpty():
            menu.exec(self.tree.viewport().mapToGlobal(position))

    def _show_history(self):
        if not self._script:
            return
        times = [e.time for e in self._entries
                 if e.type != core.ENTRY_AUTOSAVE and (self.folder_scope or e.family == self._store.key)]
        if self.folder_scope:
            title = os.path.basename(os.path.dirname(os.path.abspath(self._script)))
        else:
            title = self._store.key
        HistoryDialog(title, times, self).exec()

    def _clean_up(self):
        if not self._store:
            return
        dialog = CleanupDialog(self._store, self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            days, manual = dialog.values()
            removed = self._store.cleanup(days, include_manual=manual)
            self.refresh()
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "Deleted {} snapshot{}".format(
                len(removed), "" if len(removed) == 1 else "s"), self)

    def _compress_old(self):
        if not self._store:
            return
        count, saved = self._store.compress_all()
        self.refresh()
        if count:
            text = "Compressed {} snapshot{}, saving {}.".format(
                count, "" if count == 1 else "s", core.format_size(saved))
        else:
            text = "All snapshots are already compressed."
        QtWidgets.QMessageBox.information(self, "Compress Old Snapshots", text)

    def _open_settings(self):
        dialog = SettingsDialog(self.backend.settings(), in_nuke=self.in_nuke, parent=self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.backend.update_settings(dialog.values())
            self._update_status()


def _escape(text) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
