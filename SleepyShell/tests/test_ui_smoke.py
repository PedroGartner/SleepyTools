"""Offscreen UI smoke test for Sleepy Shell (runs without Nuke).

Requires PySide6 or PySide2 on the running Python; skips otherwise.
Everything runs with QT_QPA_PLATFORM=offscreen and an isolated temp
prefs/cache/session location, so the user's real data is never touched.

    python tests/test_ui_smoke.py
"""

import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOL_DIR = os.path.dirname(_HERE)
_SUITE_PARENT = os.path.dirname(_TOOL_DIR)
for _path in (_TOOL_DIR, _SUITE_PARENT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from SleepyCore.qt import QtWidgets  # noqa: F401
    HAS_QT = True
except Exception:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6/PySide2 not available")
class TestUISmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sleepy_shell_ui_")
        # isolate every persisted file
        from shellui.session import reset_session
        reset_session()
        from shellcore import prefs as prefs_mod, scan as scan_mod, sessions, recents
        cls.prefs_mod = prefs_mod
        prefs_mod.PREFS_FILE = os.path.join(cls.tmp, "prefs.json")
        scan_mod.CACHE_FILE = os.path.join(cls.tmp, "cache.json")
        sessions.SESSIONS_FILE = os.path.join(cls.tmp, "sessions.json")
        recents.RECENTS_FILE = os.path.join(cls.tmp, "recents.json")
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

        # build a small real portfolio on disk
        from shellcore import ops
        root = os.path.join(cls.tmp, "Projects")
        os.makedirs(root)
        cls.project = ops.create_project(root, "ProjA", {"client": "ClientX"})
        cls.shot_dir, _ = ops.create_shot(cls.project, "sh001", {}, {"comp_template": ""})
        from shellcore.schema import save_shot
        save_shot(cls.shot_dir, {"due": "2026-10-06"})  # board shows due-filtered shots
        prefs = prefs_mod.load()
        prefs["watched_roots"] = [root]
        prefs_mod.save(prefs)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_main_window_builds_and_navigates(self):
        from shellui.session import get_session
        from shellui.mainwindow import MainWindow
        from shellui import theme
        state, backend = get_session()
        state.prefs = self.prefs_mod.load()
        theme.apply(self.app, state.prefs)
        window = MainWindow(state, backend)
        window.refresh(silent=True)
        self.assertGreaterEqual(len(state.projects), 1)
        self.assertGreaterEqual(len(state.shots), 1)

        # board shows the shot
        window.board_page.refresh_views()
        self.assertEqual(len(window.board_page._shots), 1)

        # view mode switching
        for mode in ("columns", "list", "gallery"):
            window.board_page.set_view_mode(mode)
            self.assertEqual(window.board_page.stack.currentIndex(),
                             {"columns": 0, "list": 1, "gallery": 2}[mode])

        # shot page builds for the scanned shot
        shot = state.shots[0]
        window.open_shot(shot)
        self.assertIs(window.pages.currentWidget(), window.shot_page)
        self.assertIsNotNone(window.shot_page.notes_edit)

        # status change writes through the core to disk
        window.shot_page._set_status("review")
        from shellcore.schema import load_shot
        loaded, _ = load_shot(shot["path"])
        self.assertEqual(loaded["status"], "review")

        # project settings page builds
        window.project_page.set_project(state.projects[0])
        self.assertIsNotNone(window.project_page.client_edit)
        window.project_page.client_edit.setText("OtherClient")
        window.project_page._save()
        from shellcore.schema import load_project
        config, _ = load_project(state.projects[0]["path"])
        self.assertEqual(config["client"], "OtherClient")

        # preferences load + save round-trip
        window.prefs_page.load()
        window.prefs_page.font_spin.setValue(13)
        window.prefs_page.save()
        self.assertEqual(self.prefs_mod.load()["font_size"], 13)

        window.close()

    def test_nuke_panel_builds_without_nuke(self):
        # no nuke module here: the panel must still construct and show
        # the "script not in a managed shot" empty state gracefully.
        from shellui.session import get_session
        from shellui.nukepanel import ShellPanel
        state, backend = get_session()
        panel = ShellPanel()
        self.assertIsNotNone(panel.state)
        panel._record_segment()  # must not raise without nuke
        panel.close()

    def test_screenshot(self):
        from shellui.session import get_session
        from shellui.mainwindow import MainWindow
        state, backend = get_session()
        window = MainWindow(state, backend)
        window.refresh(silent=True)
        window.resize(1280, 800)
        window.show()
        self.app.processEvents()
        pixmap = window.grab()
        out = os.path.join(self.tmp, "mainwindow.png")
        pixmap.save(out)
        window.close()
        self.assertTrue(os.path.isfile(out))


    def test_no_graphics_effects_anywhere(self):
        # QTBUG-31045: effects over styled subtrees silently knock out QSS
        # backgrounds (the transparent-window bug). None must ever exist.
        from shellui.session import get_session
        from shellui.mainwindow import MainWindow
        state, backend = get_session()
        window = MainWindow(state, backend)
        window.refresh(silent=True)
        affected = [w for w in window.findChildren(QtWidgets.QWidget)
                    if w.graphicsEffect() is not None]
        self.assertEqual(affected, [])
        window.close()

    def test_preferences_can_be_left_via_sidebar(self):
        from shellui.session import get_session
        from shellui.mainwindow import MainWindow
        state, backend = get_session()
        window = MainWindow(state, backend)
        window.refresh(silent=True)
        window._goto(window.prefs_page)
        self.assertIs(window.pages.currentWidget(), window.prefs_page)
        # the mockup's navigation is the app sidebar; it must always work
        window.home_button.click()
        self.assertIs(window.pages.currentWidget(), window.home_page)
        window._goto(window.prefs_page)
        window.board_button.click()
        self.assertIs(window.pages.currentWidget(), window.board_page)
        window.close()

    def test_docked_panel_carries_its_own_stylesheet(self):
        # inside Nuke no app stylesheet exists, so the panel applies the
        # Shell QSS to itself (the "transparent panel in Nuke" bug)
        from shellui.session import get_session
        from shellui.nukepanel import ShellPanel
        state, backend = get_session()
        panel = ShellPanel()
        sheet = panel.styleSheet()
        self.assertIn("#ShellPanel", sheet)
        self.assertIn("#ShellVersionBox", sheet)
        # dimmed rows are property-driven, not effect-driven
        from shellui.widgets import dim_effect
        row = QtWidgets.QFrame()
        dim_effect(row)
        self.assertTrue(row.property("dim") is True)
        self.assertIsNone(row.graphicsEffect())
        panel.close()


if __name__ == "__main__":
    unittest.main(verbosity=1)
