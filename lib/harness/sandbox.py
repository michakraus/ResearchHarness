"""The `srt` settings of each CLI frontend, rendered from the `sandbox` section of the Claude Code
settings and from sandbox/policy.toml.

`srt` reads one settings file. `harness install` writes one per frontend that the profile's
`[setup]` chooses, `~/.config/research-harness/sandbox/<frontend>.json` (`plan_files`). The
template's `sandbox` section stays the source of the shared lists; the policy file holds only what
`srt` adds: the read limit's `allow` list, and per frontend its `state` paths, its extra
`deny_write` paths, its `own` paths, the template's deny entries that it reads and writes itself,
its `read_files`, files below a read deny directory that it reads and does not write, and its
`network`, the hosts that it reaches itself, in the grammar of `network.frontend_entries`. The
overlay `network.toml` beside the profile adds the user's hosts to a frontend's `network` in a
`[frontend.<name>]` table (`network.py`).

`srt_settings` gives one frontend's object, as docs/src/components/sandbox.md describes:

  network.allowedDomains     the template's, in order; then the frontend's `network`; without
                             each entry of `network` whose host, its `:port` cut off, an entry
                             of `deniedDomains` without a port matches (`network.denies`)
  network.deniedDomains      the template's, or [] where it has none: srt refuses a file without it
  network.allowLocalBinding  the template's
  filesystem.allowWrite      the template's, without each entry at or below another frontend's
                             `state` path; then the frontend's `state`; then `tmpdir`, when given
  filesystem.denyWrite       the template's, without the frontend's `own` and without each
                             literal entry, other than the home directory, strictly above a path
                             of the frontend's `state`; then its `deny_write`
  filesystem.denyRead        the home directory; then the template's; then each path of
                             `credentials.files`; without the frontend's `own`; each literal
                             entry, other than the home directory, strictly above a path of the
                             frontend's `read_files` written as the entry followed by `/*`
  filesystem.allowRead       the policy's `read.allow`; then the frontend's `state`; then its
                             `own`; then its `read_files`
  allowPty                   true, for every frontend: srt then allows pseudo-terminals, which a
                             frontend's terminal user interface needs (macOS only)

Every `~` and `~/` prefix becomes the home directory, a list holds no entry twice, and the first
occurrence keeps its place. "At or below" compares whole path components. A `read_files` path
that is itself an entry of `denyRead`, compared as a path, exits 2. srt lets a file allow pierce
a glob read deny, and not a literal one inside a read allow; it reads `D/**` as the literal `D`,
so the glob is `D/*`. A glob entry, one that holds `*`, `?`, `[` or `]`, stays as it is.

`plan_files` gives `srt_settings` each frontend's `network` as the policy's list followed by the
overlay's `[frontend.<name>]` table, and exits 2 on an entry of any frontend, of either source,
whose host matches by `network.denies` a `fetch` host that no `deny` entry without a port
removes, because a command of that frontend would reach the host.

With at least one frontend chosen, `plan_files` also plans the launcher sandbox/agentbox at
`~/.local/bin/agentbox`, mode 755, which starts a frontend under `srt` with its file, and, with
`claude` chosen, Claude Code's override `claude-inner-off.json` in the same directory as the
files, which the launcher passes to Claude Code to turn its own sandbox off.

The module has no subcommand; its cases run in `harness test`.
"""

import copy
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import tempfile
import tomllib
import types
from collections.abc import Callable, Mapping, Sequence
from dataclasses import FrozenInstanceError, dataclass, replace
from typing import Any, cast
from unittest import mock

from . import REPO, HarnessError, frontends, install_cases, jsonio, network
from . import profile as profile_module

POLICY = REPO / "sandbox" / "policy.toml"
# The directory of the installed files, relative to the home directory.
DIRECTORY = pathlib.PurePosixPath(".config", "research-harness", "sandbox")
LISTS = ("state", "deny_write", "own", "read_files")
# The characters that make a path entry a glob for srt.
GLOB_CHARS = "*?[]"
# The launcher that starts a CLI frontend under srt, and where the install puts it, relative to the
# home directory: a directory that a session cannot write.
LAUNCHER = REPO / "sandbox" / "agentbox"
LAUNCHER_PATH = pathlib.PurePosixPath(".local", "bin", "agentbox")
LAUNCHER_MODE = 0o755
# Claude Code's settings file for `--settings` under the launcher: its own sandbox fails inside
# srt's, so it is off.
INNER_OFF_NAME = "claude-inner-off.json"
INNER_OFF = b'{"sandbox": {"enabled": false}}\n'


@dataclass(frozen=True)
class ReadPolicy:
    """The read limit's paths that every frontend reads."""

    allow: tuple[str, ...]


@dataclass(frozen=True)
class FrontendPolicy:
    """One frontend's paths and hosts of the policy file."""

    state: tuple[str, ...]
    deny_write: tuple[str, ...]
    own: tuple[str, ...]
    read_files: tuple[str, ...]
    network: tuple[str, ...]


@dataclass(frozen=True)
class Policy:
    """sandbox/policy.toml: the read limit, and each frontend of FRONTENDS by its name."""

    read: ReadPolicy
    frontends: Mapping[str, FrontendPolicy]


def load_policy(path: pathlib.Path) -> Policy:
    """The policy file at `path`. Exits 2, naming the key or the path, on a file that cannot be
    read or is not TOML, an unknown key, a missing key or frontend, a value that is not a list of
    strings, a path that does not start with `~/`, a path with a `..` segment, and a `network`
    entry outside the grammar of `network.frontend_entries`."""
    try:
        text = path.read_bytes().decode("utf-8")
    except OSError as e:
        raise HarnessError(f"{path} cannot be read: {e.strerror}") from None
    except UnicodeDecodeError:
        raise HarnessError(f"{path} is not UTF-8") from None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise HarnessError(f"{path} is not TOML: {e}") from None
    top = table(path, "", data, ("read", "frontend"))
    read = table(path, "read.", top["read"], ("allow",))
    named = table(path, "frontend.", top["frontend"], frontends.FRONTENDS)
    tables = {
        name: table(path, f"frontend.{name}.", named[name], (*LISTS, "network"))
        for name in frontends.FRONTENDS
    }
    return Policy(
        read=ReadPolicy(allow=paths(path, "read.allow", read["allow"])),
        frontends=types.MappingProxyType(
            {
                name: FrontendPolicy(
                    *(paths(path, f"frontend.{name}.{key}", t[key]) for key in LISTS),
                    network=network.frontend_entries(path, f"frontend.{name}.network", t["network"]),
                )
                for name, t in tables.items()
            }
        ),
    )


def table(path: pathlib.Path, prefix: str, value: object, keys: tuple[str, ...]) -> dict[str, object]:
    """`value`, a table of the policy file at `path` whose keys, each named with `prefix`, are
    exactly `keys`; exits 2 otherwise."""
    if not isinstance(value, dict):
        raise HarnessError(f"{path}: {prefix.rstrip('.')} is not a table")
    found = cast("dict[str, object]", value)
    if unknown := [k for k in found if k not in keys]:
        raise HarnessError(
            f"{path}: no key {prefix}{unknown[0]}; the keys are {', '.join(prefix + k for k in keys)}"
        )
    if missing := [k for k in keys if k not in found]:
        raise HarnessError(f"{path}: no {prefix}{missing[0]}, which the policy holds")
    return found


def paths(path: pathlib.Path, key: str, value: object) -> tuple[str, ...]:
    """`value`, the list `key` of the policy file at `path`, as a tuple; exits 2 unless it is a
    list of strings that each start with `~/` and hold no `..` segment, which could leave the home
    directory."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in cast("list[object]", value)):
        raise HarnessError(f"{path}: {key} is not a list of strings")
    entries = cast("list[str]", value)
    if wrong := [p for p in entries if not p.startswith("~/")]:
        raise HarnessError(f"{path}: {key} entry {wrong[0]!r} does not start with ~/")
    if wrong := [p for p in entries if ".." in p.split("/")]:
        raise HarnessError(f"{path}: {key} entry {wrong[0]!r} holds a .. segment")
    return tuple(entries)


def expand(entry: str, home: pathlib.Path) -> str:
    """`entry` with a `~` or `~/` prefix replaced by `home`; exits 2 on another user's `~name`."""
    if entry == "~" or entry.startswith("~/"):
        return str(home) + entry[1:]
    if entry.startswith("~"):
        raise HarnessError(f"the sandbox path {entry!r} names another user's home directory")
    return entry


def below(path: str, roots: list[str]) -> bool:
    """Whether `path` is at or below one of `roots`, compared by whole path components."""
    return any(pathlib.PurePosixPath(path).is_relative_to(root) for root in roots)


def unique(entries: list[str]) -> list[str]:
    """`entries` without a repeat, each at its first place."""
    return list(dict.fromkeys(entries))


def section(sandbox: Mapping[str, object], name: str) -> dict[str, object]:
    """The object `name` of `sandbox`; exits 2 where `sandbox` has no object of that name."""
    value = sandbox.get(name)
    if not isinstance(value, dict):
        raise HarnessError(f"the sandbox object has no {name} object")
    return cast("dict[str, object]", value)


def strings(
    sandbox: Mapping[str, object], name: str, key: str, default: list[str] | None = None
) -> list[str]:
    """The list of strings `name`.`key` of `sandbox`, or `default` where the key is missing and a
    default is given; exits 2 otherwise."""
    value = section(sandbox, name).get(key, default)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in cast("list[object]", value)):
        raise HarnessError(f"the sandbox object's {name}.{key} is not a list of strings")
    return list(cast("list[str]", value))


def credential_paths(sandbox: Mapping[str, object]) -> list[str]:
    """The `path` of each entry of `credentials.files`; exits 2 on an entry without one."""
    files = section(sandbox, "credentials").get("files")
    entries = cast("list[object]", files) if isinstance(files, list) else [None]
    found = [cast("dict[str, object]", e).get("path") if isinstance(e, dict) else None for e in entries]
    if not all(isinstance(p, str) for p in found):
        raise HarnessError("the sandbox object's credentials.files is not a list of objects with a path")
    return cast("list[str]", found)


def srt_settings(
    frontend: str,
    sandbox: Mapping[str, object],
    policy: Policy,
    home: pathlib.Path,
    tmpdir: str | None,
) -> dict[str, object]:
    """The `srt` settings of `frontend`, from `sandbox`, the `sandbox` object of the rendered
    Claude Code settings, and `policy`, with `home` as the home directory and `tmpdir`, when
    given, as a writable path; the rules are in the docstring of this module."""

    def expanded(entries: Sequence[str]) -> list[str]:
        return [expand(p, home) for p in entries]

    mine = policy.frontends[frontend]
    state, own, read_files = expanded(mine.state), expanded(mine.own), expanded(mine.read_files)
    others = expanded([p for name, f in policy.frontends.items() if name != frontend for p in f.state])
    binding = section(sandbox, "network").get("allowLocalBinding")
    if not isinstance(binding, bool):
        raise HarnessError("the sandbox object's network.allowLocalBinding is not true or false")
    allow_write = [p for p in expanded(strings(sandbox, "filesystem", "allowWrite")) if not below(p, others)]
    # srt emits the write denies after the write allows, so a deny strictly above a state path
    # would refuse every write to it; srt denies a write by default, so without the deny a write
    # below it passes only where allowWrite names the path.
    deny_write = [
        p
        for p in expanded(strings(sandbox, "filesystem", "denyWrite"))
        if p not in own and not strictly_above(p, state, home)
    ]
    deny_read = read_globs(
        frontend,
        [
            p
            for p in [
                str(home),
                *expanded(strings(sandbox, "filesystem", "denyRead")),
                *expanded(credential_paths(sandbox)),
            ]
            if p not in own
        ],
        mine.read_files,
        home,
    )
    denied = strings(sandbox, "network", "deniedDomains", default=[])
    whole = [d for d in denied if ":" not in d]
    hosts = [e for e in mine.network if not any(network.denies(d, network.split_port(e)[0]) for d in whole)]
    return {
        "network": {
            "allowedDomains": unique([*strings(sandbox, "network", "allowedDomains"), *hosts]),
            "deniedDomains": unique(denied),
            "allowLocalBinding": binding,
        },
        "filesystem": {
            "allowWrite": unique([*allow_write, *state, *([tmpdir] if tmpdir is not None else [])]),
            "denyWrite": unique([*deny_write, *expanded(mine.deny_write)]),
            "denyRead": unique(deny_read),
            "allowRead": unique([*expanded(policy.read.allow), *state, *own, *read_files]),
        },
        # A frontend's terminal user interface enters raw mode on its /dev/ttysNNN, which srt
        # allows only with this key.
        "allowPty": True,
    }


def strictly_above(entry: str, paths: Sequence[str], home: pathlib.Path) -> bool:
    """Whether `entry` is a literal, one without a character of GLOB_CHARS, other than `home`, that
    lies strictly above one of `paths`, both after `~` expansion and compared as `PurePosixPath`s,
    so `~/x/` and `~//x` are `~/x`."""
    top = pathlib.PurePosixPath(entry)
    literal = not any(c in entry for c in GLOB_CHARS)
    return (
        literal
        and top != pathlib.PurePosixPath(home)
        and any(below(p, [entry]) and pathlib.PurePosixPath(p) != top for p in paths)
    )


def read_globs(
    frontend: str, deny_read: list[str], read_files: Sequence[str], home: pathlib.Path
) -> list[str]:
    """`deny_read` with each literal entry, other than `home`, that lies above a path of
    `read_files`, the frontend's list as the policy spells it, written as the entry followed by
    `/*`, in its place. Paths compare as `PurePosixPath`s after `~` expansion, so `~/x/`, `~//x`
    and `~/./x` are `~/x`, and the glob is written from that form. srt lets a file allow pierce a
    glob deny, but emits a literal deny nested in a read allow after the allows, where it wins; and
    it strips a trailing `/**` before it tells a glob from a literal, so the glob ends in `/*`,
    which covers everything below the entry and not the entry itself. Exits 2 on a path that is
    itself an entry of `deny_read`, so "above" is strictly above."""
    files = {pathlib.PurePosixPath(expand(p, home)): p for p in read_files}
    denies = {pathlib.PurePosixPath(entry) for entry in deny_read}
    if equal := [p for path, p in files.items() if path in denies]:
        raise HarnessError(
            f"the policy's frontend.{frontend}.read_files entry {equal[0]!r} is itself a read deny entry; "
            f"frontend.{frontend}.own lifts an entry"
        )
    paths = [str(p) for p in files]
    return [
        f"{pathlib.PurePosixPath(entry)}/*" if strictly_above(entry, paths, home) else entry
        for entry in deny_read
    ]


def real_tmpdir() -> str | None:
    """The real path of $TMPDIR, links resolved, or None where it is unset or empty."""
    tmpdir = os.environ.get("TMPDIR")
    return str(pathlib.Path(tmpdir).resolve()) if tmpdir else None


def plan_files(
    profile: profile_module.Profile,
    overlay: pathlib.Path,
    chosen: tuple[str, ...],
    home: pathlib.Path,
    tmpdir: str | None,
) -> list[tuple[pathlib.Path, bytes, int | None, str]]:
    """The files of `harness install` for the frontends of `chosen`: [(destination, bytes, mode,
    label)]. First, in the order of FRONTENDS, each `srt_settings` of the frontend on the `sandbox`
    object of the Claude Code settings that `profile` and the network overlay `overlay` render,
    with each frontend's `network` of the policy followed by its table of the overlay; exits 2 on
    such an entry of any frontend that reaches a `fetch` host that no `deny` entry without a port
    removes. Each file is JSON indented by 2, the keys in the order built, with a final newline,
    and mode None. Then, where `chosen` holds claude, Claude Code's override INNER_OFF, mode None;
    then the launcher sandbox/agentbox at ~/.local/bin/agentbox, mode 755. With no frontend chosen
    it plans nothing, so an overlay that the install does not read stops nothing."""
    names = [name for name in frontends.FRONTENDS if name in chosen]
    if not names:
        return []
    shipped = load_policy(POLICY)
    claude: Any = frontends.adapter("claude")
    sandbox = cast("dict[str, object]", claude.settings_template(profile, overlay)["sandbox"])
    lists = network.merged(overlay)
    tables = cast("dict[str, tuple[str, ...]]", lists["frontend"])
    policy = replace(
        shipped,
        frontends=types.MappingProxyType(
            {
                name: replace(f, network=(*f.network, *tables.get(name, ())))
                for name, f in shipped.frontends.items()
            }
        ),
    )
    # The fetch hosts that `network.generate` keeps: a deny entry without a port removes the rest.
    whole = [d for d in cast("list[str]", lists["deny"]) if ":" not in d]
    fetch = [h for h in cast("list[str]", lists["fetch"]) if not any(network.denies(d, h) for d in whole)]
    for name, mine in policy.frontends.items():
        for entry in mine.network:
            if reached := [h for h in fetch if network.denies(network.split_port(entry)[0], h)]:
                raise HarnessError(
                    f"frontend.{name}.network entry {entry!r} reaches the fetch host {reached[0]!r}, which "
                    f"no sandboxed command may reach; remove one of them"
                )
    files: list[tuple[pathlib.Path, bytes, int | None, str]] = [
        (
            home / DIRECTORY / f"{name}.json",
            (json.dumps(srt_settings(name, sandbox, policy, home, tmpdir), indent=2) + "\n").encode(),
            None,
            f"~/{DIRECTORY}/{name}.json",
        )
        for name in names
    ]
    if "claude" in names:
        files.append((home / DIRECTORY / INNER_OFF_NAME, INNER_OFF, None, f"~/{DIRECTORY}/{INNER_OFF_NAME}"))
    files.append((home / LAUNCHER_PATH, LAUNCHER.read_bytes(), LAUNCHER_MODE, f"~/{LAUNCHER_PATH}"))
    return files


# ---------------------------------------------------------------------------------------------
# The cases of `harness test`

Check = Callable[[object, str], None]
# The exit status of `harness` on a refusal.
REFUSED = 2

# A policy for the cases, with the paths that each rule of `srt_settings` reads.
FIXTURE_POLICY = """\
[read]
allow = ["~/Research", "~/.config"]

[frontend.claude]
state = ["~/.claude", "~/.claude.json", "~/.cache/claude"]
deny_write = []
own = ["~/.claude.json"]
read_files = []
network = []

[frontend.opencode]
state = ["~/.local/share/opencode"]
deny_write = ["~/.local/share/opencode/x"]
own = ["~/.local/share/opencode/auth.json"]
read_files = ["~/.config/keys/a", "~/.config/keys/b", "~/.local/x/f", "~/.box*/k"]
network = []

[frontend.omp]
state = ["~/.omp"]
deny_write = []
own = []
read_files = []
network = []

[frontend.antigravity]
state = ["~/.gemini"]
deny_write = []
own = []
read_files = []
network = []
"""
# The fixture's table of omp, which the refusals of `read_files` and `network` change.
FIXTURE_OMP = '[frontend.omp]\nstate = ["~/.omp"]\ndeny_write = []\nown = []\nread_files = []\nnetwork = []\n'
# The credential files that each frontend reads and writes itself, and the provider tokens that
# OpenCode reads, as the shipped policy and template render them with the home directory /h.
SHIPPED_OWN = {
    "claude": ("/h/.claude.json", "/h/.claude/.credentials.json", "/h/.config/anthropic/credentials"),
    "opencode": ("/h/.local/share/opencode/auth.json", "/h/.local/share/opencode/mcp-auth.json"),
    "omp": ("/h/.omp/agent/agent.db", "/h/.omp/agent/agent.db-wal", "/h/.omp/agent/.env"),
    "antigravity": ("/h/.gemini/jetski-standalone-oauth-token",),
}
# Claude Code's Anthropic credentials directory and the lock directory that it makes before a
# token refresh, and agy's token file, as the shipped template and policy render them with the
# home directory /h.
SHIPPED_ANTHROPIC = "/h/.config/anthropic/credentials"
SHIPPED_LOCK = "/h/.config/anthropic/credentials.lock"
SHIPPED_AGY = "/h/.gemini/jetski-standalone-oauth-token"
# A template's write denies for the rule of the state paths: an entry above a state path in three
# spellings, a name that shares its prefix, a glob below it, another entry, the home directory and
# an entry equal to a state path.
STATE_DENY_WRITE = ["~/d", "~/d/", "~//d", "~/dx", "~/d/*", "~/e", "~", "~/s"]
SHIPPED_KEYS = "/h/.config/api-keys"
SHIPPED_TOKENS = tuple(f"{SHIPPED_KEYS}/{n}" for n in ("gwdg-token", "opendesign-token", "tokenharbor-token"))


def fixture_sandbox() -> dict[str, Any]:
    """A `sandbox` object for the cases: a name that shares a prefix with a state path
    (`~/.claudex`), a credential path that `denyRead` holds and one that it lacks, a glob, the
    home directory itself, an absolute path, a read deny directory above two of opencode's
    `read_files`, a read deny glob above another, and opencode's `own` file."""
    return {
        "enabled": True,
        "network": {
            "allowedDomains": ["b.org", "a.org", "b.org"],
            "deniedDomains": ["x.org", "x.org"],
            "allowLocalBinding": True,
        },
        "filesystem": {
            "allowWrite": [
                "/scratch",
                "~/Research",
                "~/.claude/agents",
                "~/.claude",
                "~/.claudex",
                "~/.cache/claude",
                "~/.omp/x",
            ],
            "denyWrite": ["~/.claude.json", "~/.ssh", "~/Research/**/.git/hooks", "~/.config"],
            "denyRead": [
                "~",
                "~/.ssh",
                "~/.config/keys",
                "~/.claude.json",
                "~/.box*",
                "~/.local/share/opencode/auth.json",
            ],
        },
        "credentials": {
            "files": [
                {"path": "~/.ssh", "mode": "deny"},
                {"path": "~/.netrc", "mode": "deny"},
                {"path": "~/.claude.json", "mode": "deny"},
            ]
        },
        "excludedCommands": ["git"],
    }


def selftest() -> tuple[int, int]:
    """The shipped policy, each refusal of `load_policy`, each rule of `srt_settings` on a fixture
    and on the settings template, and sandbox/agentbox on scratch homes (`agentbox_cases`):
    (cases, wrong). The cases of `harness install` on scratch HOMEs, `install_file_cases`, run in
    the selftest of install.py."""
    n = wrong = 0

    def check(ok: object, label: str) -> None:
        nonlocal n, wrong
        n += 1
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  sandbox: {label}")

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        policy_cases(check, root)
        settings_cases(check, root)
        template_cases(check)
        plan_network_cases(check, root / "plan")
        agentbox_cases(check, root / "agentbox")
    return n, wrong


def refused(call: Callable[[], object]) -> str | None:
    """The message of the HarnessError that `call` raises, or None."""
    try:
        call()
    except HarnessError as e:
        return str(e)
    return None


def policy_cases(check: Check, root: pathlib.Path) -> None:
    """The shipped policy loads, as a frozen dataclass; each broken policy exits 2 and names the
    key or the path."""
    policy = load_policy(POLICY)
    check(
        set(policy.frontends) == set(frontends.FRONTENDS)
        and {"~/Research", "~/.julia", "~/.juliaup"} <= set(policy.read.allow)
        and "~/.claude" in policy.frontends["claude"].state
        and "~/.omp" in policy.frontends["omp"].state
        and "~/.gemini" in policy.frontends["antigravity"].state
        and {"~/.omp/agent/config.yml", "~/.omp/agent/extensions"} <= set(policy.frontends["omp"].deny_write),
        f"sandbox/policy.toml loads with the four frontends and their paths: {sorted(policy.frontends)}",
    )
    owned = {name: f.own for name, f in policy.frontends.items()}
    check(
        owned == {name: tuple(f"~{p[2:]}" for p in paths) for name, paths in SHIPPED_OWN.items()},
        f"sandbox/policy.toml: each frontend's own are its credential files: {owned}",
    )
    read_files = {name: f.read_files for name, f in policy.frontends.items()}
    check(
        read_files
        == {
            "claude": (),
            "opencode": tuple(f"~{p[2:]}" for p in SHIPPED_TOKENS),
            "omp": (),
            "antigravity": (),
        },
        f"sandbox/policy.toml: opencode reads its three provider tokens, no other frontend a file: "
        f"{read_files}",
    )
    hosts = {name: f.network for name, f in policy.frontends.items()}
    check(
        hosts == {"claude": (), "opencode": (), "omp": (), "antigravity": ("oauth2.googleapis.com",)},
        f"sandbox/policy.toml: antigravity's network is its login host, every other frontend's empty: "
        f"{hosts}",
    )

    def refuses(change: Callable[[], object], error: type[Exception]) -> bool:
        try:
            change()
        except error:
            return True
        return False

    def replace_claude() -> None:
        cast("dict[str, FrontendPolicy]", policy.frontends)["claude"] = policy.frontends["omp"]

    check(
        refuses(lambda: policy.__setattr__("frontends", {}), FrozenInstanceError)
        and refuses(lambda: policy.read.__setattr__("allow", ()), FrozenInstanceError)
        and all(
            refuses(lambda f=f: f.__setattr__("own", ()), FrozenInstanceError)
            for f in policy.frontends.values()
        )
        and refuses(replace_claude, TypeError),
        "the policy, its read limit, each frontend's paths and the mapping of the frontends refuse a change",
    )

    text = FIXTURE_POLICY
    for label, body, words in [
        ("no [frontend.antigravity]", text[: text.index("[frontend.antigravity]")], ["frontend.antigravity"]),
        ("a key alow", text.replace("allow =", "alow =", 1), ["read.alow"]),
        ("no read.allow", text.replace('allow = ["~/Research", "~/.config"]\n', "", 1), ["read.allow"]),
        ("a top-level key of its own", "extra = 1\n" + text, ["extra"]),
        ("read that is no table", text.replace("[read]\nallow =", "read =", 1), ["read is not a table"]),
        (
            "a frontend of no adapter",
            text + "[frontend.other]\nstate = []\ndeny_write = []\nown = []\nread_files = []\n",
            ["frontend.other"],
        ),
        ("a key stat", text.replace('state = ["~/.omp"]', 'stat = ["~/.omp"]', 1), ["frontend.omp.stat"]),
        ("no deny_write", text.replace("deny_write = []\n", "", 1), ["frontend.claude.deny_write"]),
        ("a path /etc in read.allow", text.replace('"~/Research"', '"/etc"', 1), ["read.allow", "/etc"]),
        (
            "a path ~/../etc in read.allow",
            text.replace('"~/Research"', '"~/../etc"', 1),
            ["read.allow", "'~/../etc'", ".."],
        ),
        (
            "a path ~/.omp/.. in state",
            text.replace('["~/.omp"]', '["~/.omp/.."]', 1),
            ["frontend.omp.state", "'~/.omp/..'", ".."],
        ),
        (
            "a path ~ alone in own",
            text.replace('own = ["~/.claude.json"]', 'own = ["~"]', 1),
            ["frontend.claude.own", "'~'"],
        ),
        (
            "a path ~user/x in state",
            text.replace('["~/.omp"]', '["~user/x"]', 1),
            ["frontend.omp.state", "~user/x"],
        ),
        (
            "a state that is a string",
            text.replace('state = ["~/.omp"]', 'state = "~/.omp"', 1),
            ["frontend.omp.state is not a list of strings"],
        ),
        (
            "a number in deny_write",
            text.replace('deny_write = ["~/.local/share/opencode/x"]', "deny_write = [1]", 1),
            ["frontend.opencode.deny_write"],
        ),
        ("text that is not TOML", "[read\n", ["is not TOML"]),
        (
            "no read_files in [frontend.omp]",
            text.replace(FIXTURE_OMP, FIXTURE_OMP.replace("read_files = []\n", ""), 1),
            ["frontend.omp.read_files"],
        ),
        (
            "a path /etc/x in read_files",
            text.replace(FIXTURE_OMP, FIXTURE_OMP.replace("read_files = []", 'read_files = ["/etc/x"]'), 1),
            ["frontend.omp.read_files", "'/etc/x'"],
        ),
        (
            "a path ~/../x in read_files",
            text.replace(FIXTURE_OMP, FIXTURE_OMP.replace("read_files = []", 'read_files = ["~/../x"]'), 1),
            ["frontend.omp.read_files", "'~/../x'", ".."],
        ),
        (
            "a number in read_files",
            text.replace(FIXTURE_OMP, FIXTURE_OMP.replace("read_files = []", "read_files = [1]"), 1),
            ["frontend.omp.read_files is not a list of strings"],
        ),
        (
            "no network in [frontend.omp]",
            text.replace(FIXTURE_OMP, FIXTURE_OMP.replace("network = []\n", ""), 1),
            ["no frontend.omp.network"],
        ),
        *(
            (
                f"a network {value}",
                text.replace(FIXTURE_OMP, FIXTURE_OMP.replace("network = []", f"network = {value}"), 1),
                ["frontend.omp.network", *words],
            )
            for value, words in [
                ('["*"]', ["'*'"]),
                ('["*.org"]', ["'*.org'"]),
                ('["https://x.example.org"]', ["'https://x.example.org'"]),
                ('["x.example.org:08080"]', ["'x.example.org:08080'"]),
                ('"x.example.org"', ["not an array"]),
                ("[1]", ["not a string"]),
            ]
        ),
    ]:
        path = root / "policy.toml"
        path.write_text(body)
        message = refused(lambda path=path: load_policy(path))
        check(
            message is not None and str(path) in message and all(w in message for w in words),
            f"a policy with {label} exits 2 and names the key: {message!r}",
        )
    latin1, absent = root / "latin1.toml", root / "absent.toml"
    latin1.write_bytes(b"# \xff\n" + FIXTURE_POLICY.encode())
    message = refused(lambda: load_policy(latin1))
    check(
        message is not None and "UTF-8" in message and str(latin1) in message,
        f"a policy that is not UTF-8 exits 2 and names the file: {message!r}",
    )
    message = refused(lambda: load_policy(absent))
    check(
        message is not None and str(absent) in message,
        f"a missing policy exits 2 and names the file: {message!r}",
    )
    dots = root / "dots.toml"
    dots.write_text(FIXTURE_POLICY.replace('"~/Research"', '"~/Research..old"', 1))
    message = refused(lambda: load_policy(dots))
    check(
        message is None and load_policy(dots).read.allow[0] == "~/Research..old",
        f"a name that holds .. but is no .. segment loads: {message!r}",
    )


def settings_cases(check: Check, root: pathlib.Path) -> None:
    """Each rule of `srt_settings` on the fixture, with the expected lists written out."""
    path = root / "fixture-policy.toml"
    path.write_text(FIXTURE_POLICY)
    policy = load_policy(path)
    home = pathlib.Path("/h")
    sandbox = fixture_sandbox()
    before = copy.deepcopy(sandbox)
    claude = srt_settings("claude", sandbox, policy, home, "/t")
    check(sandbox == before, "srt_settings leaves its sandbox object as it is")
    for name in frontends.FRONTENDS:
        check(
            list(got := srt_settings(name, sandbox, policy, home, "/t"))
            == ["network", "filesystem", "allowPty"]
            and got["allowPty"] is True,
            f"{name}'s keys are network, filesystem and allowPty, and allowPty is true: "
            f"{list(got)}, {got.get('allowPty')!r}",
        )
    check(
        claude["network"]
        == {"allowedDomains": ["b.org", "a.org"], "deniedDomains": ["x.org"], "allowLocalBinding": True},
        f"network is the template's domains in order, each once, and its allowLocalBinding: "
        f"{claude['network']}",
    )
    fs = cast("dict[str, list[str]]", claude["filesystem"])
    check(
        list(fs) == ["allowWrite", "denyWrite", "denyRead", "allowRead"],
        f"the filesystem keys: {list(fs)}",
    )
    opencode = cast(
        "dict[str, list[str]]", srt_settings("opencode", sandbox, policy, home, "/t")["filesystem"]
    )
    for name, got, key, want in [
        (
            "claude",
            fs,
            "allowWrite",
            [
                "/scratch",
                "/h/Research",
                "/h/.claude/agents",
                "/h/.claude",
                "/h/.claudex",
                "/h/.cache/claude",
                "/h/.claude.json",
                "/t",
            ],
        ),
        ("claude", fs, "denyWrite", ["/h/.ssh", "/h/Research/**/.git/hooks", "/h/.config"]),
        (
            "claude",
            fs,
            "denyRead",
            [
                "/h",
                "/h/.ssh",
                "/h/.config/keys",
                "/h/.box*",
                "/h/.local/share/opencode/auth.json",
                "/h/.netrc",
            ],
        ),
        (
            "claude",
            fs,
            "allowRead",
            ["/h/Research", "/h/.config", "/h/.claude", "/h/.claude.json", "/h/.cache/claude"],
        ),
        (
            "opencode",
            opencode,
            "allowWrite",
            ["/scratch", "/h/Research", "/h/.claudex", "/h/.local/share/opencode", "/t"],
        ),
        (
            "opencode",
            opencode,
            "denyWrite",
            [
                "/h/.claude.json",
                "/h/.ssh",
                "/h/Research/**/.git/hooks",
                "/h/.config",
                "/h/.local/share/opencode/x",
            ],
        ),
        (
            "opencode",
            opencode,
            "denyRead",
            ["/h", "/h/.ssh", "/h/.config/keys/*", "/h/.claude.json", "/h/.box*", "/h/.netrc"],
        ),
        (
            "opencode",
            opencode,
            "allowRead",
            [
                "/h/Research",
                "/h/.config",
                "/h/.local/share/opencode",
                "/h/.local/share/opencode/auth.json",
                "/h/.config/keys/a",
                "/h/.config/keys/b",
                "/h/.local/x/f",
                "/h/.box*/k",
            ],
        ),
    ]:
        check(got[key] == want, f"{name}'s {key}: {got[key]}")
    equal = root / "equal-policy.toml"
    equal.write_text(FIXTURE_POLICY.replace('"~/.local/x/f"', '"~/.config/keys"', 1))
    message = refused(lambda: srt_settings("opencode", sandbox, load_policy(equal), home, "/t"))
    check(
        message is not None
        and "frontend.opencode.read_files" in message
        and "'~/.config/keys'" in message
        and "frontend.opencode.own" in message,
        f"a read_files path that is a read deny entry itself exits 2 and names the path and own: {message!r}",
    )
    entries = ["/h", "/h/q?", "/h/b[1", "/h/c]", "/h/d"]
    globbed = read_globs("opencode", entries, [f"~{e[2:]}/k" for e in entries[1:]], home)
    check(
        globbed == ["/h", "/h/q?", "/h/b[1", "/h/c]", "/h/d/*"],
        f"a read deny entry that holds ?, [ or ] is a glob and stays as it is: {globbed}",
    )
    globbed = read_globs("opencode", ["/h", "/h/d"], ["~/d/a", "~/d/b"], home)
    check(
        globbed == ["/h", "/h/d/*"],
        f"two read_files paths below one read deny entry give one glob in its place: {globbed}",
    )
    for spelling in ["~/.config/keys/", "~/.config//keys", "~/.config/./keys", "~/", "~/.", "~/.box*"]:
        equal.write_text(FIXTURE_POLICY.replace('"~/.local/x/f"', f'"{spelling}"', 1))
        message = refused(lambda: srt_settings("opencode", sandbox, load_policy(equal), home, "/t"))
        check(
            message is not None and f"{spelling!r}" in message and "frontend.opencode.own" in message,
            f"a read_files path {spelling}, a read deny entry as a path, exits 2 and names it: {message!r}",
        )
    spelled = fixture_sandbox()
    spelled["filesystem"]["denyRead"] = ["~/", "~/.config/keys/", "~/.config/key"]
    got = cast("dict[str, list[str]]", srt_settings("opencode", spelled, policy, home, "/t")["filesystem"])[
        "denyRead"
    ]
    check(
        got[:4] == ["/h", "/h/", "/h/.config/keys/*", "/h/.config/key"],
        f"a read deny entry ~/ is the home directory and stays; ~/.config/keys/ is the glob "
        f"/h/.config/keys/*; ~/.config/key, a prefix of the read_files paths, stays literal: {got}",
    )
    equal.write_text(FIXTURE_POLICY.replace('"~/.local/x/f"', '"~/.config/keys"', 1))
    message = refused(lambda: srt_settings("opencode", spelled, load_policy(equal), home, "/t"))
    check(
        message is not None and "'~/.config/keys'" in message,
        f"a read_files path ~/.config/keys, equal as a path to the read deny entry ~/.config/keys/, "
        f"exits 2: {message!r}",
    )
    state_cases(check, root, home)
    network_cases(check, root, home)

    plain = fixture_sandbox()
    del plain["network"]["deniedDomains"]
    plain["network"]["allowLocalBinding"] = False
    no_denied = srt_settings("omp", plain, policy, home, None)
    check(
        no_denied["network"]
        == {"allowedDomains": ["b.org", "a.org"], "deniedDomains": [], "allowLocalBinding": False},
        f"a template with no deniedDomains gives [], and allowLocalBinding false stays false: "
        f"{no_denied['network']}",
    )
    omp = cast("dict[str, list[str]]", no_denied["filesystem"])
    check(
        omp["allowWrite"] == ["/scratch", "/h/Research", "/h/.claudex", "/h/.omp/x", "/h/.omp"],
        f"with no tmpdir, allowWrite ends with the last state path, and keeps a path below its own "
        f"state: {omp['allowWrite']}",
    )
    spaced = srt_settings("claude", sandbox, policy, pathlib.Path("/home/u v"), "/t")["filesystem"]
    check(
        spaced
        == {
            k: [p.replace("/h", "/home/u v", 1) if p.startswith("/h") else p for p in v]
            for k, v in fs.items()
        },
        "a home directory with a space replaces each ~ alike",
    )
    edits: list[tuple[str, Callable[[dict[str, Any]], object], str]] = [
        ("a ~user path", lambda s: s["filesystem"]["denyWrite"].append("~user/x"), "~user/x"),
        ("no denyRead", lambda s: s["filesystem"].pop("denyRead"), "filesystem.denyRead"),
        (
            "an allowWrite that is a string",
            lambda s: s["filesystem"].__setitem__("allowWrite", "/scratch"),
            "filesystem.allowWrite",
        ),
        (
            "no allowLocalBinding",
            lambda s: s["network"].pop("allowLocalBinding"),
            "network.allowLocalBinding",
        ),
        ("no credentials object", lambda s: s.pop("credentials"), "no credentials object"),
        (
            "a credential with no path",
            lambda s: s["credentials"]["files"].append({"mode": "deny"}),
            "credentials.files",
        ),
    ]
    for label, edit, word in edits:
        broken = fixture_sandbox()
        edit(broken)
        message = refused(lambda broken=broken: srt_settings("claude", broken, policy, home, "/t"))
        check(
            message is not None and word in message,
            f"a sandbox object with {label} exits 2 and names it: {message!r}",
        )


def state_cases(check: Check, root: pathlib.Path, home: pathlib.Path) -> None:
    """The write denies of STATE_DENY_WRITE, with `~/s` also spelled `~/s/` and `~//s`, for omp,
    whose state is `~/d/s` and `~/s`; those of STATE_DENY_WRITE for antigravity, whose state lies
    below none of them; then, with the globs `~/g*`, `~/q?`, `~/b[x]` and `~/c]` and the home
    directory spelled `~/` added, for omp with the state `~/dxs`, which shares a prefix with `~/d`
    and `~/dx`, and a path below each glob as a path."""
    full = ["/h/d", "/h/d/", "/h//d", "/h/dx", "/h/d/*", "/h/e", "/h", "/h/s"]
    for state, extra, name, want, label in [
        (
            '["~/d/s", "~/s"]',
            ["~/s/", "~//s"],
            "omp",
            ["/h/dx", "/h/d/*", "/h/e", "/h", "/h/s", "/h/s/", "/h//s"],
            "drops ~/d, ~/d/ and ~//d, strictly above its state ~/d/s, and keeps ~/dx, the glob ~/d/*, "
            "~/e, the home directory and ~/s, ~/s/ and ~//s, equal to its state ~/s",
        ),
        (
            '["~/d/s", "~/s"]',
            [],
            "antigravity",
            full,
            "keeps every write deny, as no path of its own state lies below one",
        ),
        (
            '["~/dxs", "~/g*/s", "~/q?/s", "~/b[x]/s", "~/c]/s"]',
            ["~/g*", "~/q?", "~/b[x]", "~/c]", "~/"],
            "omp",
            [*full, "/h/g*", "/h/q?", "/h/b[x]", "/h/c]", "/h/"],
            "with the state ~/dxs, ~/g*/s, ~/q?/s, ~/b[x]/s and ~/c]/s keeps every write deny: ~/d and "
            "~/dx are prefixes of ~/dxs and no path above it, ~/g*, ~/q?, ~/b[x] and ~/c] are globs and "
            "~/ is the home directory",
        ),
    ]:
        path = root / "state-policy.toml"
        path.write_text(FIXTURE_POLICY.replace(FIXTURE_OMP, FIXTURE_OMP.replace('["~/.omp"]', state), 1))
        sandbox = fixture_sandbox()
        sandbox["filesystem"]["denyWrite"] = [*STATE_DENY_WRITE, *extra]
        got = cast(
            "dict[str, list[str]]", srt_settings(name, sandbox, load_policy(path), home, "/t")["filesystem"]
        )
        check(got["denyWrite"] == want, f"{name}'s denyWrite {label}: {got['denyWrite']}")


def network_cases(check: Check, root: pathlib.Path, home: pathlib.Path) -> None:
    """The `allowedDomains` of `srt_settings` with a frontend `network` on the fixture: the
    template's list, then the frontend's entries, each once at its first place, without each entry
    whose host a deny entry without a port matches, case folded; another frontend's file keeps the
    template's list alone."""
    path = root / "network-policy.toml"
    hosts = ["n.org", "a.org", "x.org:8443", "*.y.org", "w.y.org", "keep.z.org", "n.org", "Up.Q.org"]
    # The network key of opencode's table, the last one before omp's.
    before, after = FIXTURE_POLICY.split("[frontend.omp]")
    path.write_text(
        f"{before.removesuffix('network = []\n\n')}network = {json.dumps(hosts)}\n\n[frontend.omp]{after}"
    )
    policy = load_policy(path)
    sandbox = fixture_sandbox()
    sandbox["network"]["deniedDomains"] = ["x.org", "x.org", "*.y.org", "keep.z.org:22", "*.q.org"]
    got = {name: srt_settings(name, sandbox, policy, home, "/t")["network"] for name in frontends.FRONTENDS}
    domains = {name: cast("dict[str, list[str]]", n)["allowedDomains"] for name, n in got.items()}
    check(
        policy.frontends["opencode"].network == tuple(hosts)
        and domains["opencode"] == ["b.org", "a.org", "n.org", "keep.z.org"],
        f"opencode's allowedDomains: the template's, then its network, each once; a deny x.org removes "
        f"x.org:8443, *.y.org removes *.y.org and w.y.org, *.q.org removes Up.Q.org, keep.z.org:22 "
        f"removes nothing: {domains['opencode']}",
    )
    check(
        all(domains[name] == ["b.org", "a.org"] for name in ("claude", "omp", "antigravity")),
        f"a frontend with an empty network has the template's allowedDomains alone: {domains}",
    )
    sandbox["network"]["deniedDomains"] = ["*"]
    everything = srt_settings("opencode", sandbox, policy, home, "/t")["network"]
    check(
        cast("dict[str, list[str]]", everything)["allowedDomains"] == ["b.org", "a.org"],
        f"a deny * removes every frontend entry and leaves the template's: {everything}",
    )


def plan_network_cases(check: Check, root: pathlib.Path) -> None:
    """The `allowedDomains` of each frontend's file as `plan_files` plans it with the dummy profile,
    the shipped policy and an overlay with frontend tables, deny entries or fetch hosts; and each
    exit 2 of an overlay's frontend table or of an entry that reaches a fetch host."""
    profile = profile_module.load(profile_module.DUMMY)
    home = pathlib.Path("/h")
    claude: Any = frontends.adapter("claude")
    count = 0
    root.mkdir()

    def overlay(text: str | None) -> pathlib.Path:
        nonlocal count
        count += 1
        path = root / f"overlay-{count}" / "network.toml"
        path.parent.mkdir()
        if text is not None:
            path.write_text(text)
        return path

    def files(text: str | None) -> dict[str, dict[str, Any]]:
        planned = plan_files(profile, overlay(text), frontends.FRONTENDS, home, "/t")
        return {
            dest.name.removesuffix(".json"): cast("dict[str, Any]", jsonio.loads(data.decode(), where=label))
            for dest, data, _, label in planned
            if dest.parent.name == DIRECTORY.name and dest.name != INNER_OFF_NAME
        }

    def domains(text: str | None) -> dict[str, list[str]]:
        return {name: obj["network"]["allowedDomains"] for name, obj in files(text).items()}

    template = cast(
        "list[str]", claude.settings_template(profile, overlay(None))["sandbox"]["network"]["allowedDomains"]
    )
    shipped = domains(None)
    check(
        all(shipped[name] == template for name in ("claude", "opencode", "omp"))
        and shipped["antigravity"] == [*template, "oauth2.googleapis.com"],
        f"with no overlay, antigravity's file adds oauth2.googleapis.com to the template's allowedDomains, "
        f"every other file has the template's: { {name: d[len(template) :] for name, d in shipped.items()} }",
    )
    tables = (
        '[frontend.opencode]\nnetwork = ["*.example.org", "chat.example.net", "127.0.0.1:8080", '
        '"chat.example.net", "localhost:8080"]\n'
        '[frontend.omp]\nnetwork = ["*.example.org"]\n'
        "[frontend.claude]\nnetwork = []\n"
    )
    tabled = domains(tables)
    check(
        tabled
        == {
            "claude": template,
            "opencode": [*template, "*.example.org", "chat.example.net", "127.0.0.1:8080", "localhost:8080"],
            "omp": [*template, "*.example.org"],
            "antigravity": [*template, "oauth2.googleapis.com"],
        },
        f"an overlay's frontend table reaches that frontend's file alone, after the policy's list, each "
        f"entry once: { {name: d[len(template) :] for name, d in tabled.items()} }",
    )
    again = domains(f'[frontend.omp]\nnetwork = ["{template[0]}", "z.example.org"]\n')["omp"]
    check(
        again == [*template, "z.example.org"],
        f"a frontend entry that the template holds stays once, at the template's place: "
        f"{again[len(template) :]}",
    )

    after = domains('[frontend.antigravity]\nnetwork = ["a.example.org"]\n')["antigravity"]
    check(
        after == [*template, "oauth2.googleapis.com", "a.example.org"],
        f"an overlay's entries follow the policy's in that frontend's file: {after[len(template) :]}",
    )

    def without_domains(obj: dict[str, Any]) -> dict[str, Any]:
        return {**obj, "network": {k: v for k, v in obj["network"].items() if k != "allowedDomains"}}

    plain, changed = files(None), files(tables)
    check(
        all(without_domains(plain[name]) == without_domains(changed[name]) for name in frontends.FRONTENDS),
        "an overlay's frontend tables change no key of a file other than allowedDomains",
    )
    denied = domains(
        'deny = ["*.example.net", "oauth2.googleapis.com", "keep.example.com:22"]\n'
        '[frontend.opencode]\nnetwork = ["chat.example.net:8443", "keep.example.com", "a.example.org"]\n'
    )
    check(
        denied["opencode"] == [*template, "keep.example.com", "a.example.org"]
        and denied["antigravity"] == template,
        f"an overlay deny without a port removes a frontend entry of the overlay and of the policy by its "
        f"host, and one with a port removes none: {denied['opencode'][len(template) :]}, "
        f"{denied['antigravity'][len(template) :]}",
    )
    for label, text, words in [
        (
            "an overlay frontend entry *.example.org above an overlay fetch host",
            'fetch = ["w.example.org"]\n[frontend.omp]\nnetwork = ["*.example.org"]\n',
            ["frontend.omp.network", "'*.example.org'", "'w.example.org'"],
        ),
        (
            "an overlay frontend entry with a port on an overlay fetch host",
            'fetch = ["w.example.org"]\n[frontend.omp]\nnetwork = ["W.example.org:8443"]\n',
            ["frontend.omp.network", "'W.example.org:8443'", "'w.example.org'"],
        ),
        (
            "a fetch host that only a deny entry with a port names, below a frontend entry",
            'deny = ["w.example.org:22"]\nfetch = ["w.example.org"]\n'
            '[frontend.omp]\nnetwork = ["*.example.org"]\n',
            ["frontend.omp.network", "'*.example.org'", "'w.example.org'"],
        ),
        (
            "the policy's entry oauth2.googleapis.com on an overlay fetch host",
            'fetch = ["oauth2.googleapis.com"]\n',
            ["frontend.antigravity.network", "'oauth2.googleapis.com'"],
        ),
        (
            "an unknown frontend cursor",
            '[frontend.cursor]\nnetwork = ["x.example.org"]\n',
            ["frontend.cursor"],
        ),
    ]:
        message = refused(lambda text=text: files(text))
        check(
            message is not None and all(w in message for w in words),
            f"plan_files with {label} exits 2 and names it: {message!r}",
        )
    message = refused(
        lambda: files('fetch = ["w.example.org"]\n[frontend.omp]\nnetwork = ["v.example.org"]\n')
    )
    check(message is None, f"a frontend entry beside a fetch host that it does not cover plans: {message!r}")
    message = refused(
        lambda: plan_files(profile, overlay('fetch = ["oauth2.googleapis.com"]\n'), ("claude",), home, "/t")
    )
    check(
        message is not None
        and all(w in message for w in ["frontend.antigravity.network", "'oauth2.googleapis.com'"]),
        f"an entry of a frontend that the install does not choose reaches a fetch host and exits 2 too: "
        f"{message!r}",
    )
    for label, text, want in [
        (
            "a fetch host that a deny removes below a frontend entry",
            'deny = ["*.w.example.org"]\nfetch = ["a.w.example.org"]\n'
            '[frontend.omp]\nnetwork = ["*.example.org"]\n',
            [*template, "*.example.org"],
        ),
        (
            "a deny that removes a fetch host and the frontend entry on it",
            'deny = ["*.example.org"]\nfetch = ["w.example.org"]\n'
            '[frontend.omp]\nnetwork = ["w.example.org:8443"]\n',
            template,
        ),
    ]:
        try:
            got: list[str] | str = domains(text)["omp"]
        except HarnessError as e:
            got = str(e)
        check(got == want, f"plan_files with {label} plans omp's list {want[len(template) :]}: {got!r}")
    message = refused(lambda: claude.settings_template(profile, overlay("[frontend.cursor]\nnetwork = []\n")))
    check(
        message is not None and "frontend.cursor" in message,
        f"the Claude Code settings refuse an overlay with an unknown frontend too: {message!r}",
    )


def template_cases(check: Check) -> None:
    """`srt_settings` of each frontend on the settings template's `sandbox` object, with a fixture
    domain list, and the shipped policy."""
    template = cast("dict[str, Any]", jsonio.load(REPO / "settings" / "settings.proposal.json"))["sandbox"]
    template["network"]["allowedDomains"] = ["example.org", "*.example.org"]
    policy = load_policy(POLICY)
    home = pathlib.Path("/h")
    credentials = ["/h" + c["path"][1:] for c in template["credentials"]["files"]]
    rendered = {name: srt_settings(name, template, policy, home, "/t") for name in frontends.FRONTENDS}

    def values(obj: object) -> list[object]:
        if isinstance(obj, dict):
            return [v for x in cast("dict[str, object]", obj).values() for v in values(x)]
        if isinstance(obj, list):
            return [v for x in cast("list[object]", obj) for v in values(x)]
        return [obj]

    for name, s in rendered.items():
        fs = cast("dict[str, list[str]]", s["filesystem"])
        mine = ["/h" + p[1:] for p in policy.frontends[name].own]
        counts = {c: fs["denyRead"].count(c) + fs["denyRead"].count(f"{c}/*") for c in credentials}
        check(
            all(k == (0 if c in mine else 1) for c, k in counts.items()),
            f"{name}: each credential path is a read deny once, as itself or as its glob, its own none: "
            f"{ {c: k for c, k in counts.items() if k != 1} }",
        )
        others = [p for other, paths in SHIPPED_OWN.items() if other != name for p in paths]
        check(
            all(p in fs["allowRead"] and p not in fs["denyRead"] + fs["denyWrite"] for p in SHIPPED_OWN[name])
            and all(p in fs["denyRead"] for p in others),
            f"{name}: its own credential files are read allows and in no deny list, every other frontend's "
            f"a read deny: {[p for p in SHIPPED_OWN[name] if p in fs['denyRead']]}, "
            f"{[p for p in others if p not in fs['denyRead']]}",
        )
        check(
            {"/h/**/.env", "/h/**/.env.*", "/h/.cache/gh", "/h/.cache/kaimon/sessions.json"}
            <= set(fs["denyRead"])
            and "/h/Research/**/.githooks" in fs["denyWrite"],
            f"{name}: reads of .env files, ~/.cache/gh and Kaimon's sessions.json and writes of .githooks "
            f"are denied: {fs['denyRead'][-6:]}, {fs['denyWrite'][-4:]}",
        )
        check(
            fs["denyRead"][0] == "/h",
            f"{name}: the home directory is the first read deny: {fs['denyRead'][0]}",
        )
        check(
            ("/h/.cache/claude" in fs["allowWrite"]) == (name == "claude"),
            f"{name}: only claude writes ~/.cache/claude: {'/h/.cache/claude' in fs['allowWrite']}",
        )
        check(
            not [v for v in values(s) if isinstance(v, str) and v.startswith("~")],
            f"{name}: no value starts with ~",
        )
        check(all(len(set(v)) == len(v) for v in fs.values()), f"{name}: no list holds an entry twice")
        last = cast("dict[str, list[str]]", srt_settings(name, template, policy, home, None)["filesystem"])
        check(
            last["allowWrite"][-1] == "/h" + policy.frontends[name].state[-1][1:],
            f"{name}: with no tmpdir, allowWrite ends with the last state path: {last['allowWrite'][-3:]}",
        )
    claude = cast("dict[str, list[str]]", rendered["claude"]["filesystem"])
    check(
        "/h/.claude/agents" in claude["allowWrite"]
        and "/h/.claude" in claude["allowWrite"]
        and claude["allowWrite"][-1] == "/t"
        and claude["denyRead"][0] == "/h"
        and "/h/.claude.json" not in claude["denyWrite"] + claude["denyRead"],
        "claude: its directory writable, /t last, the home directory the first read deny, ~/.claude.json "
        "in no deny list",
    )
    roots = ["/h/.claude", "/h/.omp", "/h/.gemini"]
    opencode = cast("dict[str, list[str]]", rendered["opencode"]["filesystem"])
    hits = [p for key in ("allowWrite", "allowRead") for p in opencode[key] if below(p, roots)]
    check(not hits, f"opencode writes and reads nothing at or below another frontend's state: {hits}")
    filesystem = template["filesystem"]
    check(
        "~/.cache/claude" not in filesystem["allowWrite"]
        and "~/Research/**/.githooks" in filesystem["denyWrite"]
        and {"~/**/.env", "~/**/.env.*", "~/.cache/gh", "~/.cache/kaimon/sessions.json"}
        <= set(filesystem["denyRead"]),
        "the template denies reads of .env files, ~/.cache/gh and Kaimon's sessions.json and writes of "
        "~/Research/**/.githooks, and allows no write of ~/.cache/claude",
    )
    for name, s in rendered.items():
        fs = cast("dict[str, list[str]]", s["filesystem"])
        mine = name == "claude"
        anthropic = (
            "writes ~/.config/anthropic/credentials and its lock, reads the credentials and has no write "
            "deny ~/.config"
            if mine
            else "neither writes ~/.config/anthropic/credentials and its lock nor reads the credentials, and "
            "keeps the write deny ~/.config"
        )
        check(
            ("/h/.config" in fs["denyWrite"]) != mine
            and "/h/.config/systemd/user" in fs["denyWrite"]
            and all((p in fs["allowWrite"]) == mine for p in (SHIPPED_ANTHROPIC, SHIPPED_LOCK))
            and (SHIPPED_ANTHROPIC in fs["allowRead"]) == mine
            and (SHIPPED_ANTHROPIC in fs["denyRead"]) != mine,
            f"{name} {anthropic}; ~/.config/systemd/user stays a write deny: {fs['allowWrite'][-4:]}, "
            f"{[p for p in fs['denyWrite'] if p.startswith('/h/.config')]}",
        )
        agy = name == "antigravity"
        check(
            (SHIPPED_AGY in fs["allowRead"]) == agy and (SHIPPED_AGY in fs["denyRead"]) != agy,
            f"{name} {'reads' if agy else 'is denied reads of'} ~/.gemini/jetski-standalone-oauth-token",
        )
    keys = filesystem["denyRead"].index("~/.config/api-keys")
    after = [SHIPPED_ANTHROPIC, SHIPPED_AGY]
    check(
        filesystem["denyRead"][keys + 1 : keys + 3] == ["~" + p[2:] for p in after]
        and {"~" + p[2:] for p in after} <= {c["path"] for c in template["credentials"]["files"]}
        and opencode["denyRead"][opencode["denyRead"].index(f"{SHIPPED_KEYS}/*") + 1 :][:2] == after,
        f"the template denies reads of ~/.config/anthropic/credentials and "
        f"~/.gemini/jetski-standalone-oauth-token after ~/.config/api-keys, and names both in "
        f"credentials.files; opencode's file keeps them there: {filesystem['denyRead'][keys : keys + 3]}",
    )
    literal = [p for p in opencode["denyRead"] if p.startswith(SHIPPED_KEYS)]
    # antigravity's own entry and opencode's follow ~/.config/api-keys, so both put it at one index.
    antigravity = cast("dict[str, list[str]]", rendered["antigravity"]["filesystem"])
    check(
        literal == [f"{SHIPPED_KEYS}/*"]
        and opencode["denyRead"].index(literal[0]) == antigravity["denyRead"].index(SHIPPED_KEYS)
        and all(t in opencode["allowRead"] for t in SHIPPED_TOKENS),
        f"opencode: ~/.config/api-keys is the read deny glob ~/.config/api-keys/* in its place, and its "
        f"three tokens are read allows: {literal}",
    )
    for name in ("claude", "omp", "antigravity"):
        fs = cast("dict[str, list[str]]", rendered[name]["filesystem"])
        check(
            [p for p in fs["denyRead"] if p.startswith(SHIPPED_KEYS)] == [SHIPPED_KEYS]
            and not [t for t in SHIPPED_TOKENS if t in fs["allowRead"]],
            f"{name}: ~/.config/api-keys stays a literal read deny, and no token is a read allow",
        )


# The script of the cases' srt: it writes its arguments, each ended by a NUL, to srt-args, its
# environment to srt-env and its parent's process ID to srt-parent, in the home directory that
# holds it at .local/bin/srt, then exits with $STUB_STATUS.
STUB_SRT = """\
#!/bin/sh
home=${0%/.local/bin/srt}
for a in "$@"; do printf '%s\\0' "$a"; done > "$home/srt-args"
/usr/bin/env > "$home/srt-env"
echo "$PPID" > "$home/srt-parent"
exit "${STUB_STATUS:-0}"
"""
# The exit status of the stub srt in the case of the status.
STUB_EXIT = 7
# The variables that the shell itself sets in the environment of a program it starts.
SHELL_SET = {"PWD", "OLDPWD", "SHLVL", "_"}
# The variables of the caller in each case: names that a script could use for its own values.
CALLER = {
    "LANG": "C",
    "name": "caller",
    "policy": "caller",
    "program": "caller",
    "file": "caller",
    "entry": "caller",
    "rest": "caller",
    "found": "caller",
    "dir": "caller",
}
# The cache variable of each tool that sandbox/agentbox sets, and its subdirectory of the run
# directory.
CACHES = {"npm_config_cache": "npm", "UV_CACHE_DIR": "uv", "TEXMFVAR": "texmf-var"}
# The directory below which sandbox/agentbox makes its run directory where TMPDIR is unset or
# empty.
FALLBACK_TMPDIR = pathlib.PurePosixPath("/", "tmp")


def stub(path: pathlib.Path) -> None:
    """An executable stub program at `path` that exits 0, its directories made."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)


@dataclass(frozen=True)
class Box:
    """A scratch home for sandbox/agentbox: the stub srt (STUB_SRT) in ~/.local/bin, the srt
    settings file of each frontend and Claude Code's override in the sandbox directory, a stub
    of each frontend's program in path/, and the empty directory tmpdir/ for $TMPDIR."""

    home: pathlib.Path

    @classmethod
    def fresh(cls, root: pathlib.Path, label: str) -> Box:
        home = root / label
        (home / ".local" / "bin").mkdir(parents=True)
        (home / DIRECTORY).mkdir(parents=True)
        (home / "tmpdir").mkdir()
        srt = home / ".local" / "bin" / "srt"
        srt.write_text(STUB_SRT)
        srt.chmod(0o755)
        for name in (*frontends.FRONTENDS, "claude-inner-off"):
            (home / DIRECTORY / f"{name}.json").write_text("{}\n")
        for program in ("claude", "opencode", "omp", "agy"):
            stub(home / "path" / program)
        return cls(home)

    def env(self, **extra: str) -> dict[str, str]:
        """The environment of a run: HOME, a PATH with path/ first, TMPDIR the directory tmpdir/,
        CALLER and `extra`."""
        return {
            "HOME": str(self.home),
            "PATH": f"{self.home}/path:/usr/bin:/bin",
            "TMPDIR": str(self.home / "tmpdir"),
            **CALLER,
            **extra,
        }

    def run(
        self,
        *args: str,
        cwd: pathlib.Path | None = None,
        variables: Mapping[str, str] | None = None,
        **extra: str,
    ) -> subprocess.CompletedProcess[str]:
        """sandbox/agentbox with `args`, in the environment `env` with `variables` and `extra`,
        with `cwd` as the working directory where it is given."""
        return subprocess.run(
            [str(REPO / "sandbox" / "agentbox"), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=self.env(**(variables or {}), **extra),
            cwd=cwd,
            timeout=60,
            check=False,
        )

    def made(self) -> list[pathlib.Path]:
        """The entries that the runs made in tmpdir/."""
        return sorted((self.home / "tmpdir").iterdir())

    def caches(self) -> dict[str, str]:
        """The cache variables of CACHES, each the path of its subdirectory of the one directory in
        tmpdir/, or {} where tmpdir/ does not hold exactly one directory whose name starts with
        agentbox. and that holds the three subdirectories."""
        made = self.made()
        if len(made) != 1 or not made[0].name.startswith("agentbox."):
            return {}
        if not all((made[0] / sub).is_dir() for sub in CACHES.values()):
            return {}
        return {name: f"{made[0]}/{sub}" for name, sub in CACHES.items()}

    def argv(self) -> list[str] | None:
        """The arguments that the stub srt saw, or None where it did not run."""
        path = self.home / "srt-args"
        return path.read_text().split("\0")[:-1] if path.exists() else None

    def environment(self) -> dict[str, str]:
        """The environment that the stub srt saw, without SHELL_SET."""
        lines = (self.home / "srt-env").read_text().splitlines()
        pairs = [line.split("=", 1) for line in lines]
        return {k: v for k, v in pairs if k not in SHELL_SET}


def agentbox_cases(check: Check, root: pathlib.Path) -> None:
    """sandbox/agentbox, run as a program on a fresh `Box` below `root` per case: its mode; for each
    frontend, the arguments that srt sees, with the caller's `a b`, `--`, the empty string, `--model`
    and `x` each as one argument, and the environment, the caller's with AGENTBOX=1 and the three
    cache variables of CACHES added; `resolution_cases`; `cache_cases`; srt's exit status; each
    refusal, which exits 2, starts no srt, makes nothing in TMPDIR and prints one line on stderr
    that names its cause; and the usage."""
    script = REPO / "sandbox" / "agentbox"
    mode = stat.S_IMODE(script.stat().st_mode) if script.is_file() else None
    # Git stores only the execute bit, so the checkout's write bits follow its umask; the install
    # sets LAUNCHER_MODE on the copy it writes.
    executable = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    check(
        mode is not None and mode & executable == executable and not mode & stat.S_IWOTH,
        f"sandbox/agentbox is a file executable by all and writable by no other: "
        f"{'no file' if mode is None else f'{mode:o}'}",
    )
    if mode is None:
        return
    tail = ["a b", "--", "", "--model", "x"]
    settings = root / "lines"
    for name, policy, extra in [
        ("claude", "claude", ["--settings", "<home>/.config/research-harness/sandbox/claude-inner-off.json"]),
        ("opencode", "opencode", ["--standalone"]),
        ("omp", "omp", ["--approval-mode", "yolo"]),
        ("agy", "antigravity", []),
    ]:
        box = Box.fresh(settings, name)
        p = box.run(name, *tail)
        want = [
            "--settings",
            f"{box.home}/.config/research-harness/sandbox/{policy}.json",
            "--",
            f"{box.home}/path/{name}",
            *(e.replace("<home>", str(box.home)) for e in extra),
            *tail,
        ]
        got = box.argv()
        check(
            p.returncode == 0 and got == want and p.stderr == "",
            f"agentbox {name}: srt gets its settings file, --, the program, {extra or 'nothing'} and each "
            f"argument as one: {p.returncode}, {got}, {p.stderr.strip()!r}",
        )
        parent = (box.home / "srt-parent").read_text().strip() if got is not None else None
        check(
            parent == str(os.getpid()),
            f"agentbox {name} execs srt, whose parent is then the caller: {parent}, caller {os.getpid()}",
        )
        seen = box.environment() if got is not None else {}
        caches = box.caches()
        check(
            caches and seen == {**box.env(), "AGENTBOX": "1", **caches},
            f"agentbox {name}: the environment is the caller's with AGENTBOX=1, and npm_config_cache, "
            f"UV_CACHE_DIR and TEXMFVAR each name its subdirectory of one new directory below TMPDIR: "
            f"{box.made()}, { {k: v for k, v in seen.items() if box.env().get(k) != v} }",
        )

    resolution_cases(check, root / "resolution")
    cache_cases(check, root / "caches")

    box = Box.fresh(root, "status")
    p = box.run("opencode", STUB_STATUS=str(STUB_EXIT))
    check(p.returncode == STUB_EXIT, f"agentbox exits with srt's status {STUB_EXIT}: {p.returncode}")

    for label, change, args, extra, words in agentbox_refusals():
        box = Box.fresh(root / "refused", label.replace(" ", "-").replace("/", "-"))
        change(box.home)
        p = box.run(*args, variables={k: v.replace("<home>", str(box.home)) for k, v in extra.items()})
        check(
            p.returncode == REFUSED
            and box.argv() is None
            and p.stdout == ""
            and p.stderr.count("\n") == 1
            and p.stderr.endswith("\n")
            and all(w.replace("<home>", str(box.home)) in p.stderr for w in words)
            and not box.made(),
            f"agentbox with {label} exits 2, starts no srt, makes nothing in TMPDIR and prints one line "
            f"that names {words}: {p.returncode}, {box.argv()}, {box.made()}, {p.stderr!r}",
        )

    for label, override, args in [
        ("opencode and no override", False, ["opencode"]),
        ("opencode --settings x", True, ["opencode", "--settings", "x"]),
        ("claude --settingsx", True, ["claude", "--settingsx"]),
        ("claude --help", True, ["claude", "--help"]),
    ]:
        box = Box.fresh(root / "passed", label.replace(" ", "-"))
        if not override:
            (box.home / DIRECTORY / "claude-inner-off.json").unlink()
        p = box.run(*args)
        got = box.argv()
        check(
            p.returncode == 0 and got is not None and got[len(got) - len(args) + 1 :] == args[1:],
            f"agentbox with {label} starts srt with the arguments: {p.returncode}, {got}, {p.stderr!r}",
        )

    for flag in ("-h", "--help"):
        box = Box.fresh(root / "usage", flag)
        p = box.run(flag)
        check(
            p.returncode == 0
            and p.stdout.startswith("usage: agentbox <frontend>")
            and p.stderr == ""
            and box.argv() is None,
            f"agentbox {flag} prints the usage to stdout and exits 0: {p.returncode}, {p.stdout[:60]!r}",
        )


def shell_finds(name: str, env: dict[str, str], cwd: pathlib.Path) -> str:
    """What `command -v <name>` prints in /bin/sh with the environment `env`, in `cwd`."""
    return subprocess.run(
        ["/bin/sh", "-c", f"command -v {name}"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=60,
        check=False,
    ).stdout.strip()


def resolution_cases(check: Check, root: pathlib.Path) -> None:
    """The program that sandbox/agentbox gives srt: for each frontend, the first on the caller's
    PATH without the cmux-cli-shims entries, with the caller's PATH passed on; an entry whose name
    only ends in cmux-cli-shims stays; a program in the working directory that is not on the PATH
    is not found; a relative PATH entry and an exported bash function, each checked against what
    this machine's /bin/sh makes of it."""
    for name in ("claude", "opencode", "omp", "agy"):
        box = Box.fresh(root / "cmux", name)
        shims = box.home / "x" / "cmux-cli-shims"
        stub(shims / "A" / name)
        stub(shims / name)
        path = f"{shims}/A:{shims}:/usr/bin:/bin:{box.home}/path"
        p = box.run(name, PATH=path)
        got = box.argv()
        seen = box.environment() if got is not None else {}
        check(
            p.returncode == 0
            and got is not None
            and got[3] == f"{box.home}/path/{name}"
            and seen.get("PATH") == path,
            f"agentbox {name} with x/cmux-cli-shims/A/{name} and x/cmux-cli-shims/{name} first on the PATH "
            f"and path/ last: srt gets path/{name}, and the program the caller's PATH: {p.returncode}, "
            f"{got[3] if got else None}, {seen.get('PATH')!r}, {p.stderr!r}",
        )

    box = Box.fresh(root, "near-names")
    near = [box.home / "x" / "not-cmux-cli-shims", box.home / "x" / "not-cmux-cli-shims" / "A"]
    for entry in near:
        stub(entry / "omp")
    for entry in near:
        p = box.run("omp", PATH=f"{entry}:{box.home}/path:/usr/bin:/bin")
        got = box.argv()
        check(
            p.returncode == 0 and got is not None and got[3] == f"{entry}/omp",
            f"agentbox omp with {entry.relative_to(box.home)}/omp first on the PATH, an entry that only "
            f"ends in a name like cmux-cli-shims: srt gets it: {p.returncode}, {got[3] if got else None}",
        )

    box = Box.fresh(root, "working-directory")
    stub(box.home / "claude")
    p = box.run("claude", cwd=box.home)
    got = box.argv()
    check(
        p.returncode == 0 and got is not None and got[3] == f"{box.home}/path/claude",
        f"agentbox claude in a directory that holds a program claude, which is not on the PATH: srt gets "
        f"path/claude: {p.returncode}, {got[3] if got else None}, {p.stderr!r}",
    )

    box = Box.fresh(root, "relative")
    stub(box.home / "rel" / "omp")
    path = f"rel:{box.home}/path:/usr/bin:/bin"
    found = shell_finds("omp", {"PATH": path}, box.home)
    p = box.run("omp", cwd=box.home, PATH=path)
    got = box.argv()
    if found.startswith("/"):
        check(
            p.returncode == 0
            and got is not None
            and pathlib.Path(got[3]).resolve() == (box.home / "rel" / "omp").resolve(),
            f"agentbox omp with rel/omp on the PATH, where /bin/sh gives the absolute path {found}: "
            f"srt gets it: {p.returncode}, {got[3] if got else None}, {p.stderr!r}",
        )
    else:
        check(
            p.returncode == REFUSED
            and got is None
            and p.stderr.count("\n") == 1
            and "omp" in p.stderr
            and "rel/omp" in p.stderr
            and not box.made(),
            f"agentbox omp with rel/omp on the PATH, where /bin/sh gives the relative {found!r}: exits 2, "
            f"starts no srt and names omp and rel/omp: {p.returncode}, {got}, {p.stderr!r}",
        )

    box = Box.fresh(root, "function")
    function = {"BASH_FUNC_claude%%": "() { :; }"}
    found = shell_finds("claude", {"PATH": box.env()["PATH"], **function}, box.home)
    p = box.run("claude", variables=function)
    got = box.argv()
    if found == "claude":
        check(
            p.returncode == REFUSED
            and got is None
            and p.stderr.count("\n") == 1
            and "claude" in p.stderr
            and not box.made(),
            f"agentbox claude with an exported function BASH_FUNC_claude%%, which /bin/sh imports: exits 2 "
            f"and starts no srt: {p.returncode}, {got}, {p.stderr!r}",
        )
    else:
        check(
            p.returncode == 0 and got is not None and got[3] == f"{box.home}/path/claude",
            f"agentbox claude with an exported function BASH_FUNC_claude%%, which /bin/sh does not import "
            f"({found!r}): srt gets path/claude: {p.returncode}, {got[3] if got else None}, {p.stderr!r}",
        )


def cache_cases(check: Check, root: pathlib.Path) -> None:
    """The cache variables of a run: a caller's non-empty value stays, an empty one is replaced;
    with TMPDIR empty, the run directory is below /tmp."""
    for label, given in [
        (
            "npm_config_cache=/c, UV_CACHE_DIR and TEXMFVAR empty",
            {"npm_config_cache": "/c", "UV_CACHE_DIR": "", "TEXMFVAR": ""},
        ),
        (
            "npm_config_cache empty, UV_CACHE_DIR=/u and TEXMFVAR=/t",
            {"npm_config_cache": "", "UV_CACHE_DIR": "/u", "TEXMFVAR": "/t"},
        ),
    ]:
        box = Box.fresh(root, label.replace(" ", "-").replace("/", "-").replace("=", "-").replace(",", ""))
        p = box.run("claude", variables=given)
        seen = box.environment() if box.argv() is not None else {}
        caches = box.caches()
        want = {k: given[k] if given.get(k) else caches.get(k) for k in CACHES}
        check(
            p.returncode == 0 and caches and {k: seen.get(k) for k in CACHES} == want,
            f"agentbox claude with {label}: a non-empty value stays, the others name the run's "
            f"subdirectories: {p.returncode}, { {k: seen.get(k) for k in CACHES} }, {box.made()}",
        )

    box = Box.fresh(root, "no-tmpdir")
    p = box.run("agy", TMPDIR="")
    seen = box.environment() if box.argv() is not None else {}
    values = [seen[k] for k in CACHES if k in seen]
    run = pathlib.PurePosixPath(values[0] if values else "/nothing").parent
    made = pathlib.Path(run)
    below_tmp = run.parent == FALLBACK_TMPDIR and run.name.startswith("agentbox.")
    check(
        p.returncode == 0
        and below_tmp
        and all(seen.get(k) == f"{run}/{sub}" and (made / sub).is_dir() for k, sub in CACHES.items()),
        f"agentbox agy with TMPDIR empty makes its run directory below /tmp: {p.returncode}, "
        f"{ {k: seen.get(k) for k in CACHES} }",
    )
    if below_tmp and made.is_dir():
        shutil.rmtree(made)


def agentbox_refusals() -> list[
    tuple[str, Callable[[pathlib.Path], object], list[str], dict[str, str], list[str]]
]:
    """Each refusal of sandbox/agentbox: (label, a change of the home, the arguments, extra
    variables, the words of its line, with <home> for the home directory)."""
    frontends_named = ["claude", "opencode", "omp", "agy"]
    srt = "<home>/.local/bin/srt"

    def nothing(_: pathlib.Path) -> None:
        return None

    def remove(*parts: str) -> Callable[[pathlib.Path], object]:
        return lambda h: h.joinpath(*parts).unlink()

    def directory(*parts: str) -> Callable[[pathlib.Path], object]:
        def change(h: pathlib.Path) -> None:
            h.joinpath(*parts).unlink()
            h.joinpath(*parts).mkdir()

        return change

    sandbox_dir = str(DIRECTORY)
    return [
        ("no argument", nothing, [], {}, ["no frontend named", *frontends_named]),
        ("an unknown name", nothing, ["vim"], {}, ["unknown frontend", *frontends_named]),
        ("an empty name", nothing, [""], {}, ["unknown frontend", *frontends_named]),
        ("AGENTBOX=1", nothing, ["claude"], {"AGENTBOX": "1"}, ["AGENTBOX"]),
        ("AGENTBOX set and empty", nothing, ["omp"], {"AGENTBOX": ""}, ["AGENTBOX"]),
        ("no srt", remove(".local", "bin", "srt"), ["claude"], {}, [srt, "harness setup"]),
        (
            "an srt that is not executable",
            lambda h: (h / ".local" / "bin" / "srt").chmod(0o644),
            ["omp"],
            {},
            [srt, "harness setup"],
        ),
        (
            "an srt that is a directory",
            directory(".local", "bin", "srt"),
            ["agy"],
            {},
            [srt, "harness setup"],
        ),
        (
            "no omp.json",
            remove(sandbox_dir, "omp.json"),
            ["omp"],
            {},
            [f"<home>/{sandbox_dir}/omp.json", "harness install --apply"],
        ),
        (
            "agy and no antigravity.json",
            remove(sandbox_dir, "antigravity.json"),
            ["agy"],
            {},
            [f"<home>/{sandbox_dir}/antigravity.json", "harness install --apply"],
        ),
        (
            "a claude.json that is a directory",
            directory(sandbox_dir, "claude.json"),
            ["claude"],
            {},
            [f"<home>/{sandbox_dir}/claude.json", "harness install --apply"],
        ),
        (
            "claude and no override",
            remove(sandbox_dir, "claude-inner-off.json"),
            ["claude"],
            {},
            [f"<home>/{sandbox_dir}/claude-inner-off.json", "harness install --apply"],
        ),
        ("no opencode on the PATH", remove("path", "opencode"), ["opencode"], {}, ["opencode"]),
        (
            "only cmux-cli-shims entries that hold claude",
            lambda h: (
                stub(h / "x" / "cmux-cli-shims" / "A" / "claude"),
                stub(h / "x" / "cmux-cli-shims" / "claude"),
            ),
            ["claude"],
            {"PATH": "<home>/x/cmux-cli-shims/A:<home>/x/cmux-cli-shims:/usr/bin:/bin"},
            ["no program claude"],
        ),
        (
            "a TMPDIR that is a file",
            lambda h: (h / "file").write_text(""),
            ["omp"],
            {"TMPDIR": "<home>/file"},
            ["<home>/file"],
        ),
        ("claude --settings x", nothing, ["claude", "--settings", "x"], {}, ["--settings"]),
        ("claude -p hi --settings=x", nothing, ["claude", "-p", "hi", "--settings=x"], {}, ["--settings"]),
        ("claude -- --settings", nothing, ["claude", "--", "--settings"], {}, ["--settings"]),
    ]


def last_line(text: str) -> str:
    return (text.strip().splitlines() or ["no output"])[-1]


def listed(text: str, label: str, status: str) -> bool:
    """Whether the install output `text` has the line of `label` with `status`."""
    return re.search(rf"(?m)^{re.escape(label)} +{status}$", text) is not None


def columns(text: str) -> set[int]:
    """The columns at which the status starts on each line of the install output `text` that lists a
    file or an environment as INSTALL, REPLACE, already identical or already synced."""
    found = re.finditer(r"(?m)^\S.*?  +(INSTALL|REPLACE|already identical|already synced)$", text)
    return {m.start(1) - m.start() for m in found}


class Installs:
    """`harness install` on scratch HOMEs below `root`, with a $TMPDIR that is a link to a
    directory."""

    def __init__(self, check: Check, root: pathlib.Path):
        self.scratch = install_cases.Scratch(check, root / "scratch")
        self.scratch.tmp.mkdir(parents=True)
        self.real = root / "real-tmp"
        self.real.mkdir()
        self.link = root / "link-tmp"
        self.link.symlink_to(self.real)
        self.run = install_cases.Scratch.run
        self.claude: Any = frontends.adapter("claude")

    def fresh(self, chosen: str, overlay: str | None = None) -> pathlib.Path:
        """A fresh scratch base whose `[setup]` chooses `chosen`, with the network overlay
        `overlay`."""
        base = self.scratch.fresh()[0]
        profile = base / "profile.toml"
        text = profile.read_text()
        head = text[: text.index("\n[setup]\n")]
        profile.write_text(f'{head}\n[setup]\nfrontends = {chosen}\ncomponents = ["julia"]\n')
        if overlay is not None:
            (base / "network.toml").write_text(overlay)
        return base

    def install(
        self, chosen: str, tmpdir: str | None, overlay: str | None = None
    ) -> tuple[pathlib.Path, list[int | None], list[str]]:
        """A fresh base (`fresh`); the exit status and output of a dry run, an --apply and a dry
        run again. A dry run that writes below the sandbox directory gives the status None."""
        base = self.fresh(chosen, overlay)
        env = {"TMPDIR": tmpdir}
        runs = [self.run(base, extra_env=env)]
        if (base / "home" / DIRECTORY).exists():
            runs[0] = (None, runs[0][1])
        runs += [self.run(base, "--apply", extra_env=env), self.run(base, extra_env=env)]
        return base, [code for code, _ in runs], [out for _, out in runs]

    def template_sandbox(self, base: pathlib.Path) -> dict[str, object]:
        """The `sandbox` object of the settings template as the profile of `base` renders it."""
        profile = profile_module.load(base / "profile.toml")
        return self.claude.settings_template(profile, base / "network.toml", python="python3")["sandbox"]

    def settings_bytes(self, base: pathlib.Path) -> bytes:
        """The bytes of a new ~/.claude/settings.json on `base`, as the adapter's `settings_file`
        documents them and with no part of the srt settings: the template rendered in the
        environment of the install, its keys of OWNED first, as JSON indented by 2 with a final
        newline."""
        env = cast("Callable[[pathlib.Path], dict[str, str]]", install_cases.Scratch.env)(base)
        with mock.patch.dict(os.environ, env, clear=True):
            template = self.claude.settings_template(
                profile_module.load(base / "profile.toml"), base / "network.toml"
            )
        owned = [k for k in self.claude.OWNED if k in template]
        ordered = {k: template[k] for k in [*owned, *(k for k in template if k not in owned)]}
        return (json.dumps(ordered, indent=2) + "\n").encode()

    def expected(self, base: pathlib.Path, name: str, tmpdir: str | None) -> bytes:
        """The bytes of `name`'s srt file on `base`."""
        obj = srt_settings(name, self.template_sandbox(base), load_policy(POLICY), base / "home", tmpdir)
        return (json.dumps(obj, indent=2) + "\n").encode()


def install_file_cases(check: Check, root: pathlib.Path) -> None:
    """`real_tmpdir` on an unset, an empty and a linked $TMPDIR. Then `harness install` on scratch
    HOMEs whose profile chooses claude and opencode: one file each, of the bytes that
    `srt_settings` gives, with the real path of $TMPDIR, Claude Code's override and the launcher
    of mode 755 (`launcher_installed`), and none after the dry run; a second dry run with no
    change; the Claude Code settings.json byte for byte as `settings_bytes` gives it; and
    `install_change_cases` on that base. With opencode alone and no $TMPDIR, no tmpdir entry, the
    launcher and no override, and the dry run's status column is one for the srt file and the other
    files; with no frontend, no file and no launcher, and a broken network overlay stops nothing.
    With claude chosen and a ~/.local/bin that is a symlink to a directory, the --apply exits 2,
    names it, and writes nothing."""
    installs = Installs(check, root)
    found = {}
    for label, value in [("unset", None), ("empty", ""), ("a link", str(installs.link))]:
        environ = {k: v for k, v in os.environ.items() if k != "TMPDIR"}
        with mock.patch.dict(
            os.environ, environ if value is None else {**environ, "TMPDIR": value}, clear=True
        ):
            found[label] = real_tmpdir()
    check(
        found == {"unset": None, "empty": None, "a link": str(installs.real.resolve())},
        f"real_tmpdir: None for an unset or empty $TMPDIR, the resolved path of a link: {found}",
    )
    base, codes, outs = installs.install('["claude", "opencode"]', str(installs.link))
    directory = base / "home" / DIRECTORY
    names = sorted(p.name for p in directory.iterdir()) if directory.is_dir() else []
    labels = [
        *(f"~/{DIRECTORY}/{name}.json" for name in ("claude", "opencode", "claude-inner-off")),
        "~/.local/bin/agentbox",
    ]
    check(
        codes[:2] == [1, 0] and names == ["claude-inner-off.json", "claude.json", "opencode.json"],
        f"two chosen frontends with claude get two files and Claude Code's override: {codes}, {names}, "
        f"{last_line(outs[1])!r}",
    )
    check(
        names
        and all(
            (directory / name).read_bytes()
            == installs.expected(base, name[: -len(".json")], str(installs.real.resolve()))
            for name in ("claude.json", "opencode.json")
        ),
        "each file holds srt_settings of its frontend as JSON indented by 2, with the real path of $TMPDIR",
    )
    override = directory / "claude-inner-off.json"
    check(
        override.is_file() and override.read_bytes() == b'{"sandbox": {"enabled": false}}\n',
        f"Claude Code's override turns its inner sandbox off: "
        f"{override.read_bytes() if override.is_file() else None!r}",
    )
    check(
        launcher_installed(base),
        "the launcher is ~/.local/bin/agentbox, of the bytes of sandbox/agentbox and mode 755",
    )
    check(
        all(listed(outs[0], label, "INSTALL") for label in labels)
        and codes[2] == 0
        and all(listed(outs[2], label, "already identical") for label in labels),
        f"the dry run lists the four files, and a second dry run reports no change for them: {codes[2]}, "
        f"{last_line(outs[2])!r}",
    )
    check(
        (base / "home" / ".claude" / "settings.json").read_bytes() == installs.settings_bytes(base),
        "the Claude Code settings.json is the template as it renders without the srt settings, byte for byte",
    )
    install_change_cases(check, installs, base)

    base, codes, outs = installs.install('["opencode"]', None)
    written = base / "home" / DIRECTORY / "opencode.json"
    check(
        codes[1] == 0
        and written.is_file()
        and written.read_bytes() == installs.expected(base, "opencode", None),
        f"with no $TMPDIR, the file has no tmpdir entry: {codes}, {last_line(outs[1])!r}",
    )
    check(
        launcher_installed(base) and not (base / "home" / DIRECTORY / "claude-inner-off.json").exists(),
        "opencode alone gets the launcher with mode 755 and no override of Claude Code",
    )
    check(
        listed(outs[0], f"~/{DIRECTORY}/opencode.json", "INSTALL") and len(columns(outs[0])) == 1,
        f"the dry run starts the status of the srt file and of every other file in one column: "
        f"{sorted(columns(outs[0]))}",
    )

    base, codes, outs = installs.install("[]", str(installs.link), overlay='allow = ["https://x.org"]\n')
    check(
        codes == [0, 0, 0]
        and not (base / "home" / DIRECTORY).exists()
        and not (base / "home" / ".local" / "bin" / "agentbox").exists(),
        f"no chosen frontend: no sandbox file, no launcher, and a broken network overlay stops nothing: "
        f"{codes}, {last_line(outs[1])!r}",
    )

    base = installs.fresh('["claude"]')
    linked = base / "linked"
    linked.mkdir()
    (base / "home" / ".local").mkdir(parents=True, exist_ok=True)
    (base / "home" / ".local" / "bin").symlink_to(linked)
    code, out = installs.run(base, "--apply", extra_env={"TMPDIR": str(installs.link)})
    check(
        code == REFUSED
        and "Traceback" not in out
        and ".local/bin" in out
        and "symlink" in out
        and not any(linked.iterdir())
        and not (base / "home" / DIRECTORY).exists()
        and not (base / "home" / ".claude" / "settings.json").exists(),
        f"claude chosen and a ~/.local/bin that is a symlink to a directory: the --apply exits 2, names "
        f"it and writes nothing: {code}, {last_line(out)!r}, {sorted(p.name for p in linked.iterdir())}",
    )


def launcher_installed(base: pathlib.Path) -> bool:
    """Whether the home of `base` holds ~/.local/bin/agentbox with the bytes of sandbox/agentbox and
    mode 755."""
    launcher = base / "home" / ".local" / "bin" / "agentbox"
    return (
        launcher.is_file()
        and (REPO / "sandbox" / "agentbox").is_file()
        and launcher.read_bytes() == (REPO / "sandbox" / "agentbox").read_bytes()
        and stat.S_IMODE(launcher.stat().st_mode) == LAUNCHER_MODE
    )


def install_change_cases(check: Check, installs: Installs, base: pathlib.Path) -> None:
    """On `base`, installed with claude and opencode: an edited srt file alone is one change, and
    an --apply prints no restart line; a launcher of mode 644 is one change, which the --apply
    sets to 755. On a fresh base, a directory at an srt file stops an --apply before anything is
    written."""
    directory = base / "home" / DIRECTORY
    (directory / "claude.json").write_text("{}\n")
    env = {"TMPDIR": str(installs.link)}
    dry, dry_out = installs.run(base, extra_env=env)
    applied, applied_out = installs.run(base, "--apply", extra_env=env)
    after = applied_out[applied_out.find("change(s) made.") :].splitlines()[1:]
    check(
        dry == 1
        and "\n1 change(s) to make." in dry_out
        and listed(dry_out, f"~/{DIRECTORY}/claude.json", "REPLACE")
        and applied == 0
        and "\n1 change(s) made." in applied_out
        and not [line for line in after if line.strip()],
        f"an edited srt file alone is one change, and an --apply prints no restart line: {dry}, {applied}, "
        f"{after}",
    )
    launcher = base / "home" / ".local" / "bin" / "agentbox"
    if launcher.is_file():
        launcher.chmod(0o644)
    dry, dry_out = installs.run(base, extra_env=env)
    applied, applied_out = installs.run(base, "--apply", extra_env=env)
    check(
        dry == 1
        and listed(dry_out, "~/.local/bin/agentbox", "MODE 0644 -> 0755")
        and applied == 0
        and launcher_installed(base),
        f"a launcher of mode 644 is one change, and the --apply gives it mode 755 again: {dry}, {applied}, "
        f"{last_line(dry_out)!r}",
    )
    other = installs.fresh('["claude", "opencode"]')
    (other / "home" / DIRECTORY / "opencode.json").mkdir(parents=True)
    code, out = installs.run(other, "--apply", extra_env=env)
    check(
        code == REFUSED
        and "Traceback" not in out
        and "is a directory" in out
        and not (other / "home" / DIRECTORY / "claude.json").exists()
        and not (other / "home" / ".local" / "bin" / "agentbox").exists()
        and not (other / "home" / ".claude" / "settings.json").exists(),
        f"a directory at an srt file stops the --apply before anything is written: {code}, "
        f"{last_line(out)!r}",
    )
