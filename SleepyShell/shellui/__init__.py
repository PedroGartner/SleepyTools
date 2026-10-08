"""Sleepy Shell UI. Qt widgets live here; importing this package pulls
Qt through SleepyCore.qt, which picks the binding the host already
uses (Nuke 13-15 -> PySide2, Nuke 16+ -> PySide6, standalone -> PySide6
first, PySide2 fallback)."""
