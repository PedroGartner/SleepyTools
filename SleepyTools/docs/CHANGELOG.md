# Sleepy tools changelog

## v3 (rebuild of how the pack is made and organised)
- **Gizmo internals redone.** Every node is laid out: the main pipe runs straight down, branches leave through Dots, side inputs come in from the side, and each stage sits in a labelled backdrop, with stages running left to right. Before, generated gizmos had no positions, so opening one stacked every node on top of each other.
- **One panel standard.** Every gizmo opens on a Controls tab with a header (name, version, category, summary). Section dividers are bold, there's a mix knob on the image tools, an About tab lists the inputs and how the tool works, and tile colours follow the category.
- **Folders by category** (Keying, Grain, Cleanup, Lens, CG, QC). `init.py` adds them, and `menu.py` builds Nodes > SleepyTools > Category from the folders.
- **One menu for the Python tools:** Nuke > SleepyTools > Command Palette / Gizmo Manager. The palette is no longer under Edit.
- **SleepyAOVRebuild** is rebuilt as a ladder (a result spine, one column per slot, check and solo spines). It does the same maths, with readable wiring.
- **Gizmo Manager** has a Category column and reads files encoding-safely.
- Old gizmo names are unchanged, so existing scripts load as before. Gizmos that gained a `mix` knob default it to 1.

## v1 of the new tools (added with v2)
SleepyEdgeExtend, SleepyLightWrap, SleepyAdditiveKeyer, SleepyPlateFill, SleepyTemporalMedian, SleepyExpoGlow, SleepyLensKit, SleepyHeatHaze, SleepyAOVRebuild, SleepyPMatte, SleepyNRelight, SleepyDepthFog, plus the Command Palette and Gizmo Manager.

## v2 fixes to the original gizmos


> **Old shots:** keep a copy of your v1 gizmos. Scripts saved with v1 load fine, but a few knobs were renamed or removed. Nuke will print "no such knob" warnings for those, and the values are lost (details below). EdgeTreatment v2 works completely differently.

### Fixed (these gave wrong results before)

**StaticNoise**
- Reset set the size multiplier to 0 (the grain vanished). It now restores the real defaults.
- **Seed** and **black** were not connected to anything. Both work now. Black adds grain in the shadows.
- Grain now animates per frame. Untick *animate grain* for a frozen pattern.
- Removed 28 duplicate hidden knobs and the Viewer node inside.

**SleepyChromaKey** (new; replaces ALPHA + ChromaKeyer)
- Colour pick now compares the picked colour and the image in the same normalised-chroma space. Before, you picked from the plate but the key compared against a halved, luminance-divided image.
- There were no NaN/inf values on black pixels (all divisions are guarded).
- Plate RGB passes through untouched. Only alpha is replaced (the old versions output the processed chroma image).
- Modes: **Colour pick**, **Screen difference** (proper green/blue colour-difference matte), and **Saturation** (what ALPHA's Key 01 was actually doing).
- Extras: tolerance/softness, ignore darks, pre-blur (key only), crunch/binarise (the old "Fill Alpha"), invert, premultiply, and a matte view.

**Smoosh_Colours**
- Colour is blended as a chroma vector instead of in HSV. Red and magenta edges no longer flip hue where HSV hue wraps. FG luminance is preserved exactly.
- Added *view edge mask*. Knob names are unchanged, so old values carry over.

**EdgeTreatment** (rebuilt: edge despill with luminance restore)
- Before, nothing happened without a mask, and inside the mask the background went black because Keylight's *Final Result* is premultiplied.
- Now Keylight runs in *Intermediate Result* (despill only), and the brightness the despill removed is added back as neutral or tinted light (*restore luminance* / *restore colour*).
- The mask is optional. Without it, the effect applies to the whole frame. The *Removed spill* view shows what was taken out.

### Improved

**SleepyGrain**
- The grain-source menu is labelled correctly: *Plate grain (extracted)* vs *Synthetic (F_ReGrain)*. The old labels were swapped in meaning.
- New knobs: *grain amount* and *ratio limit*. The multiplicative divide is safe on near-black pixels.
- Merges work on rgb only, so alpha is no longer pushed through a divide.
- New optional **mask** input (4th input): regrain only where you changed things.
- Removed the shot-specific frame hold (57), the Viewer, and the empty menu entry and group. The sample frame defaults to 1001.
- Still needs NukeX for F_ReGrain.

**GrainChecker**
- *Centred* display: grey means no grain, so negative grain is visible now (before, half the grain was below zero).
- Channel isolation, grain size, and a log toggle.
- An optional **plate** input with a split line for a plate/comp grain comparison.

**Z_Edge_Fix**
- *Depth from* channel: `rgba.red` keeps the old behaviour, and `depth.Z` lets you plug CG in directly.
- *Write to*: rgb (as before) or back into `depth.Z` of the Z input.
- The mask only applies when *use mask input* is on. Before, ticking invert with nothing connected switched the whole effect off.

**Grad4Points**
- **Free points** mode: drag 4 points in the viewer. Colours blend by inverse distance, with a *falloff power*.
- The original bilinear corner gradient is still available in *Corners* mode.
- *Sample colours from plate* reads the colours under the points from the input. *Use input format* takes the plate's format.
- **Renamed knobs:** `LLColor/LRColor/URColor/ULColor` → `c1..c4` (old values don't carry over).

**CompareQC**
- New **heatmap** mode: pixels changed by more than the threshold turn red over a dimmed image.
- *Don't set* range option works. Empty menu entries removed.

### Not changed
- **G_Fog / TX_Fog.** Its speed-up (lower-res slices) means changing the slice-builder code and every pixel-based expression together. That needs a live Nuke session to test. In the meantime, *draft slices = Half/Quarter* and *Apply Quality → Draft* are the fast preview path.

### About the "use mask/input" checkboxes
Nuke can't reliably tell a gizmo whether an input is connected, so each optional input has a checkbox. It ticks itself when you connect or disconnect with the node panel open. If the panel was closed, tick it by hand.
