"""Offscreen smoke tests for Version 2 (production) and Version 3 (Nuke) UIs.

Shared rules: isolated temp prefs/cache, offscreen platform, no Nuke.
Also verifies the two variants share one session (same AppState) and
that all three versions read identical project data.
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


def _make_portfolio(tmp):
    """Create a small portfolio and point isolated prefs at it."""
    from shellcore import ops, prefs as prefs_mod
    prefs_mod.PREFS_FILE = os.path.join(tmp, "prefs.json")
    from shellcore import scan as scan_mod, sessions, recents
    scan_mod.CACHE_FILE = os.path.join(tmp, "cache.json")
    sessions.SESSIONS_FILE = os.path.join(tmp, "sessions.json")
    recents.RECENTS_FILE = os.path.join(tmp, "recents.json")
    root = os.path.join(tmp, "Projects")
    os.makedirs(root)
    project = ops.create_project(root, "ProjA", {"client": "ClientX"})
    for name in ("sh010", "sh020", "sh110"):
        shot_dir, _ = ops.create_shot(project, name, {}, {"comp_template": ""})
        from shellcore.schema import save_shot
        save_shot(shot_dir, {"due": "2026-10-06"})  # board shows due-filtered shots
    prefs = prefs_mod.load()
    prefs["watched_roots"] = [root]
    prefs_mod.save(prefs)
    return project


@unittest.skipUnless(HAS_QT, "PySide6/PySide2 not available")
class TestVariantsSharedSession(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sleepy_shell_variants_")
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        from shellui.session import reset_session
        reset_session()
        _make_portfolio(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_entry_modules_import_without_nuke(self):
        for module in ("sleepy_shell", "sleepy_shell_production", "sleepy_shell_nuke"):
            __import__(module)
        import sleepy_shell, sleepy_shell_production, sleepy_shell_nuke  # noqa: F401
        # distinct pane identities
        self.assertNotEqual(sleepy_shell.PANEL_ID,
                            sleepy_shell_production.PANEL_ID)
        self.assertNotEqual(sleepy_shell.PANEL_ID,
                            sleepy_shell_nuke.PANEL_ID)
        self.assertNotEqual(sleepy_shell_production.PANEL_ID,
                            sleepy_shell_nuke.PANEL_ID)

    def test_shared_session_same_data(self):
        from shellui.session import get_session
        from shellui_production.production_widget import ProductionWidget
        from shellui_nuke.nuke_pane import NukePaneWidget
        from shellui.mainwindow import MainWindow
        state, backend = get_session()
        state.refresh(force=True)
        baseline = sorted(s["path"] for s in state.shots)
        v1 = MainWindow(state, backend)
        v2 = ProductionWidget(state, backend)
        v3 = NukePaneWidget(state, backend)
        # all three frontsends see the same shots through the shared session
        self.assertEqual(baseline, sorted(s["path"] for s in v1.state.shots))
        self.assertEqual(baseline, sorted(s["path"] for s in v2.state.shots))
        self.assertEqual(baseline, sorted(s["path"] for s in v3.state.shots))
        self.assertIs(state, get_session()[0])
        v1.close()
        v2.close()
        v3.close()

    def test_version_up_honors_project_naming_override(self):
        # project_config now travels on every shot item, so a project-level
        # script_pattern drives Version Up instead of being ignored
        from shellui.session import get_session
        from shellcore.schema import save_project
        state, backend = get_session()
        state.refresh(force=True)
        project = state.projects[0]
        save_project(project["path"], {"script_pattern": "{shot}_anim_v###.nk"})
        state.refresh(force=True)
        shot = state.shots[0]
        comp = shot.get("comp_dir")
        self.assertTrue(comp and os.path.isdir(comp))
        with open(os.path.join(comp, shot["name"] + "_anim_v001.nk"), "w") as fh:
            fh.write("# test\n")
        new_path, message = backend.version_up(shot)
        self.assertIsNotNone(new_path, message)
        self.assertTrue(os.path.basename(new_path).endswith("_anim_v002.nk"),
                        os.path.basename(new_path))

    def test_variant_status_change_visible_in_all(self):
        from shellui.session import get_session
        from shellui_production.production_widget import ProductionWidget
        from shellui_nuke.nuke_pane import NukePaneWidget
        from shellcore.schema import load_shot
        state, backend = get_session()
        state.refresh(force=True)
        v2 = ProductionWidget(state, backend)
        v3 = NukePaneWidget(state, backend)
        shot = state.shots[0]
        # status change through V2
        v2._set_status(shot, "hold")
        loaded, _ = load_shot(shot["path"])
        self.assertEqual(loaded["status"], "hold")
        # same data visible through V3's shared state
        v3_shot = v3.state.shot_by_path(shot["path"])
        self.assertEqual(v3_shot.status, "hold")
        # and through a fresh read (no migration, same shot.json)
        loaded2, _ = load_shot(shot["path"])
        self.assertEqual(loaded2["status"], "hold")
        v2.close()
        v3.close()


@unittest.skipUnless(HAS_QT, "PySide6/PySide2 not available")
class TestProductionWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sleepy_shell_v2_")
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        from shellui.session import reset_session
        reset_session()
        _make_portfolio(cls.tmp)
        from shellui.session import get_session
        cls.state, cls.backend = get_session()
        cls.state.refresh(force=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_tree_table_inspector(self):
        from shellui_production.production_widget import ProductionWidget
        widget = ProductionWidget(self.state, self.backend)
        widget.reload()
        # tree: one project, sequences derived (SH000 x2 + SH100 x1)
        top = widget.tree.topLevelItemCount()
        self.assertEqual(top, 1)
        project_item = widget.tree.topLevelItem(0)
        self.assertEqual(project_item.childCount(), 2)
        # table shows all three shots
        self.assertEqual(widget.table.topLevelItemCount(), 3)
        # selecting a row fills the inspector
        widget.table.setCurrentItem(widget.table.topLevelItem(0))
        self.assertIsNotNone(widget.inspector.shot)
        # search filters the table
        widget.search_edit.setText("sh110")
        widget.refresh_table()
        self.assertEqual(widget.table.topLevelItemCount(), 1)
        widget.search_edit.setText("")
        widget.close()

    def test_status_write_through(self):
        from shellui_production.production_widget import ProductionWidget
        from shellcore.schema import load_shot
        widget = ProductionWidget(self.state, self.backend)
        widget.reload()
        shot = self.state.shots[0]
        widget._set_status(shot, "review")
        loaded, _ = load_shot(shot["path"])
        self.assertEqual(loaded["status"], "review")
        widget.close()


@unittest.skipUnless(HAS_QT, "PySide6/PySide2 not available")
class TestNukePaneWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sleepy_shell_v3_")
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        from shellui.session import reset_session
        reset_session()
        _make_portfolio(cls.tmp)
        from shellui.session import get_session
        cls.state, cls.backend = get_session()
        cls.state.refresh(force=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_bins_and_editor(self):
        from shellui_nuke.nuke_pane import NukePaneWidget
        widget = NukePaneWidget(self.state, self.backend)
        widget.reload()
        self.assertEqual(widget.bins.topLevelItemCount(), 1)
        project_item = widget.bins.topLevelItem(0)
        self.assertEqual(project_item.childCount(), 3)
        # selecting a shot fills the editor
        widget.bins.setCurrentItem(project_item.child(0))
        self.assertIsNotNone(widget.shot)
        self.assertTrue(widget.editor_header.text().startswith("sh"))
        # versions list shows the no-scripts empty state
        self.assertEqual(widget.versions_list.count(), 1)
        widget.close()

    def test_meta_save(self):
        from shellui_nuke.nuke_pane import NukePaneWidget
        from shellcore.schema import load_shot
        widget = NukePaneWidget(self.state, self.backend)
        widget.reload()
        widget.bins.setCurrentItem(widget.bins.topLevelItem(0).child(0))
        widget.tags_edit.setText("beauty, key")
        widget._save_meta()
        loaded, _ = load_shot(widget.shot["path"])
        self.assertEqual(loaded["tags"], ["beauty", "key"])
        widget.close()


if __name__ == "__main__":
    unittest.main(verbosity=1)
