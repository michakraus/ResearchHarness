#!/usr/bin/env python3
"""gh with the token of the repository's owner: the wrapper that `harness install` puts at
~/.local/bin/gh, which the command gh runs where ~/.local/bin comes before the real gh on the PATH.

    gh <the arguments of gh>

gh reads one token per host, from GH_TOKEN, then GITHUB_TOKEN, then its stored login. This wrapper
finds the owner of the repository that the command acts on, in this order:

1. the command's own argument. For `gh api`, the first argument that starts with `repos/`, `orgs/`
   or `users/`, with or without a leading `/`, names the next segment, where that is an owner's
   name (letters, digits and `-`, not starting with `-`), so a placeholder `{owner}` or `:owner`
   names none. For any other command, the argument after the group and the command, as in
   `gh pr view <argument>`, where it does not start with `-`: a URL names its host and its first
   path segment, and, for the group `repo` only, `OWNER/REPO` and `HOST/OWNER/REPO` name an owner
   (elsewhere `OWNER/x` can be a branch);
2. the value of the last `-R` or `--repo` before a `--` whose reading is certain (`OWNER/REPO`,
   `HOST/OWNER/REPO` or a URL): `-R V` and `--repo V`, where a bare `-R` or `--repo` is always the
   flag, and `-RV`, `-R=V` and `--repo=V`, where the argument before is not a flag without `=`;
3. GH_REPO;
4. the owner of the remote `origin` of the working directory.

The wrapper does not know which of gh's flags take a value, so it does not read `-R` from any other
argument that gh may read as `-R`: `-RV`, `-R=V` or `--repo=V` after a flag without `=` (the value
of `-b` in `-b -RV`), a cluster of letters with an `R` after its first letter (`-nR V`, `-nRV`, or
`-tRelease`, the title `Release`), and every form after the first `--`. Where the command's own
argument names no owner and such an argument after the last certain `-R` names a repository of
another host or owner than the one the wrapper finds, compared without case, it refuses. Such an
argument whose value names no repository, as `elease` of `-tRelease`, counts for nothing: gh
would refuse that value as `-R`'s.

It reads the token store `~/.config/research-harness/forge/github.com/`: the file `<owner>.store`,
the name compared without case, as GitHub compares it, else `default.store`; each file holds the
one line `https://<user>:<token>@github.com` of git's `credential-store`. It sets GH_TOKEN to the
line's password, removes GITHUB_TOKEN, and runs the real gh with the same arguments: the first
`gh` on the PATH that is an executable file, whose resolved file is not this script, and whose
bytes are not this script's, so that a second copy of the wrapper is skipped too. It exits with
gh's status, 128 and the signal's number where a signal ends gh; a Ctrl-C goes to gh, and the
wrapper waits for it.

A host other than github.com gets no token: in `--hostname` (any command, any argument, also after
a `--`), in a non-empty GH_HOST, in the command's own argument, in `-R` or in GH_REPO; an `origin`
of another host names no owner. With no token, it removes GH_TOKEN and GITHUB_TOKEN and sets
GH_CONFIG_DIR to a new empty directory, so that gh reads no stored login either, and removes that
directory when gh ends. With a token, the caller's GH_CONFIG_DIR stays. A host other than
github.com in `--hostname` or GH_HOST comes first: then the wrapper reads no owner and refuses
nothing.

It exits 2 with one line on stderr, and runs nothing, on the refusal above, on a store file that it
cannot read or whose line holds no password, and when the PATH holds no gh but this script. The
standard library only, and Python 3.9 or later, the python3 of macOS.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass

STORE = pathlib.Path(".config", "research-harness", "forge", "github.com")
GITHUB = "github.com"
DEFAULT = "default"
SUFFIX = ".store"
# The endpoint of `gh api` that names an owner, and an owner's name.
ENDPOINT = re.compile(r"/?(?:repos|orgs|users)/([^/?#]*)")
OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")
# The place of the command's own argument: after the group and the command, `gh pr view <arg>`.
ARGUMENT = 2
# The parts of `[HOST/]OWNER/REPO`.
OWNER_REPO = 2
HOST_OWNER_REPO = 3
REFUSED = 2
# The exit status of a program that a signal ends is this plus the signal's number.
SIGNALLED = 128


class RefusedError(Exception):
    """A refusal of the wrapper: one line on stderr, exit status 2."""


@dataclass(frozen=True)
class Reading:
    """A value that gh may read as the repository of `-R`: the argument at `index` that carries it,
    as `shown` on stderr, and whether the reading is certain."""

    index: int
    shown: str
    value: str
    certain: bool


def takes_next(arg: str) -> bool:
    """Whether `arg` is a flag token without `=`, which may take the next argument as its value."""
    return arg.startswith("-") and len(arg) > 1 and "=" not in arg


def readings(args: list[str]) -> list[Reading]:
    """Every value in `args` that gh may read as `-R`'s, in order. Certain, before the first `--`:
    `-R V` and `--repo V`, where a bare `-R` or `--repo` is always the flag and V is its value
    only, and `-RV`, `-R=V` and `--repo=V`, where the argument before is not a flag token without
    `=`. Uncertain: those attached forms after such a flag token; each `R` of a short cluster
    that has only letters before it, at least one, with the rest of the argument, less one
    leading `=`, as the value, or the next argument where `R` is last; and every form after the
    first `--`."""
    found: list[Reading] = []
    after_dashes = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            after_dashes = True
        elif arg in ("-R", "--repo"):
            if i + 1 < len(args):
                found.append(Reading(i, f"{arg} {args[i + 1]}", args[i + 1], not after_dashes))
            i += 1
        elif arg.startswith(("-R", "--repo=")):
            value = arg.removeprefix("--repo=") if arg.startswith("--") else arg[2:].removeprefix("=")
            certain = not after_dashes and not (i > 0 and takes_next(args[i - 1]))
            found.append(Reading(i, arg, value, certain))
        elif arg.startswith("-") and not arg.startswith("--"):
            for at in range(2, len(arg)):
                if arg[at] == "R" and arg[1:at].isalpha():
                    if at < len(arg) - 1:
                        found.append(Reading(i, arg, arg[at + 1 :].removeprefix("="), certain=False))
                    elif i + 1 < len(args):
                        found.append(Reading(i, f"{arg} {args[i + 1]}", args[i + 1], certain=False))
        i += 1
    return found


def url_location(value: str) -> tuple[str, str] | None:
    """The host, in lower case, and the first path segment of the URL `value`, or None, also where
    `value` is no URL that urllib can split, as `https://[x/y`."""
    try:
        url = urllib.parse.urlsplit(value)
    except ValueError:
        return None
    first = url.path.strip("/").split("/")[0]
    return (url.hostname, first) if url.hostname and first else None


def location(value: str) -> tuple[str, str] | None:
    """The host and owner of a repository written as `OWNER/REPO`, `HOST/OWNER/REPO`, an `https`
    or `ssh` URL, or `git@HOST:OWNER/REPO`; None for another form, and for a URL that urllib cannot
    split, as `https://[x/y`."""
    if "://" in value:
        try:
            url = urllib.parse.urlsplit(value)
        except ValueError:
            return None
        host, path = url.hostname or "", url.path.strip("/")
        parts = path.split("/")
        return (host, parts[0]) if host and len(parts) >= OWNER_REPO and parts[0] else None
    if found := re.fullmatch(r"[^@/]+@([^:/]+):([^/]+)/.+", value):
        return found.group(1).lower(), found.group(2)
    parts = value.split("/")
    if len(parts) == OWNER_REPO and all(parts):
        return GITHUB, parts[0]
    if len(parts) == HOST_OWNER_REPO and all(parts):
        return parts[0].lower(), parts[1]
    return None


def argument(args: list[str]) -> tuple[str, str] | None:
    """The host and owner that the command's own argument names, as the docstring of this script
    describes it, or None."""
    if args[:1] == ["api"]:
        for arg in args[1 : args.index("--") if "--" in args else len(args)]:
            if found := ENDPOINT.match(arg):
                return (GITHUB, found.group(1)) if OWNER.fullmatch(found.group(1)) else None
        return None
    if len(args) <= ARGUMENT or args[ARGUMENT].startswith("-"):
        return None
    value = args[ARGUMENT]
    if "://" in value:
        return url_location(value)
    return location(value) if args[0] == "repo" else None


def origin() -> tuple[str, str] | None:
    """The host and owner of the remote `origin` of the working directory, or None where git
    gives none."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        p = subprocess.run(
            [git, "remote", "get-url", "origin"], capture_output=True, text=True, timeout=30, check=False
        )
    except subprocess.TimeoutExpired:
        return None
    return location(p.stdout.strip()) if p.returncode == 0 else None


def lower(found: tuple[str, str] | None) -> tuple[str, str] | None:
    """The host and owner `found`, the owner in lower case, as GitHub compares it; `location`
    gives the host in lower case already."""
    return None if found is None else (found[0], found[1].lower())


def owner(args: list[str], env: dict[str, str]) -> tuple[str, str] | None:
    """The host and owner that the command acts on, in the order of the docstring, or None.
    Raises RefusedError where an uncertain reading of `-R` after the last certain one names
    another host or owner."""
    if found := argument(args):
        return found
    every = readings(args)
    certain = [r for r in every if r.certain]
    last = certain[-1].index if certain else -1
    found = None
    for value in (*(r.value for r in certain[-1:]), env.get("GH_REPO") or None):
        if value is not None and (found := location(value)):
            break
    if found is None:
        found = origin()
        found = found if found is not None and found[0] == GITHUB else None
    # Every reading after the last certain one is uncertain. gh would refuse a value that names no
    # repository as -R's, so such a reading counts for nothing.
    for r in every:
        named = location(r.value)
        if r.index > last and named is not None and lower(named) != lower(found):
            mine = f"chooses the token by {'/'.join(found)}" if found is not None else "finds no owner"
            raise RefusedError(
                f"{r.shown} may name the repository of {'/'.join(named)}, while this wrapper {mine}; "
                "give the repository as -R OWNER/REPO, a flag of its own before any --"
            )
    return found


def other_host(args: list[str], env: dict[str, str]) -> bool:
    """Whether `--hostname V` or `--hostname=V` in any argument, `--` included, or a non-empty
    GH_HOST names a host other than github.com."""
    hosts = [args[i + 1] for i in range(len(args) - 1) if args[i] == "--hostname"]
    hosts += [a.removeprefix("--hostname=") for a in args if a.startswith("--hostname=")]
    hosts += [env["GH_HOST"]] if env.get("GH_HOST") else []
    return any(h.lower() != GITHUB for h in hosts)


def token(home: pathlib.Path, found: tuple[str, str] | None) -> str | None:
    """The token of the store file of `found`'s owner, or of `default.store`, or None: none for a
    host other than github.com, and none where neither file exists."""
    if found is not None and found[0] != GITHUB:
        return None
    store = home / STORE
    files = sorted(store.glob(f"*{SUFFIX}")) if store.is_dir() else []
    name = found[1].lower() if found is not None else None
    mine = [p for p in files if name is not None and p.name.removesuffix(SUFFIX).lower() == name]
    default = [p for p in files if p.name == DEFAULT + SUFFIX]
    chosen = (mine or default or [None])[0]
    if chosen is None:
        return None
    try:
        line = chosen.read_text().strip()
    except (OSError, UnicodeDecodeError) as e:
        raise RefusedError(f"{chosen} cannot be read: {e.__class__.__name__}") from None
    refused = RefusedError(f"{chosen} holds no line https://<user>:<token>@github.com with a token")
    try:
        password = urllib.parse.urlsplit(line).password
    except ValueError:
        raise refused from None
    if not password:
        raise refused
    return urllib.parse.unquote(password)


def is_wrapper(candidate: pathlib.Path, me: pathlib.Path) -> bool:
    """Whether `candidate` is this script, by its resolved file or by its bytes."""
    if candidate.resolve() == me:
        return True
    # The size first, so that the real gh, a file of another size, is not read.
    return candidate.stat().st_size == me.stat().st_size and candidate.read_bytes() == me.read_bytes()


def real_gh(path: str) -> pathlib.Path:
    """The first `gh` on `path` that is an executable file and not this script."""
    me = pathlib.Path(__file__).resolve()
    for entry in path.split(os.pathsep):
        candidate = pathlib.Path(entry or ".", "gh")
        if candidate.is_file() and os.access(candidate, os.X_OK) and not is_wrapper(candidate, me):
            return candidate
    raise RefusedError("no gh on the PATH but this wrapper")


def run(program: pathlib.Path, args: list[str], env: dict[str, str]) -> int:
    """The exit status of `program` with `args` and `env`, as a shell reports it."""
    with subprocess.Popen([str(program), *args], env=env) as p:  # no timeout: gh runs as long as its command
        # Ctrl-C reaches gh, in the same process group, which decides; the wrapper waits for its status.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        status = p.wait()
    # A gh that a signal ends exits as a shell reports it, 128 and the signal's number.
    return status if status >= 0 else SIGNALLED - status


def main(args: list[str]) -> None:
    """Run the real gh with `args` and the token of the owner, and exit with its status."""
    env = dict(os.environ)
    try:
        found = None if other_host(args, env) else token(pathlib.Path.home(), owner(args, env))
        program = real_gh(env.get("PATH", ""))
    except RefusedError as e:
        print(f"gh-token: {e}", file=sys.stderr)
        sys.exit(REFUSED)
    env.pop("GITHUB_TOKEN", None)
    if found is not None:
        env["GH_TOKEN"] = found
        sys.exit(run(program, args, env))
    env.pop("GH_TOKEN", None)
    with tempfile.TemporaryDirectory(prefix="gh-token.") as config:
        env["GH_CONFIG_DIR"] = config
        status = run(program, args, env)
    sys.exit(status)


if __name__ == "__main__":
    main(sys.argv[1:])
