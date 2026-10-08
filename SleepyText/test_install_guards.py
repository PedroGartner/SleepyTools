"""Executable verification of the transactional install guards.

Extracts the real install()/install_menu() function source from each tool
file and runs it against a mock nuke across five scenarios:
first install, second install, module reload, failed install, retry.

Run outside Nuke:  python test_install_guards.py
"""
import ast
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class FakeMenu(object):
    def __init__(self, log, name=""):
        self._log = log
        self._name = name

    def addMenu(self, name):
        self._log.append(("addMenu", self._name + "/" + name))
        return FakeMenu(self._log, self._name + "/" + name)

    def addCommand(self, label, cmd, shortcut=None):
        self._log.append(("addCommand", self._name, label))

    def addSeparator(self):
        self._log.append(("separator", self._name))


class FakeNuke(object):
    def __init__(self, fail_menu=False):
        self._fail = fail_menu
        self._log = []

    def menu(self, name):
        if self._fail:
            raise RuntimeError("simulated registration failure")
        return FakeMenu(self._log, name)

    @property
    def log(self):
        return self._log


LABS = [
    ("SleepyBlink/sleepy_blink.py", "install",
     dict(KERNELS=[], PANEL_TITLE="T", PANEL_ID="I")),
    ("SleepyExpressions/sleepy_expressions.py", "install",
     dict(CATALOG=[], PANEL_TITLE="T", PANEL_ID="I")),
    ("SleepyKnobs/sleepy_knobs.py", "install", {}),
    ("SleepyDoctor/sleepy_doctor.py", "install",
     dict(TOOL="T", PANEL_ID="I", load_settings=lambda: {})),
    ("SleepyLibrary/sleepy_library.py", "install",
     dict(PANEL_TITLE="T", PANEL_ID="I")),
]


def extract(path, func_name):
    src = open(path, "r", encoding="utf-8").read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return ast.get_source_segment(src, node)
    raise LookupError("%s not found in %s" % (func_name, path))


def make_ns(nuke, extra):
    ns = dict(nuke=nuke, _installed=False, _nkpanels=None)
    ns.update(extra)
    return ns


def registered_count(nuke):
    return len([e for e in nuke.log if e[0] in ("addCommand", "addMenu", "separator")])


def check(cond, msg):
    if not cond:
        print("  FAIL:", msg)
        return False
    print("  ok:", msg)
    return True


def test_lab(relpath, func, extra):
    print(relpath)
    src = extract(os.path.join(ROOT, relpath), func)
    ok = True

    # 1. first install: registers, sets both flags
    nk = FakeNuke()
    ns = make_ns(nk, extra)
    exec(src, ns)
    ns[func]()
    ok &= check(registered_count(nk) > 0, "first install registers")
    ok &= check(getattr(nk, "_flag_pending", None) is None and flag_true(nk, extra), "persistent flag True after success")
    ok &= check(ns["_installed"] is True, "module flag True after success")
    n_commands = registered_count(nk)

    # 2. second install: no duplicates
    ns[func]()
    ok &= check(registered_count(nk) == n_commands, "second install adds nothing")

    # 3. module reload: fresh module namespace, same nuke process
    ns2 = make_ns(nk, extra)
    exec(src, ns2)
    ns2[func]()
    ok &= check(registered_count(nk) == n_commands, "reload adds nothing")
    ok &= check(ns2["_installed"] is True, "reload adopts persistent flag")

    # 4. failed install: nothing marked, exception propagates, retry possible
    bad = FakeNuke(fail_menu=True)
    ns3 = make_ns(bad, extra)
    exec(src, ns3)
    try:
        ns3[func]()
        raised = False
    except RuntimeError:
        raised = True
    ok &= check(raised, "failure raises (original behavior preserved)")
    ok &= check(not flag_exists(bad, extra), "persistent flag NOT set after failure")
    ok &= check(ns3["_installed"] is False, "module flag NOT set after failure")

    # 5. retry after failure succeeds
    ns3b = make_ns(bad, extra)   # same nuke object, failure cleared
    bad._fail = False
    exec(src, ns3b)
    ns3b[func]()
    ok &= check(registered_count(bad) > 0 and flag_true(bad, extra) and ns3b["_installed"] is True,
                "retry after failure installs and sets flags")
    return ok


def _flag_name(extra):
    return None


def flag_true(nk, extra):
    for a in dir(nk):
        if a.endswith("_installed") and not a.startswith("_batch"):
            return getattr(nk, a) is True
    return False


def flag_exists(nk, extra):
    for a in dir(nk):
        if a.endswith("_installed") and not a.startswith("_batch"):
            return True
    return False


def test_batch_integration():
    print("SleepyQueue/sleepy_queue_nuke_integration.py install_menu")
    src = extract(os.path.join(ROOT, "SleepyQueue/sleepy_queue_nuke_integration.py"), "install_menu")
    extra = dict(send_selected_writes=lambda: None, send_all_writes=lambda: None,
                 send_selected_current_frame=lambda: None, open_batch_renderer=lambda: None,
                 start_read_listener=lambda: None)
    ok = True

    nk = FakeNuke()
    ns = make_ns(nk, extra)
    exec(src, ns)
    ns["install_menu"]()
    ok &= check(("addMenu", "Nuke/SleepyTools/Sleepy Queue") in nk.log,
                "menu created at Nuke > SleepyTools > Sleepy Queue")
    ok &= check(getattr(nk, "_sleepy_queue_menu_installed", False) is True, "flag True after success")
    n = registered_count(nk)
    ns["install_menu"]()
    ok &= check(registered_count(nk) == n, "second install adds nothing")

    ns2 = make_ns(nk, extra)
    exec(src, ns2)
    ns2["install_menu"]()
    ok &= check(registered_count(nk) == n, "reload adds nothing")

    bad = FakeNuke(fail_menu=True)
    ns3 = make_ns(bad, extra)
    exec(src, ns3)
    try:
        ns3["install_menu"]()
        raised = False
    except RuntimeError:
        raised = True
    ok &= check(raised, "failure raises")
    ok &= check(not hasattr(bad, "_sleepy_queue_menu_installed"), "flag NOT set after failure")

    bad._fail = False
    ns3b = make_ns(bad, extra)
    exec(src, ns3b)
    ns3b["install_menu"]()
    ok &= check(getattr(bad, "_sleepy_queue_menu_installed", False) is True, "retry after failure succeeds")
    return ok


def main():
    ok = True
    for rel, func, extra in LABS:
        ok &= test_lab(rel, func, extra)
    ok &= test_batch_integration()
    print("\nRESULT:", "ALL GUARD TESTS PASSED" if ok else "FAILURES DETECTED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
