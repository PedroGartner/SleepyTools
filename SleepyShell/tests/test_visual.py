"""Visual regression tests: render the real UI offscreen and assert that
the stylesheet's colors actually reach the screen.

These tests exist because Qt style sheets fail SILENTLY: a wrong
objectName, an ancestor's bare "background: transparent" declaration
(ancestor precedence beats the app sheet), or a QGraphicsEffect over a
styled subtree (QTBUG-31045) all render black/transparent without any
error. Sampling painted pixels catches every one of those.

    python tests/test_visual.py
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
    from SleepyCore.qt import QtCore, QtWidgets  # noqa: F401
    HAS_QT = True
except Exception:
    HAS_QT = False

# mockup palette
WINDOW = (0x16, 0x17, 0x19)
SIDE = (0x19, 0x1A, 0x1C)
CHROME = (0x12, 0x13, 0x14)
BASE = (0x1E, 0x1F, 0x22)
ACCENT = (0xF0, 0xA0, 0x43)


def _close(color, expected, tol=6):
    return all(abs(color[i] - expected[i]) <= tol for i in range(3))


@unittest.skipUnless(HAS_QT, "PySide6/PySide2 not available")
class TestVisualFidelity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sleepy_shell_visual_")
        from shellui.session import reset_session
        reset_session()
        from shellcore import prefs as prefs_mod, scan as scan_mod
        from shellcore import sessions, recents, ops
        prefs_mod.PREFS_FILE = os.path.join(cls.tmp, "prefs.json")
        scan_mod.CACHE_FILE = os.path.join(cls.tmp, "cache.json")
        sessions.SESSIONS_FILE = os.path.join(cls.tmp, "sessions.json")
        recents.RECENTS_FILE = os.path.join(cls.tmp, "recents.json")
        root = os.path.join(cls.tmp, "Projects")
        os.makedirs(root)
        project = ops.create_project(root, "ProjA", {"client": "ClientX"})
        shot_dir, _ = ops.create_shot(project, "sh001", {}, {"comp_template": ""})
        from shellcore.schema import save_shot
        save_shot(shot_dir, {"due": "2026-10-06"})  # board shows due-filtered shots
        comp = os.path.join(shot_dir, "comp")
        with open(os.path.join(comp, "sh001_comp_v001.nk"), "w") as fh:
            fh.write("x\n")
        prefs = prefs_mod.load()
        prefs["watched_roots"] = [root]
        prefs_mod.save(prefs)

        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        from shellui.session import get_session
        from shellui import theme
        state, backend = get_session()
        state.prefs = prefs_mod.load()
        theme.apply(cls.app, state.prefs)
        from shellui.mainwindow import MainWindow
        cls.win = MainWindow(state, backend)
        cls.win.resize(1380, 820)
        cls.win.show()
        cls.app.processEvents()
        state.refresh(force=True)
        cls.app.processEvents()
        cls.img = None

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _dominant(self, widget):
        """Most frequent color inside ``widget``'s rect in the window grab.

        Robust against text glyphs and icon pixels: for buttons, cards and
        panels the stylesheet background dominates the rect.
        """
        self.app.processEvents()
        img = self.win.grab().toImage()
        top_left = widget.mapTo(self.win, QtCore.QPoint(0, 0))
        counts = {}
        step = 3 if widget.width() * widget.height() > 4000 else 1
        for y in range(2, widget.height() - 2, step):
            for x in range(2, widget.width() - 2, step):
                c = img.pixelColor(top_left.x() + x, top_left.y() + y)
                key = (c.red(), c.green(), c.blue())
                counts[key] = counts.get(key, 0) + 1
        if not counts:
            return (0, 0, 0)
        return max(counts.items(), key=lambda kv: kv[1])[0]

    def _assert_color(self, widget, expected, label, tol=6):
        got = self._dominant(widget)
        self.assertTrue(
            _close(got, expected, tol),
            "{}: expected #{:02x}{:02x}{:02x}, got #{:02x}{:02x}{:02x}{}".format(
                label, expected[0], expected[1], expected[2],
                got[0], got[1], got[2],
                " (widget not styled?)" if got == (0, 0, 0) else ""))

    # ------------------------------------------------------------------
    def test_sidebar_and_chrome(self):
        self.win._goto(self.win.home_page)
        self.app.processEvents()
        self._assert_color(self.win.findChild(QtWidgets.QFrame, "ShellSidebar"),
                           SIDE, "sidebar bg")
        self._assert_color(self.win.findChild(QtWidgets.QFrame, "ShellTitlebar"),
                           CHROME, "titlebar chrome")
        self._assert_color(self.win.findChild(QtWidgets.QFrame, "ShellStatusbar"),
                           CHROME, "statusbar chrome")
        self._assert_color(self.win.findChild(QtWidgets.QFrame, "ShellWindow"),
                           WINDOW, "window frame bg")

    def test_primary_button_is_accent(self):
        self.win._goto(self.win.home_page)
        self.app.processEvents()
        # the hero's Resume button carries property accent=true
        buttons = [b for b in self.win.home_page.findChildren(QtWidgets.QPushButton)
                   if b.property("accent") is True and b.isVisible()]
        self.assertTrue(buttons, "no visible accent button on home")
        self._assert_color(buttons[0], ACCENT, "primary button bg", tol=8)

    def test_board_group_and_seg_checked(self):
        self.win._goto(self.win.board_page)
        self.win.board_page.set_view_mode("list")
        self.app.processEvents()
        groups = [f for f in self.win.board_page.findChildren(QtWidgets.QFrame)
                  if f.objectName() == "ShellGroup" and f.isVisible()]
        self.assertTrue(groups, "no visible list group")
        self._assert_color(groups[0], SIDE, "list group bg")

        checked = [b for b in self.win.board_page.view_buttons.values()
                   if b.isChecked()]
        self.assertTrue(checked, "no checked view button")
        self._assert_color(checked[0], ACCENT, "seg checked bg", tol=8)

    def test_hero_card_base(self):
        self.win._goto(self.win.home_page)
        self.app.processEvents()
        heroes = [f for f in self.win.home_page.findChildren(QtWidgets.QFrame)
                  if f.objectName() == "ShellHero" and f.isVisible()]
        if heroes:  # only when a resume card exists
            self._assert_color(heroes[0], BASE, "hero bg")

    def test_statusbar_hint_updates_per_page(self):
        if self.win.state.projects:
            self.win.project_page.set_project(self.win.state.projects[0])
        self.win._goto(self.win.project_page)
        if self.win.state.projects:
            self.assertIn("project.json", self.win._hint_label.text())
        self.win._goto(self.win.board_page)
        self.assertIn("Showing", self.win._hint_label.text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
