"""Launching Nuke and opening folders. Used by the standalone launcher;
inside Nuke the backend opens scripts directly instead."""

import os
import subprocess
import sys


def find_nuke_executables():
    """Best-effort list of installed Nuke executables, newest first.

    Windows: C:\\Program Files\\Nuke16.1v5\\Nuke16.1.exe
    Returns [] when nothing is found; the user can always set the path
    manually in Preferences.
    """
    found = []
    if sys.platform.startswith("win"):
        bases = [os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files")),
                 os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))]
        for base in bases:
            if not os.path.isdir(base):
                continue
            try:
                entries = os.listdir(base)
            except OSError:
                continue
            for entry in entries:
                if entry.lower().startswith("nuke"):
                    folder = os.path.join(base, entry)
                    if not os.path.isdir(folder):
                        continue
                    try:
                        for name in os.listdir(folder):
                            if name.lower().startswith("nuke") and name.lower().endswith(".exe"):
                                full = os.path.join(folder, name)
                                if os.path.isfile(full):
                                    found.append(full)
                    except OSError:
                        continue
    elif sys.platform == "darwin":
        bases = ["/Applications"]
        for base in bases:
            try:
                entries = os.listdir(base)
            except OSError:
                continue
            for entry in entries:
                if entry.lower().startswith("nuke") and entry.endswith(".app"):
                    full = os.path.join(base, entry, "Contents", "MacOS", entry[:-4])
                    if os.path.isfile(full):
                        found.append(full)
    else:
        for base in ("/usr/local", "/opt"):
            try:
                entries = os.listdir(base)
            except OSError:
                continue
            for entry in entries:
                if entry.lower().startswith("nuke"):
                    full = os.path.join(base, entry, "Nuke" + entry[4:])
                    if os.path.isfile(full):
                        found.append(full)
    found = list(dict.fromkeys(found))
    found.sort(reverse=True)
    return found


def launch_nuke_app(executable):
    """Start Nuke without a script (the home screen's 'Open Nuke…')."""
    if not executable or not os.path.isfile(executable):
        raise FileNotFoundError("Nuke executable not set or missing: {!r}".format(executable))
    flags = 0
    if sys.platform.startswith("win"):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen([executable], close_fds=True, creationflags=flags)


def launch_nuke_with(executable, script_path):
    """Start Nuke (detached) with a script. Returns the Popen handle."""
    if not executable or not os.path.isfile(executable):
        raise FileNotFoundError("Nuke executable not set or missing: {!r}".format(executable))
    flags = 0
    if sys.platform.startswith("win"):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen([executable, script_path], close_fds=True, creationflags=flags)


def open_in_explorer(path):
    """Reveal a folder in the OS file browser. Returns True on success."""
    try:
        if not os.path.isdir(path):
            return False
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: attribute exists on Windows
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except (OSError, AttributeError):
        return False
