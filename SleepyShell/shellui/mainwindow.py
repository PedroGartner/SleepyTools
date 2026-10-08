"""The Sleepy Shell main window: sidebar navigation and the pages.

Chrome follows the mockup: #121314 titlebar strip (logo, name, dim
screen name), 250px #191a1c sidebar with accent-bordered active rows,
and a #121314 status strip whose text changes per screen like the
mockup's per-screen statusbars.
"""

import os

from SleepyCore.qt import QtCore, QtGui, QtWidgets

from shellui import theme
from shellui.page_board import BoardPage
from shellui.page_home import HomePage
from shellui.page_settings import PreferencesPage, ProjectSettingsPage
from shellui.page_shot import ShotPage
from shellui.widgets import Chip, clear_layout, face_logo_pixmap, styled


class MainWindow(QtWidgets.QMainWindow):
    """The mockup's floating app window: frameless, rounded, custom chrome.

    Only the standalone launcher uses this class; the docked Nuke panel
    (shellui.nukepanel) keeps Nuke's own pane chrome, since a docked tab
    cannot be frameless.
    """

    def __init__(self, state, backend, parent=None):
        super(MainWindow, self).__init__(parent)
        self.state = state
        self.backend = backend
        self._standalone = parent is None
        self.setWindowTitle("Sleepy Shell")
        self.resize(1280, 800)
        if self._standalone:
            # Mockup-style floating card: frameless with custom chrome.
            # Deliberately OPAQUE — WA_TranslucentBackground made the whole
            # window see-through on some Windows compositors/DPI setups
            # (every app-stylesheet background silently missing) while
            # offscreen renders looked fine. Rounded corners come from a
            # window mask instead of an alpha surface; an opaque window
            # cannot fail this way.
            self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)

        central = styled(QtWidgets.QWidget())
        # NOTE: never setStyleSheet("background: transparent") on the central
        # widget — bare declarations cascade to every descendant at ancestor
        # precedence and knock out the app stylesheet's backgrounds (the
        # window/sidebar rendered transparent/black because of exactly that).
        self.setCentralWidget(central)
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        window_frame = QtWidgets.QFrame()
        window_frame.setObjectName("ShellWindow")
        self._window_frame = window_frame
        outer.addWidget(window_frame, 1)
        frame_layout = QtWidgets.QVBoxLayout(window_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        frame_layout.addWidget(self._build_titlebar())
        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        frame_layout.addLayout(body, 1)

        body.addWidget(self._build_sidebar())

        self.pages = QtWidgets.QStackedWidget()
        self.home_page = HomePage(state, backend)
        self.board_page = BoardPage(state, backend)
        self.shot_page = ShotPage(state, backend)
        self.project_page = ProjectSettingsPage(state)
        self.prefs_page = PreferencesPage(state)
        for page in (self.home_page, self.board_page, self.shot_page,
                     self.project_page, self.prefs_page):
            self.pages.addWidget(page)
        body.addWidget(self.pages, 1)

        frame_layout.addWidget(self._build_footer())
        self._update_status()

        # wiring
        self.home_page.openShot.connect(self.open_shot)
        self.home_page.gotoBoard.connect(lambda: self._goto(self.board_page))
        self.board_page.openShot.connect(self.open_shot)
        self.board_page.shotChanged.connect(self._on_data_changed)
        self.shot_page.shotChanged.connect(self._on_data_changed)
        self.project_page.backToBoard.connect(lambda: self._goto(self.board_page))
        self.project_page.projectChanged.connect(self._on_data_changed)
        self.state.projectsChanged.connect(self._on_projects_changed)

        self.refresh(silent=True)
        if self._standalone:
            self._apply_round_mask()

    # ------------------------------------------------------------------
    def _apply_round_mask(self):
        """Rounded corners for the opaque frameless window.

        The mask clips the native window to the mockup's 8px radius
        without WA_TranslucentBackground (see __init__ for why the alpha
        surface is off-limits). Re-applied on every resize.
        """
        if self._window_frame is None:
            return
        bitmap = QtGui.QBitmap(self.size())
        bitmap.fill(QtCore.Qt.color0)
        painter = QtGui.QPainter(bitmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(QtCore.Qt.color1)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 8, 8)
        painter.end()
        self.setMask(QtGui.QRegion(bitmap))

    def resizeEvent(self, event):
        if self._standalone:
            self._apply_round_mask()
        super(MainWindow, self).resizeEvent(event)

    # ------------------------------------------------------------------
    def _build_titlebar(self):
        """The mockup's app header: logo, name, screen name, window dots."""
        from shellui.widgets import ShellTitleBar
        bar = ShellTitleBar(self.showMinimized, self._toggle_maximize, self.close,
                            self._standalone)
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)
        logo = QtWidgets.QLabel()
        logo.setFixedSize(21, 21)
        logo.setAlignment(QtCore.Qt.AlignCenter)
        face = face_logo_pixmap(21)
        if face is not None:
            logo.setPixmap(face)
        else:
            # icon file missing: keep the lettered accent tile
            logo.setText("G")
            logo.setStyleSheet("background: {}; color: {}; font-weight: 700;"
                               " font-size: 12.5px; border-radius: 3px;".format(
                                   self.state.prefs.get("accent", "#f0a043"),
                                   theme.DARK["window"]))
        layout.addWidget(logo)
        name = QtWidgets.QLabel("Sleepy Shell")
        name.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(name)
        self.screen_label = QtWidgets.QLabel("project manager — launcher")
        self.screen_label.setStyleSheet("color: {}; font-size: 11px;".format(
            theme.DARK["dim"]))
        layout.addWidget(self.screen_label)
        layout.addStretch(1)
        if self._standalone:
            for glyph, callback, is_close in (
                    ("\u2014", self.showMinimized, False),
                    ("\u25a1", self._toggle_maximize, False),
                    ("\u2715", self.close, True)):
                button = QtWidgets.QPushButton(glyph)
                button.setObjectName("ShellWinButton")
                button.setProperty("close", is_close)
                button.setCursor(QtCore.Qt.ArrowCursor)
                button.setFixedSize(38, 26)
                button.clicked.connect(callback)
                layout.addWidget(button)
        return bar

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _build_footer(self):
        """The mockup's status strip: index counts, cache info, page hint."""
        footer = QtWidgets.QFrame()
        footer.setObjectName("ShellStatusbar")
        footer.setFixedHeight(30)
        layout = QtWidgets.QHBoxLayout(footer)
        layout.setContentsMargins(14, 4, 10, 4)
        layout.setSpacing(18)
        self._status_label = QtWidgets.QLabel("")
        layout.addWidget(self._status_label)
        self._cache_label = QtWidgets.QLabel("")
        layout.addWidget(self._cache_label)
        layout.addStretch(1)
        self._hint_label = QtWidgets.QLabel("")
        layout.addWidget(self._hint_label)
        version = QtWidgets.QLabel("Sleepy Shell v1.0")
        layout.addWidget(version)
        if self._standalone:
            grip = QtWidgets.QSizeGrip(footer)
            grip.setFixedSize(16, 16)
            layout.addWidget(grip, 0, QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight)
        return footer

    def _build_sidebar(self):
        from shellui.widgets import spaced_header
        sidebar = QtWidgets.QFrame()
        sidebar.setObjectName("ShellSidebar")
        sidebar.setFixedWidth(250)
        layout = QtWidgets.QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 10, 0, 12)
        layout.setSpacing(0)

        self.home_button = self._nav_button("Home", "home")
        self.board_button = self._nav_button("Board", "columns")
        # the sidebar IS the app's navigation: these must always answer,
        # otherwise pages like Preferences are a one-way door
        self.home_button.clicked.connect(lambda: self._goto(self.home_page))
        self.board_button.clicked.connect(lambda: self._goto(self.board_page))
        layout.addWidget(self.home_button)
        layout.addWidget(self.board_button)

        projects_caption = spaced_header("Projects", size=10, spacing=1.2)
        projects_caption.setContentsMargins(16, 14, 16, 8)
        projects_caption.setStyleSheet("color: {};".format(theme.DARK["dim"]))
        layout.addWidget(projects_caption)
        self.project_buttons_layout = QtWidgets.QVBoxLayout()
        self.project_buttons_layout.setSpacing(0)
        layout.addLayout(self.project_buttons_layout)
        layout.addStretch(1)

        actions = QtWidgets.QVBoxLayout()
        actions.setContentsMargins(12, 0, 12, 0)
        actions.setSpacing(8)
        new_project = QtWidgets.QPushButton("+ New Project")
        new_project.clicked.connect(self._new_project)
        actions.addWidget(new_project)
        adopt_button = QtWidgets.QPushButton("Adopt discovered shots...")
        adopt_button.clicked.connect(self._adopt)
        actions.addWidget(adopt_button)
        prefs_button = QtWidgets.QPushButton("Preferences")
        prefs_button.clicked.connect(lambda: self._goto(self.prefs_page))
        actions.addWidget(prefs_button)
        layout.addLayout(actions)

        self.roots_box = QtWidgets.QFrame()
        self.roots_box.setObjectName("ShellRoots")
        roots_wrap = QtWidgets.QHBoxLayout()
        roots_wrap.setContentsMargins(12, 12, 12, 0)
        roots_wrap.addWidget(self.roots_box)
        layout.addLayout(roots_wrap)
        self.roots_box_layout = QtWidgets.QVBoxLayout(self.roots_box)
        self.roots_box_layout.setContentsMargins(11, 9, 11, 9)
        self.roots_box_layout.setSpacing(4)
        self._fill_roots_box()
        return sidebar

    def _fill_roots_box(self):
        """The mockup's WATCHED ROOTS box: ✓ ok / ⚠ offline rows."""
        from shellui.widgets import spaced_header
        box_layout = self.roots_box_layout
        clear_layout(box_layout)
        caption = spaced_header("Watched roots", size=10, spacing=1.0)
        caption.setStyleSheet("color: {};".format(theme.DARK["text"]))
        box_layout.addWidget(caption)
        roots = self.state.prefs.get("watched_roots", [])
        if not roots:
            empty = QtWidgets.QLabel("none — add one in Preferences")
            empty.setObjectName("ShellDim")
            empty.setWordWrap(True)
            box_layout.addWidget(empty)
            return
        for root in roots:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(6)
            state_text = self.state.root_states.get(os.path.normpath(root), "ok")
            mark, color = (("\u2713", theme.STATUS_COLORS["approved"]) if state_text == "ok"
                           else ("\u26a0", theme.STATUS_COLORS["hold"]))
            mark_label = QtWidgets.QLabel(mark)
            mark_label.setStyleSheet("color: {}; font-size: 11px;".format(color))
            row.addWidget(mark_label)
            name = QtWidgets.QLabel(root)
            name.setStyleSheet("font-size: 11px;")
            row.addWidget(name, 1)
            if state_text != "ok":
                warn = QtWidgets.QLabel("offline")
                warn.setObjectName("ShellDim")
                row.addWidget(warn)
            box_layout.addLayout(row)

    def _nav_button(self, label, icon_name):
        from shellui import icons
        button = QtWidgets.QPushButton(" " + label)
        button.setObjectName("ShellNavButton")
        button.setIcon(icons.icon(icon_name))
        button.setCheckable(True)
        button.setCursor(QtCore.Qt.PointingHandCursor)
        return button

    # ------------------------------------------------------------------
    def _goto(self, page):
        self.pages.setCurrentWidget(page)
        self.home_button.setChecked(page is self.home_page)
        self.board_button.setChecked(page is self.board_page)
        subs = {id(self.home_page): "project manager — launcher",
                id(self.board_page): "the board",
                id(self.shot_page): "shot detail",
                id(self.project_page): "project settings",
                id(self.prefs_page): "preferences — global"}
        self.screen_label.setText(subs.get(id(page), ""))
        self._hint_label.setText(getattr(page, "status_hint", lambda: "")())
        if page is self.home_page:
            page.refresh()
        if page is self.prefs_page:
            page.load()

    def refresh(self, silent=False):
        self.state.refresh(force=not silent)
        if self.pages.currentWidget() is self.home_page:
            self.home_page.refresh()
        self._update_status()

    def _on_projects_changed(self):
        self._fill_project_buttons()
        self.board_page.reload_projects()
        self._update_status()
        current = self.pages.currentWidget()
        if current is self.home_page:
            self.home_page.refresh()

    def _on_data_changed(self):
        self.state.refresh(force=True)
        self.board_page.refresh_views()
        self._update_status()

    def _fill_project_buttons(self):
        from shellui.widgets import ClickableFrame, clear_layout
        clear_layout(self.project_buttons_layout)
        accent = self.state.prefs.get("accent", "#f0a043")
        for project in self.state.projects:
            holder = ClickableFrame()
            holder.setCursor(QtCore.Qt.PointingHandCursor)
            row = QtWidgets.QHBoxLayout()
            row.setContentsMargins(16, 9, 14, 9)
            row.setSpacing(8)
            color = project.get("color") or ("#f0a043" if project["managed"] else "#8a8f98")
            dot = QtWidgets.QLabel()
            dot.setFixedSize(7, 7)
            dot.setStyleSheet("background: {}; border-radius: 3px;".format(color))
            row.addWidget(dot)
            text_col = QtWidgets.QVBoxLayout()
            text_col.setSpacing(2)
            name = QtWidgets.QLabel(project["name"])
            name.setStyleSheet("background: transparent; font-weight: 600;"
                               " font-size: 12.5px;")
            text_col.addWidget(name)
            shots = [s for s in self.state.shots
                     if s.get("project_path") == project["path"]]
            due = sum(1 for s in shots if (s.get("config") or {}).get("due"))
            bits = ["{} shot{}".format(len(shots), "" if len(shots) == 1 else "s")]
            if due:
                bits.append("{} due".format(due))
            if not project["managed"]:
                bits.append("discovered")
            sub = QtWidgets.QLabel(" · ".join(bits))
            sub.setStyleSheet("background: transparent; color: #9a9ea6; font-size: 11px;")
            text_col.addWidget(sub)
            row.addLayout(text_col, 1)
            if not project["managed"]:
                row.addWidget(Chip("disc.", "#8a8f98", dim=True))
            holder.setLayout(row)
            holder.setStyleSheet(
                "ClickableFrame {{ border-left: 2px solid transparent; }}"
                "ClickableFrame:hover {{ background: #1f2022; }}"
                "ClickableFrame[active=\"true\"] {{ background: #222326;"
                " border-left: 2px solid {}; }}".format(accent))
            active = self.state.current_project == project["path"]
            holder.setProperty("active", active)
            holder._shell_project = project
            holder.leftClicked.connect(
                lambda p=project: self._select_project(p))
            holder.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            holder.customContextMenuRequested.connect(
                lambda pos, p=project, w=holder: self._project_menu(p, w, pos))
            self.project_buttons_layout.addWidget(holder)
        # keep the active highlight in sync on later refreshes
        style = self.style()
        for i in range(self.project_buttons_layout.count()):
            item = self.project_buttons_layout.itemAt(i)
            if item.widget() is not None:
                style.unpolish(item.widget())
                style.polish(item.widget())

    def _project_menu(self, project, holder, pos):
        menu = QtWidgets.QMenu(self)
        menu.addAction("Open Board", lambda: self._select_project(project))
        menu.addAction("Project settings...",
                       lambda: self.open_project_settings(project))
        menu.exec(holder.mapToGlobal(pos))

    def open_project_settings(self, project):
        self.project_page.set_project(project)
        self._goto(self.project_page)

    def _select_project(self, project):
        self.state.current_project = project["path"]
        self.board_page.reload_projects()
        self._goto(self.board_page)

    def _update_status(self):
        count_projects = len(self.state.projects)
        count_shots = len(self.state.shots)
        offline = [root for root, state in self.state.root_states.items() if state != "ok"]
        text = "Index: <b>{} projects · {} shots</b>".format(count_projects, count_shots)
        if self.state.from_cache:
            text += " (cached)"
        if offline:
            text += " · {} offline".format(len(offline))
        self._status_label.setText(text)
        self._cache_label.setText(self._cache_text())
        self._fill_roots_box()

    def _cache_text(self):
        from shellcore import scan as scan_mod
        path = getattr(scan_mod, "CACHE_FILE", None)
        try:
            stat = os.stat(path)
            size_mb = stat.st_size / 1048576.0
            if size_mb < 0.1:
                size = "{} KB".format(max(1, int(stat.st_size / 1024)))
            else:
                size = "{:.0f} MB".format(size_mb)
            import datetime
            updated = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%H:%M")
            return "Cache <b>{}</b> · updated {}".format(size, updated)
        except (OSError, TypeError, ValueError):
            return ""

    # ------------------------------------------------------------------
    def open_shot(self, shot):
        self.state.remember_open(shot)
        self.shot_page.set_shot(shot)
        self._goto(self.shot_page)

    def _new_project(self):
        from shellui.dialogs import NewProjectDialog
        dialog = NewProjectDialog(self.state, self)
        if dialog.exec() and dialog.created_path:
            self.state.refresh(force=True)
            self._goto(self.board_page)

    def _adopt(self):
        from shellui.dialogs import AdoptDialog
        dialog = AdoptDialog(self.state, self)
        if dialog.exec() and dialog.adopted:
            self.state.refresh(force=True)

    def new_shot_for(self, project):
        from shellui.dialogs import NewShotDialog
        dialog = NewShotDialog(project, self.state, self)
        if dialog.exec() and dialog.created_path:
            self.state.refresh(force=True)
            for shot in self.state.shots:
                if shot["path"] == dialog.created_path:
                    self.open_shot(shot)
                    break
