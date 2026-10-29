"""The writer of a private file: `write_private` gives a file its mode from its first byte.

`write_bytes` followed by `chmod` leaves a new file readable under the umask's mode until the
`chmod`, and leaves an existing file's mode as it was. `write_private` creates a temporary name
beside the file with `os.open`, `O_CREAT | O_EXCL` and the mode, sets that exact mode on the empty
file, writes the bytes, and moves the file into place with `Path.replace`, which is `os.replace`.
So no file that holds the bytes has a mode with more bits than the mode at any moment, whatever
the umask, an existing file ends with the mode, and a symlink at the path is replaced, not written
through.
"""

import contextlib
import os
import pathlib
import secrets
import stat
import tempfile
from typing import Protocol
from unittest import mock

from . import HarnessError

type FilePath = str | os.PathLike[str]


def write_private(path: FilePath, data: bytes, mode: int = 0o600) -> None:
    """Write `data` to the file at `path` with the permission bits `mode`. A failure removes the
    temporary name and raises HarnessError with the path."""
    target = pathlib.Path(path)
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, mode)
    except OSError as e:
        raise HarnessError(f"cannot write {target}: {e.strerror}") from None
    try:
        with os.fdopen(fd, "wb") as f:
            # The umask narrows the mode of os.open; fchmod sets it whole, before any byte is in.
            os.fchmod(f.fileno(), mode)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        temporary.replace(target)
    except OSError as e:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
        raise HarnessError(f"cannot write {target}: {e.strerror}") from None


class Case(Protocol):
    """The recorder of one case: its label and its verdict."""

    def __call__(self, label: str, *, ok: bool) -> None: ...


def mode_of(p: pathlib.Path) -> int:
    """The permission bits of the file at `p`, not of a symlink's target."""
    return stat.S_IMODE(p.lstat().st_mode)


def mode_cases(case: Case, root: pathlib.Path) -> None:
    """Three writes under umask 0, where a mode that comes from the umask shows its group and other
    bits. Each file that os.open creates has its mode read at once, and each chmod reads the mode
    and the size of its target before it changes the mode."""
    created: list[int] = []
    chmods: list[tuple[int, int]] = []
    real_open, real_fchmod, real_chmod = os.open, os.fchmod, os.chmod

    def watched_open(file: FilePath, flags: int, mode: int = 0o777) -> int:
        fd = real_open(file, flags, mode)
        if flags & os.O_CREAT:
            created.append(stat.S_IMODE(os.fstat(fd).st_mode))
        return fd

    def watched_fchmod(fd: int, mode: int) -> None:
        st = os.fstat(fd)
        chmods.append((stat.S_IMODE(st.st_mode), st.st_size))
        real_fchmod(fd, mode)

    def watched_chmod(file: FilePath, mode: int) -> None:
        st = pathlib.Path(file).stat()
        chmods.append((stat.S_IMODE(st.st_mode), st.st_size))
        real_chmod(file, mode)

    existing = root / "existing"
    existing.write_bytes(b"old\n")
    existing.chmod(0o644)
    writes = [
        ("new", b"secret 1\n", 0o600),
        ("existing", b"secret 2\n", 0o600),
        ("narrow", b"secret 3\n", 0o400),
    ]
    umask = os.umask(0)
    try:
        with (
            mock.patch.object(os, "open", watched_open),
            mock.patch.object(os, "fchmod", watched_fchmod),
            mock.patch.object(os, "chmod", watched_chmod),
        ):
            write_private(root / "new", b"secret 1\n")
            write_private(existing, b"secret 2\n")
            write_private(root / "narrow", b"secret 3\n", mode=0o400)
    finally:
        os.umask(umask)
    for name, data, want in writes:
        p = root / name
        got = (oct(mode_of(p)), p.read_bytes())
        case(
            f"the {name} file ends with mode {oct(want)} and its bytes -> {got}", ok=got == (oct(want), data)
        )
    modes = [oct(m) for m in created]
    case(
        f"under umask 0, each of the three files is created without group or other bits -> {modes}",
        ok=len(created) == len(writes) and not any(m & 0o077 for m in created),
    )
    exposed = [(oct(m), size) for m, size in chmods if m & 0o077 and size]
    case(
        f"no chmod meets the bytes under a wider mode -> {[(oct(m), size) for m, size in chmods]}",
        ok=not exposed,
    )
    left = sorted(p.name for p in root.iterdir())
    case(
        f"no other file is left beside the three -> {left}", ok=left == sorted(name for name, _, _ in writes)
    )


def path_cases(case: Case, root: pathlib.Path) -> None:
    """A symlink at the path, and two paths that cannot be written."""
    target = root / "target"
    target.write_bytes(b"target\n")
    link = root / "link"
    link.symlink_to(target)
    write_private(link, b"secret 4\n")
    case(
        f"a symlink at the path is replaced by the file, not written through -> "
        f"link {link.is_symlink()}, target {target.read_bytes()!r}",
        ok=not link.is_symlink()
        and link.read_bytes() == b"secret 4\n"
        and target.read_bytes() == b"target\n",
    )
    (root / "directory").mkdir()
    for label, path in (
        ("a path in a missing directory", root / "missing" / "f"),
        ("a path that is a directory", root / "directory"),
    ):
        before = sorted(p.name for p in root.iterdir())
        try:
            write_private(path, b"secret 5\n")
            message = "written"
        except HarnessError as e:
            message = str(e)
        after = sorted(p.name for p in root.iterdir())
        case(
            f"{label} raises HarnessError with the path and leaves no file -> {message}, {after}",
            ok=str(path) in message and after == before,
        )


def selftest() -> tuple[int, int]:
    """The cases of the module docstring: (number of cases, number wrong)."""
    total = wrong = 0

    def case(label: str, *, ok: bool) -> None:
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  fsutil: {label}")

    with tempfile.TemporaryDirectory(prefix="harness-fsutil-") as tmp:
        (pathlib.Path(tmp) / "modes").mkdir()
        mode_cases(case, pathlib.Path(tmp) / "modes")
        (pathlib.Path(tmp) / "paths").mkdir()
        path_cases(case, pathlib.Path(tmp) / "paths")
    return total, wrong
