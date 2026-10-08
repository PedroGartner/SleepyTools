"""Search across the portfolio.

Metadata search (names, notes, tags, client) always works. Deep search
inspects the node contents of .nk scripts when SnapshotBrowser's
``nkparse`` reader is importable; when it is not, deep search simply
reports that it is unavailable instead of failing.
"""

import os

from shellcore.naming import parse_version_number


def _norm(value):
    return (value or "").lower()


def search_shots(shots, text, project=None):
    """Filter shot dicts by a free-text query over name/notes/tags/project."""
    text = _norm(text).strip()
    if not text:
        return list(shots)
    terms = text.split()
    results = []
    for shot in shots:
        haystack = " ".join([
            _norm(shot.get("name")),
            _norm((shot.get("config") or {}).get("notes")),
            " ".join(_norm(t) for t in (shot.get("config") or {}).get("tags", [])),
            _norm(shot.get("project_name")),
            _norm(shot.get("project_client")),
        ])
        if all(term in haystack for term in terms):
            if project is None or shot.get("project_path") == project:
                results.append(shot)
    return results


def _nkparse():
    try:
        import nkparse  # SnapshotBrowser's reader, when its folder is on sys.path
        return nkparse
    except Exception:
        try:
            from snapbrowser import nkparse
            return nkparse
        except Exception:
            return None


def deep_search_scripts(paths, text, max_files=200, max_bytes=20 * 1024 * 1024):
    """Search node names, classes and knob text inside .nk files.

    Returns (matches, available). ``matches`` is a list of
    {path, node, snippet} dicts. ``available`` is False when nkparse
    could not be imported; callers should show a hint instead.
    """
    text = _norm(text).strip()
    if not text:
        return [], True
    nkparse = _nkparse()
    if nkparse is None:
        return [], False
    matches = []
    checked = 0
    for path in paths:
        if checked >= max_files:
            break
        try:
            if os.path.getsize(path) > max_bytes:
                continue
        except OSError:
            continue
        try:
            script = nkparse.parse_file(path)
        except Exception:
            continue
        checked += 1
        for node in script.nodes.values():
            knobs = " ".join(_norm("{} {}".format(k, v))
                             for k, v in (node.knobs or {}).items())
            haystack = " ".join([_norm(node.name), _norm(node.cls), knobs])
            if text in haystack:
                matches.append({
                    "path": path,
                    "node": node.name,
                    "snippet": (node.cls + " " + (node.snippet()[:100] if node.snippet() else "")).strip(),
                    "version": parse_version_number(path) or 0,
                })
                if len(matches) >= 100:
                    return matches, True
    return matches, True
