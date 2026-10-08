"""Sleepy Expressions for Nuke.

A dockable panel with a searchable library of Expression node recipes. Pick one and it
creates an Expression node (or a small Group for things that need neighbouring pixels,
like normals from a 2D image or the fake relight) connected to the selected node.
Values become knobs on a Params tab: sliders, colour pickers and viewer handles.

Install (menu.py):
    import sleepy_expressions
    sleepy_expressions.install()

Then: Windows > Sleepy Expressions, or the Sleepy toolbar menu. Every recipe is also in
SleepyTools > Expressions, so you can find it with the Tab menu.
"""
import json
import os
import re
import textwrap

import nuke

try:
    import nukescripts
    from nukescripts import panels as _nkpanels
except ImportError:  # running outside Nuke's GUI
    nukescripts = None
    _nkpanels = None

# Qt binding selection: use Nuke's Qt version to avoid second Qt binding crash
def _import_qt():
    """Qt binding for the running host: Nuke 13-15 -> PySide2, Nuke 16+ -> PySide6.

    Importing the other binding loads a second Qt into Nuke and crashes it, so
    the Nuke version is checked before any import. Prefers SleepyCore.qt
    when the core pack is installed; the copy below is the same logic so this
    file also works on its own.
    """
    try:
        from SleepyCore import qt as _core_qt
        return _core_qt
    except Exception:
        pass
    import sys
    try:
        import nuke
        _major = int(nuke.NUKE_VERSION_MAJOR)
    except Exception:
        _major = None
    if _major is not None:
        if _major >= 16:
            from PySide6 import QtCore, QtGui, QtWidgets
        else:
            from PySide2 import QtCore, QtGui, QtWidgets
    elif "PySide2.QtWidgets" in sys.modules:
        from PySide2 import QtCore, QtGui, QtWidgets
    else:
        try:
            from PySide6 import QtCore, QtGui, QtWidgets
        except ImportError:
            from PySide2 import QtCore, QtGui, QtWidgets
    from types import SimpleNamespace
    return SimpleNamespace(QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets)


_qt = _import_qt()
QtCore, QtGui, QtWidgets = _qt.QtCore, _qt.QtGui, _qt.QtWidgets

__version__ = "1.0"
PANEL_ID = "uk.co.pg.ExpressionLab"
PANEL_TITLE = "Sleepy Expressions"
USER_FILE = os.path.join(os.path.expanduser("~"), ".nuke", "sleepy_expression_lab_user.json")
USER_CAT = "My expressions"
CHANNELS = ("r", "g", "b", "a")
CHANNEL_LABELS = {"r": "red", "g": "green", "b": "blue", "a": "alpha"}

CATALOG = json.loads(r'''[{"kind":"group","cat":"Normals & relight","id":"normal_from_image","title":"Normal map from image","desc":"Builds a tangent-space normal map from any 2D image, treating brightness as height. For baked bumps, fake relighting and IDistort refraction. Blur sets how big the shapes are; strength sets how deep.","inputs":["img"],"params":[{"n":"source","t":"enum","items":["Luminance","Red","Green","Blue","Alpha","Max RGB"],"v":0,"l":"source"},{"n":"invert","t":"bool","v":0,"l":"invert"},{"n":"blur","t":"float","v":2,"lo":0,"hi":60,"l":"blur"},{"n":"spacing","t":"float","v":1,"lo":0.5,"hi":10,"l":"sample spacing"},{"n":"strength","t":"float","v":40,"lo":0,"hi":400,"l":"strength"},{"n":"flip_green","t":"bool","v":0,"l":"flip green (DirectX)"},{"n":"encode","t":"bool","v":1,"l":"encode 0–1 (normal-map look)"}],"nodes":[{"id":"H","class":"Expression","in":["img"],"t":[["l","parent.source == 0 ? 0.2126*r + 0.7152*g + 0.0722*b : parent.source == 1 ? r : parent.source == 2 ? g : parent.source == 3 ? b : parent.source == 4 ? a : max(r, max(g, b))"],["hgt","parent.invert ? 1 - l : l"]],"r":"hgt","g":"hgt","b":"hgt","a":"hgt"},{"id":"BL","class":"Blur","in":["H"],"knobs":{"channels":"rgba"},"expr":{"size":"parent.blur"}},{"id":"TxR","class":"Transform","in":["BL"],"knobs":{"filter":"Impulse"},"expr":{"translate":["-max(0.5, parent.spacing)","0"]}},{"id":"TxL","class":"Transform","in":["BL"],"knobs":{"filter":"Impulse"},"expr":{"translate":["max(0.5, parent.spacing)","0"]}},{"id":"TyU","class":"Transform","in":["BL"],"knobs":{"filter":"Impulse"},"expr":{"translate":["0","-max(0.5, parent.spacing)"]}},{"id":"TyD","class":"Transform","in":["BL"],"knobs":{"filter":"Impulse"},"expr":{"translate":["0","max(0.5, parent.spacing)"]}},{"id":"C1","class":"Copy","in":["TxR","TxL"],"knobs":{"from0":"rgba.red","to0":"rgba.green"}},{"id":"C2","class":"Copy","in":["C1","TyU"],"knobs":{"from0":"rgba.red","to0":"rgba.blue"}},{"id":"C3","class":"Copy","in":["C2","TyD"],"knobs":{"from0":"rgba.red","to0":"rgba.alpha"}},{"id":"N","class":"Expression","in":["C3"],"t":[["dx","(r - g)*parent.strength/(2*max(0.5, parent.spacing))"],["dy","(b - a)*parent.strength/(2*max(0.5, parent.spacing))*(parent.flip_green ? -1 : 1)"],["len","sqrt(dx*dx + dy*dy + 1)"]],"r":"-dx/len","g":"-dy/len","b":"1/len","a":"1"},{"id":"ENC","class":"Expression","in":["N"],"r":"parent.encode ? r*0.5 + 0.5 : r","g":"parent.encode ? g*0.5 + 0.5 : g","b":"parent.encode ? b*0.5 + 0.5 : b"}],"output":"ENC","layers":[],"plate":{"img":"photo"},"view":"rgb"},{"kind":"group","cat":"Normals & relight","id":"fake_relight","title":"Fake relight (2D)","desc":"Relights 2D footage. Builds normals from the image (or uses a normals input, or a separate bump image) and lights them with a directional or point light you drag in the viewer. Includes wrap, specular and rim.","inputs":["img","normals","bump"],"params":[{"tab":"Light"},{"n":"light_type","t":"enum","items":["Directional","Point (drag in viewer)"],"v":1,"l":"light type"},{"n":"azimuth","t":"float","v":135,"lo":-180,"hi":180,"l":"azimuth"},{"n":"elevation","t":"float","v":35,"lo":0,"hi":90,"l":"elevation"},{"n":"light_pos","t":"xy","v":[0.25,0.8],"frac":true,"l":"light pos"},{"n":"light_height","t":"float","v":500,"lo":1,"hi":4000,"l":"light height"},{"n":"falloff","t":"float","v":1800,"lo":1,"hi":8000,"l":"falloff"},{"n":"light_color","t":"color","v":[1,0.9,0.78],"l":"light color"},{"n":"intensity","t":"float","v":1.2,"lo":0,"hi":6,"l":"intensity"},{"n":"ambient","t":"float","v":0.55,"lo":0,"hi":2,"l":"ambient"},{"n":"wrap","t":"float","v":0.3,"lo":0,"hi":1,"l":"wrap"},{"n":"spec_amount","t":"float","v":0.15,"lo":0,"hi":4,"l":"spec amount"},{"n":"shininess","t":"float","v":30,"lo":1,"hi":200,"l":"shininess"},{"n":"rim_amount","t":"float","v":0,"lo":0,"hi":4,"l":"rim amount"},{"n":"rim_power","t":"float","v":3,"lo":1,"hi":10,"l":"rim power"},{"n":"view","t":"enum","items":["Result","Lighting only","Normals"],"v":0,"l":"view"},{"n":"amount","t":"float","v":1,"lo":0,"hi":1,"l":"mix"},{"tab":"Normals"},{"n":"use_normals_input","t":"bool","v":0,"l":"use normals input"},{"n":"normals_encoded","t":"bool","v":0,"l":"normals input is 0–1"},{"n":"use_bump_input","t":"bool","v":0,"l":"height from bump input"},{"n":"source","t":"enum","items":["Luminance","Red","Green","Blue","Alpha","Max RGB"],"v":0,"l":"source"},{"n":"invert","t":"bool","v":0,"l":"invert"},{"n":"blur","t":"float","v":8,"lo":0,"hi":60,"l":"blur"},{"n":"spacing","t":"float","v":1,"lo":0.5,"hi":10,"l":"sample spacing"},{"n":"strength","t":"float","v":60,"lo":0,"hi":400,"l":"strength"},{"n":"flip_green","t":"bool","v":0,"l":"flip green"}],"nodes":[{"id":"HS","class":"Switch","in":["img","bump"],"expr":{"which":"parent.use_bump_input"}},{"id":"H","class":"Expression","in":["HS"],"t":[["l","parent.source == 0 ? 0.2126*r + 0.7152*g + 0.0722*b : parent.source == 1 ? r : parent.source == 2 ? g : parent.source == 3 ? b : parent.source == 4 ? a : max(r, max(g, b))"],["hgt","parent.invert ? 1 - l : l"]],"r":"hgt","g":"hgt","b":"hgt","a":"hgt"},{"id":"BL","class":"Blur","in":["H"],"knobs":{"channels":"rgba"},"expr":{"size":"parent.blur"}},{"id":"TxR","class":"Transform","in":["BL"],"knobs":{"filter":"Impulse"},"expr":{"translate":["-max(0.5, parent.spacing)","0"]}},{"id":"TxL","class":"Transform","in":["BL"],"knobs":{"filter":"Impulse"},"expr":{"translate":["max(0.5, parent.spacing)","0"]}},{"id":"TyU","class":"Transform","in":["BL"],"knobs":{"filter":"Impulse"},"expr":{"translate":["0","-max(0.5, parent.spacing)"]}},{"id":"TyD","class":"Transform","in":["BL"],"knobs":{"filter":"Impulse"},"expr":{"translate":["0","max(0.5, parent.spacing)"]}},{"id":"C1","class":"Copy","in":["TxR","TxL"],"knobs":{"from0":"rgba.red","to0":"rgba.green"}},{"id":"C2","class":"Copy","in":["C1","TyU"],"knobs":{"from0":"rgba.red","to0":"rgba.blue"}},{"id":"C3","class":"Copy","in":["C2","TyD"],"knobs":{"from0":"rgba.red","to0":"rgba.alpha"}},{"id":"N","class":"Expression","in":["C3"],"t":[["dx","(r - g)*parent.strength/(2*max(0.5, parent.spacing))"],["dy","(b - a)*parent.strength/(2*max(0.5, parent.spacing))*(parent.flip_green ? -1 : 1)"],["len","sqrt(dx*dx + dy*dy + 1)"]],"r":"-dx/len","g":"-dy/len","b":"1/len","a":"1"},{"id":"DEC","class":"Expression","in":["normals"],"r":"parent.normals_encoded ? r*2 - 1 : r","g":"parent.normals_encoded ? g*2 - 1 : g","b":"parent.normals_encoded ? b*2 - 1 : b"},{"id":"NS","class":"Switch","in":["N","DEC"],"expr":{"which":"parent.use_normals_input"}},{"id":"LT","class":"Expression","in":["NS"],"t":[["ldx","parent.light_type ? parent.light_pos.x - (x + 0.5) : cos(parent.elevation*pi/180)*cos(parent.azimuth*pi/180)"],["ldy","parent.light_type ? parent.light_pos.y - (y + 0.5) : cos(parent.elevation*pi/180)*sin(parent.azimuth*pi/180)"],["ldz","parent.light_type ? parent.light_height : sin(parent.elevation*pi/180)"],["ln","max(1e-6, sqrt(ldx*ldx + ldy*ldy + ldz*ldz))"]],"r":"(parent.light_type ? 1/(1 + pow2(ln/parent.falloff)) : 1)*clamp(((r*ldx + g*ldy + b*ldz)/ln + parent.wrap)/(1 + parent.wrap))","g":"(parent.light_type ? 1/(1 + pow2(ln/parent.falloff)) : 1)*pow(max(0, (r*ldx/ln + g*ldy/ln + b*(ldz/ln + 1))/sqrt(pow2(ldx/ln) + pow2(ldy/ln) + pow2(ldz/ln + 1))), parent.shininess)","b":"pow(clamp(1 - b), parent.rim_power)","a":"1"},{"id":"CP","class":"Copy","in":["img","LT"],"knobs":{"from0":"rgba.red","to0":"pgL.red","from1":"rgba.green","to1":"pgL.green","from2":"rgba.blue","to2":"pgL.blue"}},{"id":"CPN","class":"Copy","in":["CP","NS"],"knobs":{"from0":"rgba.red","to0":"pgN.red","from1":"rgba.green","to1":"pgN.green","from2":"rgba.blue","to2":"pgN.blue"}},{"id":"OUT","class":"Expression","in":["CPN"],"expr":{"mix":"parent.amount"},"t":[["diff","pgL.red*parent.intensity"],["sp","pgL.green*parent.spec_amount"],["rim","pgL.blue*parent.rim_amount"],["vw","parent.view"]],"r":"vw == 2 ? pgN.red*0.5 + 0.5 : (vw == 1 ? 1 : r)*(parent.ambient + diff*parent.light_color.r) + (sp + rim)*parent.light_color.r","g":"vw == 2 ? pgN.green*0.5 + 0.5 : (vw == 1 ? 1 : g)*(parent.ambient + diff*parent.light_color.g) + (sp + rim)*parent.light_color.g","b":"vw == 2 ? pgN.blue*0.5 + 0.5 : (vw == 1 ? 1 : b)*(parent.ambient + diff*parent.light_color.b) + (sp + rim)*parent.light_color.b"},{"id":"RM","class":"Remove","in":["OUT"],"knobs":{"operation":"remove","channels":"pgL","channels2":"pgN"}}],"output":"RM","layers":[["pgL",["pgL.red","pgL.green","pgL.blue"]],["pgN",["pgN.red","pgN.green","pgN.blue"]]],"plate":{"img":"photo"},"view":"rgb","note":"Point mode: the light pos handle appears in the viewer while the group's panel is open."},{"kind":"group","cat":"Normals & relight","id":"curvature","title":"Curvature / cavity from image","desc":"High-pass of the height: dark in cracks and pores, bright on ridges. Use it as a dirt or AO-style multiply, or as a matte for grime.","inputs":["img"],"params":[{"n":"source","t":"enum","items":["Luminance","Red","Green","Blue","Alpha","Max RGB"],"v":0,"l":"source"},{"n":"invert","t":"bool","v":0,"l":"invert"},{"n":"radius","t":"float","v":6,"lo":0,"hi":100,"l":"radius"},{"n":"gain","t":"float","v":8,"lo":0,"hi":50,"l":"gain"},{"n":"view","t":"enum","items":["Signed (grey = flat)","Cavities","Peaks","Multiply onto plate"],"v":0,"l":"view"},{"n":"amount","t":"float","v":0.6,"lo":0,"hi":2,"l":"amount"}],"nodes":[{"id":"H","class":"Expression","in":["img"],"t":[["l","parent.source == 0 ? 0.2126*r + 0.7152*g + 0.0722*b : parent.source == 1 ? r : parent.source == 2 ? g : parent.source == 3 ? b : parent.source == 4 ? a : max(r, max(g, b))"],["hgt","parent.invert ? 1 - l : l"]],"r":"hgt","g":"hgt","b":"hgt","a":"hgt"},{"id":"BL","class":"Blur","in":["H"],"knobs":{"channels":"rgba"},"expr":{"size":"parent.radius"}},{"id":"CP","class":"Copy","in":["H","BL"],"knobs":{"from0":"rgba.red","to0":"rgba.green"}},{"id":"CP2","class":"Copy","in":["img","CP"],"knobs":{"from0":"rgba.red","to0":"pgC.red","from1":"rgba.green","to1":"pgC.green"}},{"id":"OUT","class":"Expression","in":["CP2"],"t":[["d","(pgC.red - pgC.green)*parent.gain"],["vw","parent.view"]],"c":"vw == 0 ? 0.5 + d : vw == 1 ? clamp(-d) : vw == 2 ? clamp(d) : @*clamp(1 + d*parent.amount, 0, 2)"},{"id":"RM","class":"Remove","in":["OUT"],"knobs":{"operation":"remove","channels":"pgC"}}],"output":"RM","layers":[["pgC",["pgC.red","pgC.green"]]],"plate":{"img":"photo"},"view":"rgb"},{"kind":"group","cat":"Normals & relight","id":"normal_blend","title":"Blend two normal maps","desc":"Adds a detail normal map onto a base (whiteout blend), so fine bumps follow the big shapes. Both inputs in the same encoding.","inputs":["base","detail"],"params":[{"n":"encoded","t":"bool","v":1,"l":"inputs are 0–1 normal maps"},{"n":"detail_amount","t":"float","v":1,"lo":0,"hi":3,"l":"detail amount"}],"nodes":[{"id":"DA","class":"Expression","in":["base"],"r":"parent.encoded ? r*2 - 1 : r","g":"parent.encoded ? g*2 - 1 : g","b":"parent.encoded ? b*2 - 1 : b"},{"id":"DB","class":"Expression","in":["detail"],"r":"(parent.encoded ? r*2 - 1 : r)*parent.detail_amount","g":"(parent.encoded ? g*2 - 1 : g)*parent.detail_amount","b":"mix(1, parent.encoded ? b*2 - 1 : b, parent.detail_amount)"},{"id":"CP","class":"Copy","in":["DA","DB"],"knobs":{"from0":"rgba.red","to0":"pgD.red","from1":"rgba.green","to1":"pgD.green","from2":"rgba.blue","to2":"pgD.blue"}},{"id":"OUT","class":"Expression","in":["CP"],"t":[["nx","r + pgD.red"],["ny","g + pgD.green"],["nz","b*pgD.blue"],["len","max(1e-6, sqrt(nx*nx + ny*ny + nz*nz))"]],"r":"parent.encoded ? nx/len*0.5 + 0.5 : nx/len","g":"parent.encoded ? ny/len*0.5 + 0.5 : ny/len","b":"parent.encoded ? nz/len*0.5 + 0.5 : nz/len","a":"1"},{"id":"RM","class":"Remove","in":["OUT"],"knobs":{"operation":"remove","channels":"pgD"}}],"output":"RM","layers":[["pgD",["pgD.red","pgD.green","pgD.blue"]]],"plate":{"base":"normals_enc","detail":"detail_enc"},"view":"rgb"},{"kind":"group","cat":"Normals & relight","id":"matcap","title":"Matcap shading","desc":"Shades normals with a matcap image (a lit sphere photo or render): instant clay, chrome or skin looks.","inputs":["normals","matcap"],"params":[{"n":"encoded","t":"bool","v":0,"l":"normals are 0–1"},{"n":"flip_y","t":"bool","v":0,"l":"flip y"},{"n":"zoom","t":"float","v":0.97,"lo":0.5,"hi":1.2,"l":"zoom"},{"n":"swap_stmap_inputs","t":"bool","v":0,"l":"swap STMap inputs (if result is wrong)"}],"nodes":[{"id":"UV","class":"Expression","in":["normals"],"t":[["nx","parent.encoded ? r*2 - 1 : r"],["ny","(parent.encoded ? g*2 - 1 : g)*(parent.flip_y ? -1 : 1)"]],"r":"nx*0.5*parent.zoom + 0.5","g":"ny*0.5*parent.zoom + 0.5","b":"0","a":"1"},{"id":"SW0","class":"Switch","in":["matcap","UV"],"expr":{"which":"parent.swap_stmap_inputs"}},{"id":"SW1","class":"Switch","in":["UV","matcap"],"expr":{"which":"parent.swap_stmap_inputs"}},{"id":"ST","class":"STMap","in":["SW0","SW1"],"knobs":{"uv":"rgb"}},{"id":"AL","class":"Copy","in":["ST","normals"],"knobs":{"from0":"rgba.alpha","to0":"rgba.alpha"}}],"output":"AL","layers":[],"plate":{"normals":"normals","matcap":"matcap"},"view":"rgb"},{"kind":"expr","cat":"Normals & relight","id":"normal_normalize","title":"Normalize vector","desc":"Makes every vector length 1. With only over 1 ticked it only shortens long vectors, like your mag > 1 version.","params":[{"n":"only_over_one","t":"bool","v":0,"l":"only over one"}],"t":[["mag","sqrt(r*r + g*g + b*b)"]],"plate":"normals","view":"rgb","c":"(mag > 0 && (mag > 1 || !only_over_one)) ? @/mag : @"},{"kind":"expr","cat":"Normals & relight","id":"normal_rebuild_z","title":"Rebuild normal Z","desc":"Recomputes blue from red and green for 2-channel normal maps. max(0, …) stops NaNs where r²+g² goes past 1.","params":[],"t":[["facing","sqrt(max(0, 1 - r*r - g*g))"]],"plate":"normals","view":"rgb","b":"facing"},{"kind":"expr","cat":"Normals & relight","id":"n_dot_vector","title":"N · vector","desc":"Dot product with the norm colour knob, divided by its length. Your Expression1 setup with any direction.","params":[{"n":"norm","t":"color","v":[0.5,0.5,0.7],"l":"norm"}],"t":[["len","max(1e-6, sqrt(norm.r*norm.r + norm.g*norm.g + norm.b*norm.b))"]],"plate":"normals","view":"a","a":"max((r*norm.r + g*norm.g + b*norm.b)/len, 0)"},{"kind":"expr","cat":"Normals & relight","id":"normals_decode","title":"Decode normal map (0–1 → -1–1)","desc":"For normal maps stored as images (purple-blue).","params":[],"t":[],"plate":"normals_enc","view":"rgb","c":"@*2 - 1"},{"kind":"expr","cat":"Normals & relight","id":"normals_encode","title":"Encode normals (-1–1 → 0–1)","desc":"Turns raw normals into a viewable normal-map image.","params":[],"t":[],"plate":"normals","view":"rgb","c":"@*0.5 + 0.5"},{"kind":"expr","cat":"Normals & relight","id":"normal_flip_green","title":"Flip green (OpenGL ↔ DirectX)","desc":"Inverts the Y of a normal map. Tick encoded for 0–1 maps.","params":[{"n":"encoded","t":"bool","v":0,"l":"encoded"}],"t":[],"plate":"normals","view":"rgb","g":"encoded ? 1 - g : -g"},{"kind":"expr","cat":"Normals & relight","id":"normal_rotate","title":"Rotate normals in screen","desc":"Spins the XY of the normals, which turns the light direction they react to.","params":[{"n":"angle","t":"float","v":45,"lo":-180,"hi":180,"l":"angle"}],"t":[["c","cos(angle*pi/180)"],["sn","sin(angle*pi/180)"]],"plate":"normals","view":"rgb","r":"r*c - g*sn","g":"r*sn + g*c"},{"kind":"expr","cat":"Normals & relight","id":"normal_strength","title":"Normal strength","desc":"Flattens (below 1) or exaggerates (above 1) a normal map and renormalizes it.","params":[{"n":"amount","t":"float","v":1.5,"lo":0,"hi":4,"l":"amount"}],"t":[["nx","r*amount"],["ny","g*amount"],["len","max(1e-6, sqrt(nx*nx + ny*ny + b*b))"]],"plate":"normals","view":"rgb","r":"nx/len","g":"ny/len","b":"b/len"},{"kind":"expr","cat":"Normals & relight","id":"normal_matrix","title":"Transform by 3×3 matrix","desc":"Multiplies the vector by three rows. Paste a camera's rotation to turn world normals into camera space.","params":[{"n":"row0","t":"color","v":[1,0,0],"l":"row0"},{"n":"row1","t":"color","v":[0,1,0],"l":"row1"},{"n":"row2","t":"color","v":[0,0,1],"l":"row2"}],"t":[],"plate":"normals","view":"rgb","r":"r*row0.r + g*row0.g + b*row0.b","g":"r*row1.r + g*row1.g + b*row1.b","b":"r*row2.r + g*row2.g + b*row2.b"},{"kind":"expr","cat":"Normals & relight","id":"shade_directional","title":"Directional light shading","desc":"Lambert shading from azimuth and elevation (elevation 90 = straight from camera). Normals in rgb, -1 to 1, z pointing at camera. Use Decode first for 0–1 normal maps.","params":[{"n":"azimuth","t":"float","v":135,"lo":-180,"hi":180,"l":"azimuth"},{"n":"elevation","t":"float","v":35,"lo":0,"hi":90,"l":"elevation"},{"n":"light_color","t":"color","v":[1,0.92,0.8],"l":"light color"},{"n":"intensity","t":"float","v":1,"lo":0,"hi":4,"l":"intensity"},{"n":"ambient","t":"float","v":0.1,"lo":0,"hi":1,"l":"ambient"}],"t":[["lx","cos(elevation*pi/180)*cos(azimuth*pi/180)"],["ly","cos(elevation*pi/180)*sin(azimuth*pi/180)"],["lz","sin(elevation*pi/180)"],["ndl","max(0, r*lx + g*ly + b*lz)"]],"plate":"normals","view":"rgb","r":"ambient + ndl*light_color.r*intensity","g":"ambient + ndl*light_color.g*intensity","b":"ambient + ndl*light_color.b*intensity"},{"kind":"expr","cat":"Normals & relight","id":"shade_point2d","title":"Point light 2D (viewer handle)","desc":"Drag light pos in the viewer. Height lifts the light off the image, falloff in pixels. Normals in rgb, -1 to 1, z pointing at camera. Use Decode first for 0–1 normal maps.","params":[{"n":"light_pos","t":"xy","v":[0.3,0.75],"frac":true,"l":"light pos"},{"n":"light_height","t":"float","v":400,"lo":1,"hi":3000,"l":"light height"},{"n":"falloff","t":"float","v":1500,"lo":1,"hi":6000,"l":"falloff"},{"n":"light_color","t":"color","v":[1,0.9,0.75],"l":"light color"},{"n":"intensity","t":"float","v":1.5,"lo":0,"hi":6,"l":"intensity"}],"t":[["ldx","light_pos.x - (x + 0.5)"],["ldy","light_pos.y - (y + 0.5)"],["ln","max(1e-6, sqrt(ldx*ldx + ldy*ldy + light_height*light_height))"],["lit","max(0, (r*ldx + g*ldy + b*light_height)/ln)/(1 + pow2(ln/falloff))*intensity"]],"plate":"normals","view":"rgb","r":"lit*light_color.r","g":"lit*light_color.g","b":"lit*light_color.b"},{"kind":"expr","cat":"Normals & relight","id":"spec_blinn","title":"Specular (Blinn)","desc":"Highlight from a directional light, viewer at the camera. Raise shininess for tighter highlights.","params":[{"n":"azimuth","t":"float","v":135,"lo":-180,"hi":180,"l":"azimuth"},{"n":"elevation","t":"float","v":35,"lo":0,"hi":90,"l":"elevation"},{"n":"shininess","t":"float","v":40,"lo":1,"hi":200,"l":"shininess"},{"n":"amount","t":"float","v":1,"lo":0,"hi":4,"l":"amount"}],"t":[["lx","cos(elevation*pi/180)*cos(azimuth*pi/180)"],["ly","cos(elevation*pi/180)*sin(azimuth*pi/180)"],["lz","sin(elevation*pi/180)"],["hl","sqrt(lx*lx + ly*ly + pow2(lz + 1))"]],"plate":"normals","view":"rgb","c":"pow(max(0, (r*lx + g*ly + b*(lz + 1))/hl), shininess)*amount"},{"kind":"expr","cat":"Normals & relight","id":"rim_fresnel","title":"Rim / Fresnel","desc":"Bright where surfaces turn away from camera. Schlick Fresnel with base reflectance f0.","params":[{"n":"f0","t":"float","v":0.04,"lo":0,"hi":1,"l":"f0"},{"n":"power","t":"float","v":5,"lo":1,"hi":10,"l":"power"},{"n":"rim_color","t":"color","v":[0.6,0.8,1],"l":"rim color"},{"n":"amount","t":"float","v":1,"lo":0,"hi":4,"l":"amount"}],"t":[["fr","f0 + (1 - f0)*pow(clamp(1 - abs(b)), power)"]],"plate":"normals","view":"rgb","r":"fr*rim_color.r*amount","g":"fr*rim_color.g*amount","b":"fr*rim_color.b*amount"},{"kind":"expr","cat":"Normals & relight","id":"toon_bands","title":"Toon bands","desc":"Cel shading: N·L quantised into bands.","params":[{"n":"azimuth","t":"float","v":135,"lo":-180,"hi":180,"l":"azimuth"},{"n":"elevation","t":"float","v":35,"lo":0,"hi":90,"l":"elevation"},{"n":"bands","t":"int","v":3,"lo":1,"hi":10,"l":"bands"},{"n":"tint","t":"color","v":[1,0.85,0.7],"l":"tint"}],"t":[["ndl","max(0, r*cos(elevation*pi/180)*cos(azimuth*pi/180) + g*cos(elevation*pi/180)*sin(azimuth*pi/180) + b*sin(elevation*pi/180))"],["q","ceil(ndl*bands)/bands"]],"plate":"normals","view":"rgb","r":"q*tint.r","g":"q*tint.g","b":"q*tint.b"},{"kind":"expr","cat":"Normals & relight","id":"hemisphere_light","title":"Sky / ground light","desc":"Ambient light from above and below. For world normals use green as up, for screen normals too.","params":[{"n":"sky","t":"color","v":[0.55,0.7,1],"l":"sky"},{"n":"ground","t":"color","v":[0.3,0.22,0.15],"l":"ground"},{"n":"intensity","t":"float","v":1,"lo":0,"hi":4,"l":"intensity"}],"t":[["h","clamp(g*0.5 + 0.5)"]],"plate":"normals","view":"rgb","r":"mix(ground.r, sky.r, h)*intensity","g":"mix(ground.g, sky.g, h)*intensity","b":"mix(ground.b, sky.b, h)*intensity"},{"kind":"expr","cat":"Normals & relight","id":"key_fill","title":"Key + fill lights","desc":"Two directional lights as direction vectors (colour knobs) with their own colours.","params":[{"n":"key_dir","t":"color","v":[-0.6,0.6,0.5],"l":"key dir"},{"n":"key_color","t":"color","v":[1,0.85,0.65],"l":"key color"},{"n":"fill_dir","t":"color","v":[0.7,-0.2,0.6],"l":"fill dir"},{"n":"fill_color","t":"color","v":[0.25,0.35,0.6],"l":"fill color"}],"t":[["kd","max(0, (r*key_dir.r + g*key_dir.g + b*key_dir.b)/max(1e-6, sqrt(key_dir.r*key_dir.r + key_dir.g*key_dir.g + key_dir.b*key_dir.b)))"],["fd","max(0, (r*fill_dir.r + g*fill_dir.g + b*fill_dir.b)/max(1e-6, sqrt(fill_dir.r*fill_dir.r + fill_dir.g*fill_dir.g + fill_dir.b*fill_dir.b)))"]],"plate":"normals","view":"rgb","r":"kd*key_color.r + fd*fill_color.r","g":"kd*key_color.g + fd*fill_color.g","b":"kd*key_color.b + fd*fill_color.b"},{"kind":"expr","cat":"Normals & relight","id":"up_matte","title":"Up-facing matte","desc":"Selects surfaces facing up (green of world normals). For snow, dust, rain wetness.","params":[{"n":"lo","t":"float","v":0.4,"lo":-1,"hi":1,"l":"lo"},{"n":"hi","t":"float","v":0.8,"lo":-1,"hi":1,"l":"hi"}],"t":[],"plate":"normals","view":"a","a":"smoothstep(lo, hi, g)"},{"kind":"expr","cat":"Normals & relight","id":"normal_to_idistort","title":"Normals → IDistort offset","desc":"Fake refraction: pixel offsets from normal XY. Set IDistort's UV channels to rgb.","params":[{"n":"amount","t":"float","v":40,"lo":0,"hi":200,"l":"amount"}],"t":[],"plate":"normals","view":"rgb","r":"r*amount","g":"g*amount","b":"0"},{"kind":"expr","cat":"Normals & relight","id":"fake_sss","title":"Wrap light + subsurface tint","desc":"Soft wrap-around diffuse with a coloured glow on the terminator. Applies to rgb using the N layer.","params":[{"n":"azimuth","t":"float","v":135,"lo":-180,"hi":180,"l":"azimuth"},{"n":"elevation","t":"float","v":35,"lo":0,"hi":90,"l":"elevation"},{"n":"wrap","t":"float","v":0.4,"lo":0,"hi":1,"l":"wrap"},{"n":"sss_color","t":"color","v":[1,0.3,0.2],"l":"sss color"},{"n":"sss","t":"float","v":0.5,"lo":0,"hi":2,"l":"sss"},{"n":"ambient","t":"float","v":0.35,"lo":0,"hi":1,"l":"ambient"}],"t":[["ndl","N.red*cos(elevation*pi/180)*cos(azimuth*pi/180) + N.green*cos(elevation*pi/180)*sin(azimuth*pi/180) + N.blue*sin(elevation*pi/180)"],["dw","clamp((ndl + wrap)/(1 + wrap))"],["term","pow(clamp(1 - abs(ndl)), 3)*sss*a"]],"plate":"sphere","view":"rgb","c":"@*(ambient + dw) + term*sss_color.@"},{"kind":"expr","cat":"Normals & relight","id":"p_point_light","title":"3D point light from P + N","desc":"Relights CG with a light at a world position. Needs P (world position) and N (world normals) layers.","params":[{"n":"light_pos","t":"xyz","v":[-1.5,1.2,1.5],"l":"light pos"},{"n":"light_color","t":"color","v":[1,0.9,0.75],"l":"light color"},{"n":"intensity","t":"float","v":1.5,"lo":0,"hi":10,"l":"intensity"},{"n":"falloff","t":"float","v":2,"lo":0.01,"hi":20,"l":"falloff"},{"n":"ambient","t":"float","v":0.4,"lo":0,"hi":2,"l":"ambient"}],"t":[["lx","light_pos.x - P.red"],["ly","light_pos.y - P.green"],["lz","light_pos.z - P.blue"],["d","max(1e-6, sqrt(lx*lx + ly*ly + lz*lz))"]],"plate":"sphere","view":"rgb","c":"@*(ambient + max(0, (N.red*lx + N.green*ly + N.blue*lz)/d)*light_color.@*intensity/(1 + pow2(d/falloff)))"},{"kind":"expr","cat":"Light & glow (2D)","id":"point_glow","title":"Point glow","desc":"Adds an inverse-square glow at a viewer handle.","params":[{"n":"pos","t":"xy","v":[0.62,0.62],"frac":true,"l":"pos"},{"n":"radius","t":"float","v":60,"lo":1,"hi":600,"l":"radius"},{"n":"glow_color","t":"color","v":[1,0.7,0.35],"l":"glow color"},{"n":"intensity","t":"float","v":1,"lo":0,"hi":10,"l":"intensity"}],"t":[["d","hypot(x + 0.5 - pos.x, y + 0.5 - pos.y)"],["gl","intensity/(1 + pow2(d/radius))"]],"plate":"photo","view":"rgb","c":"@ + glow_color.@*gl"},{"kind":"expr","cat":"Light & glow (2D)","id":"spotlight_2d","title":"Spotlight","desc":"Keeps a soft circle lit and darkens the rest.","params":[{"n":"pos","t":"xy","v":[0.5,0.5],"frac":true,"l":"pos"},{"n":"radius","t":"float","v":420,"lo":1,"hi":2000,"l":"radius"},{"n":"softness","t":"float","v":0.6,"lo":0,"hi":1,"l":"softness"},{"n":"outside","t":"float","v":0.25,"lo":0,"hi":1,"l":"outside"}],"t":[["d","hypot(x + 0.5 - pos.x, y + 0.5 - pos.y)"],["m","1 - smoothstep(radius*(1 - softness), radius, d)"]],"plate":"photo","view":"rgb","c":"@*mix(outside, 1, m)"},{"kind":"expr","cat":"Light & glow (2D)","id":"two_point_gradient","title":"Gradient between two points","desc":"0 at point A, 1 at point B, projected along the line. Drag both handles.","params":[{"n":"pa","t":"xy","v":[0.2,0.2],"frac":true,"l":"pa"},{"n":"pb","t":"xy","v":[0.8,0.8],"frac":true,"l":"pb"},{"n":"smooth","t":"bool","v":1,"l":"smooth"}],"t":[["vx","pb.x - pa.x"],["vy","pb.y - pa.y"],["tt","clamp(((x + 0.5 - pa.x)*vx + (y + 0.5 - pa.y)*vy)/max(1e-6, vx*vx + vy*vy))"]],"plate":"photo","view":"a","a":"smooth ? smoothstep(0, 1, tt) : tt"},{"kind":"expr","cat":"Light & glow (2D)","id":"light_beam","title":"Light beam","desc":"A cone of light from a point, aimed by direction, with spread and length.","params":[{"n":"pos","t":"xy","v":[0.1,0.9],"frac":true,"l":"pos"},{"n":"direction","t":"float","v":-40,"lo":-180,"hi":180,"l":"direction"},{"n":"spread","t":"float","v":18,"lo":1,"hi":90,"l":"spread"},{"n":"length","t":"float","v":1200,"lo":10,"hi":5000,"l":"length"},{"n":"beam_color","t":"color","v":[1,0.9,0.7],"l":"beam color"},{"n":"intensity","t":"float","v":0.8,"lo":0,"hi":4,"l":"intensity"}],"t":[["dx","x + 0.5 - pos.x"],["dy","y + 0.5 - pos.y"],["dd","max(1e-6, hypot(dx, dy))"],["ad","acos(clamp((dx*cos(direction*pi/180) + dy*sin(direction*pi/180))/dd, -1, 1))*180/pi"]],"plate":"photo","view":"rgb","c":"@ + beam_color.@*intensity*(1 - smoothstep(spread*0.4, spread, ad))*exp(-dd/length)"},{"kind":"expr","cat":"Light & glow (2D)","id":"anamorphic_streak","title":"Anamorphic streak","desc":"A long horizontal flare streak through a point.","params":[{"n":"pos","t":"xy","v":[0.62,0.62],"frac":true,"l":"pos"},{"n":"length","t":"float","v":500,"lo":10,"hi":3000,"l":"length"},{"n":"thickness","t":"float","v":3,"lo":0.5,"hi":40,"l":"thickness"},{"n":"streak_color","t":"color","v":[0.4,0.6,1],"l":"streak color"},{"n":"intensity","t":"float","v":2,"lo":0,"hi":10,"l":"intensity"}],"t":[["sk","exp(-abs(y + 0.5 - pos.y)/thickness)*exp(-abs(x + 0.5 - pos.x)/length)*intensity"]],"plate":"photo","view":"rgb","c":"@ + streak_color.@*sk"},{"kind":"expr","cat":"Light & glow (2D)","id":"caustics","title":"Caustics","desc":"Animated ridged noise, like light through water. Multiply or add it onto a plate.","params":[{"n":"scale","t":"float","v":0.006,"lo":0.0005,"hi":0.05,"l":"scale"},{"n":"speed","t":"float","v":0.04,"lo":0,"hi":0.5,"l":"speed"},{"n":"sharpness","t":"float","v":6,"lo":1,"hi":20,"l":"sharpness"},{"n":"intensity","t":"float","v":1,"lo":0,"hi":4,"l":"intensity"}],"t":[["n1","1 - abs(noise(x*scale, y*scale, frame*speed))"],["n2","1 - abs(noise(x*scale*1.7 + 13, y*scale*1.7 + 7, frame*speed*1.3))"]],"plate":"black","view":"rgb","c":"pow(n1*n2, sharpness)*intensity*4","a":"1"},{"kind":"expr","cat":"Distortion STMaps","id":"stmap_polar_to_rect","title":"Polar → rectangular","desc":"Unwraps a circle around a centre into a strip: x is angle, y is radius. Feed into an STMap node (uv channels = rgb) with your plate in src.","params":[{"n":"center","t":"xy","v":[0.5,0.5],"frac":true,"l":"center"},{"n":"max_radius","t":"float","v":540,"lo":1,"hi":4000,"l":"max radius"}],"t":[["ang","(x + 0.5)/width*2*pi"],["rad","(y + 0.5)/height*max_radius"]],"plate":"black","view":"stmap","r":"(center.x + rad*cos(ang))/width","g":"(center.y + rad*sin(ang))/height","b":"0","a":"1"},{"kind":"expr","cat":"Distortion STMaps","id":"stmap_rect_to_polar","title":"Rectangular → polar","desc":"Wraps the image around a centre: the bottom edge becomes the middle. Tiny planets. Feed into an STMap node (uv channels = rgb) with your plate in src.","params":[{"n":"center","t":"xy","v":[0.5,0.5],"frac":true,"l":"center"},{"n":"max_radius","t":"float","v":540,"lo":1,"hi":4000,"l":"max radius"},{"n":"rotate","t":"float","v":0,"lo":-180,"hi":180,"l":"rotate"}],"t":[["dx","x + 0.5 - center.x"],["dy","y + 0.5 - center.y"]],"plate":"black","view":"stmap","r":"fmod(atan2(dy, dx) + rotate*pi/180 + 4*pi, 2*pi)/(2*pi)","g":"hypot(dx, dy)/max_radius","b":"0","a":"1"},{"kind":"expr","cat":"Distortion STMaps","id":"stmap_swirl","title":"Swirl","desc":"Twists the image around a point, strongest in the centre. Feed into an STMap node (uv channels = rgb) with your plate in src.","params":[{"n":"center","t":"xy","v":[0.5,0.5],"frac":true,"l":"center"},{"n":"radius","t":"float","v":450,"lo":1,"hi":3000,"l":"radius"},{"n":"twist","t":"float","v":180,"lo":-1080,"hi":1080,"l":"twist"}],"t":[["dx","x + 0.5 - center.x"],["dy","y + 0.5 - center.y"],["d","hypot(dx, dy)"],["rot","twist*pi/180*pow2(clamp(1 - d/radius))"]],"plate":"black","view":"stmap","r":"(center.x + dx*cos(rot) - dy*sin(rot))/width","g":"(center.y + dx*sin(rot) + dy*cos(rot))/height","b":"0","a":"1"},{"kind":"expr","cat":"Distortion STMaps","id":"stmap_kaleidoscope","title":"Kaleidoscope","desc":"Mirrors one wedge around the centre into segments. Feed into an STMap node (uv channels = rgb) with your plate in src.","params":[{"n":"center","t":"xy","v":[0.5,0.5],"frac":true,"l":"center"},{"n":"segments","t":"int","v":6,"lo":2,"hi":24,"l":"segments"},{"n":"rotate","t":"float","v":0,"lo":-180,"hi":180,"l":"rotate"}],"t":[["dx","x + 0.5 - center.x"],["dy","y + 0.5 - center.y"],["wd","2*pi/segments"],["ang","abs(fmod(atan2(dy, dx) + rotate*pi/180 + 8*pi, wd) - wd/2)"]],"plate":"black","view":"stmap","r":"(center.x + hypot(dx, dy)*cos(ang))/width","g":"(center.y + hypot(dx, dy)*sin(ang))/height","b":"0","a":"1"},{"kind":"expr","cat":"Distortion STMaps","id":"stmap_ripple","title":"Ripple","desc":"Animated circular waves that fade with distance. Feed into an STMap node (uv channels = rgb) with your plate in src.","params":[{"n":"center","t":"xy","v":[0.5,0.5],"frac":true,"l":"center"},{"n":"wavelength","t":"float","v":60,"lo":2,"hi":400,"l":"wavelength"},{"n":"amplitude","t":"float","v":8,"lo":0,"hi":100,"l":"amplitude"},{"n":"speed","t":"float","v":4,"lo":-40,"hi":40,"l":"speed"},{"n":"decay","t":"float","v":600,"lo":1,"hi":4000,"l":"decay"}],"t":[["dx","x + 0.5 - center.x"],["dy","y + 0.5 - center.y"],["d","max(1e-6, hypot(dx, dy))"],["off","sin((d - frame*speed)*2*pi/wavelength)*amplitude*exp(-d/decay)"]],"plate":"black","view":"stmap","r":"(x + 0.5 + dx/d*off)/width","g":"(y + 0.5 + dy/d*off)/height","b":"0","a":"1"},{"kind":"expr","cat":"Distortion STMaps","id":"stmap_wave","title":"Sine wave","desc":"Shifts rows sideways with a travelling sine. Heat shimmer, underwater, flags. Feed into an STMap node (uv channels = rgb) with your plate in src.","params":[{"n":"amplitude","t":"float","v":12,"lo":0,"hi":200,"l":"amplitude"},{"n":"wavelength","t":"float","v":120,"lo":2,"hi":1000,"l":"wavelength"},{"n":"speed","t":"float","v":3,"lo":-40,"hi":40,"l":"speed"}],"t":[],"plate":"black","view":"stmap","r":"(x + 0.5 + sin((y + frame*speed)*2*pi/wavelength)*amplitude)/width","g":"(y + 0.5)/height","b":"0","a":"1"},{"kind":"expr","cat":"Distortion STMaps","id":"stmap_noise_warp","title":"Noise warp","desc":"Organic wobble from animated noise. Feed into an STMap node (uv channels = rgb) with your plate in src.","params":[{"n":"amplitude","t":"float","v":25,"lo":0,"hi":300,"l":"amplitude"},{"n":"scale","t":"float","v":0.004,"lo":0.0002,"hi":0.05,"l":"scale"},{"n":"speed","t":"float","v":0.03,"lo":0,"hi":0.5,"l":"speed"}],"t":[],"plate":"black","view":"stmap","r":"(x + 0.5 + noise(x*scale, y*scale, frame*speed)*amplitude)/width","g":"(y + 0.5 + noise(x*scale + 31.7, y*scale + 11.3, frame*speed)*amplitude)/height","b":"0","a":"1"},{"kind":"expr","cat":"Distortion STMaps","id":"stmap_tile","title":"Tile / mirror repeat","desc":"Repeats the image tiles × tiles, optionally mirrored so seams match. Feed into an STMap node (uv channels = rgb) with your plate in src.","params":[{"n":"tiles","t":"float","v":3,"lo":1,"hi":20,"l":"tiles"},{"n":"mirror","t":"bool","v":1,"l":"mirror"}],"t":[["tu","(x + 0.5)/width*tiles"],["tv","(y + 0.5)/height*tiles"]],"plate":"black","view":"stmap","r":"mirror ? 1 - abs(fmod(tu, 2) - 1) : fmod(tu, 1)","g":"mirror ? 1 - abs(fmod(tv, 2) - 1) : fmod(tv, 1)","b":"0","a":"1"},{"kind":"expr","cat":"Distortion STMaps","id":"stmap_bulge","title":"Bulge / pinch","desc":"Fisheye bulge (power below 1) or pinch (above 1) inside a radius. Feed into an STMap node (uv channels = rgb) with your plate in src.","params":[{"n":"center","t":"xy","v":[0.5,0.5],"frac":true,"l":"center"},{"n":"radius","t":"float","v":500,"lo":1,"hi":3000,"l":"radius"},{"n":"power","t":"float","v":0.6,"lo":0.1,"hi":3,"l":"power"}],"t":[["dx","x + 0.5 - center.x"],["dy","y + 0.5 - center.y"],["d","max(1e-6, hypot(dx, dy))"],["nd","d < radius ? pow(d/radius, power)*radius : d"]],"plate":"black","view":"stmap","r":"(center.x + dx/d*nd)/width","g":"(center.y + dy/d*nd)/height","b":"0","a":"1"},{"kind":"expr","cat":"Distortion STMaps","id":"stmap_pixelate","title":"Pixelate (mosaic)","desc":"Every block samples its centre pixel. Feed into an STMap node (uv channels = rgb) with your plate in src.","params":[{"n":"block","t":"float","v":32,"lo":1,"hi":400,"l":"block"}],"t":[],"plate":"black","view":"stmap","r":"(floor(x/block)*block + block/2)/width","g":"(floor(y/block)*block + block/2)/height","b":"0","a":"1"},{"kind":"expr","cat":"Distortion STMaps","id":"stmap_zoom_rotate","title":"Zoom and rotate","desc":"Scales and rotates around a viewer handle. Feed into an STMap node (uv channels = rgb) with your plate in src.","params":[{"n":"center","t":"xy","v":[0.5,0.5],"frac":true,"l":"center"},{"n":"zoom","t":"float","v":1.5,"lo":0.1,"hi":10,"l":"zoom"},{"n":"rotate","t":"float","v":15,"lo":-180,"hi":180,"l":"rotate"}],"t":[["dx","(x + 0.5 - center.x)/zoom"],["dy","(y + 0.5 - center.y)/zoom"],["c","cos(-rotate*pi/180)"],["sn","sin(-rotate*pi/180)"]],"plate":"black","view":"stmap","r":"(center.x + dx*c - dy*sn)/width","g":"(center.y + dx*sn + dy*c)/height","b":"0","a":"1"},{"kind":"expr","cat":"Colour","id":"luminance","title":"Luminance (Rec.709)","desc":"Weighted grey. For ACEScg use 0.2722, 0.6741, 0.0537.","params":[],"t":[["l","0.2126*r + 0.7152*g + 0.0722*b"]],"plate":"sphere","view":"rgb","c":"l"},{"kind":"expr","cat":"Colour","id":"saturation","title":"Saturation","desc":"sat 0 is grey, 1 is unchanged, above 1 boosts.","params":[{"n":"sat","t":"float","v":0.5,"lo":0,"hi":1.5,"l":"sat"}],"t":[["l","0.2126*r + 0.7152*g + 0.0722*b"]],"plate":"sphere","view":"rgb","c":"lerp(l, @, sat)"},{"kind":"expr","cat":"Colour","id":"invert","title":"Invert","desc":"1 minus the channel. Alpha is left alone.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"1 - @"},{"kind":"expr","cat":"Colour","id":"swap_rb","title":"Swap red and blue","desc":"Any channel can read any other; reorder freely.","params":[],"t":[],"plate":"sphere","view":"rgb","r":"b","b":"r"},{"kind":"expr","cat":"Colour","id":"exposure","title":"Exposure in stops","desc":"Each stop doubles or halves the light, like a camera.","params":[{"n":"stops","t":"float","v":1.0,"lo":0,"hi":3.0,"l":"stops"}],"t":[],"plate":"sphere","view":"rgb","c":"@*pow(2, stops)"},{"kind":"expr","cat":"Colour","id":"gamma","title":"Gamma","desc":"Negative values pass through unchanged so pow doesn't return NaN.","params":[{"n":"gamma_v","t":"float","v":2.2,"lo":0,"hi":6.6000000000000005,"l":"gamma"}],"t":[],"plate":"sphere","view":"rgb","c":"@ > 0 ? pow(@, 1/gamma_v) : @"},{"kind":"expr","cat":"Colour","id":"contrast_pivot","title":"Contrast around a pivot","desc":"Log-style contrast that keeps the pivot (mid grey 0.18) fixed.","params":[{"n":"contrast","t":"float","v":1.3,"lo":0,"hi":3.9000000000000004,"l":"contrast"},{"n":"pivot","t":"float","v":0.18,"lo":0,"hi":0.54,"l":"pivot"}],"t":[],"plate":"sphere","view":"rgb","c":"@ > 0 ? pivot*pow(@/pivot, contrast) : @"},{"kind":"expr","cat":"Colour","id":"lift_gain","title":"Lift and gain","desc":"Remaps 0 to lift and 1 to gain, like Grade's lift and gain.","params":[{"n":"lift","t":"float","v":0.02,"lo":0,"hi":0.06,"l":"lift"},{"n":"gain","t":"float","v":1.1,"lo":0,"hi":3.3000000000000003,"l":"gain"}],"t":[],"plate":"sphere","view":"rgb","c":"lerp(lift, gain, @)"},{"kind":"expr","cat":"Colour","id":"posterize","title":"Posterize","desc":"Quantises each channel to a number of steps.","params":[{"n":"steps","t":"int","v":6,"lo":1,"hi":24,"l":"steps"}],"t":[],"plate":"sphere","view":"rgb","c":"floor(@*steps)/steps"},{"kind":"expr","cat":"Colour","id":"threshold","title":"Threshold","desc":"Pure black and white from luminance.","params":[],"t":[["l","0.2126*r + 0.7152*g + 0.0722*b"]],"plate":"sphere","view":"rgb","c":"l > 0.5 ? 1 : 0"},{"kind":"expr","cat":"Colour","id":"solarize","title":"Solarize","desc":"Inverts everything above 0.5.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"@ > 0.5 ? 1 - @ : @"},{"kind":"expr","cat":"Colour","id":"clamp_01","title":"Clamp 0–1","desc":"clamp(x) with one argument clamps to 0–1. Use clamp(x, lo, hi) for other ranges.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"clamp(@)"},{"kind":"expr","cat":"Colour","id":"soft_clip","title":"Soft clip highlights","desc":"Rolls values above the knee smoothly towards 1 instead of clipping.","params":[{"n":"knee","t":"float","v":0.8,"lo":0,"hi":2.4000000000000004,"l":"knee"}],"t":[],"plate":"sphere","view":"rgb","c":"@ > knee ? knee + (1 - knee)*tanh((@ - knee)/(1 - knee)) : @"},{"kind":"expr","cat":"Colour","id":"srgb_to_linear","title":"sRGB to linear","desc":"The exact piecewise sRGB curve, not a 2.2 gamma.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"@ <= 0.04045 ? @/12.92 : pow((@ + 0.055)/1.055, 2.4)"},{"kind":"expr","cat":"Colour","id":"linear_to_srgb","title":"Linear to sRGB","desc":"The inverse of the curve above.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"@ <= 0.0031308 ? @*12.92 : 1.055*pow(@, 1/2.4) - 0.055"},{"kind":"expr","cat":"Colour","id":"heat_map","title":"Heat map","desc":"Luminance as black, red, yellow, white.","params":[],"t":[["l","0.2126*r + 0.7152*g + 0.0722*b"]],"plate":"sphere","view":"rgb","r":"clamp(l*3)","g":"clamp(l*3 - 1)","b":"clamp(l*3 - 2)"},{"kind":"expr","cat":"Colour","id":"duotone","title":"Duotone","desc":"Maps shadows to one colour and highlights to another.","params":[],"t":[["l","0.2126*r + 0.7152*g + 0.0722*b"]],"plate":"sphere","view":"rgb","r":"lerp(0.05, 1.0, l)","g":"lerp(0.08, 0.75, l)","b":"lerp(0.25, 0.45, l)"},{"kind":"expr","cat":"Colour","id":"warm_cool","title":"Warm / cool balance","desc":"Positive warm adds red and removes blue; negative cools.","params":[{"n":"warm","t":"float","v":0.1,"lo":0,"hi":0.30000000000000004,"l":"warm"}],"t":[],"plate":"sphere","view":"rgb","r":"r*(1 + warm)","b":"b*(1 - warm)"},{"kind":"expr","cat":"Colour","id":"hue_rotate","title":"Hue rotate","desc":"Rotates hue around the grey axis, keeping luminance roughly steady.","params":[{"n":"hue","t":"float","v":60,"lo":-180,"hi":180,"l":"hue"}],"t":[["c","cos(hue*pi/180)"],["sn","sin(hue*pi/180)*0.57735"],["d","(1 - cos(hue*pi/180))/3"]],"plate":"photo","view":"rgb","r":"r*(c + d) + g*(d - sn) + b*(d + sn)","g":"r*(d + sn) + g*(c + d) + b*(d - sn)","b":"r*(d - sn) + g*(d + sn) + b*(c + d)"},{"kind":"expr","cat":"Colour","id":"channel_mixer","title":"Channel mixer","desc":"Each output channel is a mix of the inputs. Rows are the weights of r, g, b.","params":[{"n":"red_out","t":"color","v":[1,0,0],"l":"red out"},{"n":"green_out","t":"color","v":[0,1,0],"l":"green out"},{"n":"blue_out","t":"color","v":[0.2,0.2,0.6],"l":"blue out"}],"t":[],"plate":"photo","view":"rgb","r":"r*red_out.r + g*red_out.g + b*red_out.b","g":"r*green_out.r + g*green_out.g + b*green_out.b","b":"r*blue_out.r + g*blue_out.g + b*blue_out.b"},{"kind":"expr","cat":"Colour","id":"hue_key","title":"Hue key","desc":"Selects a hue from a picked colour, by angle in the chroma plane. Ignores grey pixels below min sat.","params":[{"n":"target","t":"color","v":[0.1,0.6,0.15],"l":"target"},{"n":"tolerance","t":"float","v":20,"lo":0,"hi":180,"l":"tolerance"},{"n":"softness","t":"float","v":20,"lo":0,"hi":180,"l":"softness"},{"n":"min_sat","t":"float","v":0.05,"lo":0,"hi":1,"l":"min sat"}],"t":[["cx","r - (g + b)/2"],["cy","(g - b)*0.866"],["tcx","target.r - (target.g + target.b)/2"],["tcy","(target.g - target.b)*0.866"]],"plate":"sphere","view":"a","a":"(1 - smoothstep(tolerance, tolerance + softness, acos(clamp((cx*tcx + cy*tcy)/(hypot(cx, cy)*hypot(tcx, tcy) + 1e-9), -1, 1))*180/pi))*smoothstep(0, min_sat, hypot(cx, cy))"},{"kind":"expr","cat":"Colour","id":"vibrance","title":"Vibrance","desc":"Boosts saturation more on dull colours than on already strong ones.","params":[{"n":"amount","t":"float","v":0.8,"lo":-1,"hi":3,"l":"amount"}],"t":[["mx","max(r, max(g, b))"],["mn","min(r, min(g, b))"],["l","0.2126*r + 0.7152*g + 0.0722*b"],["st","mx > 0 ? (mx - mn)/mx : 0"]],"plate":"photo","view":"rgb","c":"mix(l, @, 1 + amount*(1 - st))"},{"kind":"expr","cat":"Colour","id":"filmic_aces","title":"Filmic tonemap (ACES fit)","desc":"Narkowicz's ACES curve: compresses highlights into 0–1 for a filmic look.","params":[{"n":"exposure","t":"float","v":0,"lo":-6,"hi":6,"l":"exposure"}],"t":[["e","pow(2, exposure)"]],"plate":"sphere","view":"rgb","c":"@ > 0 ? clamp((@*e*(2.51*@*e + 0.03))/(@*e*(2.43*@*e + 0.59) + 0.14)) : 0"},{"kind":"expr","cat":"Colour","id":"reinhard","title":"Reinhard tonemap","desc":"Rolls off highlights; white is the value that maps to 1.","params":[{"n":"white","t":"float","v":4,"lo":1,"hi":50,"l":"white"}],"t":[],"plate":"sphere","view":"rgb","c":"@ > 0 ? @*(1 + @/(white*white))/(1 + @) : @"},{"kind":"expr","cat":"Colour","id":"gradient_map","title":"Gradient map (3 colours)","desc":"Maps luminance onto shadow, mid and highlight colours.","params":[{"n":"shadows","t":"color","v":[0.05,0.03,0.15],"l":"shadows"},{"n":"mids","t":"color","v":[0.8,0.3,0.25],"l":"mids"},{"n":"highs","t":"color","v":[1,0.95,0.75],"l":"highs"}],"t":[["l","clamp(0.2126*r + 0.7152*g + 0.0722*b)"]],"plate":"photo","view":"rgb","c":"l < 0.5 ? mix(shadows.@, mids.@, l*2) : mix(mids.@, highs.@, (l - 0.5)*2)"},{"kind":"expr","cat":"Colour","id":"day_for_night","title":"Day for night","desc":"Desaturates, tints blue and underexposes.","params":[{"n":"saturation","t":"float","v":0.35,"lo":0,"hi":1,"l":"saturation"},{"n":"tint","t":"color","v":[0.55,0.75,1.1],"l":"tint"},{"n":"exposure","t":"float","v":-2,"lo":-6,"hi":2,"l":"exposure"}],"t":[["l","0.2126*r + 0.7152*g + 0.0722*b"]],"plate":"photo","view":"rgb","c":"mix(l, @, saturation)*tint.@*pow(2, exposure)"},{"kind":"expr","cat":"Colour","id":"bleach_bypass","title":"Bleach bypass","desc":"Overlays luminance on the image: crunchy contrast, low saturation.","params":[{"n":"amount","t":"float","v":0.7,"lo":0,"hi":1,"l":"amount"}],"t":[["l","clamp(0.2126*r + 0.7152*g + 0.0722*b)"]],"plate":"photo","view":"rgb","c":"mix(@, @ < 0.5 ? 2*@*l : 1 - 2*(1 - @)*(1 - l), amount)"},{"kind":"expr","cat":"Colour","id":"split_tone","title":"Split toning","desc":"Tints shadows and highlights separately, balanced around a pivot.","params":[{"n":"shadow_tint","t":"color","v":[0.85,1,1.15],"l":"shadow tint"},{"n":"high_tint","t":"color","v":[1.15,1.02,0.85],"l":"high tint"},{"n":"balance","t":"float","v":0.4,"lo":0,"hi":1,"l":"balance"}],"t":[["l","0.2126*r + 0.7152*g + 0.0722*b"]],"plate":"photo","view":"rgb","c":"@*mix(shadow_tint.@, high_tint.@, smoothstep(balance - 0.3, balance + 0.3, l))"},{"kind":"expr","cat":"Colour","id":"neutralise_grey","title":"Neutralise a picked grey","desc":"Pick something that should be grey: the cast is divided out, brightness kept.","params":[{"n":"neutral","t":"color","v":[0.5,0.45,0.38],"l":"neutral"}],"t":[["nl","0.2126*neutral.r + 0.7152*neutral.g + 0.0722*neutral.b"]],"plate":"photo","view":"rgb","c":"@*nl/max(neutral.@, 1e-6)"},{"kind":"expr","cat":"Colour","id":"cineon_to_lin","title":"Cineon log → linear","desc":"Standard Cineon: black 95, white 685, 0.6 gamma.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"(pow(10, (@*1023 - 685)/300) - 0.0108)/(1 - 0.0108)"},{"kind":"expr","cat":"Colour","id":"lin_to_cineon","title":"Linear → Cineon log","desc":"The inverse, for writing log DPX by hand.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"(685 + 300*log10(max(1e-6, @*(1 - 0.0108) + 0.0108)))/1023"},{"kind":"expr","cat":"Keying & despill","id":"green_matte","title":"Green screen matte","desc":"Colour-difference key: green minus the larger of red and blue. Raise gain to harden.","params":[{"n":"gain","t":"float","v":4.0,"lo":0,"hi":12.0,"l":"gain"}],"t":[],"plate":"sphere","view":"a","a":"clamp(1 - (g - max(r, b))*gain)"},{"kind":"expr","cat":"Keying & despill","id":"blue_matte","title":"Blue screen matte","desc":"The same colour-difference key for blue screens.","params":[{"n":"gain","t":"float","v":4.0,"lo":0,"hi":12.0,"l":"gain"}],"t":[],"plate":"sphere","view":"a","a":"clamp(1 - (b - max(r, g))*gain)"},{"kind":"expr","cat":"Keying & despill","id":"luma_key","title":"Luma key","desc":"Soft key between two luminance levels.","params":[],"t":[["l","0.2126*r + 0.7152*g + 0.0722*b"]],"plate":"sphere","view":"a","a":"smoothstep(0.3, 0.6, l)"},{"kind":"expr","cat":"Keying & despill","id":"colour_distance_key","title":"Colour distance key","desc":"Distance in RGB from the key colour (kr, kg, kb). Inside 0.1 is fully keyed, beyond 0.35 is solid.","params":[{"n":"kr","t":"float","v":0.1,"lo":0,"hi":0.30000000000000004,"l":"kr"},{"n":"kg","t":"float","v":0.6,"lo":0,"hi":1.7999999999999998,"l":"kg"},{"n":"kb","t":"float","v":0.15,"lo":0,"hi":0.44999999999999996,"l":"kb"}],"t":[["d","sqrt(pow2(r - kr) + pow2(g - kg) + pow2(b - kb))"]],"plate":"sphere","view":"a","a":"smoothstep(0.1, 0.35, d)"},{"kind":"expr","cat":"Keying & despill","id":"despill_average","title":"Green despill (average)","desc":"Limits green to the average of red and blue. The most neutral of the three.","params":[],"t":[],"plate":"sphere","view":"rgb","g":"min(g, (r + b)/2)"},{"kind":"expr","cat":"Keying & despill","id":"despill_red","title":"Green despill (red limit)","desc":"Limits green to red. Strong; keeps skin warm.","params":[],"t":[],"plate":"sphere","view":"rgb","g":"min(g, r)"},{"kind":"expr","cat":"Keying & despill","id":"despill_max","title":"Green despill (max limit)","desc":"Limits green to the larger of red and blue. The gentlest; keeps yellows and cyans.","params":[],"t":[],"plate":"sphere","view":"rgb","g":"min(g, max(r, b))"},{"kind":"expr","cat":"Keying & despill","id":"despill_blue","title":"Blue despill","desc":"Limits blue to the average of red and green.","params":[],"t":[],"plate":"sphere","view":"rgb","b":"min(b, (r + g)/2)"},{"kind":"expr","cat":"Keying & despill","id":"spill_map","title":"Spill map","desc":"How much green the average despill removes. Use it as a mask or to add BG light back.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"max(0, g - (r + b)/2)"},{"kind":"expr","cat":"Keying & despill","id":"despill_restore","title":"Despill with luminance restore","desc":"Despills green, then adds the lost brightness back as neutral grey. amt 0–1.","params":[{"n":"amount","t":"float","v":1.0,"lo":0,"hi":3.0,"l":"amount"}],"t":[["sp","max(0, g - (r + b)/2)"]],"plate":"sphere","view":"rgb","r":"r + sp*0.7152*amount","g":"g - sp + sp*0.7152*amount","b":"b + sp*0.7152*amount"},{"kind":"expr","cat":"Alpha & mattes","id":"unpremult","title":"Unpremultiply (safe)","desc":"Divides by alpha only where alpha is above 0, so there's no inf or NaN.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"a > 0 ? @/a : @"},{"kind":"expr","cat":"Alpha & mattes","id":"premult","title":"Premultiply","desc":"Multiplies colour by alpha.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"@*a"},{"kind":"expr","cat":"Alpha & mattes","id":"alpha_from_luma","title":"Alpha from luminance","desc":"Useful for elements shot on black: smoke, sparks, flares.","params":[],"t":[],"plate":"sphere","view":"a","a":"0.2126*r + 0.7152*g + 0.0722*b"},{"kind":"expr","cat":"Alpha & mattes","id":"alpha_from_max","title":"Alpha from max RGB","desc":"Any lit pixel gets alpha. Stronger than luminance for saturated elements.","params":[],"t":[],"plate":"sphere","view":"a","a":"max(r, max(g, b))"},{"kind":"expr","cat":"Alpha & mattes","id":"matte_levels","title":"Matte levels (crunch)","desc":"Anything below lo goes to 0, above hi to 1.","params":[{"n":"lo","t":"float","v":0.1,"lo":0,"hi":0.30000000000000004,"l":"lo"},{"n":"hi","t":"float","v":0.9,"lo":0,"hi":2.7,"l":"hi"}],"t":[],"plate":"sphere","view":"a","a":"clamp((a - lo)/(hi - lo))"},{"kind":"expr","cat":"Alpha & mattes","id":"binarise","title":"Binarise alpha","desc":"Hard 0 or 1 at 0.5.","params":[],"t":[],"plate":"sphere","view":"a","a":"a > 0.5 ? 1 : 0"},{"kind":"expr","cat":"Alpha & mattes","id":"invert_alpha","title":"Invert alpha","desc":"Holdout from a matte.","params":[],"t":[],"plate":"sphere","view":"a","a":"1 - a"},{"kind":"expr","cat":"Alpha & mattes","id":"edge_matte","title":"Edge matte","desc":"Peaks where alpha is 0.5, zero at solid core and background. For edge-only fixes.","params":[],"t":[],"plate":"sphere","view":"a","a":"clamp(4*a*(1 - a))"},{"kind":"expr","cat":"Alpha & mattes","id":"alpha_to_rgb","title":"Alpha to RGB","desc":"Shows the alpha in all three colour channels.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"a"},{"kind":"expr","cat":"Alpha & mattes","id":"solid_alpha","title":"Solid alpha","desc":"Sets alpha to 1 everywhere.","params":[],"t":[],"plate":"sphere","view":"a","a":"1"},{"kind":"expr","cat":"QC & fixes","id":"kill_nan","title":"Remove NaN and inf","desc":"NaN is the only value not equal to itself, so x == x catches it. Huge values count as inf.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"(@ == @ && abs(@) < 1e20) ? @ : 0","a":"(a == a && abs(a) < 1e20) ? a : 0"},{"kind":"expr","cat":"QC & fixes","id":"clamp_negatives","title":"Clamp negatives","desc":"Zeroes negative values and keeps superwhites.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"max(@, 0)"},{"kind":"expr","cat":"QC & fixes","id":"flag_negatives","title":"Flag negative pixels","desc":"Magenta wherever any channel is below 0.","params":[],"t":[["bad","r < 0 || g < 0 || b < 0"]],"plate":"sphere","view":"rgb","r":"bad ? 1 : r","g":"bad ? 0 : g","b":"bad ? 1 : b"},{"kind":"expr","cat":"QC & fixes","id":"flag_superwhite","title":"Flag superwhites","desc":"Orange wherever any channel is above 1.","params":[],"t":[["bad","r > 1 || g > 1 || b > 1"]],"plate":"sphere","view":"rgb","r":"bad ? 1 : r","g":"bad ? 0.4 : g","b":"bad ? 0 : b"},{"kind":"expr","cat":"QC & fixes","id":"flag_nan","title":"Flag NaN and inf","desc":"Cyan wherever a channel is NaN or infinite.","params":[],"t":[["bad","!(r == r && g == g && b == b) || abs(r) > 1e20 || abs(g) > 1e20 || abs(b) > 1e20"]],"plate":"sphere","view":"rgb","r":"bad ? 0 : r","g":"bad ? 1 : g","b":"bad ? 1 : b"},{"kind":"expr","cat":"QC & fixes","id":"zebras","title":"Zebra stripes","desc":"Moving black stripes over anything brighter than 1, like a camera's zebras.","params":[],"t":[["l","0.2126*r + 0.7152*g + 0.0722*b"],["zb","fmod(floor((x + y + frame*2)/8), 2)"]],"plate":"sphere","view":"rgb","c":"(l > 1 && zb) ? 0 : @"},{"kind":"expr","cat":"QC & fixes","id":"exposure_zones","title":"Exposure false colour","desc":"Stops from mid grey: green is 0.18, blue is under, red is over.","params":[],"t":[["l","0.2126*r + 0.7152*g + 0.0722*b"],["st","l > 0 ? log(l/0.18)/log(2) : -10"]],"plate":"sphere","view":"rgb","r":"clamp((st + 1)/3)","g":"clamp(1 - abs(st)/3)","b":"clamp((-st - 1)/3)"},{"kind":"expr","cat":"QC & fixes","id":"illegal_premult","title":"Flag rgb above alpha","desc":"Red where colour exceeds alpha: an unpremultiplied image, or a broken premult.","params":[],"t":[["bad","max(r, max(g, b)) > a + 0.001"]],"plate":"sphere","view":"rgb","r":"bad ? 1 : r*0.3","g":"bad ? 0 : g*0.3","b":"bad ? 0 : b*0.3"},{"kind":"expr","cat":"QC & fixes","id":"semi_transparent","title":"Show semi-transparent pixels","desc":"Yellow where alpha is between 0 and 1. Good for spotting dirty mattes.","params":[],"t":[["semi","a > 0.001 && a < 0.999"]],"plate":"sphere","view":"rgb","r":"semi ? 1 : r*0.4","g":"semi ? 0.9 : g*0.4","b":"semi ? 0 : b*0.4"},{"kind":"expr","cat":"QC & fixes","id":"nan_isnan","title":"NaN to zero (isnan)","desc":"The isnan() version from your setup. Covers NaN only; use Remove NaN and inf for infinities too.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"isnan(@) ? 0 : @","a":"isnan(a) ? 0 : a"},{"kind":"expr","cat":"QC & fixes","id":"nan_flag_red","title":"NaN flag (isnan)","desc":"Red where any channel is NaN, black elsewhere. Your Expression1 setup.","params":[],"t":[],"plate":"sphere","view":"rgb","r":"isnan(r) || isnan(g) || isnan(b) ? 1 : 0","g":"0","b":"0"},{"kind":"expr","cat":"QC & fixes","id":"colour_match_matte","title":"Matte by picked colour","desc":"Alpha where the pixel is within tolerance of a picked colour. Good for checking plate matches.","params":[{"n":"target","t":"color","v":[0.8,0.4,0.2],"l":"target"},{"n":"tolerance","t":"float","v":0.1,"lo":0,"hi":1,"l":"tolerance"}],"t":[],"plate":"sphere","view":"a","a":"sqrt(pow2(r - target.r) + pow2(g - target.g) + pow2(b - target.b)) < tolerance ? 1 : 0"},{"kind":"expr","cat":"CG & depth","id":"depth_normalise","title":"Normalise depth","desc":"Maps distance near→far to 0→1 for viewing. Needs a depth.Z channel in the input.","params":[{"n":"near","t":"float","v":1.0,"lo":0,"hi":3.0,"l":"near"},{"n":"far","t":"float","v":100.0,"lo":0,"hi":300.0,"l":"far"}],"t":[],"plate":"sphere","view":"rgb","c":"clamp((depth.Z - near)/(far - near))","a":"1"},{"kind":"expr","cat":"CG & depth","id":"depth_invert","title":"1/Z to distance","desc":"Nuke's ScanlineRender writes 1/Z. This turns it into real distance (and back again).","params":[],"t":[],"plate":"sphere","view":"rgb","note":"Previewed on a depth pass that already holds distance.","c":"depth.Z > 0 ? 1/depth.Z : 0","a":"1"},{"kind":"expr","cat":"CG & depth","id":"depth_fog","title":"Depth fog","desc":"Blends towards a fog colour between near and far.","params":[{"n":"near","t":"float","v":5.0,"lo":0,"hi":15.0,"l":"near"},{"n":"far","t":"float","v":60.0,"lo":0,"hi":180.0,"l":"far"}],"t":[["f","clamp((depth.Z - near)/(far - near))"]],"plate":"sphere","view":"rgb","r":"lerp(r, 0.55, f)","g":"lerp(g, 0.6, f)","b":"lerp(b, 0.7, f)"},{"kind":"expr","cat":"CG & depth","id":"depth_slice","title":"Depth slice matte","desc":"Selects a band w units wide around a distance. Handy for rack-focus mattes.","params":[{"n":"mid","t":"float","v":8.0,"lo":0,"hi":24.0,"l":"mid"},{"n":"thick","t":"float","v":2.0,"lo":0,"hi":6.0,"l":"line thickness"}],"t":[],"plate":"sphere","view":"a","a":"1 - smoothstep(0, thick, abs(depth.Z - mid))"},{"kind":"expr","cat":"CG & depth","id":"p_sphere","title":"Position pass sphere","desc":"Spherical matte around a world point (px, py, pz). Change P to your position layer's name.","params":[{"n":"px","t":"float","v":0.0,"lo":0,"hi":1,"l":"px"},{"n":"py","t":"float","v":0.0,"lo":0,"hi":1,"l":"py"},{"n":"pz","t":"float","v":0.0,"lo":0,"hi":1,"l":"pz"}],"t":[["d","sqrt(pow2(P.red - px) + pow2(P.green - py) + pow2(P.blue - pz))"]],"plate":"sphere","view":"a","a":"1 - smoothstep(0.6, 1.0, d)"},{"kind":"expr","cat":"CG & depth","id":"p_height","title":"Position pass height","desc":"Ground-up gradient in world Y, for height fog or dirt on the lower part of objects.","params":[{"n":"y0","t":"float","v":0.0,"lo":0,"hi":1,"l":"y0"},{"n":"y1","t":"float","v":1.0,"lo":0,"hi":3.0,"l":"y1"}],"t":[],"plate":"sphere","view":"a","a":"smoothstep(y0, y1, P.green)"},{"kind":"expr","cat":"CG & depth","id":"n_relight","title":"Normals relight","desc":"Brightens the side facing the light direction (lx, ly, lz). Use world-space normals.","params":[{"n":"lx","t":"float","v":-0.7,"lo":-2.0999999999999996,"hi":2.0999999999999996,"l":"lx"},{"n":"ly","t":"float","v":0.5,"lo":0,"hi":1.5,"l":"ly"},{"n":"lz","t":"float","v":0.5,"lo":0,"hi":1.5,"l":"lz"}],"t":[["ndl","max(0, (N.red*lx + N.green*ly + N.blue*lz)/sqrt(lx*lx + ly*ly + lz*lz))"]],"plate":"sphere","view":"rgb","c":"@*(0.5 + ndl)"},{"kind":"expr","cat":"CG & depth","id":"n_dot_l","title":"N·L light matte","desc":"The lit side of the normals as a matte, for grading key and fill separately.","params":[{"n":"lx","t":"float","v":-0.7,"lo":-2.0999999999999996,"hi":2.0999999999999996,"l":"lx"},{"n":"ly","t":"float","v":0.5,"lo":0,"hi":1.5,"l":"ly"},{"n":"lz","t":"float","v":0.5,"lo":0,"hi":1.5,"l":"lz"}],"t":[["ndl","max(0, (N.red*lx + N.green*ly + N.blue*lz)/sqrt(lx*lx + ly*ly + lz*lz))"]],"plate":"sphere","view":"a","a":"ndl"},{"kind":"expr","cat":"CG & depth","id":"n_view","title":"Normals to colour","desc":"Remaps -1–1 normals into a viewable 0–1 range.","params":[],"t":[],"plate":"sphere","view":"rgb","r":"N.red*0.5 + 0.5","g":"N.green*0.5 + 0.5","b":"N.blue*0.5 + 0.5","a":"1"},{"kind":"expr","cat":"CG & depth","id":"facing_ratio","title":"Facing ratio","desc":"1 facing camera, 0 at grazing angles. Needs camera-space normals. Invert it for a rim matte.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"abs(N.blue)","a":"1"},{"kind":"expr","cat":"CG & depth","id":"motion_magnitude","title":"Motion vector length","desc":"Speed in pixels per frame, divided by 20 for viewing. Rename forward to your vector layer.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"hypot(forward.u, forward.v)/20","a":"1"},{"kind":"expr","cat":"CG & depth","id":"barrel_stmap","title":"Barrel distortion STMap","desc":"An STMap with k1 distortion. Feed it into an STMap node. Negative k gives pincushion.","params":[{"n":"k1","t":"float","v":0.08,"lo":0,"hi":0.24,"l":"k1 (distortion)"}],"t":[["nx","(x+0.5)/width*2 - 1"],["ny","(y+0.5)/height*2 - 1"],["r2","nx*nx + ny*ny"]],"plate":"sphere","view":"stmap","r":"nx*(1 + k1*r2)*0.5 + 0.5","g":"ny*(1 + k1*r2)*0.5 + 0.5","b":"0","a":"1"},{"kind":"expr","cat":"Generators","id":"ramp_horizontal","title":"Horizontal ramp","desc":"0 on the left, 1 on the right. Pixel centres are at x+0.5.","params":[],"t":[],"plate":"black","view":"rgb","c":"(x+0.5)/width","a":"1"},{"kind":"expr","cat":"Generators","id":"ramp_vertical","title":"Vertical ramp","desc":"0 at the bottom, 1 at the top. Nuke's y axis points up.","params":[],"t":[],"plate":"black","view":"rgb","c":"(y+0.5)/height","a":"1"},{"kind":"expr","cat":"Generators","id":"ramp_radial","title":"Radial ramp","desc":"1 in the centre, falling to 0 at half the short side of the frame.","params":[],"t":[["cx","width/2"],["cy","height/2"],["d","hypot(x+0.5-cx, y+0.5-cy)"]],"plate":"black","view":"rgb","c":"clamp(1 - d/(min(width, height)/2))","a":"1"},{"kind":"expr","cat":"Generators","id":"soft_circle","title":"Soft circle","desc":"Solid inside 150 px, soft to 250 px. Change the two numbers in smoothstep for the size and softness.","params":[],"t":[["cx","width/2"],["cy","height/2"],["d","hypot(x+0.5-cx, y+0.5-cy)"]],"plate":"black","view":"rgb","c":"1 - smoothstep(150, 250, d)","a":"1 - smoothstep(150, 250, d)"},{"kind":"expr","cat":"Generators","id":"ring","title":"Ring","desc":"A 300 px radius ring with a 6 px soft edge on each side.","params":[],"t":[["cx","width/2"],["cy","height/2"],["d","hypot(x+0.5-cx, y+0.5-cy)"]],"plate":"black","view":"rgb","c":"1 - smoothstep(0, 6, abs(d - 300))","a":"1 - smoothstep(0, 6, abs(d - 300))"},{"kind":"expr","cat":"Generators","id":"diamond","title":"Diamond","desc":"Manhattan distance from the centre gives a diamond-shaped falloff.","params":[],"t":[["cx","width/2"],["cy","height/2"]],"plate":"black","view":"rgb","c":"clamp(1 - (abs(x+0.5-cx) + abs(y+0.5-cy))/400)","a":"1"},{"kind":"expr","cat":"Generators","id":"rectangle","title":"Rectangle matte","desc":"Hard box from (x0, y0) to (x1, y1) in pixels.","params":[{"n":"x0","t":"float","v":400.0,"lo":0,"hi":1200.0,"l":"x0"},{"n":"y0","t":"float","v":200.0,"lo":0,"hi":600.0,"l":"y0"},{"n":"x1","t":"float","v":1500.0,"lo":0,"hi":4500.0,"l":"x1"},{"n":"y1","t":"float","v":880.0,"lo":0,"hi":2640.0,"l":"y1"}],"t":[],"plate":"black","view":"rgb","c":"(x >= x0 && x < x1 && y >= y0 && y < y1) ? 1 : 0","a":"(x >= x0 && x < x1 && y >= y0 && y < y1) ? 1 : 0"},{"kind":"expr","cat":"Generators","id":"checkerboard","title":"Checkerboard","desc":"Squares of size pixels. Handy for checking distortion and tracking.","params":[{"n":"size","t":"int","v":64,"lo":1,"hi":256,"l":"size"}],"t":[],"plate":"black","view":"rgb","c":"fmod(floor(x/size) + floor(y/size), 2)","a":"1"},{"kind":"expr","cat":"Generators","id":"stripes","title":"Vertical stripes","desc":"Black and white bars, period pixels wide. Swap x for y for horizontal stripes.","params":[{"n":"period","t":"int","v":40,"lo":1,"hi":160,"l":"period"}],"t":[],"plate":"black","view":"rgb","c":"step(0.5, fmod(x/period, 1))","a":"1"},{"kind":"expr","cat":"Generators","id":"grid_lines","title":"Grid lines","desc":"Lines every cell pixels, w pixels thick.","params":[{"n":"cell","t":"int","v":100,"lo":1,"hi":400,"l":"cell"},{"n":"thick","t":"float","v":2.0,"lo":0,"hi":6.0,"l":"line thickness"}],"t":[],"plate":"black","view":"rgb","c":"(fmod(x, cell) < thick || fmod(y, cell) < thick) ? 1 : 0","a":"1"},{"kind":"expr","cat":"Generators","id":"polar_angle","title":"Polar angle","desc":"Angle around the centre as 0–1. Useful as a base for radial wipes and spirals.","params":[],"t":[["cx","width/2"],["cy","height/2"]],"plate":"black","view":"rgb","c":"(atan2(y+0.5-cy, x+0.5-cx) + pi)/(2*pi)","a":"1"},{"kind":"expr","cat":"Generators","id":"colour_wheel","title":"Colour wheel","desc":"Hue by angle, white in the centre, full colour at 400 px.","params":[],"t":[["cx","width/2"],["cy","height/2"],["ang","atan2(y+0.5-cy, x+0.5-cx)"],["d","clamp(hypot(x+0.5-cx, y+0.5-cy)/400)"]],"plate":"black","view":"rgb","r":"lerp(1, 0.5 + 0.5*cos(ang), d)","g":"lerp(1, 0.5 + 0.5*cos(ang - 2.0944), d)","b":"lerp(1, 0.5 + 0.5*cos(ang + 2.0944), d)","a":"1"},{"kind":"expr","cat":"Generators","id":"two_colour_gradient","title":"Two-colour gradient","desc":"Left-to-right blend between two RGB colours. Edit the lerp start and end values.","params":[],"t":[["scale","(x+0.5)/width"]],"plate":"black","view":"rgb","r":"lerp(0.02, 1.0, scale)","g":"lerp(0.06, 0.55, scale)","b":"lerp(0.25, 0.1, scale)","a":"1"},{"kind":"expr","cat":"Generators","id":"st_identity","title":"UV / STMap identity","desc":"Red = u, green = v. The neutral STMap: feed it through a distortion to bake a warp.","params":[],"t":[],"plate":"black","view":"stmap","r":"(x+0.5)/width","g":"(y+0.5)/height","b":"0","a":"1"},{"kind":"expr","cat":"Generators","id":"sine_pattern","title":"Sine interference","desc":"Soft repeating blobs. Change 0.05 to change the frequency.","params":[],"t":[],"plate":"black","view":"rgb","c":"sin(x*0.05)*sin(y*0.05)*0.5 + 0.5","a":"1"},{"kind":"expr","cat":"Generators","id":"noise_animated","title":"Animated noise","desc":"Smooth Perlin noise that drifts over time. s sets the scale.","params":[{"n":"scale","t":"float","v":0.01,"lo":0,"hi":0.03,"l":"scale"}],"t":[],"plate":"black","view":"rgb","c":"noise(x*scale, y*scale, frame*0.05)*0.5 + 0.5","a":"1"},{"kind":"expr","cat":"Generators","id":"fbm_clouds","title":"fBm clouds","desc":"Fractal noise: 6 octaves, lacunarity 2, gain 0.5. A good base for fog, dirt and breakup mattes.","params":[],"t":[],"plate":"black","view":"rgb","c":"fBm(x*0.004, y*0.004, frame*0.01, 6, 2, 0.5)*0.5 + 0.5","a":"1"},{"kind":"expr","cat":"Generators","id":"turbulence","title":"Turbulence","desc":"Like fBm but with sharper creases. Good for fire, smoke and marble.","params":[],"t":[],"plate":"black","view":"rgb","c":"turbulence(x*0.005, y*0.005, frame*0.02, 6, 2, 0.5)","a":"1"},{"kind":"expr","cat":"Generators","id":"tv_static","title":"TV static","desc":"New random value per pixel per frame.","params":[],"t":[],"plate":"black","view":"rgb","c":"random(x, y, frame)","a":"1"},{"kind":"expr","cat":"Generators","id":"colour_static","title":"Colour static","desc":"Independent random values per channel, using offset seeds.","params":[],"t":[],"plate":"black","view":"rgb","r":"random(x, y, frame)","g":"random(x, y, frame + 100)","b":"random(x, y, frame + 200)","a":"1"},{"kind":"expr","cat":"Generators","id":"marble","title":"Marble","desc":"Sine stripes bent by turbulence.","params":[{"n":"frequency","t":"float","v":0.02,"lo":0.001,"hi":0.2,"l":"frequency"},{"n":"distortion","t":"float","v":6,"lo":0,"hi":30,"l":"distortion"}],"t":[],"plate":"black","view":"rgb","c":"0.5 + 0.5*sin(x*frequency + turbulence(x*0.004, y*0.004, 0.5, 5, 2, 0.5)*distortion)","a":"1"},{"kind":"expr","cat":"Generators","id":"wood_rings","title":"Wood rings","desc":"Rings around a point with noisy wobble.","params":[{"n":"center","t":"xy","v":[0.3,0.4],"frac":true,"l":"center"},{"n":"ring","t":"float","v":40,"lo":2,"hi":400,"l":"ring"},{"n":"wobble","t":"float","v":30,"lo":0,"hi":200,"l":"wobble"}],"t":[],"plate":"black","view":"rgb","c":"fmod(hypot(x + 0.5 - center.x, y + 0.5 - center.y) + noise(x*0.003, y*0.003, 0)*wobble, ring)/ring","a":"1"},{"kind":"expr","cat":"Generators","id":"starfield","title":"Starfield","desc":"Random stars that twinkle over time.","params":[{"n":"density","t":"float","v":0.004,"lo":0,"hi":0.05,"l":"density"},{"n":"twinkle","t":"float","v":0.4,"lo":0,"hi":1,"l":"twinkle"}],"t":[],"plate":"black","view":"rgb","c":"random(x, y, 7) > 1 - density ? random(x, y, 9)*(1 - twinkle + twinkle*sin(frame*0.4 + random(x, y, 11)*6.283)) : 0","a":"1"},{"kind":"expr","cat":"Time & animation","id":"flicker","title":"Random flicker","desc":"New brightness every frame, ±10%.","params":[],"t":[["f","1 + (random(frame, 1, 1) - 0.5)*0.2"]],"plate":"sphere","view":"rgb","c":"@*f"},{"kind":"expr","cat":"Time & animation","id":"smooth_flicker","title":"Smooth flicker","desc":"Noise over time instead of random, so it wobbles like a flame or a bad bulb.","params":[],"t":[["f","1 + noise(frame*0.3, 0, 0)*0.15"]],"plate":"sphere","view":"rgb","c":"@*f"},{"kind":"expr","cat":"Time & animation","id":"pulse","title":"Pulse","desc":"Sine brightness cycle once per fps frames.","params":[{"n":"fps","t":"int","v":24,"lo":1,"hi":96,"l":"fps"}],"t":[["f","0.5 + 0.5*sin(frame*2*pi/fps)"]],"plate":"sphere","view":"rgb","c":"@*f"},{"kind":"expr","cat":"Time & animation","id":"strobe","title":"Strobe","desc":"Image on even frames, black on odd.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"fmod(frame, 2) < 1 ? @ : 0"},{"kind":"expr","cat":"Time & animation","id":"wipe_linear","title":"Linear wipe","desc":"Hard left-to-right alpha wipe over dur frames from start.","params":[{"n":"start","t":"int","v":1001,"lo":801,"hi":1201,"l":"start"},{"n":"dur","t":"int","v":24,"lo":1,"hi":96,"l":"dur"}],"t":[["p","clamp((frame - start)/dur)"]],"plate":"sphere","view":"a","a":"x + 0.5 < width*p ? 1 : 0"},{"kind":"expr","cat":"Time & animation","id":"wipe_soft","title":"Soft wipe","desc":"The same wipe with an 80 px soft edge.","params":[{"n":"start","t":"int","v":1001,"lo":801,"hi":1201,"l":"start"},{"n":"dur","t":"int","v":24,"lo":1,"hi":96,"l":"dur"}],"t":[["p","clamp((frame - start)/dur)"]],"plate":"sphere","view":"a","a":"1 - smoothstep(width*p - 80, width*p + 80, x + 0.5)"},{"kind":"expr","cat":"Time & animation","id":"wipe_iris","title":"Iris wipe","desc":"A circle that opens from the centre to the corners.","params":[{"n":"start","t":"int","v":1001,"lo":801,"hi":1201,"l":"start"},{"n":"dur","t":"int","v":24,"lo":1,"hi":96,"l":"dur"}],"t":[["p","clamp((frame - start)/dur)"]],"plate":"sphere","view":"a","a":"hypot(x+0.5 - width/2, y+0.5 - height/2) < p*hypot(width, height)/2 ? 1 : 0"},{"kind":"expr","cat":"Time & animation","id":"wipe_clock","title":"Clock wipe","desc":"Sweeps clockwise from 12 o'clock over 24 frames from 1001.","params":[{"n":"start","t":"int","v":1001,"lo":801,"hi":1201,"l":"start"},{"n":"dur","t":"int","v":24,"lo":1,"hi":96,"l":"dur"}],"t":[["dx","x + 0.5 - width/2"],["dy","y + 0.5 - height/2"]],"plate":"sphere","view":"a","a":"fmod(atan2(dx, dy) + 2*pi, 2*pi)/(2*pi) < clamp((frame - start)/dur) ? 1 : 0"},{"kind":"expr","cat":"Time & animation","id":"rolling_scanlines","title":"Rolling scanlines","desc":"Fine lines that roll upward over time.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"@*(0.92 + 0.08*sin((y + frame*4)*0.8))"},{"kind":"expr","cat":"Time & animation","id":"frame_colour","title":"Colour per frame","desc":"A flat random colour that changes every frame. Spots dropped or repeated frames at a glance.","params":[],"t":[],"plate":"sphere","view":"rgb","r":"random(frame, 1, 1)","g":"random(frame, 2, 2)","b":"random(frame, 3, 3)","a":"1"},{"kind":"expr","cat":"Time & animation","id":"scanning_bar","title":"Scanning bar","desc":"A white bar that crosses the frame at 40 px per frame. Shows playback speed and stutter.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"abs(x + 0.5 - fmod(frame*40, width)) < 20 ? 1 : @"},{"kind":"group","cat":"Look & overlays","id":"edge_detect","title":"Edge detect","desc":"Gradient magnitude of the image (Sobel-style). View the direction as colour, or lay the edges over the plate.","inputs":["img"],"params":[{"n":"source","t":"enum","items":["Luminance","Red","Green","Blue","Alpha","Max RGB"],"v":0,"l":"source"},{"n":"invert","t":"bool","v":0,"l":"invert"},{"n":"blur","t":"float","v":1,"lo":0,"hi":30,"l":"blur"},{"n":"spacing","t":"float","v":1,"lo":0.5,"hi":10,"l":"sample spacing"},{"n":"gain","t":"float","v":20,"lo":0,"hi":100,"l":"gain"},{"n":"view","t":"enum","items":["Magnitude","Direction as colour","Over plate"],"v":0,"l":"view"}],"nodes":[{"id":"H","class":"Expression","in":["img"],"t":[["l","parent.source == 0 ? 0.2126*r + 0.7152*g + 0.0722*b : parent.source == 1 ? r : parent.source == 2 ? g : parent.source == 3 ? b : parent.source == 4 ? a : max(r, max(g, b))"],["hgt","parent.invert ? 1 - l : l"]],"r":"hgt","g":"hgt","b":"hgt","a":"hgt"},{"id":"BL","class":"Blur","in":["H"],"knobs":{"channels":"rgba"},"expr":{"size":"parent.blur"}},{"id":"TxR","class":"Transform","in":["BL"],"knobs":{"filter":"Impulse"},"expr":{"translate":["-max(0.5, parent.spacing)","0"]}},{"id":"TxL","class":"Transform","in":["BL"],"knobs":{"filter":"Impulse"},"expr":{"translate":["max(0.5, parent.spacing)","0"]}},{"id":"TyU","class":"Transform","in":["BL"],"knobs":{"filter":"Impulse"},"expr":{"translate":["0","-max(0.5, parent.spacing)"]}},{"id":"TyD","class":"Transform","in":["BL"],"knobs":{"filter":"Impulse"},"expr":{"translate":["0","max(0.5, parent.spacing)"]}},{"id":"C1","class":"Copy","in":["TxR","TxL"],"knobs":{"from0":"rgba.red","to0":"rgba.green"}},{"id":"C2","class":"Copy","in":["C1","TyU"],"knobs":{"from0":"rgba.red","to0":"rgba.blue"}},{"id":"C3","class":"Copy","in":["C2","TyD"],"knobs":{"from0":"rgba.red","to0":"rgba.alpha"}},{"id":"CPE","class":"Copy","in":["img","C3"],"knobs":{"from0":"rgba.red","to0":"pgE.red","from1":"rgba.green","to1":"pgE.green","from2":"rgba.blue","to2":"pgE.blue","from3":"rgba.alpha","to3":"pgE.alpha"}},{"id":"OUT","class":"Expression","in":["CPE"],"t":[["gx","(pgE.red - pgE.green)/(2*max(0.5, parent.spacing))*parent.gain"],["gy","(pgE.blue - pgE.alpha)/(2*max(0.5, parent.spacing))*parent.gain"],["mag","hypot(gx, gy)"],["ang","atan2(gy, gx)"]],"r":"parent.view == 0 ? mag : parent.view == 1 ? mag*(0.5 + 0.5*cos(ang)) : max(r, mag)","g":"parent.view == 0 ? mag : parent.view == 1 ? mag*(0.5 + 0.5*cos(ang - 2.0944)) : max(g, mag)","b":"parent.view == 0 ? mag : parent.view == 1 ? mag*(0.5 + 0.5*cos(ang + 2.0944)) : max(b, mag)"},{"id":"RM","class":"Remove","in":["OUT"],"knobs":{"operation":"remove","channels":"pgE"}}],"output":"RM","layers":[["pgE",["pgE.red","pgE.green","pgE.blue","pgE.alpha"]]],"plate":{"img":"photo"},"view":"rgb"},{"kind":"expr","cat":"Look & overlays","id":"vignette","title":"Vignette","desc":"Aspect-correct darkening towards the corners. amt sets the strength.","params":[{"n":"amount","t":"float","v":0.5,"lo":0,"hi":1.5,"l":"amount"}],"t":[["nx","(x+0.5)/width*2 - 1"],["ny","((y+0.5)/height*2 - 1)*height/width"],["d","sqrt(nx*nx + ny*ny)"]],"plate":"sphere","view":"rgb","c":"@*(1 - amount*smoothstep(0.3, 1.2, d))"},{"kind":"expr","cat":"Look & overlays","id":"dither","title":"Dither for 8-bit","desc":"Adds ±half a code value of noise to break up banding before writing 8-bit files.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"@ + (random(x, y, frame) - 0.5)/255"},{"kind":"expr","cat":"Look & overlays","id":"quick_grain","title":"Quick mono grain","desc":"Grain that scales with brightness. A quick stand-in, not a match to a real stock.","params":[],"t":[["gr","(random(x, y, frame) - 0.5)*0.08"]],"plate":"sphere","view":"rgb","c":"@ + gr*sqrt(max(@, 0))"},{"kind":"expr","cat":"Look & overlays","id":"crt_lines","title":"CRT lines","desc":"Darkens every third row.","params":[],"t":[],"plate":"sphere","view":"rgb","c":"fmod(y, 3) < 1 ? @*0.6 : @"},{"kind":"expr","cat":"Look & overlays","id":"letterbox","title":"Letterbox","desc":"Black bars for any aspect ratio. ar 2.39 is scope.","params":[{"n":"aspect","t":"float","v":2.39,"lo":0,"hi":7.17,"l":"aspect"}],"t":[["bar","(height - width/aspect)/2"]],"plate":"sphere","view":"rgb","c":"(y < bar || y >= height - bar) ? 0 : @"},{"kind":"expr","cat":"Look & overlays","id":"thirds","title":"Rule of thirds","desc":"Thin white lines on the thirds, w pixels either side.","params":[{"n":"thick","t":"float","v":1.5,"lo":0,"hi":4.5,"l":"line thickness"}],"t":[],"plate":"sphere","view":"rgb","c":"(abs(x+0.5 - width/3) < thick || abs(x+0.5 - 2*width/3) < thick || abs(y+0.5 - height/3) < thick || abs(y+0.5 - 2*height/3) < thick) ? 1 : @"},{"kind":"expr","cat":"Look & overlays","id":"safe_area","title":"Safe area box","desc":"A box inset by m of the frame on each side (0.05 = 90% action safe, 0.1 = title safe).","params":[{"n":"margin","t":"float","v":0.05,"lo":0,"hi":0.15000000000000002,"l":"margin"},{"n":"thick","t":"float","v":1.5,"lo":0,"hi":4.5,"l":"line thickness"}],"t":[["l","width*margin"],["bt","height*margin"]],"plate":"sphere","view":"rgb","c":"(((abs(x+0.5 - l) < thick || abs(x+0.5 - (width - l)) < thick) && y >= bt && y <= height - bt) || ((abs(y+0.5 - bt) < thick || abs(y+0.5 - (height - bt)) < thick) && x >= l && x <= width - l)) ? 1 : @"},{"kind":"expr","cat":"Look & overlays","id":"centre_cross","title":"Centre cross","desc":"A small crosshair at the frame centre.","params":[],"t":[["cx","width/2"],["cy","height/2"]],"plate":"sphere","view":"rgb","c":"((abs(x+0.5 - cx) < 1.5 && abs(y+0.5 - cy) < 30) || (abs(y+0.5 - cy) < 1.5 && abs(x+0.5 - cx) < 30)) ? 1 : @"},{"kind":"expr","cat":"Look & overlays","id":"halftone","title":"Halftone dots","desc":"Turns the image into rotated print dots sized by luminance.","params":[{"n":"cell","t":"float","v":14,"lo":3,"hi":80,"l":"cell"},{"n":"angle","t":"float","v":45,"lo":-90,"hi":90,"l":"angle"}],"t":[["ru","(x*cos(angle*pi/180) + y*sin(angle*pi/180))/cell"],["rv","(-x*sin(angle*pi/180) + y*cos(angle*pi/180))/cell"],["dd","hypot(ru - floor(ru) - 0.5, rv - floor(rv) - 0.5)"],["l","clamp(0.2126*r + 0.7152*g + 0.0722*b)"]],"plate":"photo","view":"rgb","c":"dd < sqrt(l)*0.7 ? 1 : 0"}]''')


# ---------------------------------------------------------------- recipe helpers
def channel_exprs(rec):
    """Per-channel expressions. 'c' is shorthand for r/g/b with @ standing for the channel.
    None means the channel is left unchanged."""
    out = {}
    for c in CHANNELS:
        if c in rec:
            out[c] = rec[c]
        elif "c" in rec and c != "a":
            out[c] = rec["c"].replace("@", c)
        else:
            out[c] = None
    return out


def load_user_recipes():
    try:
        with open(USER_FILE) as fh:
            data = json.load(fh)
        return [r for r in data if isinstance(r, dict) and r.get("id")]
    except (IOError, OSError, ValueError):
        return []


def save_user_recipes(recipes):
    folder = os.path.dirname(USER_FILE)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    tmp = USER_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(recipes, fh, indent=1)
    os.replace(tmp, USER_FILE)


def all_recipes():
    return CATALOG + load_user_recipes()


def find_recipe(recipe_id):
    for rec in all_recipes():
        if rec["id"] == recipe_id:
            return rec
    raise KeyError("No expression recipe called %r" % recipe_id)


def default_values(rec):
    return dict((p["n"], p["v"]) for p in rec.get("params", []) if "n" in p)


# ---------------------------------------------------------------- node building
class _Undo(object):
    def __init__(self, name):
        self.name = name
        self.undo = None

    def __enter__(self):
        try:
            self.undo = nuke.Undo()
            self.undo.begin(self.name)
        except Exception:
            self.undo = None
        return self

    def __exit__(self, *exc):
        if self.undo is not None:
            try:
                self.undo.end()
            except Exception:
                pass
        return False


def _format_size():
    try:
        f = nuke.root().format()
        return float(f.width()), float(f.height())
    except Exception:
        return 1920.0, 1080.0


def _slug(text):
    return re.sub(r"[^A-Za-z0-9_]+", "_", text).strip("_") or "x"


def _make_knob(p):
    t, n, label = p["t"], p["n"], p.get("l", p["n"])
    if t == "float":
        k = nuke.Double_Knob(n, label)
        k.setRange(float(p.get("lo", 0)), float(p.get("hi", 1)))
    elif t == "int":
        k = nuke.Int_Knob(n, label)
    elif t == "bool":
        k = nuke.Boolean_Knob(n, label)
        k.setFlag(nuke.STARTLINE)
    elif t == "enum":
        k = nuke.Enumeration_Knob(n, label, list(p["items"]))
    elif t == "color":
        k = nuke.Color_Knob(n, label)
    elif t == "xy":
        k = nuke.XY_Knob(n, label)
    elif t == "xyz":
        k = nuke.XYZ_Knob(n, label)
    else:
        raise ValueError("Unknown knob type %r" % t)
    if p.get("tip"):
        k.setTooltip(p["tip"])
    return k


def _set_knob_value(k, p, value):
    t = p["t"]
    if t == "float":
        k.setValue(float(value))
    elif t == "int":
        k.setValue(int(value))
    elif t == "bool":
        k.setValue(bool(value))
    elif t == "enum":
        k.setValue(int(value))
    elif t in ("color", "xyz"):
        for i, v in enumerate(value[:3]):
            k.setValue(float(v), i)
    elif t == "xy":
        w, h = _format_size() if p.get("frac") else (1.0, 1.0)
        k.setValue(float(value[0]) * w, 0)
        k.setValue(float(value[1]) * h, 1)


def _add_params(node, rec, values, tab_label):
    params = rec.get("params", [])
    if not params or "tab" not in params[0]:
        node.addKnob(nuke.Tab_Knob("sleepy_params", tab_label))
    info = nuke.Text_Knob("sleepy_info", "", textwrap.fill(rec.get("desc", ""), 72))
    node.addKnob(info)
    rid = nuke.String_Knob("sleepy_recipe", "recipe")
    node.addKnob(rid)
    rid.setValue(rec["id"])
    rid.setFlag(nuke.INVISIBLE)
    for p in params:
        if "tab" in p:
            node.addKnob(nuke.Tab_Knob("sleepy_tab_" + _slug(p["tab"]).lower(), p["tab"]))
            continue
        k = _make_knob(p)
        node.addKnob(k)
        _set_knob_value(k, p, values.get(p["n"], p["v"]))


def _fill_expression(node, spec):
    for i in range(4):
        node["temp_name%d" % i].setValue("")
        node["temp_expr%d" % i].setValue("")
    for i, (name, expr) in enumerate(spec.get("t", [])[:4]):
        node["temp_name%d" % i].setValue(name)
        node["temp_expr%d" % i].setValue(expr)
    exprs = channel_exprs(spec)
    for i, c in enumerate(CHANNELS):
        if exprs[c] is not None:
            node["expr%d" % i].setValue(exprs[c])
    for i, script in enumerate(spec.get("channels") or []):
        if script:
            try:
                node["channel%d" % i].fromScript(script)
            except Exception:
                pass


def _safe_name(node, name):
    try:
        node.setName(name, uncollide=True)
    except Exception:
        pass


def _selected():
    try:
        return nuke.selectedNode()
    except ValueError:
        return None


def create_expression(rec, values=None, open_panel=False):
    values = values or {}
    with _Undo("Sleepy Expressions: " + rec["title"]):
        node = nuke.createNode("Expression", inpanel=False)
        _fill_expression(node, rec)
        if rec.get("params"):
            _add_params(node, rec, values, "Params")
        _safe_name(node, "SleepyX_" + _slug(rec["id"]))
        node["label"].setValue(rec["title"])
    if open_panel:
        node.showControlPanel()
    return node


def _make_internal(spec):
    cls = spec["class"]
    maker = getattr(nuke.nodes, cls, None)
    if maker is None:
        raise RuntimeError("This Nuke has no %s node" % cls)
    node = maker()
    if cls == "Expression":
        _fill_expression(node, spec)
    knobs = node.knobs()
    for name, value in spec.get("knobs", {}).items():
        if name in knobs:
            node[name].setValue(value)
    for name, expr in spec.get("expr", {}).items():
        if name not in knobs:
            continue
        if isinstance(expr, list):
            for i, e in enumerate(expr):
                node[name].setExpression(e, i)
        else:
            node[name].setExpression(expr)
    _safe_name(node, spec["id"])
    return node


def _layout(nodes_in_order, inputs_of):
    depth, col_used = {}, {}
    for name, node in nodes_in_order:
        srcs = [s for s in inputs_of.get(name, []) if s in depth]
        d = (max(depth[s] for s in srcs) + 1) if srcs else 0
        depth[name] = d
        col = col_used.get(d, 0)
        col_used[d] = col + 1
        node.setXYpos(col * 140, d * 90)


def create_group(rec, values=None, open_panel=False):
    values = values or {}
    sel = _selected()
    with _Undo("Sleepy Expressions: " + rec["title"]):
        for name, chans in rec.get("layers", []):
            try:
                nuke.Layer(name, list(chans))
            except Exception:
                pass
        group = nuke.nodes.Group()
        _add_params(group, rec, values, rec["title"])
        group.begin()
        try:
            made, inputs_of, order = {}, {}, []
            for i, name in enumerate(rec["inputs"]):
                inp = nuke.nodes.Input()
                _safe_name(inp, name)
                if "number" in inp.knobs():
                    inp["number"].setValue(i)
                made[name] = inp
                order.append((name, inp))
            for spec in rec["nodes"]:
                node = _make_internal(spec)
                for i, src in enumerate(spec.get("in", [])):
                    if src:
                        node.setInput(i, made[src])
                made[spec["id"]] = node
                inputs_of[spec["id"]] = [s for s in spec.get("in", []) if s]
                order.append((spec["id"], node))
            out = nuke.nodes.Output()
            out.setInput(0, made[rec["output"]])
            inputs_of["Output"] = [rec["output"]]
            order.append(("Output", out))
            _layout(order, inputs_of)
        finally:
            group.end()
        _safe_name(group, "Sleepy_" + _slug(rec["title"]).replace("__", "_"))
        if sel is not None:
            group.setInput(0, sel)
            group.setXYpos(sel.xpos(), sel.ypos() + 110)
        else:
            try:
                group.autoplace()
            except Exception:
                pass
        for n in nuke.selectedNodes():
            n.setSelected(False)
        group.setSelected(True)
    if open_panel:
        group.showControlPanel()
    return group


def create(recipe, values=None, open_panel=False):
    """Create a recipe by id (or recipe dict). values overrides the default knob values."""
    rec = find_recipe(recipe) if isinstance(recipe, str) else recipe
    if rec.get("kind") == "group":
        return create_group(rec, values, open_panel)
    return create_expression(rec, values, open_panel)


# ---------------------------------------------------------------- saving your own
_default_expression_knobs = None


def _expression_default_knobs():
    global _default_expression_knobs
    if _default_expression_knobs is None:
        tmp = nuke.nodes.Expression()
        try:
            _default_expression_knobs = set(tmp.knobs().keys())
        finally:
            nuke.delete(tmp)
    return _default_expression_knobs


def recipe_from_node(node, title, desc=""):
    """Build a user recipe from an Expression node: temp variables, channel expressions,
    channel routing and any user knobs (float, int, bool, menu, colour, XY, XYZ)."""
    if node.Class() != "Expression":
        raise ValueError("Select an Expression node (selected: %s)." % node.Class())
    rec = {"kind": "expr", "cat": USER_CAT, "id": "user_" + _slug(title).lower(), "title": title,
           "desc": desc or "Saved from %s." % node.name(), "params": [], "t": [], "plate": "sphere", "view": "rgb"}
    for i in range(4):
        name, expr = node["temp_name%d" % i].value().strip(), node["temp_expr%d" % i].value().strip()
        if name:
            rec["t"].append([name, expr])
    for i, c in enumerate(CHANNELS):
        expr = node["expr%d" % i].value().strip()
        if expr:
            rec[c] = expr
    rec["channels"] = [node["channel%d" % i].toScript() for i in range(4) if "channel%d" % i in node.knobs()]
    defaults = _expression_default_knobs()
    for name, k in node.knobs().items():
        if name in defaults or name.startswith("sleepy_"):
            continue
        cls, label = k.Class(), (k.label() or name)
        try:
            if cls == "Double_Knob":
                v = float(k.value())
                rec["params"].append({"n": name, "t": "float", "v": v, "lo": min(0.0, v * 3), "hi": max(1.0, abs(v) * 3), "l": label})
            elif cls == "Int_Knob":
                rec["params"].append({"n": name, "t": "int", "v": int(k.value()), "l": label})
            elif cls == "Boolean_Knob":
                rec["params"].append({"n": name, "t": "bool", "v": int(k.value()), "l": label})
            elif cls == "Enumeration_Knob":
                rec["params"].append({"n": name, "t": "enum", "items": list(k.values()), "v": int(k.getValue()), "l": label})
            elif cls in ("Color_Knob", "AColor_Knob"):
                v = [k.value(i) for i in range(3)]
                rec["params"].append({"n": name, "t": "color", "v": v, "l": label})
            elif cls == "XY_Knob":
                rec["params"].append({"n": name, "t": "xy", "v": [k.value(0), k.value(1)], "frac": False, "l": label})
            elif cls == "XYZ_Knob":
                rec["params"].append({"n": name, "t": "xyz", "v": [k.value(i) for i in range(3)], "l": label})
        except Exception:
            continue
    return rec


def save_selected(title, desc=""):
    node = _selected()
    if node is None:
        raise ValueError("Select an Expression node first.")
    rec = recipe_from_node(node, title, desc)
    recipes = [r for r in load_user_recipes() if r["id"] != rec["id"]]
    recipes.append(rec)
    save_user_recipes(recipes)
    return rec


def delete_user_recipe(recipe_id):
    save_user_recipes([r for r in load_user_recipes() if r["id"] != recipe_id])


# ---------------------------------------------------------------- panel
_MONO = QtGui.QFont("Consolas" if os.name == "nt" else "Menlo")
_MONO.setStyleHint(QtGui.QFont.Monospace)
_instance = None


def recipe_text(rec):
    """Readable listing of what a recipe creates."""
    lines = []
    if rec.get("kind") == "group":
        lines.append("Group  ·  inputs: " + ", ".join(rec["inputs"]))
        lines.append("")
        for spec in rec["nodes"]:
            if spec["class"] != "Expression":
                extra = ", ".join("%s=%s" % kv for kv in list(spec.get("knobs", {}).items()) + list(spec.get("expr", {}).items()))
                lines.append("%-5s %s  %s" % (spec["id"], spec["class"], extra))
                continue
            lines.append("%-5s Expression" % spec["id"])
            for name, expr in spec.get("t", []):
                lines.append("      %s = %s" % (name, expr))
            exprs = channel_exprs(spec)
            for c in CHANNELS:
                if exprs[c] is not None:
                    lines.append("      %-5s = %s" % (CHANNEL_LABELS[c], exprs[c]))
        return "\n".join(lines)
    for name, expr in rec.get("t", []):
        lines.append("%s = %s" % (name, expr))
    if lines:
        lines.append("")
    exprs = channel_exprs(rec)
    for c in CHANNELS:
        lines.append("%-5s = %s" % (CHANNEL_LABELS[c], exprs[c] if exprs[c] is not None else "(unchanged)"))
    return "\n".join(lines)


class _ColorField(QtWidgets.QWidget):
    def __init__(self, value, parent=None):
        super(_ColorField, self).__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.spins = []
        for v in value:
            s = QtWidgets.QDoubleSpinBox()
            s.setRange(-1e6, 1e6)
            s.setDecimals(3)
            s.setSingleStep(0.05)
            s.setValue(v)
            s.valueChanged.connect(self._update_swatch)
            lay.addWidget(s)
            self.spins.append(s)
        self.swatch = QtWidgets.QPushButton()
        self.swatch.setFixedWidth(28)
        self.swatch.setToolTip("Pick a colour")
        self.swatch.clicked.connect(self._pick)
        lay.addWidget(self.swatch)
        self._update_swatch()

    def value(self):
        return [s.value() for s in self.spins]

    def _update_swatch(self, *args):
        c = [max(0, min(255, int(round((max(v, 0) ** (1 / 2.2)) * 255)))) for v in self.value()]
        self.swatch.setStyleSheet("background-color: rgb(%d,%d,%d); border: 1px solid #555;" % tuple(c))

    def _pick(self):
        c = [max(0, min(255, int(round((max(v, 0) ** (1 / 2.2)) * 255)))) for v in self.value()]
        col = QtWidgets.QColorDialog.getColor(QtGui.QColor(*c), self, "Pick colour")
        if col.isValid():
            for s, v in zip(self.spins, (col.redF(), col.greenF(), col.blueF())):
                s.setValue(round(v ** 2.2, 4))


class _VecField(QtWidgets.QWidget):
    def __init__(self, value, decimals=3, parent=None):
        super(_VecField, self).__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.spins = []
        for v in value:
            s = QtWidgets.QDoubleSpinBox()
            s.setRange(-1e7, 1e7)
            s.setDecimals(decimals)
            s.setSingleStep(0.05)
            s.setValue(v)
            lay.addWidget(s)
            self.spins.append(s)

    def value(self):
        return [s.value() for s in self.spins]


class ExpressionLabPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(ExpressionLabPanel, self).__init__(parent)
        global _instance
        _instance = self
        self.current = None
        self.fields = {}
        self._build_ui()
        self.reload()

    # ---- UI
    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        top = QtWidgets.QHBoxLayout()
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search: normal, relight, despill, wipe, stmap…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._create_current)
        top.addWidget(self.search, 1)
        self.count = QtWidgets.QLabel()
        top.addWidget(self.count)
        root.addLayout(top)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        root.addWidget(split, 1)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(220)
        self.tree.currentItemChanged.connect(self._on_select)
        self.tree.itemDoubleClicked.connect(lambda item, col: item.parent() is not None and self._create_current())
        split.addWidget(self.tree)

        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        self.title = QtWidgets.QLabel()
        f = self.title.font()
        f.setPointSize(f.pointSize() + 4)
        f.setBold(True)
        self.title.setFont(f)
        self.title.setWordWrap(True)
        rl.addWidget(self.title)
        self.meta = QtWidgets.QLabel()
        self.meta.setStyleSheet("color: #a0a0a0;")
        rl.addWidget(self.meta)
        self.desc = QtWidgets.QLabel()
        self.desc.setWordWrap(True)
        self.desc.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        rl.addWidget(self.desc)

        self.param_box = QtWidgets.QGroupBox("Starting values (become knobs on the node)")
        self.param_form = QtWidgets.QFormLayout(self.param_box)
        self.param_form.setLabelAlignment(QtCore.Qt.AlignRight)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(self.param_box)
        rl.addWidget(scroll, 2)

        self.code = QtWidgets.QPlainTextEdit()
        self.code.setReadOnly(True)
        self.code.setFont(_MONO)
        self.code.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        rl.addWidget(self.code, 2)

        row = QtWidgets.QHBoxLayout()
        self.btn_create = QtWidgets.QPushButton("Create node")
        self.btn_create.setDefault(True)
        self.btn_create.setStyleSheet("QPushButton { font-weight: bold; padding: 5px 14px; }")
        self.btn_create.clicked.connect(self._create_current)
        row.addWidget(self.btn_create)
        self.chk_open = QtWidgets.QCheckBox("Open properties")
        self.chk_open.setChecked(True)
        row.addWidget(self.chk_open)
        row.addStretch(1)
        self.btn_reset = QtWidgets.QPushButton("Reset values")
        self.btn_reset.clicked.connect(lambda: self._show(self.current))
        row.addWidget(self.btn_reset)
        self.btn_copy = QtWidgets.QPushButton("Copy text")
        self.btn_copy.setToolTip("Copy the expressions to the clipboard")
        self.btn_copy.clicked.connect(self._copy_text)
        row.addWidget(self.btn_copy)
        rl.addLayout(row)

        row2 = QtWidgets.QHBoxLayout()
        self.btn_save = QtWidgets.QPushButton("Save selected Expression node…")
        self.btn_save.setToolTip("Adds the selected Expression node, with its knobs, to My expressions")
        self.btn_save.clicked.connect(self._save_selected)
        row2.addWidget(self.btn_save)
        self.btn_delete = QtWidgets.QPushButton("Delete from My expressions")
        self.btn_delete.clicked.connect(self._delete_current)
        row2.addWidget(self.btn_delete)
        row2.addStretch(1)
        rl.addLayout(row2)

        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)

    # ---- data
    def reload(self, select_id=None):
        self.recipes = all_recipes()
        self.tree.clear()
        cats = {}
        for rec in self.recipes:
            cat = rec.get("cat", USER_CAT)
            if cat not in cats:
                item = QtWidgets.QTreeWidgetItem([cat])
                f = item.font(0)
                f.setBold(True)
                item.setFont(0, f)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsSelectable)
                self.tree.addTopLevelItem(item)
                cats[cat] = item
            label = rec["title"] + ("   [group]" if rec.get("kind") == "group" else "")
            child = QtWidgets.QTreeWidgetItem([label])
            child.setData(0, QtCore.Qt.UserRole, rec["id"])
            child.setToolTip(0, rec.get("desc", ""))
            child.setData(0, QtCore.Qt.UserRole + 1, " ".join([rec["title"], rec.get("desc", ""), rec["id"], cat, json.dumps(rec)]).lower())
            cats[cat].addChild(child)
        self._filter(self.search.text())
        target = select_id
        if target is None and self.current is not None:
            target = self.current["id"]
        if not self._select_id(target):
            first = self._first_visible()
            if first is not None:
                self.tree.setCurrentItem(first)

    def _iter_children(self):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                yield top, top.child(j)

    def _first_visible(self):
        for top, child in self._iter_children():
            if not child.isHidden():
                return child
        return None

    def _select_id(self, rid):
        if not rid:
            return False
        for top, child in self._iter_children():
            if child.data(0, QtCore.Qt.UserRole) == rid and not child.isHidden():
                self.tree.setCurrentItem(child)
                return True
        return False

    def _filter(self, text):
        words = text.lower().split()
        shown = 0
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            n = 0
            for j in range(top.childCount()):
                child = top.child(j)
                hay = child.data(0, QtCore.Qt.UserRole + 1) or ""
                ok = all(w in hay for w in words)
                child.setHidden(not ok)
                n += ok
            top.setHidden(n == 0)
            top.setText(0, "%s  (%d)" % (top.text(0).split("  (")[0], n))
            top.setExpanded(bool(words) or top.isExpanded())
            shown += n
        self.count.setText("%d" % shown)
        cur = self.tree.currentItem()
        if words and (cur is None or cur.isHidden() or cur.parent() is None):
            first = self._first_visible()
            if first is not None:
                self.tree.setCurrentItem(first)

    def _on_select(self, item, prev=None):
        if item is None or item.parent() is None:
            return
        rid = item.data(0, QtCore.Qt.UserRole)
        for rec in self.recipes:
            if rec["id"] == rid:
                self._show(rec)
                return

    def _clear_form(self):
        while self.param_form.rowCount():
            self.param_form.removeRow(0)
        self.fields = {}

    def _show(self, rec):
        if rec is None:
            return
        self.current = rec
        self.title.setText(rec["title"])
        if rec.get("kind") == "group":
            kind = "Group of %d nodes  ·  inputs: %s" % (len(rec["nodes"]), ", ".join(rec["inputs"]))
        else:
            kind = "Expression node"
        self.meta.setText("%s  ·  %s" % (rec.get("cat", USER_CAT), kind))
        desc = rec.get("desc", "")
        if rec.get("note"):
            desc += "\n\n" + rec["note"]
        self.desc.setText(desc)
        self._clear_form()
        params = rec.get("params", [])
        for p in params:
            if "tab" in p:
                lab = QtWidgets.QLabel("<b>%s</b>" % p["tab"])
                self.param_form.addRow(lab)
                continue
            w = self._make_field(p)
            self.fields[p["n"]] = (p, w)
            label = p.get("l", p["n"])
            if p["t"] == "xy" and p.get("frac"):
                label += " (0–1 of format)"
            self.param_form.addRow(label, w)
        if not params:
            self.param_form.addRow(QtWidgets.QLabel("No knobs: this one is just expressions."))
        self.code.setPlainText(recipe_text(rec))
        self.btn_delete.setEnabled(rec.get("cat") == USER_CAT)

    def _make_field(self, p):
        t, v = p["t"], p["v"]
        if t == "float":
            w = QtWidgets.QDoubleSpinBox()
            w.setRange(-1e7, 1e7)
            w.setDecimals(4)
            span = float(p.get("hi", 1)) - float(p.get("lo", 0))
            w.setSingleStep(max(1e-4, span / 100.0))
            w.setValue(float(v))
            w.setToolTip("Slider range on the node: %g to %g" % (p.get("lo", 0), p.get("hi", 1)))
        elif t == "int":
            w = QtWidgets.QSpinBox()
            w.setRange(-10 ** 7, 10 ** 7)
            w.setValue(int(v))
        elif t == "bool":
            w = QtWidgets.QCheckBox()
            w.setChecked(bool(v))
        elif t == "enum":
            w = QtWidgets.QComboBox()
            w.addItems(p["items"])
            w.setCurrentIndex(int(v))
        elif t == "color":
            w = _ColorField(list(v))
        elif t == "xy":
            w = _VecField(list(v), 3)
        elif t == "xyz":
            w = _VecField(list(v), 3)
        else:
            w = QtWidgets.QLabel(str(v))
        return w

    def values(self):
        out = {}
        for name, (p, w) in self.fields.items():
            t = p["t"]
            if t in ("float", "int"):
                out[name] = w.value()
            elif t == "bool":
                out[name] = int(w.isChecked())
            elif t == "enum":
                out[name] = w.currentIndex()
            elif t in ("color", "xy", "xyz"):
                out[name] = w.value()
        return out

    # ---- actions
    def _create_current(self):
        if self.current is None:
            return
        try:
            create(self.current, self.values(), self.chk_open.isChecked())
        except Exception as exc:
            nuke.message("Couldn't create %s:\n%s" % (self.current["title"], exc))

    def _copy_text(self):
        if self.current is not None:
            QtWidgets.QApplication.clipboard().setText(recipe_text(self.current))

    def _save_selected(self):
        node = _selected()
        if node is None or node.Class() != "Expression":
            nuke.message("Select an Expression node to save it to My expressions.")
            return
        title, ok = QtWidgets.QInputDialog.getText(self, "Save to My expressions", "Name:", text=node.name())
        if not ok or not title.strip():
            return
        desc, ok = QtWidgets.QInputDialog.getText(self, "Save to My expressions", "What does it do? (optional)")
        try:
            rec = save_selected(title.strip(), desc.strip() if ok else "")
        except Exception as exc:
            nuke.message("Couldn't save: %s" % exc)
            return
        self.search.clear()
        self.reload(select_id=rec["id"])

    def _delete_current(self):
        rec = self.current
        if rec is None or rec.get("cat") != USER_CAT:
            return
        if nuke.ask("Delete '%s' from My expressions?" % rec["title"]):
            delete_user_recipe(rec["id"])
            self.current = None
            self.reload()

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()


# ---------------------------------------------------------------- install
_installed = False


def show():
    """Open the panel docked next to Properties, or raise it if it's already open."""
    if _instance is not None:
        try:
            if _instance.isVisible():
                _instance.raise_()
                _instance.activateWindow()
                _instance.focus_search()
                return _instance
        except RuntimeError:  # the Qt object was deleted with its pane
            pass
    if _nkpanels is None:
        raise RuntimeError("Sleepy Expressions needs Nuke's GUI.")
    panel = _nkpanels.registerWidgetAsPanel("sleepy_expressions.ExpressionLabPanel", PANEL_TITLE, PANEL_ID, True)
    pane = nuke.getPaneFor("Properties.1") or nuke.getPaneFor("DAG.1")
    if pane is not None:
        panel.addToPane(pane)
    else:
        panel.addToPane()
    return panel


def install(toolbar_menu="SleepyTools", shortcut=""):
    """Register the panel and menus. Safe to call again; survives module reloads."""
    global _installed
    if _installed:
        return
    if getattr(nuke, "_sleepy_expression_lab_installed", False):
        _installed = True           # installed by an earlier copy of this module
        return
    if _nkpanels is not None:
        _nkpanels.registerWidgetAsPanel("sleepy_expressions.ExpressionLabPanel", PANEL_TITLE, PANEL_ID)
    # Top menu bar: SleepyTools > Expression Lab and SleepyTools > Expressions > ...
    # Node toolbar / Tab menu: SleepyTools > Expressions > ... (so Tab search finds every recipe)
    for bar in (nuke.menu("Nuke"), nuke.menu("Nodes")):
        menu = bar.addMenu(toolbar_menu)
        menu.addCommand("Expression Lab", "sleepy_expressions.show()", shortcut)
        exprs = menu.addMenu("Expressions")
        for rec in CATALOG:
            label = rec["title"].replace("/", "-").replace("\\", "-")
            cat = rec["cat"].replace("/", "-")
            exprs.addCommand("%s/%s" % (cat, label), "sleepy_expressions.create(%r)" % rec["id"])
        shortcut = ""  # only register the shortcut once
    nuke._sleepy_expression_lab_installed = True
    _installed = True
