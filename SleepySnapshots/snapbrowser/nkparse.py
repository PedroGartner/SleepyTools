"""Read Nuke scripts as text and compare them.

A small Tcl-aware reader for .nk files: it splits a script into node blocks
(including nodes inside groups), reads each node's knobs as raw strings,
replays the script's set/push stack to work out how nodes are connected, and
compares two scripts node by node. No nuke import, so it works anywhere.
"""

from __future__ import annotations

import gzip
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

#: Knobs that change whenever nodes are moved or clicked.
LAYOUT_KNOBS = frozenset({"xpos", "ypos", "selected"})

GROUP_CLASSES = frozenset({"Group", "LiveGroup"})

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"
RENAMED = "renamed"
STATUSES = (ADDED, REMOVED, CHANGED, RENAMED)

#: Named inputs for common two-stream nodes.
INPUT_NAMES = {
    "Merge2": ("B", "A"),
    "Copy": ("B", "A"),
    "ChannelMerge": ("B", "A"),
    "Keymix": ("B", "A"),
    "Dissolve": ("0", "1"),
}

_HEADER_RE = re.compile(r"^([A-Za-z_][\w.:]*)(?:\s+[^{}\s]+)*\s*\{$")
_CLONE_RE = re.compile(r"^clone\s+(\S+)(?:\s+([A-Za-z_][\w.:]*))?\s*\{$")
_SPECIAL_RE = re.compile(r'[\\"{}\n]')
_NODE_LINE_RE = re.compile(r"^[ \t]*([A-Za-z_]\w*)[ \t]*\{[ \t]*\r?$", re.MULTILINE)


@dataclass
class Node:
    cls: str
    name: str
    path: str
    knobs: "OrderedDict[str, str]"
    text: str
    parent: str = ""
    children_text: str = ""
    inputs: List[Optional[str]] = field(default_factory=list)
    main_inputs: int = 0

    @property
    def is_group(self) -> bool:
        return self.cls in GROUP_CLASSES

    def input_label(self, index: int) -> str:
        if index >= self.main_inputs and self.main_inputs < len(self.inputs):
            return "input {} (mask)".format(index)
        names = INPUT_NAMES.get(self.cls)
        if names and index < len(names):
            return "input {} ({})".format(index, names[index])
        return "input {}".format(index)

    def snippet(self) -> str:
        """Script text for this node (and a group's contents) with its inputs cut."""
        body = _set_knob(self.text, "inputs", "0")
        body = _set_knob(body, "selected", "true")
        return body + self.children_text


@dataclass
class Script:
    nodes: "OrderedDict[str, Node]" = field(default_factory=OrderedDict)
    version: str = ""
    #: False when the set/push stack could not be replayed cleanly, in which
    #: case connections are not compared.
    connections_ok: bool = True

    def get(self, path: str) -> Optional[Node]:
        return self.nodes.get(path)


@dataclass
class KnobChange:
    knob: str
    old: Optional[str]
    new: Optional[str]
    #: Input index for connection changes; None for ordinary knobs.
    index: Optional[int] = None

    @property
    def is_input(self) -> bool:
        return self.index is not None


@dataclass
class NodeDiff:
    path: str
    cls: str
    status: str
    changes: List[KnobChange] = field(default_factory=list)
    old: Optional[Node] = None
    new: Optional[Node] = None
    old_path: str = ""


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def read_text(path: str) -> str:
    """Text of a .nk or gzip-compressed .nk.gz script."""
    if path.lower().endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _scan(text: str, index: int, stop_at_newline: bool):
    """Walk Tcl-ish text from ``index``.

    Returns the index of the closing ``}`` of the enclosing block (when
    ``stop_at_newline`` is False) or of the newline ending the current
    statement (when True). Braces and quotes inside values are respected.
    """
    depth = 0
    in_quote = False
    length = len(text)
    while True:
        match = _SPECIAL_RE.search(text, index)
        if match is None:
            return length
        pos = match.start()
        char = text[pos]
        if char == "\\":
            index = pos + 2
            continue
        if in_quote:
            if char == '"':
                in_quote = False
        elif depth:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
        elif char == '"':
            if pos == 0 or text[pos - 1] in " \t\n":
                in_quote = True
        elif char == "{":
            depth += 1
        elif char == "}":
            if not stop_at_newline:
                return pos
        elif char == "\n" and stop_at_newline:
            return pos
        index = pos + 1


def _split_statements(body: str) -> List[str]:
    statements = []
    index = 0
    length = len(body)
    while index < length:
        end = _scan(body, index, stop_at_newline=True)
        statement = body[index:end].strip()
        if statement:
            statements.append(statement)
        index = end + 1
    return statements


def parse_knobs(body: str) -> "OrderedDict[str, str]":
    knobs: "OrderedDict[str, str]" = OrderedDict()
    for statement in _split_statements(body):
        parts = statement.split(None, 1)
        name = parts[0]
        value = parts[1].strip() if len(parts) > 1 else ""
        if name in knobs:
            knobs[name] = knobs[name] + "\n" + value
        else:
            knobs[name] = value
    return knobs


def _input_counts(spec: Optional[str]):
    """(total, main) from an ``inputs`` knob such as "2" or "2+1". Missing means 1."""
    if spec is None:
        return 1, 1
    try:
        parts = [int(p) for p in spec.strip().split("+")]
    except ValueError:
        return None
    return sum(parts), parts[0]


def parse(text: str) -> Script:
    """Split script text into nodes, keyed by their full path (Group1.Blur1)."""
    script = Script()
    groups: List[tuple] = []  # (path, index where its children start)
    stacks: List[list] = [[]]
    variables: Dict[str, Optional[str]] = {}
    index = 0
    length = len(text)

    def pop():
        if stacks[-1]:
            return stacks[-1].pop()
        script.connections_ok = False
        return None

    while index < length:
        line_end = text.find("\n", index)
        if line_end == -1:
            line_end = length
        line = text[index:line_end]
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            index = line_end + 1
            continue

        header = _HEADER_RE.match(stripped)
        clone = _CLONE_RE.match(stripped) if not header or header.group(1) == "clone" else None
        if (header and header.group(1) != "clone") or clone:
            cls = header.group(1) if header else (clone.group(2) or "clone")
            brace = index + line.rindex("{")
            close = _scan(text, brace + 1, stop_at_newline=False)
            knobs = parse_knobs(text[brace + 1:close])
            block_end = text.find("\n", close)
            block_end = length if block_end == -1 else block_end + 1

            parent = groups[-1][0] if groups else ""
            if cls == "Root":
                name = "Root"
                path = "Root"
            else:
                name = _unquote(knobs.get("name", "")) or "{}_{}".format(cls, len(script.nodes))
                path = parent + "." + name if parent else name

            node = Node(cls, name, path, knobs, text[index:block_end], parent)
            script.nodes[path] = node

            if cls != "Root":
                counts = _input_counts(knobs.get("inputs"))
                if counts is None:
                    script.connections_ok = False
                    counts = (1, 1)
                total, main = counts
                node.inputs = [pop() for _ in range(total)]
                node.main_inputs = main
                if cls in GROUP_CLASSES:
                    groups.append((path, block_end))
                    stacks.append([])
                else:
                    stacks[-1].append(path)
            index = block_end
            continue

        end = _scan(text, index, stop_at_newline=True)
        statement = text[index:end].strip()
        parts = statement.split()
        word = parts[0] if parts else ""
        if word == "end_group" and groups:
            path, start = groups.pop()
            stop = min(end + 1, length)
            children = text[start:stop]
            script.nodes[path].children_text = children if children.endswith("\n") else children + "\n"
            if len(stacks) > 1:
                stacks.pop()
            stacks[-1].append(path)
        elif word == "push" and len(parts) > 1:
            target = parts[1]
            if target == "0":
                stacks[-1].append(None)
            elif target.startswith("$") and target[1:] in variables:
                stacks[-1].append(variables[target[1:]])
            else:
                stacks[-1].append(None)
                script.connections_ok = False
        elif word == "set" and len(parts) > 1:
            variables[parts[1]] = stacks[-1][-1] if stacks[-1] else None
        elif word == "version" and not script.version:
            script.version = statement[len("version"):].strip()
        index = end + 1

    return script


def parse_file(path: str) -> Script:
    return parse(read_text(path))


def count_nodes_in_text(text: str) -> int:
    return sum(1 for m in _NODE_LINE_RE.finditer(text) if m.group(1) != "Root")


def count_nodes(path: str) -> Optional[int]:
    """Fast approximate node count (no full parse)."""
    try:
        return count_nodes_in_text(read_text(path))
    except OSError:
        return None


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    if len(value) >= 2 and value[0] == "{" and value[-1] == "}":
        return value[1:-1]
    return value


def _set_knob(block: str, knob: str, value: str) -> str:
    """Set a simple one-line knob in a node block's text, adding it if missing."""
    pattern = re.compile(r"^([ \t]*){}[ \t][^\n]*$".format(re.escape(knob)), re.MULTILINE)
    if pattern.search(block):
        return pattern.sub(lambda m: "{}{} {}".format(m.group(1), knob, value), block, count=1)
    brace = block.index("{")
    newline = block.find("\n", brace)
    if newline == -1:
        return block
    indent = re.match(r"[ \t]*", block[newline + 1:]).group(0) or " "
    return block[:newline + 1] + "{}{} {}\n".format(indent, knob, value) + block[newline + 1:]


# --------------------------------------------------------------------------
# Comparing
# --------------------------------------------------------------------------

def node_changes(before: Node, after: Node, ignore=LAYOUT_KNOBS,
                 connections: bool = True) -> List[KnobChange]:
    """Knob and connection differences between two states of a node."""
    ignore = set(ignore or ())
    ignore.add("name")
    if connections:
        ignore.add("inputs")

    changes = []
    if before.cls != after.cls:
        changes.append(KnobChange("(class)", before.cls, after.cls))
    names = list(before.knobs) + [k for k in after.knobs if k not in before.knobs]
    for name in names:
        if name in ignore:
            continue
        old_value = before.knobs.get(name)
        new_value = after.knobs.get(name)
        if _normalise(old_value) != _normalise(new_value):
            changes.append(KnobChange(name, old_value, new_value))

    if connections:
        count = max(len(before.inputs), len(after.inputs))
        for i in range(count):
            old_input = before.inputs[i] if i < len(before.inputs) else None
            new_input = after.inputs[i] if i < len(after.inputs) else None
            if old_input != new_input:
                label = (after if i < len(after.inputs) else before).input_label(i)
                changes.append(KnobChange(label, old_input, new_input, index=i))
    return changes


def _signature(node: Node) -> tuple:
    """What must match for a removed and an added node to count as a rename."""
    skip = {"name", "inputs"} | LAYOUT_KNOBS
    knobs = tuple((k, _normalise(v)) for k, v in node.knobs.items() if k not in skip)
    return node.cls, node.parent, knobs


def _same_place(before: Node, after: Node, connections: bool) -> bool:
    """Same spot in the node graph, or fed by the same nodes."""
    if (before.knobs.get("xpos"), before.knobs.get("ypos")) == \
            (after.knobs.get("xpos"), after.knobs.get("ypos")):
        return True
    return connections and bool(before.inputs) and before.inputs == after.inputs


def _meaningful_knobs(node: Node) -> int:
    return sum(1 for k in node.knobs if k not in LAYOUT_KNOBS and k not in ("name", "inputs"))


def diff(old: Script, new: Script, ignore=LAYOUT_KNOBS, renames: bool = True) -> List[NodeDiff]:
    """Nodes added, removed, renamed or changed from ``old`` to ``new``, in script order."""
    connections = old.connections_ok and new.connections_ok
    result: List[NodeDiff] = []

    for path, node in new.nodes.items():
        before = old.nodes.get(path)
        if before is None:
            result.append(NodeDiff(path, node.cls, ADDED, new=node))
            continue
        changes = node_changes(before, node, ignore, connections)
        if changes:
            result.append(NodeDiff(path, node.cls, CHANGED, changes, before, node))

    removed = [NodeDiff(path, node.cls, REMOVED, old=node)
               for path, node in old.nodes.items() if path not in new.nodes]

    if renames and removed:
        _pair_renames(result, removed, ignore, connections)

    return result + removed


def _pair_renames(result: List[NodeDiff], removed: List[NodeDiff], ignore, connections) -> None:
    """Turn matching removed/added pairs into renames, in place.

    Nodes must have the same class, group and knob values. Nodes with no knobs
    of their own (Dots, for example) must also sit at the same spot
    in the node graph or have the same inputs, so unrelated look-alikes are
    not paired.
    """
    by_signature: Dict[tuple, List[NodeDiff]] = {}
    for item in removed:
        by_signature.setdefault(_signature(item.old), []).append(item)

    for position, item in enumerate(result):
        if item.status != ADDED:
            continue
        added = item.new
        candidates = by_signature.get(_signature(added))
        if not candidates:
            continue
        if not _meaningful_knobs(added):
            candidates = [c for c in candidates if _same_place(c.old, added, connections)]
            if not candidates:
                continue
        match = candidates.pop(0)
        removed.remove(match)
        before = match.old
        changes = [KnobChange("name", before.name, added.name)]
        changes += [c for c in node_changes(before, added, ignore, connections) if c.is_input]
        result[position] = NodeDiff(added.path, added.cls, RENAMED, changes, before, added,
                                    old_path=before.path)


def _normalise(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return " ".join(value.split())


def summary(diffs: List[NodeDiff]) -> Dict[str, int]:
    counts = {status: 0 for status in STATUSES}
    for item in diffs:
        counts[item.status] += 1
    return counts


def short_value(value: Optional[str], limit: int = 90) -> str:
    """One-line preview of a knob value for display."""
    if value is None:
        return "(default)"
    flat = " ".join(value.split())
    if len(flat) <= limit:
        return flat
    return "{}… ({:,} chars)".format(flat[:limit], len(value))


def short_input(path: Optional[str], parent: str = "") -> str:
    """Display name for an input, relative to the node's group."""
    if path is None:
        return "(not connected)"
    if parent and path.startswith(parent + "."):
        return path[len(parent) + 1:]
    return path


def describe(change: KnobChange, node: Optional[Node]):
    """(before, after) display strings for a change."""
    if change.is_input:
        parent = node.parent if node else ""
        return short_input(change.old, parent), short_input(change.new, parent)
    return short_value(change.old), short_value(change.new)
