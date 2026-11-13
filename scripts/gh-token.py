#!/usr/bin/env python3
"""gh with the token of the repository's owner: the wrapper that `harness install` puts at
~/.local/bin/gh, ahead of the real gh on the PATH.

    gh <the arguments of gh>

gh reads one token per host, from GH_TOKEN, then GITHUB_TOKEN, then its stored login. This wrapper
finds the owner of the repository that the command acts on, in this order: the value of `-R` or
`--repo` (`OWNER/REPO`, `HOST/OWNER/REPO` or a URL, also as `--repo=…` or `-R…`); GH_REPO; for
`gh api`, the first argument that starts with `repos/`, `orgs/` or `users/`, with or without a
leading `/`, and its next segment; the owner of the remote `origin` of the working directory.

It reads the token store `~/.config/research-harness/forge/github.com/`: the file `<owner>.store`,
the name compared without case, as GitHub compares it, else `default.store`; each file holds the
one line `https://<user>:<token>@github.com` of git's `credential-store`. It sets GH_TOKEN to the
line's password, removes GITHUB_TOKEN, and runs the real gh with the same arguments: the first
`gh` on the PATH whose resolved file is not this script. A host other than github.com in `-R` or
GH_REPO gets no token; an `origin` of another host names no owner. With no token, it removes
GH_TOKEN and GITHUB_TOKEN and sets GH_CONFIG_DIR to a new empty directory, so that gh reads no
stored login either.

It exits 2 with one line on stderr, and runs nothing, on a store file that it cannot read or whose
line holds no password, and when the PATH holds no gh but this script. The standard library only.
"""

import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.parse

STORE = pathlib.Path(".config", "research-harness", "forge", "github.com")
GITHUB = "github.com"
DEFAULT = "default"
SUFFIX = ".store"
# The endpoint of `gh api` that names an owner.
ENDPOINT = re.compile(r"/?(?:repos|orgs|users)/([^/?#]+)")
# The parts of `[HOST/]OWNER/REPO`.
OWNER_REPO = 2
HOST_OWNER_REPO = 3
REFUSED = 2
# The exit status of a program that a signal ends is this plus the signal's number.
SIGNALLED = 128


class RefusedError(Exception):
    """A refusal of the wrapper: one line on stderr, exit status 2."""


def repo_flag(args: list[str]) -> str | None:
    """The value of the first `-R` or `--repo` in `args`, before a `--`, or None."""
    for i, arg in enumerate(args):
        if arg == "--":
            return None
        if arg in ("-R", "--repo"):
            return args[i + 1] if i + 1 < len(args) else None
        if arg.startswith("--repo="):
            return arg.removeprefix("--repo=")
        if arg.startswith("-R"):
            return arg.removeprefix("-R")
    return None


def location(value: str) -> tuple[str, str] | None:
    """The host and owner of a repository written as `OWNER/REPO`, `HOST/OWNER/REPO`, an `https`
    or `ssh` URL, or `git@HOST:OWNER/REPO`; None for another form."""
    if "://" in value:
        url = urllib.parse.urlsplit(value)
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


def owner(args: list[str], env: dict[str, str]) -> tuple[str, str] | None:
    """The host and owner that the command acts on, in the order of the docstring, or None."""
    for value in (repo_flag(args), env.get("GH_REPO") or None):
        if value is not None and (found := location(value)):
            return found
    if args[:1] == ["api"]:
        for arg in args[1:]:
            if found := ENDPOINT.match(arg):
                return GITHUB, found.group(1)
    found = origin()
    return found if found is not None and found[0] == GITHUB else None


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
    password = urllib.parse.urlsplit(line).password
    if not password:
        raise RefusedError(f"{chosen} holds no line https://<user>:<token>@github.com with a token")
    return urllib.parse.unquote(password)


def real_gh(path: str) -> pathlib.Path:
    """The first `gh` on `path` that is an executable file and whose resolved file is not this
    script."""
    me = pathlib.Path(__file__).resolve()
    for entry in path.split(os.pathsep):
        candidate = pathlib.Path(entry or ".", "gh")
        if candidate.is_file() and os.access(candidate, os.X_OK) and candidate.resolve() != me:
            return candidate
    raise RefusedError("no gh on the PATH but this wrapper")


def main(args: list[str]) -> None:
    """Run the real gh with `args` and the token of the owner, and exit with its status."""
    env = dict(os.environ)
    try:
        found = token(pathlib.Path.home(), owner(args, env))
        program = real_gh(env.get("PATH", ""))
    except RefusedError as e:
        print(f"gh-token: {e}", file=sys.stderr)
        sys.exit(REFUSED)
    env.pop("GITHUB_TOKEN", None)
    if found is None:
        env.pop("GH_TOKEN", None)
        env["GH_CONFIG_DIR"] = tempfile.mkdtemp(prefix="gh-token.")
    else:
        env["GH_TOKEN"] = found
    with subprocess.Popen([str(program), *args], env=env) as p:  # no timeout: gh runs as long as its command
        # Ctrl-C reaches gh, in the same process group, which decides; the wrapper waits for its status.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        status = p.wait()
    # A gh that a signal ends exits as a shell reports it, 128 and the signal's number.
    sys.exit(status if status >= 0 else SIGNALLED - status)


if __name__ == "__main__":
    main(sys.argv[1:])
