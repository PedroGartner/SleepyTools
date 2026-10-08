"""Loads Snapshot Browser when this folder is added as a Nuke plugin path."""

try:
    import sleepy_snapshots  # noqa: F401
except Exception:
    import traceback

    print("[Snapshot Browser] Failed to load:")
    traceback.print_exc()
    try:
        import SleepyCore
        SleepyCore.log_exception("load sleepy_snapshots")
    except Exception:
        pass
