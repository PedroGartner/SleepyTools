"""Monochrome line icons drawn with QPainter — no image assets, no emoji.

Matches the flat Nuke UI language: thin round-cap strokes in a single
color. Icons are designed on a 16x16 grid and rendered at 2x for
crispness. ``icon(name, color, size)`` returns a QIcon.
"""

import math
import re

from SleepyCore.qt import QtCore, QtGui

_TOKEN_RE = re.compile(r"([ML])\s*([\d.]+)\s*([\d.]+)")


def _arc_points(cx, cy, r, start_deg, end_deg, steps=11):
    """Polyline approximation of a circular arc (degrees, y-down screen space)."""
    points = []
    for i in range(steps + 1):
        angle = math.radians(start_deg + (end_deg - start_deg) * i / steps)
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points


#: name -> list of ops:
#: ("line", x1, y1, x2, y2) | ("circle", cx, cy, r) | ("rect", x, y, w, h)
#: | ("path", "M x y L x y ...") | ("poly", [(x, y), ...])
_PATHS = {
    "search": [("circle", 6.5, 6.5, 4.3), ("line", 9.9, 9.9, 13.6, 13.6)],
    "clock": [("circle", 8, 8, 5.7), ("path", "M8 4.6 L8 8 L10.4 9.4")],
    "funnel": [("path", "M2.5 3 L13.5 3 L9.2 8.2 L9.2 12.8 L6.8 11.5 L6.8 8.2 Z")],
    "flag": [("line", 4, 14, 4, 2), ("path", "M4 3 L12 3 L9.8 5.7 L12 8.5 L4 8.5")],
    "folder": [("path", "M2 4.5 L6.5 4.5 L8 6.2 L14 6.2 L14 12.5 L2 12.5 Z")],
    "plus": [("line", 8, 3.5, 8, 12.5), ("line", 3.5, 8, 12.5, 8)],
    "gear": [("circle", 8, 8, 2.4),
             ("path", "M8 2.5 L8 4.4 M8 11.6 L8 13.5 M2.5 8 L4.4 8 M11.6 8 L13.5 8 "
                      "M4.1 4.1 L5.4 5.4 M10.6 10.6 L11.9 11.9 M11.9 4.1 L10.6 5.4 "
                      "M5.4 10.6 L4.1 11.9")],
    "refresh": [("poly", _arc_points(8, 8, 5.2, -60, 240)),
                ("line", 10.6, 3.5, 10.6, 1.1), ("line", 10.6, 3.5, 13.1, 3.5)],
    "camera": [("rect", 2, 5, 12, 8.5), ("circle", 8, 9.2, 2.2),
               ("path", "M5.5 5 L6.8 3.2 L9.2 3.2 L10.5 5")],
    "send": [("line", 2.5, 8, 12.5, 8), ("path", "M9 4.5 L12.5 8 L9 11.5")],
    "open": [("path", "M3 2.5 L9.5 2.5 L13 6 L13 13.5 L3 13.5 Z"),
             ("path", "M9.5 2.5 L9.5 6 L13 6")],
    "trash": [("line", 3.5, 4.5, 12.5, 4.5), ("path", "M6 4.5 L6 3 L10 3 L10 4.5"),
              ("path", "M4.8 4.5 L5.4 13 L10.6 13 L11.2 4.5")],
    "warn": [("path", "M8 2.5 L14 13 L2 13 Z"), ("line", 8, 6.5, 8, 9.5),
             ("line", 8, 11, 8, 11.15)],
    "dot": [("circle", 8, 8, 2.6)],
    "film": [("rect", 2, 3.5, 12, 9), ("line", 5, 3.5, 5, 12.5), ("line", 2.2, 8, 5, 8),
             ("path", "M6.5 6 L11.5 8 L6.5 10 Z")],
    "home": [("path", "M3 8 L8 3.5 L13 8"),
             ("path", "M4.5 7.2 L4.5 13 L11.5 13 L11.5 7.2")],
    "grid": [("rect", 3, 3, 4.4, 4.4), ("rect", 8.6, 3, 4.4, 4.4),
             ("rect", 3, 8.6, 4.4, 4.4), ("rect", 8.6, 8.6, 4.4, 4.4)],
    "list": [("line", 3, 4.5, 13, 4.5), ("line", 3, 8, 13, 8), ("line", 3, 11.5, 13, 11.5)],
    "columns": [("rect", 3, 3, 2.8, 10), ("rect", 6.6, 3, 2.8, 10),
                ("rect", 10.2, 3, 2.8, 10)],
}


def _build_path(spec):
    """Turn 'M8 4.6 L8 8 L10.4 9.4' into a QPainterPath (unknown cmds = line)."""
    path = QtGui.QPainterPath()
    started = False
    for match in _TOKEN_RE.finditer(spec):
        x, y = float(match.group(2)), float(match.group(3))
        if not started or match.group(1) == "M":
            path.moveTo(x, y)
            started = True
        else:
            path.lineTo(x, y)
    return path


def paint(painter, name, color, rect, stroke=1.4):
    """Paint one icon into ``rect`` (QRect or QRectF) — usable in delegates."""
    ops = _PATHS.get(name)
    if not ops:
        return
    painter.save()
    pen = QtGui.QPen(QtGui.QColor(color), stroke)
    pen.setCapStyle(QtCore.Qt.RoundCap)
    pen.setJoinStyle(QtCore.Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    center = rect.center()
    size = min(rect.width(), rect.height())
    scale = size / 16.0
    painter.translate(center)
    painter.scale(scale, scale)
    painter.translate(-8, -8)
    for op in ops:
        kind = op[0]
        if kind == "line":
            painter.drawLine(QtCore.QPointF(op[1], op[2]), QtCore.QPointF(op[3], op[4]))
        elif kind == "circle":
            painter.drawEllipse(QtCore.QPointF(op[1], op[2]), op[3], op[3])
        elif kind == "rect":
            painter.drawRect(QtCore.QRectF(op[1], op[2], op[3], op[4]))
        elif kind == "poly":
            points = [QtCore.QPointF(x, y) for x, y in op[1]]
            painter.drawPolyline(points)
        elif kind == "path":
            painter.drawPath(_build_path(op[1]))
    painter.restore()


def icon(name, color="#9a9ea6", size=14, device_ratio=2.0):
    """Render ``name`` into a QIcon at ``size`` logical pixels."""
    if name not in _PATHS:
        return QtGui.QIcon()
    px = max(8, int(size * device_ratio))
    pixmap = QtGui.QPixmap(px, px)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    rect = QtCore.QRectF(0, 0, px, px).adjusted(
        device_ratio, device_ratio, -device_ratio, -device_ratio)
    paint(painter, name, color, rect, stroke=1.4 * device_ratio)
    painter.end()
    return QtGui.QIcon(pixmap)
