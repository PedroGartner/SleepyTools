"""Morning-briefing derivation: what deserves attention right now.

Pure derivation from shot items (as built by shellui.state) — nothing
is stored. Groups shots into: due today, due within the due window,
waiting on client, in review, and stale (untouched for N days).
"""

from datetime import date, timedelta

from shellcore.sessions import last_opened
from shellcore.schema import STATUS_WAITING, STATUS_REVIEW


def _due_date(shot):
    raw = (shot.get("config") or {}).get("due")
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _idle_days(shot):
    folder = shot.get("comp_dir") or shot.get("path")
    stamp = last_opened(folder)
    if not stamp:
        return None
    return (date.today() - date.fromtimestamp(stamp)).days


def compute_briefing(shots, stale_days=14, due_window=7, today=None):
    """Return ordered briefing groups: {title, key, shots} for non-empty ones.

    Order: due today, due this window, waiting client, in review, stale.
    Each shot appears at most once (first matching group wins).
    """
    today = today or date.today()
    horizon = today + timedelta(days=max(1, int(due_window)))
    groups = [
        {"key": "due_today", "title": "Due today", "shots": []},
        {"key": "due_soon", "title": "Due in {} days".format(due_window), "shots": []},
        {"key": "waiting", "title": "Waiting client", "shots": []},
        {"key": "review", "title": "In review", "shots": []},
        {"key": "stale", "title": "Idle {}+ days".format(stale_days), "shots": []},
    ]
    by_key = {g["key"]: g for g in groups}
    for shot in shots:
        status = (shot.get("config") or {}).get("status", "wip")
        due = _due_date(shot)
        if due is not None and due <= today:
            by_key["due_today"]["shots"].append(shot)
            continue
        if due is not None and due <= horizon:
            by_key["due_soon"]["shots"].append(shot)
            continue
        if status == STATUS_WAITING:
            by_key["waiting"]["shots"].append(shot)
            continue
        if status == STATUS_REVIEW:
            by_key["review"]["shots"].append(shot)
            continue
        idle = _idle_days(shot)
        if idle is not None and idle >= int(stale_days) and status not in ("delivered",):
            by_key["stale"]["shots"].append(shot)
    result = [g for g in groups if g["shots"]]
    for g in result:
        g["shots"].sort(key=lambda s: (_due_date(s) or date.max).isoformat())
    return result
