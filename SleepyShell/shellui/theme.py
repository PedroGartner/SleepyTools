"""Theming for Sleepy Shell.

Palette mirrors SleepyCore.themes and the HTML mockup exactly:
window #161719, side panels #191a1c, chrome strips #121314, base cards
#1e1f22, accent #f0a043. The accent is parametric so Preferences can
recolor the whole Shell. "Follow Nuke" mode skips the stylesheet so
the panel blends with the host's native palette.

QSS notes:
- rgba() colors are written with PERCENT alpha ("rgba(240,160,67,14%)").
  Qt style sheets read the CSS-style float/percent form; a bare 0-255
  int is not the CSS alpha and renders wrong.
- Plain QWidget containers only paint a stylesheet background when
  WA_StyledBackground is set; pages mark themselves via widgets.styled().
- QGraphicsDropShadowEffect must never wrap subtrees that contain
  styled children (QTBUG-31045 renders those backgrounds black) — the
  mockup shadow is dropped in favour of clean 1px borders.
"""

import os

from SleepyCore.qt import QtGui

DARK = {
    "window": "#161719",
    "base": "#1e1f22",
    "alt": "#26272a",
    "alt2": "#2e3033",
    "line": "#3a3c40",
    "line_soft": "#2a2c30",
    "text": "#e6e6e6",
    "dim": "#9a9ea6",
    # mockup-only surfaces
    "side": "#191a1c",       # sidebar, setnav, board groups/columns
    "chrome": "#121314",     # titlebar + statusbar strips
    "hover": "#323438",      # .btn:hover
    "hover_soft": "#1f2022", # .proj:hover / .snav:hover
    "active": "#222326",     # .proj.active / .snav.on
}

LIGHT = {
    "window": "#e9eaec",
    "base": "#f4f5f6",
    "alt": "#e0e2e5",
    "alt2": "#d5d8db",
    "line": "#b8bcc2",
    "line_soft": "#cdd1d6",
    "text": "#1d1f22",
    "dim": "#5c6167",
    "side": "#f0f1f3",
    "chrome": "#e2e4e7",
    "hover": "#d8dbdf",
    "hover_soft": "#e9ebee",
    "active": "#e2e5e9",
}

STATUS_COLORS = {
    "wip": "#f0a043",
    "waiting": "#c9a75b",
    "review": "#5b9dd9",
    "approved": "#6fbf73",
    "delivered": "#8a8f98",
    "hold": "#d96b5b",
}

ACCENTS = ["#f0a043", "#4fb8a8", "#5b9dd9", "#6fbf73", "#d96b5b", "#a88bd9"]

ACCENT_NAMES = {
    "#f0a043": "Sleepy Orange (default)",
    "#4fb8a8": "Teal",
    "#5b9dd9": "Blue",
    "#6fbf73": "Green",
    "#d96b5b": "Red",
    "#a88bd9": "Purple",
}

DENSITY = {
    "comfortable": {"pad": 6, "row": 6, "font": 0},
    "compact": {"pad": 3, "row": 3, "font": -1},
}


def mix(color, overlay, alpha):
    """Blend two #rrggbb colors; overlay at ``alpha`` (0..1) over color."""
    c1, c2 = QtGui.QColor(color), QtGui.QColor(overlay)
    r = int(c1.red() * (1 - alpha) + c2.red() * alpha)
    g = int(c1.green() * (1 - alpha) + c2.green() * alpha)
    b = int(c1.blue() * (1 - alpha) + c2.blue() * alpha)
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def rgba(color, alpha):
    """QSS-safe rgba() string from #rrggbb + 0..1 alpha (percent form)."""
    c = QtGui.QColor(color)
    return "rgba({},{},{},{:.0f}%)".format(
        c.red(), c.green(), c.blue(), max(0, min(100, alpha * 100)))


def build_qss(accent="#f0a043", mode="dark", density="comfortable", font_size=12):
    if mode == "light":
        pal = dict(LIGHT)
    else:
        pal = dict(DARK)
    d = DENSITY.get(density, DENSITY["comfortable"])
    pad = d["pad"]
    accent_dim = rgba(pal["window"], 0.14) if mode != "dark" else rgba("#161719", 0.14)
    accent_dim = rgba(pal["base"], 0.14)
    accent_soft = mix(pal["base"], accent, 0.10)
    hold = STATUS_COLORS["hold"]
    ok = STATUS_COLORS["approved"]

    return """
* {{ font-size: {fs}px; outline: none; }}
QMainWindow, QDialog {{ background: {window}; }}
QWidget {{ color: {text};
  font-family: 'Segoe UI', 'Noto Sans', sans-serif; }}
QFrame {{ background: {window}; }}
QLabel {{ background: transparent; }}
QScrollArea {{ border: none; background: {window}; }}
QScrollArea > QWidget > QWidget {{ background: {window}; }}
QScrollBar:vertical {{ background: {window}; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {line}; min-height: 24px; border-radius: 3px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {window}; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {line}; min-width: 24px; border-radius: 3px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

#ShellSearch {{ background: {window}; border: 1px solid {line}; border-radius: 4px; }}
#ShellSearch QLineEdit {{ background: transparent; border: none; font-size: {edit_fs}px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox,
QDateEdit, QListWidget {{
  background: {window}; color: {text}; border: 1px solid {line};
  border-radius: 4px; padding: {pad}px 10px; selection-background-color: {accent};
  selection-color: {window};
  font-size: {edit_fs}px; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{ background: {alt}; color: {text}; border: 1px solid {line};
  selection-background-color: {accent_dim}; }}
QSpinBox::up-button, QSpinBox::down-button, QDateEdit::up-button, QDateEdit::down-button {{
  background: {alt}; width: 14px; border: none; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus {{
  border-color: {accent}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {dim}; background: {base}; }}

QPushButton {{
  background: {alt}; color: {text}; border: 1px solid {line};
  border-radius: 3px; padding: {pad}px 12px; font-size: 12.5px; }}
QPushButton:hover {{ background: {hover}; }}
QPushButton:pressed {{ background: {accent_dim}; }}
QPushButton:disabled {{ background: {base}; color: {dim}; border-color: {line_soft}; }}
QPushButton[accent="true"] {{ background: {accent}; border-color: {accent};
  color: {window}; font-weight: 600; }}
QPushButton[accent="true"]:hover {{ background: {accent_hover}; }}
QPushButton[accent="true"]:pressed {{ background: {accent_hover}; }}
QPushButton[danger="true"] {{ background: {base}; color: {hold};
  border-color: {hold_border}; }}
QPushButton[danger="true"]:hover {{ border-color: {hold}; background: {hold_dim}; }}
QPushButton[flat="true"] {{ background: transparent; border: none; color: {dim};
  padding: 2px 6px; }}
QPushButton[flat="true"]:hover {{ color: {text}; background: {alt}; }}

QCheckBox {{ background: transparent; spacing: 7px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {line};
  border-radius: 3px; background: {window}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QCheckBox:disabled {{ color: {dim}; }}

QListWidget, QTreeWidget, QTableWidget {{ background: {window}; border: 1px solid {line_soft};
  border-radius: 4px; alternate-background-color: {alt}; }}
QListWidget::item {{ padding: {row}px 8px; }}
QListWidget::item:selected {{ background: {accent_dim}; color: {text}; }}
QListWidget::item:hover {{ background: {alt}; }}

QMenu {{ background: {alt}; color: {text}; border: 1px solid {line}; }}
QMenu::item {{ padding: 5px 24px; }}
QMenu::item:selected {{ background: {accent_dim}; }}
QMenu::separator {{ height: 1px; background: {line_soft}; margin: 3px 8px; }}

QToolTip {{ background: {alt2}; color: {text}; border: 1px solid {line}; padding: 4px; }}

QSplitter::handle {{ background: {line_soft}; }}

/* docked Nuke panel root */
#ShellPanel {{ background: {window}; }}
#ShellPanel #ShellVersionBox {{ background: {base}; border: 1px solid {line_soft};
  border-radius: 6px; }}

/* ---- window chrome -------------------------------------------------- */
#ShellWindow {{ background: {window}; border: 1px solid {line}; border-radius: 8px; }}
#ShellTitlebar {{ background: {chrome}; border-bottom: 1px solid {line_soft}; }}
#ShellTitlebar QLabel {{ background: transparent; }}
#ShellWinButton {{ background: transparent; border: none; color: {dim};
  font-size: 13px; padding: 4px 10px; border-radius: 3px; }}
#ShellWinButton:hover {{ background: {alt}; color: {text}; }}
#ShellWinButton[close="true"]:hover {{ background: {hold}; color: #ffffff; }}
#ShellStatusbar {{ background: {chrome}; border-top: 1px solid {line_soft}; }}
#ShellStatusbar QLabel {{ background: transparent; color: {dim}; font-size: 11px; }}

/* ---- sidebar --------------------------------------------------------- */
#ShellSidebar {{ background: {side}; border-right: 1px solid {line_soft}; }}
#ShellSidebar QLabel {{ background: transparent; }}
#ShellRoots {{ background: transparent; border: 1px solid {line_soft}; border-radius: 5px; }}
#ShellRoots QLabel {{ background: transparent; }}
QPushButton#ShellNavButton {{ text-align: left; padding: 8px 14px; border: none;
  border-left: 2px solid transparent; border-radius: 0; background: transparent;
  color: {text}; font-size: 12.5px; }}
QPushButton#ShellNavButton:hover {{ background: {hover_soft}; }}
QPushButton#ShellNavButton:checked {{ background: {active};
  border-left: 2px solid {accent}; font-weight: 600; }}
QPushButton#ShellSNav {{ text-align: left; padding: 8px 16px; border: none;
  border-left: 2px solid transparent; border-radius: 0; background: transparent;
  color: {text}; font-size: 12.5px; }}
QPushButton#ShellSNav:hover {{ background: {hover_soft}; }}
QPushButton#ShellSNav:checked {{ background: {active};
  border-left: 2px solid {accent}; font-weight: 600; }}

/* ---- controls --------------------------------------------------------- */
QToolButton#ShellPill {{ border: 1px solid {line}; border-radius: 16px;
  padding: 4px 12px; background: {base}; color: {text}; font-size: 11.5px; }}
QToolButton#ShellPill:hover {{ background: {alt}; }}
QToolButton#ShellPill:checked {{ border-color: {accent}; color: {accent};
  background: {accent_dim}; }}
#ShellSegGroup {{ border: 1px solid {line}; border-radius: 4px; background: {alt}; }}
#ShellSegGroup QPushButton {{ border: none; border-radius: 0; padding: 6px 13px;
  background: transparent; color: {dim}; font-size: 11.5px; }}
#ShellSegGroup QPushButton:hover {{ color: {text}; }}
#ShellSegGroup QPushButton:checked {{ background: {accent}; color: {window};
  font-weight: 600; }}
#ShellSwatch {{ border: 2px solid transparent; border-radius: 4px; background: {alt}; }}
#ShellSwatch:checked {{ border: 2px solid #ffffff; }}
QPushButton[sel2="true"] {{ background: {window}; border: 1px solid {line};
  border-radius: 4px; padding: 5px 12px; font-size: 12.5px; color: {text}; }}
QPushButton[sel2="true"]:hover {{ background: {alt}; }}
QPushButton[sel2="true"]:checked {{ border-color: {accent}; color: {accent}; }}

/* ---- cards / groups ---------------------------------------------------- */
#ShellCard {{ background: {base}; border: 1px solid {line_soft}; border-radius: 7px; }}
#ShellCard:hover {{ border: 1px solid {accent}; }}
#ShellSection {{ background: {base}; border: 1px solid {line_soft}; border-radius: 7px; }}
#ShellGroup {{ background: {side}; border: 1px solid {line_soft}; border-radius: 7px; }}
#ShellHero {{ background: {base}; border: 1px solid {line}; border-radius: 8px; }}
#ShellRow {{ background: transparent; border-radius: 5px; }}
#ShellRow:hover {{ background: {alt}; }}
/* dimmed rows/cards (delivered/hold) — property-driven, no QGraphicsEffect
   (QTBUG-31045: effects over styled subtrees knock out child backgrounds) */
#ShellRow[dim="true"] QLabel {{ color: {dim}; }}
#ShellCard[dim="true"] {{ background: {window}; border-color: {line_soft}; }}
#ShellCard[dim="true"] QLabel {{ color: {dim}; }}
#ShellVersionBox {{ background: {base}; border: 1px solid {line_soft}; border-radius: 6px; }}
#ShellVRow {{ background: transparent; border: 1px solid transparent; border-radius: 5px; }}
#ShellVRow:hover {{ background: {alt}; }}
#ShellVRow[cur="true"] {{ background: {accent_dim}; border: 1px solid {accent_border}; }}
#ShellNote {{ background: {window}; border: 1px solid {line_soft}; border-radius: 4px; }}
#ShellMChip {{ background: {window}; border: 1px solid {line_soft}; border-radius: 4px;
  padding: 4px 10px; color: {dim}; }}
#ShellBadge {{ background: {accent_dim}; color: {accent};
  border: 1px solid {accent_border}; border-radius: 3px; padding: 1px 6px;
  font-size: 9.5px; font-weight: 600; }}
#ShellPreview {{ background: {window}; border: 1px dashed {line}; border-radius: 4px; }}
#ShellFItem {{ background: {window}; border: 1px solid {line_soft}; border-radius: 4px; }}
#ShellNoteWarn {{ background: {hold_dim}; border: 1px solid {hold_border};
  border-radius: 5px; }}
#ShellNoteWarn QLabel {{ background: transparent; }}
#ShellNoteInfo {{ background: {accent_dim}; border: 1px solid {accent_border};
  border-radius: 5px; }}
#ShellNoteInfo QLabel {{ background: transparent; }}
#ShellSetNav {{ background: {side}; border-right: 1px solid {line_soft}; }}
#ShellSetNav QLabel {{ background: transparent; }}

/* ---- typography --------------------------------------------------------- */
QLabel#ShellH1 {{ font-size: {h1}px; font-weight: 600; background: transparent; }}
QLabel#ShellH2 {{ font-size: 22px; font-weight: 600; background: transparent; }}
QLabel#ShellH3 {{ font-size: 11px; font-weight: 700; color: {dim};
  background: transparent; }}
QLabel#ShellDim {{ color: {dim}; background: transparent; }}
QLabel#ShellKicker {{ color: {accent}; font-size: 10.5px; font-weight: 700;
  background: transparent; }}
""".format(
        fs=font_size, edit_fs=font_size + 2,
        h1=font_size + 8, pad=pad, row=d["row"],
        window=pal["window"], base=pal["base"], alt=pal["alt"], alt2=pal["alt2"],
        line=pal["line"], line_soft=pal["line_soft"], text=pal["text"], dim=pal["dim"],
        side=pal["side"], chrome=pal["chrome"], hover=pal["hover"],
        hover_soft=pal["hover_soft"], active=pal["active"],
        accent=accent, accent_dim=accent_dim, accent_soft=accent_soft,
        accent_hover=mix(accent, "#ffffff", 0.18),
        accent_border=rgba(accent, 0.35),
        hold=hold, hold_border=rgba(hold, 0.50), hold_dim=rgba(hold, 0.10),
        ok=ok,
    )


def status_color(status):
    return STATUS_COLORS.get(status, STATUS_COLORS["delivered"])


def apply_scale_env(prefs):
    """Set the global interface zoom BEFORE QApplication is created.

    QT_SCALE_FACTOR uniformly scales every px in the interface (styles,
    layouts, dialogs) — the only mechanism that scales hardcoded px
    sizes too. Only the standalone launcher can use it; inside Nuke the
    host process already exists, and Nuke's own scaling applies.
    """
    try:
        scale = float(prefs.get("ui_scale", 1.0) or 1.0)
    except (TypeError, ValueError):
        scale = 1.0
    if scale and abs(scale - 1.0) > 0.001:
        os.environ["QT_SCALE_FACTOR"] = "{:g}".format(scale)


def apply(app, prefs):
    """Apply appearance prefs to a QApplication."""
    mode = prefs.get("theme_mode", "dark")
    if mode == "nuke":
        app.setStyleSheet("")
    else:
        app.setStyleSheet(build_qss(prefs.get("accent", "#f0a043"), mode,
                                    prefs.get("density", "comfortable"),
                                    int(prefs.get("font_size", 12) or 12)))
    from shellui.widgets import app_logo_icon
    app.setWindowIcon(app_logo_icon(32, prefs.get("accent", "#f0a043")))
    font = app.font()
    try:
        # font_size is a px value (the mockup is px based); Qt's default
        # font stays point sized, so convert at the usual 96 dpi ratio.
        font.setPointSize(max(8, round(int(prefs.get("font_size", 12) or 12) * 0.75)))
    except (TypeError, ValueError):
        pass
    app.setFont(font)
