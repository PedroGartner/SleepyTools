"""Frame Doctor command line: QC a rendered frame sequence.

    python tools/frame_doctor.py <folder-or-frame-or-pattern> [--sample N] [--json]

Examples:
    python tools/frame_doctor.py D:\\renders\\sh031
    python tools/frame_doctor.py D:\\renders\\sh031\\sh031_comp_v002.####.exr
    python tools/frame_doctor.py D:\\renders\\sh031 --sample 5 --json

Checks: missing frames, zero-byte frames, black frames, flat frames,
NaNs (EXR), clipped superwhite frames, resolution changes.
Readers: OpenEXR (EXR) and QtGui (PNG/JPG/TIFF/BMP); formats without a
reader on this machine are reported as unreadable rather than skipped
silently.
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOL_DIR = os.path.dirname(_HERE)
_SUITE_PARENT = os.path.dirname(_TOOL_DIR)
for _path in (_TOOL_DIR, _SUITE_PARENT):
    if _path not in sys.path:
        sys.path.append(_path.replace("\\", "/"))

from shellcore import framedoctor, framedoctor_readers  # noqa: E402


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    sample = 1
    if "--sample" in argv:
        try:
            sample = max(1, int(argv[argv.index("--sample") + 1]))
        except (IndexError, ValueError):
            print("invalid --sample value")
            return 1
    folder, sequence = framedoctor.find_sequence(args[0])
    if sequence is None:
        print("No frame sequence found at {!r}".format(args[0]))
        return 1
    report = framedoctor.analyze(sequence["frames"], framedoctor_readers.load,
                                 sample=sample)
    if "--json" in argv:
        print(json.dumps(report, indent=1, default=str))
    else:
        print("Frame Doctor — {}".format(report["sequence"]))
        print("  frames: {frame_count} ({first}-{last}), scanned {scanned}".format(**report))
        if report.get("width"):
            print("  resolution: {width}x{height}".format(**report))
        print("  verdict: {}".format(report["verdict"]))
        for problem in report["problems"]:
            print("  - " + problem)
    return 0 if report["verdict"] == "OK" else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
