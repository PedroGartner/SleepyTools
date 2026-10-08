"""Self-test for SleepyCore. Run inside Nuke to verify the install.

Usage:
    python -c "import SleepyCore.selftest"
"""

import sys

__all__ = ["run"]


def run():
    """Run all self-tests. Returns True if all pass."""
    print("=== SleepyCore self-test ===")
    tests = [
        ("Qt binding", _test_qt_binding),
        ("Reload detection", _test_reload),
        ("Settings round-trip", _test_settings),
        ("Crash logging", _test_crashlog),
        ("Theme palette", _test_theme),
        ("Menu helpers", _test_menus),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print("  PASS: %s" % name)
            passed += 1
        except Exception as exc:
            print("  FAIL: %s - %s" % (name, exc))
    print("=== %d/%d passed ===" % (passed, len(tests)))
    return passed == len(tests)


def _test_qt_binding():
    from SleepyCore.qt import QtCore, QtGui, QtWidgets, QT6, qt_exec, event_pos
    assert QtCore is not None
    assert QtGui is not None
    assert QtWidgets is not None
    assert isinstance(QT6, bool)
    # Verify Qt 5/6 compatibility helpers exist
    assert callable(qt_exec)
    assert callable(event_pos)


def _test_reload():
    from SleepyCore.reload import stale_modules, refresh_modules, iter_tool_modules
    assert callable(stale_modules)
    assert callable(refresh_modules)
    assert callable(iter_tool_modules)
    # Should not crash on empty prefixes
    assert stale_modules("nonexistent_module_xyz") == []
    assert refresh_modules("nonexistent_module_xyz") == 0


def _test_settings():
    from SleepyCore.settings import get, set, get_tool_settings
    tool = "_test_tool_xyz"
    key = "_test_key"
    val = "test_value_%d" % __import__("time").time()
    # Clean up first
    from SleepyCore.settings import _load_all, _save_all
    data = _load_all()
    if tool in data:
        del data[tool]
    _save_all(data)
    # Test set/get
    set(tool, key, val)
    assert get(tool, key) == val
    # Test defaults
    assert get(tool, "nonexistent", "default") == "default"
    # Test get_tool_settings
    settings = get_tool_settings(tool, {"default": "value"})
    assert settings.get(key) == val
    # Cleanup
    data = _load_all()
    if tool in data:
        del data[tool]
    _save_all(data)


def _test_crashlog():
    from SleepyCore.crashlog import log_exception
    try:
        raise ValueError("test")
    except Exception:
        log_exception("selftest")
    # Should not crash


def _test_theme():
    from SleepyCore.themes import get_palette, apply, widget_style
    from SleepyCore.qt import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    w = QtWidgets.QWidget()
    apply(w)
    assert w.palette().color(w.backgroundRole()).name().lower() == "#161719"
    w.deleteLater()


def _test_menus():
    from SleepyCore.menus import get_sleepy_menu, add_sleepy_command, add_sleepy_submenu
    try:
        import nuke
        m = get_sleepy_menu()
        # In headless test, nuke.menu() may return None; that's OK
        if m is not None:
            add_sleepy_command("_test_cmd", lambda: None)
            sub = add_sleepy_submenu("_test_sub")
            # Cleanup
            try:
                m.removeItem("_test_cmd")
            except Exception:
                pass
            try:
                m.removeItem("_test_sub")
            except Exception:
                pass
    except ImportError:
        pass  # No Nuke available


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)