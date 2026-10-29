"""Absolute paths as chains of names, so that a check follows a long chain of `cd` in linear time.

A `Place` is one absolute path: its parent `Place` and its last name. A step to a child or to the
parent costs the same at every depth, and a `Place` never changes, so a check can resolve an operand
from a working directory without copying it. Each `Place` keeps the first `HEAD` names of its path,
so a test against a root of the guard reads no more than those.

A step reads the file system only below a directory that exists, and only the path of that
directory and one name more. A path below a name that does not exist names no file, so the result
is the one that a read of the whole path gives.

Two modes of a step: `real` resolves a symbolic link as `Path.resolve` does, and `..` then leaves
the resolved directory; `plain` keeps every name, and `..` drops the last name, as a lexical
normalisation does. Both record whether the path names a file.
"""

import functools
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

type Mode = Literal["real", "plain"]

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
        """The anchor of every path, which names a file."""
        return Place(None, name, 1, (name,), name, None)

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

    def child(self, name: str, mode: Mode) -> Place:
        """The child `name` of this path, after a read of it when this path names a file."""
        joined = self.joined(name)
        if self.real is None:
            return joined
        text = str(PurePosixPath(self.real, name))
        try:
            found = Path(text).lstat() if mode == "real" else Path(text).stat()
        except OSError, ValueError:
            return joined
        if mode == "real" and stat.S_ISLNK(found.st_mode):
            return through(text)
        return Place(self, name, joined.size, joined.head, text, None)

    def go(self, path: str, mode: Mode) -> Place:
        """The path that `path` names from this one: an absolute `path` starts at the anchor."""
        pure = PurePosixPath(path)
        place = start(pure, mode) if pure.is_absolute() else self
        for name in pure.parts[1 if pure.is_absolute() else 0 :]:
            place = place.parent() if name == ".." else place.child(name, mode)
        return place

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
    """The `Place` of a resolved absolute path, each name read once without following a link."""
    pure = PurePosixPath(path)
    place = start(pure, "real")
    for name in pure.parts[1:]:
        joined = place.joined(name)
        if place.real is None:
            place = joined
            continue
        text = str(PurePosixPath(place.real, name))
        try:
            Path(text).lstat()
        except OSError, ValueError:
            place = joined
            continue
        place = Place(place, name, joined.size, joined.head, text, None)
    return place


def place(path: str, mode: Mode) -> Place:
    """The `Place` of an absolute path."""
    return Place.anchor().go(path, mode)
