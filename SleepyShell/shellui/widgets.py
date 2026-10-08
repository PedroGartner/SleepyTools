"""Shared Shell widgets: chips, thumbnails, toggles, sections, empty states.

Widget styling follows the HTML mockup: pill chips (radius 20px look),
140-degree muted gradient thumbnails with a big translucent code label,
34x18 pill toggles, and titled panel sections with an uppercase
letter-spaced caption. Letter spacing is set on the QFont because Qt
style sheets have no letter-spacing property.
"""

import hashlib
import os

from SleepyCore.qt import QtCore, QtGui, QtWidgets

from shellui import icons


def styled(widget):
    """Plain QWidgets need WA_StyledBackground to paint a QSS background."""
    widget.setAttribute(QtCore.Qt.WA_StyledBackground, True)
    return widget


class ClickableFrame(QtWidgets.QFrame):
    """A frame that reports left-click and double-click via callbacks.

    Qt event handlers must be overridden on the class, not assigned on
    instances, so plain attribute assignment cannot be used here.
    """

    leftClicked = QtCore.Signal()
    doubleClicked = QtCore.Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.leftClicked.emit()
        super(ClickableFrame, self).mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super(ClickableFrame, self).mouseDoubleClickEvent(event)


class ElidedLabel(QtWidgets.QLabel):
    """A QLabel that elides its text instead of clipping."""

    def __init__(self, text="", parent=None):
        super(ElidedLabel, self).__init__(parent)
        self._full = text
        self.setText(text)

    def setText(self, text):
        self._full = text or ""
        super(ElidedLabel, self).setText(self._full)

    def text(self):
        return self._full

    def resizeEvent(self, event):
        metrics = self.fontMetrics()
        super(ElidedLabel, self).setText(metrics.elidedText(
            self._full, QtCore.Qt.ElideMiddle, max(10, self.width() - 4)))
        super(ElidedLabel, self).resizeEvent(event)


class Chip(QtWidgets.QLabel):
    """Rounded status pill (the mockup's .chip): 11px, 600, pill radius.

    Background 15% of the status color, border 40%, matching
    .c-wip/.c-review/... in the mockup CSS.
    """

    def __init__(self, text, color="#8a8f98", parent=None, dim=False):
        super(Chip, self).__init__(text, parent)
        self._color = color
        self._dim = dim
        # never inflate to the row height (mockup chips hug their text)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self._apply()

    def set_status_color(self, color, dim=False):
        self._color = color
        self._dim = dim
        self._apply()

    def _apply(self):
        c = QtGui.QColor(self._color)
        rgb = "{},{},{}".format(c.red(), c.green(), c.blue())
        if self._dim:
            self.setStyleSheet(
                "QLabel {{ background: rgba({rgb},10%);"
                " color: {hex};"
                " border: 1px solid rgba({rgb},28%); border-radius: 10px;"
                " padding: 1px 9px; font-size: 11px; font-weight: 600; }}".format(
                    rgb=rgb, hex=self._color))
        else:
            self.setStyleSheet(
                "QLabel {{ background: rgba({rgb},15%); color: {hex};"
                " border: 1px solid rgba({rgb},40%); border-radius: 10px;"
                " padding: 1px 9px; font-size: 11px; font-weight: 600; }}".format(
                    rgb=rgb, hex=self._color))


class NeutralChip(QtWidgets.QLabel):
    """The mockup's neutral chip: alt background, dim text, line border."""

    def __init__(self, text, parent=None):
        super(NeutralChip, self).__init__(text, parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.setStyleSheet(
            "QLabel { background: #26272a; color: #9a9ea6;"
            " border: 1px solid #3a3c40; border-radius: 10px;"
            " padding: 1px 9px; font-size: 11px; font-weight: 600; }")


class MetaChip(QtWidgets.QLabel):
    """The shot-settings .mchip: window bg, soft border, dim label + bold value."""

    def __init__(self, label, value, parent=None):
        value = value if value not in (None, "") else "—"
        super(MetaChip, self).__init__(
            "<span style=\"color:#9a9ea6;\">{} </span>"
            "<b style=\"color:#e6e6e6; font-weight:600;\">{}</b>".format(
                label, value), parent)
        self.setObjectName("ShellMChip")


# The mockup's g1..g8 placeholder gradients (140deg, dark -> mid tone).
G_GRADIENTS = (
    ("#1f2b38", "#3e5a74"),
    ("#2b2318", "#6e5426"),
    ("#23301f", "#4e6e35"),
    ("#301f26", "#74435a"),
    ("#1e2e2e", "#3f6b66"),
    ("#2a2a30", "#5a5a78"),
    ("#32261a", "#8a6a3a"),
    ("#20222c", "#4a5470"),
)


class Thumb(QtWidgets.QLabel):
    """Shot thumbnail: real image when available, mockup gradient otherwise.

    The gradient pair is picked from the mockup's g1..g8 palette by a
    hash of the shot name, so a shot always renders the same placeholder.
    ``expanding=True`` fills the available width at a fixed height (home
    cards, gallery cards) instead of a fixed size.
    """

    SIZE_SMALL = (96, 54)
    SIZE_CARD = (74, 52)
    SIZE_BIG = (260, 146)

    def __init__(self, shot_name, image_path=None, size=SIZE_CARD, parent=None,
                 tag=None, expanding=False, radius=5, font_px=None):
        super(Thumb, self).__init__(parent)
        self._shot_name = shot_name
        self._image_path = image_path
        self._tag = tag
        self._expanding = expanding
        self._radius = radius
        self._font_px = font_px
        if expanding:
            self.setFixedHeight(size[1])
            self.setMinimumWidth(40)
        else:
            self.setFixedSize(*size)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self._render()

    def resizeEvent(self, event):
        if self._expanding:
            self._render()
        super(Thumb, self).resizeEvent(event)

    def set_image(self, image_path):
        self._image_path = image_path
        self._render()

    def _render(self):
        w = max(10, self.width())
        h = max(10, self.height())
        if self._image_path and os.path.isfile(self._image_path):
            pix = QtGui.QPixmap(self._image_path)
            if not pix.isNull():
                self.setPixmap(pix.scaled(
                    w, h, QtCore.Qt.KeepAspectRatioByExpanding,
                    QtCore.Qt.SmoothTransformation))
                return
        digest = hashlib.md5(self._shot_name.encode("utf-8")).hexdigest()
        c1, c2 = G_GRADIENTS[int(digest[:4], 16) % len(G_GRADIENTS)]
        gradient = QtGui.QLinearGradient(0, 0, w, h)  # ~140deg in the mockup
        gradient.setColorAt(0, QtGui.QColor(c1))
        gradient.setColorAt(1, QtGui.QColor(c2))
        pix = QtGui.QPixmap(w, h)
        pix.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pix)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        path = QtGui.QPainterPath()
        path.addRoundedRect(0, 0, w, h, self._radius, self._radius)
        painter.fillPath(path, gradient)

        # big translucent code label, soft drop shadow like the mockup
        font = painter.font()
        font.setBold(True)
        font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 1.0)
        font.setPixelSize(self._font_px or max(9, int(h * 0.19)))
        painter.setFont(font)
        rect = pix.rect()
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 110)))
        painter.drawText(rect.adjusted(0, 1, 0, 1),
                         QtCore.Qt.AlignCenter, self._shot_name)
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 145)))
        painter.drawText(rect, QtCore.Qt.AlignCenter, self._shot_name)
        if self._tag:
            tag_font = painter.font()
            tag_font.setBold(False)
            tag_font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 1.0)
            tag_font.setPixelSize(9)
            painter.setFont(tag_font)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 125)))
            painter.drawText(QtCore.QRect(7, h - 16, w - 14, 12),
                             QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                             self._tag.upper())
        painter.end()
        self.setPixmap(pix)


class Toggle(QtWidgets.QAbstractButton):
    """Small switch, drawn like the mockup's .tog2 pill toggle."""

    def __init__(self, checked=False, parent=None):
        super(Toggle, self).__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(34, 18)
        self._accent = "#f0a043"

    def set_accent(self, color):
        self._accent = color
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        on = self.isChecked()
        bg = QtGui.QColor(self._accent) if on else QtGui.QColor("#3a3c40")
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(0, 0, 34, 18, 9, 9)
        painter.setBrush(QtGui.QColor("#e6e6e6") if not on else QtGui.QColor("#161719"))
        x = 18 if on else 2
        painter.drawEllipse(x, 2, 14, 14)
        painter.end()

    def hitButton(self, pos):
        return self.rect().contains(pos)


class Section(QtWidgets.QFrame):
    """Titled card panel (the mockup's .panel: base bg, soft border).

    ``title`` renders as the uppercase letter-spaced caption on the
    left; ``extra`` is the small dim right-hand note ("stored in
    shot.json", "from disk", ...).
    """

    def __init__(self, title, extra=None, parent=None):
        super(Section, self).__init__(parent)
        self.setObjectName("ShellSection")
        self.extra_widget = extra
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(15, 11, 15, 13)
        layout.setSpacing(9)
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)
        label = QtWidgets.QLabel(title.upper())
        set_section_font(label)
        header.addWidget(label)
        header.addStretch(1)
        if extra:
            extra.setObjectName("ShellDim")
            extra.setStyleSheet("font-size: 11px; background: transparent;")
            header.addWidget(extra)
        layout.addLayout(header)
        self.body = QtWidgets.QVBoxLayout()
        self.body.setSpacing(8)
        layout.addLayout(self.body)

    def add(self, widget):
        self.body.addWidget(widget)
        return widget

    def add_layout(self, layout):
        self.body.addLayout(layout)
        return layout


def set_section_font(label, size=11, spacing=1.1):
    """Uppercase 11px/700 caption with letter tracking (mockup h4/h5)."""
    font = label.font()
    font.setPixelSize(size)
    font.setBold(True)
    font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, spacing)
    label.setFont(font)
    return label


class EmptyState(QtWidgets.QLabel):
    """Centered, dim message for empty lists/pages."""

    def __init__(self, text, icon_name=None, parent=None):
        super(EmptyState, self).__init__(parent)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet("color: #9a9ea6; background: transparent; padding: 24px;")
        if icon_name:
            self.setText("<div align='center'>{icon}<br><br>{text}</div>".format(
                icon="", text=text))
        else:
            self.setText(text)


def tool_button(icon_name, tooltip, callback, color="#9a9ea6", size=14, parent=None):
    """Flat icon button with a working action."""
    button = QtWidgets.QToolButton(parent)
    button.setIcon(icons.icon(icon_name, color=color, size=size))
    button.setToolTip(tooltip)
    button.setCursor(QtCore.Qt.PointingHandCursor)
    button.setStyleSheet(
        "QToolButton { background: transparent; border: none; padding: 3px; }"
        "QToolButton:hover { border-radius: 3px; background: #26272a; }")
    button.clicked.connect(callback)
    return button


def hline():
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.HLine)
    line.setStyleSheet("color: #2a2c30; background: #2a2c30; max-height: 1px; border: none;")
    return line


def clear_layout(layout):
    """Remove and delete all child widgets/layouts of ``layout``.

    Widgets are detached (setParent(None) + hide) immediately so a
    rebuild never shows stale rows on top of the new ones; deleteLater
    only frees the C++ side afterwards.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.hide()
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())
            item.layout().deleteLater()


def app_logo_icon(size=32, accent="#f0a043"):
    """The Sleepy G tile as a QIcon — the app/window icon everywhere."""
    ratio = 2.0
    pixmap = QtGui.QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor(accent))
    painter.drawRoundedRect(0, 0, size, size, 5, 5)
    font = painter.font()
    font.setPixelSize(int(size * 0.68))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QtGui.QColor("#161719"))
    painter.drawText(pixmap.rect(), QtCore.Qt.AlignCenter, "G")
    painter.end()
    return QtGui.QIcon(pixmap)


FACE_ICON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sleepy_icon.png")


def apply_standalone_icon(app, *windows):
    """Give the standalone (outside Nuke) windows the Sleepy face icon.

    Set on the windows themselves as well: ``theme.apply`` replaces the
    application-level icon again whenever the appearance prefs change.
    Nuke-hosted panels never call this and keep their own icon behavior.
    """
    if os.name == "nt":
        try:
            # own taskbar identity, so the icon is not replaced by python.exe's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Sleepy.Shell")
        except (AttributeError, OSError):
            pass
    icon = QtGui.QIcon(FACE_ICON_FILE)
    if icon.isNull():
        return
    app.setWindowIcon(icon)
    for window in windows:
        window.setWindowIcon(icon)


def face_logo_pixmap(size):
    """The Sleepy face as a crisp ``size`` x ``size`` logical-px pixmap, or None
    when the icon file is missing (callers then keep their lettered tile)."""
    source = QtGui.QPixmap(FACE_ICON_FILE)
    if source.isNull():
        return None
    # match the screen's pixel ratio: a mismatched pixmap gets resampled by
    # the painter without smoothing, which wrecks the thin lines
    screen = QtWidgets.QApplication.primaryScreen()
    ratio = max(1.0, screen.devicePixelRatio()) if screen is not None else 1.0
    pixel = int(round(size * ratio))
    pixmap = source.scaled(pixel, pixel, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def spaced_header(text, size=11, color="#9a9ea6", spacing=1.2):
    """Uppercase section caption with letter spacing, like the mockup's h3/h4.

    ``size`` is in pixels (the mockup's px values are used directly).
    """
    label = QtWidgets.QLabel(text.upper())
    font = label.font()
    font.setPixelSize(size)
    font.setBold(True)
    font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, spacing)
    label.setFont(font)
    label.setStyleSheet("color: {}; background: transparent;".format(color))
    return label


def kbd_pixmap(text="Ctrl+K"):
    """Paint the mockup's .kbd hint chip as a pixmap at readable size.

    Painted at plain 1x logical size (56x22, 12px text). A 2x
    devicePixelRatio pixmap was tried first, but PySide6's QLabel drops
    the DPR when storing it and displays the pixmap at 2x — clipped and
    unreadable. 1x is correct on every platform; use as a QLabel pixmap
    inside the search box (a QLineEdit action icon would be squashed
    into the ~16px icon box).
    """
    px_w, px_h = 56, 22
    pixmap = QtGui.QPixmap(px_w, px_h)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QtGui.QPen(QtGui.QColor("#3a3c40"), 1))
    painter.setBrush(QtGui.QColor("#26272a"))
    painter.drawRoundedRect(1, 1, px_w - 2, px_h - 3, 3, 3)
    painter.setPen(QtGui.QPen(QtGui.QColor("#c9ccd1")))
    font = painter.font()
    font.setPixelSize(12)
    font.setBold(False)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), QtCore.Qt.AlignCenter, text)
    painter.end()
    return pixmap



def dim_effect(widget, opacity=None):
    """Mockup's .dim rows (delivered/hold entries) — WITHOUT QGraphicsEffect.

    Graphics effects over subtrees containing QSS-styled children render
    those backgrounds black/transparent (QTBUG-31045) — the exact bug
    that made the standalone window transparent on real Windows, while
    every offscreen render looked fine. Dimming is therefore done with a
    dynamic property + stylesheet rules (theme.py's [dim="true"] rules)
    instead of an effect. ``opacity`` is accepted for call-site
    compatibility and ignored.
    """
    widget.setProperty("dim", True)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    return widget


class WeekBars(QtWidgets.QWidget):
    """The mockup's .week chart: 7 accent bars, 44px tall, values 0..1."""

    def __init__(self, values=None, width=200, parent=None):
        super(WeekBars, self).__init__(parent)
        self._values = list(values or [])
        self.setFixedSize(width, 44)

    def set_values(self, values):
        self._values = list(values or [])
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)
        gap = 4
        count = 7
        bar_w = (self.width() - gap * (count - 1)) / count
        peak = max(self._values) if self._values else 0.0
        for i in range(count):
            value = self._values[i] if i < len(self._values) else 0.0
            frac = (value / peak) if peak > 0 else 0.0
            frac = max(frac, 0.06) if value > 0 else 0.0
            h = max(4, int((self.height() - 2) * frac)) if frac else 4
            x = i * (bar_w + gap)
            rect = QtCore.QRectF(x, self.height() - h, bar_w, h)
            painter.setBrush(QtGui.QColor(240, 160, 67, 36))  # accent-dim
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(rect)
            painter.setBrush(QtCore.Qt.NoBrush)
            pen = QtGui.QPen(QtGui.QColor("#f0a043"), 2)
            painter.setPen(pen)
            painter.drawLine(QtCore.QPointF(x + 1, self.height() - h),
                             QtCore.QPointF(x + bar_w - 1, self.height() - h))
        painter.end()
def global_pos(event):
    """Mouse event position in global coordinates (Qt 5 / Qt 6)."""
    if hasattr(event, "globalPosition"):
        try:
            return event.globalPosition().toPoint()
        except Exception:
            pass
    return event.globalPos()


class ShellTitleBar(QtWidgets.QFrame):
    """Mockup-style window title bar: draggable, double-click maximizes."""

    def __init__(self, on_min, on_max, on_close, standalone, parent=None):
        super(ShellTitleBar, self).__init__(parent)
        self.setObjectName("ShellTitlebar")
        self._drag_pos = None
        self._on_min = on_min
        self._on_max = on_max
        self._standalone = standalone
        self.setFixedHeight(42)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Fixed)
        if standalone:
            self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_pos = global_pos(event) - self.window().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & QtCore.Qt.LeftButton:
            self.window().move(global_pos(event) - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        event.ignore()

    def mouseDoubleClickEvent(self, event):
        if self._standalone and self._on_max is not None:
            self._on_max()
        event.accept()
