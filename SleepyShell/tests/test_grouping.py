"""Tests for sequence grouping (V2 presentation logic)."""

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOL_DIR = os.path.dirname(_HERE)
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)

from shellcore import grouping


class TestGrouping(unittest.TestCase):
    def test_hundred_bucketing(self):
        self.assertEqual(grouping.sequence_key("sh0134"), "sh0100")
        self.assertEqual(grouping.sequence_key("sh010"), "sh000")
        self.assertEqual(grouping.sequence_key("sh099"), "sh000")
        self.assertEqual(grouping.sequence_key("sh100"), "sh100")

    def test_prefix_and_misc(self):
        self.assertEqual(grouping.sequence_key("bg020"), "bg000")
        self.assertEqual(grouping.sequence_key("plates"), "misc")
        self.assertEqual(grouping.sequence_key(""), "misc")
        self.assertEqual(grouping.sequence_key("sh_x010"), "sh_x000")

    def test_grouping_sorted(self):
        shots = [{"name": "sh020"}, {"name": "sh010"}, {"name": "nt004"}]
        groups = grouping.group_shots(shots)
        self.assertEqual(list(groups.keys()), ["nt000", "sh000"])
        self.assertEqual([s["name"] for s in groups["sh000"]], ["sh010", "sh020"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
