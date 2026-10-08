# Sleepy Shell V1 — Visual Fidelity Pass (mockup alignment)

Scope: **V1 only** (`shellui/` + its entry points). V2
(`shellui_production/`) and V3 (`shellui_nuke/`) were not touched.
Nothing was redesigned; the HTML mockup
(the original design mockup) was treated as the visual
specification and every value below was taken from its CSS, not
guessed. No feature was removed; external integrations
(Snapshot Browser, SleepyQueue, SleepyCore) are used through their
existing public APIs only.

## The three bugs that made the UI "colorless"

1. **`central.setStyleSheet("background: transparent")`** on the main
   window's central widget. A bare declaration set on a widget
   cascades to *every descendant* at ancestor precedence, which beats
   the application stylesheet — so `#ShellWindow`, `#ShellSidebar`,
   pages, everything rendered transparent (black through the
   translucent frameless window). Removed; comment left in the code.
2. **QGraphicsDropShadowEffect over styled subtrees** (Qt bug 31045):
   the shadow effect on the window frame / hero rendered the QSS
   backgrounds of child widgets (e.g. the solid-orange "Resume in
   Nuke" button) black. Shadows removed from containers; the mockup
   depth comes from the 1px `#3a3c40` window border instead.
3. **Plain QWidget containers never painted QSS backgrounds** without
   `WA_StyledBackground`. Pages and scroll contents now mark
   themselves (`widgets.styled()`), and the universal `QWidget`
   rule no longer carries a background — containers are transparent by
   default so cards/groups sit on the correct surface color.

New regression tests (`tests/test_visual.py`) render the real window
offscreen and assert the painted pixels (dominant color per widget):
sidebar `#191a1c`, chrome strips `#121314`, window `#161719`, hero
`#1e1f22`, primary button and checked segment `#f0a043`. These catch
all three failure classes above if they ever come back.

## shellui/theme.py

- Full palette: added the mockup-only surfaces — side `#191a1c`,
  chrome `#121314`, hover `#323438`, hover-soft `#1f2022`,
  active `#222326` (light-mode equivalents included). Accent names map
  for the Preferences labels.
- `rgba()` colors are now written in **percent form** (Qt QSS reads
  CSS-style alpha; bare 0–255 ints do not).
- QSS rebuilt from the mockup CSS: inputs use window bg + 4px radius
  (`.tin`); buttons 3px radius / 12px padding with `#323438` hover;
  primary hover `#f7b25e` equivalent (parametric); danger buttons use
  hold-red border at 50%; chips/pills/segments/swatches/sel2/fitem/
  preview/note-warn/vrow/panel rules added (`ShellVRow`, `ShellMChip`,
  `ShellBadge`, `ShellPreview`, `ShellFItem`, `ShellNoteWarn`,
  `ShellSetNav`, `ShellNavButton`, `ShellSNav`, `ShellVersionBox`,
  `ShellPanel` …). `#ShellGroup` now uses the mockup's `#191a1c`
  (was window color); `#ShellStatusbar` uses chrome (was window).
- `sel2` pills are styled via a `sel2=true` property so accent changes
  recolor them without rebuilding the page.
- App font now converts the px pref (`font_size`) to point size at
  96 dpi instead of setting the raw px value as points.

## shellui/widgets.py

- `Chip`: true pill (radius 10, padding 1px 9px, 11px/600), bg 15% /
  border 40% of the status color (mockup `.chip`), Fixed size policy
  so tall rows can no longer inflate it.
- `NeutralChip` (alt bg, dim text — the mockup's neutral chips) and
  `MetaChip` (window bg + soft border, dim label + bold value,
  `.mchip`).
- `Thumb`: gradients now picked from the mockup's **g1–g8** palette
  (140deg, hash-stable per shot); code label 19% of height with letter
  spacing and soft shadow; 9px uppercase tag bottom-left; `expanding`
  mode fills the card width (home/gallery cards, fixes the old fixed
  260x146 letterboxing); `radius`/`font_px` parameters for the
  different card sizes.
- `Section`: panel paddings 15/11/13 and the small dim right-hand note
  ("stored in shot.json") like the mockup's `.panel h4`.
- `set_section_font` (uppercase, pixel-sized, letter-tracked captions
  — Qt QSS has no letter-spacing), `kbd_icon` (paints the Ctrl+K chip),
  `WeekBars` (accent week chart, 44px), `dim_effect` (mockup .dim/.75
  opacity rows), `styled()` helper.
- `add_card_shadow` kept for leaf use only, with a docstring warning
  about QTBUG-31045.

## shellui/mainwindow.py

- Sidebar 250px (was 230), `#191a1c` surface; Home/Board styled as the
  mockup's nav rows (accent left border on active); PROJECTS caption
  spaced exactly like `.side h4`; project rows 9px/16px padding with
  7px dots and hover/active states `#1f2022`/`#222326`; right-click on
  a project row opens Board / Project settings.
- WATCHED ROOTS box moved to the very bottom (mockup order), uses ✓/⚠
  marks, transparent bg on the sidebar.
- Titlebar: 21px accent logo, 13px name, lowercase dim screen sub
  ("project manager — launcher", "the board", …) matching the mockup.
- Status strip: `#121314`, three parts — "Index: N projects · M shots
  (cached) · X offline", "Cache 1 KB · updated 15:21" (real cache file
  stat), page-specific hint right-aligned (Board: "Showing N of M
  shots · right-click = set status · double-click = open latest";
  Shot: managed/discovered + derived counts; Preferences: prefs file
  path; Project settings: project.json note) — the mockup's
  per-screen statusbars.
- `open_project_settings()` + entry points (board toolbar gear, sidebar
  project context menu) — the Project Settings page was previously
  unreachable.

## shellui/page_home.py

- Added the mockup's search row: search field ("Search shots, notes,
  tags, node types…"), painted Ctrl+K hint chip, working Ctrl+K
  shortcut, Enter jumps to the Board with the query; "Open Nuke…"
  button (standalone only; launches Nuke without a script).
- Hero: 340px thumb, accent kicker with 1.4px tracking, meta line with
  snapshot count, four stat columns (Status chip / Session time /
  Latest render / Due), actions "Resume in Nuke" + "Open folder" +
  "Snapshot Browser" (delegates to Snapshot Browser's
  `nuke_bridge.show_panel()` inside Nuke, explains standalone).
- Recent shots: four-column grid of mockup cards — full-bleed 96px
  thumb, name + status chip row, project + "today/yesterday/N days
  ago" row.

## shellui/page_board.py

- Toolbar: gear button next to the project combo (opens Project
  Settings), pills/segments restyled by QSS (checked segment now
  actually paints accent — it never did before).
- Columns: mockup `.bcard` — 74x52 thumb left, name + dim version,
  status/due chips, "ClientX · today" sub line; delivered/hold cards
  at 75% opacity; columns `#191a1c` with 420px min height.
- List: group headers with 8px dot, tracked uppercase colored title,
  count and "sorted by due date" / "kept until you hide them" notes;
  rows with 96x54 thumb, version cell (64px), due chip cell (150px),
  date cell (150px) and the mockup's wide 250px cell
  ("N snapshots · rendered ✓ / not rendered yet"); delivered/hold rows
  dimmed to 0.55.
- Gallery: status pill row with counts (click to hide/show a status,
  mockup `.gpills .off`), cards with 135px full-bleed thumb and chips
  overlaid top-right / bottom-left (`.gstat`/`.gdue`), caption row
  with version, project · when sub line, delivered/hold at 0.6,
  reflows on resize like `auto-fill minmax(240px, 1fr)`.

## shellui/page_shot.py

- Breadcrumb "Project › shots › sh034" with bold names (mockup
  `.crumb`); 22px title; due/priority/tags chips next to the title
  block; status picker chips faded when inactive, 1px accent outline
  on the active one (mockup `.statuspick`).
- Left column 330px: 200px thumb with version tag, full-width accent
  "Open Latest (vNNN)", 2x2 action grid (Version Up / Send to
  SleepyQueue / Open Folder / Snapshot) — all previous actions kept.
- Versions panel: mockup `.vrow` — 64x38 thumb, bold v-number, date ·
  size · rendered ✓ / snapshot count, accent star on the current row,
  current row highlighted with accent-dim + 35% outline; file dates/
  sizes are real (node counts are not stored on disk and are not
  invented).
- Renders panel: ✓/✗ marks (ok/red, bold) per record with right dim
  meta.
- Time panel: bold total + "this week" caption and the accent week
  bars driven by real per-day session data.
- Shot settings: mockup `.mchip` meta chips (fps / format / working
  space / status / range / handles) + the due/priority/tags editor row.
- Per-page statusbar text (managed + derived counts).

## shellui/page_settings.py

- **Preferences** rebuilt on the mockup's settings layout: 200px left
  nav (Appearance / New Shot Rules / Scanning / Startup / Advanced)
  with accent-bordered active rows, group cards with the 230px
  label+description column (`.frow`), last row of each group without
  the bottom border.
  - Appearance: 22px accent swatches (white ring when selected) with
    the "Sleepy Orange (default)" name label, theme-mode and density
    sel2 chips (Follow Nuke / Sleepy Dark / Light exp.; Comfortable /
    Compact), "12 px" font spinbox. All apply live and persist.
  - New Shot Rules: folder template as the mockup's `.flist` items
    (grip, locked badge on comp, ✕ to remove, dashed "+ Add folder…",
    click to select, Up/Down/Remove work on the selection), shot /
    script pattern fields and a live dashed **preview**
    ("creating sh035 → shots/sh035/comp plates ref renders
    deliverables + sh035_comp_v001.nk").
  - Scanning: watched roots list + Add folder… / Remove / Rescan now.
  - Startup: pill toggles for "Show Shell on launch", "Resume card"
    and "Stale-shot check" (all wired, see prefs.py) plus the Nuke
    executable row (Browse / Detect).
  - Advanced: schema formats, prefs file path, open crash-log folder
    (SleepyCore's 50-log store).
- **Project Settings** rebuilt: crumb, title with managed chip +
  "N shots · M sequences", red "defaults apply to new shots only"
  banner, Identity (client, project color swatches, tags), Technical
  defaults (fps, format, working space, range, handles, naming
  overrides), Folders & templates (Standard (suite) vs Client
  structure sel2 chips — the existing `folder_template` config value
  finally has UI, comp template + Browse), Rendering & delivery
  (render output, deliverable naming), Danger zone (Re-scan now /
  Clear local cache / Unmanage project… in the hold-red danger style).

## shellui/nukepanel.py

- Laid out like the mockup's Nuke panel: header strip with accent G
  logo + shot name + project + status chip; due + "25 fps · ACEScg"
  chip row; VERSIONS box (`#ShellVersionBox`) with the current version
  highlighted; 2-column small-button grid (Open Latest / Version Up /
  To SleepyQueue / Snapshot / Folder); "OTHER SHOTS · project" rows
  with 40x24 thumbs, status chip and version; Notes footer with the
  bold label and top border. Session heartbeat logic unchanged.

## shellui/dialogs.py

- Adopt dialog restyled as the mockup's modal: header strip, dim note
  with accent keywords, checkbox rows (bold name + dim path/versions),
  right-aligned footer with a live "Adopt N shots" primary button.
  Behavior unchanged (writes shot.json only).

## shellui/backend.py / shellcore/launch.py / standalone.py

- `launch_nuke_app()` — launches Nuke without a script ("Open Nuke…").
- `open_snapshot_browser()` — standalone explains, inside Nuke calls
  Snapshot Browser's public `nuke_bridge.show_panel()`.
- `standalone.py` honors the new `show_on_launch` pref (starts on the
  Board when the launcher hero is disabled).

## shellcore/prefs.py

- New defaults (type-checked, unknown keys preserved as before):
  `show_on_launch: true`, `resume_card: true`, `stale_check: true`
  (`stale_days` already existed; the check now feeds the Board's
  "idle N days" notes).

## tests/test_visual.py (new)

- Renders the real MainWindow offscreen with an isolated portfolio and
  asserts painted pixels: sidebar / titlebar / statusbar / window /
  hero surfaces, primary-button and checked-segment accent, group bg,
  plus per-page status hints. Guards the three silent-QSS failure
  classes described at the top.

## Untouched on purpose

- `shellcore/*` engine behavior, `shellui_production/` (V2),
  `shellui_nuke/` (V3), and every other tool in the suite.

## Follow-up round (Oct 3)

**Nuke entry points — menu-home compatibility shim.** All three
`sleepy_shell*.py` entries now register through
`_add_suite_submenu()`: try the original `add_sleepy_submenu()`
(home `SleepyTools`), then an older-style core's `add_submenu()`
(home `SleepyTools`), then find-or-create the home menu directly. With the
currently deployed core the first path wins, so menu placement is
unchanged. Distinct pane IDs and per-entry install flags are
preserved.

**Fixes (all verified by the full test suite):**

- Removed 10 unused imports (`widgets.py`, `nuke_pane.py`,
  `inspector.py`, `production_widget.py`, `test_visual.py`).
- `backend._script_pattern` read `shot["project_config"]`, which
  nothing ever set, so project-level script-naming overrides were
  silently ignored by Version Up. `state.py` now threads the project
  config onto every shot item (`project_config`), and a regression
  test (`test_variants.py`) proves Version Up follows a project's
  `{shot}_anim_v###.nk` override.
- The Board's "Due in 7 days" pill now starts engaged, matching the
  mockup's toolbar, and the board's status hint explains when the due
  filter is hiding shots ("due filter on (shots without a due date are
  hidden)").

## Runtime round (Oct 3, after first real launch)

The first launch on real Windows surfaced two bugs that every offscreen
render had missed, plus a sweep that found two more of the same class.

1. **Transparent standalone window.** The frameless window used
   `WA_TranslucentBackground`; on some Windows compositors/DPI setups
   every app-stylesheet background (window frame, sidebar, statusbar)
   silently failed to composite, leaving only per-widget-styled
   controls floating over the desktop. Fixed by making the window
   opaque — an opaque window cannot fail this way. The mockup's rounded
   corners now come from a window mask (`setMask`, re-applied on
   resize) instead of an alpha surface.
2. **"Cannot leave Preferences."** Two causes: the transparency above
   made page switches visually invisible, and — the real trap — the
   sidebar **Home/Board buttons were never connected to anything**
   (pages only changed when other widgets called `_goto`). A new
   click-driven test caught it; the buttons are now wired and the
   Preferences page is provably escapable via the sidebar.
3. **Docked panel transparent inside Nuke.** The panel styled itself
   with objectName rules that live in the *application* stylesheet —
   which only the standalone applies. Inside Nuke those rules did not
   exist, so Nuke's colors showed through. The panel now applies the
   Shell QSS to itself (scoped to the panel, never leaking into the
   host; the "Follow Nuke" mode still skips it).
4. **Same bug class elsewhere — effects eliminated.** `dim_effect` used
   a `QGraphicsOpacityEffect` on Board rows/cards (QTBUG-31045 class:
   effects over styled subtrees knock out child backgrounds). Dimming
   is now a `dim` dynamic property styled by theme rules; zero
   QGraphicsEffect instances remain in the suite, and
   `add_card_shadow` was deleted entirely.
5. **Dead gallery cards.** Board Gallery cards looked clickable
   (pointing-hand cursor) but never had the event filter installed —
   double-click/right-click did nothing. Fixed; also the context menu
   now maps its position through the card, not the page.
6. **New regression tests** (test_ui_smoke.py): no-QWidget-has-a-
   graphics-effect sweep, Preferences-escapable-via-sidebar click test,
   docked-panel-carries-own-stylesheet test, property-driven dimming
   test.

## Interface zoom (Oct 3, after font-size feedback)

Static font bumps weren't enough on high-DPI displays, and per-label
sizes can never converge. The launcher now supports a real
**interface zoom**: a `ui_scale` preference (100/110/125/150%,
Preferences > Appearance > Interface zoom) applied as
`QT_SCALE_FACTOR` before the QApplication is created, which uniformly
scales every px in the interface — styles, layouts and dialogs —
like browser zoom. It applies on the next launcher start (the
environment must be set before Qt initializes); inside Nuke the host's
own scaling applies instead. The four standalone entry points
(standalone*.py, shell_selector.py) bootstrap it, and the user's
saved preference was set to 125% after the "still too small" feedback.

## Font revert + editable-only enlargement (Oct 3, same day)

The 125% zoom plus the size bump overshot — "everything is too big".
Revert: all inline font sizes went back to the fidelity-pass values
(inverse of the bump map), `font_size` default back to 12, and the
saved preference reset to ui_scale 1.0 / font_size 12. The Interface
zoom feature itself stays (default 100%).

The user's actual request survives as a targeted rule: **editable
controls** (QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox,
QDoubleSpinBox, QComboBox, QDateEdit, QListWidget) render at
`font_size + 2` px — one parametric QSS rule, so they stay two points
above the base at any font-size setting. Verified programmatically:
search/combo/spin render 14px while labels render the old 12px.

## .bat startup fix + Ctrl+K chip (Oct 3)

Making the Ctrl+K hint bigger initially used `QLineEdit.setIconSize()`,
which does not exist on QLineEdit — the home page crashed on build and
the .bat appeared to "not open" (the process died before showing any
window). Fixed by rebuilding the mockup's `.search` row properly: one
styled frame (`#ShellSearch`) containing the magnifier pixmap, the
borderless line edit, and the Ctrl+K chip as a real QLabel at 56x22
with 12px text — no more icon-box shrinking. The chip is painted at
plain 1x: a 2x devicePixelRatio pixmap was tried, but PySide6's QLabel
drops the DPR when storing it and displays the pixmap at double size,
clipped.

New regression test `tests/bat_smoke.py` runs the exact .bat code path
(`python standalone.py`) offscreen with an auto-quit timer — any
startup crash now fails in the test instead of on a double-click.

## Feature round: checklists, briefing, duplicate, Frame Doctor (Oct 3)

Four additions, all built on the shared core so V2/V3 can adopt the
same data:

1. **Shot checklists.** Additive `tasks` field in shot.json
   (`[{name, done}]`, malformed entries dropped on load, dict items now
   survive list coercion). Shot page gains a Checklist section:
   checkbox rows with strikethrough on done, x to remove, "Add a
   step..." field.
2. **Morning briefing on Home.** A card above the search row: Due
   today / Due in N days / Waiting client / In review / Idle 14+ days,
   each with clickable shot chips (derived only — nothing stored,
   `shellcore/briefing.py`).
3. **Duplicate / branch shot.** Board right-click > "Duplicate shot...":
   scaffolds the next shot from the template, copies the source's
   latest comp in as v001, carries tags, records
   "Duplicated from X" in notes (`ops.duplicate_shot`). Uses
   highest+1 naming (next_shot_name is collision-only and would return
   sh001 next to sh010).
4. **Frame Doctor.** Output QC for rendered sequences: discovers
   sequences, finds missing-frame gaps and zero-byte files, and per
   frame reports black, flat, NaN (EXR), clipped-superwhite and
   resolution changes, then a verdict. Core in
   `shellcore/framedoctor.py` (pure math/discovery; readers isolated in
   `framedoctor_readers.py` — OpenEXR for EXR when installed, QtGui
   QImage for PNG/JPG/TIFF/BMP, function-level imports). Shot page:
   every render row with a known output gets a "Frame Doctor" button
   that scans in a background QThread and renders the verdict + findings
   under Recent renders. CLI: `tools/frame_doctor.py
   <folder-or-pattern> [--sample N] [--json]` (exit 2 = problems found).

## New Project dialog + app icon (Oct 3)

- The Sleepy **G tile is now the application/window icon** (painted,
  parametric accent, applied via theme.apply) — every window and dialog
  carries it, including New Project, which previously showed the
  generic Qt icon.
- **New Project dialog expanded**: Tags, Handles, Shot/Script name
  patterns (prefilled from Preferences), Folder structure (Standard
  suite vs Client structure), Comp template with Browse, Render output,
  and a "Create the first shot now (sh001)" checkbox — every field
  maps to a real project.json value, defaults from Preferences, empty
  fields omitted. The first-shot checkbox is created ABOVE the form
  (visually first) and creating a project with it enabled scaffolds
  sh001 immediately (verified: project + shot.json + comp folder).
