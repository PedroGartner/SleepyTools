"""Simulate the SleepyShell.bat startup path end to end.

Runs exactly what the .bat runs — python standalone.py — on the
offscreen platform, with a timer that quits after the window has been
shown. Exit code 0 means the launcher opens; any startup crash (like
the QLineEdit.setIconSize AttributeError that once broke the .bat)
fails here instead of on the user's double-click.

    python tests/bat_smoke.py
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
SUITE = os.path.dirname(TOOL)


def main():
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    runner = os.path.join(HERE, "_bat_runner.py")
    proc = subprocess.run([sys.executable, runner], env=env,
                          capture_output=True, text=True, timeout=120,
                          cwd=TOOL)
    if proc.returncode != 0:
        print("STARTUP FAILED")
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:])
        return 1
    print("BAT STARTUP OK (window shown, clean exit)")
    tail = (proc.stderr or "").strip().splitlines()[-3:]
    for line in tail:
        print("  ", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
