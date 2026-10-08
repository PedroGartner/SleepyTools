"""Per-process singleton for (AppState, backend).

Nuke creates widgets via ``registerWidgetAsPanel`` with no constructor
arguments, so the panel pulls its state from here. One session per
process; both the main window (standalone) and the docked panel (Nuke)
share it.
"""

_SESSION = None


def get_session():
    """Return (AppState, backend), creating them on first use."""
    global _SESSION
    if _SESSION is None:
        from shellui.backend import make_backend
        from shellui.state import AppState
        state = AppState()
        state.backend = make_backend()
        _SESSION = (state, state.backend)
    return _SESSION


def reset_session():
    """Drop the cached session. Intended for tests and dev tooling;
    production code never needs it (one session per process is the norm)."""
    global _SESSION
    _SESSION = None
