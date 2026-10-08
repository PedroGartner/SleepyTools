"""Frame Doctor readers: turn an image file into luminance statistics.

Tried in order per extension:
- EXR: the OpenEXR package + numpy (optional install, same as
  Sleepy Queue's preview)
- PNG/JPG/TIFF/BMP: QtGui.QImage (always available inside the suite),
  with numpy if present for speed and a pure-python fallback

Each reader returns ``{width, height, mean, std, nan_count,
hot_fraction}`` — see shellcore.framedoctor. This is the only core
module that may touch Qt, and only inside functions: importing
``shellcore.framedoctor_readers`` without Qt/OpenEXR/PIL works and the
readers simply report that they cannot read.
"""

import math
import os

_EXTENSIONS_EXR = (".exr",)
_EXTENSIONS_QT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


def load(path):
    """Read one frame. Returns a stats dict or None when unreadable."""
    ext = os.path.splitext(path)[1].lower()
    if not os.path.isfile(path):
        return None
    if ext in _EXTENSIONS_EXR:
        stats = _load_exr(path)
        if stats:
            return stats
        return None
    if ext in _EXTENSIONS_QT:
        return _load_qt(path)
    return None


def available_extensions():
    """Extensions a reader exists for on this machine (for UI hints)."""
    result = set()
    try:
        import OpenEXR  # noqa: F401
        result.update(_EXTENSIONS_EXR)
    except Exception:
        pass
    try:
        from SleepyCore.qt import QtGui  # noqa: F401
        result.update(_EXTENSIONS_QT)
    except Exception:
        pass
    return sorted(result)


def _load_exr(path):
    try:
        import OpenEXR
        import numpy
    except Exception:
        return None
    try:
        exr = OpenEXR.InputFile(path)
        header = exr.header()
        channels = header["channels"]
        window = header["dataWindow"]
        width = window.max.x - window.min.x + 1
        height = window.max.y - window.min.y + 1
        names = [c for c in ("R", "G", "B") if c in channels]
        if not names:
            names = list(channels.keys())[:1]
        arrays = [numpy.frombuffer(exr.channel(c, window), dtype="half")
                  for c in names]
        pixels = numpy.vstack(arrays).astype(numpy.float32)
        pixels = pixels.reshape(len(arrays), height, width)
        return _stats_from_array(pixels)
    except Exception:
        return None


def _stats_from_array(pixels):
    """pixels: [channel][y][x] float array — compute the report stats."""
    try:
        import numpy
        lum = pixels.mean(axis=0)
        finite = numpy.isfinite(lum)
        nan_count = int((~finite).sum())
        values = lum[finite]
        if values.size == 0:
            return {"width": lum.shape[1], "height": lum.shape[0],
                    "mean": 0.0, "std": 0.0, "nan_count": nan_count,
                    "hot_fraction": 0.0}
        hot = float((values > 1.0).sum()) / float(values.size)
        return {
            "width": int(lum.shape[1]), "height": int(lum.shape[0]),
            "mean": float(values.mean()), "std": float(values.std()),
            "nan_count": nan_count, "hot_fraction": hot,
        }
    except Exception:
        return None


def _load_qt(path):
    try:
        from SleepyCore.qt import QtGui
    except Exception:
        return None
    try:
        image = QtGui.QImage(path)
        if image.isNull():
            return None
        image = image.convertToFormat(QtGui.QImage.Format_ARGB32)
        width, height = image.width(), image.height()
        if not width or not height:
            return None
        # sample on a grid bounded to ~512 across, straight over the
        # ARGB32 buffer (little-endian: B, G, R, A per pixel)
        step = max(1, max(width, height) // 512)
        ptr = image.constBits()
        buf = memoryview(bytes(ptr)) if not isinstance(
            ptr, (bytes, bytearray, memoryview)) else memoryview(ptr)
        bpl = image.bytesPerLine()
        total = 0.0
        total_sq = 0.0
        hot = 0
        count = 0
        for y in range(0, height, step):
            base = y * bpl
            for px in range(0, width * 4, 4 * step):
                r = buf[base + px + 2]
                g = buf[base + px + 1]
                b = buf[base + px]
                lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
                total += lum
                total_sq += lum * lum
                if lum > 1.0:
                    hot += 1
                count += 1
        if not count:
            return None
        mean = total / count
        std = math.sqrt(max(0.0, total_sq / count - mean * mean))
        return {"width": width, "height": height, "mean": mean, "std": std,
                "nan_count": 0, "hot_fraction": hot / count}
    except Exception:
        return None
    try:
        image = QtGui.QImage(path)
        if image.isNull():
            return None
        image = image.convertToFormat(QtGui.QImage.Format_ARGB32)
        width, height = image.width(), image.height()
        if not width or not height:
            return None
        total = 0.0
        total_sq = 0.0
        hot = 0
        count = 0
        max_dim = 512
        step = max(1, max(width, height) // max_dim)
        for y in range(0, height, step):
            line = image.constBits()
            # scan one row through a wrapped QImage to stay version-safe
            row_img = image.copy(0, y, width, min(step, height - y))
            ptr = row_img.constBits()
            bytes_per_row = row_img.bytesPerLine()
            raw = bytes(ptr) if not isinstance(ptr, (bytes, bytearray)) else ptr
            row_values = []
            for px in range(0, width * 4, 4 * step):
                b, g, r = raw[px], raw[px + 1], raw[px + 2]
                lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
                row_values.append(lum)
            for v in row_values:
                total += v
                total_sq += v * v
                if v > 1.0:
                    hot += 1
                count += 1
        if not count:
            return None
        mean = total / count
        std = math.sqrt(max(0.0, total_sq / count - mean * mean))
        return {"width": width, "height": height, "mean": mean, "std": std,
                "nan_count": 0, "hot_fraction": hot / count}
    except Exception:
        return None
