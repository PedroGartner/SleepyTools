"""Shared dark theme palette for the suite.

Tools can adopt this for a consistent look by calling:
    from SleepyCore.themes import apply
    apply(my_widget)
"""

from SleepyCore.qt import QtWidgets, QtGui, QtCore


# Dark palette matching the Text Editor's theme
DARK_PALETTE = {
    "window": "#161719",
    "window_text": "#e6e6e6",
    "base": "#1e1f22",
    "alternate_base": "#26272a",
    "tool_tip_base": "#2a2b2e",
    "tool_tip_text": "#e6e6e6",
    "text": "#e6e6e6",
    "button": "#26272a",
    "button_text": "#e6e6e6",
    "bright_text": "#ffffff",
    "highlight": "#f0a043",
    "highlighted_text": "#161719",
    "link": "#f0a043",
}


def get_palette():
    """Return a QPalette with the dark theme."""
    pal = QtGui.QPalette()
    for role_name, color in DARK_PALETTE.items():
        role = getattr(QtGui.QPalette, role_name.capitalize(), None)
        if role is not None:
            pal.setColor(role, QtGui.QColor(color))
    return pal


def apply(widget):
    """Apply the dark theme to a widget and its children."""
    widget.setPalette(get_palette())
    # Ensure child widgets inherit
    for child in widget.findChildren(QtWidgets.QWidget):
        child.setPalette(get_palette())


def widget_style():
    """Return a QSS string for the dark theme (for Text Editor compatibility)."""
    return (
        "QWidget { background-color: %s; color: %s; }"
        "QPlainTextEdit, QTextEdit, QLineEdit { background-color: %s; color: %s; "
        "selection-background-color: %s; }"
        "QPushButton { background-color: %s; color: %s; border: 1px solid #3a3c40; "
        "padding: 4px 8px; border-radius: 3px; }"
        "QPushButton:hover { background-color: #323438; }"
        "QPushButton:pressed { background-color: #3d4045; }"
        "QComboBox { background-color: %s; color: %s; border: 1px solid #3a3c40; "
        "padding: 2px 18px 2px 6px; }"
        "QComboBox::drop-down { border: none; }"
        "QTabWidget::pane { border: 1px solid #3a3c40; }"
        "QTabBar::tab { background: %s; color: %s; padding: 6px 12px; "
        "border: 1px solid #3a3c40; border-bottom: none; }"
        "QTabBar::tab:selected { background: %s; }"
        "QSplitter::handle { background: #3a3c40; }"
        "QScrollBar:vertical { background: %s; width: 12px; }"
        "QScrollBar::handle:vertical { background: #4a4c50; min-height: 20px; }"
    ) % (
        DARK_PALETTE["window"], DARK_PALETTE["window_text"],
        DARK_PALETTE["base"], DARK_PALETTE["text"], DARK_PALETTE["highlight"],
        DARK_PALETTE["button"], DARK_PALETTE["button_text"],
        DARK_PALETTE["base"], DARK_PALETTE["text"],
        DARK_PALETTE["button"], DARK_PALETTE["window_text"],
        DARK_PALETTE["alternate_base"],
        DARK_PALETTE["base"],
    )


def button_style():
    """Return a QSS string for buttons (for Text Editor compatibility)."""
    return (
        "QPushButton { background-color: %s; color: %s; border: 1px solid #3a3c40; "
        "padding: 4px 8px; border-radius: 3px; }"
        "QPushButton:hover { background-color: #323438; }"
        "QPushButton:pressed { background-color: #3d4045; }"
    ) % (DARK_PALETTE["button"], DARK_PALETTE["button_text"])