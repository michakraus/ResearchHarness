"""The writer of a private file: `write_private` gives a file its mode from its first byte.

`write_bytes` followed by `chmod` leaves a new file readable under the umask's mode until the
`chmod`, and leaves an existing file's mode as it was. `write_private` creates a temporary name
beside the file with `os.open`, `O_CREAT | O_EXCL` and the mode, sets that exact mode on the empty
file, writes the bytes, and moves the file into place with `Path.replace`, which is `os.replace`.
Any failure removes the temporary name. So no file that holds the bytes has a mode with more bits
than the mode at any moment, whatever the umask, an existing file ends with the mode, and a symlink
at the path is replaced, not written through.
"""

import contextlib
import os
import pathlib
import secrets
import stat
import tempfile
from typing import Protocol, cast
from unittest import mock

from . import HarnessError

type FilePath = str | os.PathLike[str]


def write_private(path: FilePath, data: bytes, mode: int = 0o600) -> None:
    """Write `data` to the file at `path` with the permission bits `mode`. A failure removes the
    temporary name and raises HarnessError with the path."""
    target = pathlib.Path(path)
    if not target.name:
        raise HarnessError(f"cannot write {os.fspath(path)!r}: the path names no file")
    # 40 characters of the name are at most 160 bytes, so the temporary name fits where the name does.
    temporary = target.with_name(f".{target.name[:40]}.{secrets.token_hex(8)}.tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, mode)
    except OSError as e:
        raise HarnessError(f"cannot write {target}: {e.strerror}") from None
    except ValueError as e:  # a NUL character in the path
        raise HarnessError(f"cannot write {target}: {e}") from None
    try:
        with os.fdopen(fd, "wb") as f:
            # The umask narrows the mode of os.open; fchmod sets it whole, before any byte is in.
            os.fchmod(f.fileno(), mode)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        temporary.replace(target)
    except OSError as e:
        raise HarnessError(f"cannot write {target}: {e.strerror}") from None
    finally:
        # After the replace the temporary name is gone; after any failure it goes here.
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


class Case(Protocol):
    """The recorder of one case: its label and its verdict."""

    def __call__(self, label: str, *, ok: bool) -> None: ...


def written(path: pathlib.Path, data: bytes) -> str:
    """`written`, or the message of the HarnessError that `write_private(path, data)` raises."""
    try:
        write_private(path, data)
    except HarnessError as e:
        return str(e)
    return "written"


def mode_of(p: pathlib.Path) -> int:
    """The permission bits of the file at `p`, not of a symlink's target."""
    return stat.S_IMODE(p.lstat().st_mode)


def mode_cases(case: Case, root: pathlib.Path) -> None:
    """Three writes under umask 0, where a mode that comes from the umask shows its group and other
    bits. Each file that os.open creates has its mode read at once, and each chmod reads the mode
    and the size of its target before it changes the mode."""
    created: list[int] = []
    exclusive: list[bool] = []
    chmods: list[tuple[int, int]] = []
    real_open, real_fchmod, real_chmod = os.open, os.fchmod, os.chmod

    def watched_open(file: FilePath, flags: int, mode: int = 0o777) -> int:
        fd = real_open(file, flags, mode)
        if flags & os.O_CREAT:
            created.append(stat.S_IMODE(os.fstat(fd).st_mode))
            exclusive.append(bool(flags & os.O_EXCL))
        return fd

    def watched_fchmod(fd: int, mode: int) -> None:
        st = os.fstat(fd)
        chmods.append((stat.S_IMODE(st.st_mode), st.st_size))
        real_fchmod(fd, mode)

    # Path.chmod calls os.chmod with follow_symlinks.
    def watched_chmod(file: FilePath, mode: int, *, follow_symlinks: bool = True) -> None:
        st = pathlib.Path(file).stat(follow_symlinks=follow_symlinks)
        chmods.append((stat.S_IMODE(st.st_mode), st.st_size))
        real_chmod(file, mode, follow_symlinks=follow_symlinks)

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
    case(
        f"each of the three files is opened with O_CREAT and O_EXCL -> O_EXCL {exclusive}",
        ok=len(exclusive) == len(writes) and all(exclusive),
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

    # Under umask 077, os.open alone would drop the group and other bits of mode 0644.
    umask = os.umask(0o077)
    try:
        write_private(root / "shared", b"shared\n", mode=0o644)
    finally:
        os.umask(umask)
    got = oct(mode_of(root / "shared"))
    case(f"under umask 077, a file of mode 0o644 ends with mode 0o644 -> {got}", ok=got == oct(0o644))


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
    for name in ("n" * 255, "é" * 127):
        path = root / name
        message = written(path, b"long\n")
        case(
            f"a name of {len(os.fsencode(name))} bytes is written -> {message[-60:]}",
            ok=message == "written" and path.read_bytes() == b"long\n",
        )
        path.unlink(missing_ok=True)
    before = sorted(p.name for p in root.iterdir())
    try:
        write_private(root / "text", cast("bytes", "not bytes"))
        message = "written"
    except TypeError as e:
        message = f"TypeError: {e}"
    after = sorted(p.name for p in root.iterdir())
    case(
        f"a failure that is no OSError raises it and leaves no file -> {message}, {after}",
        ok=message.startswith("TypeError") and after == before,
    )
    (root / "directory").mkdir()
    for label, path in (
        ("a path in a missing directory", root / "missing" / "f"),
        ("a path that is a directory", root / "directory"),
        ("a path with a NUL character", root / "a\0b"),
    ):
        before = sorted(p.name for p in root.iterdir())
        message = written(path, b"secret 5\n")
        after = sorted(p.name for p in root.iterdir())
        case(
            f"{label} raises HarnessError with the path and leaves no file -> {message!r}, {after}",
            ok=str(path) in message and after == before,
        )
    for given in ("", "/"):
        try:
            write_private(given, b"secret 6\n")
            message = "written"
        except HarnessError as e:
            message = str(e)
        except ValueError as e:
            message = f"ValueError: {e}"
        case(
            f"the path {given!r} names no file and raises HarnessError with the path -> {message!r}",
            ok=message.startswith("cannot write ") and repr(given) in message,
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
