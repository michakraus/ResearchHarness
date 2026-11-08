"""The `srt` settings of each CLI frontend, rendered from the `sandbox` section of the Claude Code
settings and from sandbox/policy.toml.

`srt` reads one settings file. `harness install` writes one per frontend that the profile's
`[setup]` chooses, `~/.config/research-harness/sandbox/<frontend>.json` (`plan_files`). The
template's `sandbox` section stays the source of the shared lists; the policy file holds only what
`srt` adds: the read limit's `allow` list, and per frontend its `state` paths, its extra
`deny_write` paths and its `own` paths, the template's deny entries that it reads and writes
itself.

`srt_settings` gives one frontend's object, as docs/src/components/sandbox.md describes:

  network.allowedDomains     the template's, in order
  network.deniedDomains      the template's, or [] where it has none: srt refuses a file without it
  network.allowLocalBinding  the template's
  filesystem.allowWrite      the template's, without each entry at or below another frontend's
                             `state` path; then the frontend's `state`; then `tmpdir`, when given
  filesystem.denyWrite       the template's, without the frontend's `own`; then its `deny_write`
  filesystem.denyRead        the home directory; then the template's; then each path of
                             `credentials.files`; without the frontend's `own`
  filesystem.allowRead       the policy's `read.allow`; then the frontend's `state`

Every `~` and `~/` prefix becomes the home directory, a list holds no entry twice, and the first
occurrence keeps its place. "At or below" compares whole path components. Nothing runs under
`srt` yet; the files are what a launcher passes to it.

The module has no subcommand; its cases run in `harness test`.
"""

import copy
import json
import os
import pathlib
import re
import tempfile
import tomllib
import types
from collections.abc import Callable, Mapping, Sequence
from dataclasses import FrozenInstanceError, dataclass
from typing import Any, cast
from unittest import mock

from . import REPO, HarnessError, frontends, install_cases, jsonio
from . import profile as profile_module

POLICY = REPO / "sandbox" / "policy.toml"
# The directory of the installed files, relative to the home directory.
DIRECTORY = pathlib.PurePosixPath(".config", "research-harness", "sandbox")
LISTS = ("state", "deny_write", "own")


@dataclass(frozen=True)
class ReadPolicy:
    """The read limit's paths that every frontend reads."""

    allow: tuple[str, ...]


@dataclass(frozen=True)
class FrontendPolicy:
    """One frontend's paths of the policy file."""

    state: tuple[str, ...]
    deny_write: tuple[str, ...]
    own: tuple[str, ...]


@dataclass(frozen=True)
class Policy:
    """sandbox/policy.toml: the read limit, and each frontend of FRONTENDS by its name."""

    read: ReadPolicy
    frontends: Mapping[str, FrontendPolicy]


def load_policy(path: pathlib.Path) -> Policy:
    """The policy file at `path`. Exits 2, naming the key or the path, on a file that cannot be
    read or is not TOML, an unknown key, a missing key or frontend, a value that is not a list of
    strings, and a path that does not start with `~/`."""
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
    tables = {name: table(path, f"frontend.{name}.", named[name], LISTS) for name in frontends.FRONTENDS}
    return Policy(
        read=ReadPolicy(allow=paths(path, "read.allow", read["allow"])),
        frontends=types.MappingProxyType(
            {
                name: FrontendPolicy(*(paths(path, f"frontend.{name}.{key}", t[key]) for key in LISTS))
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
    list of strings that each start with `~/`."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in cast("list[object]", value)):
        raise HarnessError(f"{path}: {key} is not a list of strings")
    entries = cast("list[str]", value)
    if wrong := [p for p in entries if not p.startswith("~/")]:
        raise HarnessError(f"{path}: {key} entry {wrong[0]!r} does not start with ~/")
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
    state, own = expanded(mine.state), set(expanded(mine.own))
    others = expanded([p for name, f in policy.frontends.items() if name != frontend for p in f.state])
    binding = section(sandbox, "network").get("allowLocalBinding")
    if not isinstance(binding, bool):
        raise HarnessError("the sandbox object's network.allowLocalBinding is not true or false")
    allow_write = [p for p in expanded(strings(sandbox, "filesystem", "allowWrite")) if not below(p, others)]
    deny_write = [p for p in expanded(strings(sandbox, "filesystem", "denyWrite")) if p not in own]
    deny_read = [
        str(home),
        *expanded(strings(sandbox, "filesystem", "denyRead")),
        *expanded(credential_paths(sandbox)),
    ]
    return {
        "network": {
            "allowedDomains": strings(sandbox, "network", "allowedDomains"),
            "deniedDomains": strings(sandbox, "network", "deniedDomains", default=[]),
            "allowLocalBinding": binding,
        },
        "filesystem": {
            "allowWrite": unique([*allow_write, *state, *([tmpdir] if tmpdir is not None else [])]),
            "denyWrite": unique([*deny_write, *expanded(mine.deny_write)]),
            "denyRead": unique([p for p in deny_read if p not in own]),
            "allowRead": unique([*expanded(policy.read.allow), *state]),
        },
    }


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
) -> list[tuple[pathlib.Path, bytes, None, str]]:
    """The files of `harness install` for the frontends of `chosen`, in the order of FRONTENDS:
    [(destination, bytes, None, label)], each `srt_settings` of the frontend on the `sandbox`
    object of the Claude Code settings that `profile` and the network overlay `overlay` render,
    as JSON indented by 2, the keys in the order built, with a final newline. With no frontend
    chosen it renders nothing, so an overlay that the install does not read stops nothing."""
    names = [name for name in frontends.FRONTENDS if name in chosen]
    if not names:
        return []
    policy = load_policy(POLICY)
    claude: Any = frontends.adapter("claude")
    sandbox = cast("dict[str, object]", claude.settings_template(profile, overlay)["sandbox"])
    return [
        (
            home / DIRECTORY / f"{name}.json",
            (json.dumps(srt_settings(name, sandbox, policy, home, tmpdir), indent=2) + "\n").encode(),
            None,
            f"~/{DIRECTORY}/{name}.json",
        )
        for name in names
    ]


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

[frontend.opencode]
state = ["~/.local/share/opencode"]
deny_write = ["~/.local/share/opencode/x"]
own = []

[frontend.omp]
state = ["~/.omp"]
deny_write = []
own = []

[frontend.antigravity]
state = ["~/.gemini"]
deny_write = []
own = []
"""


def fixture_sandbox() -> dict[str, Any]:
    """A `sandbox` object for the cases: a name that shares a prefix with a state path
    (`~/.claudex`), a credential path that `denyRead` holds and one that it lacks, a glob, the
    home directory itself, and an absolute path."""
    return {
        "enabled": True,
        "network": {
            "allowedDomains": ["b.org", "a.org"],
            "deniedDomains": ["x.org"],
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
            "denyRead": ["~", "~/.ssh", "~/.claude.json"],
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
    """The shipped policy, each refusal of `load_policy`, and each rule of `srt_settings` on a
    fixture and on the settings template: (cases, wrong). The cases of `harness install` on
    scratch HOMEs, `install_file_cases`, run in the selftest of install.py."""
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
        and {"~/.omp/agent/config.yml", "~/.omp/agent/extensions"} <= set(policy.frontends["omp"].deny_write)
        and policy.frontends["claude"].own == ("~/.claude.json",),
        f"sandbox/policy.toml loads with the four frontends and their paths: {sorted(policy.frontends)}",
    )
    try:
        policy.read.__setattr__("allow", ())
        frozen = False
    except FrozenInstanceError:
        frozen = True
    check(frozen, "the policy is a frozen dataclass")

    text = FIXTURE_POLICY
    for label, body, words in [
        ("no [frontend.antigravity]", text[: text.index("[frontend.antigravity]")], ["frontend.antigravity"]),
        ("a key alow", text.replace("allow =", "alow =", 1), ["read.alow"]),
        ("no read.allow", text.replace('allow = ["~/Research", "~/.config"]\n', "", 1), ["read.allow"]),
        ("a top-level key of its own", "extra = 1\n" + text, ["extra"]),
        ("read that is no table", text.replace("[read]\nallow =", "read =", 1), ["read is not a table"]),
        (
            "a frontend of no adapter",
            text + "[frontend.other]\nstate = []\ndeny_write = []\nown = []\n",
            ["frontend.other"],
        ),
        ("a key stat", text.replace('state = ["~/.omp"]', 'stat = ["~/.omp"]', 1), ["frontend.omp.stat"]),
        ("no deny_write", text.replace("deny_write = []\n", "", 1), ["frontend.claude.deny_write"]),
        ("a path /etc in read.allow", text.replace('"~/Research"', '"/etc"', 1), ["read.allow", "/etc"]),
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
    check(list(claude) == ["network", "filesystem"], f"the keys are network and filesystem: {list(claude)}")
    check(
        claude["network"]
        == {"allowedDomains": ["b.org", "a.org"], "deniedDomains": ["x.org"], "allowLocalBinding": True},
        f"network is the template's domains in order and its allowLocalBinding: {claude['network']}",
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
        ("claude", fs, "denyRead", ["/h", "/h/.ssh", "/h/.netrc"]),
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
        ("opencode", opencode, "denyRead", ["/h", "/h/.ssh", "/h/.claude.json", "/h/.netrc"]),
        ("opencode", opencode, "allowRead", ["/h/Research", "/h/.config", "/h/.local/share/opencode"]),
    ]:
        check(got[key] == want, f"{name}'s {key}: {got[key]}")

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
        counts = {c: fs["denyRead"].count(c) for c in credentials}
        check(
            all(k == (0 if c in mine else 1) for c, k in counts.items()),
            f"{name}: each credential path is a read deny once, its own none: "
            f"{ {c: k for c, k in counts.items() if k != 1} }",
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

    def expected(self, base: pathlib.Path, name: str, tmpdir: str | None) -> bytes:
        """The bytes of `name`'s srt file on `base`."""
        obj = srt_settings(name, self.template_sandbox(base), load_policy(POLICY), base / "home", tmpdir)
        return (json.dumps(obj, indent=2) + "\n").encode()


def install_file_cases(check: Check, root: pathlib.Path) -> None:
    """`real_tmpdir` on an unset, an empty and a linked $TMPDIR. Then `harness install` on scratch
    HOMEs whose profile chooses claude and opencode: one file each, of the bytes that
    `srt_settings` gives, with the real path of $TMPDIR, and none after the dry run; a second dry
    run with no change; the Claude Code settings' `sandbox` as the template renders it; and
    `install_change_cases` on that base. With no $TMPDIR, no tmpdir entry, and the dry run's
    status column is one for the srt file and the other files; with no frontend, no file, and a
    broken network overlay stops nothing."""
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
    labels = [f"~/{DIRECTORY}/{name}.json" for name in ("claude", "opencode")]
    check(
        codes[:2] == [1, 0] and names == ["claude.json", "opencode.json"],
        f"two chosen frontends get two files: {codes}, {names}, {last_line(outs[1])!r}",
    )
    check(
        names
        and all(
            (directory / name).read_bytes()
            == installs.expected(base, name[: -len(".json")], str(installs.real.resolve()))
            for name in names
        ),
        "each file holds srt_settings of its frontend as JSON indented by 2, with the real path of $TMPDIR",
    )
    check(
        all(listed(outs[0], label, "INSTALL") for label in labels)
        and codes[2] == 0
        and all(listed(outs[2], label, "already identical") for label in labels),
        f"the dry run lists both files, and a second dry run reports no change for them: {codes[2]}, "
        f"{last_line(outs[2])!r}",
    )
    settings = cast("dict[str, Any]", jsonio.load(base / "home" / ".claude" / "settings.json"))
    check(
        settings["sandbox"] == installs.template_sandbox(base),
        "the Claude Code settings hold the template's sandbox section as it renders",
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
        listed(outs[0], f"~/{DIRECTORY}/opencode.json", "INSTALL") and len(columns(outs[0])) == 1,
        f"the dry run starts the status of the srt file and of every other file in one column: "
        f"{sorted(columns(outs[0]))}",
    )

    base, codes, outs = installs.install("[]", str(installs.link), overlay='allow = ["https://x.org"]\n')
    check(
        codes == [0, 0, 0] and not (base / "home" / DIRECTORY).exists(),
        f"no chosen frontend: no sandbox file, and a broken network overlay stops nothing: {codes}, "
        f"{last_line(outs[1])!r}",
    )


def install_change_cases(check: Check, installs: Installs, base: pathlib.Path) -> None:
    """On `base`, installed with claude and opencode: an edited srt file alone is one change, and
    an --apply prints no restart line. On a fresh base, a directory at an srt file stops an
    --apply before anything is written."""
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
    other = installs.fresh('["claude", "opencode"]')
    (other / "home" / DIRECTORY / "opencode.json").mkdir(parents=True)
    code, out = installs.run(other, "--apply", extra_env=env)
    check(
        code == REFUSED
        and "Traceback" not in out
        and "is a directory" in out
        and not (other / "home" / DIRECTORY / "claude.json").exists()
        and not (other / "home" / ".claude" / "settings.json").exists(),
        f"a directory at an srt file stops the --apply before anything is written: {code}, "
        f"{last_line(out)!r}",
    )
