"""Dialogs used by the Snapshot Browser panel."""

from __future__ import annotations

import datetime as _dt

from snapbrowser import core, nkparse
from snapbrowser.qt import QtCore, QtGui, QtWidgets

STATUS_COLORS = {
    nkparse.ADDED: "#81c784",
    nkparse.REMOVED: "#e57373",
    nkparse.CHANGED: "#ffd54f",
    nkparse.RENAMED: "#64b5f6",
    core.HISTORY_FIRST: "#b0b0b0",
}
STATUS_LABELS = {
    nkparse.ADDED: "Added",
    nkparse.REMOVED: "Removed",
    nkparse.CHANGED: "Changed",
    nkparse.RENAMED: "Renamed",
    core.HISTORY_FIRST: "Earliest state",
}
STATUS_FILTER = [None, nkparse.ADDED, nkparse.REMOVED, nkparse.CHANGED, nkparse.RENAMED]
ROLE_DIFF = getattr(QtCore.Qt.UserRole, "value", QtCore.Qt.UserRole) + 10
ROLE_KNOB = ROLE_DIFF + 1
MUTED = "color: #8a8a8a;"


def _tooltip(value, is_input=False):
    if value is None:
        return "(not connected)" if is_input else "(default)"
    return value if len(value) <= 2000 else value[:2000] + "\n\u2026"


def _change_item(change, node, index):
    """Tree row for one knob or connection change."""
    before, after = nkparse.describe(change, node)
    child = QtWidgets.QTreeWidgetItem([change.knob, "", before, after])
    child.setData(0, ROLE_DIFF, index)
    child.setData(0, ROLE_KNOB, change.knob)
    child.setToolTip(2, _tooltip(change.old, change.is_input))
    child.setToolTip(3, _tooltip(change.new, change.is_input))
    grey = QtGui.QBrush(QtGui.QColor("#777"))
    if change.old is None:
        child.setForeground(2, grey)
    if change.new is None:
        child.setForeground(3, grey)
    if change.is_input:
        child.setForeground(0, QtGui.QBrush(QtGui.QColor("#90caf9")))
    return child


def _plural(count, word):
    return "{} {}{}".format(count, word, "" if count == 1 else "s")


# --------------------------------------------------------------------------
# Script compare
# --------------------------------------------------------------------------

class CompareDialog(QtWidgets.QDialog):
    """Node and knob differences between two scripts.

    ``newer_is_live`` means the newer side is the script open in Nuke, which
    enables reverting knobs onto it.
    """

    def __init__(self, backend, older_label, older_text, newer_label, newer_text,
                 newer_is_live=False, parent=None, on_history=None):
        super().__init__(parent)
        self.backend = backend
        self.newer_is_live = newer_is_live
        self.on_history = on_history
        self._older = nkparse.parse(older_text)
        self._newer = nkparse.parse(newer_text)
        self._diffs = []

        self.setWindowTitle("Compare Scripts")
        self.resize(980, 640)

        sides = QtWidgets.QLabel(
            "<b>Older:</b> {}&nbsp;&nbsp;&nbsp;→&nbsp;&nbsp;&nbsp;<b>Newer:</b> {}".format(
                _escape(older_label), _escape(newer_label)))
        sides.setWordWrap(True)

        self.summary_label = QtWidgets.QLabel()

        self.ignore_layout = QtWidgets.QCheckBox("Ignore position and selection")
        self.ignore_layout.setChecked(True)
        self.ignore_layout.toggled.connect(self._recompute)

        self.status_filter = QtWidgets.QComboBox()
        self.status_filter.addItems(["All changes", "Added", "Removed", "Changed", "Renamed"])
        self.status_filter.currentIndexChanged.connect(self._apply_filter)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Filter nodes or knobs...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)

        options = QtWidgets.QHBoxLayout()
        options.addWidget(self.summary_label, 1)
        options.addWidget(self.ignore_layout)
        options.addWidget(self.status_filter)
        options.addWidget(self.search)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Node / Knob", "Class", "Older", "Newer"])
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 240)
        self.tree.setColumnWidth(1, 110)
        self.tree.setColumnWidth(2, 280)
        self.tree.itemSelectionChanged.connect(self._update_buttons)

        self.select_button = QtWidgets.QPushButton("Select In Node Graph")
        self.select_button.setToolTip("Select the listed nodes (or the selected rows) in the open script")
        self.select_button.clicked.connect(self._select_in_graph)
        self.revert_button = QtWidgets.QPushButton("Revert")
        self.revert_button.setToolTip("Put the older knob values, connections and names back "
                                      "on the live nodes (whole nodes or the selected rows)")
        self.revert_button.clicked.connect(self._revert)
        self.paste_older_button = QtWidgets.QPushButton("Paste Older Node")
        self.paste_older_button.setToolTip("Paste the older version of the node, disconnected")
        self.paste_older_button.clicked.connect(lambda: self._paste(older=True))
        self.paste_newer_button = QtWidgets.QPushButton("Paste Newer Node")
        self.paste_newer_button.clicked.connect(lambda: self._paste(older=False))
        self.history_button = QtWidgets.QPushButton("Node History")
        self.history_button.setToolTip("Every saved state of the selected node")
        self.history_button.clicked.connect(self._show_history)
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(self.accept)

        in_nuke = getattr(backend, "IN_NUKE", False)
        self.select_button.setVisible(in_nuke)
        self.revert_button.setVisible(in_nuke and newer_is_live)
        self.paste_older_button.setVisible(in_nuke)
        self.paste_newer_button.setVisible(in_nuke and not newer_is_live)
        self.history_button.setVisible(on_history is not None)

        buttons = QtWidgets.QHBoxLayout()
        for button in (self.select_button, self.revert_button, self.paste_older_button,
                       self.paste_newer_button, self.history_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)

        self.note = QtWidgets.QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet(MUTED)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(sides)
        layout.addLayout(options)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.note)
        layout.addLayout(buttons)

        self._recompute()

    # -- data -------------------------------------------------------------

    def _recompute(self, *args):
        ignore = nkparse.LAYOUT_KNOBS if self.ignore_layout.isChecked() else ()
        self._diffs = nkparse.diff(self._older, self._newer, ignore)
        self._fill()

    def _reload_live(self):
        if self.newer_is_live:
            self._newer = nkparse.parse(self.backend.current_state_text())
            self._recompute()

    def _fill(self):
        self.tree.clear()
        counts = nkparse.summary(self._diffs)
        if not self._diffs:
            self.summary_label.setText("No differences.")
        else:
            self.summary_label.setText("  \u00b7  ".join(
                "<span style='color:{}'>{} {}</span>".format(STATUS_COLORS[k], counts[k], STATUS_LABELS[k].lower())
                for k in nkparse.STATUSES if counts[k]))
        if self._older.connections_ok and self._newer.connections_ok:
            self.note.setText("Blue rows are connection changes. Renamed nodes are matched by class and knob values.")
        else:
            self.note.setText("Connections could not be read from one of the scripts, so only knobs are compared.")

        for index, item_diff in enumerate(self._diffs):
            title = item_diff.path
            if item_diff.status == nkparse.RENAMED:
                title = "{}  (was {})".format(item_diff.path, item_diff.old_path)
            node_item = QtWidgets.QTreeWidgetItem([title, item_diff.cls, "", ""])
            node_item.setData(0, ROLE_DIFF, index)
            node_item.setForeground(0, QtGui.QBrush(QtGui.QColor(STATUS_COLORS[item_diff.status])))
            font = node_item.font(0)
            font.setBold(True)
            node_item.setFont(0, font)
            if item_diff.status == nkparse.ADDED:
                node_item.setText(3, "Added")
            elif item_diff.status == nkparse.REMOVED:
                node_item.setText(2, "Removed")
            else:
                node_item.setText(2, _plural(len(item_diff.changes), "change"))

            node = item_diff.new or item_diff.old
            for change in item_diff.changes:
                node_item.addChild(_change_item(change, node, index))

            self.tree.addTopLevelItem(node_item)
            node_item.setExpanded(item_diff.status != nkparse.ADDED and len(item_diff.changes) <= 12)

        self._apply_filter()
        self._update_buttons()

    def _apply_filter(self, *args):
        wanted = STATUS_FILTER[self.status_filter.currentIndex()]
        text = self.search.text().strip().lower()
        for row in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(row)
            item_diff = self._diffs[item.data(0, ROLE_DIFF)]
            status_ok = wanted is None or item_diff.status == wanted
            node_match = not text or text in item_diff.path.lower() or text in item_diff.cls.lower() \
                or text in item_diff.old_path.lower()
            any_child = False
            for c in range(item.childCount()):
                child = item.child(c)
                child_match = node_match or text in child.text(0).lower()
                child.setHidden(not child_match)
                any_child = any_child or child_match
            item.setHidden(not status_ok or not (node_match or any_child))

    # -- selection helpers ----------------------------------------------

    def _selected(self):
        """{diff index: set of knob names or None for the whole node}."""
        result = {}
        for item in self.tree.selectedItems():
            index = item.data(0, ROLE_DIFF)
            knob = item.data(0, ROLE_KNOB)
            if knob is None:
                result[index] = None
            elif result.get(index, set()) is not None:
                result.setdefault(index, set()).add(knob)
        return result

    def _update_buttons(self):
        selected = self._selected()
        diffs = [self._diffs[i] for i in selected]
        self.revert_button.setEnabled(any(d.status in (nkparse.CHANGED, nkparse.RENAMED) for d in diffs))
        self.history_button.setEnabled(len(diffs) == 1)
        self.paste_older_button.setEnabled(any(d.old is not None for d in diffs))
        self.paste_newer_button.setEnabled(any(d.new is not None for d in diffs))
        self.select_button.setEnabled(bool(self._diffs))

    # -- actions ----------------------------------------------------------

    def _select_in_graph(self):
        selected = self._selected()
        items = [self._diffs[i] for i in selected] if selected else self._diffs
        paths = [d.path for d in items]
        found = self.backend.select_nodes(paths)
        missing = len(paths) - found
        message = "Selected {} node{}.".format(found, "" if found == 1 else "s")
        if missing:
            message += " {} not in the open script.".format(missing)
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), message, self)

    def _revert(self):
        applied_total = 0
        skipped_total = []
        for index, knobs in self._selected().items():
            item_diff = self._diffs[index]
            if item_diff.status not in (nkparse.CHANGED, nkparse.RENAMED):
                continue
            changes = [c for c in item_diff.changes if knobs is None or c.knob in knobs]
            applied, skipped = self.backend.revert_knobs(item_diff.path, changes)
            applied_total += applied
            skipped_total += ["{}: {}".format(item_diff.path, k) for k in skipped]
        message = "Reverted {}.".format(_plural(applied_total, "change"))
        if skipped_total:
            message += "\n\nNot reverted (user knobs, class changes or missing nodes):\n" + \
                "\n".join(skipped_total[:20])
            QtWidgets.QMessageBox.information(self, "Revert", message)
        else:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), message, self)
        self._reload_live()

    def _show_history(self):
        selected = list(self._selected())
        if len(selected) == 1 and self.on_history is not None:
            self.on_history(self._diffs[selected[0]].path)

    def _paste(self, older):
        count = 0
        for index in self._selected():
            item_diff = self._diffs[index]
            node = item_diff.old if older else item_diff.new
            if node is None:
                continue
            if self.backend.paste_node(node.snippet(), node.parent):
                count += 1
        if count:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(),
                                        "Pasted {} node{}.".format(count, "" if count == 1 else "s"), self)
            self._reload_live()


# --------------------------------------------------------------------------
# Node history
# --------------------------------------------------------------------------

def _format_when(stamp):
    local = stamp.astimezone()
    today = _dt.datetime.now().astimezone().date()
    if local.date() == today:
        return "Today " + local.strftime("%H:%M")
    if local.date() == today - _dt.timedelta(days=1):
        return "Yesterday " + local.strftime("%H:%M")
    return local.strftime("%d %b %Y %H:%M")


def open_node_history(backend, script, node_path, parent=None):
    """Read every saved state of ``script`` and show the history of one node."""
    entries = core.build_timeline(script)
    live = backend.current_state_text() if getattr(backend, "IN_NUKE", False) else None
    sources = core.history_sources(entries, live, "Current script (unsaved changes included)")

    progress = QtWidgets.QProgressDialog("Reading saved states...", "Cancel", 0, len(sources), parent)
    progress.setWindowTitle("Node History")
    progress.setWindowModality(QtCore.Qt.WindowModal)
    progress.setMinimumDuration(400)

    def tick(done, total):
        progress.setValue(done)
        QtWidgets.QApplication.processEvents()
        return not progress.wasCanceled()

    try:
        events = core.node_history(sources, node_path, progress=tick)
    finally:
        progress.close()
    NodeHistoryDialog(backend, node_path, sources, events, parent).exec()


class NodeHistoryDialog(QtWidgets.QDialog):
    """Every saved state in which one node changed, newest first."""

    def __init__(self, backend, node_path, sources, events, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.node_path = node_path
        self.sources = sources
        self.events = events
        self.in_nuke = getattr(backend, "IN_NUKE", False)

        self.setWindowTitle("Node History - " + node_path)
        self.resize(940, 600)

        self.heading = QtWidgets.QLabel()
        self.heading.setWordWrap(True)

        self.ignore_layout = QtWidgets.QCheckBox("Ignore position and selection")
        self.ignore_layout.setChecked(True)
        self.ignore_layout.toggled.connect(self._recompute)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.heading, 1)
        top.addWidget(self.ignore_layout)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["When / Knob", "Saved state", "Before", "After"])
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 200)
        self.tree.setColumnWidth(1, 250)
        self.tree.setColumnWidth(2, 220)
        self.tree.itemSelectionChanged.connect(self._update_buttons)

        self.apply_button = QtWidgets.QPushButton("Apply This State")
        self.apply_button.setToolTip("Set the live node's knobs and connections to how they were here")
        self.apply_button.clicked.connect(self._apply_state)
        self.paste_button = QtWidgets.QPushButton("Paste This Version")
        self.paste_button.setToolTip("Paste the node as it was here, disconnected")
        self.paste_button.clicked.connect(self._paste)
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(self.accept)
        self.apply_button.setVisible(self.in_nuke)
        self.paste_button.setVisible(self.in_nuke)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.paste_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)

        note = QtWidgets.QLabel("A renamed node starts a new history under its new name.")
        note.setStyleSheet(MUTED)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.tree, 1)
        layout.addWidget(note)
        layout.addLayout(buttons)
        self._fill()

    def _recompute(self, *args):
        ignore = nkparse.LAYOUT_KNOBS if self.ignore_layout.isChecked() else ()
        self.events = core.node_history(self.sources, self.node_path, ignore)
        self._fill()

    def _reload_live(self):
        if self.sources and self.sources[-1].text is not None:
            self.sources[-1].text = self.backend.current_state_text()
        self._recompute()

    def _fill(self):
        selected = self._selected_event() if self.tree.topLevelItemCount() else None
        selected_source = selected.source if selected is not None else None
        reselect = None
        self.tree.clear()
        changes = sum(1 for e in self.events if e.status != core.HISTORY_FIRST)
        if not self.events:
            summary = "This node was not found in any saved state."
        else:
            first = self.events[0]
            summary = "{} across {} saved states. First seen in {}, {}.".format(
                _plural(changes, "change"), len(self.sources), _escape(first.source.label),
                _format_when(first.source.time))
        self.heading.setText("<b>{}</b><br>{}".format(_escape(self.node_path), summary))

        for index in range(len(self.events) - 1, -1, -1):
            event = self.events[index]
            label = event.source.label
            if event.source.note:
                label += "  \u2014 " + event.source.note
            status = STATUS_LABELS[event.status]
            if event.status == nkparse.CHANGED:
                status = _plural(len(event.changes), "change")
            item = QtWidgets.QTreeWidgetItem([_format_when(event.source.time), label, status, ""])
            item.setData(0, ROLE_DIFF, index)
            item.setToolTip(1, label)
            item.setForeground(2, QtGui.QBrush(QtGui.QColor(STATUS_COLORS[event.status])))
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            node = event.node or event.previous
            for change in event.changes:
                item.addChild(_change_item(change, node, index))
            self.tree.addTopLevelItem(item)
            item.setExpanded(len(event.changes) <= 12)
            if selected_source is not None and event.source is selected_source:
                reselect = item
        if reselect is not None:
            self.tree.setCurrentItem(reselect)
        self._update_buttons()

    def _selected_event(self):
        items = self.tree.selectedItems()
        if not items:
            return None
        index = items[0].data(0, ROLE_DIFF)
        return self.events[index] if index is not None else None

    def _update_buttons(self):
        event = self._selected_event()
        has_state = event is not None and event.node is not None
        self.apply_button.setEnabled(has_state)
        self.paste_button.setEnabled(has_state)

    def _apply_state(self):
        event = self._selected_event()
        if event is None or event.node is None:
            return
        live = nkparse.parse(self.backend.current_state_text())
        current = live.get(self.node_path)
        if current is None:
            if self.backend.paste_node(event.node.snippet(), event.node.parent):
                QtWidgets.QToolTip.showText(QtGui.QCursor.pos(),
                                            "The node was not in the script, so it was pasted.", self)
            self._reload_live()
            return

        changes = nkparse.node_changes(event.node, current, nkparse.LAYOUT_KNOBS, live.connections_ok)
        if not changes:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "The node already matches this state.", self)
            return
        applied, skipped = self.backend.revert_knobs(self.node_path, changes)
        message = "Applied {}.".format(_plural(applied, "change"))
        if skipped:
            QtWidgets.QMessageBox.information(
                self, "Apply This State",
                message + "\n\nNot applied (user knobs, class changes or missing nodes):\n" +
                "\n".join(skipped[:20]))
        else:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), message, self)
        self._reload_live()

    def _paste(self):
        event = self._selected_event()
        if event is not None and event.node is not None:
            if self.backend.paste_node(event.node.snippet(), event.node.parent):
                QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "Pasted.", self)


# --------------------------------------------------------------------------
# Image compare
# --------------------------------------------------------------------------

class WipeView(QtWidgets.QWidget):
    def __init__(self, older, newer, parent=None):
        super().__init__(parent)
        self._a = older
        self._b = newer
        self._split = 0.5
        self.side_by_side = False
        self.setMinimumSize(560, 320)
        self.setCursor(QtCore.Qt.SizeHorCursor)

    def set_side_by_side(self, value):
        self.side_by_side = bool(value)
        self.setCursor(QtCore.Qt.ArrowCursor if value else QtCore.Qt.SizeHorCursor)
        self.update()

    @staticmethod
    def _fit(size, area):
        if size.isEmpty():
            return QtCore.QRect(area)
        scaled = size.scaled(area.size(), QtCore.Qt.KeepAspectRatio)
        x = area.x() + (area.width() - scaled.width()) // 2
        y = area.y() + (area.height() - scaled.height()) // 2
        return QtCore.QRect(x, y, scaled.width(), scaled.height())

    def _target(self):
        return self._fit(self._a.size(), self.rect().adjusted(8, 8, -8, -28))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QtGui.QColor(24, 24, 24))
        label_y = self.height() - 10
        painter.setPen(QtGui.QColor(160, 160, 160))

        if self.side_by_side:
            half = self.rect().adjusted(8, 8, -8, -28)
            left = QtCore.QRect(half.x(), half.y(), half.width() // 2 - 4, half.height())
            right = QtCore.QRect(left.right() + 8, half.y(), left.width(), half.height())
            painter.drawPixmap(self._fit(self._a.size(), left), self._a)
            painter.drawPixmap(self._fit(self._b.size(), right), self._b)
            painter.drawText(left.x(), label_y, "Older")
            painter.drawText(right.x(), label_y, "Newer")
            return

        target = self._target()
        split_x = target.x() + int(target.width() * self._split)
        painter.drawPixmap(target, self._a)
        painter.save()
        painter.setClipRect(QtCore.QRect(split_x, target.y(), target.right() - split_x + 1, target.height()))
        painter.drawPixmap(target, self._b)
        painter.restore()
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 1))
        painter.drawLine(split_x, target.top(), split_x, target.bottom())
        painter.setPen(QtGui.QColor(160, 160, 160))
        painter.drawText(target.x(), label_y, "← Older")
        painter.drawText(target.right() - 60, label_y, "Newer →")

    def _drag(self, event):
        if self.side_by_side:
            return
        target = self._target()
        x = event.position().x() if hasattr(event, "position") else event.x()
        if target.width() > 0:
            self._split = min(1.0, max(0.0, (x - target.x()) / float(target.width())))
            self.update()

    def mousePressEvent(self, event):
        self._drag(event)

    def mouseMoveEvent(self, event):
        self._drag(event)


class ImageCompareDialog(QtWidgets.QDialog):
    def __init__(self, older_path, older_label, newer_path, newer_label, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare Thumbnails")
        self.resize(900, 560)

        self.view = WipeView(QtGui.QPixmap(older_path), QtGui.QPixmap(newer_path))

        side = QtWidgets.QCheckBox("Side by side")
        side.toggled.connect(self.view.set_side_by_side)

        labels = QtWidgets.QLabel("<b>Older:</b> {}&nbsp;&nbsp;&nbsp;<b>Newer:</b> {}".format(
            _escape(older_label), _escape(newer_label)))
        labels.setWordWrap(True)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(labels, 1)
        top.addWidget(side)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.view, 1)
        hint = QtWidgets.QLabel("Drag across the image to move the wipe.")
        hint.setStyleSheet(MUTED)
        layout.addWidget(hint)


# --------------------------------------------------------------------------
# Clean up
# --------------------------------------------------------------------------

class CleanupDialog(QtWidgets.QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Clean Up Snapshots")

        self.days = QtWidgets.QSpinBox()
        self.days.setRange(0, 3650)
        self.days.setValue(14)
        self.days.setSuffix(" days")
        self.days.valueChanged.connect(self._update_preview)

        self.include_manual = QtWidgets.QCheckBox("Include manual snapshots")
        self.include_manual.toggled.connect(self._update_preview)

        self.preview = QtWidgets.QLabel()
        self.usage = QtWidgets.QLabel()
        self.usage.setStyleSheet(MUTED)

        form = QtWidgets.QFormLayout()
        form.addRow("Delete snapshots older than", self.days)
        form.addRow("", self.include_manual)

        note = QtWidgets.QLabel("Starred snapshots are always kept.")
        note.setStyleSheet(MUTED)

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("Delete")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("<b>{}</b>".format(_escape(store.key))))
        layout.addWidget(self.usage)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(self.preview)
        layout.addWidget(self.buttons)
        self._update_preview()

    def candidates(self):
        limit = _dt.datetime.now().astimezone() - _dt.timedelta(days=self.days.value())
        manual = self.include_manual.isChecked()
        return [s for s in self.store.list()
                if not s.starred and s.created < limit and (manual or s.is_automatic)]

    def _update_preview(self, *args):
        self.usage.setText("Snapshot folder uses {}".format(core.format_size(self.store.disk_usage())))
        items = self.candidates()
        size = 0
        for snap in items:
            for path in snap.files():
                try:
                    size += QtCore.QFileInfo(path).size()
                except Exception:
                    pass
        self.preview.setText("{} snapshot{} will be deleted, freeing {}.".format(
            len(items), "" if len(items) == 1 else "s", core.format_size(size)))
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(bool(items))

    def values(self):
        return self.days.value(), self.include_manual.isChecked()


# --------------------------------------------------------------------------
# Work history
# --------------------------------------------------------------------------

def _format_duration(delta):
    minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return "{} h {:02d} min".format(hours, minutes)
    return "{} min".format(minutes)


class HistoryDialog(QtWidgets.QDialog):
    def __init__(self, title, times, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Work History")
        self.resize(560, 460)

        sessions = core.work_sessions(times)
        total = sum((s.duration for s in sessions), _dt.timedelta())
        days = len({s.start.date() for s in sessions})

        heading = QtWidgets.QLabel("<b>{}</b><br>About {} over {} session{} on {} day{}".format(
            _escape(title), _format_duration(total), len(sessions), "" if len(sessions) == 1 else "s",
            days, "" if days == 1 else "s"))

        table = QtWidgets.QTreeWidget()
        table.setRootIsDecorated(False)
        table.setAlternatingRowColors(True)
        table.setHeaderLabels(["Date", "From", "To", "Duration", "Saves & snapshots"])
        for session in sessions:
            start = session.start.astimezone()
            end = session.end.astimezone()
            table.addTopLevelItem(QtWidgets.QTreeWidgetItem([
                start.strftime("%a %d %b %Y"),
                start.strftime("%H:%M"),
                end.strftime("%H:%M") if end.date() == start.date() else end.strftime("%d %b %H:%M"),
                _format_duration(session.duration),
                str(session.events),
            ]))
        for column, width in enumerate((130, 60, 90, 90)):
            table.setColumnWidth(column, width)

        note = QtWidgets.QLabel("Estimated from snapshot and save times. Gaps over 30 minutes start a new session.")
        note.setWordWrap(True)
        note.setStyleSheet(MUTED)

        close = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        close.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(table, 1)
        layout.addWidget(note)
        layout.addWidget(close)


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, values, in_nuke=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Snapshot Browser Settings")

        self.interval = QtWidgets.QSpinBox()
        self.interval.setRange(0, 240)
        self.interval.setSuffix(" min")
        self.interval.setSpecialValueText("Off")
        self.interval.setValue(int(values.get("auto_interval_minutes") or 0))

        self.keep = QtWidgets.QSpinBox()
        self.keep.setRange(1, 999)
        self.keep.setValue(int(values.get("keep_automatic") or 20))
        self.keep.setToolTip("Per kind (auto, on save, render, before restore). "
                             "Manual and starred snapshots are always kept.")

        self.on_save = QtWidgets.QCheckBox("Snapshot every time the script is saved")
        self.on_save.setChecked(bool(values.get("snapshot_on_save")))
        self.thumbnails = QtWidgets.QCheckBox("Capture a viewer thumbnail")
        self.thumbnails.setChecked(bool(values.get("thumbnails")))
        self.ask_note = QtWidgets.QCheckBox("Ask for a note when taking a snapshot")
        self.ask_note.setChecked(bool(values.get("ask_note")))

        self.compress = QtWidgets.QCheckBox("Store snapshots compressed (.nk.gz)")
        self.compress.setChecked(bool(values.get("compress_snapshots", True)))

        self.hotkey = QtWidgets.QLineEdit(values.get("hotkey") or "")
        self.hotkey.setPlaceholderText("e.g. ctrl+alt+s")
        self.hotkey.setToolTip("Takes effect after restarting Nuke")

        form = QtWidgets.QFormLayout()
        form.addRow("Auto snapshot every", self.interval)
        form.addRow("Keep automatic snapshots", self.keep)
        form.addRow("", self.on_save)
        form.addRow("", self.thumbnails)
        form.addRow("", self.ask_note)
        form.addRow("", self.compress)
        form.addRow("Hotkey", self.hotkey)
        for widget in (self.interval, self.on_save, self.thumbnails, self.hotkey):
            widget.setEnabled(in_nuke)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        if not in_nuke:
            hint = QtWidgets.QLabel("Greyed-out settings only apply inside Nuke.")
            hint.setStyleSheet(MUTED)
            layout.addWidget(hint)
        layout.addWidget(buttons)

    def values(self):
        return {
            "auto_interval_minutes": self.interval.value(),
            "keep_automatic": self.keep.value(),
            "snapshot_on_save": self.on_save.isChecked(),
            "thumbnails": self.thumbnails.isChecked(),
            "ask_note": self.ask_note.isChecked(),
            "hotkey": self.hotkey.text().strip(),
            "compress_snapshots": self.compress.isChecked(),
        }


def _escape(text) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
