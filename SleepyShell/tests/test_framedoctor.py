"""Frame Doctor tests: pure analysis with a fake reader, plus an
end-to-end pass over a real PNG sequence built with QImage (skips
without Qt)."""

import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOL_DIR = os.path.dirname(_HERE)
_SUITE_PARENT = os.path.dirname(_TOOL_DIR)
for _path in (_TOOL_DIR, _SUITE_PARENT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from shellcore import framedoctor

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from SleepyCore.qt import QtGui  # noqa: F401
    HAS_QT = True
except Exception:
    HAS_QT = False


class FakeReaderTest(unittest.TestCase):
    def _frames(self, tmp, numbers, ext="png"):
        frames = []
        for n in numbers:
            path = os.path.join(tmp, "shot.{:04d}.{}".format(n, ext))
            with open(path, "w") as fh:
                fh.write("x")
            frames.append((n, path))
        return frames

    def test_gaps(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        frames = self._frames(tmp, [1001, 1002, 1005, 1009])
        self.assertEqual(framedoctor.frame_gaps(frames),
                         [(1003, 1004), (1006, 1008)])

    def test_no_gaps(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        frames = self._frames(tmp, [1, 2, 3])
        self.assertEqual(framedoctor.frame_gaps(frames), [])

    def test_zero_byte_and_verdict(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        frames = self._frames(tmp, [1, 2, 3])
        open(frames[1][1], "w").close()  # zero bytes
        stats = {"width": 160, "height": 90, "mean": 0.2, "std": 0.1,
                 "nan_count": 0, "hot_fraction": 0.0}
        report = framedoctor.analyze(frames, lambda p: stats)
        self.assertEqual(report["zero_byte"], [2])
        self.assertEqual(report["verdict"], "PROBLEMS")

    def test_black_nan_hot(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        frames = self._frames(tmp, [1, 2, 3, 4])
        black = dict(width=16, height=9, mean=0.0, std=0.0, nan_count=0,
                     hot_fraction=0.0)
        hot = dict(width=16, height=9, mean=0.9, std=0.4, nan_count=0,
                   hot_fraction=0.8)
        nan = dict(width=16, height=9, mean=0.5, std=0.1, nan_count=3,
                   hot_fraction=0.0)
        normal = dict(width=16, height=9, mean=0.3, std=0.1, nan_count=0,
                      hot_fraction=0.0)
        reads = {path: stats for (number, path), stats in
                 zip(frames, [normal, black, hot, nan])}
        report = framedoctor.analyze(frames, lambda p: reads[p])
        self.assertIn(2, report["black"])
        self.assertIn(3, report["hot"])
        self.assertIn(4, report["nan"])
        self.assertEqual(report["verdict"], "PROBLEMS")

    def test_resolution_change(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        frames = self._frames(tmp, [1, 2])
        reads = {
            frames[0][1]: dict(width=160, height=90, mean=0.3, std=0.1,
                               nan_count=0, hot_fraction=0.0),
            frames[1][1]: dict(width=320, height=180, mean=0.3, std=0.1,
                               nan_count=0, hot_fraction=0.0),
        }
        report = framedoctor.analyze(frames, lambda p: reads[p])
        self.assertEqual(report["resolution_changes"], [2])

    def test_find_sequence_patterns(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self._frames(tmp, [1, 2])
        folder, seq = framedoctor.find_sequence(
            os.path.join(tmp, "shot.####.png"))
        self.assertEqual(folder, tmp)
        self.assertEqual(len(seq["frames"]), 2)
        folder, seq = framedoctor.find_sequence(tmp)
        self.assertEqual(len(seq["frames"]), 2)


@unittest.skipUnless(HAS_QT, "Qt not available")
class QImageReaderTest(unittest.TestCase):
    def test_png_sequence_black_and_gap(self):
        tmp = tempfile.mkdtemp(prefix="framedoctor_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        from shellcore import framedoctor_readers

        def write(number, color, noise=0):
            img = QtGui.QImage(160, 90, QtGui.QImage.Format_ARGB32)
            img.fill(QtGui.QColor(color))
            if noise:
                import random
                random.seed(number)
                painter = QtGui.QPainter(img)
                for _ in range(noise):
                    painter.setPen(QtGui.QColor(255, 255, 255))
                    painter.drawPoint(random.randrange(160),
                                      random.randrange(90))
                painter.end()
            path = os.path.join(tmp, "shot.{:04d}.png".format(number))
            self.assertTrue(img.save(path, "PNG"))

        write(1, "#101010", noise=60)
        write(2, "#202020", noise=60)
        write(3, "#000000")           # black frame
        write(5, "#404040", noise=60)  # gap at 4
        folder, seq = framedoctor.find_sequence(
            os.path.join(tmp, "shot.0001.png"))
        report = framedoctor.analyze(seq["frames"], framedoctor_readers.load)
        self.assertEqual(report["gaps"], [(4, 4)])
        self.assertIn(3, report["black"])
        self.assertEqual(report["verdict"], "PROBLEMS")
        self.assertEqual(report["width"], 160)
        self.assertEqual(report["height"], 90)


if __name__ == "__main__":
    unittest.main(verbosity=1)
