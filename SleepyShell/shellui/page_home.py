"""Home page: search row, continue-where-you-left-off hero, recent shots.

Matches the mockup's launcher screen: search field with a Ctrl+K hint
and an "Open Nuke…" button, a hero card with kicker/stat row/actions,
and a four-column recent-shots grid of full-bleed 96px thumbs.
"""

from datetime import date

from SleepyCore.qt import QtCore, QtGui, QtWidgets, QShortcut

from shellui.widgets import (Chip, EmptyState, Thumb, clear_layout, styled)


class HomePage(QtWidgets.QWidget):
    openShot = QtCore.Signal(object)
    gotoBoard = QtCore.Signal()

    def __init__(self, state, backend, parent=None):
        super(HomePage, self).__init__(parent)
        self.state = state
        self.backend = backend
        self._cards = []
        styled(self)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        content = styled(QtWidgets.QWidget())
        self.layout_root = QtWidgets.QVBoxLayout(content)
        self.layout_root.setContentsMargins(20, 18, 20, 18)
        self.layout_root.setSpacing(16)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.layout_root.addStretch(1)

    # ------------------------------------------------------------------
    def status_hint(self):
        return ""

    def refresh(self):
        clear_layout(self.layout_root)
        self.layout_root.addStretch(0)

        self._build_briefing()
        recents = self.state.recent_shots(limit=8)
        if recents:
            self._build_search_row()
            self._build_hero(recents[0])
            from shellui.widgets import spaced_header
            self.layout_root.addWidget(spaced_header("Recent shots", size=11,
                                                     spacing=1.2))
            grid = QtWidgets.QGridLayout()
            grid.setSpacing(12)
            # the mockup's grid is four ~250px columns; cards never stretch
            # to the window width even when fewer than four are shown
            for index, shot in enumerate(recents[:4]):
                card = self._recent_card(shot)
                card.setFixedWidth(262)
                grid.addWidget(card, 0, index)
            grid.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
            self.layout_root.addLayout(grid)
        else:
            self._build_search_row()
            empty = QtWidgets.QFrame()
            empty.setObjectName("ShellHero")
            empty_layout = QtWidgets.QVBoxLayout(empty)
            empty_layout.setContentsMargins(28, 24, 28, 24)
            empty_layout.setSpacing(10)
            heading = QtWidgets.QLabel("Welcome to Sleepy Shell")
            heading.setObjectName("ShellH1")
            empty_layout.addWidget(heading)
            text = EmptyState(
                "No recent shots yet.\n\n"
                "Add a watched root in Preferences (the parent folder that holds "
                "your projects), then open a shot from the Board.\n\n"
                "Shell derives everything from disk: versions, snapshots, renders "
                "and last-opened times. It only stores status, notes, due date "
                "and tags per shot.")
            empty_layout.addWidget(text)
            button_row = QtWidgets.QHBoxLayout()
            button_row.addStretch(1)
            board_button = QtWidgets.QPushButton("Open the Board")
            board_button.setProperty("accent", True)
            board_button.clicked.connect(self.gotoBoard.emit)
            button_row.addWidget(board_button)
            empty_layout.addLayout(button_row)
            self.layout_root.addWidget(empty)
        self.layout_root.addStretch(1)

    # ------------------------------------------------------------------
    def _build_search_row(self):
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(10)

        # mockup's .search: one styled frame holding the magnifier, the
        # input and the Ctrl+K chip. A QLineEdit action icon would be
        # forced into the ~16px icon box (unreadably small), so the chip
        # is a real QLabel painted at full size instead.
        box = QtWidgets.QFrame()
        box.setObjectName("ShellSearch")
        box_row = QtWidgets.QHBoxLayout(box)
        box_row.setContentsMargins(10, 3, 8, 3)
        box_row.setSpacing(8)
        icon_label = QtWidgets.QLabel()
        icon_label.setPixmap(kbd_search_pixmap())
        box_row.addWidget(icon_label)

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Search shots, notes, tags, node types…")
        self.search_edit.setFrame(False)
        self.search_edit.setBackgroundRole(QtGui.QPalette.Window)
        self.search_edit.setStyleSheet("background: transparent; border: none;")
        self.search_edit.returnPressed.connect(self._search_jump)
        box_row.addWidget(self.search_edit, 1)

        kbd_label = QtWidgets.QLabel()
        kbd_label.setPixmap(kbd_chip_pixmap("Ctrl+K"))
        kbd_label.setToolTip("Press Ctrl+K to focus the search")
        box_row.addWidget(kbd_label)

        shortcut = QShortcut(QtGui.QKeySequence("Ctrl+K"), self)
        shortcut.activated.connect(lambda: (self.search_edit.setFocus(),
                                            self.search_edit.selectAll()))
        row.addWidget(box, 1)

        if not self.backend.can_nuke:
            nuke_button = QtWidgets.QPushButton("Open Nuke…")
            nuke_button.clicked.connect(self._open_nuke)
            row.addWidget(nuke_button)
        self.layout_root.addLayout(row)

    def _search_jump(self):
        text = self.search_edit.text().strip()
        main = self.window()
        board = getattr(main, "board_page", None)
        if board is not None:
            board.set_search(text)
        self.gotoBoard.emit()

    def _open_nuke(self):
        ok, message = self.backend.launch_app()
        if not ok:
            QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)

    # ------------------------------------------------------------------
    def _build_briefing(self):
        """The morning briefing: what deserves attention right now."""
        from shellcore.briefing import compute_briefing
        from shellui.widgets import spaced_header
        groups = compute_briefing(self.state.shots,
                                  stale_days=int(self.state.prefs.get(
                                      "stale_days", 14) or 14),
                                  due_window=int(self.state.prefs.get(
                                      "due_days", 7) or 7))
        if not groups:
            return
        box = QtWidgets.QFrame()
        box.setObjectName("ShellCard")
        box_layout = QtWidgets.QVBoxLayout(box)
        box_layout.setContentsMargins(14, 10, 14, 12)
        box_layout.setSpacing(6)
        header = QtWidgets.QHBoxLayout()
        header.addWidget(spaced_header("Briefing", size=11, spacing=1.2))
        header.addStretch(1)
        box_layout.addLayout(header)
        for group in groups:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(7)
            title = QtWidgets.QLabel("{} ({})".format(
                group["title"], len(group["shots"])))
            title.setStyleSheet("color: #9a9ea6; font-size: 12px;")
            row.addWidget(title)
            for shot in group["shots"][:4]:
                chip = ClickableChipLabel(shot["name"])
                chip.clicked.connect(lambda s=shot: self.openShot.emit(s))
                row.addWidget(chip)
            remaining = len(group["shots"]) - 4
            if remaining > 0:
                more = QtWidgets.QLabel("+{}".format(remaining))
                more.setObjectName("ShellDim")
                row.addWidget(more)
            row.addStretch(1)
            box_layout.addLayout(row)
        self.layout_root.addWidget(box)

    def _build_hero(self, shot):
        hero = QtWidgets.QFrame()
        hero.setObjectName("ShellHero")
        layout = QtWidgets.QHBoxLayout(hero)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        thumb = Thumb(shot["name"], self._thumb_path(shot), (340, 190),
                      tag=_thumb_tag(shot), radius=0, font_px=34)
        layout.addWidget(thumb)
        info = QtWidgets.QVBoxLayout()
        info.setContentsMargins(20, 18, 20, 18)
        info.setSpacing(6)
        kicker = QtWidgets.QLabel("Continue where you left off")
        kicker.setObjectName("ShellKicker")
        _tracked(kicker, 1.4)
        info.addWidget(kicker)
        title = QtWidgets.QLabel(_script_label(shot))
        title.setObjectName("ShellH1")
        info.addWidget(title)
        snap_count = len(self.state.shot_snapshots(shot))
        meta_bits = ["{}".format(shot.get("project_name", "")),
                     "last opened {}".format(_ago_text(shot))]
        if snap_count:
            meta_bits.append("{} snapshots".format(snap_count))
        project_label = QtWidgets.QLabel(" · ".join(b for b in meta_bits if b))
        project_label.setObjectName("ShellDim")
        project_label.setStyleSheet("font-size: 12.5px;")
        info.addWidget(project_label)
        info.addSpacing(6)
        info.addLayout(self._hero_stats(shot))
        info.addStretch(1)
        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(8)
        open_button = QtWidgets.QPushButton("Resume in Nuke")
        open_button.setProperty("accent", True)
        if not self.backend.can_nuke:
            open_button.setToolTip(
                "Launches Nuke with this script (set the Nuke executable "
                "under Preferences > Startup).")
        open_button.clicked.connect(lambda: self._resume(shot))
        actions.addWidget(open_button)
        folder_button = QtWidgets.QPushButton("Open folder")
        folder_button.clicked.connect(lambda: self._open_folder(shot))
        actions.addWidget(folder_button)
        browser_button = QtWidgets.QPushButton("Snapshot Browser")
        browser_button.clicked.connect(lambda: self._open_snapshot_browser(shot))
        actions.addWidget(browser_button)
        actions.addStretch(1)
        info.addLayout(actions)
        layout.addLayout(info, 1)
        self.layout_root.addWidget(hero)

    def _hero_stats(self, shot):
        """The mockup's four stat columns under the hero title."""
        from shellcore import sessions as sessions_mod
        from shellcore.versions import render_records
        from shellui import theme
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(26)
        summary = sessions_mod.summarize_for_shot(shot["path"], shot.get("comp_dir"))
        renders = render_records(self.state.shot_snapshots(shot))
        latest_render = "—"
        if renders:
            info = renders[0].get("render") or {}
            latest_render = "{} · {}".format(info.get("write_node", "?"),
                                             info.get("frame_range", "?"))
        due = (shot.get("config") or {}).get("due")
        due_value = "—"
        due_color = None
        if due:
            try:
                days = (date.fromisoformat(due) - date.today()).days
                due_value = "in {} days".format(days) if days > 0 else \
                    ("today" if days == 0 else "{}d overdue".format(-days))
                due_color = theme.status_color("wip" if days >= 0 else "hold")
            except ValueError:
                due_value = due
        for caption, value_widget in (
                ("Status", Chip(_status_label(shot), theme.status_color(shot.status))),
                ("Session time", _stat_value(_hours_text(summary.get("total", 0.0)))),
                ("Latest render", _stat_value(latest_render, dim=True)),
                ("Due", _stat_value(due_value, color=due_color))):
            column = QtWidgets.QVBoxLayout()
            column.setSpacing(3)
            cap = QtWidgets.QLabel(caption)
            cap.setObjectName("ShellDim")
            cap.setStyleSheet("font-size: 10.5px;")
            column.addWidget(cap)
            column.addWidget(value_widget)
            holder = QtWidgets.QWidget()
            holder.setLayout(column)
            row.addWidget(holder)
        row.addStretch(1)
        return row

    def _open_snapshot_browser(self, shot):
        ok, message = self.backend.open_snapshot_browser(shot)
        if not ok:
            QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)
        else:
            self.state.remember_open(shot)

    def _resume(self, shot):
        from shellcore.versions import latest_version
        entry = latest_version(shot.get("comp_dir"))
        if entry is None:
            QtWidgets.QMessageBox.information(
                self, "Sleepy Shell", "This shot has no scripts yet.")
            return
        ok, message = self.backend.open_script(entry["path"])
        if ok:
            self.state.remember_open(shot)
        else:
            QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)

    def _recent_card(self, shot):
        """The mockup's home .card: full-bleed 96px thumb + cbody rows."""
        from shellui.widgets import ClickableFrame
        from shellui import theme
        card = ClickableFrame()
        card.setObjectName("ShellCard")
        card.setCursor(QtCore.Qt.PointingHandCursor)
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(Thumb(shot["name"], self._thumb_path(shot), (150, 96),
                               expanding=True, radius=0, font_px=19))
        body = QtWidgets.QVBoxLayout()
        body.setContentsMargins(11, 9, 11, 11)
        body.setSpacing(3)
        name_row = QtWidgets.QHBoxLayout()
        name = QtWidgets.QLabel(shot["name"])
        name.setStyleSheet("font-weight: 600; font-size: 12.5px; background: transparent;")
        name_row.addWidget(name)
        name_row.addStretch(1)
        name_row.addWidget(Chip(_status_label(shot), theme.status_color(shot.status)))
        body.addLayout(name_row)
        meta_row = QtWidgets.QHBoxLayout()
        project = QtWidgets.QLabel(shot.get("project_name", ""))
        project.setObjectName("ShellDim")
        project.setStyleSheet("font-size: 11px;")
        meta_row.addWidget(project)
        meta_row.addStretch(1)
        when = QtWidgets.QLabel(_ago_text(shot))
        when.setObjectName("ShellDim")
        when.setStyleSheet("font-size: 11px;")
        meta_row.addWidget(when)
        body.addLayout(meta_row)
        layout.addLayout(body)
        card._shell_shot = shot
        card.leftClicked.connect(lambda: self.openShot.emit(shot))
        return card

    def _open_folder(self, shot):
        ok, message = self.backend.open_folder(shot["path"])
        if not ok:
            QtWidgets.QMessageBox.information(self, "Sleepy Shell", message)

    def _thumb_path(self, shot):
        thumbs = self.state.shot_thumbnails(shot, limit=1)
        return thumbs[0] if thumbs else None


def kbd_search_pixmap():
    """Magnifier pixmap for the search box (painted at 2x for crispness)."""
    from shellui import icons
    return icons.icon("search").pixmap(28, 28)


def kbd_chip_pixmap(text="Ctrl+K"):
    """The mockup's .kbd hint chip as a pixmap at full readable size."""
    from shellui.widgets import kbd_pixmap
    return kbd_pixmap(text)


def _tracked(label, spacing):
    """Letter-spacing helper for kicker-style labels."""
    from SleepyCore.qt import QtGui
    font = label.font()
    font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, spacing)
    label.setFont(font)
    return label


def _script_label(shot):
    from shellcore.versions import latest_version
    entry = latest_version(shot.get("comp_dir"))
    if entry:
        return entry["name"]
    return shot["name"] + " (no scripts yet)"


def _status_label(shot):
    from shellcore.schema import STATUS_LABELS
    return STATUS_LABELS.get(shot.status, shot.status)


def _ago_text(shot):
    from shellcore.sessions import last_opened
    stamp = last_opened(shot.get("comp_dir"))
    if not stamp:
        return "never"
    days = (date.today() - date.fromtimestamp(stamp)).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return "{} days ago".format(days)


class ClickableChipLabel(QtWidgets.QLabel):
    """A chip-styled label that opens a shot on click."""

    clicked = QtCore.Signal()

    def __init__(self, text, parent=None):
        super(ClickableChipLabel, self).__init__(text, parent)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setStyleSheet(
            "QLabel { background: #26272a; color: #e6e6e6; border: 1px solid #3a3c40;"
            " border-radius: 9px; padding: 1px 9px; font-size: 11px; }"
            "QLabel:hover { border-color: #f0a043; color: #f0a043; }")

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super(ClickableChipLabel, self).mouseReleaseEvent(event)


def _stat_value(text, color=None, dim=False):
    label = QtWidgets.QLabel(text)
    label.setStyleSheet("font-weight: 600; font-size: 12.5px;{}".format(
        " color: {};".format(color) if color else
        (" color: #9a9ea6;" if dim else "")))
    return label


def _hours_text(seconds):
    hours = float(seconds or 0) / 3600.0
    if hours < 1:
        return "{}m".format(int(float(seconds or 0) // 60))
    return "{:.1f}h".format(hours)


def _thumb_tag(shot):
    project = shot.get("project_name") or ""
    return " · ".join(x for x in (project.split("_")[0].lower(), "comp") if x)
