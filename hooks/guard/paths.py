"""Absolute paths as chains of names, so that a check follows a long chain of `cd` in linear time.

A `Place` is one absolute path: its parent `Place` and its last name. A step to a child or to the
parent costs the same at every depth, and a `Place` never changes, so a check can resolve an operand
from a working directory without copying it. Each `Place` keeps the first `HEAD` names of its path,
so a test against a root of the guard reads no more than those.

A step reads the file system only below a directory that exists, and only the path of that
directory and one name more. A path below a name that does not exist names no file, so the result
is the one that a read of the whole path gives.

Two modes of a walk: `real` resolves a symbolic link as `Path.resolve` does, and `..` then leaves
the resolved directory; `plain` keeps every name, and `..` drops the last name, as a lexical
normalisation does. Both record whether the path names a file. A third mode of a step, `link`,
reads a name without following it, for a path that is resolved already and for a `.git` of any
kind.

Every read of the file system that a payload makes is a function of this module, and each is
memoised once per process: `child` reads a (directory, name, mode) once and keeps one `Place` of
it, the anchor is one `Place`, and `work_tree` asks a directory once whether it holds a `.git`.
The guard decides one payload per process, so a payload reads each (directory, name, mode) at most
once however many checks, readings and call sites ask for it. Above the reads, `go` walks a (start
`Place`, word, mode) once, and `place` an absolute path text once in each mode, so a walk that
every check and every reading asks for steps once.
"""

import functools
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

type Mode = Literal["real", "plain"]
type Read = Literal["real", "plain", "link"]

# The names that each `Place` keeps from the start of its path.
HEAD = 64


@dataclass(frozen=True, slots=True, eq=False)
class Place:
    """An absolute path: `up`, the path of its parent, or None for the anchor `/`; `name`, its last
    name, or the anchor; `size`, the number of its names with the anchor; `head`, its first `HEAD`
    names; `real`, its text when it names a file, or None; `found`, the longest path above it that
    names a file, or None when `real` is set."""

    up: Place | None
    name: str
    size: int
    head: tuple[str, ...]
    real: str | None
    found: Place | None

    @staticmethod
    def anchor(name: str = "/") -> Place:
        """The anchor of every path, which names a file: one `Place` for each anchor, so that every
        walk reads from the same `Place`s."""
        found = ANCHORS.get(name)
        if found is None:
            found = ANCHORS[name] = Place(None, name, 1, (name,), name, None)
        return found

    def existing(self) -> Place:
        """The longest path at or above this one that names a file."""
        return self if self.found is None else self.found

    def parent(self) -> Place:
        """The path one name up; the anchor is its own parent."""
        return self if self.up is None else self.up

    def joined(self, name: str) -> Place:
        """The child `name` of this path, read from no file."""
        head = self.head if len(self.head) >= HEAD else (*self.head, name)
        return Place(self, name, self.size + 1, head, None, self.existing())

    def child(self, name: str, mode: Read) -> Place:
        """The child `name` of this path, from the memo: one read of it in `mode`, when this path
        names a file, and one `Place`, for each (path, name, mode) of the process."""
        key = (self, name, mode)
        found = CHILDREN.get(key)
        if found is None:
            found = CHILDREN[key] = self.read(name, mode)
        return found

    def read(self, name: str, mode: Read) -> Place:
        """The child `name` of this path, after a read of it when this path names a file: `real`
        follows a symbolic link, `plain` reads what a link names, `link` reads the link itself."""
        joined = self.joined(name)
        if self.real is None:
            return joined
        path = Path(self.real, name)
        text = str(path)
        try:
            found = path.stat() if mode == "plain" else path.lstat()
        except OSError, ValueError:
            return joined
        if mode == "real" and stat.S_ISLNK(found.st_mode):
            return through(text)
        return Place(self, name, joined.size, joined.head, text, None)

    def go(self, path: str, mode: Mode) -> Place:
        """The path that `path` names from this one, from the memo: an absolute `path` starts at the
        anchor."""
        key = (self, path, mode)
        found = WALKS.get(key)
        if found is None:
            pure = PurePosixPath(path)
            found = place(path, mode) if pure.is_absolute() else self.walk(pure, mode)
            WALKS[key] = found
        return found

    def walk(self, pure: PurePosixPath, mode: Mode) -> Place:
        """The path that `pure` names from this one, one step for each name: an absolute `pure` starts
        at the anchor."""
        found = start(pure, mode) if pure.is_absolute() else self
        for name in pure.parts[1 if pure.is_absolute() else 0 :]:
            found = found.parent() if name == ".." else found.child(name, mode)
        return found

    def names(self) -> list[str]:
        """Every name of the path, the anchor first."""
        found: list[str] = []
        place: Place | None = self
        while place is not None:
            found.append(place.name)
            place = place.up
        return found[::-1]

    def text(self) -> str:
        """The path as text."""
        if self.real is not None:
            return self.real
        tail: list[str] = []
        place = self
        while place.real is None and place.up is not None:
            tail.append(place.name)
            place = place.up
        return str(PurePosixPath(place.text(), *tail[::-1]))

    def starts(self, root: tuple[str, ...]) -> bool:
        """True when the path is `root` or lies below it; `root` as the names of `PurePosixPath.parts`."""
        if self.size < len(root):
            return False
        return (self.head if len(root) <= len(self.head) else tuple(self.names()))[: len(root)] == root

    def below(self, root: tuple[str, ...]) -> bool:
        """True when the path lies strictly below `root`."""
        return self.size > len(root) and self.starts(root)

    def same(self, other: Place) -> bool:
        """True when both are one path."""
        return self.size == other.size and self.head == other.head and self.text() == other.text()


def start(path: PurePosixPath, mode: Mode) -> Place:
    """The anchor of an absolute path: `//` stays apart from `/` in `plain` mode, as a lexical
    normalisation keeps it, and is `/` once resolved."""
    return Place.anchor(path.anchor if mode == "plain" else "/")


@functools.lru_cache(maxsize=1024)
def through(link: str) -> Place:
    """The `Place` that the symbolic link `link` resolves to; a chain of `cd` that passes one link
    many times resolves it once."""
    return settled(str(Path(link).resolve()))


def settled(path: str) -> Place:
    """The `Place` of a resolved absolute path, each name read from the memo without following a
    link."""
    pure = PurePosixPath(path)
    place = start(pure, "real")
    for name in pure.parts[1:]:
        place = place.child(name, "link")
    return place


def has_git(place: Place, mode: Read) -> bool:
    """True when the directory `place` holds a `.git`, read from the memo: of any kind in `link`
    mode, and one that names a file in `plain` mode."""
    return place.child(".git", mode).real is not None


def work_tree(place: Place, mode: Read) -> Place | None:
    """The nearest directory at or above `place` that holds a `.git`, or None; only a directory that
    exists can hold one. Each directory is asked once in each mode, and the answer of every
    directory that a climb passes is kept, so a later climb from below stops where this one went."""
    climbed: list[Place] = []
    found: Place | None = None
    current: Place | None = place.existing()
    while current is not None:
        if (current, mode) in TREES:
            found = TREES[current, mode]
            break
        climbed.append(current)
        if has_git(current, mode):
            found = current
            break
        current = current.up
    for each in climbed:
        TREES[each, mode] = found
    return found


# The memos of a process: the one `Place` of each anchor; the child that each (path, name, mode)
# reads; the work tree of each (directory, mode); the walk of each (start, word, mode). A `Place` is
# its own key, by identity, so a key names one path of one walk.
ANCHORS: dict[str, Place] = {}
CHILDREN: dict[tuple[Place, str, Read], Place] = {}
TREES: dict[tuple[Place, Read], Place | None] = {}
WALKS: dict[tuple[Place, str, Mode], Place] = {}


@functools.cache
def place(path: str, mode: Mode) -> Place:
    """The `Place` of an absolute path, walked once in each mode."""
    return Place.anchor().walk(PurePosixPath(path), mode)
