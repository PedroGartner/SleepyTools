"""Qt import shim: version-aware PySide2/6 selection with compatibility helpers.

Nuke 13-15 -> PySide2, Nuke 16+ -> PySide6.
"""

import sys

def _binding_name():
    """Return the Qt binding module name for this host, or None outside Qt.

    Order matters:
    1. Inside Nuke the version decides, always. No probing imports.
    2. Outside Nuke, reuse a binding that is already loaded (the host
       application may have made the choice for us).
    3. Standalone (tests, plain Python): prefer PySide6, fall back to
       PySide2.
    """
    try:
        import nuke
        major = int(nuke.NUKE_VERSION_MAJOR)
    except Exception:
        major = None
    if major is not None:
        return "PySide6" if major >= 16 else "PySide2"
    for name in ("PySide6", "PySide2"):
        if name + ".QtWidgets" in sys.modules:
            return name
    return None


_BINDING = _binding_name()
if _BINDING == "PySide2":
    from PySide2 import QtCore, QtGui, QtWidgets
    QT6 = False
elif _BINDING == "PySide6":
    from PySide6 import QtCore, QtGui, QtWidgets
    QT6 = True
else:
    # Outside Nuke (standalone use, tests): prefer PySide6.
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        QT6 = True
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
        QT6 = False

Signal = QtCore.Signal

# QShortcut moved from QtWidgets (Qt 5) to QtGui (Qt 6).
QShortcut = getattr(QtGui, "QShortcut", None) or getattr(QtWidgets, "QShortcut", None)

# QOpenGLWidget: QtWidgets in Qt 5, its own module in Qt 6.
if QT6:
    try:
        from PySide6.QtOpenGLWidgets import QOpenGLWidget
    except ImportError:
        QOpenGLWidget = None
else:
    QOpenGLWidget = getattr(QtWidgets, "QOpenGLWidget", None)


__all__ = ["QtCore", "QtGui", "QtWidgets", "Signal", "QOpenGLWidget", "QShortcut"]
