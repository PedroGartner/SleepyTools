# Sleepy tools for Nuke (v3)

## Install
1. Copy the `SleepyTools` folder into your `.nuke` folder.
2. Add one line to `~/.nuke/init.py`:
   ```python
   nuke.pluginAddPath('./SleepyTools')
   ```
3. Restart Nuke. Nothing goes in your own `menu.py`: the pack builds its own menus.

## Where things are
| In Nuke | What |
|---|---|
| **Nodes toolbar > SleepyTools > Keying / Grain / Cleanup / Lens / CG / QC** | every gizmo, one submenu per folder (Tab search finds them too) |
| **Nuke > SleepyTools > Command Palette** (Ctrl+Alt+Space) | fuzzy search for commands, nodes, gizmos and nodes in the script |
| **Nuke > SleepyTools > Gizmo Manager** | gizmo usage, swap, bake to Group (also dockable from Windows > Custom) |
| **Nuke > SleepyTools > Sleepy tools help** | opens this file |

Your other Sleepy tools (Setup Library and so on) also install into Nuke > SleepyTools, so everything sits in one menu.

## Folder layout
```
SleepyTools/
  init.py, menu.py             Nuke runs these
  gizmos/
    Keying/    SleepyChromaKey, SleepyAdditiveKeyer, SleepyEdgeExtend, SleepyLightWrap, EdgeTreatment, Smoosh_Colours
    Grain/     SleepyGrain, GrainChecker, StaticNoise
    Cleanup/   SleepyPlateFill, SleepyTemporalMedian, Grad4Points
    Lens/      SleepyExpoGlow, SleepyLensKit, SleepyHeatHaze
    CG/        SleepyAOVRebuild, SleepyPMatte, SleepyNRelight, SleepyDepthFog, Z_Edge_Fix
    QC/        CompareQC
  python/      sleepy_tools.py (paths + menus), sleepy_command_palette.py, sleepy_gizmo_manager.py
  docs/        this README, CHANGELOG, previews/ (picture of every gizmo's node graph)
```
To add a gizmo, drop it into a category folder (or make a new folder) and restart Nuke.

## Every gizmo follows the same standard
- **Controls** tab first. It opens with a header line (name, version, category, one-line summary), then the knobs in bold-labelled sections, and **mix** last on tools that change the image.
- An **About** tab with the inputs and how the tool works. The `?` help button shows the same text.
- Tile colour by category: Keying green, Grain brown, Cleanup blue, Lens orange, CG purple, QC red.
- Inside (Ctrl+Enter), the main pipe runs straight down. Every stage has its own labelled backdrop, stages run left to right, and branches leave through Dots, with side inputs entering from the side. `docs/previews` shows each graph.

Old gizmo names are kept, so existing scripts keep loading.

## Notes
- The "use mask input" checkboxes tick themselves when you connect the input with the node panel open; otherwise tick them by hand.
- SleepyGrain's synthetic mode needs NukeX (F_ReGrain). Everything else uses standard Nuke nodes.
