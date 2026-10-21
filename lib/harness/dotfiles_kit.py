"""Copy the dotfiles kit of the harness into a chezmoi source.

    harness dotfiles-kit [--apply] DEST

`examples/dotfiles/kit.toml` names each file of the kit and its class. A code file of `DEST`
that is missing, or differs from the kit in its bytes or in its execute bit, is a change; a seed
file is a change only when `DEST` lacks it, and a seed file that exists stays as it is. A file of
`DEST` that `kit.toml` does not name is not read. The dry run lists each change and exits 1 when
there is one; `--apply` writes them.

`DEST` is a clone of the chezmoi source, not the source that chezmoi applies: the subcommand
refuses `~/.local/share/chezmoi` and each directory below it, compared as resolved paths, because
a change of the applied source goes through a branch and a merge request. Each file of `kit.toml`
stays inside the resolved `DEST`: a file whose directory resolves outside it, through a symbolic
link, stops the dry run and `--apply` before the first write. A link at a code file's own path
is replaced, not followed.
"""

import os
import pathlib
import stat
import tomllib

from . import REPO, HarnessError, changing, outcome

KIT = REPO / "examples" / "dotfiles"
CLASSES = ("code", "seed")


def applied_source(home):
    """The source directory that chezmoi applies, below `home`."""
    return home / ".local" / "share" / "chezmoi"


def check_dest(dest, home):
    """Refuse a `dest` that is not a directory, or is the applied source or below it."""
    if not dest.is_dir():
        raise HarnessError(f"{dest} is not a directory")
    applied = applied_source(home).resolve()
    resolved = dest.resolve()
    if resolved == applied or applied in resolved.parents:
        raise HarnessError(f"{dest} is the applied chezmoi source {applied}: copy the kit into a clone of it, "
                           "on a branch, and merge it through a merge request")


def read_kit(kit):
    """[(path relative to `kit`, class)] of `kit`/kit.toml; a malformed table, an unknown class or
    a file that the kit lacks is a `HarnessError` that names it."""
    table = kit / "kit.toml"
    try:
        files = tomllib.loads(table.read_bytes().decode()).get("files")
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise HarnessError(f"{table} cannot be read: {e}") from None
    if not isinstance(files, dict):
        raise HarnessError(f"{table} has no [files] table")
    for rel, cls in files.items():
        if cls not in CLASSES:
            raise HarnessError(f"{table} gives {rel} the class {cls!r}, not code or seed")
        if not (kit / rel).is_file():
            raise HarnessError(f"{table} names {rel}, which the harness lacks at {kit / rel}")
    return list(files.items())


def executable(path):
    """Whether the owner may execute `path`: the bit that git records."""
    return bool(path.stat().st_mode & stat.S_IXUSR)


def check_targets(rels, dest):
    """Refuse each path of `rels` below `dest` whose parent directory resolves outside the resolved
    `dest`, through a symbolic link or `..`, or does not resolve, through a loop of links: a read or
    a write there leaves `dest`. A link at the path itself is not followed here."""
    root = pathlib.Path(os.path.realpath(dest))
    for rel in rels:
        target = dest / rel
        parent = pathlib.Path(os.path.realpath(target.parent))
        if any(p.is_symlink() for p in (parent, *parent.parents)):
            raise HarnessError(f"{target}: its directory {target.parent} does not resolve: a loop of symbolic links")
        if parent != root and root not in parent.parents:
            raise HarnessError(f"{target}: its directory {target.parent} resolves to {parent}, outside {root}")


def plan(kit, dest):
    """[(path, class, status)] of each change: `MISSING`, `DIFFERS` or `MODE`. Each file of
    `kit.toml` is checked to stay inside `dest` before the first is compared."""
    entries = read_kit(kit)
    check_targets([rel for rel, _ in entries], dest)
    changes = []
    for rel, cls in entries:
        src, dst = kit / rel, dest / rel
        if not os.path.lexists(dst):
            changes.append((rel, cls, "MISSING"))
        elif cls == "seed":
            continue
        elif dst.is_symlink() or not dst.is_file() or dst.read_bytes() != src.read_bytes():
            changes.append((rel, cls, "DIFFERS"))
        elif executable(dst) != executable(src):
            changes.append((rel, cls, "MODE"))
    return changes


def copy(src, dst):
    """Write the bytes of `src` to `dst` where they differ, then give `dst` the execute bit of
    `src`: set where `dst` is readable, or cleared everywhere. A link at `dst` is replaced, not
    followed."""
    try:
        if dst.is_symlink():
            dst.unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        if not dst.is_file() or dst.read_bytes() != data:
            dst.write_bytes(data)
        mode = stat.S_IMODE(dst.stat().st_mode)
        want = mode | (mode & 0o444) >> 2 if executable(src) else mode & ~0o111
        if want != mode:
            dst.chmod(want)
    except OSError as e:
        raise HarnessError(f"{dst} cannot be written: {e.strerror or e}") from None


def dotfiles_kit(args, kit=KIT, home=None):
    dest = pathlib.Path(args.dest)
    check_dest(dest, pathlib.Path.home() if home is None else home)
    changes = plan(kit, dest)
    width = max((len(rel) for rel, _, _ in changes), default=0)
    for rel, cls, status in changes:
        print(f"{rel:<{width}}  {status}  ({cls})")
        if args.apply:
            copy(kit / rel, dest / rel)
    if not changes:
        print(f"{dest} has the kit of {kit}")
    elif args.apply:
        print(f"\n{len(changes)} file(s) copied into {dest}")
    else:
        print(f"\n{len(changes)} file(s) to copy; harness dotfiles-kit --apply {dest} copies them")
    return outcome(args, len(changes))


def cmd_dotfiles_kit(args):
    return dotfiles_kit(args)


def register(sub):
    p = sub.add_parser("dotfiles-kit", help="copy the dotfiles kit into a chezmoi source",
                       description="Compare the chezmoi source DEST with the dotfiles kit of the harness, "
                                   "examples/dotfiles/kit.toml: list each code file that is missing or differs, "
                                   "and each seed file that is missing; exit 1 when there is one. --apply copies "
                                   "them. A seed file that exists is never written. DEST must be a directory, "
                                   "and not the applied source ~/.local/share/chezmoi.")
    p.add_argument("dest", metavar="DEST", help="the chezmoi source to copy the kit into: a clone, on a branch")
    changing(p, help="copy the files; without it, print the list").set_defaults(run=cmd_dotfiles_kit)


def selftest():
    """The subcommand on a scratch kit and scratch destinations: the list of the dry run, the
    writes of `--apply`, the refusals of `DEST`, and the kit of the harness on an empty source."""
    import argparse
    import contextlib
    import io
    import subprocess
    import sys
    import tempfile

    results = []

    def check(ok, label):
        results.append(ok)
        print(f"{'ok ' if ok else 'BAD'}  dotfiles-kit: {label}")

    def attempt(dest, kit, home, apply=False):
        """(exit status, stdout, the error text or '')."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                code, error = dotfiles_kit(argparse.Namespace(dest=str(dest), apply=apply), kit=kit, home=home), ""
            except HarnessError as e:
                code, error = 2, str(e)
        return code, out.getvalue(), error

    def listed(stdout):
        """The paths that a run lists, the first word of each line that has a status."""
        return {line.split()[0] for line in stdout.splitlines() if line.split()[1:2] in (["MISSING"], ["DIFFERS"], ["MODE"])}

    def tree(root):
        """{path: (bytes, executable)} of each file below `root`."""
        return {str(p.relative_to(root)): (p.read_bytes(), bool(p.stat().st_mode & stat.S_IXUSR))
                for p in sorted(root.rglob("*")) if p.is_file()}

    with tempfile.TemporaryDirectory(prefix="harness-dotfiles-kit-") as tmp:
        tmp = pathlib.Path(tmp)
        home, kit = tmp / "home", tmp / "kit"
        files = {"code/a.sh": b"echo a\n", "code/b": b"b\n", "code/x.sh": b"echo x\n", "seed/data.toml": b"k = 1\n",
                 "seed/new.toml": b"n = 1\n"}
        for rel, data in files.items():
            (kit / rel).parent.mkdir(parents=True, exist_ok=True)
            (kit / rel).write_bytes(data)
        (kit / "code" / "x.sh").chmod(0o755)
        (kit / "not-in-kit").write_text("never copied\n")
        (kit / "kit.toml").write_text('[files]\n"code/a.sh" = "code"\n"code/b" = "code"\n"code/x.sh" = "code"\n'
                                      '"seed/data.toml" = "seed"\n"seed/new.toml" = "seed"\n')
        home.mkdir()

        # An empty source: the dry run lists every file, --apply copies them, and the dry run after
        # it lists nothing.
        dest = tmp / "dest"
        dest.mkdir()
        before = tree(dest)
        code, out, _ = attempt(dest, kit, home)
        check(code == 1 and listed(out) == set(files) and tree(dest) == before,
              f"an empty source: the dry run lists every file of kit.toml and exits 1, writing nothing: "
              f"exit {code}, listed {sorted(listed(out))}")
        code, out, _ = attempt(dest, kit, home, apply=True)
        check(code == 0 and tree(dest) == {k: v for k, v in tree(kit).items() if k in files},
              f"--apply writes each file with its bytes and execute bit, and exits 0: exit {code}")
        code, out, _ = attempt(dest, kit, home)
        check(code == 0 and listed(out) == set(),
              f"the dry run after --apply exits 0 and lists nothing: exit {code}, listed {sorted(listed(out))}")

        # A changed code file, a code file with the other execute bit, a changed seed file, and a
        # file that kit.toml does not name.
        (dest / "code" / "a.sh").write_bytes(b"echo changed\n")
        (dest / "code" / "b").chmod(0o755)
        (dest / "seed" / "data.toml").write_bytes(b"k = 2\n")
        (dest / "mine.txt").write_bytes(b"private\n")
        (dest / "seed" / "new.toml").unlink()
        code, out, _ = attempt(dest, kit, home)
        check(code == 1 and listed(out) == {"code/a.sh", "code/b", "seed/new.toml"},
              f"the dry run lists a changed code file, a code file whose execute bit differs and a missing seed "
              f"file, and not a changed seed file or a file outside kit.toml: exit {code}, listed {sorted(listed(out))}")
        check([line.split()[1] for line in out.splitlines() if line.startswith("code/")] == ["DIFFERS", "MODE"],
              f"the status of a changed code file is DIFFERS, and of one whose execute bit differs MODE: {out!r}")
        code, out, _ = attempt(dest, kit, home, apply=True)
        after = tree(dest)
        check(code == 0 and after["code/a.sh"] == (b"echo a\n", False) and after["code/b"] == (b"b\n", False)
              and after["seed/new.toml"] == (b"n = 1\n", False),
              f"--apply restores the code files and the missing seed file: exit {code}")
        check(after["seed/data.toml"] == (b"k = 2\n", False) and after["mine.txt"] == (b"private\n", False),
              "--apply never writes a seed file that exists, and leaves a file outside kit.toml as it is")
        code, out, _ = attempt(dest, kit, home)
        check(code == 0, f"the dry run after the second --apply exits 0: exit {code}")

        # A code file that is a symbolic link: a change, and --apply replaces the link, not its target.
        outside = tmp / "outside"
        outside.write_bytes(b"echo a\n")
        (dest / "code" / "a.sh").unlink()
        (dest / "code" / "a.sh").symlink_to(outside)
        code, out, _ = attempt(dest, kit, home)
        check(code == 1 and listed(out) == {"code/a.sh"}, f"a code file that is a link is a change: exit {code}")
        code, out, _ = attempt(dest, kit, home, apply=True)
        check(code == 0 and not (dest / "code" / "a.sh").is_symlink() and outside.read_bytes() == b"echo a\n",
              f"--apply replaces the link with the file and leaves the link's target alone: exit {code}")
        # A directory at a code file's path: a change, which --apply cannot write.
        (dest / "code" / "b").unlink()
        (dest / "code" / "b").mkdir()
        code, out, _ = attempt(dest, kit, home)
        check(code == 1 and listed(out) == {"code/b"}, f"a directory at a code file's path is a change: exit {code}")
        code, out, error = attempt(dest, kit, home, apply=True)
        check(code == 2 and "code/b" in error and "\n" not in error,
              f"--apply on a directory at a code file's path exits 2 with one line that names it: {code}, {error!r}")
        (dest / "code" / "b").rmdir()
        (dest / "code" / "b").write_bytes(b"b\n")
        # A seed file that is a link with no target exists: --apply writes neither it nor its target.
        (dest / "seed" / "new.toml").unlink()
        (dest / "seed" / "new.toml").symlink_to(tmp / "nowhere")
        code, out, _ = attempt(dest, kit, home, apply=True)
        check(code == 0 and listed(out) == set() and not (tmp / "nowhere").exists(),
              f"a seed file that is a link with no target is left as it is: exit {code}, listed {sorted(listed(out))}")

        # A directory of DEST that is a symbolic link out of DEST: the dry run and --apply exit 2
        # with one line that names the file, before the first write. The seed directory comes after
        # the code files, so a check made file by file would write the code files first.
        outdir = tmp / "outdir"
        outdir.mkdir()
        (tmp / "pre-x" / "code").mkdir(parents=True)
        (tmp / "deep" / "d").mkdir(parents=True)
        for name, link, to, word in (("out-code", "code", outdir, "code/"),
                                     ("out-seed", "seed", outdir, "seed/"),
                                     ("out-dangling", "code", tmp / "nowhere-dir", "code/"),
                                     ("out-dotdot", "code", "..", "code/"),
                                     ("pre", "code", tmp / "pre-x" / "code", "code/"),
                                     ("out-loop", "code", "code", "code/")):
            d = tmp / name
            d.mkdir()
            (d / link).symlink_to(to)
            for apply in (False, True):
                before = tree(tmp)
                code, out, error = attempt(d, kit, home, apply=apply)
                check(code == 2 and word in error and "\n" not in error and listed(out) == set() and tree(tmp) == before
                      and not (tmp / "nowhere-dir").exists(),
                      f"{'--apply' if apply else 'the dry run'} on {name}, whose {link} links to {to}, exits 2 with one "
                      f"line that names the file and writes nothing: exit {code}, {error!r}, listed {sorted(listed(out))}")
        bad = tmp / "deep" / "kit"
        (bad / "code").mkdir(parents=True)
        (bad / "code" / "b").write_bytes(b"b\n")
        (tmp / "deep" / "escape").write_bytes(b"e\n")
        (bad / "kit.toml").write_text('[files]\n"code/b" = "code"\n"../escape" = "code"\n')
        code, out, error = attempt(tmp / "deep" / "d", bad, home, apply=True)
        check(code == 2 and "escape" in error and not any((tmp / "deep" / "d").iterdir()),
              f"a kit.toml entry with .. out of DEST exits 2 and writes nothing: exit {code}, {error!r}")
        nest = tmp / "nest"
        (nest / "n" / "m").mkdir(parents=True)
        (nest / "n" / "m" / "f").write_bytes(b"f\n")
        (nest / "kit.toml").write_text('[files]\n"n/m/f" = "code"\n')
        d = tmp / "out-nest"
        d.mkdir()
        (d / "n").symlink_to("n")
        code, out, error = attempt(d, nest, home, apply=True)
        check(code == 2 and "n/m/f" in error and "loop" in error and "\n" not in error,
              f"a loop of links two directories above a file exits 2 with one line that names the file: exit {code}, "
              f"{error!r}")
        # A directory that links inside DEST, and a DEST that is itself a link: the files stay inside.
        d = tmp / "inner"
        (d / "real").mkdir(parents=True)
        (d / "code").symlink_to("real")
        code, out, _ = attempt(d, kit, home)
        check(code == 1 and listed(out) == set(files), f"a directory that links inside DEST is no refusal: exit {code}")
        code, out, _ = attempt(d, kit, home, apply=True)
        check(code == 0 and (d / "real" / "a.sh").read_bytes() == b"echo a\n",
              f"--apply writes through a directory that links inside DEST: exit {code}")
        (tmp / "dest-link").symlink_to(dest)
        code, out, error = attempt(tmp / "dest-link", kit, home)
        check(code == 0, f"a DEST that is a link to a directory: the files stay inside its target: exit {code}, {error!r}")

        # The refusals of DEST, each before any write: not a directory, or the applied source by
        # its resolved path.
        applied = applied_source(home)
        (applied / "sub").mkdir(parents=True)
        (tmp / "link").symlink_to(applied)
        (tmp / "file").write_text("x\n")
        for label, target in (("a missing DEST", tmp / "missing"), ("a DEST that is a file", tmp / "file"),
                              ("the applied source", applied), ("a directory below the applied source", applied / "sub"),
                              ("a link to the applied source", tmp / "link"),
                              ("the applied source through ..", applied / "sub" / ".."),
                              ("the applied source as a relative path", os.path.relpath(applied))):
            for apply in (False, True):
                before = tree(tmp)
                code, out, error = attempt(target, kit, home, apply=apply)
                check(code == 2 and error and "\n" not in error and tree(tmp) == before,
                      f"{'--apply' if apply else 'the dry run'} on {label} exits 2 with one line and writes nothing: "
                      f"exit {code}, {error!r}")
        (tmp / "home-link").symlink_to(home)
        code, out, error = attempt(applied, kit, tmp / "home-link")
        check(code == 2, f"the applied source, with a home directory that is a link, exits 2: exit {code}, {error!r}")
        code, out, error = attempt(applied, kit, home)
        check(code == 2 and "applied" in error and "merge request" in error,
              f"the refusal of the applied source says why: {error!r}")
        other = tmp / "chezmoi"
        other.mkdir()
        code, out, error = attempt(other, kit, home)
        check(code == 1, f"a source named chezmoi elsewhere is not the applied source: exit {code}, {error!r}")

        # A kit.toml that names a file the kit lacks, or that cannot be read as the table of the kit.
        for label, table, word in (("a file that the kit lacks", b'[files]\n"code/gone" = "code"\n', "code/gone"),
                                   ("an unknown class", b'[files]\n"code/b" = "other"\n', "other"),
                                   ("no [files] table", b'x = 1\n', "[files]"),
                                   ("not TOML", b'[files\n', "cannot be read"),
                                   ("not UTF-8", b'[files]\n# \xff\n', "cannot be read")):
            bad = tmp / "bad"
            bad.mkdir(exist_ok=True)
            (bad / "code").mkdir(exist_ok=True)
            (bad / "code" / "b").write_bytes(b"b\n")
            (bad / "kit.toml").write_bytes(table)
            code, out, error = attempt(dest, bad, home)
            check(code == 2 and word in error and "\n" not in error,
                  f"a kit.toml with {label} exits 2 with one line that names it: exit {code}, {error!r}")
        (tmp / "bad" / "kit.toml").unlink()
        code, out, error = attempt(dest, tmp / "bad", home)
        check(code == 2 and "kit.toml" in error and "\n" not in error,
              f"a kit with no kit.toml exits 2 with one line that names it: exit {code}, {error!r}")

        # The kit of the harness, through the command: every file of kit.toml, on an empty source.
        empty = tmp / "empty"
        empty.mkdir()
        env = {**os.environ, "HOME": str(home)}
        p = subprocess.run([sys.executable, str(REPO / "bin" / "harness"), "dotfiles-kit", str(empty)],
                           capture_output=True, text=True, env=env)
        names = set(tomllib.loads((KIT / "kit.toml").read_text())["files"])
        check(p.returncode == 1 and listed(p.stdout) == names and not any(empty.iterdir()),
              f"harness dotfiles-kit on an empty source lists the {len(names)} files of the harness's kit.toml and "
              f"exits 1: exit {p.returncode}, listed {len(listed(p.stdout))}, {p.stderr.strip()[-300:]!r}")
    return len(results), results.count(False)
