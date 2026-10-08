"""Sleepy Blink for Nuke.

A dockable panel with a library of BlinkScript kernels: normals from images, depth AO,
bilateral/median/Kuwahara filters, bokeh, zoom and directional blur, chromatic aberration,
edge extend, outlines, round erode/dilate, firefly and NaN fixing. BlinkScript can read
neighbouring pixels, which plain Expression nodes can't.

Pick a kernel, set its starting values and press Create: you get a BlinkScript node with the
kernel compiled and the values set, connected to the selected node.

Install: put the SleepyBlink folder in ~/.nuke and add to ~/.nuke/init.py:
    nuke.pluginAddPath('./SleepyBlink')
"""
import json
import os
import re

import nuke

try:
    from nukescripts import panels as _nkpanels
except ImportError:
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
PANEL_ID = "uk.co.pg.BlinkScriptLab"
PANEL_TITLE = "Sleepy Blink"
USER_FILE = os.path.join(os.path.expanduser("~"), ".nuke", "sleepy_blinkscript_lab_user.json")
USER_CAT = "My kernels"

KERNELS = json.loads(r'''[{"id":"SleepySobelNormals","kernel":"SleepySobelNormals","cat":"Normals & surface","title":"Normal map from image (Sobel)","desc":"True 3\u00d73 Sobel normal map in one node: brightness (or any channel) as height. Cleaner than the Expression Lab group and faster.","params":[{"n":"strength","t":"float","v":20.0,"lo":0,"hi":200,"l":"strength"},{"n":"spacing","t":"int","v":1,"lo":1,"hi":10,"l":"spacing"},{"n":"source","t":"enum","v":0,"items":["Luminance","Red","Green","Blue","Alpha"],"l":"source"},{"n":"invert","t":"bool","v":0,"l":"invert"},{"n":"flipGreen","t":"bool","v":0,"l":"flip green (DirectX)"},{"n":"encode","t":"bool","v":1,"l":"encode 0\u20131"}],"source":"kernel SleepySobelNormals : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRanged2D, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  float strength;\n  int spacing;\n  int source;\n  bool invert;\n  bool flipGreen;\n  bool encode;\n\nlocal:\n  int s;\n\n  void define() {\n    defineParam(strength, \"strength\", 20.0f);\n    defineParam(spacing, \"spacing\", 1);\n    defineParam(source, \"source\", 0);\n    defineParam(invert, \"invert\", false);\n    defineParam(flipGreen, \"flipGreen\", false);\n    defineParam(encode, \"encode\", true);\n  }\n\n  void init() {\n    s = max(1, spacing);\n    src.setRange(-s, -s, s, s);\n  }\n\n  // height at a neighbour: 0 luminance, 1 red, 2 green, 3 blue, 4 alpha\n  float h(int dx, int dy) {\n    SampleType(src) p = src(dx * s, dy * s);\n    float v = 0.2126f * p.x + 0.7152f * p.y + 0.0722f * p.z;\n    if (source == 1) v = p.x;\n    if (source == 2) v = p.y;\n    if (source == 3) v = p.z;\n    if (source == 4) v = p.w;\n    return invert ? 1.0f - v : v;\n  }\n\n  void process(int2 pos) {\n    float gx = (h(1, -1) + 2.0f * h(1, 0) + h(1, 1)) - (h(-1, -1) + 2.0f * h(-1, 0) + h(-1, 1));\n    float gy = (h(-1, 1) + 2.0f * h(0, 1) + h(1, 1)) - (h(-1, -1) + 2.0f * h(0, -1) + h(1, -1));\n    float k = strength / (8.0f * s);\n    gx *= k;\n    gy *= k * (flipGreen ? -1.0f : 1.0f);\n    float3 n = normalize(float3(-gx, -gy, 1.0f));\n    if (encode) n = n * 0.5f + 0.5f;\n    dst() = float4(n.x, n.y, n.z, 1.0f);\n  }\n};\n"},{"id":"SleepyNormalCurvature","kernel":"SleepyNormalCurvature","cat":"Normals & surface","title":"Curvature from normals","desc":"Convex and concave areas from a normal map: bright on bumps, dark in dents. For edge wear, dirt and cavity masks.","params":[{"n":"gain","t":"float","v":0.5,"lo":0,"hi":5,"l":"gain"},{"n":"spacing","t":"int","v":1,"lo":1,"hi":10,"l":"spacing"},{"n":"encoded","t":"bool","v":0,"l":"normals are 0\u20131"},{"n":"mode","t":"enum","v":0,"items":["Signed (grey = flat)","Convex only","Concave only"],"l":"mode"}],"source":"kernel SleepyNormalCurvature : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRanged2D, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  float gain;\n  int spacing;\n  bool encoded;\n  int mode;\n\nlocal:\n  int s;\n\n  void define() {\n    defineParam(gain, \"gain\", 0.5f);\n    defineParam(spacing, \"spacing\", 1);\n    defineParam(encoded, \"encoded\", false);\n    defineParam(mode, \"mode\", 0);\n  }\n\n  void init() {\n    s = max(1, spacing);\n    src.setRange(-s, -s, s, s);\n  }\n\n  float2 nxy(int dx, int dy) {\n    SampleType(src) p = src(dx * s, dy * s);\n    float2 v = float2(p.x, p.y);\n    if (encoded) v = v * 2.0f - 1.0f;\n    return v;\n  }\n\n  // divergence of the normal field: positive on bumps (convex), negative in dents (concave)\n  // mode 0 signed (grey = flat), 1 convex only, 2 concave only\n  void process(int2 pos) {\n    float c = ((nxy(1, 0).x - nxy(-1, 0).x) + (nxy(0, 1).y - nxy(0, -1).y)) * 0.5f / s * gain * 10.0f;\n    float v = 0.5f + c;\n    if (mode == 1) v = max(c, 0.0f);\n    if (mode == 2) v = max(-c, 0.0f);\n    dst() = float4(v, v, v, 1.0f);\n  }\n};\n"},{"id":"SleepyDepthAO","kernel":"SleepyDepthAO","cat":"Normals & surface","title":"Ambient occlusion from depth","desc":"Screen-space AO from a depth pass: darkens creases, corners and contact areas. Flat and tilted surfaces stay clean. Put depth in the chosen channel (use a Shuffle).","params":[{"n":"radius","t":"int","v":24,"lo":2,"hi":128,"l":"radius"},{"n":"range","t":"float","v":1.0,"lo":0.01,"hi":20,"l":"range (depth units)"},{"n":"bias","t":"float","v":0.02,"lo":0,"hi":1,"l":"bias"},{"n":"strength","t":"float","v":1.0,"lo":0,"hi":4,"l":"strength"},{"n":"channel","t":"enum","v":0,"items":["Red","Green","Blue","Alpha"],"l":"channel"},{"n":"inverseDepth","t":"bool","v":0,"l":"depth is 1/Z (ScanlineRender)"}],"source":"kernel SleepyDepthAO : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRanged2D, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  int radius;\n  float range;\n  float bias;\n  float strength;\n  int channel;\n  bool inverseDepth;\n\nlocal:\n  int r;\n\n  void define() {\n    defineParam(radius, \"radius\", 24);\n    defineParam(range, \"range\", 1.0f);\n    defineParam(bias, \"bias\", 0.02f);\n    defineParam(strength, \"strength\", 1.0f);\n    defineParam(channel, \"channel\", 0);\n    defineParam(inverseDepth, \"inverseDepth\", false);\n  }\n\n  void init() {\n    r = clamp(radius, 2, 128);\n    src.setRange(-r, -r, r, r);\n  }\n\n  // distance to camera at an offset; 0 (empty) counts as far away\n  float depth(int dx, int dy) {\n    SampleType(src) p = src(dx, dy);\n    float d = p.x;\n    if (channel == 1) d = p.y;\n    if (channel == 2) d = p.z;\n    if (channel == 3) d = p.w;\n    if (inverseDepth) d = d > 0.0f ? 1.0f / d : 1e6f;\n    else if (d <= 0.0f) d = 1e6f;\n    return d;\n  }\n\n  // screen-space ambient occlusion from depth alone. Each direction samples a pair of opposite\n  // neighbours: on a flat or tilted plane their average equals this pixel's depth, so only real\n  // creases and corners (both sides closer) occlude. Differences much larger than 'range' are\n  // ignored so foreground objects don't darken the background behind them.\n  void process(int2 pos) {\n    float d0 = depth(0, 0);\n    float occ = 0.0f;\n    float total = 0.0f;\n    float jitter = 0.35f * (float)((pos.x * 7 + pos.y * 13) % 4);\n    for (int a = 0; a < 8; a++) {\n      float ang = a * 0.3926991f + jitter;\n      float cs = cos(ang);\n      float sn = sin(ang);\n      for (int st = 1; st <= 4; st++) {\n        float t = st / 4.0f;\n        int dx = (int)floor(cs * r * t + 0.5f);\n        int dy = (int)floor(sn * r * t + 0.5f);\n        float d1 = depth(dx, dy);\n        float d2 = depth(-dx, -dy);\n        float diff = d0 - 0.5f * (d1 + d2);\n        float near = d0 - min(d1, d2);\n        float w = 1.0f - t * 0.5f;\n        if (diff > bias && near < range * 2.0f) occ += w * clamp(diff / range, 0.0f, 1.0f);\n        total += w;\n      }\n    }\n    float ao = clamp(1.0f - strength * 2.0f * occ / total, 0.0f, 1.0f);\n    dst() = float4(ao, ao, ao, 1.0f);\n  }\n};\n"},{"id":"SleepyBilateral","kernel":"SleepyBilateral","cat":"Blur & filter","title":"Bilateral blur (edge-preserving)","desc":"Smooths flat areas and keeps edges sharp: skin, noise, CG fireflies on gradients. sigmaRange sets how different a colour must be to count as an edge.","params":[{"n":"radius","t":"int","v":6,"lo":1,"hi":32,"l":"radius"},{"n":"sigmaSpace","t":"float","v":3.0,"lo":0.5,"hi":16,"l":"sigmaSpace"},{"n":"sigmaRange","t":"float","v":0.1,"lo":0.005,"hi":1,"l":"sigmaRange"}],"source":"kernel SleepyBilateral : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRanged2D, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  int radius;\n  float sigmaSpace;\n  float sigmaRange;\n\nlocal:\n  int r;\n\n  void define() {\n    defineParam(radius, \"radius\", 6);\n    defineParam(sigmaSpace, \"sigmaSpace\", 3.0f);\n    defineParam(sigmaRange, \"sigmaRange\", 0.1f);\n  }\n\n  void init() {\n    r = clamp(radius, 1, 32);\n    src.setRange(-r, -r, r, r);\n  }\n\n  // edge-preserving blur: neighbours count less the further they are in space and in colour\n  void process(int2 pos) {\n    SampleType(src) c = src(0, 0);\n    float ss = 2.0f * max(sigmaSpace * sigmaSpace, 1e-4f);\n    float sr = 2.0f * max(sigmaRange * sigmaRange, 1e-8f);\n    float4 sum = float4(0.0f);\n    float wsum = 0.0f;\n    for (int j = -r; j <= r; j++) {\n      for (int i = -r; i <= r; i++) {\n        SampleType(src) p = src(i, j);\n        float3 d = float3(p.x - c.x, p.y - c.y, p.z - c.z);\n        float w = exp(-(float)(i * i + j * j) / ss - dot(d, d) / sr);\n        sum += float4(p.x, p.y, p.z, p.w) * w;\n        wsum += w;\n      }\n    }\n    dst() = sum / max(wsum, 1e-8f);\n  }\n};\n"},{"id":"SleepyMedian","kernel":"SleepyMedian","cat":"Blur & filter","title":"Median (despeckle)","desc":"Picks the neighbour with the median brightness, so dust, dead pixels and salt-and-pepper noise vanish without new colours. Radius 1\u20133.","params":[{"n":"radius","t":"int","v":1,"lo":1,"hi":3,"l":"radius"},{"n":"amount","t":"float","v":1.0,"lo":0,"hi":1,"l":"mix"}],"source":"kernel SleepyMedian : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRanged2D, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  int radius;\n  float amount;\n\nlocal:\n  int r;\n\n  void define() {\n    defineParam(radius, \"radius\", 1);\n    defineParam(amount, \"amount\", 1.0f);\n  }\n\n  void init() {\n    r = clamp(radius, 1, 3);\n    src.setRange(-r, -r, r, r);\n  }\n\n  float lum(SampleType(src) p) { return 0.2126f * p.x + 0.7152f * p.y + 0.0722f * p.z; }\n\n  // picks the neighbour whose luminance is the median, so colours stay intact (no new colours made)\n  void process(int2 pos) {\n    int n = (2 * r + 1) * (2 * r + 1);\n    int mid = n / 2;\n    SampleType(src) best = src(0, 0);\n    int idx = 0;\n    for (int j = -r; j <= r; j++) {\n      for (int i = -r; i <= r; i++) {\n        SampleType(src) p = src(i, j);\n        float lp = lum(p);\n        int below = 0;\n        int idx2 = 0;\n        for (int jj = -r; jj <= r; jj++) {\n          for (int ii = -r; ii <= r; ii++) {\n            float lq = lum(src(ii, jj));\n            if (lq < lp || (lq == lp && idx2 < idx)) below++;\n            idx2++;\n          }\n        }\n        if (below == mid) best = p;\n        idx++;\n      }\n    }\n    SampleType(src) c = src(0, 0);\n    dst() = c + (best - c) * amount;\n  }\n};\n"},{"id":"SleepyKuwahara","kernel":"SleepyKuwahara","cat":"Blur & filter","title":"Kuwahara (painterly)","desc":"Oil-paint look: each pixel takes the mean of its flattest quadrant, so edges stay crisp while textures turn into strokes.","params":[{"n":"radius","t":"int","v":5,"lo":1,"hi":20,"l":"radius"}],"source":"kernel SleepyKuwahara : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRanged2D, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  int radius;\n\nlocal:\n  int r;\n\n  void define() {\n    defineParam(radius, \"radius\", 5);\n  }\n\n  void init() {\n    r = clamp(radius, 1, 20);\n    src.setRange(-r, -r, r, r);\n  }\n\n  // mean colour and luminance variance of one quadrant\n  float4 quadrant(int x0, int x1, int y0, int y1) {\n    float3 sum = float3(0.0f);\n    float l1 = 0.0f;\n    float l2 = 0.0f;\n    float n = 0.0f;\n    for (int j = y0; j <= y1; j++) {\n      for (int i = x0; i <= x1; i++) {\n        SampleType(src) p = src(i, j);\n        float l = 0.2126f * p.x + 0.7152f * p.y + 0.0722f * p.z;\n        sum += float3(p.x, p.y, p.z);\n        l1 += l;\n        l2 += l * l;\n        n += 1.0f;\n      }\n    }\n    float3 m = sum / n;\n    float var = l2 / n - (l1 / n) * (l1 / n);\n    return float4(m.x, m.y, m.z, var);\n  }\n\n  // painterly smoothing: each pixel takes the mean of whichever quadrant around it is flattest\n  void process(int2 pos) {\n    float4 q0 = quadrant(-r, 0, 0, r);\n    float4 q1 = quadrant(0, r, 0, r);\n    float4 q2 = quadrant(-r, 0, -r, 0);\n    float4 q3 = quadrant(0, r, -r, 0);\n    float4 best = q0;\n    if (q1.w < best.w) best = q1;\n    if (q2.w < best.w) best = q2;\n    if (q3.w < best.w) best = q3;\n    dst() = float4(best.x, best.y, best.z, src(0, 0).w);\n  }\n};\n"},{"id":"SleepyBokehBlur","kernel":"SleepyBokehBlur","cat":"Blur & filter","title":"Bokeh blur","desc":"Lens blur with a circular or bladed aperture. Bright pixels are weighted up so highlights bloom into discs.","params":[{"n":"size","t":"float","v":12.0,"lo":1,"hi":40,"l":"radius"},{"n":"threshold","t":"float","v":0.8,"lo":0,"hi":4,"l":"threshold"},{"n":"boost","t":"float","v":4.0,"lo":0,"hi":20,"l":"boost"},{"n":"blades","t":"int","v":0,"lo":0,"hi":9,"l":"blades (0 = round)"},{"n":"rotation","t":"float","v":0.0,"lo":0,"hi":180,"l":"rotation"}],"source":"kernel SleepyBokehBlur : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRanged2D, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  float size;\n  float threshold;\n  float boost;\n  int blades;\n  float rotation;\n\nlocal:\n  int r;\n\n  void define() {\n    defineParam(size, \"size\", 12.0f);\n    defineParam(threshold, \"threshold\", 0.8f);\n    defineParam(boost, \"boost\", 4.0f);\n    defineParam(blades, \"blades\", 0);\n    defineParam(rotation, \"rotation\", 0.0f);\n  }\n\n  void init() {\n    r = clamp((int)ceil(size), 1, 40);\n    src.setRange(-r, -r, r, r);\n  }\n\n  // 1 inside the aperture shape (circle, or a polygon with 'blades' sides), soft over 1 pixel\n  float aperture(float x, float y) {\n    float d = sqrt(x * x + y * y);\n    if (blades >= 3) {\n      float seg = 6.2831853f / blades;\n      float a = atan2(y, x) - rotation * 0.0174533f;\n      float t = fmod(fmod(a, seg) + seg, seg) - seg * 0.5f;\n      d = d * cos(t) / cos(seg * 0.5f);\n    }\n    return clamp(size + 0.5f - d, 0.0f, 1.0f);\n  }\n\n  // lens blur: averages over the aperture shape, with bright pixels weighted up so highlights bloom into discs\n  void process(int2 pos) {\n    float4 sum = float4(0.0f);\n    float wsum = 0.0f;\n    for (int j = -r; j <= r; j++) {\n      for (int i = -r; i <= r; i++) {\n        float ap = aperture((float)i, (float)j);\n        if (ap <= 0.0f) continue;\n        SampleType(src) p = src(i, j);\n        float l = 0.2126f * p.x + 0.7152f * p.y + 0.0722f * p.z;\n        float w = ap * (1.0f + boost * max(l - threshold, 0.0f));\n        sum += float4(p.x, p.y, p.z, p.w) * w;\n        wsum += w;\n      }\n    }\n    dst() = sum / max(wsum, 1e-8f);\n  }\n};\n"},{"id":"SleepyZoomBlur","kernel":"SleepyZoomBlur","cat":"Blur & filter","title":"Zoom blur","desc":"Radial blur towards a centre (0\u20131 of the frame): speed, impacts, transitions.","params":[{"n":"amount","t":"float","v":0.08,"lo":0,"hi":0.5,"l":"amount"},{"n":"center","t":"float2","v":[0.5,0.5],"l":"center"},{"n":"samples","t":"int","v":24,"lo":2,"hi":128,"l":"samples"}],"source":"kernel SleepyZoomBlur : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRandom, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  float amount;\n  float2 center;\n  int samples;\n\n  void define() {\n    defineParam(amount, \"amount\", 0.08f);\n    defineParam(center, \"center\", float2(0.5f, 0.5f));\n    defineParam(samples, \"samples\", 24);\n  }\n\n  // radial (zoom) blur towards a centre given as 0-1 of the frame\n  void process(int2 pos) {\n    float w = (float)src.bounds.width();\n    float h = (float)src.bounds.height();\n    float2 c = float2(src.bounds.x1 + center.x * w, src.bounds.y1 + center.y * h);\n    float2 p = float2(pos.x + 0.5f, pos.y + 0.5f);\n    int n = clamp(samples, 2, 128);\n    float4 sum = float4(0.0f);\n    for (int k = 0; k < n; k++) {\n      float t = (float)k / (float)(n - 1);\n      float2 q = c + (p - c) * (1.0f - amount * t);\n      sum += bilinear(src, q.x - 0.5f, q.y - 0.5f);\n    }\n    dst() = sum / (float)n;\n  }\n};\n"},{"id":"SleepyDirectionalBlur","kernel":"SleepyDirectionalBlur","cat":"Blur & filter","title":"Directional blur","desc":"Blur along an angle; one-sided turns it into a trailing streak.","params":[{"n":"length","t":"float","v":30.0,"lo":0,"hi":300,"l":"length"},{"n":"angle","t":"float","v":0.0,"lo":-180,"hi":180,"l":"angle"},{"n":"samples","t":"int","v":32,"lo":2,"hi":256,"l":"samples"},{"n":"oneSided","t":"bool","v":0,"l":"one-sided (trail)"}],"source":"kernel SleepyDirectionalBlur : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRandom, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  float blurLength;\n  float angle;\n  int samples;\n  bool oneSided;\n\n  void define() {\n    defineParam(blurLength, \"length\", 30.0f);\n    defineParam(angle, \"angle\", 0.0f);\n    defineParam(samples, \"samples\", 32);\n    defineParam(oneSided, \"oneSided\", false);\n  }\n\n  // motion-style blur along an angle (degrees); oneSided smears only backwards, like a streak trail\n  void process(int2 pos) {\n    float a = angle * 0.0174533f;\n    float2 dir = float2(cos(a), sin(a));\n    float2 p = float2(pos.x + 0.5f, pos.y + 0.5f);\n    int n = clamp(samples, 2, 256);\n    float4 sum = float4(0.0f);\n    for (int k = 0; k < n; k++) {\n      float t = (float)k / (float)(n - 1);\n      float off = oneSided ? -t * blurLength : (t - 0.5f) * blurLength;\n      float2 q = p + dir * off;\n      sum += bilinear(src, q.x - 0.5f, q.y - 0.5f);\n    }\n    dst() = sum / (float)n;\n  }\n};\n"},{"id":"SleepyClarity","kernel":"SleepyClarity","cat":"Blur & filter","title":"Clarity (local contrast)","desc":"Large-radius unsharp mask: adds punch to midtone detail. Luma-only avoids colour shifts; protect highlights stops halos on bright areas.","params":[{"n":"radius","t":"int","v":20,"lo":1,"hi":100,"l":"radius"},{"n":"amount","t":"float","v":0.4,"lo":-1,"hi":2,"l":"amount"},{"n":"lumaOnly","t":"bool","v":1,"l":"luma only"},{"n":"protectHighlights","t":"bool","v":1,"l":"protect highlights"}],"source":"kernel SleepyClarity : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRanged2D, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  int radius;\n  float amount;\n  bool lumaOnly;\n  bool protectHighlights;\n\nlocal:\n  int r;\n  int stp;\n\n  void define() {\n    defineParam(radius, \"radius\", 20);\n    defineParam(amount, \"amount\", 0.4f);\n    defineParam(lumaOnly, \"lumaOnly\", true);\n    defineParam(protectHighlights, \"protectHighlights\", true);\n  }\n\n  void init() {\n    r = clamp(radius, 1, 100);\n    stp = max(1, r / 6);\n    src.setRange(-r, -r, r, r);\n  }\n\n  // local contrast: pushes each pixel away from its blurred surroundings (big-radius unsharp mask).\n  // Sparse sampling keeps large radii cheap.\n  void process(int2 pos) {\n    SampleType(src) c = src(0, 0);\n    float s2 = 2.0f * (r * 0.5f) * (r * 0.5f);\n    float3 sum = float3(0.0f);\n    float wsum = 0.0f;\n    for (int j = -r; j <= r; j += stp) {\n      for (int i = -r; i <= r; i += stp) {\n        SampleType(src) p = src(i, j);\n        float w = exp(-(float)(i * i + j * j) / s2);\n        sum += float3(p.x, p.y, p.z) * w;\n        wsum += w;\n      }\n    }\n    float3 m = sum / wsum;\n    float3 col = float3(c.x, c.y, c.z);\n    float lc = 0.2126f * c.x + 0.7152f * c.y + 0.0722f * c.z;\n    float lm = 0.2126f * m.x + 0.7152f * m.y + 0.0722f * m.z;\n    float k = amount;\n    if (protectHighlights) k *= clamp(1.5f - lc, 0.0f, 1.0f);\n    float3 o;\n    if (lumaOnly) o = col + float3((lc - lm) * k);\n    else o = col + (col - m) * k;\n    dst() = float4(o.x, o.y, o.z, c.w);\n  }\n};\n"},{"id":"SleepyChromaticAberration","kernel":"SleepyChromaticAberration","cat":"Lens","title":"Chromatic aberration","desc":"Lateral CA: red pushed outward, blue inward, growing towards the corners. amount is the shift in pixels at the corner.","params":[{"n":"amount","t":"float","v":6.0,"lo":0,"hi":40,"l":"amount (px at corner)"},{"n":"falloff","t":"float","v":1.5,"lo":0.5,"hi":4,"l":"falloff"},{"n":"center","t":"float2","v":[0.5,0.5],"l":"center"}],"source":"kernel SleepyChromaticAberration : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRandom, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  float amount;\n  float falloff;\n  float2 center;\n\n  void define() {\n    defineParam(amount, \"amount\", 6.0f);\n    defineParam(falloff, \"falloff\", 1.5f);\n    defineParam(center, \"center\", float2(0.5f, 0.5f));\n  }\n\n  // lateral CA: red is pushed outward, blue inward, more towards the corners.\n  // amount = pixel shift at the corner; center is 0-1 of the frame.\n  void process(int2 pos) {\n    float w = (float)src.bounds.width();\n    float h = (float)src.bounds.height();\n    float2 c = float2(src.bounds.x1 + center.x * w, src.bounds.y1 + center.y * h);\n    float2 p = float2(pos.x + 0.5f, pos.y + 0.5f);\n    float2 d = p - c;\n    float len = length(d);\n    float halfDiag = 0.5f * sqrt(w * w + h * h);\n    float2 dir = len > 0.0f ? d / len : float2(0.0f);\n    float shift = amount * pow(clamp(len / halfDiag, 0.0f, 1.0f), falloff);\n    SampleType(src) g = src(pos.x, pos.y);\n    SampleType(src) rs = bilinear(src, p.x - dir.x * shift - 0.5f, p.y - dir.y * shift - 0.5f);\n    SampleType(src) bs = bilinear(src, p.x + dir.x * shift - 0.5f, p.y + dir.y * shift - 0.5f);\n    dst() = float4(rs.x, g.y, bs.z, g.w);\n  }\n};\n"},{"id":"SleepyEdgeExtend","kernel":"SleepyEdgeExtend","cat":"Mattes & edges","title":"Edge extend (colour push)","desc":"Pushes clean core colour out under soft edges so they don't carry green spill or dark fringes. Output is unpremultiplied colour with the original alpha: premultiply after it.","params":[{"n":"radius","t":"int","v":12,"lo":1,"hi":64,"l":"radius"},{"n":"softness","t":"float","v":0.5,"lo":0.1,"hi":2,"l":"softness"},{"n":"premultiplied","t":"bool","v":1,"l":"input is premultiplied"},{"n":"keepCore","t":"bool","v":1,"l":"keep solid core"},{"n":"coreThreshold","t":"float","v":0.8,"lo":0.3,"hi":1,"l":"core alpha threshold"}],"source":"kernel SleepyEdgeExtend : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRanged2D, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  int radius;\n  float softness;\n  bool premultiplied;\n  bool keepCore;\n  float coreThreshold;\n\nlocal:\n  int r;\n\n  void define() {\n    defineParam(radius, \"radius\", 12);\n    defineParam(softness, \"softness\", 0.5f);\n    defineParam(premultiplied, \"premultiplied\", true);\n    defineParam(keepCore, \"keepCore\", true);\n    defineParam(coreThreshold, \"coreThreshold\", 0.8f);\n  }\n\n  void init() {\n    r = clamp(radius, 1, 64);\n    src.setRange(-r, -r, r, r);\n  }\n\n  // average of nearby solid-core colour (normalised convolution): only pixels with alpha above\n  // coreThreshold contribute, so spill in the soft edge isn't spread. Pushes the foreground colour\n  // out under soft edges so they don't carry the background or a dark fringe. Output is unpremultiplied\n  // colour with the original alpha; premultiply after it.\n  void process(int2 pos) {\n    SampleType(src) c = src(0, 0);\n    float sigma = max(r * softness, 0.5f);\n    float s2 = 2.0f * sigma * sigma;\n    float3 sum = float3(0.0f);\n    float wsum = 0.0f;\n    for (int j = -r; j <= r; j++) {\n      for (int i = -r; i <= r; i++) {\n        SampleType(src) p = src(i, j);\n        float core = clamp((p.w - coreThreshold + 0.15f) / 0.15f, 0.0f, 1.0f);\n        float w = exp(-(float)(i * i + j * j) / s2) * core;\n        float3 col = float3(p.x, p.y, p.z);\n        if (premultiplied) col = p.w > 1e-5f ? col / p.w : float3(0.0f);\n        sum += col * w;\n        wsum += w;\n      }\n    }\n    float3 ext = wsum > 1e-8f ? sum / wsum : float3(0.0f);\n    float3 own = float3(c.x, c.y, c.z);\n    if (premultiplied) own = c.w > 1e-5f ? own / c.w : float3(0.0f);\n    float keep = keepCore ? clamp((c.w - 0.95f) / 0.05f, 0.0f, 1.0f) : 0.0f;\n    float3 o = ext + (own - ext) * keep;\n    dst() = float4(o.x, o.y, o.z, c.w);\n  }\n};\n"},{"id":"SleepyAlphaStroke","kernel":"SleepyAlphaStroke","cat":"Mattes & edges","title":"Stroke / outline from alpha","desc":"Outline around a matte, outside or inside, with width and softness. Or output the distance field for glows and custom falloffs.","params":[{"n":"width","t":"float","v":8.0,"lo":0.5,"hi":60,"l":"width"},{"n":"softness","t":"float","v":1.5,"lo":0,"hi":20,"l":"softness"},{"n":"color","t":"color","v":[1.0,0.75,0.2,1.0],"l":"color"},{"n":"mode","t":"enum","v":0,"items":["Stroke over image","Stroke only","Distance field"],"l":"mode"},{"n":"inside","t":"bool","v":0,"l":"inside the shape"}],"source":"kernel SleepyAlphaStroke : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRanged2D, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  float width;\n  float softness;\n  float4 color;\n  int mode;\n  bool inside;\n\nlocal:\n  int r;\n\n  void define() {\n    defineParam(width, \"width\", 8.0f);\n    defineParam(softness, \"softness\", 1.5f);\n    defineParam(color, \"color\", float4(1.0f, 0.75f, 0.2f, 1.0f));\n    defineParam(mode, \"mode\", 0);\n    defineParam(inside, \"inside\", false);\n  }\n\n  void init() {\n    r = clamp((int)ceil(width + softness) + 1, 1, 64);\n    src.setRange(-r, -r, r, r);\n  }\n\n  // distance to the nearest pixel on the other side of the matte edge (alpha 0.5), searched within r.\n  // mode 0: stroke over the image, 1: stroke only, 2: distance field (0 at the edge, 1 at r)\n  void process(int2 pos) {\n    SampleType(src) c = src(0, 0);\n    bool inShape = c.w >= 0.5f;\n    float best = (float)r;\n    for (int j = -r; j <= r; j++) {\n      for (int i = -r; i <= r; i++) {\n        bool other = src(i, j).w >= 0.5f;\n        if (other != inShape) best = min(best, sqrt((float)(i * i + j * j)));\n      }\n    }\n    if (mode == 2) {\n      float v = best / (float)r;\n      dst() = float4(v, v, v, 1.0f);\n      return;\n    }\n    bool onSide = inside ? inShape : !inShape;\n    float s = onSide ? 1.0f - clamp((best - width + softness) / max(softness, 1e-3f), 0.0f, 1.0f) : 0.0f;\n    float sa = s * color.w;\n    if (mode == 1) {\n      dst() = float4(color.x * sa, color.y * sa, color.z * sa, sa);\n      return;\n    }\n    // stroke under the image (outside) or over it (inside), premultiplied\n    if (inside) dst() = float4(c.x + (color.x * sa - c.x) * s, c.y + (color.y * sa - c.y) * s, c.z + (color.z * sa - c.z) * s, max(c.w, sa));\n    else dst() = float4(c.x + color.x * sa * (1.0f - c.w), c.y + color.y * sa * (1.0f - c.w), c.z + color.z * sa * (1.0f - c.w), c.w + sa * (1.0f - c.w));\n  }\n};\n"},{"id":"SleepyRoundErodeDilate","kernel":"SleepyRoundErodeDilate","cat":"Mattes & edges","title":"Round erode / dilate","desc":"Grows (positive) or shrinks (negative) a matte as circles, with sub-pixel size, instead of the square shape of a min/max filter.","params":[{"n":"size","t":"float","v":4.0,"lo":-64,"hi":64,"l":"size"},{"n":"alphaOnly","t":"bool","v":1,"l":"alpha only"}],"source":"kernel SleepyRoundErodeDilate : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRanged2D, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  float size;\n  bool alphaOnly;\n\nlocal:\n  int r;\n\n  void define() {\n    defineParam(size, \"size\", 4.0f);\n    defineParam(alphaOnly, \"alphaOnly\", true);\n  }\n\n  void init() {\n    r = clamp((int)ceil(fabs(size)), 1, 64);\n    src.setRange(-r, -r, r, r);\n  }\n\n  // round-shaped min (erode, size < 0) or max (dilate, size > 0) with sub-pixel radius,\n  // so mattes grow and shrink as circles instead of squares\n  void process(int2 pos) {\n    SampleType(src) c = src(0, 0);\n    bool grow = size > 0.0f;\n    float rad = fabs(size);\n    float4 acc = c;\n    for (int j = -r; j <= r; j++) {\n      for (int i = -r; i <= r; i++) {\n        float d = sqrt((float)(i * i + j * j));\n        float cover = clamp(rad + 0.5f - d, 0.0f, 1.0f);\n        if (cover <= 0.0f) continue;\n        SampleType(src) p = src(i, j);\n        float4 q = float4(p.x, p.y, p.z, p.w);\n        float4 v = c + (q - c) * cover;\n        acc = grow ? max(acc, v) : min(acc, v);\n      }\n    }\n    if (alphaOnly) dst() = float4(c.x, c.y, c.z, acc.w);\n    else dst() = acc;\n  }\n};\n"},{"id":"SleepyFireflyKiller","kernel":"SleepyFireflyKiller","cat":"Cleanup","title":"Firefly killer","desc":"Removes isolated hot pixels from renders and sensors (also NaN/inf): a pixel much brighter than every neighbour is replaced by their mean. Show detected to tune it.","params":[{"n":"threshold","t":"float","v":1.0,"lo":0,"hi":20,"l":"threshold"},{"n":"ratio","t":"float","v":3.0,"lo":1,"hi":20,"l":"ratio"},{"n":"radius","t":"int","v":1,"lo":1,"hi":3,"l":"radius"},{"n":"showDetected","t":"bool","v":0,"l":"show detected"}],"source":"kernel SleepyFireflyKiller : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRanged2D, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  float threshold;\n  float ratio;\n  int radius;\n  bool showDetected;\n\nlocal:\n  int r;\n\n  void define() {\n    defineParam(threshold, \"threshold\", 1.0f);\n    defineParam(ratio, \"ratio\", 3.0f);\n    defineParam(radius, \"radius\", 1);\n    defineParam(showDetected, \"showDetected\", false);\n  }\n\n  void init() {\n    r = clamp(radius, 1, 3);\n    src.setRange(-r, -r, r, r);\n  }\n\n  float lum(SampleType(src) p) { return 0.2126f * p.x + 0.7152f * p.y + 0.0722f * p.z; }\n\n  // removes isolated hot pixels (render fireflies, sensor hot spots): a pixel brighter than\n  // 'threshold' and 'ratio' times brighter than every neighbour (or NaN/inf) is replaced by the neighbours' mean\n  void process(int2 pos) {\n    SampleType(src) c = src(0, 0);\n    float4 sum = float4(0.0f);\n    float mx = -1e30f;\n    float n = 0.0f;\n    for (int j = -r; j <= r; j++) {\n      for (int i = -r; i <= r; i++) {\n        if (i == 0 && j == 0) continue;\n        SampleType(src) p = src(i, j);\n        float lp = lum(p);\n        if (!(lp == lp) || lp > 1e30f) continue;\n        sum += float4(p.x, p.y, p.z, p.w);\n        mx = max(mx, lp);\n        n += 1.0f;\n      }\n    }\n    float lc = lum(c);\n    bool broken = !(lc == lc) || lc > 1e30f;\n    bool hot = broken || (lc > threshold && lc > ratio * max(mx, 1e-6f));\n    if (showDetected) dst() = hot ? float4(1.0f, 0.0f, 1.0f, 1.0f) : c * 0.25f;\n    else dst() = hot ? (n > 0.0f ? sum / n : float4(0.0f)) : c;\n  }\n};\n"},{"id":"SleepyFixBadPixels","kernel":"SleepyFixBadPixels","cat":"Cleanup","title":"Fix NaN / inf pixels","desc":"Replaces NaN and infinite pixels (optionally negatives) with the average of the good pixels around them, instead of black holes.","params":[{"n":"radius","t":"int","v":2,"lo":1,"hi":8,"l":"radius"},{"n":"fixNegative","t":"bool","v":0,"l":"also fix negatives"},{"n":"showBad","t":"bool","v":0,"l":"show bad pixels"}],"source":"kernel SleepyFixBadPixels : ImageComputationKernel<ePixelWise>\n{\n  Image<eRead, eAccessRanged2D, eEdgeClamped> src;\n  Image<eWrite> dst;\n\nparam:\n  int radius;\n  bool fixNegative;\n  bool showBad;\n\nlocal:\n  int r;\n\n  void define() {\n    defineParam(radius, \"radius\", 2);\n    defineParam(fixNegative, \"fixNegative\", false);\n    defineParam(showBad, \"showBad\", false);\n  }\n\n  void init() {\n    r = clamp(radius, 1, 8);\n    src.setRange(-r, -r, r, r);\n  }\n\n  bool bad(SampleType(src) p) {\n    float s = p.x + p.y + p.z + p.w;\n    if (!(s == s) || fabs(s) > 1e30f) return true;\n    if (!(p.x == p.x) || !(p.y == p.y) || !(p.z == p.z) || !(p.w == p.w)) return true;\n    if (fixNegative && (p.x < 0.0f || p.y < 0.0f || p.z < 0.0f)) return true;\n    return false;\n  }\n\n  // replaces NaN, infinite (and optionally negative) pixels with the average of the good ones around them\n  void process(int2 pos) {\n    SampleType(src) c = src(0, 0);\n    bool b = bad(c);\n    if (showBad) {\n      dst() = b ? float4(0.0f, 1.0f, 1.0f, 1.0f) : float4(0.0f, 0.0f, 0.0f, 0.0f);\n      return;\n    }\n    if (!b) {\n      dst() = c;\n      return;\n    }\n    float4 sum = float4(0.0f);\n    float n = 0.0f;\n    for (int j = -r; j <= r; j++) {\n      for (int i = -r; i <= r; i++) {\n        SampleType(src) p = src(i, j);\n        if (!bad(p)) {\n          sum += float4(p.x, p.y, p.z, p.w);\n          n += 1.0f;\n        }\n      }\n    }\n    dst() = n > 0.0f ? sum / n : float4(0.0f);\n  }\n};\n"}]''')


# ---------------------------------------------------------------- library
def load_user_kernels():
    try:
        with open(USER_FILE) as fh:
            data = json.load(fh)
        return [k for k in data if isinstance(k, dict) and k.get("id") and k.get("source")]
    except (IOError, OSError, ValueError):
        return []


def save_user_kernels(items):
    folder = os.path.dirname(USER_FILE)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    tmp = USER_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(items, fh, indent=1)
    os.replace(tmp, USER_FILE)


def all_kernels():
    return KERNELS + load_user_kernels()


def find_kernel(kid):
    for k in all_kernels():
        if k["id"] == kid:
            return k
    raise KeyError("No kernel called %r" % kid)


def kernel_name(source):
    m = re.search(r"\bkernel\s+(\w+)", source)
    return m.group(1) if m else ""


# ---------------------------------------------------------------- node building
class _Undo(object):
    def __init__(self, name):
        self.name, self.undo = name, None

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


def _param_knob(node, kname, pname):
    knobs = node.knobs()
    for cand in (kname + "_" + pname, pname):
        if cand in knobs:
            return knobs[cand]
    for name, k in knobs.items():
        if name.endswith("_" + pname):
            return k
    return None


def _compile(node):
    knobs = node.knobs()
    if "recompile" in knobs:
        try:
            knobs["recompile"].execute()
            return True
        except Exception:
            pass
    try:
        node["kernelSource"].setNeedsRecompile()
        return True
    except Exception:
        return False


def _set_param(k, p, value):
    t = p["t"]
    if t == "float":
        k.setValue(float(value))
    elif t in ("int", "enum"):
        k.setValue(int(value))
    elif t == "bool":
        k.setValue(bool(value))
    elif t in ("float2", "color"):
        for i, v in enumerate(value):
            k.setValue(float(v), i)


def create(kernel, values=None, open_panel=False):
    """Create a BlinkScript node for a kernel id (or kernel dict). values override the defaults."""
    rec = find_kernel(kernel) if isinstance(kernel, str) else kernel
    values = values or {}
    kname = rec.get("kernel") or kernel_name(rec["source"])
    with _Undo("Sleepy Blink: " + rec["title"]):
        try:
            node = nuke.createNode("BlinkScript", inpanel=False)
        except Exception as exc:
            raise RuntimeError("Couldn't create a BlinkScript node (%s). Some Nuke licences only "
                               "allow BlinkScript in NukeX." % exc)
        node["kernelSource"].setValue(rec["source"])
        _compile(node)
        missing = []
        for p in rec.get("params", []):
            k = _param_knob(node, kname, p["n"])
            if k is None:
                missing.append(p["n"])
                continue
            try:
                _set_param(k, p, values.get(p["n"], p["v"]))
            except Exception:
                missing.append(p["n"])
        try:
            node.setName("SleepyB_" + re.sub(r"\W+", "_", rec["id"]).replace("Sleepy", "", 1), uncollide=True)
        except Exception:
            pass
        node["label"].setValue(rec["title"])
    if missing and values:
        nuke.message("The kernel is loaded, but these values couldn't be set yet: %s.\n"
                     "Press Recompile on the node, then set them there." % ", ".join(missing))
    if open_panel:
        node.showControlPanel()
    return node


def save_selected(title, desc=""):
    try:
        node = nuke.selectedNode()
    except ValueError:
        raise ValueError("Select a BlinkScript node first.")
    if node.Class() != "BlinkScript":
        raise ValueError("Select a BlinkScript node (selected: %s)." % node.Class())
    src = node["kernelSource"].value()
    if not src.strip():
        raise ValueError("That BlinkScript node has no kernel source.")
    kid = "user_" + re.sub(r"\W+", "_", title).strip("_").lower()
    rec = {"id": kid, "kernel": kernel_name(src), "cat": USER_CAT, "title": title,
           "desc": desc or "Saved from %s." % node.name(), "params": [], "source": src}
    items = [k for k in load_user_kernels() if k["id"] != kid]
    items.append(rec)
    save_user_kernels(items)
    return rec


def delete_user_kernel(kid):
    save_user_kernels([k for k in load_user_kernels() if k["id"] != kid])


# ---------------------------------------------------------------- panel
_instance = None


class _Vec(QtWidgets.QWidget):
    def __init__(self, value, color=False, parent=None):
        super(_Vec, self).__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.spins = []
        for v in value:
            s = QtWidgets.QDoubleSpinBox()
            s.setRange(-1e7, 1e7)
            s.setDecimals(3)
            s.setSingleStep(0.05)
            s.setValue(v)
            lay.addWidget(s)
            self.spins.append(s)
        if color:
            b = QtWidgets.QPushButton()
            b.setFixedWidth(28)
            b.setToolTip("Pick a colour")
            b.clicked.connect(self._pick)
            lay.addWidget(b)
            self.swatch = b
            for s in self.spins:
                s.valueChanged.connect(self._paint)
            self._paint()

    def _rgb8(self):
        return [max(0, min(255, int(round(max(s.value(), 0) ** (1 / 2.2) * 255)))) for s in self.spins[:3]]

    def _paint(self, *a):
        self.swatch.setStyleSheet("background-color: rgb(%d,%d,%d); border: 1px solid #555;" % tuple(self._rgb8()))

    def _pick(self):
        col = QtWidgets.QColorDialog.getColor(QtGui.QColor(*self._rgb8()), self, "Pick colour")
        if col.isValid():
            for s, v in zip(self.spins, (col.redF(), col.greenF(), col.blueF())):
                s.setValue(round(v ** 2.2, 4))

    def value(self):
        return [s.value() for s in self.spins]


class BlinkScriptLabPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(BlinkScriptLabPanel, self).__init__(parent)
        global _instance
        _instance = self
        self.current = None
        self.fields = {}
        self._build()
        self.reload()

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search: normals, AO, bokeh, median, outline…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._create)
        root.addWidget(self.search)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        root.addWidget(split, 1)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(210)
        self.tree.currentItemChanged.connect(self._on_select)
        self.tree.itemDoubleClicked.connect(lambda it, c: it.parent() is not None and self._create())
        split.addWidget(self.tree)

        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        self.title = QtWidgets.QLabel()
        f = self.title.font()
        f.setPointSize(f.pointSize() + 4)
        f.setBold(True)
        self.title.setFont(f)
        rl.addWidget(self.title)
        self.meta = QtWidgets.QLabel()
        self.meta.setStyleSheet("color: #a0a0a0;")
        rl.addWidget(self.meta)
        self.desc = QtWidgets.QLabel()
        self.desc.setWordWrap(True)
        rl.addWidget(self.desc)
        box = QtWidgets.QGroupBox("Starting values")
        self.form = QtWidgets.QFormLayout(box)
        self.form.setLabelAlignment(QtCore.Qt.AlignRight)
        rl.addWidget(box)
        self.code = QtWidgets.QPlainTextEdit()
        self.code.setReadOnly(True)
        mono = QtGui.QFont("Consolas" if os.name == "nt" else "Menlo")
        mono.setStyleHint(QtGui.QFont.Monospace)
        self.code.setFont(mono)
        self.code.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        rl.addWidget(self.code, 1)

        row = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton("Create node")
        b.setStyleSheet("QPushButton { font-weight: bold; padding: 5px 14px; }")
        b.clicked.connect(self._create)
        row.addWidget(b)
        self.chk_open = QtWidgets.QCheckBox("Open properties")
        self.chk_open.setChecked(True)
        row.addWidget(self.chk_open)
        row.addStretch(1)
        for label, fn in (("Reset values", lambda: self._show(self.current)), ("Copy source", self._copy),
                          ("Save .blink…", self._export)):
            bb = QtWidgets.QPushButton(label)
            bb.clicked.connect(fn)
            row.addWidget(bb)
        rl.addLayout(row)
        row2 = QtWidgets.QHBoxLayout()
        bs = QtWidgets.QPushButton("Save selected BlinkScript node…")
        bs.clicked.connect(self._save_selected)
        row2.addWidget(bs)
        self.btn_del = QtWidgets.QPushButton("Delete from My kernels")
        self.btn_del.clicked.connect(self._delete)
        row2.addWidget(self.btn_del)
        row2.addStretch(1)
        rl.addLayout(row2)
        split.addWidget(right)
        split.setStretchFactor(1, 3)

    def reload(self, select=None):
        self.items = all_kernels()
        self.tree.clear()
        cats = {}
        for rec in self.items:
            cat = rec.get("cat", USER_CAT)
            if cat not in cats:
                top = QtWidgets.QTreeWidgetItem([cat])
                f = top.font(0)
                f.setBold(True)
                top.setFont(0, f)
                top.setFlags(top.flags() & ~QtCore.Qt.ItemIsSelectable)
                self.tree.addTopLevelItem(top)
                top.setExpanded(True)
                cats[cat] = top
            it = QtWidgets.QTreeWidgetItem([rec["title"]])
            it.setData(0, QtCore.Qt.UserRole, rec["id"])
            it.setToolTip(0, rec.get("desc", ""))
            it.setData(0, QtCore.Qt.UserRole + 1, " ".join([rec["title"], rec.get("desc", ""), rec["id"], cat]).lower())
            cats[cat].addChild(it)
        self._filter(self.search.text())
        target = select or (self.current or {}).get("id")
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                ch = top.child(j)
                if target is None or ch.data(0, QtCore.Qt.UserRole) == target:
                    self.tree.setCurrentItem(ch)
                    return

    def _filter(self, text):
        words = text.lower().split()
        first = None
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            n = 0
            for j in range(top.childCount()):
                ch = top.child(j)
                ok = all(w in (ch.data(0, QtCore.Qt.UserRole + 1) or "") for w in words)
                ch.setHidden(not ok)
                if ok:
                    n += 1
                    first = first or ch
            top.setHidden(n == 0)
        cur = self.tree.currentItem()
        if words and first is not None and (cur is None or cur.isHidden() or cur.parent() is None):
            self.tree.setCurrentItem(first)

    def _on_select(self, item, prev=None):
        if item is None or item.parent() is None:
            return
        rid = item.data(0, QtCore.Qt.UserRole)
        for rec in self.items:
            if rec["id"] == rid:
                self._show(rec)
                return

    def _show(self, rec):
        if rec is None:
            return
        self.current = rec
        self.title.setText(rec["title"])
        self.meta.setText("%s  ·  BlinkScript kernel %s" % (rec.get("cat", USER_CAT), rec.get("kernel") or kernel_name(rec["source"])))
        self.desc.setText(rec.get("desc", ""))
        while self.form.rowCount():
            self.form.removeRow(0)
        self.fields = {}
        for p in rec.get("params", []):
            t, v = p["t"], p["v"]
            if t == "float":
                w = QtWidgets.QDoubleSpinBox()
                w.setRange(-1e7, 1e7)
                w.setDecimals(4)
                w.setSingleStep(max(1e-4, (p["hi"] - p["lo"]) / 100.0))
                w.setValue(v)
            elif t == "int":
                w = QtWidgets.QSpinBox()
                w.setRange(-10 ** 6, 10 ** 6)
                w.setValue(int(v))
            elif t == "bool":
                w = QtWidgets.QCheckBox()
                w.setChecked(bool(v))
            elif t == "enum":
                w = QtWidgets.QComboBox()
                w.addItems(p["items"])
                w.setCurrentIndex(int(v))
            else:
                w = _Vec(list(v), color=(t == "color"))
            self.fields[p["n"]] = (p, w)
            label = p.get("l", p["n"]) + (" (0–1 of frame)" if t == "float2" else "")
            self.form.addRow(label, w)
        if not rec.get("params"):
            self.form.addRow(QtWidgets.QLabel("Values are set on the node after it's created."))
        self.code.setPlainText(rec["source"])
        self.btn_del.setEnabled(rec.get("cat") == USER_CAT)

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
            else:
                out[name] = w.value()
        return out

    def _create(self):
        if self.current is None:
            return
        try:
            create(self.current, self.values(), self.chk_open.isChecked())
        except Exception as exc:
            nuke.message("Couldn't create %s:\n%s" % (self.current["title"], exc))

    def _copy(self):
        if self.current:
            QtWidgets.QApplication.clipboard().setText(self.current["source"])

    def _export(self):
        if not self.current:
            return
        name = (self.current.get("kernel") or kernel_name(self.current["source"]) or "kernel") + ".blink"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save kernel", os.path.join(os.path.expanduser("~"), name), "BlinkScript (*.blink)")
        if path:
            with open(path, "w") as fh:
                fh.write(self.current["source"])

    def _save_selected(self):
        title, ok = QtWidgets.QInputDialog.getText(self, "Save to My kernels", "Name:")
        if not ok or not title.strip():
            return
        desc, ok = QtWidgets.QInputDialog.getText(self, "Save to My kernels", "What does it do? (optional)")
        try:
            rec = save_selected(title.strip(), desc.strip() if ok else "")
        except Exception as exc:
            nuke.message(str(exc))
            return
        self.search.clear()
        self.reload(select=rec["id"])

    def _delete(self):
        rec = self.current
        if rec and rec.get("cat") == USER_CAT and nuke.ask("Delete '%s' from My kernels?" % rec["title"]):
            delete_user_kernel(rec["id"])
            self.current = None
            self.reload()


# ---------------------------------------------------------------- install
_installed = False


def show():
    if _instance is not None:
        try:
            if _instance.isVisible():
                _instance.raise_()
                _instance.search.setFocus()
                return _instance
        except RuntimeError:
            pass
    if _nkpanels is None:
        raise RuntimeError("Sleepy Blink needs Nuke's GUI.")
    panel = _nkpanels.registerWidgetAsPanel("sleepy_blink.BlinkScriptLabPanel", PANEL_TITLE, PANEL_ID, True)
    pane = nuke.getPaneFor("Properties.1") or nuke.getPaneFor("DAG.1")
    if pane is not None:
        panel.addToPane(pane)
    else:
        panel.addToPane()
    return panel


def install(menu="SleepyTools"):
    """Register the panel and menus. Safe to call again; survives module reloads."""
    global _installed
    if _installed:
        return
    if getattr(nuke, "_sleepy_blinkscript_lab_installed", False):
        _installed = True           # installed by an earlier copy of this module
        return
    if _nkpanels is not None:
        _nkpanels.registerWidgetAsPanel("sleepy_blink.BlinkScriptLabPanel", PANEL_TITLE, PANEL_ID)
    for bar in (nuke.menu("Nuke"), nuke.menu("Nodes")):
        m = bar.addMenu(menu)
        m.addCommand("BlinkScript Lab", "sleepy_blink.show()")
        sub = m.addMenu("BlinkScripts")
        for rec in KERNELS:
            sub.addCommand("%s/%s" % (rec["cat"].replace("/", "-"), rec["title"].replace("/", "-")),
                           "sleepy_blink.create(%r)" % rec["id"])
    nuke._sleepy_blinkscript_lab_installed = True
    _installed = True
