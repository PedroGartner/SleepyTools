"""Install the Sleepy Queue menu into Nuke.

Run once with any Python:  python install_sleepy_queue_integration.py
"""

from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
NUKE_DIR = Path.home() / ".nuke"
MODULE = "sleepy_queue_nuke_integration.py"
MARKER = "# Sleepy Queue integration"

NUKE_DIR.mkdir(parents=True, exist_ok=True)
shutil.copy2(HERE / MODULE, NUKE_DIR / MODULE)
print("Copied", MODULE, "to", NUKE_DIR)

# Remember where the app lives, so Nuke never has to ask for it.
(NUKE_DIR / "sleepy_queue_path.txt").write_text(str(HERE / "sleepy_queue.py"), encoding="utf-8")
print("Sleepy Queue location saved:", HERE / "sleepy_queue.py")

menu = NUKE_DIR / "menu.py"
existing = menu.read_text(encoding="utf-8") if menu.exists() else ""
snippet = (
    "\n" + MARKER + "\ntry:\n    import sleepy_queue_nuke_integration as _bg\n    _bg.install_menu()\n"
    "except Exception as _bg_error:\n    print(\"Sleepy Queue integration:\", _bg_error)\n"
)
if MARKER not in existing:
    with menu.open("a", encoding="utf-8") as fh:
        fh.write(snippet)
    print("Added Sleepy Queue menu to:", menu)
else:
    print("Sleepy Queue menu entry already exists in:", menu)

try:
    import PySide6  # noqa: F401

    print("PySide6 found for this Python.")
except ImportError:
    print(
        "WARNING: PySide6 is not installed for this Python. Install it with:\n    python -m pip install PySide6 psutil"
    )
print("Restart Nuke, then use Nuke > SleepyTools > Sleepy Queue.")
