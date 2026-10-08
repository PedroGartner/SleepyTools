"""Standalone test for the Sleepy Shell core engine.

Run with any plain Python 3 from anywhere:
    python SleepyShell/tests/test_core.py
No Nuke, no Qt. Uses temp folders for every filesystem write.
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOL_DIR = os.path.dirname(_HERE)
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)

from shellcore import (launch as launch_mod, naming, ops, prefs as prefs_mod,
                       scan, schema, search, sessions, versions)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sleepy_shell_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def touch_nk(self, folder, name, text="# test\n"):
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path


def make_project(root, name="ProjA", shots=("sh001", "sh002"), manage=True, project_config=None):
    project = os.path.join(root, name)
    shots_dir = os.path.join(project, "shots")
    os.makedirs(shots_dir)
    config = dict(schema.PROJECT_DEFAULTS)
    if project_config:
        config.update(project_config)
    schema.save_project(project, config)
    for shot in shots:
        shot_dir = os.path.join(shots_dir, shot)
        os.makedirs(os.path.join(shot_dir, "comp"))
        if manage:
            schema.save_shot(shot_dir, {"status": schema.STATUS_WIP})
    return project


class TestSchema(Base):
    def test_shot_roundtrip(self):
        shot_dir = os.path.join(self.tmp, "sh010")
        os.makedirs(shot_dir)
        saved = schema.save_shot(shot_dir, {"status": "review", "due": "2026-10-05",
                                            "priority": 2, "tags": ["beauty"], "notes": "hi"})
        self.assertEqual(saved["status"], "review")
        loaded, err = schema.load_shot(shot_dir)
        self.assertIsNone(err)
        self.assertEqual(loaded["due"], "2026-10-05")
        self.assertEqual(loaded["format"], schema.FORMAT_SHOT)

    def test_unknown_fields_preserved(self):
        shot_dir = os.path.join(self.tmp, "sh011")
        os.makedirs(shot_dir)
        schema.save_shot(shot_dir, {"status": "wip", "future_thing": {"a": 1}})
        loaded, _ = schema.load_shot(shot_dir)
        self.assertEqual(loaded["future_thing"], {"a": 1})
        schema.save_shot(shot_dir, {"status": "hold"})
        loaded, _ = schema.load_shot(shot_dir)
        self.assertEqual(loaded["future_thing"], {"a": 1})

    def test_bad_types_fall_back(self):
        shot_dir = os.path.join(self.tmp, "sh012")
        os.makedirs(shot_dir)
        with open(os.path.join(shot_dir, "shot.json"), "w") as fh:
            json.dump({"status": 42, "tags": "nope", "priority": "lots", "due": 7}, fh)
        loaded, err = schema.load_shot(shot_dir)
        self.assertIsNone(err)
        self.assertEqual(loaded["status"], schema.SHOT_DEFAULTS["status"])
        self.assertEqual(loaded["tags"], [])
        self.assertIsNone(loaded["priority"])

    def test_malformed_json_returns_defaults_with_error(self):
        shot_dir = os.path.join(self.tmp, "sh013")
        os.makedirs(shot_dir)
        with open(os.path.join(shot_dir, "shot.json"), "w") as fh:
            fh.write("{not json")
        loaded, err = schema.load_shot(shot_dir)
        self.assertEqual(loaded, schema.SHOT_DEFAULTS)
        self.assertEqual(err, "unreadable shot.json")

    def test_missing_file_no_error(self):
        loaded, err = schema.load_shot(os.path.join(self.tmp, "nothing"))
        self.assertEqual(loaded, schema.SHOT_DEFAULTS)
        self.assertIsNone(err)

    def test_project_roundtrip(self):
        project = make_project(self.tmp, project_config={"client": "ClientX", "fps": 30})
        loaded, err = schema.load_project(project)
        self.assertIsNone(err)
        self.assertEqual(loaded["client"], "ClientX")
        self.assertEqual(loaded["fps"], 30)


class TestNaming(Base):
    def test_expand_shot_name(self):
        self.assertEqual(naming.expand_shot_name("sh###", 35), "sh035")
        self.assertEqual(naming.expand_shot_name("sh###", 7), "sh007")
        self.assertEqual(naming.expand_shot_name("ep1_sh###", 123), "ep1_sh123")
        self.assertEqual(naming.expand_shot_name("shot_", 5), "shot_5")

    def test_parse_and_next(self):
        self.assertEqual(naming.parse_shot_number("sh012", "sh###"), 12)
        self.assertIsNone(naming.parse_shot_number("bg_comp", "sh###"))
        self.assertEqual(naming.next_shot_name([], "sh###"), "sh001")
        folder = os.path.join(self.tmp, "shots")
        os.makedirs(folder)
        os.makedirs(os.path.join(folder, "sh001"))
        os.makedirs(os.path.join(folder, "sh002"))
        self.assertEqual(naming.next_shot_name(folder, "sh###"), "sh003")

    def test_version_parsing(self):
        self.assertEqual(naming.parse_version_number("sh035_comp_v012.nk"), 12)
        self.assertIsNone(naming.parse_version_number("plate.nk"))
        self.assertEqual(naming.version_base("sh035_comp_v012.nk"), "sh035_comp")
        self.assertEqual(naming.script_name("{shot}_comp_v###.nk", "sh035", 3), "sh035_comp_v003.nk")

    def test_next_version_file(self):
        comp = os.path.join(self.tmp, "comp")
        os.makedirs(comp)
        self.touch_nk(comp, "sh035_comp_v001.nk")
        self.touch_nk(comp, "sh035_comp_v004.nk")
        self.assertEqual(naming.next_version_file(comp, "{shot}_comp_v###.nk", "sh035"),
                         "sh035_comp_v005.nk")

    def test_sanitize(self):
        self.assertEqual(naming.sanitize_name('bad:name*"x'), "bad_name__x")


class TestScan(Base):
    def test_managed_and_discovered(self):
        managed = make_project(self.tmp, "ManagedProj", shots=("sh010",))
        discovered = os.path.join(self.tmp, "ClientStuff")
        os.makedirs(os.path.join(discovered, "sh020", "comp"))
        self.touch_nk(os.path.join(discovered, "sh020", "comp"), "sh020_comp_v001.nk")
        unrelated = os.path.join(self.tmp, "NotAProject")
        os.makedirs(unrelated)

        projects, error = scan.find_projects(self.tmp)
        self.assertIsNone(error)
        names = {p["name"]: p for p in projects}
        self.assertIn("ManagedProj", names)
        self.assertIn("ClientStuff", names)
        self.assertNotIn("NotAProject", names)
        self.assertTrue(names["ManagedProj"]["managed"])
        self.assertFalse(names["ClientStuff"]["managed"])

        shots = scan.find_shots(managed)
        self.assertEqual([s["name"] for s in shots], ["sh010"])
        self.assertTrue(shots[0]["managed"])
        shots = scan.find_shots(discovered)
        self.assertEqual([s["name"] for s in shots], ["sh020"])
        self.assertFalse(shots[0]["managed"])

    def test_offline_root(self):
        projects, states = scan.scan_roots([os.path.join(self.tmp, "does_not_exist")])
        self.assertEqual(projects, [])
        self.assertEqual(list(states.values())[0], "offline")

    def test_cache_roundtrip(self):
        make_project(self.tmp, "ProjA", shots=())
        old_cache_file = scan.CACHE_FILE
        scan.CACHE_FILE = os.path.join(self.tmp, "cache.json")
        try:
            prefs = {"watched_roots": [self.tmp], "cache_ttl_seconds": 300}
            projects, states, from_cache = scan.cached_scan(prefs, force=True)
            self.assertFalse(from_cache)
            self.assertEqual(len(projects), 1)
            projects, states, from_cache = scan.cached_scan(prefs)
            self.assertTrue(from_cache)
            self.assertEqual(len(projects), 1)
        finally:
            scan.CACHE_FILE = old_cache_file

    def test_container_folder(self):
        project = os.path.join(self.tmp, "ProjB")
        os.makedirs(os.path.join(project, "shots", "seq010", "sh010", "comp"))
        self.touch_nk(os.path.join(project, "shots", "seq010", "sh010", "comp"), "sh010_comp_v001.nk")
        projects, _ = scan.find_projects(self.tmp)
        self.assertEqual([p["name"] for p in projects], ["ProjB"])
        shots = scan.find_shots(project)
        self.assertEqual([s["name"] for s in shots], ["sh010"])


class TestVersions(Base):
    def test_list_versions_sorted(self):
        comp = os.path.join(self.tmp, "comp")
        self.touch_nk(comp, "sh010_comp_v002.nk")
        self.touch_nk(comp, "sh010_comp_v010.nk")
        self.touch_nk(comp, "sh010_comp_v001.nk")
        self.touch_nk(comp, "thumbnail.jpg")
        entries = versions.list_versions(comp)
        self.assertEqual([e["number"] for e in entries], [10, 2, 1])

    def test_snapshots_read(self):
        comp = os.path.join(self.tmp, "comp")
        self.touch_nk(comp, "sh010_comp_v001.nk")
        snap_folder = os.path.join(comp, ".snapshots", "sh010_comp_20260101_0000_ab12")
        os.makedirs(snap_folder)
        with open(os.path.join(snap_folder, "meta.json"), "w") as fh:
            json.dump({"format": "snapshot/1", "id": "abc", "kind": "render", "note": "Final",
                       "created": "2026-01-01T10:00:00+02:00", "thumbnail": "t.jpg",
                       "render": {"frame_range": "1001-1010"}}, fh)
        with open(os.path.join(snap_folder, "t.jpg"), "w") as fh:
            fh.write("fake")
        snaps = versions.snapshots_for(os.path.join(self.tmp), comp)
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0]["kind"], "render")
        thumbs = versions.thumbnails_for(self.tmp, comp)
        self.assertEqual(len(thumbs), 1)
        self.assertEqual(len(versions.render_records(snaps)), 1)

    def test_missing_snapshots_folder(self):
        self.assertEqual(versions.snapshots_for(self.tmp, self.tmp), [])


class TestOps(Base):
    def test_create_project(self):
        project = ops.create_project(self.tmp, "NewProj", {"client": "C1"})
        self.assertTrue(os.path.isfile(os.path.join(project, "project.json")))
        self.assertTrue(os.path.isdir(os.path.join(project, "shots")))
        with self.assertRaises(ops.OpError):
            ops.create_project(self.tmp, "NewProj")

    def test_create_shot_with_template(self):
        project = make_project(self.tmp, "ProjA", shots=())
        template = self.touch_nk(self.tmp, "base.nk", "# template\n")
        config, _ = schema.load_project(project)
        config["comp_template"] = template
        prefs = {}
        shot_dir, script = ops.create_shot(project, None, prefs, config)
        self.assertEqual(os.path.basename(shot_dir), "sh001")
        self.assertTrue(os.path.isfile(script))
        self.assertTrue(os.path.isdir(os.path.join(shot_dir, "plates")))
        self.assertTrue(os.path.isdir(os.path.join(shot_dir, "comp")))
        loaded, _ = schema.load_shot(shot_dir)
        self.assertEqual(loaded["status"], "wip")
        # next one increments
        shot_dir2, _ = ops.create_shot(project, None, prefs, config)
        self.assertEqual(os.path.basename(shot_dir2), "sh002")

    def test_create_shot_no_template_empty_comp(self):
        project = make_project(self.tmp, "ProjA", shots=())
        shot_dir, script = ops.create_shot(project, "my_shot", {}, {})
        self.assertIsNone(script)
        self.assertTrue(os.path.isdir(os.path.join(shot_dir, "comp")))
        with self.assertRaises(ops.OpError):
            ops.create_shot(project, "my_shot", {}, {})

    def test_adopt_and_unmanage(self):
        shot_dir = os.path.join(self.tmp, "sh030")
        os.makedirs(os.path.join(shot_dir, "comp"))
        self.touch_nk(os.path.join(shot_dir, "comp"), "sh030_comp_v001.nk")
        ops.adopt_shot(shot_dir, {"status": "wip"})
        self.assertTrue(schema.is_our_shot_config(os.path.join(shot_dir, "shot.json")))
        foreign = os.path.join(self.tmp, "other")
        os.makedirs(foreign)
        with open(os.path.join(foreign, "shot.json"), "w") as fh:
            json.dump({"format": "someone-elses/9"}, fh)
        removed = ops.unmanage_project(self.tmp)
        self.assertEqual(removed, 1)  # ours removed, foreign left alone
        self.assertFalse(os.path.isfile(os.path.join(shot_dir, "shot.json")))
        self.assertTrue(os.path.isfile(os.path.join(foreign, "shot.json")))


class TestTasks(Base):
    def test_normalize_and_roundtrip(self):
        shot_dir = os.path.join(self.tmp, "sh100")
        os.makedirs(shot_dir)
        schema.save_shot(shot_dir, {"tasks": ["track",
                                              {"name": "despill", "done": True},
                                              42, {"nope": 1}]})
        loaded, _ = schema.load_shot(shot_dir)
        self.assertEqual(loaded["tasks"],
                         [{"name": "track", "done": False},
                          {"name": "despill", "done": True}])
        schema.save_shot(shot_dir, {"status": "review"})  # partial save keeps tasks
        loaded2, _ = schema.load_shot(shot_dir)
        self.assertEqual(len(loaded2["tasks"]), 2)


class TestBriefing(Base):
    def _shot(self, name, status="wip", due=None, comp_mtime_days_ago=None):
        shot = {"name": name, "path": os.path.join(self.tmp, name),
                "config": {"status": status, "due": due}, "comp_dir": None}
        return shot

    def test_groups_ordered_and_exclusive(self):
        from datetime import date
        from shellcore.briefing import compute_briefing
        today = date(2026, 10, 5)
        shots = [
            self._shot("sh_today", due="2026-10-05"),
            self._shot("sh_soon", due="2026-10-09"),
            self._shot("sh_far", due="2026-10-30"),
            self._shot("sh_waiting", status="waiting"),
            self._shot("sh_review", status="review"),
        ]
        groups = compute_briefing(shots, stale_days=14, due_window=7, today=today)
        keys = [g["key"] for g in groups]
        self.assertEqual(keys, ["due_today", "due_soon", "waiting", "review"])
        self.assertEqual(groups[0]["shots"][0]["name"], "sh_today")
        self.assertEqual(groups[1]["shots"][0]["name"], "sh_soon")

    def test_stale(self):
        from datetime import date
        from shellcore import sessions as sessions_mod
        sessions_mod.SESSIONS_FILE = os.path.join(self.tmp, "sessions.json")
        import time
        old_dir = os.path.join(self.tmp, "sh_old", "comp")
        os.makedirs(old_dir)
        old_file = os.path.join(old_dir, "sh_old_comp_v001.nk")
        with open(old_file, "w") as fh:
            fh.write("x")
        stamp = time.time() - 30 * 86400
        os.utime(old_file, (stamp, stamp))
        from shellcore.briefing import compute_briefing
        shots = [self._shot("sh_old")]
        shots[0]["comp_dir"] = old_dir
        groups = compute_briefing(shots, stale_days=14, today=date.today())
        self.assertEqual([g["key"] for g in groups], ["stale"])


class TestDuplicate(Base):
    def test_duplicate_copies_comp_and_metadata(self):
        project = ops.create_project(self.tmp, "ProjD", {})
        src_dir, _ = ops.create_shot(project, "sh010", {}, {"comp_template": ""})
        comp = os.path.join(src_dir, "comp", "sh010_comp_v001.nk")
        with open(comp, "w") as fh:
            fh.write("# comp\n" + "y" * 500)
        schema.save_shot(src_dir, {"tags": ["keying"]})
        new_dir, script = ops.duplicate_shot(src_dir, None, {},
                                             {"comp_template": ""})
        self.assertEqual(os.path.basename(new_dir), "sh011")
        self.assertTrue(script and script.endswith("sh011_comp_v001.nk"))
        with open(script) as fh:
            self.assertGreater(len(fh.read()), 500)
        loaded, _ = schema.load_shot(new_dir)
        self.assertEqual(loaded["tags"], ["keying"])
        self.assertIn("Duplicated from sh010", loaded["notes"])
        # explicit name is honored
        new_dir2, _ = ops.duplicate_shot(src_dir, "shX_custom", {},
                                         {"comp_template": ""})
        self.assertTrue(new_dir2.endswith("shX_custom"))


class TestSessions(Base):
    def test_segments_and_summary(self):
        sessions.SESSIONS_FILE = os.path.join(self.tmp, "sessions.json")
        now = time.time()
        sessions.add_segment(r"c:\proj\shots\sh010\comp\sh010_comp_v003.nk",
                             now - 3600, now - 600,
                             shot_path=r"c:\proj\shots\sh010",
                             project_path=r"c:\proj")
        sessions.add_segment("bad", now - 100, now - 500)  # inverted, ignored
        summary = sessions.summarize_for_shot(r"c:\proj\shots\sh010",
                                              comp_dir=r"c:\proj\shots\sh010\comp")
        self.assertAlmostEqual(summary["total"], 3000, delta=5)
        self.assertGreater(summary["this_week"], 0)
        self.assertEqual(len(summary["by_day"]), 1)

    def test_prune_old(self):
        sessions.SESSIONS_FILE = os.path.join(self.tmp, "sessions.json")
        old = time.time() - 200 * 86400
        sessions.add_segment("x", old - 100, old - 50, shot_path="s")
        self.assertEqual(sessions.summarize_for_shot("s")["total"], 0.0)


class TestSearch(Base):
    def test_metadata_search(self):
        shots = [
            {"name": "sh010_comp", "config": {"notes": "beer can cleanup", "tags": ["beauty"]},
             "project_name": "ProjA", "project_client": "ClientX", "project_path": "p1"},
            {"name": "sh020_comp", "config": {"notes": "sky", "tags": []},
             "project_name": "ProjB", "project_client": "", "project_path": "p2"},
        ]
        self.assertEqual(len(search.search_shots(shots, "beer")), 1)
        self.assertEqual(len(search.search_shots(shots, "sh020")), 1)
        self.assertEqual(len(search.search_shots(shots, "clientx")), 1)
        self.assertEqual(len(search.search_shots(shots, "")), 2)
        self.assertEqual(len(search.search_shots(shots, "beauty", project="p2")), 0)

    def test_deep_search_unavailable_is_graceful(self):
        # nkparse is not importable in this test context unless SnapshotBrowser is on sys.path
        matches, available = search.deep_search_scripts([], "x")
        self.assertIsInstance(matches, list)
        self.assertIsInstance(available, bool)

    def test_deep_search_with_nkparse(self):
        sys.path.insert(0, os.path.join(os.path.dirname(_TOOL_DIR), "SleepySnapshots"))
        try:
            nk = search._nkparse()
            if nk is None:
                self.skipTest("nkparse not importable")
            script = self.touch_nk(self.tmp, "sh010_comp_v001.nk",
                                   "Blur1 {\n name Blur1\n size 10\n}\n")
            matches, available = search.deep_search_scripts([script], "blur")
            self.assertTrue(available)
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["node"], "Blur1")
        finally:
            sys.path.remove(os.path.join(os.path.dirname(_TOOL_DIR), "SleepySnapshots"))


class TestPrefs(Base):
    def test_defaults_and_persist(self):
        prefs_mod.PREFS_FILE = os.path.join(self.tmp, "prefs.json")
        loaded = prefs_mod.load()
        self.assertEqual(loaded["accent"], "#f0a043")
        loaded["watched_roots"] = [r"d:\Projects"]
        loaded["font_size"] = "not_a_number"
        prefs_mod.save(loaded)
        reloaded = prefs_mod.load()
        self.assertEqual(reloaded["watched_roots"], [r"d:\Projects"])
        self.assertEqual(reloaded["font_size"],
                         prefs_mod.PREFS_DEFAULTS["font_size"])  # coerced back

    def test_folder_template_never_empty(self):
        prefs_mod.PREFS_FILE = os.path.join(self.tmp, "prefs.json")
        loaded = prefs_mod.load()
        loaded["folder_template"] = ["", "  "]
        self.assertEqual(prefs_mod.save(loaded)["folder_template"],
                         prefs_mod.PREFS_DEFAULTS["folder_template"])


class TestLaunch(Base):
    def test_find_executables_returns_list(self):
        result = launch_mod.find_nuke_executables()
        self.assertIsInstance(result, list)

    def test_launch_requires_real_executable(self):
        with self.assertRaises(FileNotFoundError):
            launch_mod.launch_nuke_with(r"c:\definitely\missing\Nuke.exe", "x.nk")


from shellcore import launch as launch_mod  # noqa: E402  (import after class defs is fine at module level)

if __name__ == "__main__":
    unittest.main(verbosity=1)
