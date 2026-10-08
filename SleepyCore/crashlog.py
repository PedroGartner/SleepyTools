"""Uncaught exception logging for the suite.

Logs are written to ~/.nuke/sleepy_core/crash_logs/ with timestamps.
Keeps the newest 50 logs. Tools can opt out via settings
(sleepy_core.crash_logs: false).
"""

import io
import os
import sys
import time
import traceback

LOG_DIR = os.path.join(os.path.expanduser("~"), ".nuke", "sleepy_core", "crash_logs")
MAX_LOGS = 50
_hook_installed = False


def _ensure_dir():
    if not os.path.isdir(LOG_DIR):
        try:
            os.makedirs(LOG_DIR)
        except Exception:
            pass


def _cleanup_old():
    try:
        files = sorted(
            [os.path.join(LOG_DIR, f) for f in os.listdir(LOG_DIR) if f.endswith(".log")],
            key=os.path.getmtime,
        )
        for f in files[:-MAX_LOGS]:
            try:
                os.remove(f)
            except Exception:
                pass
    except Exception:
        pass


def log_exception(context=""):
    """Log the current exception with context. Safe to call from any except block."""
    try:
        _ensure_dir()
        _cleanup_old()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(LOG_DIR, "crash_%s.log" % timestamp)
        with io.open(path, "w", encoding="utf-8", errors="replace") as fh:
            fh.write("Context: %s\n" % context)
            fh.write("Time: %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            fh.write("Python: %s\n" % sys.version)
            try:
                import nuke
                fh.write("Nuke: %s\n" % getattr(nuke, "NUKE_VERSION_STRING", "unknown"))
            except Exception:
                fh.write("Nuke: not available\n")
            fh.write("\nTraceback:\n")
            traceback.print_exc(file=fh)
    except Exception:
        pass  # never crash while logging a crash


def install_excepthook():
    """Install a global sys.excepthook that logs uncaught exceptions."""
    global _hook_installed
    if _hook_installed:
        return
    old_hook = sys.excepthook

    def hook(exc_type, exc_value, exc_tb):
        log_exception("Uncaught exception")
        old_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = hook
    _hook_installed = True