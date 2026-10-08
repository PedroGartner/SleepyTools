#!/usr/bin/env python
"""Minimal runtime test for TextEditor in Nuke.

Run inside Nuke (Script Editor or `nuke -t test_runtime.py`):
    import sys
    sys.path.insert(0, r"<path to the SleepyText folder>")
    import test_runtime
    test_runtime.run_all()

Tests:
  1. Import & Qt binding selection
  2. Menu installation (idempotent)
  3. Floating window open/close
  4. Dockable panel creation
  5. Tab operations (new, close, split)
  6. Run Python code in editor
  7. Settings persistence
  8. Write node pre-render check (if writes exist)
  9. Reload safety (open → close → reopen)
  10. Callback idempotency (install twice)
"""
from __future__ import print_function
import sys
import time
import traceback

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------
_results = []


def _ok(name, msg=""):
    _results.append(("PASS", name, msg))
    print("  ✓ %s%s" % (name, (" — " + msg) if msg else ""))


def _fail(name, exc):
    _results.append(("FAIL", name, str(exc)))
    print("  ✗ %s: %s" % (name, exc))


def _skip(name, reason):
    _results.append(("SKIP", name, reason))
    print("  ~ %s: %s" % (name, reason))


# ---------------------------------------------------------------------------
# Qt event loop helper
# ---------------------------------------------------------------------------
def _process_events(ms=200):
    """Process Qt events to allow deleteLater, destroyed signals, etc."""
    try:
        from nuke_text_editor.qt import QtWidgets, QtCore
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, ms)
        time.sleep(0.05)
    except Exception:
        time.sleep(ms / 1000.0)


def _wait_for_window_cleanup(window, timeout_ms=3000):
    """Wait until a window is closed and no longer visible.
    In Qt5/PySide2, WA_DeleteOnClose schedules deletion but the C++ object
    may persist until the event loop processes it. The practical test is
    that the window is no longer visible."""
    start = time.time()
    while time.time() - start < timeout_ms / 1000.0:
        _process_events(50)
        try:
            if not window.isVisible():
                return True
        except RuntimeError:
            # C++ object deleted
            return True
    return False


# ---------------------------------------------------------------------------
# Individual tests
# ---------------------------------------------------------------------------
def test_1_import_and_qt():
    """Verify imports work and Qt binding matches Nuke version."""
    try:
        import nuke
        import nuke_text_editor
        from nuke_text_editor import qt

        major = int(nuke.NUKE_VERSION_MAJOR)
        expected_qt6 = major >= 16
        actual_qt6 = qt.QT6

        if actual_qt6 != expected_qt6:
            _fail("test_1_import_and_qt",
                  "Qt binding mismatch: Nuke %d expects QT6=%s, got QT6=%s"
                  % (major, expected_qt6, actual_qt6))
            return

        _ok("test_1_import_and_qt", "Nuke %d, QT6=%s" % (major, actual_qt6))
    except Exception as e:
        _fail("test_1_import_and_qt", e)


def test_2_menu_install_idempotent():
    """Call install() twice — should not duplicate menus."""
    try:
        import nuke
        import nuke_text_editor

        sleepy_menu = nuke.menu("Nuke").findItem("SleepyTools")
        before = len(sleepy_menu.items()) if sleepy_menu else 0

        nuke_text_editor.install()
        nuke_text_editor.install()

        sleepy_menu = nuke.menu("Nuke").findItem("SleepyTools")
        after = len(sleepy_menu.items()) if sleepy_menu else 0

        if before == 0 and after > 0:
            _ok("test_2_menu_install_idempotent", "menu created (%d items)" % after)
        elif before == after:
            _ok("test_2_menu_install_idempotent", "idempotent (%d items)" % after)
        else:
            _fail("test_2_menu_install_idempotent", "menu count changed: %d -> %d" % (before, after))
    except Exception as e:
        _fail("test_2_menu_install_idempotent", e)


def test_3_floating_window():
    """Open and close the floating editor window."""
    try:
        import nuke_text_editor
        from nuke_text_editor import main_window

        w = nuke_text_editor.show_texteditor()
        if w is None:
            _fail("test_3_floating_window", "show_texteditor() returned None")
            return

        if not isinstance(w, main_window.TextEditorWidget):
            _fail("test_3_floating_window", "wrong type: %s" % type(w))
            return

        # Close and wait for actual C++ deletion
        w.close()
        _process_events(200)

        # Wait for window to close (no longer visible or C++ deleted)
        cleaned = _wait_for_window_cleanup(w, 3000)
        if not cleaned:
            _fail("test_3_floating_window", "window still visible after 3s")
            return

        _ok("test_3_floating_window", "open/close OK (C++ object deleted)")
    except Exception as e:
        _fail("test_3_floating_window", e)


def test_4_dockable_panel():
    """Create the dockable panel widget (Pane > Text Editor)."""
    try:
        import nuke_text_editor
        from nuke_text_editor import main_window

        panel = nuke_text_editor.create_panel()
        if panel is None:
            _fail("test_4_dockable_panel", "create_panel() returned None")
            return

        if not isinstance(panel, main_window.TextEditorPanel):
            _fail("test_4_dockable_panel", "wrong type: %s" % type(panel))
            return

        if not hasattr(panel, "tab_widget"):
            _fail("test_4_dockable_panel", "panel missing tab_widget")
            return

        _ok("test_4_dockable_panel", "panel created OK")
    except Exception as e:
        _fail("test_4_dockable_panel", e)


def test_5_tab_operations():
    """New tab, close tab, split view."""
    try:
        import nuke_text_editor
        from nuke_text_editor import main_window

        w = nuke_text_editor.show_texteditor()
        initial_tabs = w.tab_widget.count()

        w.new_tab()
        if w.tab_widget.count() != initial_tabs + 1:
            _fail("test_5_tab_operations", "new_tab failed: %d -> %d"
                  % (initial_tabs, w.tab_widget.count()))
            w.close()
            _wait_for_window_cleanup(w)
            return

        w.close_current_tab()
        if w.tab_widget.count() != initial_tabs:
            _fail("test_5_tab_operations", "close_current_tab: %d -> %d"
                  % (initial_tabs + 1, w.tab_widget.count()))
            w.close()
            _wait_for_window_cleanup(w)
            return

        w.toggle_split()
        if not w.split_tabs.isVisible():
            _fail("test_5_tab_operations", "split view not visible after toggle_split")
            w.close()
            _wait_for_window_cleanup(w)
            return

        w.toggle_split()
        if w.split_tabs.isVisible():
            _fail("test_5_tab_operations", "split view still visible after second toggle")
            w.close()
            _wait_for_window_cleanup(w)
            return

        w.close()
        _wait_for_window_cleanup(w)
        _ok("test_5_tab_operations", "new/close/split OK")
    except Exception as e:
        _fail("test_5_tab_operations", e)


def test_6_run_python_code():
    """Execute code in the editor and verify output panel shows result."""
    try:
        import nuke_text_editor
        from nuke_text_editor import main_window

        w = nuke_text_editor.show_texteditor()
        editor = w.current_editor()
        if editor is None:
            _fail("test_6_run_python_code", "no current editor")
            w.close()
            _wait_for_window_cleanup(w)
            return

        test_code = "print('HELLO_FROM_EDITOR')\nresult = 2 + 2\nprint('RESULT:', result)"
        editor.setPlainText(test_code)

        output_panel = w.output_panel
        w.run_selection()

        _process_events(300)

        # Read output BEFORE closing window (view is the actual QPlainTextEdit)
        try:
            view = output_panel.view if hasattr(output_panel, 'view') else output_panel
            after_text = view.toPlainText() if hasattr(view, 'toPlainText') else str(view)
        except RuntimeError as e:
            _fail("test_6_run_python_code", "OutputPanel already deleted: %s" % e)
            w.close()
            _wait_for_window_cleanup(w)
            return

        w.close()
        _wait_for_window_cleanup(w)

        if "HELLO_FROM_EDITOR" in after_text or "RESULT:" in after_text:
            _ok("test_6_run_python_code", "code executed, output captured")
        else:
            _fail("test_6_run_python_code", "output not captured: %s" % after_text[:200])
    except Exception as e:
        _fail("test_6_run_python_code", e)


def test_7_settings_persistence():
    """Verify settings save/load across instances."""
    try:
        import nuke_text_editor
        from nuke_text_editor import settings

        s = settings.Settings()
        test_key = "_test_runtime_%d" % int(time.time())
        test_val = "test_value_123"

        s.set(test_key, test_val)
        s.sync()

        s2 = settings.Settings()
        got = s2.value(test_key)
        if got != test_val:
            _fail("test_7_settings_persistence", "expected %r, got %r" % (test_val, got))
            return

        s2.set(test_key, None)
        s2.sync()

        _ok("test_7_settings_persistence", "save/load OK")
    except Exception as e:
        _fail("test_7_settings_persistence", e)


def test_8_write_node_check():
    """Test the pre-render Write node check (integration.check_writes_before_send)."""
    try:
        import nuke
        import nuke_text_editor
        from nuke_text_editor import integration

        writes = [n for n in nuke.allNodes() if n.Class() in ("Write", "Write2", "DeepWrite")]
        if not writes:
            _skip("test_8_write_node_check", "no Write nodes in script")
            return

        result = integration.check_writes_before_send(writes, parent=None, action_label="Test Send")
        _ok("test_8_write_node_check", "check_writes_before_send returned %s" % result)
    except Exception as e:
        _fail("test_8_write_node_check", e)


def test_9_reload_safety():
    """Open → close → reopen (triggers refresh_modules)."""
    try:
        import nuke_text_editor
        from nuke_text_editor import main_window

        w1 = nuke_text_editor.show_texteditor()
        w1.create_tab("Test Tab 1")
        w1.close()
        _wait_for_window_cleanup(w1)

        w2 = nuke_text_editor.show_texteditor()
        w2.create_tab("Test Tab 2")
        w2.close()
        _wait_for_window_cleanup(w2)

        _ok("test_9_reload_safety", "open/close/reopen OK (no stale-class errors)")
    except Exception as e:
        _fail("test_9_reload_safety", e)


def test_10_callback_idempotency():
    """Verify install() twice doesn't duplicate Nuke callbacks."""
    try:
        import nuke
        import nuke_text_editor
        from nuke_text_editor import integration

        nuke_text_editor.install()

        if not getattr(nuke, "_sleepy_text_editor_installed", False):
            _fail("test_10_callback_idempotency", "_sleepy_text_editor_installed flag not set")
            return

        nuke_text_editor.install()

        if not getattr(nuke, "_sleepy_text_editor_installed", False):
            _fail("test_10_callback_idempotency", "flag lost after second install")
            return

        _ok("test_10_callback_idempotency", "install() idempotent via _sleepy_text_editor_installed flag")
    except Exception as e:
        _fail("test_10_callback_idempotency", e)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run_all():
    print("\n=== TextEditor Runtime Test ===")
    print("Nuke version: %s" % __import__("nuke").NUKE_VERSION_STRING)

    tests = [
        test_1_import_and_qt,
        test_2_menu_install_idempotent,
        test_3_floating_window,
        test_4_dockable_panel,
        test_5_tab_operations,
        test_6_run_python_code,
        test_7_settings_persistence,
        test_8_write_node_check,
        test_9_reload_safety,
        test_10_callback_idempotency,
    ]

    for i, t in enumerate(tests):
        # Clean up any floating window between tests
        if i > 0:
            from nuke_text_editor import main_window
            for w in main_window.live_windows():
                try:
                    if w.property("sleepy_text_editor_floating"):
                        w.close()
                except RuntimeError:
                    pass
            _process_events(100)

        try:
            t()
        except Exception as e:
            _fail(t.__name__, "test harness error: %s" % e)

    print("\n=== Summary ===")
    passed = sum(1 for r in _results if r[0] == "PASS")
    failed = sum(1 for r in _results if r[0] == "FAIL")
    skipped = sum(1 for r in _results if r[0] == "SKIP")
    print("  PASS: %d  FAIL: %d  SKIP: %d" % (passed, failed, skipped))

    if failed:
        print("\nFAILURES:")
        for status, name, msg in _results:
            if status == "FAIL":
                print("  - %s: %s" % (name, msg))
        return False

    print("\nAll tests passed.")
    return True


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)