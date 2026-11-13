"""The git configuration of the forge token store, which `harness install` renders.

The token store `~/.config/research-harness/forge/<host>/<name>.store` holds one token per file,
mode 600, in the format of git's `credential-store`: one line `https://<user>:<token>@<host>`.
`<name>` is an owner of the host, a GitHub account or organisation or a GitLab group, or `default`
for every other owner of the host. The owners are the file names, so the harness names none.

`render(store)` gives the git configuration of the store at `store`. Per host directory, in the
order of the names: a section `[credential "https://<host>"]` with an empty `helper`, which clears
every helper before it, and, where `default.store` exists, the get-only helper of that file; then,
for each other `<name>.store`, a section `[credential "https://<host>/<name>"]` with an empty
`helper` and the get-only helper of that file. Then, when the directory `github.com` exists,
`[credential "https://gist.github.com"]` with an empty `helper` only, so that no token reaches a
gist. git applies the helpers of every section whose URL matches, in the order of the
configuration, and matches the path by whole components and with case; so each owner gets its own
token and every other owner of the host the default's, or none. The get-only helper,
`!f() { test "$1" = get && exec git credential-store --file <file> get; }; f`, answers `get` from
the file and never writes it: a plain `store --file` erases the file's line on a `reject`, as
after a token that expired.

`render` exits 2, with one line that names the path, on a host directory whose name is no host
name, a `<name>` outside `[A-Za-z0-9-]+` or starting with `-`, a store file, after symbolic links,
that the group or others can read (the line names its mode), and a store file whose text is not
the one line `https://<user>:<token>@<host>` with `<host>` its directory's name. It names no token.

`plan_files(home)` plans the rendered file at `~/.config/research-harness/forge.gitconfig`, mode
600, beside the store and not inside it: git exits fatal on an `include` that it cannot read, and
the store is a read deny of Claude Code's sandbox. Without the store directory it plans nothing.
`notice(home)` is the one line that `harness install` prints when the store exists and
`~/.gitconfig` holds no `include.path` of the rendered file.

The module has no subcommand; its cases run in `harness test`.
"""

import os
import pathlib
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable

from . import HarnessError, fsutil, install_cases

# The token store and the rendered file, relative to the home directory.
STORE = pathlib.PurePosixPath(".config", "research-harness", "forge")
RENDERED = pathlib.PurePosixPath(".config", "research-harness", "forge.gitconfig")
RENDERED_MODE = 0o600
# The store file of every owner without a file of its own.
DEFAULT = "default"
SUFFIX = ".store"
GITHUB = "github.com"
GIST = "gist.github.com"
# An owner's name: letters, digits and `-`, not starting with `-`.
OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")
# A host name: labels of letters, digits and `-`, joined by dots.
HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)*")
# The one line of a store file; the host is compared with the directory's name.
LINE = re.compile(r"https://[^:/@\s]+:[^:/@\s]+@([^/@\s]+)\n?")
# The bits of a store file's mode that let the group or others read it.
READABLE = stat.S_IRGRP | stat.S_IROTH
GIT = shutil.which("git") or "git"


def render(store: pathlib.Path) -> str:
    """The git configuration of the token store at `store`, as the docstring of this module
    describes it; exits 2 on a file or a directory that it refuses."""
    lines = [
        "# The credential helpers of the forge token store, rendered by `harness install`. Include",
        "# this file after the credential lines of ~/.gitconfig.",
    ]
    hosts = sorted(p for p in store.iterdir() if p.is_dir())
    for directory in hosts:
        if not HOST.fullmatch(directory.name):
            raise HarnessError(f"{directory} is a directory of the token store whose name is no host name")
        files = {p.name.removesuffix(SUFFIX): checked(p) for p in sorted(directory.glob(f"*{SUFFIX}"))}
        lines += section(f"https://{directory.name}", files.get(DEFAULT))
        lines += [
            line
            for name, path in files.items()
            if name != DEFAULT
            for line in section(f"https://{directory.name}/{name}", path)
        ]
    if store / GITHUB in hosts:
        lines += section(f"https://{GIST}", None)
    return "".join(f"{line}\n" for line in lines)


def checked(path: pathlib.Path) -> pathlib.Path:
    """`path`, a store file whose name, mode and line `render` accepts; exits 2 otherwise, with one
    line that names the file, and its mode where that is the cause."""
    name = path.name.removesuffix(SUFFIX)
    if not OWNER.fullmatch(name):
        raise HarnessError(
            f"{path}: {name!r} is no owner's name, which holds letters, digits and -, and starts with no -"
        )
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as e:
        raise HarnessError(f"{path} cannot be read: {e.strerror}") from None
    if mode & READABLE:
        raise HarnessError(
            f"{path} has mode {mode:03o}: the group or others can read its token; chmod 600 it"
        )
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError) as e:
        raise HarnessError(f"{path} cannot be read: {e.__class__.__name__}") from None
    found = LINE.fullmatch(text)
    if found is None or found.group(1) != path.parent.name:
        raise HarnessError(
            f"{path} does not hold the one line https://<user>:<token>@{path.parent.name} of its directory"
        )
    return path


def section(url: str, path: pathlib.Path | None) -> list[str]:
    """The lines of the section of `url`: the empty `helper`, then the get-only helper of the store
    file `path` where it is given."""
    lines = [f'[credential "{url}"]', "\thelper ="]
    if path is not None:
        helper = (
            f'!f() {{ test "$1" = get && exec git credential-store --file {shlex.quote(str(path))} get; }}; f'
        )
        # A value of a git configuration file escapes \ and " inside its double quotes.
        quoted = helper.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'\thelper = "{quoted}"')
    return lines


def plan_files(home: pathlib.Path) -> list[tuple[pathlib.Path, bytes, int | None, str]]:
    """The rendered file of the token store below `home`, [(destination, bytes, mode, label)], or
    [] where the store directory does not exist."""
    store = home / STORE
    if not store.is_dir():
        return []
    return [(home / RENDERED, render(store).encode(), RENDERED_MODE, f"~/{RENDERED}")]


def notice(home: pathlib.Path) -> str | None:
    """The notice line when the token store below `home` exists and `~/.gitconfig` holds no
    `include.path` of the rendered file, else None. git reads the paths, with `~` expanded; a
    relative path is relative to the home directory, as git reads it in ~/.gitconfig."""
    if not (home / STORE).is_dir():
        return None
    p = subprocess.run(
        [GIT, "config", "--file", str(home / ".gitconfig"), "--path", "--get-all", "include.path"],
        capture_output=True,
        text=True,
        # No `GIT_*` variable of the caller: a `GIT_DIR` that a git hook exports names another repository.
        env={**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")}, "HOME": str(home)},
        timeout=60,
        check=False,
    )
    included = [home / line for line in p.stdout.splitlines()] if p.returncode == 0 else []
    if home / RENDERED in included:
        return None
    return (
        f"NOTICE: ~/.gitconfig does not include ~/{RENDERED}, so git uses none of the forge tokens; add "
        f"`[include] path = ~/{RENDERED}` after its credential lines"
    )


# ---------------------------------------------------------------------------------------------
# The cases of `harness test`

Check = Callable[[object, str], None]
# The exit status of `harness install` on a refusal.
REFUSED = 2
# A credential helper before the rendered file that answers every URL: a section that does not
# clear it lets it through.
GENERIC = "GENERIC"
GENERIC_HELPER = f'[credential]\n\thelper = "!f() {{ echo username=u; echo password={GENERIC}; }}; f"\n'


def fake_token(name: str) -> str:
    """A token for the cases, made at run time, so that no token-shaped literal is in the tree."""
    return f"T-{name}-{secrets.token_hex(4)}"


def store_file(store: pathlib.Path, host: str, name: str, token: str, mode: int = 0o600) -> pathlib.Path:
    """`<store>/<host>/<name>.store` with the line of `token` for `host`, and mode `mode`."""
    user = "oauth2" if host != GITHUB else "x-access-token"
    path = store / host / f"{name}{SUFFIX}"
    path.parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_private(path, f"https://{user}:{token}@{host}\n".encode(), mode)
    return path


class Git:
    """`git credential` with the configuration `GENERIC_HELPER` and an include of the rendered
    file of `store`, in a scratch home below `root`, reading none of the user's configuration."""

    def __init__(self, root: pathlib.Path, store: pathlib.Path):
        self.home = root / "home"
        self.home.mkdir(parents=True)
        self.rendered = root / "forge.gitconfig"
        self.text = render(store)
        self.rendered.write_text(self.text)
        self.config = root / "config"
        self.config.write_text(f"{GENERIC_HELPER}[include]\n\tpath = {self.rendered}\n")

    def run(self, action: str, given: str) -> subprocess.CompletedProcess[str]:
        """`git credential <action>` with `given` on stdin."""
        return subprocess.run(
            [GIT, "credential", action],
            input=given,
            capture_output=True,
            text=True,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(self.home),
                "GIT_CONFIG_GLOBAL": str(self.config),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
            },
            timeout=60,
            check=False,
        )

    def fill(self, url: str) -> str | None:
        """The password that `git credential fill` gives for `url`, or None where it gives none."""
        p = self.run("fill", f"url={url}\n\n")
        found = [line[len("password=") :] for line in p.stdout.splitlines() if line.startswith("password=")]
        return found[0] if p.returncode == 0 and found else None


def fill_cases(check: Check, root: pathlib.Path) -> None:
    """`render` on a store with an owner, a default and a GitLab group, with `GENERIC_HELPER`
    before it: each URL's password, a `reject` that keeps the owner's file, and a store without a
    default."""
    store = root / "store"
    tokens = {name: fake_token(name) for name in ("Example-A", DEFAULT, "group-a")}
    owner = store_file(store, GITHUB, "Example-A", tokens["Example-A"])
    store_file(store, GITHUB, DEFAULT, tokens[DEFAULT])
    store_file(store, "gitlab.example.org", "group-a", tokens["group-a"])
    git = Git(root / "full", store)
    for url, want, label in [
        (
            "https://github.com/Example-A/repo.git",
            tokens["Example-A"],
            "the owner of a store file gets its token",
        ),
        (
            "https://github.com/stranger/repo.git",
            tokens[DEFAULT],
            "an owner without a file gets the default's",
        ),
        ("https://gist.github.com/x.git", None, "a gist URL gets no password"),
        (
            "https://gitlab.example.org/group-a/sub/repo.git",
            tokens["group-a"],
            "a project below the GitLab group of a store file gets the group's token",
        ),
        ("https://gitlab.example.org/other/repo.git", None, "another group of that host gets no password"),
    ]:
        got = git.fill(url)
        check(got == want, f"{label}: {url} -> {got == want}")
    before = owner.read_bytes()
    p = git.run(
        "reject",
        "protocol=https\nhost=github.com\npath=Example-A/repo.git\nusername=x-access-token\n"
        f"password={tokens['Example-A']}\n\n",
    )
    check(
        p.returncode == 0 and owner.read_bytes() == before,
        f"a reject for Example-A keeps the line of Example-A.store: {p.returncode}, "
        f"{owner.read_bytes() == before}",
    )

    lone = root / "lone"
    store_file(lone, GITHUB, "Example-A", tokens["Example-A"])
    git = Git(root / "no-default", lone)
    got = git.fill("https://github.com/stranger/repo.git")
    host = '[credential "https://github.com"]\n\thelper =\n['
    check(
        got is None and host in git.text,
        f"without default.store, an owner without a file gets no password, and the host's section holds "
        f"only the reset: {got is None}, {host in git.text}",
    )
    check(
        git.fill("https://github.com/Example-A/repo.git") == tokens["Example-A"],
        "without default.store, the owner of a store file still gets its token",
    )


class Install:
    """`harness install --apply` on scratch HOMEs below `root` whose profile chooses claude."""

    def __init__(self, check: Check, root: pathlib.Path):
        self.scratch = install_cases.Scratch(check, root)
        self.scratch.tmp.mkdir(parents=True)

    def fresh(self) -> tuple[pathlib.Path, pathlib.Path]:
        """A fresh scratch base and its home's token store directory, which does not exist yet."""
        base = self.scratch.fresh()[0]
        profile = base / "profile.toml"
        text = profile.read_text()
        head = text[: text.index("\n[setup]\n")]
        profile.write_text(f'{head}\n[setup]\nfrontends = ["claude"]\ncomponents = ["julia"]\n')
        return base, base / "home" / STORE

    @staticmethod
    def apply(base: pathlib.Path) -> tuple[int | None, str]:
        """`harness install --apply` on `base`."""
        return install_cases.Scratch.run(base, "--apply")


def install_refusal_cases(check: Check, root: pathlib.Path) -> None:
    """`harness install --apply` with a store file that the group or others can read, one named
    `-x.store`, one whose line names another host, and one in a host directory whose name is no
    host name: each exits 2, names the file and writes nothing. With a valid store and a
    `~/.gitconfig` without the include, the notice and the rendered file; with the include, no
    notice."""
    installs = Install(check, root)
    token = fake_token("a")

    def readable(store: pathlib.Path) -> pathlib.Path:
        return store_file(store, GITHUB, "Example-A", token, 0o644)

    def dashed(store: pathlib.Path) -> pathlib.Path:
        return store_file(store, GITHUB, "-x", token)

    def other_host(store: pathlib.Path) -> pathlib.Path:
        path = store_file(store, GITHUB, "Example-A", token)
        fsutil.write_private(path, f"https://x-access-token:{token}@github.example.org\n".encode())
        return path

    def bad_host(store: pathlib.Path) -> pathlib.Path:
        store_file(store, "bad host", "Example-A", token)
        return store / "bad host"

    for label, make, words in [
        ("a store file of mode 644", readable, ["644"]),
        ("a store file named -x.store", dashed, []),
        ("a store file whose line names another host", other_host, []),
        ("a host directory whose name is no host name", bad_host, []),
    ]:
        base, store = installs.fresh()
        named = make(store)
        code, out = installs.apply(base)
        written = [
            p for p in (base / "home" / RENDERED, base / "home" / ".claude" / "settings.json") if p.exists()
        ]
        check(
            code == REFUSED
            and "Traceback" not in out
            and str(named) in out
            and all(w in out for w in words)
            and token not in out
            and not written,
            f"{label}: the install exits 2, names the file{' and its mode' if words else ''}, names no "
            f"token and writes nothing: {code}, {out.strip().splitlines()[-1:]}, {written}",
        )

    base, store = installs.fresh()
    store_file(store, GITHUB, DEFAULT, token)
    code, out = installs.apply(base)
    rendered = base / "home" / RENDERED
    lines = [line for line in out.splitlines() if "forge.gitconfig" in line and "does not include" in line]
    check(
        code == 0
        and len(lines) == 1
        and rendered.is_file()
        and rendered.read_text() == render(store)
        and stat.S_IMODE(rendered.stat().st_mode) == RENDERED_MODE,
        f"a valid store and a ~/.gitconfig without the include: exit 0, one notice line, and the "
        f"rendered file of mode 600: {code}, {lines}, {rendered.is_file()}",
    )
    (base / "home" / ".gitconfig").write_text(
        "[include]\n\tpath = ~/.config/research-harness/forge.gitconfig\n"
    )
    code, out = installs.apply(base)
    check(
        code == 0 and "does not include" not in out,
        f"with the include in ~/.gitconfig, no notice: {code}",
    )
    base = installs.fresh()[0]
    code, out = installs.apply(base)
    check(
        code == 0 and "does not include" not in out and not (base / "home" / RENDERED).exists(),
        f"without the store directory, no rendered file and no notice: {code}",
    )


def selftest() -> tuple[int, int]:
    """`render` with `git credential` on scratch stores, and `harness install` on scratch HOMEs:
    (cases, wrong)."""
    n = wrong = 0

    def check(ok: object, label: str) -> None:
        nonlocal n, wrong
        n += 1
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  forge: {label}")

    with tempfile.TemporaryDirectory(prefix="harness-forge-") as tmp:
        root = pathlib.Path(tmp)
        fill_cases(check, root / "fill")
        install_refusal_cases(check, root / "install")
    return n, wrong
