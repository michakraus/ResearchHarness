"""The merge into a JSON file that another program owns: `merge` and `merged` change the values
that a change sets, and keep every other byte of the file.

`merged(text, change, *, where)` reads `text` with the refusals of `jsonio`, passes the parsed
object to `change`, and returns the text with only the changed values written again: the key
order, the indentation, the separators, a minified layout, CRLF line ends, the escapes, the final
newline or its absence, and the text of every number that the change leaves stay. A changed string
is written with its characters, not their escapes, except a lone surrogate, which UTF-8 cannot
encode and which stays a `\\u` escape. A key that the change adds goes at the end of its object,
in the file's indentation and separators; a key that it removes goes with its separator. An empty
text, or one of whitespace only, is read as `{}`, and a key added to an empty object at the top
level is indented by 2.

`merge(path, change)` does the same to the file at `path`, through `fsutil.write_private` with the
file's own mode. A missing file is read as an empty one and created with mode 0600, and a symlink
at `path` stays a link: its target is written.
"""

import json
import os
import pathlib
import re
import stat
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from . import HarnessError, fsutil, jsonio

type JsonValue = jsonio.JsonValue
type Change = Callable[[dict[str, JsonValue]], dict[str, JsonValue]]

WHITESPACE = " \t\r\n"
NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
LONE_SURROGATE = re.compile(r"[\ud800-\udfff]")
# Decodes one string of a text that jsonio has read, at its index.
DECODER = json.JSONDecoder()
LITERALS: tuple[tuple[str, JsonValue], ...] = (("true", True), ("false", False), ("null", None))


@dataclass(frozen=True)
class Entry:
    """A member of an object or an element of an array: its key (None in an array), where it
    starts (its key, or its value in an array), where its key ends, and its value."""

    key: str | None
    start: int
    key_end: int
    node: Node


@dataclass(frozen=True)
class Node:
    """A value of the text: its span, its parsed value, and the entries of an object or an array
    (None for any other value)."""

    start: int
    end: int
    value: JsonValue
    entries: tuple[Entry, ...] | None


@dataclass(frozen=True)
class Style:
    """The layout of a text: its line end, the indentation of one level (None for a text of one
    line), and the separators after a key and between two entries on one line."""

    newline: str
    unit: str | None
    key_separator: str
    item_separator: str


@dataclass(frozen=True)
class Edit:
    """The text `new` in place of the span from `start` to `end`."""

    start: int
    end: int
    new: str


def skip(text: str, i: int) -> int:
    """The index of the first character at or after `i` that is not JSON whitespace."""
    while i < len(text) and text[i] in WHITESPACE:
        i += 1
    return i


def parse(text: str, i: int) -> Node:
    """The value that starts at or after `i` in `text`, which `jsonio.loads` has read."""
    i = skip(text, i)
    if text[i] in "{[":
        return container(text, i)
    if text[i] == '"':
        string: tuple[str, int] = DECODER.raw_decode(text, i)
        return Node(i, string[1], string[0], None)
    for word, value in LITERALS:
        if text.startswith(word, i):
            return Node(i, i + len(word), value, None)
    m = NUMBER.match(text, i)
    if m is None:
        raise HarnessError(f"no JSON value at index {i}")
    token = m.group()
    number = float(token) if any(c in token for c in ".eE") else int(token)
    return Node(i, m.end(), number, None)


def container(text: str, i: int) -> Node:
    """The object or the array whose bracket is at `i`."""
    close = "}" if text[i] == "{" else "]"
    entries: list[Entry] = []
    j = skip(text, i + 1)
    while text[j] != close:
        if close == "}":
            decoded: tuple[str, int] = DECODER.raw_decode(text, j)
            key, key_end = decoded
            node = parse(text, skip(text, key_end) + 1)
            entries.append(Entry(key, j, key_end, node))
        else:
            node = parse(text, j)
            entries.append(Entry(None, node.start, node.start, node))
        j = skip(text, node.end)
        if text[j] == ",":
            j = skip(text, j + 1)
    value: JsonValue = (
        {e.key: e.node.value for e in entries if e.key is not None}
        if close == "}"
        else [e.node.value for e in entries]
    )
    return Node(i, j + 1, value, tuple(entries))


def walk(node: Node) -> list[Node]:
    """`node` and the objects and arrays inside it, in the order of the text."""
    found = [node]
    for e in node.entries or ():
        if e.node.entries is not None:
            found += walk(e.node)
    return found


def style_of(text: str, top: Node) -> Style:
    """The layout of `text`, whose top-level object is `top`. The unit is the indentation of the
    first indented line after the first, 2 spaces for a text of several lines that indents none,
    and 2 spaces for a text whose top-level object is empty."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.rstrip(WHITESPACE).split("\n")
    unit = None if len(lines) == 1 and top.entries else "  "
    for line in lines[1:]:
        stripped = line.lstrip(" \t")
        if stripped and stripped != line:
            unit = line[: len(line) - len(stripped)]
            break
    containers = walk(top)
    keyed = [e for n in containers if isinstance(n.value, dict) for e in n.entries or ()]
    key_separator = text[keyed[0].key_end : keyed[0].node.start] if keyed else ":" if unit is None else ": "
    between = [
        text[n.entries[0].node.end : n.entries[1].start]
        for n in containers
        if n.entries is not None and len(n.entries) > 1
    ]
    one_line = [s for s in between if "\n" not in s]
    item_separator = one_line[0] if one_line else "," + (" " if key_separator.endswith(" ") else "")
    return Style(newline, unit, key_separator, item_separator)


def scalar(value: JsonValue, where: str) -> str:
    """The JSON text of a value that is no object and no array: a string with its characters
    raw, except a lone surrogate, which stays a `\\u` escape."""
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as e:
        raise HarnessError(f"{where}: the change sets {value!r}, which is no JSON value: {e}") from None
    return LONE_SURROGATE.sub(lambda m: f"\\u{ord(m[0]):04x}", text) if isinstance(value, str) else text


def render(value: JsonValue, indent: str, style: Style, where: str) -> str:
    """The JSON text of `value` in the layout `style`, whose first line follows text on a line
    indented by `indent`."""
    if isinstance(value, dict):
        opening, closing = "{", "}"
        inner = indent + (style.unit or "")
        items = [
            scalar(k, where) + style.key_separator + render(v, inner, style, where) for k, v in value.items()
        ]
    elif isinstance(value, list):
        opening, closing = "[", "]"
        inner = indent + (style.unit or "")
        items = [render(v, inner, style, where) for v in value]
    else:
        return scalar(value, where)
    if not items:
        return opening + closing
    if style.unit is None:
        return opening + style.item_separator.join(items) + closing
    newline = style.newline
    return opening + newline + inner + ("," + newline + inner).join(items) + newline + indent + closing


def same(a: JsonValue, b: JsonValue) -> bool:
    """Whether `a` and `b` are one JSON value of one type: 1 and 1.0, 0.0 and -0.0, or 1 and true
    are not."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
    return type(a) is type(b) and repr(a) == repr(b)


def indent_at(text: str, index: int) -> str:
    """The spaces and tabs that open the line of `text` that holds `index`."""
    line = text[text.rfind("\n", 0, index) + 1 : index]
    return line[: len(line) - len(line.lstrip(" \t"))]


class Merge:
    """The edits that turn the values of a text into the values of a changed object."""

    def __init__(self, text: str, style: Style, where: str) -> None:
        self.text, self.style, self.where = text, style, where

    def edits(self, node: Node, new: JsonValue) -> list[Edit]:
        """The edits of the span of `node` that give it the value `new`."""
        if same(node.value, new):
            return []
        if node.entries and isinstance(node.value, dict) and isinstance(new, dict):
            pairs = [(e, new[e.key]) for e in node.entries if e.key is not None and e.key in new]
            added = [(k, v) for k, v in new.items() if k not in node.value]
            if pairs:
                return self.entry_edits(node, node.entries, pairs, added)
        elif node.entries and isinstance(node.value, list) and isinstance(new, list):
            pairs = self.kept_elements(node.entries, new)
            if pairs:
                count = len(node.entries)
                added = [(None, v) for v in new[count:]] if len(pairs) == count else []
                return self.entry_edits(node, node.entries, pairs, added)
        return [
            Edit(node.start, node.end, render(new, indent_at(self.text, node.start), self.style, self.where))
        ]

    @staticmethod
    def kept_elements(entries: tuple[Entry, ...], new: list[JsonValue]) -> list[tuple[Entry, JsonValue]]:
        """The elements of an array that stay, each with its new value: each element in turn for an
        array that keeps or adds elements; for one that loses elements, the old elements that the
        new ones are, in order, or [] when the new array is no such subsequence."""
        if len(new) >= len(entries):
            return list(zip(entries, new, strict=False))
        pairs: list[tuple[Entry, JsonValue]] = []
        old = iter(entries)
        for value in new:
            e = next((e for e in old if same(e.node.value, value)), None)
            if e is None:
                return []
            pairs.append((e, value))
        return pairs

    def entry_edits(
        self,
        node: Node,
        entries: tuple[Entry, ...],
        pairs: Sequence[tuple[Entry, JsonValue]],
        added: Sequence[tuple[str | None, JsonValue]],
    ) -> list[Edit]:
        """The edits of an object or an array whose `entries` are those of the text: the entries of
        `pairs` stay with their new values, the others go with a separator, and the entries `added`
        follow the last one."""
        text = self.text
        edits = [edit for e, value in pairs for edit in self.edits(e.node, value)]
        kept = {id(e) for e, _ in pairs}
        last = max(i for i, e in enumerate(entries) if id(e) in kept)
        # An entry before the last that stays goes up to the start of the entry after it, with
        # its separator; the entries after the last that stays go from that one's end.
        edits += [
            Edit(e.start, entries[i + 1].start, "") for i, e in enumerate(entries[:last]) if id(e) not in kept
        ]
        final = entries[-1]
        start, end = entries[last].node.end, final.node.end
        indent = indent_at(text, entries[last].start)
        key_separator = text[final.key_end : final.node.start]
        if "\n" in text[node.start : entries[0].start]:
            separator = "," + self.style.newline + indent
        elif len(entries) > 1:
            separator = text[entries[0].node.end : entries[1].start]
        else:
            separator = self.style.item_separator
        new = "".join(
            separator
            + ("" if key is None else scalar(key, self.where) + key_separator)
            + render(value, indent, self.style, self.where)
            for key, value in added
        )
        if new or end > start:
            edits.append(Edit(start, end, new))
        return edits


def an_object(value: object, where: str) -> dict[str, JsonValue]:
    """`value`, the result of a change, which is an object."""
    if not isinstance(value, dict):
        raise HarnessError(f"{where}: the change returns {type(value).__name__}, not an object")
    return cast("dict[str, JsonValue]", value)


def merged(text: str, change: Change, *, where: str) -> str:
    """`text` with the values that `change` sets written again, and every other byte kept."""
    if not text.strip(WHITESPACE):
        text = "{}\n"
    data = jsonio.loads(text, where=where)
    top = parse(text, 0)
    new = an_object(change(data), where)
    pieces: list[str] = []
    at = 0
    for edit in sorted(Merge(text, style_of(text, top), where).edits(top, new), key=lambda e: e.start):
        pieces += [text[at : edit.start], edit.new]
        at = edit.end
    return "".join([*pieces, text[at:]])


def merge(path: str | os.PathLike[str], change: Change) -> None:
    """Apply `change` to the JSON file at `path`, keeping every byte outside the changed values."""
    given = pathlib.Path(path)
    target = given.resolve() if given.is_symlink() else given
    try:
        mode = stat.S_IMODE(target.stat().st_mode)
        data = target.read_bytes()
    except FileNotFoundError:
        mode, data = 0o600, b""
    except OSError as e:
        raise HarnessError(f"cannot read {given}: {e.strerror}") from None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HarnessError(f"{given} is not UTF-8: {e.reason} at byte {e.start}") from None
    new = merged(text, change, where=str(given)).encode("utf-8")
    if new != data:
        fsutil.write_private(target, new, mode)


def setting(*keys: str, value: JsonValue) -> Change:
    """A change that sets the value at the path `keys`, and returns the object it changed."""

    def change(data: dict[str, JsonValue]) -> dict[str, JsonValue]:
        node = data
        for key in keys[:-1]:
            inner = node[key]
            if not isinstance(inner, dict):
                raise HarnessError(f"{key} is no object")
            node = inner
        node[keys[-1]] = value
        return data

    return change


def removing(key: str) -> Change:
    """A change that removes the top-level `key`."""

    def change(data: dict[str, JsonValue]) -> dict[str, JsonValue]:
        del data[key]
        return data

    return change


def appending(key: str, value: JsonValue) -> Change:
    """A change that appends `value` to the top-level array `key` where it is absent."""

    def change(data: dict[str, JsonValue]) -> dict[str, JsonValue]:
        array = data[key]
        if not isinstance(array, list):
            raise HarnessError(f"{key} is no array")
        if value not in array:
            array.append(value)
        return data

    return change


def keeping(data: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """A change that returns the object it gets."""
    return data


def both(*changes: Change) -> Change:
    """The changes, one after the other."""

    def change(data: dict[str, JsonValue]) -> dict[str, JsonValue]:
        for c in changes:
            data = c(data)
        return data

    return change


MINIFIED = '{"a":1,"settings":{"grants":{"allow":["command(git status)"],"deny":[],"ask":[]}}}'
# (label, the text before, the change, the text after)
CASES: list[tuple[str, str, Change, str]] = [
    (
        "key order and an indentation of 4",
        '{\n    "b": 1,\n    "a": 2,\n    "c": {\n        "d": "x"\n    }\n}\n',
        setting("a", value=5),
        '{\n    "b": 1,\n    "a": 5,\n    "c": {\n        "d": "x"\n    }\n}\n',
    ),
    ("separators", '{ "a" : 1 ,"b":2 }', setting("b", value=3), '{ "a" : 1 ,"b":3 }'),
    (
        "a minified file whose change finds its rule present",
        MINIFIED,
        setting("settings", "grants", "allow", value=["command(git status)"]),
        MINIFIED,
    ),
    (
        "a nested value in a minified file",
        '{"a":1,"b":{"c":true}}',
        setting("b", "c", value=False),
        '{"a":1,"b":{"c":false}}',
    ),
    ("a key added to a minified file", '{"a":1}', setting("z", value=2), '{"a":1,"z":2}'),
    (
        "a key added to an inner object indented by 2",
        '{\n  "x": {\n    "a": 1\n  }\n}\n',
        setting("x", "b", value="n"),
        '{\n  "x": {\n    "a": 1,\n    "b": "n"\n  }\n}\n',
    ),
    (
        "a key added to a file indented by 4",
        '{\n    "a": 1\n}\n',
        setting("b", value=True),
        '{\n    "a": 1,\n    "b": true\n}\n',
    ),
    (
        "CRLF line ends, a changed key and an added one",
        '{\r\n  "a": 1,\r\n  "b": 2\r\n}\r\n',
        both(setting("b", value=3), setting("c", value=4)),
        '{\r\n  "a": 1,\r\n  "b": 3,\r\n  "c": 4\r\n}\r\n',
    ),
    (
        "numbers that the change leaves keep their text",
        '{\n  "a": 1.0,\n  "b": 1e5,\n  "c": 1E+05,\n  "d": -0.0,\n  "e": 10\n}\n',
        setting("e", value=11),
        '{\n  "a": 1.0,\n  "b": 1e5,\n  "c": 1E+05,\n  "d": -0.0,\n  "e": 11\n}\n',
    ),
    (
        "escapes, raw characters and a surrogate escape stay; a changed string is written raw",
        '{\n  "a": "\\u2014",\n  "b": "\u2014",\n  "s": "\\ud800",\n  "n": 1\n}\n',
        setting("n", value="\u00e9\u2014"),
        '{\n  "a": "\\u2014",\n  "b": "\u2014",\n  "s": "\\ud800",\n  "n": "\u00e9\u2014"\n}\n',
    ),
    (
        "a lone surrogate is written as its escape",
        '{\n  "n": 1\n}\n',
        setting("n", value="\ud800"),
        '{\n  "n": "\\ud800"\n}\n',
    ),
    ("a file without a final newline", '{"a": 1}', setting("a", value=2), '{"a": 2}'),
    ("the empty text", "", keeping, "{}\n"),
    ("a text of whitespace only", " \n", keeping, "{}\n"),
    ("a key added to the empty text", "", setting("a", value=1), '{\n  "a": 1\n}\n'),
    ("a key added to {}", "{}", setting("a", value=1), '{\n  "a": 1\n}'),
    (
        "an object added to a file indented by 4",
        '{\n    "a": 1\n}\n',
        setting("o", value={"p": [1, "q"], "r": {}}),
        '{\n    "a": 1,\n    "o": {\n        "p": [\n            1,\n            "q"\n'
        '        ],\n        "r": {}\n    }\n}\n',
    ),
    (
        "an object added to a minified file",
        '{"a":1}',
        setting("o", value={"p": [1, 2]}),
        '{"a":1,"o":{"p":[1,2]}}',
    ),
    (
        "an empty array that gains a member, indented",
        '{\n  "allow": [],\n  "z": 1\n}\n',
        appending("allow", "x"),
        '{\n  "allow": [\n    "x"\n  ],\n  "z": 1\n}\n',
    ),
    (
        "an indented array that gains a member",
        '{\n  "allow": [\n    "x"\n  ]\n}\n',
        appending("allow", "y"),
        '{\n  "allow": [\n    "x",\n    "y"\n  ]\n}\n',
    ),
    (
        "a minified array that gains a member",
        '{"allow":["x"],"deny":[]}',
        both(appending("allow", "y"), appending("deny", "z")),
        '{"allow":["x","y"],"deny":["z"]}',
    ),
    (
        "a key removed in the middle",
        '{\n  "a": 1,\n  "b": 2,\n  "c": 3\n}\n',
        removing("b"),
        '{\n  "a": 1,\n  "c": 3\n}\n',
    ),
    ("the last key removed", '{\n  "a": 1,\n  "b": 2\n}\n', removing("b"), '{\n  "a": 1\n}\n'),
    ("the first key removed", '{"a":1,"b":2}', removing("a"), '{"b":2}'),
    ("the only key removed", '{\n  "a": 1\n}\n', removing("a"), "{}\n"),
    (
        "two last keys removed and one added",
        '{\n  "a": 1,\n  "b": 2,\n  "c": 3\n}\n',
        both(removing("b"), removing("c"), setting("d", value=4)),
        '{\n  "a": 1,\n  "d": 4\n}\n',
    ),
    (
        "an array member removed",
        '{"a": [1, 2, 3]}',
        setting("a", value=[1, 3]),
        '{"a": [1, 3]}',
    ),
    ("a value of another type", '{"a": [1, 2], "b": 1}', setting("a", value="x"), '{"a": "x", "b": 1}'),
    ("a number that keeps its value as another type", '{"a": 1.0}', setting("a", value=1), '{"a": 1}'),
]

# (label, the text, the change): each raises HarnessError.
REFUSED: list[tuple[str, str, Change]] = [
    ("a key twice", '{\n  "a": 1,\n  "a": 2\n}\n', setting("z", value=1)),
    ("a key twice in an inner object", '{"o": {"a": 1, "a": 2}}', setting("z", value=1)),
    ("a top-level array", "[1]\n", setting("z", value=1)),
    ("a BOM", '\ufeff{"a": 1}\n', setting("z", value=1)),
    ("NaN", '{"a": NaN}', setting("z", value=1)),
    ("a nesting deeper than 200", '{"a": ' + "[" * 200 + "]" * 200 + "}", setting("z", value=1)),
    ("a change that sets NaN", '{"a": 1}', setting("a", value=float("nan"))),
    ("a change that returns no object", '{"a": 1}', lambda _data: cast("dict[str, JsonValue]", [])),
]


class Case(Protocol):
    """The recorder of one case: its label and its verdict."""

    def __call__(self, label: str, *, ok: bool) -> None: ...


def refusal(path: pathlib.Path, change: Change) -> str:
    """The message of the HarnessError that `merge(path, change)` raises, or `written`."""
    try:
        merge(path, change)
    except HarnessError as e:
        return str(e)
    return "written"


def table_cases(case: Case, root: pathlib.Path) -> None:
    """The cases of CASES and REFUSED, each on a file of its own below `root`."""
    for i, (label, before, change, after) in enumerate(CASES):
        path = root / f"case-{i}.json"
        path.write_bytes(before.encode("utf-8"))
        message = refusal(path, change)
        got = path.read_bytes().decode("utf-8") if message == "written" else message
        case(f"merge: {label} -> {got!r}, want {after!r}", ok=got == after)
    for i, (label, before, change) in enumerate(REFUSED):
        path = root / f"refused-{i}.json"
        path.write_bytes(before.encode("utf-8"))
        message = refusal(path, change)
        kept = path.read_bytes() == before.encode("utf-8")
        case(
            f"merge: {label} is refused, names the file and keeps its bytes -> {message}, kept {kept}",
            ok=str(path) in message and kept,
        )


def file_cases(case: Case, root: pathlib.Path) -> None:
    """The cases of the file that `merge` writes: its mode, a missing file, a symlink, bytes that are
    not UTF-8, and a change that keeps the object."""
    got = merged('{"a": 1}', setting("a", value=2), where="w")
    case(
        f"merged returns the text and writes nothing -> {got!r}",
        ok=got == '{"a": 2}' and not list(root.iterdir()),
    )

    path = root / "mode.json"
    path.write_bytes(b'{"a": 1}\n')
    path.chmod(0o644)
    merge(path, setting("a", value=2))
    got_mode = oct(stat.S_IMODE(path.stat().st_mode))
    case(f"merge keeps the file's mode 0o644 -> {got_mode}", ok=got_mode == oct(0o644))

    path = root / "missing.json"
    merge(path, setting("a", value=1))
    got_mode = oct(stat.S_IMODE(path.stat().st_mode))
    got = path.read_bytes()
    case(
        f"merge creates a missing file with mode 0o600 -> {got_mode}, {got!r}",
        ok=got_mode == oct(0o600) and got == b'{\n  "a": 1\n}\n',
    )

    target = root / "target.json"
    target.write_bytes(b'{"a": 1}\n')
    target.chmod(0o640)
    link = root / "link.json"
    link.symlink_to(target)
    merge(link, setting("a", value=2))
    got = target.read_bytes()
    got_mode = oct(stat.S_IMODE(target.stat().st_mode))
    case(
        f"merge through a symlink writes its target with the target's mode, and the link stays -> "
        f"link {link.is_symlink()}, {got!r}, {got_mode}",
        ok=link.is_symlink() and got == b'{"a": 2}\n' and got_mode == oct(0o640),
    )

    path = root / "latin1.json"
    path.write_bytes(b'{"a": "\xe9"}')
    message = refusal(path, setting("a", value=2))
    case(f"merge refuses a file that is not UTF-8 and names it -> {message}", ok=str(path) in message)

    path = root / "same.json"
    path.write_bytes(b'{"a": 1}')
    before = path.stat().st_ino
    merge(path, keeping)
    case("merge leaves a file that the change keeps as it is", ok=path.stat().st_ino == before)


def selftest() -> tuple[int, int]:
    """The cases of the module docstring: (number of cases, number wrong)."""
    total = wrong = 0

    def case(label: str, *, ok: bool) -> None:
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  ownedjson: {label}")

    with tempfile.TemporaryDirectory(prefix="harness-ownedjson-") as tmp:
        (pathlib.Path(tmp) / "table").mkdir()
        table_cases(case, pathlib.Path(tmp) / "table")
        (pathlib.Path(tmp) / "files").mkdir()
        file_cases(case, pathlib.Path(tmp) / "files")
    return total, wrong
