"""Sleepy Shell core engine.

Pure Python: no nuke import, no Qt import. Everything here runs both
inside Nuke and in a standalone Python, so the launcher and the docked
panel share exactly one implementation of scanning, metadata, naming
and session tracking.
"""

__version__ = "1.0.0"
