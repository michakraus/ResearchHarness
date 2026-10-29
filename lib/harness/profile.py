"""The private profile, and the render of a harness template with it.

    harness render TEMPLATE    # print the rendered text
    harness get KEY            # print a profile value, one line per item
    harness leaks              # the repository and its renders hold no private string
    harness leaks --commits F  # nor does a line that a commit of F adds or its message, one SHA per line
    harness test               # the render's own cases, with every other module's

The profile is a TOML file of every value that names a person, an institution or a machine:
`harness --profile F`, else $RESEARCH_HARNESS_PROFILE, else ~/.config/research-harness/profile.toml.
`examples/profile.toml` is a dummy that shows every key. `load` gives a `Profile`, a frozen
dataclass. The keys of REQUIRED must be there, and every key is one of REQUIRED or OPTIONAL, of
its type, and a required list is not empty; any other profile exits 2 with one line that names the
file, the key and, but for an unknown key, the type, and a retired key with the step that
replaces it (`checked`). `home` is optional: the running user's home directory without it. A
string value that is `~` or starts with `~/`, an item of a list too, means `home`
(`expand_home`).

The model tables load into frozen dataclasses too: `read_models` checks the shape and the types of
every table, refuses a table or a key that no frontend reads, and gives `Models`; `model_tables`
gives one frontend's `ModelTables`. Every table is optional and empty without it; an adapter
refuses one that its frontend needs.

A placeholder is `{name}`: lower case, digits and `_`, no colon, so OpenCode's `{env:…}` and
`{file:…}` pass through. `name` is a key of the values that the template renders with: the
profile's (`context`), or a case's own mapping. A string value substitutes. A list value
repeats what holds it, once per item in profile order, and removes it for an empty list: in a
parsed JSON list (`render_data`) the string element, in text (`render_text`) the line, which must
then end in a comma. A table value renders in text only, on a line that holds the placeholder
alone: the members of a JSON object, at that line's indentation, with no comma after the last.
More than one list placeholder in one element or line is an error, and so is
a placeholder that the profile does not define: a template that renders with a hole in it is a
grant or a deny that silently matches nothing; an optional string that the profile leaves unset
is no value (`values`). The render-only `providers` is no key of the profile: `harness install`
fills it from providers.toml, and `render` and `leaks` give it as {}, so that the template renders
no provider (`context`). `autocommit_branch` is never missing: without it, `load` gives `main` on
the machine whose short host name is `template_host` or without `template_host`, and
`memory/<short host name>` on every other (`branch_default`).
`develop`, optional, is true or false, false without it: with true, `harness install --apply` adds
the `dev` group of uv.lock to the Python environment; any other value exits 2.
`render` of the settings template also generates its network rules from `settings/network.toml`
and the overlay `network.toml` beside the profile (`network.py`).

`leaks` also searches the repository, not the renders, for a name of the research tree: every
directory below a `repository_roots` entry, read when it runs, and every `org` entry. It matches
a whole word, as `git grep -w` does. The repository's own `owner/name`, from its `origin` URL,
and the host of its GitHub Pages site, `owner.github.io`, are the allowed occurrences. With
`--commits F` it also searches, for both, the paths and the lines that each commit of F adds
(`git show --format= --text -U0`), so a leak that a later commit removes or renames away is still
a hit, and the message of each commit (`git show -s --format=%B`,
the subject and the body, trailers too), a hit at `<sha12> message:<n>` with `n` from 1; gitleaks
reads no message. The author, the committer, a tag message and `git notes` are not searched. The
pre-push hook passes the commits that a push sends.
"""

import argparse
import contextlib
import dataclasses
import io
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import tomllib
import types
from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast
from unittest import mock

from . import REPO, HarnessError, fmt, frontends, frontmatter, network

DEFAULT = pathlib.Path.home() / ".config" / "research-harness" / "profile.toml"
DUMMY = REPO / "examples" / "profile.toml"
# A home directory of the dummy that is not the running user's: `leaks` renders the templates
# with the dummy under it, because the user's `leak` list names the running user's home, and the
# scratch profiles of the install cases set it.
DUMMY_HOME = "/home/example"
# The host name under which `leaks` renders the dummy, for the same reason: the dummy's
# `autocommit_branch` names the host, and the user's `leak` list may name the running one.
DUMMY_HOST = "example-other"

PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
# A line that holds one placeholder alone, after its indentation.
ALONE = re.compile(r"( *)\{([a-z][a-z0-9_]*)\}\n?")

# The templates that `leaks` renders with the dummy profile, relative to the repository, with
# the TEMPLATES of each adapter.
TEMPLATES = [
    "settings/settings.proposal.json",
    "launchagents/kaimon.plist",
    "launchagents/julia-update.plist",
    "launchagents/claude-autocommit.plist",
    "systemd/kaimon.service",
    "systemd/julia-update.service",
    "systemd/julia-update.timer",
    "systemd/claude-autocommit.service",
    "systemd/claude-autocommit.timer",
]


@dataclasses.dataclass(frozen=True, slots=True)
class Profile:
    """The profile, as `load` gives it: every value with `~` expanded. A list is a tuple. Without
    its key, `home`, `harness` and `autocommit_branch` have the values that `load` gives,
    `template_host` and `launchd_prefix` are "", `develop` is false, and an optional list is ()."""

    home: str
    harness: str
    memory_project: str
    tree_agents: str
    org: tuple[str, ...]
    repository_roots: tuple[str, ...]
    leak: tuple[str, ...]
    autocommit_branch: str
    template_host: str = ""
    launchd_prefix: str = ""
    develop: bool = False
    docs_exceptions: tuple[str, ...] = ()
    docs_additions: tuple[str, ...] = ()
    protected_dir: tuple[str, ...] = ()


# The words of the expected type in a refusal.
STRING, LIST, NONEMPTY, BOOL = "a string", "a list of strings", "a non-empty list of strings", "true or false"
# The keys of the profile, each with its type. A required list holds one item or more.
REQUIRED = {
    "memory_project": STRING,
    "tree_agents": STRING,
    "org": NONEMPTY,
    "repository_roots": NONEMPTY,
    "leak": NONEMPTY,
}
OPTIONAL = {
    "home": STRING,
    "harness": STRING,
    "template_host": STRING,
    "autocommit_branch": STRING,
    "launchd_prefix": STRING,
    "develop": BOOL,
    "docs_exceptions": LIST,
    "docs_additions": LIST,
    "protected_dir": LIST,
}

# A value of a template's placeholder: a string, a list of strings, or a table, which renders as
# the members of a JSON object.
type Value = str | list[str] | Mapping[str, object]
# The values that a template renders with, by name: a profile's (`context`), or a case's own.
type Context = Mapping[str, Value]


def location(path: str | os.PathLike[str] | None = None) -> pathlib.Path:
    """The path of the profile: `path`, else the environment's, else the default path."""
    return pathlib.Path(path or os.environ.get("RESEARCH_HARNESS_PROFILE") or DEFAULT)


def load(
    path: str | os.PathLike[str] | None = None, home: str | None = None, host: str | None = None
) -> Profile:
    """The profile at `path`, else the environment's, else the default path, checked against the
    keys of REQUIRED and OPTIONAL (`checked`), with `~` expanded (`expand_home`) and
    `autocommit_branch` set (`branch_default`); `home` is the home directory of a profile that
    names none, the running user's by default, and `host` the host name, the running machine's by
    default. `harness` is this checkout without the key."""
    path = location(path)
    if not path.is_file():
        raise HarnessError(f"no profile at {path} — copy examples/profile.toml there and fill it in")
    try:
        data = tomllib.loads(path.read_bytes().decode("utf-8"))
    except UnicodeDecodeError:
        raise HarnessError(f"{path} is not UTF-8") from None
    except tomllib.TOMLDecodeError as e:
        raise HarnessError(f"{path} is not TOML: {e}") from None
    strings, lists, develop = checked(data, path)
    strings, lists = expand_home(strings, lists, path, home)
    return Profile(
        home=strings["home"],
        harness=strings.get("harness", str(REPO)),
        memory_project=strings["memory_project"],
        tree_agents=strings["tree_agents"],
        org=lists["org"],
        repository_roots=lists["repository_roots"],
        leak=lists["leak"],
        autocommit_branch=branch_default(strings, path, host),
        template_host=strings.get("template_host", ""),
        launchd_prefix=strings.get("launchd_prefix", ""),
        develop=develop,
        docs_exceptions=lists.get("docs_exceptions", ()),
        docs_additions=lists.get("docs_additions", ()),
        protected_dir=lists.get("protected_dir", ()),
    )


def checked(
    data: dict[str, Any], path: pathlib.Path
) -> tuple[dict[str, str], dict[str, tuple[str, ...]], bool]:
    """The strings, the lists and `develop` of `data`, the parsed profile at `path`. A retired key
    exits 2 with the step that replaces it; then an unknown key, a table among them, a missing
    key of REQUIRED, a value that is not of its key's type and an empty list of REQUIRED, each
    naming `path`, the key and, but for an unknown key, the type."""
    if "extra_domain" in data:
        raise HarnessError(
            f"{path}: the profile key extra_domain is retired: move its hosts into the allow array of "
            f"{path.parent / 'network.toml'} and remove the key"
        )
    if old := [k for k in ("opencode_providers", "omp_providers") if k in data]:
        raise HarnessError(
            f"{path}: the profile holds {', '.join(old)}, which {path.parent / 'providers.toml'} "
            "replaces: write each provider once there, as examples/providers.toml shows, and remove "
            "the key from the profile"
        )
    if unknown := [k for k in data if k not in REQUIRED and k not in OPTIONAL]:
        raise HarnessError(
            f"{path}: {', '.join(f'`{k}`' for k in unknown)} is no key of the profile; "
            "examples/profile.toml shows every key"
        )
    if missing := [k for k in REQUIRED if k not in data]:
        raise HarnessError(
            f"{path}: the profile has no "
            + ", ".join(f"`{k}`, {REQUIRED[k]}" for k in missing)
            + "; examples/profile.toml shows it"
        )
    strings: dict[str, str] = {}
    lists: dict[str, tuple[str, ...]] = {}
    develop = False
    for key, v in data.items():
        kind = REQUIRED.get(key) or OPTIONAL[key]
        if kind == STRING and isinstance(v, str):
            strings[key] = v
        elif kind == BOOL and isinstance(v, bool):
            develop = v
        elif kind in (LIST, NONEMPTY) and isinstance(v, list):
            items = cast("list[object]", v)
            if not all(isinstance(x, str) for x in items) or (kind == NONEMPTY and not items):
                raise HarnessError(f"{path}: `{key}` is {v!r}, not {kind}")
            lists[key] = tuple(cast("list[str]", items))
        else:
            raise HarnessError(f"{path}: `{key}` is {v!r}, not {kind}")
    return strings, lists, develop


def branch_default(strings: Mapping[str, str], path: pathlib.Path, host: str | None = None) -> str:
    """The `autocommit_branch` of the profile's `strings`: its own, else `main` without
    `template_host` or on the machine whose short host name is `template_host`, else
    `memory/<short host name>`. The short host name is `host`, else `socket.gethostname()`, up to
    its first `.`, as `hostname -s` prints it; it compares exactly, and an empty one gives `main`.
    So one profile works unedited on every machine. A `template_host` that is not a short host
    name, a string that is not empty and holds no `.`, exits 2."""
    template = strings.get("template_host")
    if template is not None and (not template or "." in template):
        raise HarnessError(f"{path}: `template_host` is {template!r}, not a short host name without a `.`")
    if "autocommit_branch" in strings:
        return strings["autocommit_branch"]
    short = (socket.gethostname() if host is None else host).split(".")[0]
    return "main" if template is None or not short or short == template else f"memory/{short}"


def expand_home(
    strings: Mapping[str, str],
    lists: Mapping[str, tuple[str, ...]],
    path: pathlib.Path,
    home: str | None = None,
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    """`strings` with `home` set and `~` expanded, and `lists` with `~` expanded. `home` is the
    profile's own, else `home`, else `pathlib.Path.home()`; it must be an absolute path with no
    `~`, and loses a trailing slash, so that `~/x` never gives `//x`. A string that is exactly
    `~`, or starts with `~/`, as a value or as an item of a list, becomes `home`, or `home` and the
    rest. Any other `~` stays, `~name/x` too. A profile at `path` that breaks a rule of `home`
    exits 2."""
    given = "home" in strings
    if given:
        home = strings["home"]
    elif home is None:
        try:
            home = str(pathlib.Path.home())
        except RuntimeError:
            home = None
    if not (home is not None and "~" not in home and pathlib.PurePath(home).is_absolute()):
        if given:
            raise HarnessError(f"{path}: `home` is {home!r}, not an absolute path without `~`")
        raise HarnessError(
            f"{path}: the home directory is not known ({home!r}); set `home` to an absolute path"
        )
    root = home.rstrip("/") or "/"

    def expanded(v: str) -> str:
        if v == "~":
            return root
        if v.startswith("~/"):
            return root.rstrip("/") + v[1:]
        return v

    out = {k: expanded(v) for k, v in strings.items()}
    out["home"] = root
    return out, {k: tuple(map(expanded, v)) for k, v in lists.items()}


def values(profile: Profile) -> dict[str, str | list[str]]:
    """The values of `profile` by name, as a template and `harness get` read them: each field but
    `develop`, a tuple as a list, and no optional string that the profile leaves unset, so that a
    placeholder of one is an error, as for a key that the profile lacks."""
    out: dict[str, str | list[str]] = {
        "home": profile.home,
        "harness": profile.harness,
        "memory_project": profile.memory_project,
        "tree_agents": profile.tree_agents,
        "org": list(profile.org),
        "repository_roots": list(profile.repository_roots),
        "leak": list(profile.leak),
        "autocommit_branch": profile.autocommit_branch,
        "docs_exceptions": list(profile.docs_exceptions),
        "docs_additions": list(profile.docs_additions),
        "protected_dir": list(profile.protected_dir),
    }
    out |= {
        k: v
        for k, v in (("template_host", profile.template_host), ("launchd_prefix", profile.launchd_prefix))
        if v
    }
    return out


def context(profile: Profile, **extra: Value) -> dict[str, Value]:
    """The render's values of `profile` (`values`), with `extra` over them: the render-only
    `providers`, which `harness install` fills from providers.toml and `render` and `leaks` give as
    {}, so that the template renders no provider."""
    return {**values(profile), **extra}


def rendering(profile: Profile | Context) -> Context:
    """The values that a template renders with: `context` of a profile, else `profile` itself."""
    return context(profile) if isinstance(profile, Profile) else profile


def value(name: str, given: Context, where: str) -> Value:
    if name not in given:
        raise KeyError(f"placeholder {{{name}}} in {where!r}: the profile has no key {name!r}")
    return given[name]


def get(profile: Profile, key: str) -> str | list[str]:
    """The profile's value of `key` (`values`); a missing key is a `HarnessError`."""
    found = values(profile)
    if key not in found:
        raise HarnessError(f"the profile has no key {key!r} — examples/profile.toml shows it")
    return found[key]


def models_path(args: argparse.Namespace) -> pathlib.Path:
    """The model tables: `--models`, else $RESEARCH_HARNESS_MODELS, else models.toml beside the profile."""
    given: str | None = getattr(args, "models", None)
    if given:
        return pathlib.Path(given)
    if os.environ.get("RESEARCH_HARNESS_MODELS"):
        return pathlib.Path(os.environ["RESEARCH_HARNESS_MODELS"])
    profile: str | os.PathLike[str] = args.profile or os.environ.get("RESEARCH_HARNESS_PROFILE") or DEFAULT
    return pathlib.Path(profile).parent / "models.toml"


def network_path(profile: str | os.PathLike[str] | None = None) -> pathlib.Path:
    """The overlay of the network lists: network.toml beside the profile `profile`, else beside
    the profile of `location`."""
    return location(profile).parent / "network.toml"


def providers_path(profile: str | os.PathLike[str] | None = None) -> pathlib.Path:
    """The model providers of OpenCode and oh-my-pi (`providers.py`): providers.toml beside the
    profile `profile`, else beside the profile of `location`."""
    return location(profile).parent / "providers.toml"


@dataclasses.dataclass(frozen=True, slots=True)
class Seat:
    """A seat of a council: a copy of its agent named `name` on `model`; `verify` for the seat
    that also judges each verify round, alone."""

    name: str
    model: str
    verify: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class ModelTables:
    """The tables of MODEL_TABLES of the model tables at `path`: the shared ones, the sub-tables of
    [opencode] or of [omp], or one frontend's, the latter over the shared ones (`model_tables`).
    Each field but `path` is the table of its name, but `tiers`, which is [models], {tier: model}.
    An absent table is empty."""

    path: pathlib.Path
    tiers: Mapping[str, str] = dataclasses.field(default_factory=dict[str, str])
    model_overrides: Mapping[str, str] = dataclasses.field(default_factory=dict[str, str])
    model_variants: Mapping[str, str] = dataclasses.field(default_factory=dict[str, str])
    variants: Mapping[str, str] = dataclasses.field(default_factory=dict[str, str])
    reasoning_effort: Mapping[str, str] = dataclasses.field(default_factory=dict[str, str])
    councils: Mapping[str, tuple[Seat, ...]] = dataclasses.field(default_factory=dict[str, tuple[Seat, ...]])
    context_limits: Mapping[str, int] = dataclasses.field(default_factory=dict[str, int])


@dataclasses.dataclass(frozen=True, slots=True)
class Models:
    """The model tables at `path`, as `read_models` gives them: [claude] and [antigravity], each
    {tier: model}, the sub-table [antigravity.model_overrides], the shared tables, and the
    sub-tables of [opencode] and [omp]. An absent table is empty."""

    path: pathlib.Path
    claude: Mapping[str, str]
    antigravity: Mapping[str, str]
    antigravity_overrides: Mapping[str, str]
    shared: ModelTables
    opencode: ModelTables
    omp: ModelTables


# The old keys of a table of the tiers, Claude Code's names, and the neutral tier of each.
OLD_TIERS = {"opus": "large", "sonnet": "medium", "haiku": "small"}


def parsed_models(path: pathlib.Path) -> dict[str, Any]:
    """The model tables at `path`, parsed; a file that does not exist, cannot be read, is not UTF-8
    or is not TOML exits 2."""
    if not path.is_file():
        raise HarnessError(f"no model tables at {path} — copy examples/models.toml there and fill it in")
    try:
        return tomllib.loads(path.read_bytes().decode("utf-8"))
    except OSError as e:
        raise HarnessError(f"{path} cannot be read: {e.strerror}") from None
    except UnicodeDecodeError:
        raise HarnessError(f"{path} is not UTF-8") from None
    except tomllib.TOMLDecodeError as e:
        raise HarnessError(f"{path} is not TOML: {e}") from None


def old_tier_names(path: pathlib.Path, models: Mapping[str, object]) -> None:
    """Exit 2 when a table of the tiers of `models`, the parsed model tables at `path`, [claude],
    [models], [opencode.models] or [omp.models], has a key of OLD_TIERS: one message names each
    rename of each table, and a missing [claude]."""

    def table(value: object) -> dict[str, object]:
        return cast("dict[str, object]", value) if isinstance(value, dict) else {}

    opencode, omp = table(models.get("opencode")), table(models.get("omp"))
    renames: list[str] = []
    for name, part in [
        ("claude", table(models.get("claude"))),
        ("models", table(models.get("models"))),
        ("omp.models", table(omp.get("models"))),
        ("opencode.models", table(opencode.get("models"))),
    ]:
        if old := [t for t in OLD_TIERS if t in part]:
            renames.append(f"in [{name}] rename " + ", ".join(f"{t} to {OLD_TIERS[t]}" for t in old))
    if renames:
        add = (
            []
            if isinstance(models.get("claude"), dict)
            else ["add a [claude] table of the tiers, which examples/models.toml shows"]
        )
        raise HarnessError(f"{path} names tiers by their old names: " + "; ".join(renames + add))


def read_models(path: str | os.PathLike[str]) -> Models:
    """The model tables at `path`, checked: a file that does not exist, cannot be read, is not
    UTF-8 or is not TOML exits 2, and so does a table of the tiers, [claude], [models],
    [opencode.models] or [omp.models], with a key of OLD_TIERS: one message names each rename of
    each table, and a missing [claude]. Then a tier at the top level, a table that no frontend
    reads, and a value of the wrong shape exit 2, naming `path`, the table and the key (`tiers`,
    `tables`). Every table is optional."""
    path = pathlib.Path(path)
    models = parsed_models(path)
    old_tier_names(path, models)
    if top := [t for t in frontmatter.TIERS if t in models]:
        raise HarnessError(
            f"{path}: the tiers {', '.join(top)} are at the top level; move them into [models]"
        )
    tops = ["claude", "antigravity", *MODEL_TABLES, *SHARING]
    if unknown := sorted(set(models) - set(tops)):
        raise HarnessError(f"{path} has no table {', '.join(unknown)}; it has {', '.join(tops)}")
    data: dict[str, dict[str, Any]] = {}
    for name, table in models.items():
        if not isinstance(table, dict):
            raise HarnessError(f"{path}: [{name}] is not a table")
        data[name] = cast("dict[str, Any]", table)
    claude = tiers(path, "claude", data.get("claude", {}), complete=True)
    agy = data.get("antigravity", {})
    overrides = agy.get("model_overrides", {})
    if not isinstance(overrides, dict):
        raise HarnessError(f"{path}: [antigravity.model_overrides] is not a table of agent = tier")
    if wrong := [a for a, v in cast("dict[str, object]", overrides).items() if not isinstance(v, str)]:
        raise HarnessError(
            f"{path}: [antigravity.model_overrides] {', '.join(wrong)} is not a string that names a tier"
        )
    shared = tables(path, "", {k: v for k, v in data.items() if k in MODEL_TABLES})
    own: dict[str, ModelTables] = {}
    for name in SHARING:
        table = data.get(name, {})
        if top := [t for t in frontmatter.TIERS if t in table]:
            raise HarnessError(
                f"{path}: [{name}] holds the tiers {', '.join(top)}; move them into [models], or "
                f"into [{name}.models] for {name} alone"
            )
        if unknown := sorted(set(table) - set(MODEL_TABLES)):
            raise HarnessError(
                f"{path}: [{name}] has no sub-table {', '.join(unknown)}; it has {', '.join(MODEL_TABLES)}"
            )
        own[name] = tables(path, f"{name}.", table)
    return Models(
        path=path,
        claude=claude,
        antigravity=tiers(path, "antigravity", {k: v for k, v in agy.items() if k != "model_overrides"}),
        antigravity_overrides=cast("dict[str, str]", overrides),
        shared=shared,
        opencode=own["opencode"],
        omp=own["omp"],
    )


def tiers(
    path: pathlib.Path, name: str, table: Mapping[str, object], *, complete: bool = False
) -> dict[str, str]:
    """{tier: model} of the table [`name`], `table`, of the model tables at `path`: the tiers of
    frontmatter.TIERS, each a string that is not blank, and with `complete` every one of them in a
    table that is not empty. Any other key, a missing tier and any other value exit 2."""
    if not table:
        return {}
    names = frontmatter.TIERS
    missing = [t for t in names if t not in table] if complete else []
    unknown = sorted(set(table) - set(names))
    extra = ["model_overrides"] if name == "antigravity" else []
    if missing or unknown:
        raise HarnessError(
            f"{path}: [{name}] holds the tiers {' and '.join([', '.join(names), *extra])}; "
            + "; ".join(
                [f"it has no {', '.join(missing)}, a string that names a model"] * bool(missing)
                + [f"{', '.join(unknown)} is no tier"] * bool(unknown)
            )
        )
    if wrong := [t for t, v in table.items() if not (isinstance(v, str) and v.strip())]:
        raise HarnessError(
            f"{path}: the tier {', '.join(wrong)} of [{name}] is not a string that names a model"
        )
    return cast("dict[str, str]", dict(table))


def tables(path: pathlib.Path, prefix: str, data: Mapping[str, object]) -> ModelTables:
    """The tables of MODEL_TABLES in `data`, the shared ones of the model tables at `path` with the
    `prefix` "", or the sub-tables of [opencode] or [omp] with the prefix `opencode.` or `omp.`.
    Each is a table. A value of `models`, `model_overrides`, `model_variants`, `variants` or
    `reasoning_effort` is a string that is not blank; a context limit is a positive integer; a
    council is a list of one to eight seats {name, model}, at most one of them with `verify =
    true`. Any other value exits 2, naming `path`, the table and the key."""
    parts: dict[str, dict[str, object]] = {}
    for sub in MODEL_TABLES:
        part = data.get(sub, {})
        if not isinstance(part, dict):
            raise HarnessError(f"{path}: [{prefix}{sub}] is not a table")
        parts[sub] = cast("dict[str, object]", part)
    strings: dict[str, dict[str, str]] = {}
    for sub in ("models", "model_overrides", "model_variants", "variants", "reasoning_effort"):
        if wrong := [k for k, v in parts[sub].items() if not (isinstance(v, str) and v.strip())]:
            raise HarnessError(
                f"{path}: the value of {', '.join(wrong)} in [{prefix}{sub}] is not a string that is "
                "not blank"
            )
        strings[sub] = cast("dict[str, str]", parts[sub])
    limits = parts["context_limits"]
    if wrong := [k for k, v in limits.items() if not (type(v) is int and v > 0)]:
        raise HarnessError(
            f"{path}: the value of {', '.join(wrong)} in [{prefix}context_limits] is not a positive integer"
        )
    councils = {
        agent: council(path, f"{prefix}councils.{agent}", seats) for agent, seats in parts["councils"].items()
    }
    return ModelTables(
        path=path,
        tiers=strings["models"],
        model_overrides=strings["model_overrides"],
        model_variants=strings["model_variants"],
        variants=strings["variants"],
        reasoning_effort=strings["reasoning_effort"],
        councils=councils,
        context_limits=cast("dict[str, int]", limits),
    )


def council(path: pathlib.Path, where: str, seats: object) -> tuple[Seat, ...]:
    """The seats of the council `where`, `seats`, of the model tables at `path`: a list of one to
    eight tables {name, model}, each a string that is not blank, at most one of them with
    `verify = true`; any other value exits 2."""
    if not (
        isinstance(seats, list)
        and all(
            isinstance(s, dict)
            and {"name", "model"} <= set(cast("dict[str, object]", s)) <= {"name", "model", "verify"}
            for s in cast("list[object]", seats)
        )
    ):
        raise HarnessError(
            f"{path}: {where} is a list of {{ name = …, model = … }}, and one seat may add `verify = true`"
        )
    tables = cast("list[dict[str, object]]", seats)
    if len(tables) not in COUNCIL_SEATS:
        raise HarnessError(f"{path}: {where} has {len(tables)} seats; a council has 1 to 8")
    out: list[Seat] = []
    for seat in tables:
        name, model, verify = seat["name"], seat["model"], seat.get("verify", False)
        for key, v in (("name", name), ("model", model)):
            if not isinstance(v, str) or not v.strip():
                raise HarnessError(f"{path}: the seat {key} {v!r} of {where} is not a string")
        if not isinstance(verify, bool):
            raise HarnessError(f"{path}: `verify` of the seat {name!r} of {where} is not true or false")
        out.append(Seat(cast("str", name), cast("str", model), verify))
    if sum(s.verify for s in out) > 1:
        raise HarnessError(f"{path}: more than one seat of {where} has `verify = true`")
    return tuple(out)


def tier_table(path: str | os.PathLike[str], frontend: str) -> dict[str, str]:
    """{tier: model} of [claude] of the model tables at `path` (`read_models`), which maps each
    tier to a model of `frontend`; a models.toml without it exits 2."""
    table = read_models(path).claude
    if not table:
        raise HarnessError(
            f"{path} has no [claude] table, which maps the tiers {', '.join(frontmatter.TIERS)} to "
            f"{frontend}'s models — examples/models.toml shows it"
        )
    return dict(table)


# The model tables that OpenCode and oh-my-pi share, at the top level of models.toml; each is
# optional. `models` maps a tier to a model; `model_overrides` an agent to its model in place of its
# tier's; `model_variants` a model to the effort of every agent on it; `variants` and
# `reasoning_effort` an agent or a council seat to its effort, over `model_variants`; `councils` an
# agent to its seats; `context_limits` a model to the input tokens it may hold. [opencode] and
# [omp] may hold the same sub-tables, each key of which replaces the shared one for that frontend
# alone. [claude] is Claude Code's table of the tiers, and [antigravity] Antigravity's; neither
# frontend takes a model from the shared tables.
MODEL_TABLES = [
    "models",
    "model_overrides",
    "model_variants",
    "variants",
    "reasoning_effort",
    "councils",
    "context_limits",
]
# The frontends that read MODEL_TABLES, each with a table of its own overrides.
SHARING: tuple[Literal["opencode", "omp"], ...] = ("opencode", "omp")
# A council has one to eight seats beside its agent.
COUNCIL_SEATS = range(1, 9)


def model_tables(path: str | os.PathLike[str], name: Literal["opencode", "omp"]) -> ModelTables:
    """The shared tables MODEL_TABLES of the model tables at `path` (`read_models`), each with the
    keys of its sub-table of [`name`] over its own. No two seats of the councils share a name: each
    seat is installed as `<name>.md`, so a second seat of one name would replace the first; such a
    pair exits 2."""
    models = read_models(path)
    own = models.opencode if name == "opencode" else models.omp
    merged = ModelTables(
        path=models.path,
        tiers={**models.shared.tiers, **own.tiers},
        model_overrides={**models.shared.model_overrides, **own.model_overrides},
        model_variants={**models.shared.model_variants, **own.model_variants},
        variants={**models.shared.variants, **own.variants},
        reasoning_effort={**models.shared.reasoning_effort, **own.reasoning_effort},
        councils={**models.shared.councils, **own.councils},
        context_limits={**models.shared.context_limits, **own.context_limits},
    )
    seen: dict[str, str] = {}
    for agent, seats in merged.councils.items():
        for seat in seats:
            if seat.name in seen:
                raise HarnessError(
                    f"{models.path}: the seat {seat.name!r} of councils.{agent} is also a seat "
                    f"of councils.{seen[seat.name]}"
                )
            seen[seat.name] = agent
    return merged


def agent_model(name: str, tier: object, models: ModelTables, where: object) -> str | None:
    """The model of the agent `name` of tier `tier` (None for an agent with no tier), with
    `models` from model_tables: its override, else its tier's model, else None, which leaves the
    agent on its caller's model. A tier with no model exits 2, naming `where`."""
    model = None
    if tier is not None:
        if not isinstance(tier, str) or tier not in models.tiers:
            raise HarnessError(f"{where}: the tier {tier!r} has no entry in the models of {models.path}")
        model = models.tiers[tier]
    return models.model_overrides.get(name, model)


def agent_effort(name: str, model: str | None, models: ModelTables) -> str | None:
    """The effort of the agent or seat `name` on `model`: its `variants` entry, else its
    `reasoning_effort` entry, else the `model_variants` entry of `model`, else None."""
    fallback = None if model is None else models.model_variants.get(model)
    return models.variants.get(name, models.reasoning_effort.get(name, fallback))


def council_description(source: str, seat: Seat, frontend: str) -> str:
    """The description of the council seat `seat` of the agent `source` under `frontend`."""
    verify = " It also judges each verify round, alone." if seat.verify else ""
    return (
        f"A member of the round-1 critic council of build-part under {frontend}, on {seat.model}.{verify} "
        f"The same agent as {source}, which has the full description. Spawn it only as the build-part "
        "dispatcher."
    )


def render_line(line: str, profile: Profile | Context) -> str:
    """Substitute every string placeholder in one line, with the values of `profile`
    (`rendering`); a list placeholder is an error."""
    given = rendering(profile)

    def substitute(m: re.Match[str]) -> str:
        v = value(m.group(1), given, m.group(0))
        if not isinstance(v, str):
            kind = "list" if isinstance(v, list) else "table"
            raise TypeError(f"placeholder {m.group(0)}: a {kind} renders only on a line of its own")
        return v

    return PLACEHOLDER.sub(substitute, line)


def render_text(text: str, profile: Profile | Context) -> str:
    """Substitute string placeholders; repeat a line that holds a list placeholder.

    Such a line becomes one copy per item, and disappears for an empty list. It must end in a
    comma, unless the list has exactly one item: a copy of the last entry of a JSON object or
    list would otherwise need a comma it does not have, or leave one dangling. A line that holds a
    table placeholder alone becomes the table's members as JSON (`members`).
    """
    given = rendering(profile)
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        if (m := ALONE.fullmatch(line)) and isinstance(table := given.get(m.group(2)), Mapping):
            out.append(members(table, m.group(1)))
            continue
        copies = expand(line, given)
        if len(copies) != 1 and not line.rstrip().endswith(","):
            raise ValueError(f"{line.strip()!r}: a repeated line must end in a comma")
        out += copies
    return "".join(out)


def members(table: Mapping[str, object], indent: str) -> str:
    """The members of `table` as the lines of a JSON object, each line after `indent`, with no
    comma after the last; "" for an empty table."""
    lines = json.dumps(dict(table), indent=2, ensure_ascii=False).splitlines()[1:-1]
    return "".join(f"{indent}{line[2:]}\n" for line in lines)


def expand(text: str, given: Context) -> list[str]:
    """One string per item of the list placeholder in `text`, or `[text]` rendered."""
    lists = {n: v for n in PLACEHOLDER.findall(text) if isinstance(v := value(n, given, text), list)}
    if not lists:
        return [render_line(text, given)]
    if len(lists) > 1:
        raise ValueError(f"{text!r}: more than one list placeholder")
    ((name, items),) = lists.items()
    return [render_line(text.replace("{" + name + "}", item), given) for item in items]


def render_data(obj: Any, profile: Profile | Context) -> Any:
    """Render a parsed JSON value: keys and strings substitute, list elements expand."""
    given = rendering(profile)
    if isinstance(obj, dict):
        return {render_line(k, given): render_data(v, given) for k, v in cast("dict[str, Any]", obj).items()}
    if isinstance(obj, list):
        out: list[Any] = []
        for item in cast("list[Any]", obj):
            if isinstance(item, str):
                out += expand(item, given)
            else:
                out.append(render_data(item, given))
        return out
    if isinstance(obj, str):
        return render_line(obj, given)
    return obj


def render_file(path: str | os.PathLike[str], profile: Profile | Context) -> str:
    """A template rendered as text, so its bytes stay; parsed and re-serialised only for a
    `.json` that holds a list placeholder, which needs the structure."""
    given = rendering(profile)
    text = pathlib.Path(path).read_text()
    lists = [n for n in PLACEHOLDER.findall(text) if isinstance(given.get(n), list)]
    try:
        if lists and pathlib.Path(path).suffix == ".json":
            return json.dumps(render_data(json.loads(text), given), indent=2, ensure_ascii=False) + "\n"
        return render_text(text, given)
    except (KeyError, TypeError, ValueError) as e:
        raise HarnessError(f"{path}: {e.args[0]}") from e


def cmd_render(args: argparse.Namespace | types.SimpleNamespace) -> int:
    given = context(load(args.profile), providers={})
    if pathlib.Path(args.template).resolve() == network.TEMPLATE:
        cfg = network.apply(json.loads(render_file(args.template, given)), network_path(args.profile))
        sys.stdout.write(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(render_file(args.template, given))
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    v = get(load(args.profile), args.key)
    print(v if isinstance(v, str) else "\n".join(v))
    return 0


def tree_names(profile: Profile) -> list[str]:
    """The directory names below every `repository_roots` entry, and the `org` entries."""
    names = set(profile.org)
    for root in map(pathlib.Path, profile.repository_roots):
        if not root.is_dir():
            raise HarnessError(f"repository_roots entry {root} is not a directory")
        names |= {p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")}
    return sorted(names)


def name_pattern(names: list[str]) -> re.Pattern[str]:
    """A whole-word match of any of `names`: no letter, digit or `_` on either side."""
    return re.compile(r"(?<![A-Za-z0-9_])(?:" + "|".join(map(re.escape, names)) + r")(?![A-Za-z0-9_])")


def own_repository(repo: pathlib.Path = REPO) -> str | None:
    """`owner/name` of the `origin` URL, or None without one."""
    url = subprocess.run(
        ["git", "remote", "get-url", "origin"],  # noqa: S607 -- git runs from PATH
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?\s*$", url)
    return m.group(1) if m else None


def name_hits(line: str, pattern: re.Pattern[str], allowed: str | None) -> list[str]:
    """The tree names in `line`, after removing every occurrence of `allowed`, the repository's own
    `owner/name`, and of `owner.github.io`, the host of its GitHub Pages site."""
    if allowed:
        line = line.replace(allowed, "").replace(allowed.split("/")[0] + ".github.io", "")
    return pattern.findall(line)


def templates() -> list[str]:
    """The templates that `leaks` renders with the dummy profile: TEMPLATES and each adapter's."""
    return TEMPLATES + [t for adapter in frontends.load() for t in adapter.TEMPLATES]


SHA = re.compile(r"[0-9a-f]{7,64}")
# A hunk header; a merge's combined diff has one `@` and one column per parent more.
HUNK = re.compile(r"(@@+) (?:-\S+ )+\+(\d+)")


def read_commits(path: str | os.PathLike[str]) -> list[str]:
    """The SHAs of `path`, one per line; a file that cannot be read or a line that is no SHA
    exits 2."""
    try:
        shas = pathlib.Path(path).read_text().split()
    except (OSError, UnicodeDecodeError) as e:
        raise HarnessError(f"{path} cannot be read: {e}") from None
    bad = [s for s in shas if not SHA.fullmatch(s)]
    if bad:
        raise HarnessError(f"{path}: {bad[0]!r} is not a commit SHA")
    return shas


# The escapes of a path that git quotes: `\` and three octal digits, or one character.
QUOTED = re.compile(rb"\\([0-7]{3}|.)")
ESCAPES = {b"a": 7, b"b": 8, b"t": 9, b"n": 10, b"v": 11, b"f": 12, b"r": 13}


def unquoted(path: str) -> str:
    """`path` of a diff header with git's quotes removed: git writes a path with a byte outside
    printable ASCII, a `"` or a `\\` in double quotes, with C escapes."""
    if len(path) < 2 or path[0] != '"' or path[-1] != '"':
        return path
    return QUOTED.sub(
        lambda m: bytes([int(m[1], 8) if len(m[1]) == 3 else ESCAPES.get(m[1], m[1][0])]), path[1:-1].encode()
    ).decode(errors="replace")


def added_lines(sha: str, repo: pathlib.Path = REPO) -> list[tuple[str, str]]:
    """(where, text) for each path and line that the commit `sha` adds. A path is that of each
    file that the commit adds or changes against any parent, a rename's new path too, as line 0.
    A line is a `+` line of `git show --format= --text -U0`, so a binary file's lines too; in a
    merge's combined diff, a line with a `+` in any parent's column. No external diff and no
    textconv driver rewrites them."""
    p = subprocess.run(
        [  # noqa: S607 -- git runs from PATH
            "git",
            "diff-tree",
            "-r",
            "-z",
            "-m",
            "--root",
            "--no-commit-id",
            "--name-only",
            "--no-renames",
            "--diff-filter=d",
            sha,
        ],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if p.returncode:
        raise HarnessError(f"git diff-tree {sha}: {p.stderr.decode(errors='replace').strip()}")
    paths = dict.fromkeys(p.stdout.decode(errors="replace").split("\0"))  # -m names a path once per parent
    out = [(f"{sha[:12]} {path}:0", path) for path in paths if path]
    p = subprocess.run(
        [  # noqa: S607 -- git runs from PATH
            "git",
            "show",
            "--format=",
            "--text",
            "-U0",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            sha,
        ],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if p.returncode:
        raise HarnessError(f"git show {sha}: {p.stderr.decode(errors='replace').strip()}")
    path, number, parents = "", 0, 0
    for line in p.stdout.decode(errors="replace").split("\n"):
        hunk = HUNK.match(line)
        if line.startswith("diff "):
            parents = 0  # the file's header, up to its first hunk
        elif hunk:
            parents, number = len(hunk.group(1)) - 1, int(hunk.group(2))
        elif not parents:
            if line.startswith("+++ "):  # git ends a path that holds a space with a tab
                path = unquoted(line[4:].removesuffix("\t")).removeprefix("b/")
        elif not line.startswith("\\"):  # not "\ No newline at end of file"
            prefix = line[:parents]
            if "+" in prefix:
                out.append((f"{sha[:12]} {path}:{number}", line[parents:]))
            if "-" not in prefix:
                number += 1
    return out


def message_lines(sha: str, repo: pathlib.Path = REPO):
    """(where, text) for each line of the message of the commit `sha`, `%B`: the raw subject and
    body, trailers too, numbered from 1. The author, the committer and a signature are not read."""
    p = subprocess.run(
        ["git", "show", "-s", "--no-show-signature", "--format=%B", sha],  # noqa: S607 -- git runs from PATH
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if p.returncode:
        raise HarnessError(f"git show -s {sha}: {p.stderr.decode(errors='replace').strip()}")
    return [
        (f"{sha[:12]} message:{n}", line)
        for n, line in enumerate(p.stdout.decode(errors="replace").split("\n"), 1)
    ]


def commit_hits(
    shas: list[str],
    leak: Sequence[str],
    pattern: re.Pattern[str],
    allowed: str | None,
    repo: pathlib.Path = REPO,
) -> list[tuple[str, str]]:
    """(where, string) for each private string and tree name in a path or on a line that one of `shas`
    adds, or on a line of its message."""
    return [
        (where, s)
        for sha in shas
        for where, line in added_lines(sha, repo) + message_lines(sha, repo)
        for s in [s for s in leak if s in line] + name_hits(line, pattern, allowed)
    ]


def cmd_leaks(args: argparse.Namespace, repo: pathlib.Path = REPO) -> int:
    """`harness leaks` on the tracked files and the commits of `repo`; the templates are this
    repository's."""
    profile = load(args.profile)
    leak = profile.leak
    names = tree_names(profile)
    pattern, allowed = name_pattern(names), own_repository(repo)
    dummy = context(load(DUMMY, home=DUMMY_HOME, host=DUMMY_HOST), providers={})
    files = subprocess.run(
        ["git", "ls-files", "-z"],  # noqa: S607 -- git runs from PATH
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    sources = [(f, (repo / f).read_text(errors="replace")) for f in files if f and (repo / f).is_file()]
    tracked = len(sources)
    sources += [(f + " (rendered with the dummy)", render_file(REPO / f, dummy)) for f in templates()]
    hits = 0
    for i, (name, text) in enumerate(sources):
        for number, line in enumerate([name] + text.splitlines()):
            found = [s for s in leak if s in line]
            if i < tracked:
                found += name_hits(line, pattern, allowed)
            for s in found:
                hits += 1
                print(f"  {name}:{number}: {s!r}")
    commits = ""
    if args.commits is not None:
        shas = read_commits(args.commits)
        for where, s in commit_hits(shas, leak, pattern, allowed, repo):
            hits += 1
            print(f"  {where}: {s!r}")
        commits = f", {len(shas)} commits"
    print(f"  {len(sources)} files{commits}, {len(leak)} leak strings, {len(names)} tree names, {hits} hits")
    return 1 if hits else 0


CASES: list[tuple[Any, Context, Any]] = [
    # (template, profile, expected); expected None means an error.
    ("{home}/.ssh", {"home": "/h"}, "/h/.ssh"),
    ("{file:~/.config/x} {env:HOME}", {}, "{file:~/.config/x} {env:HOME}"),
    ("{missing}", {}, None),
    ("{org}", {"org": ["a"]}, "a"),
    ("  {home}/{dir}/**,\n}\n", {"home": "/h", "dir": ["A", "B"]}, "  /h/A/**,\n  /h/B/**,\n}\n"),
    ("  {dir}\n", {"dir": ["A", "B"]}, None),
    ("  {dir},\n}\n", {"dir": []}, "}\n"),
    (["gh -R {org}/*", "x"], {"org": ["a", "b"]}, ["gh -R a/*", "gh -R b/*", "x"]),
    (["d:{extra}"], {"extra": []}, []),
    (["{home}/{dir}/**"], {"home": "/h", "dir": ["D"]}, ["/h/D/**"]),
    (["{a}{b}"], {"a": ["1"], "b": ["2"]}, None),
    ({"{home}": ["{home}"]}, {"home": "/h"}, {"/h": ["/h"]}),
    (
        "{\n  {t}\n}\n",
        {"t": {"a": {"m/x:1": 2}, "b": []}},
        '{\n  "a": {\n    "m/x:1": 2\n  },\n  "b": []\n}\n',
    ),
    ("{\n  {t}\n}\n", {"t": {}}, "{\n}\n"),
    ("  x: {t},\n", {"t": {"a": 1}}, None),
    (["{t}"], {"t": {"a": 1}}, None),
]


NAME_CASES: list[tuple[str, list[str]]] = [
    # (line, expected tree names), with the names Pkg, my-paper and org and the allowed org/Repo.
    ("Packages/Pkg/src", ["Pkg"]),
    ("Pkg.jl and Pkg's", ["Pkg", "Pkg"]),
    ("PkgBase MyPkg Pkg_x pkg", []),
    ("the my-paper repository", ["my-paper"]),
    ("github.com/org/Repo", []),
    ("github.com/org/Other", ["org"]),
    ("https://org.github.io/Repo/", []),
    ("https://org.github.io/", []),
    ("org.github.com", ["org"]),
]


def commit_cases():
    """The cases of `leaks --commits` on a fixture repository: (number of cases, number wrong)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="leaks",
        GIT_AUTHOR_EMAIL="leaks@example.org",
        GIT_COMMITTER_NAME="leaks",
        GIT_COMMITTER_EMAIL="leaks@example.org",
    )
    wrong = 0
    with tempfile.TemporaryDirectory(prefix="harness-leaks-") as tmp:
        repo = pathlib.Path(tmp) / "repo"
        repo.mkdir()

        def git(*args: str, **extra: str) -> str:
            """`git args` in the fixture; `extra` sets variables of its environment."""
            return subprocess.run(
                ["git", *args],  # noqa: S607 -- git runs from PATH
                cwd=repo,
                env={**env, **extra},
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        def commit(name: str, data: bytes | None = None, *move: str) -> str:
            if move:
                git("mv", "--", name, *move)
            elif data is None:
                git("rm", "-q", "--", name)
            else:
                (repo / name).write_bytes(data)
                git("add", "--", name)
            git("commit", "-q", "-m", "change")  # a clean message: the cases of a message are below
            return git("rev-parse", "HEAD")

        def note(message: bytes) -> str:
            """An empty commit with the message `message`, bytes taken as they are."""
            (pathlib.Path(tmp) / "message").write_bytes(message)
            git(
                "commit",
                "-q",
                "--allow-empty",
                "--allow-empty-message",
                "--cleanup=verbatim",
                "-F",
                str(pathlib.Path(tmp) / "message"),
            )
            return git("rev-parse", "HEAD")

        git("init", "-q", "-b", "main")
        root = commit("root-Pkg.md", b"plain\n")
        commit("a.txt", b"one\n")
        added = commit("a.txt", b"one\nthe LEAK here\n")
        removed = commit("a.txt", b"one\n")
        binary = commit("b.bin", b"\0\1\2 LEAK \0\n")
        named = commit("a.txt", b"one\nPkg.jl\n")
        unnamed = commit("a.txt", b"one\n")
        path_added = commit("notes-Pkg.md", b"plain\n")
        path_renamed = commit("notes-Pkg.md", None, "notes.md")
        rename_in = commit("notes.md", None, "Pkg-notes.md")
        commit("Pkg-notes.md", None, "notes.md")
        empty = commit("LEAK.txt", b"")
        spaced = commit("a b.txt", b"x\nLEAK")
        git("switch", "-q", "-c", "side")
        commit("side-Pkg.md", b"plain\n")
        git("switch", "-q", "main")
        git("merge", "-q", "--no-ff", "-m", "merge", "side")
        merge = git("rev-parse", "HEAD")
        # The messages: empty commits, so that the tree and the lines stay clean.
        body = note(b"a clean subject\n\nthe LEAK in the body\n")
        subject = note(b"Pkg: a subject\n")
        own = note(b"see github.com/org/Pkg\n")
        clean = commit("c.txt", b"clean\n")
        no_message = note(b"")
        latin = note(b"caf\xe9 LEAK\n")
        both = note(b"LEAK and Pkg\n")
        git("switch", "-q", "-c", "side2")
        note(b"side\n")
        git("switch", "-q", "main")
        git("merge", "-q", "--no-ff", "-m", "merge LEAK", "side2")
        merged = git("rev-parse", "HEAD")
        for name in ("b.bin", "LEAK.txt", "a b.txt", "root-Pkg.md", "side-Pkg.md"):
            commit(name)
        pattern = name_pattern(["Pkg"])
        cases = [
            ("a leak on an added line", [added], 1),
            ("the same leak only on a removed line", [removed], 0),
            ("a leak that one commit adds and a later one removes", [added, removed], 1),
            ("a leak in a binary file", [binary], 1),
            ("a tree name on an added line", [named], 1),
            ("the same tree name only on a removed line", [unnamed], 0),
            (
                "a tree name in a path that one commit adds and a later one renames away",
                [path_added, path_renamed],
                1,
            ),
            ("a tree name in the new path of a pure rename", [rename_in], 1),
            ("a leak in the path of an empty file", [empty], 1),
            ("a tree name in a path of the root commit", [root], 1),
        ]
        for label, shas, expected in cases:
            got = len(commit_hits(shas, ["LEAK"], pattern, None, repo))
            wrong += got != expected
            print(f"{'ok ' if got == expected else 'BAD'}  leaks --commits: {label} -> {got} hits")
        got = [where for where, _ in commit_hits([spaced], ["LEAK"], pattern, None, repo)]
        expected = [f"{spaced[:12]} a b.txt:2"]
        wrong += got != expected
        print(
            f"{'ok ' if got == expected else 'BAD'}  leaks --commits: the place of a leak in a path "
            f"with a space -> {got}"
        )
        got = [where for where, _ in commit_hits([merge], ["LEAK"], pattern, None, repo)]
        expected = [f"{merge[:12]} side-Pkg.md:0"]
        wrong += got != expected
        print(
            f"{'ok ' if got == expected else 'BAD'}  leaks --commits: a tree name in a path that a "
            f"merge brings from its side parent -> {got}"
        )
        # (label, shas, tree names, allowed owner/name, expected places); the leak string is LEAK.
        message_cases: list[tuple[str, list[str], list[str], str | None, list[str]]] = [
            ("a leak in a message body", [body], ["Pkg"], None, [f"{body[:12]} message:3"]),
            ("a tree name in a message subject", [subject], ["Pkg"], None, [f"{subject[:12]} message:1"]),
            ("the own owner/name in a message", [own], ["Pkg", "org"], "org/Pkg", []),
            ("a clean message and clean content", [clean], ["Pkg"], None, []),
            ("an empty message", [no_message], ["Pkg"], None, []),
            (
                "a leak in the ASCII part of a message that is not UTF-8",
                [latin],
                ["Pkg"],
                None,
                [f"{latin[:12]} message:1"],
            ),
            (
                "a leak string and a tree name on one message line",
                [both],
                ["Pkg"],
                None,
                [f"{both[:12]} message:1"] * 2,
            ),
            ("a leak in a merge's message", [merged], ["Pkg"], None, [f"{merged[:12]} message:1"]),
            ("a SHA listed twice", [body, body], ["Pkg"], None, [f"{body[:12]} message:3"] * 2),
        ]
        for label, shas, names, allowed, expected in message_cases:
            got = [where for where, _ in commit_hits(shas, ["LEAK"], name_pattern(names), allowed, repo)]
            wrong += got != expected
            print(f"{'ok ' if got == expected else 'BAD'}  leaks --commits: {label} -> {got}")
        (repo / "commits").write_text(f"{added}\n--output=x\n")
        try:
            read_commits(repo / "commits")
            got = "read"
        except HarnessError:
            got = "refused"
        wrong += got != "refused"
        print(f"{'ok ' if got == 'refused' else 'BAD'}  leaks --commits: a line that is not a SHA -> {got}")
        # `harness leaks` itself, on the fixture's clean tree, without and with the commits.
        (pathlib.Path(tmp) / "roots" / "Pkg").mkdir(parents=True)
        roots = f"[{json.dumps(str(pathlib.Path(tmp) / 'roots'))}]"
        (pathlib.Path(tmp) / "profile.toml").write_text(profile_text(leak='["LEAK"]', repository_roots=roots))
        (pathlib.Path(tmp) / "commits").write_text(git("rev-list", "HEAD") + "\n")
        runs: list[tuple[str, pathlib.Path | None, int, list[str]]] = [
            ("the tree only", None, 0, []),
            (
                "the tree and every commit",
                pathlib.Path(tmp) / "commits",
                1,
                [
                    f"  {added[:12]} a.txt:2: 'LEAK'",
                    f"  {path_added[:12]} notes-Pkg.md:0: 'Pkg'",
                    f"  {body[:12]} message:3: 'LEAK'",
                ],
            ),
        ]
        for label, commits, status, lines in runs:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                got = cmd_leaks(
                    argparse.Namespace(profile=pathlib.Path(tmp) / "profile.toml", commits=commits), repo
                )
            ok = got == status and all(line in out.getvalue().splitlines() for line in lines)
            wrong += not ok
            print(f"{'ok ' if ok else 'BAD'}  leaks: {label} -> exit {got}")
        # The home directory as a leak string, `~` in the profile: the templates render with the
        # dummy under a home that is not the running user's, so they hold no hit.
        (pathlib.Path(tmp) / "profile-home.toml").write_text(
            profile_text(leak='["~"]', repository_roots=roots)
        )
        out = io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            mock.patch.dict(os.environ, HOME=str(pathlib.Path(tmp) / "roots")),
        ):
            got = cmd_leaks(
                argparse.Namespace(profile=pathlib.Path(tmp) / "profile-home.toml", commits=None), repo
            )
        summary = out.getvalue().splitlines()[-1]
        ok = got == 0 and summary.endswith(", 0 hits")
        wrong += not ok
        print(
            f"{'ok ' if ok else 'BAD'}  leaks: the running user's home as the leak string, and the templates "
            f"rendered with the dummy -> exit {got}, {summary.strip()!r}"
        )
        # The running host's name as a leak string: the dummy's `autocommit_branch` renders under a
        # host name that is not the running one, so the templates hold no hit.
        (pathlib.Path(tmp) / "profile-host.toml").write_text(
            profile_text(leak='["leakhost"]', repository_roots=roots)
        )
        out = io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            mock.patch("socket.gethostname", return_value="leakhost.example.org"),
        ):
            got = cmd_leaks(
                argparse.Namespace(profile=pathlib.Path(tmp) / "profile-host.toml", commits=None), repo
            )
        summary = out.getvalue().splitlines()[-1]
        ok = got == 0 and summary.endswith(", 0 hits")
        wrong += not ok
        print(
            f"{'ok ' if ok else 'BAD'}  leaks: the running host's name as the leak string, and the templates "
            f"rendered with the dummy -> exit {got}, {summary.strip()!r}"
        )
        # The templates that `harness leaks` renders: TEMPLATES and each adapter's. The leak string is
        # the suffix of a rendered template's name, so each template it renders is one hit on line 0.
        (pathlib.Path(tmp) / "profile-templates.toml").write_text(
            profile_text(leak='[" (rendered with the dummy)"]', repository_roots=roots)
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_leaks(
                argparse.Namespace(profile=pathlib.Path(tmp) / "profile-templates.toml", commits=None), repo
            )
        rendered = {
            line.strip().rsplit(" (rendered with the dummy):0: ", 1)[0]
            for line in out.getvalue().splitlines()
            if " (rendered with the dummy):0: " in line
        }
        adapters = {t for adapter in frontends.load() for t in adapter.TEMPLATES}
        ok = bool(adapters - set(TEMPLATES)) and rendered == set(TEMPLATES) | adapters
        wrong += not ok
        print(
            f"{'ok ' if ok else 'BAD'}  leaks: renders TEMPLATES and each adapter's TEMPLATES -> "
            f"{len(rendered)} templates, missing {sorted((set(TEMPLATES) | adapters) - rendered)}"
        )
        # The limits that docs/src/security.md states: a leak only in a commit's author name, only in
        # the message of an annotated tag on a listed commit, or only in a note on one, is no hit; the
        # same leak in a listed commit's message is one, so the fixture can see it. Empty commits.
        git("commit", "-q", "--allow-empty", "-m", "clean", GIT_AUTHOR_NAME="the LEAK author")
        author = git("rev-parse", "HEAD")
        tagged = note(b"clean\n")
        git("tag", "-a", "v1", "-m", "the LEAK in a tag", tagged)
        noted = note(b"clean\n")
        git("notes", "add", "-m", "the LEAK in a note", noted)
        messaged = note(b"the LEAK in a message\n")
        # (label, SHA, where git shows the leak, expected hits)
        limits = [
            ("a leak only in a commit's author name", author, git("show", "-s", "--format=%an", author), 0),
            (
                "a leak only in the message of an annotated tag on the commit",
                tagged,
                git("tag", "-l", "--format=%(contents)", "v1"),
                0,
            ),
            ("a leak only in a git note on the commit", noted, git("notes", "show", noted), 0),
            (
                "the same leak in the commit's message",
                messaged,
                git("show", "-s", "--format=%B", messaged),
                1,
            ),
        ]
        for label, sha, shown, expected in limits:
            (pathlib.Path(tmp) / "commits").write_text(sha + "\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = cmd_leaks(
                    argparse.Namespace(
                        profile=pathlib.Path(tmp) / "profile.toml", commits=pathlib.Path(tmp) / "commits"
                    ),
                    repo,
                )
            summary = out.getvalue().splitlines()[-1]
            ok = "LEAK" in shown and status == min(expected, 1) and summary.endswith(f", {expected} hits")
            wrong += not ok
            print(f"{'ok ' if ok else 'BAD'}  leaks --commits: {label} -> exit {status}, {summary.strip()!r}")
        # An evil merge: a path that the merge itself adds, so it differs from both parents and
        # `-m` names it twice, and a path that differs from the second parent only.
        git("switch", "-q", "-c", "side3")
        commit("s.txt", b"side\n")
        git("switch", "-q", "main")
        commit("m-Pkg.md", b"main\n")
        git("merge", "-q", "--no-ff", "--no-commit", "side3")
        (repo / "evil-Pkg.md").write_bytes(b"evil\n")
        git("add", "--", "evil-Pkg.md")
        git("commit", "-q", "-m", "merge")
        evil = git("rev-parse", "HEAD")
        # A merge whose resolution adds a LEAK line that neither parent has, after a line of the
        # second parent that it removes.
        commit("f.txt", b"base\n")
        git("switch", "-q", "-c", "side4")
        commit("f.txt", b"side\n")
        git("switch", "-q", "main")
        commit("f.txt", b"main\n")
        subprocess.run(
            ["git", "merge", "-q", "--no-ff", "side4"],  # noqa: S607 -- git runs from PATH
            cwd=repo,
            env=env,
            capture_output=True,
            check=False,
        )
        (repo / "f.txt").write_bytes(b"main\nLEAK\n")
        git("add", "--", "f.txt")
        git("commit", "-q", "-m", "merge")
        resolved = git("rev-parse", "HEAD")
        # Paths that git quotes in a diff header: a non-ASCII character, and a `"`.
        cafe = commit("café.txt", b"LEAK\n")
        quote = commit('a"b.txt', b"LEAK\n")
        # (label, SHA, expected places); the leak string is LEAK, the tree name Pkg.
        place_cases = [
            (
                "an evil merge names each path once, the one that differs from the second parent only too",
                evil,
                [f"{evil[:12]} evil-Pkg.md:0", f"{evil[:12]} m-Pkg.md:0"],
            ),
            (
                "a line that a merge's resolution adds, which neither parent has",
                resolved,
                [f"{resolved[:12]} f.txt:2"],
            ),
            ("a leak in a path with a non-ASCII character", cafe, [f"{cafe[:12]} café.txt:1"]),
            ('a leak in a path with a "', quote, [f'{quote[:12]} a"b.txt:1']),
        ]
        for label, sha, expected in place_cases:
            got = [where for where, _ in commit_hits([sha], ["LEAK"], pattern, None, repo)]
            wrong += got != expected
            print(f"{'ok ' if got == expected else 'BAD'}  leaks --commits: {label} -> {got}")
        # `cmd_leaks` allows the owner/name of the origin of `repo`, not that of this checkout: the
        # message of `own` names org/Pkg, and Pkg is a tree name.
        for name in ("m-Pkg.md", "evil-Pkg.md", "f.txt", "café.txt", 'a"b.txt'):
            commit(name)
        git("remote", "add", "origin", "https://github.com/org/Pkg.git")
        (pathlib.Path(tmp) / "commits").write_text(own + "\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = cmd_leaks(
                argparse.Namespace(
                    profile=pathlib.Path(tmp) / "profile.toml", commits=pathlib.Path(tmp) / "commits"
                ),
                repo,
            )
        summary = out.getvalue().splitlines()[-1]
        ok = (
            own_repository(repo) == "org/Pkg" != own_repository()
            and status == 0
            and summary.endswith(", 0 hits")
        )
        wrong += not ok
        print(
            f"{'ok ' if ok else 'BAD'}  leaks --commits: the own owner/name of a repository whose origin is not "
            f"this checkout's -> exit {status}, {summary.strip()!r}"
        )
    return len(cases) + 3 + len(message_cases) + len(runs) + 3 + len(limits) + len(place_cases) + 1, wrong


# The tools that `.githooks/pre-push` starts from the PATH in `prepush_case`, besides the stubs.
PREPUSH_TOOLS = ["bash", "sh", "git", "mktemp", "rm", "cat", "tail", "head", "grep", "awk"]


KIT_TESTS = ["update-check", "check-check", "driver-check", "render-check", "script-check"]
KIT_SKIP = "skip  chezmoi: not found; CI runs the kit's tests"
COMPILE = "-m compileall -q lib hooks scripts adapters"


NO_INTERPRETER = "pre-push: bin/harness names no interpreter of the Python environment"
# The checks of the strict profile, as the stubs of the environment's tools log them.
STRICT = ["ruff format --check --no-cache .", "ruff check --no-cache .", "basedpyright"]


def prepush_case(
    path: str | None = None,
    kit_fails: str | None = None,
    *,
    no_environment: bool = False,
    lacks: tuple[str, ...] = (),
    fails: str = "",
) -> tuple[int, int]:
    """`.githooks/pre-push` on a fixture checkout whose `origin` is a GitHub URL, for a push to
    main, with stubs of gitleaks, of `bin/harness` and of the Python environment's interpreter,
    and no shellcheck, julia or chezmoi on the PATH: `harness leaks` runs in the hook's clone with
    that URL as its `origin`, not the path of the checkout, `bin/harness test` runs once, the
    compile check runs on the interpreter that the stub's `interpreter(environment_path())`
    names, the three checks of STRICT run in the clone from the environment's bin/, and the kit's
    tests are skipped with one line. The environment's `ruff` and `basedpyright` and a second pair
    first on the PATH are stubs that log their arguments. With `no_environment`, the stub's
    `environment_path` raises: the hook prints NO_INTERPRETER, runs no compile check and no check
    of STRICT, and refuses the push. With `lacks`, the names of tools that the environment lacks:
    the hook prints one line per tool that names `harness install --apply`, runs no check of
    STRICT and no tool of the PATH, and refuses the push. With `fails`, one command of STRICT,
    whose stub exits 1: the hook still runs all three and refuses the push. With `kit_fails`,
    the name of one of KIT_TESTS, a stub of chezmoi is on the PATH and the fixture holds the five
    kit tests, of which that one exits 1: the hook runs all five and refuses the push with one
    line that names it. The tools are linked from `path`, this process's PATH by default, without a
    directory named `git-core`: git puts its exec path first in a hook's PATH, and a `git` started
    from a link to that copy looks for `git-upload-pack` beside the link. (number of cases, number
    wrong)"""
    search = os.pathsep.join(
        d
        for d in (os.environ.get("PATH", "") if path is None else path).split(os.pathsep)
        if pathlib.PurePath(d).name != "git-core"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="leaks",
        GIT_AUTHOR_EMAIL="leaks@example.org",
        GIT_COMMITTER_NAME="leaks",
        GIT_COMMITTER_EMAIL="leaks@example.org",
    )
    url = "https://github.com/owner/fixture.git"
    with tempfile.TemporaryDirectory(prefix="harness-pre-push-") as tmp:
        tmp = pathlib.Path(tmp)
        tools, repo, seen = tmp / "bin", tmp / "repo", tmp / "origin-seen"
        tools.mkdir()
        missing = [tool for tool in PREPUSH_TOOLS if shutil.which(tool, path=search) is None]
        if missing:
            print(f"BAD  pre-push: the case needs {', '.join(missing)} on the PATH; it does not run")
            return 1, 1
        for tool in PREPUSH_TOOLS:
            # `missing` is empty, so each tool is found.
            (tools / tool).symlink_to(cast(str, shutil.which(tool, path=search)))
        (tools / "python3").symlink_to(sys.executable)
        (tools / "gitleaks").write_text(
            '#!/bin/sh\n[ "$1" = version ] && echo v8.24.0\n[ "$1" = stdin ] && cat >/dev/null\nexit 0\n'
        )
        (tools / "gitleaks").chmod(0o755)
        (repo / "bin").mkdir(parents=True)
        # The stub names the environment's interpreter as bin/harness does, by `environment_path`
        # and `interpreter`, and runs its commands only as a script.
        (repo / "bin" / "harness").write_text(
            "import os, subprocess, sys\n"
            "def environment_path():\n"
            "    return os.environ['STUB_ENVIRONMENT']\n"
            "def interpreter(environment):\n"
            "    return os.path.join(environment, 'bin', 'python')\n"
            "if __name__ == '__main__':\n"
            "    open(os.environ['HARNESS_RAN'], 'a').write(sys.argv[1] + '\\n')\n"
            "    if sys.argv[1] == 'leaks':\n"
            "        url = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True,\n"
            "                             text=True).stdout\n"
            "        open(os.environ['ORIGIN_SEEN'], 'w').write(url.strip())\n"
            "    print('0 cases, 0 wrong')\n"
        )
        environment, harness_ran, compiled = (
            tmp / "environment with space",
            tmp / "harness-ran",
            tmp / "compiled",
        )
        (environment / "bin").mkdir(parents=True)
        (environment / "bin" / "python").write_text(f"#!/bin/sh\necho \"$*\" >> '{compiled}'\n")
        (environment / "bin" / "python").chmod(0o755)
        strict = tmp / "strict"
        for directory, prefix, names in (
            (environment / "bin", "", [t for t in ("ruff", "basedpyright") if t not in lacks]),
            (tools, "PATH ", ["ruff", "basedpyright"]),
        ):
            for name in names:
                # The command of STRICT that `fails` names exits 1.
                (directory / name).write_text(
                    f'#!/bin/sh\nline="{prefix}{name} $*"\necho "$line | $(pwd)" >> \'{strict}\'\n'
                    f"[ \"${{line% }}\" = '{fails}' ] && exit 1\nexit 0\n"
                )
                (directory / name).chmod(0o755)
        ran = tmp / "kit-ran"
        if kit_fails:
            (tools / "chezmoi").write_text("#!/bin/sh\nexit 0\n")
            (tools / "chezmoi").chmod(0o755)
            (repo / "examples" / "dotfiles" / "tests").mkdir(parents=True)
            for name in KIT_TESTS:
                (repo / "examples" / "dotfiles" / "tests" / f"{name}.py").write_text(
                    "import os, sys\n"
                    f"open(os.environ['KIT_RAN'], 'a').write({name!r} + '\\n')\n"
                    f"sys.exit({int(name == kit_fails)})\n"
                )

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", *args],  # noqa: S607 -- git runs from PATH
                cwd=repo,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        git("init", "-q", "-b", "main")
        git("add", "--", ".")
        git("commit", "-q", "-m", "fixture")
        git("remote", "add", "origin", url)
        sha = git("rev-parse", "HEAD")
        try:
            p = subprocess.run(
                [str(REPO / ".githooks" / "pre-push"), "origin", url],
                input=f"refs/heads/main {sha} refs/heads/main {'0' * 40}\n",
                cwd=repo,
                env={
                    **env,
                    "PATH": str(tools),
                    "ORIGIN_SEEN": str(seen),
                    "TMPDIR": str(tmp),
                    "KIT_RAN": str(ran),
                    "HARNESS_RAN": str(harness_ran),
                    **({} if no_environment else {"STUB_ENVIRONMENT": str(environment)}),
                },
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            code, text = p.returncode, p.stdout + p.stderr
        except subprocess.TimeoutExpired:
            code, text = None, "TIMEOUT"
        got = seen.read_text() if seen.exists() else None
        tests = ran.read_text().split() if ran.exists() else []
        commands = harness_ran.read_text().split() if harness_ran.exists() else []
        compile_runs = compiled.read_text().splitlines() if compiled.exists() else []
        checks = strict.read_text().splitlines() if strict.exists() else []
    strict_runs = [line.partition(" | ")[0].strip() for line in checks]
    # The hook's clone is repo/ below the hook's own directory under TMPDIR, not the fixture's repo/.
    in_clone = all(
        line.partition(" | ")[2].endswith("/repo") and "/harness-pre-push." in line for line in checks
    )
    lines = text.strip().splitlines() or ["no output"]
    if kit_fails:
        refusal = f"pre-push: refused, the kit's tests failed: examples/dotfiles/tests/{kit_fails}.py"
        ok = code == 1 and got == url and tests == KIT_TESTS and lines[-1] == refusal
        print(
            f"{'ok ' if ok else 'BAD'}  pre-push: with chezmoi on the PATH, the kit's tests run and "
            f"{kit_fails}.py exiting 1 refuses the push -> exit {code}, ran {tests}, {lines[-1]!r}"
        )
        return 1, int(not ok)
    if no_environment:
        ok = (
            code == 1
            and NO_INTERPRETER in lines
            and compile_runs == []
            and checks == []
            and commands == ["leaks", "test"]
            and any(line.startswith("pre-push: refused;") for line in lines)
        )
        print(
            f"{'ok ' if ok else 'BAD'}  pre-push: when bin/harness names no interpreter of the environment, the "
            f"hook says so, runs no compile check and no check of the strict profile and refuses the push "
            f"-> exit {code}, compile {compile_runs}, checks {checks}, "
            f"{[line for line in lines if line.startswith('pre-push:')]}"
        )
        return 1, int(not ok)
    if lacks:
        said = [line for line in lines if line.startswith("pre-push: no ")]
        ok = (
            code == 1
            and checks == []
            and len(said) == len(lacks)
            and all(f"pre-push: no {tool} in " in line for tool, line in zip(lacks, said, strict=True))
            and all("harness install --apply" in line for line in said)
            and any(line.startswith("pre-push: refused;") for line in lines)
        )
        print(
            f"{'ok ' if ok else 'BAD'}  pre-push: an environment without {' and '.join(lacks)}, "
            f"with both tools on the PATH: one line per tool that names harness install --apply, "
            f"no check runs, the push is refused -> exit {code}, checks {checks}, "
            f"{[line for line in lines if line.startswith('pre-push:')]}"
        )
        return 1, int(not ok)
    if fails:
        ok = (
            code == 1
            and strict_runs == STRICT
            and any(line.startswith("pre-push: refused;") for line in lines)
        )
        print(
            f"{'ok ' if ok else 'BAD'}  pre-push: `{fails}` fails: all three checks run "
            f"and the push is refused -> exit {code}, checks {strict_runs}, "
            f"{[line for line in lines if line.startswith('pre-push:')]}"
        )
        return 1, int(not ok)
    ok = (
        code == 0
        and got == url
        and KIT_SKIP in lines
        and tests == []
        and commands == ["leaks", "test"]
        and compile_runs == [COMPILE]
        and strict_runs == STRICT
        and in_clone
        and not any("python3.14" in line for line in lines)
    )
    print(
        f"{'ok ' if ok else 'BAD'}  pre-push: harness leaks runs in the clone with the checkout's "
        f"origin URL, bin/harness test runs once, the compile check runs on the environment's interpreter, "
        f"the three checks of the strict profile run in the clone with the environment's tools, "
        f"and without chezmoi the kit's tests skip with one line "
        f"-> exit {code}, origin {got!r}, harness {commands}, compile {compile_runs}, checks {checks}, "
        f"skip line {KIT_SKIP in lines}, {lines[-1]!r}"
    )
    return 1, int(not ok)


def prepush_branch_cases():
    """`.githooks/pre-push` for a push of a topic branch, on a fixture checkout whose
    `refs/remotes/origin/main` holds a commit that adds the private string and one that removes it.
    The stub of `bin/harness leaks` searches the tree at HEAD and each commit of `--commits` for
    the string. A clean branch passes, so the commits of origin/main are not sent; a branch whose
    new commit adds the string and whose next commit removes it is refused; a branch on the
    commit with the string is refused for its tree. An existing branch that merges origin/main
    passes, because a commit of a remote branch is not sent, and is refused when its own new
    commits add the string. No case runs the suite. (number of cases, number wrong)"""
    search = os.pathsep.join(
        d for d in os.environ.get("PATH", "").split(os.pathsep) if pathlib.PurePath(d).name != "git-core"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="leaks",
        GIT_AUTHOR_EMAIL="leaks@example.org",
        GIT_COMMITTER_NAME="leaks",
        GIT_COMMITTER_EMAIL="leaks@example.org",
    )
    url = "https://github.com/owner/fixture.git"
    with tempfile.TemporaryDirectory(prefix="harness-pre-push-") as tmp:
        tmp = pathlib.Path(tmp)
        tools, repo = tmp / "bin", tmp / "repo"
        tools.mkdir()
        missing = [tool for tool in PREPUSH_TOOLS if shutil.which(tool, path=search) is None]
        if missing:
            print(f"BAD  pre-push: the branch cases need {', '.join(missing)} on the PATH; they do not run")
            return 1, 1
        for tool in PREPUSH_TOOLS:
            # `missing` is empty, so each tool is found.
            (tools / tool).symlink_to(cast(str, shutil.which(tool, path=search)))
        (tools / "python3").symlink_to(sys.executable)
        (repo / "bin").mkdir(parents=True)
        # The stub holds the leak string split, so its own tree does not hit.
        (repo / "bin" / "harness").write_text(
            "import subprocess, sys\n"
            "if sys.argv[1] != 'leaks':\n"
            "    print('the suite ran'); sys.exit(1)\n"
            "word = 'LE' + 'AK'\n"
            "hit = subprocess.run(['git', 'grep', '-q', word, 'HEAD']).returncode == 0\n"
            "for sha in open(sys.argv[3]).read().split():\n"
            "    hit |= word in subprocess.run(['git', 'show', sha], capture_output=True, text=True).stdout\n"
            "print('1 hit' if hit else '0 hits')\n"
            "sys.exit(int(hit))\n"
        )

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", *args],  # noqa: S607 -- git runs from PATH
                cwd=repo,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        def commit(name: str, content: str | None = None) -> str:
            if content is None:
                git("rm", "-q", "--", name)
            else:
                (repo / name).write_text(content)
                git("add", "--", name)
            git("commit", "-q", "-m", f"change {name}")
            return git("rev-parse", "HEAD")

        git("init", "-q", "-b", "main")
        git("add", "--", "bin/harness")
        git("commit", "-q", "-m", "fixture")
        base = git("rev-parse", "HEAD")
        git("remote", "add", "origin", url)
        with_leak = commit("a.txt", "LEAK\n")
        main = commit("a.txt")
        git("update-ref", "refs/remotes/origin/main", main)
        clean = commit("clean.txt", "clean\n")
        git("checkout", "-q", "--detach", main)
        commit("x.txt", "LEAK\n")
        removed = commit("x.txt")
        git("checkout", "-q", "--detach", with_leak)
        on_leak = commit("y.txt", "clean\n")
        # A branch pushed before origin/main took the commit with the leak string, which then merges
        # origin/main: the commits of origin/main that its old tip lacks are on a remote branch, not sent.
        git("checkout", "-q", "--detach", base)
        old_tip = commit("old.txt", "old\n")
        git("update-ref", "refs/remotes/origin/topic", old_tip)
        git("merge", "-q", "--no-edit", main)
        merged = git("rev-parse", "HEAD")
        commit("z.txt", "LEAK\n")
        merged_removed = commit("z.txt")
        none = "0" * 40
        cases = [
            (
                "a clean new branch on origin/main passes, and the commits of origin/main are not sent",
                clean,
                none,
                0,
                "the leak check of the branches passed",
            ),
            (
                "a branch whose new commit adds the leak string, removed by the next commit, is refused",
                removed,
                none,
                1,
                "found a leak",
            ),
            (
                "a branch whose tree holds the leak string of an earlier commit is refused",
                on_leak,
                none,
                1,
                "found a leak",
            ),
            (
                "an existing branch that merges origin/main passes: the commits of a remote branch are not sent",
                merged,
                old_tip,
                0,
                "the leak check of the branches passed",
            ),
            (
                "an existing branch that merges origin/main, then adds and removes the leak string, is refused",
                merged_removed,
                old_tip,
                1,
                "found a leak",
            ),
        ]
        wrong = 0
        for label, sha, remote_sha, expected, marker in cases:
            try:
                p = subprocess.run(
                    [str(REPO / ".githooks" / "pre-push"), "origin", url],
                    input=f"refs/heads/topic {sha} refs/heads/topic {remote_sha}\n",
                    cwd=repo,
                    env={**env, "PATH": str(tools), "TMPDIR": str(tmp)},
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                code, text = p.returncode, p.stdout + p.stderr
            except subprocess.TimeoutExpired:
                code, text = None, "TIMEOUT"
            last = (text.strip().splitlines() or ["no output"])[-1]
            ok = code == expected and marker in last and "the suite ran" not in text
            wrong += not ok
            print(f"{'ok ' if ok else 'BAD'}  pre-push: {label} -> exit {code}, {last!r}")
    return len(cases), wrong


# The required keys of the profile, with values of the example's form, for a case that writes a
# profile of its own: TOML text, one `key = value` line each.
REQUIRED_TEXT = {
    "memory_project": '"-home-example-Research"',
    "tree_agents": '"/t"',
    "org": '["example-org"]',
    "repository_roots": '["/r"]',
    "leak": '["example-user"]',
}


def profile_text(**keys: str) -> str:
    """A profile of REQUIRED_TEXT with `keys` over it, each a TOML value; a key given as "" is left
    out."""
    return "".join(f"{k} = {v}\n" for k, v in (REQUIRED_TEXT | keys).items() if v)


def refused(got: object, name: str, key: str, kind: str | None) -> bool:
    """Whether `got`, a case's result, is the message of one refusal, "error: " and one line, that
    names the file `name`, the key `key` as a word, and the type word `kind` when given."""
    return (
        isinstance(got, str)
        and got.startswith("error: ")
        and "\n" not in got
        and name in got
        and re.search(rf"(?<![A-Za-z0-9_]){re.escape(key)}(?![A-Za-z0-9_])", got) is not None
        and (kind is None or kind in got)
    )


def schema_cases() -> tuple[int, int]:
    """The cases of the profile's schema: an unknown key, a missing required key, a value of the
    wrong type, an empty required list, a `[setup]` table and the retired keys each exit 2 naming
    the file, the key and, but for an unknown or a retired key, the expected type; an optional
    value that is absent gives its default and no None. Each loads a scratch profile under a `HOME`
    set inside this process, and one runs `harness get` in a child whose environment sets `HOME`:
    (number of cases, number wrong)."""
    wrong, n = 0, 0

    def check(ok: bool, label: str) -> None:  # noqa: FBT001 -- the form of every selftest's check
        nonlocal wrong, n
        n += 1
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  profile: schema: {label}")

    with tempfile.TemporaryDirectory(prefix="harness-schema-") as tmp_name:
        tmp = pathlib.Path(tmp_name).resolve()
        user = tmp / "user"
        user.mkdir()

        def loaded(text: str) -> object:
            """`load` of the profile `text`, under `HOME` = `user`; a HarnessError's message, or
            any other exception's type and message, in place of the profile."""
            path = tmp / "profile.toml"
            path.write_text(text)
            with mock.patch.dict(os.environ, HOME=str(user)):
                try:
                    return load(path)
                except HarnessError as e:
                    return f"error: {e}"
                except Exception as e:  # noqa: BLE001 -- the case reports what broke, and the next case runs
                    return f"raised {type(e).__name__}: {e}"

        example = DUMMY.read_text()
        # (label, profile text, the key the refusal names, the type word it names)
        refusals: list[tuple[str, str, str, str | None]] = [
            ("an unknown key", example + 'nosuchkey = "x"\n', "nosuchkey", None),
            ("a [setup] table", example + '\n[setup]\nfrontends = ["claude"]\n', "setup", None),
            ("a nested table of an unknown key", profile_text() + '[table]\nk = "~/t"\n', "table", None),
            ("a number as `harness`", profile_text(harness="1"), "harness", "str"),
            ("a list as `home`", profile_text(home='["/h"]'), "home", "str"),
            ("a number as `template_host`", profile_text(template_host="1"), "template_host", "str"),
            ("a string as `org`", profile_text(org='"example-org"'), "org", "list"),
            (
                "a number in `repository_roots`",
                profile_text(repository_roots='["/r", 1]'),
                "repository_roots",
                "list",
            ),
            (
                "a nested list as `protected_dir`",
                profile_text(protected_dir='[["~/n"]]'),
                "protected_dir",
                "list",
            ),
            ("an empty `leak`", profile_text(leak="[]"), "leak", "list"),
            ("an empty `org`", profile_text(org="[]"), "org", "list"),
            ("an empty `repository_roots`", profile_text(repository_roots="[]"), "repository_roots", "list"),
            ("a string as `develop`", profile_text(develop='"yes"'), "develop", "true or false"),
        ]
        refusals += [
            (f"no `{key}`", profile_text(**{key: ""}), key, "str" if kind.startswith('"') else "list")
            for key, kind in REQUIRED_TEXT.items()
        ]
        # A key with no type word is refused as a key that the profile does not have, whatever its
        # value.
        for label, text, key, kind in refusals:
            got = loaded(text)
            check(
                refused(got, "profile.toml", key, kind) and (kind is not None or "no key of" in str(got)),
                f"{label} is refused, naming the file and {key} -> {got}",
            )
        # The retired keys exit 2 with the message of the file that replaces each.
        for key, value, replacement in (
            ("extra_domain", '["x.org"]', "network.toml"),
            ("opencode_providers", "{}", "providers.toml"),
            ("omp_providers", "{}", "providers.toml"),
        ):
            got = loaded(f"{profile_text()}{key} = {value}\n")
            check(
                refused(got, "profile.toml", key, None)
                and str(tmp / replacement) in str(got)
                and (replacement == "network.toml" or "examples/providers.toml" in str(got)),
                f"the retired key {key} is refused, naming {replacement} beside the profile -> {got}",
            )
        # An absent optional value gives its default, and no field is None.
        got = loaded(profile_text())
        expected: dict[str, object] = {
            "home": str(user),
            "harness": str(REPO),
            "template_host": "",
            "autocommit_branch": "main",
            "launchd_prefix": "",
            "develop": False,
            "docs_exceptions": (),
            "docs_additions": (),
            "protected_dir": (),
        }
        actual = {k: getattr(got, k, "missing") for k in expected}
        check(
            isinstance(got, Profile)
            and actual == expected
            and all(getattr(got, f.name) is not None for f in dataclasses.fields(got)),
            f"the required keys alone: each optional value at its default, no field None -> {actual}",
        )
        # An optional string that the profile leaves unset is no value of a template or of `get`.
        unset: list[str] = []
        if isinstance(got, Profile):
            bare = got
            for call in (
                lambda: get(bare, "template_host"),
                lambda: get(bare, "launchd_prefix"),
                lambda: render_file(REPO / "launchagents" / "kaimon.plist", bare),
            ):
                try:
                    unset.append(f"rendered {call()!r}")
                except HarnessError as e:
                    unset.append(str(e))
        check(
            len(unset) == 3
            and "'template_host'" in unset[0]
            and "'launchd_prefix'" in unset[1]
            and "{launchd_prefix}" in unset[2],
            f"an unset optional string: harness get and a template that names it exit 2 -> {unset}",
        )
        got = loaded(profile_text(docs_exceptions="[]"))
        check(
            isinstance(got, Profile) and got.docs_exceptions == (),
            f"an empty optional list loads -> {getattr(got, 'docs_exceptions', got)}",
        )
        got = loaded(example)
        check(
            isinstance(got, Profile) and got.org == ("example-org", "example-user") and got.develop is False,
            f"examples/profile.toml loads -> {getattr(got, 'org', got)}",
        )
        # `harness get` with an unknown key: exit 2 and one line, under a scratch HOME in the child.
        (tmp / "unknown.toml").write_text(example + 'nosuchkey = "x"\n')
        env = {**os.environ, "HOME": str(user)}
        env.pop("RESEARCH_HARNESS_PROFILE", None)
        p = subprocess.run(
            [
                sys.executable,
                str(REPO / "bin" / "harness"),
                "--profile",
                str(tmp / "unknown.toml"),
                "get",
                "org",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        said = [line for line in p.stderr.splitlines() if line.startswith("harness get: ")]
        check(
            p.returncode == 2
            and len(said) == 1
            and "unknown.toml" in said[0]
            and "nosuchkey" in said[0]
            and "Traceback" not in p.stderr,
            f"harness get with an unknown key exits 2 with one line -> exit {p.returncode}, {said}",
        )
    return n, wrong


def models_schema_cases() -> tuple[int, int]:
    """The cases of the model tables' schema: a table that no frontend reads, an unknown key, a
    missing tier and a value of the wrong type each exit 2 naming the file, the key and, but for an
    unknown key, the expected type; an old tier name is named ahead of an unknown key; an absent
    table gives its default and no None. Each loads a scratch models.toml: (number of cases, number
    wrong)."""
    wrong, n = 0, 0

    def check(ok: bool, label: str) -> None:  # noqa: FBT001 -- the form of every selftest's check
        nonlocal wrong, n
        n += 1
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  profile: models schema: {label}")

    with tempfile.TemporaryDirectory(prefix="harness-models-schema-") as tmp_name:
        tmp = pathlib.Path(tmp_name).resolve()
        models_example = (REPO / "examples" / "models.toml").read_text()

        def models_loaded(text: str) -> object:
            path = tmp / "models.toml"
            path.write_text(text)
            try:
                return read_models(path)
            except HarnessError as e:
                return f"error: {e}"
            except Exception as e:  # noqa: BLE001 -- the case reports what broke, and the next case runs
                return f"raised {type(e).__name__}: {e}"

        claude = '[claude]\nlarge = "opus"\nmedium = "sonnet"\nsmall = "haiku"\n'
        # (label, text, the key the refusal names, the type word it names)
        model_refusals: list[tuple[str, str, str, str | None]] = [
            (
                "a top-level table that no frontend reads",
                models_example + '\n[nosuchtable]\nx = "y"\n',
                "nosuchtable",
                None,
            ),
            ("a key of [claude] that is no tier", claude + 'huge = "opus"\n', "huge", None),
            ("[claude] without a tier", claude.replace('small = "haiku"\n', ""), "small", "str"),
            ("a number as a tier of [claude]", claude.replace('large = "opus"', "large = 1"), "large", "str"),
            (
                "a key of [antigravity] that is no tier",
                '[antigravity]\nlarge = "flash"\neffort = "x"\n',
                "effort",
                None,
            ),
            ("a number as a tier of [antigravity]", "[antigravity]\nlarge = 1\n", "large", "str"),
            ("a number in [model_overrides]", claude + "[model_overrides]\nbuilder = 1\n", "builder", "str"),
            ("a string as a context limit", claude + '[context_limits]\n"a/b" = "x"\n', "a/b", "integer"),
            ("a [councils] entry that is no list", claude + '[councils]\njudge = "x"\n', "judge", "list"),
            ("a sub-table of [omp] that no frontend reads", claude + "[omp.nosuch]\nx = 1\n", "nosuch", None),
            ("a number in [omp.models]", claude + "[omp.models]\nsmall = 1\n", "small", "str"),
            ("a top-level value that is no table", 'claude = "opus"\n', "claude", "table"),
            (
                "[antigravity.model_overrides] that is no table",
                '[antigravity]\nmodel_overrides = "flash"\n',
                "model_overrides",
                "table",
            ),
            (
                "a number in [antigravity.model_overrides]",
                "[antigravity.model_overrides]\nbuilder = 1\n",
                "builder",
                "str",
            ),
            ("a blank tier of [claude]", claude.replace('large = "opus"', 'large = " "'), "large", "str"),
            ("a [councils] entry that is a number", claude + "[councils]\njudge = 1\n", "judge", "list"),
            (
                "a blank seat model",
                claude + '[councils]\njudge = [{ name = "s", model = " " }]\n',
                "judge",
                "str",
            ),
        ]
        # A key with no type word is refused as a table, a sub-table or a tier that the file may not
        # hold, whatever its value.
        for label, text, key, kind in model_refusals:
            got = models_loaded(text)
            check(
                refused(got, "models.toml", key, kind)
                and (kind is not None or re.search(r"\bno (table|sub-table|tier)\b", str(got)) is not None),
                f"{label} is refused, naming the file and {key} -> {got}",
            )
        got = models_loaded(claude.replace("small", "haiku") + 'huge = "x"\n')
        check(
            isinstance(got, str) and "rename haiku to small" in got and "huge" not in got,
            f"an old tier name is named ahead of an unknown key -> {got}",
        )
        # An absent optional table gives its default, and no field is None.
        got = models_loaded(claude + '[models]\nlarge = "a/l"\n')
        shared = getattr(got, "shared", None)
        tables = [getattr(got, name, None) for name in ("shared", "opencode", "omp")]
        check(
            isinstance(got, Models)
            and got.antigravity == {}
            and got.antigravity_overrides == {}
            and isinstance(shared, ModelTables)
            and shared.tiers == {"large": "a/l"}
            and all(
                isinstance(t, ModelTables)
                and t.model_overrides == {}
                and t.councils == {}
                and t.context_limits == {}
                and all(getattr(t, f.name) is not None for f in dataclasses.fields(t))
                for t in tables
            )
            and all(getattr(got, f.name) is not None for f in dataclasses.fields(got)),
            f"a models.toml without [antigravity], [model_overrides], [councils] and [opencode]: each "
            f"table at its default, none None -> {got}",
        )
        (tmp / "no-claude.toml").write_text('[models]\nlarge = "a/l"\n')
        try:
            missing = f"loaded {tier_table(tmp / 'no-claude.toml', 'Claude Code')}"
        except HarnessError as e:
            missing = str(e)
        check(
            "has no [claude] table" in missing and str(tmp / "no-claude.toml") in missing,
            f"tier_table of a models.toml without [claude] exits 2 -> {missing}",
        )
        tables = model_tables(tmp / "models.toml", "opencode") if isinstance(got, Models) else None
        check(
            isinstance(tables, ModelTables)
            and tables.tiers == {"large": "a/l"}
            and tables.councils == {}
            and tables.path == tmp / "models.toml",
            f"model_tables of a models.toml without [opencode]: the shared tables alone -> {tables}",
        )
        # The effort of an agent: its `variants` entry, else its `reasoning_effort` entry, else the
        # `model_variants` entry of its model; none for an agent with no model.
        efforts = ModelTables(
            path=tmp / "models.toml",
            model_variants={"a/l": "medium"},
            variants={"judge": "high"},
            reasoning_effort={"judge": "low", "seat": "low"},
        )
        got_efforts = [
            agent_effort("judge", "a/l", efforts),
            agent_effort("seat", "a/l", efforts),
            agent_effort("builder", "a/l", efforts),
            agent_effort("builder", None, efforts),
        ]
        check(
            got_efforts == ["high", "low", "medium", None],
            f"agent_effort: variants, then reasoning_effort, then model_variants -> {got_efforts}",
        )
        got = models_loaded(models_example)
        check(
            isinstance(got, Models)
            and got.claude == {"large": "opus", "medium": "sonnet", "small": "haiku"}
            and got.omp.tiers == {"small": "provider-d/small-model"}
            and got.shared.councils["julia-critic"][0]
            == Seat("critic-b", "provider-c/other-model", verify=True),
            f"examples/models.toml loads -> {getattr(got, 'claude', got)}",
        )
    return n, wrong


def home_cases():
    """The cases of `home` and of `~` in a value, each through `load` of a profile in a scratch
    directory whose `HOME` is set inside this process, and `harness get` on an unedited copy of
    examples/profile.toml: (number of cases, number wrong)."""
    wrong, n = 0, 0

    def check(ok: bool, label: str) -> None:  # noqa: FBT001 -- the form of every selftest's check
        nonlocal wrong, n
        n += 1
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  profile: {label}")

    with tempfile.TemporaryDirectory(prefix="harness-home-") as tmp:
        tmp = pathlib.Path(tmp).resolve()
        user = tmp / "user"
        user.mkdir()

        def loaded(text: str, home_env: str = str(user), home: str | None = None) -> Profile | str:
            """`load` of the profile of REQUIRED_TEXT with `text` after it, under `HOME` =
            `home_env`; a HarnessError's message, or any other exception's type and message, in
            place of the profile."""
            (tmp / "profile.toml").write_text(profile_text() + text)
            with mock.patch.dict(os.environ, HOME=home_env):
                try:
                    return load(tmp / "profile.toml", home=home)
                except HarnessError as e:
                    return f"error: {e}"
                except Exception as e:  # noqa: BLE001 -- the case reports what broke, and the next case runs
                    return f"raised {type(e).__name__}: {e}"

        def refused(got: object, key: str = "home") -> bool:
            return isinstance(got, str) and got.startswith("error: ") and f"`{key}`" in got

        got = loaded('harness = "~/a"\n')
        check(
            isinstance(got, Profile) and got.home == str(user) and got.harness == f"{user}/a",
            f"no `home`: the running user's home, and `~/a` below it -> {got}",
        )
        got = loaded('harness = "~/a"\n', home_env=str(user) + "/")
        check(
            isinstance(got, Profile) and got.home == str(user),
            f"no `home`, $HOME with a trailing slash: none in `home` -> {got}",
        )
        got = loaded('home = "/h"\nharness = "~/a"\n')
        check(
            isinstance(got, Profile) and got.home == "/h" and got.harness == "/h/a",
            f"a given `home` -> {got}",
        )
        got = loaded('home = "/h/"\nharness = "~/a"\nlaunchd_prefix = "~"\n')
        check(
            isinstance(got, Profile)
            and got.home == "/h"
            and got.harness == "/h/a"
            and got.launchd_prefix == "/h",
            f"a given `home` with a trailing slash: removed, so no `//` -> {got}",
        )
        got = loaded('home = "/"\nharness = "~/a"\nlaunchd_prefix = "~"\n')
        check(
            isinstance(got, Profile)
            and got.home == "/"
            and got.harness == "/a"
            and got.launchd_prefix == "/",
            f"`home` the root directory -> {got}",
        )
        for text, label in (
            ('home = "h"\n', "a relative `home`"),
            ('home = ""\n', "an empty `home`"),
            ('home = "~"\n', "`home` = `~`"),
            ('home = "~/h"\n', "`home` below `~`"),
            ('home = "/h/~x"\n', "`home` with a `~` inside"),
            ("home = 1\n", "a number as `home`"),
            ('home = ["/h"]\n', "a list as `home`"),
        ):
            got = loaded(text)
            check(refused(got), f"{label} is refused, naming the key -> {got}")
        got = loaded('harness = "~"\n', home_env="relative")
        check(refused(got), f"no `home` and a relative $HOME: refused, naming the key -> {got}")
        with mock.patch.object(pathlib.Path, "home", mock.Mock(side_effect=RuntimeError("no home"))):
            got = loaded('harness = "~"\n')
        check(refused(got), f"no `home` and no home directory: refused, naming the key -> {got}")
        got = loaded('harness = "~"\n', home="/fallback")
        check(
            isinstance(got, Profile) and got.home == "/fallback" and got.harness == "/fallback",
            f"no `home`, and the caller's home -> {got}",
        )
        got = loaded('home = "/h"\nharness = "~"\n', home="/fallback")
        check(
            isinstance(got, Profile) and got.home == "/h",
            f"a given `home` over the caller's home -> {got}",
        )
        # `~` in each form, in a string and in a list item, on keys that the schema knows.
        (tmp / "profile.toml").write_text(
            'home = "/h"\nharness = "~"\ntree_agents = "~/x/y"\norg = ["~/a", "b", "~", "a~b"]\n'
            'memory_project = "a~b"\nlaunchd_prefix = "a/~"\nautocommit_branch = "~x"\n'
            'template_host = "~name/x"\ndevelop = true\nrepository_roots = ["/r"]\nleak = ["l"]\n'
        )
        try:
            got = load(tmp / "profile.toml")
        except HarnessError as e:
            got = f"error: {e}"
        except Exception as e:  # noqa: BLE001 -- the case reports what broke, and the next case runs
            got = f"raised {type(e).__name__}: {e}"
        wanted: dict[str, object] = {
            "home": "/h",
            "harness": "/h",
            "tree_agents": "/h/x/y",
            "org": ("/h/a", "b", "/h", "a~b"),
            "memory_project": "a~b",
            "launchd_prefix": "a/~",
            "autocommit_branch": "~x",
            "template_host": "~name/x",
            "develop": True,
        }
        for key, value in wanted.items():
            check(
                isinstance(got, Profile) and getattr(got, key) == value,
                f"{key} -> {getattr(got, key, got)!r}, expected {value!r}",
            )
        # The values of no string or list: each a refusal that names the file and the key.
        for text, key in (
            ("harness = 3\n", "harness"),
            ('protected_dir = [["~/n"]]\n', "protected_dir"),
            ('[table]\nk = "~/t"\n', "table"),
        ):
            got = loaded(text)
            check(
                refused(got, key) and "profile.toml" in str(got),
                f"{text.strip()!r} is refused, naming the file and the key -> {got}",
            )
        # examples/profile.toml as copied: `harness get` under the scratch HOME.
        copy = tmp / "copy.toml"
        copy.write_bytes(DUMMY.read_bytes())
        env = {**os.environ, "HOME": str(user)}
        env.pop("RESEARCH_HARNESS_PROFILE", None)
        for key, expected in (
            ("home", str(user)),
            ("harness", f"{user}/Research/Harness"),
            ("tree_agents", f"{user}/Research/Environment/Agents"),
            ("repository_roots", f"{user}/Research/Packages\n{user}/Research/Experiments"),
        ):
            p = subprocess.run(
                [sys.executable, str(REPO / "bin" / "harness"), "--profile", str(copy), "get", key],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            check(
                p.returncode == 0 and p.stdout.strip() == expected,
                f"examples/profile.toml as copied: harness get {key} -> exit {p.returncode}, {p.stdout.strip()!r}",
            )
        dummy = tomllib.loads(DUMMY.read_text())
        check(
            "home" not in dummy and dummy["leak"][0] == "~",
            f"examples/profile.toml: no `home` key, and `~` as the home entry of `leak` -> "
            f"{'home' in dummy}, {dummy['leak']}",
        )
    return n, wrong


def branch_cases():
    """The cases of the default of `autocommit_branch`, each through `load` of a profile in a
    scratch directory under a host name that `socket.gethostname` gives inside this process, and
    `harness get autocommit_branch`: (number of cases, number wrong)."""
    wrong, n = 0, 0

    def check(ok: bool, label: str) -> None:  # noqa: FBT001 -- the form of every selftest's check
        nonlocal wrong, n
        n += 1
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  profile: autocommit_branch: {label}")

    with tempfile.TemporaryDirectory(prefix="harness-branch-") as tmp:
        tmp = pathlib.Path(tmp)

        def branch(text: str, host: str) -> str:
            """`autocommit_branch` of the profile of REQUIRED_TEXT and `text` loaded on the host
            `host`; a HarnessError's message in its place."""
            (tmp / "profile.toml").write_text(profile_text(home='"/h"') + text)
            with mock.patch("socket.gethostname", return_value=host):
                try:
                    return load(tmp / "profile.toml").autocommit_branch
                except HarnessError as e:
                    return f"error: {e}"

        # (label, profile text, host name, expected branch)
        for label, text, host, expected in [
            ("no `template_host` -> main", "", "beta", "main"),
            ("`template_host` is this host -> main", 'template_host = "alpha"\n', "alpha", "main"),
            ("another host -> memory/<host>", 'template_host = "alpha"\n', "beta", "memory/beta"),
            (
                "a given branch with `template_host`, on another host",
                'template_host = "alpha"\nautocommit_branch = "own"\n',
                "beta",
                "own",
            ),
            (
                "a given branch with `template_host`, on the template host",
                'template_host = "alpha"\nautocommit_branch = "own"\n',
                "alpha",
                "own",
            ),
            ("a given branch without `template_host`", 'autocommit_branch = "own"\n', "beta", "own"),
            (
                "a host name with a domain part, another host",
                'template_host = "alpha"\n',
                "beta.example.org",
                "memory/beta",
            ),
            (
                "a host name with a domain part, the template host",
                'template_host = "alpha"\n',
                "alpha.example.org",
                "main",
            ),
            ("an empty host name -> main", 'template_host = "alpha"\n', "", "main"),
            (
                "a host name that differs in case only is another host",
                'template_host = "alpha"\n',
                "Alpha",
                "memory/Alpha",
            ),
        ]:
            got = branch(text, host)
            check(got == expected, f"{label} -> {got!r}")
        for text, label in (
            ('template_host = ""\n', "an empty `template_host`"),
            ('template_host = "alpha.example.org"\n', "a `template_host` with a domain part"),
            ("template_host = 1\n", "a number as `template_host`"),
        ):
            got = branch(text, "beta")
            check(
                got.startswith("error: ") and "`template_host`" in got,
                f"{label} is refused, naming the key -> {got!r}",
            )
        # `harness get autocommit_branch` prints the default.
        (tmp / "profile.toml").write_text(profile_text(home='"/h"', template_host='"alpha"'))
        out = io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            mock.patch("socket.gethostname", return_value="beta.example.org"),
        ):
            try:
                status = cmd_get(argparse.Namespace(profile=tmp / "profile.toml", key="autocommit_branch"))
            except HarnessError as e:
                status = f"error: {e}"
        check(
            status == 0 and out.getvalue() == "memory/beta\n",
            f"harness get prints the default -> {status}, {out.getvalue()!r}",
        )
        dummy = tomllib.loads(DUMMY.read_text())
        check(
            isinstance(dummy.get("template_host"), str) and "autocommit_branch" not in dummy,
            f"examples/profile.toml sets `template_host` and no `autocommit_branch` -> "
            f"{dummy.get('template_host')!r}, {dummy.get('autocommit_branch')!r}",
        )
    return n, wrong


def selftest():
    """The render's cases, the tree-name cases, the cases of `home` and `~`, of `autocommit_branch`,
    of the schema of the profile and of the model tables, the cases of `--commits`, and the
    `origin` case, the kit case, the case with no environment, the cases of an
    environment without the tools of the strict profile, the cases of a check of the strict profile
    that fails and the branch cases of the pre-push hook:
    (number of cases, number wrong)."""
    wrong = 0
    for template, profile, expected in CASES:
        try:
            got = (
                render_text(template, profile)
                if isinstance(template, str)
                else render_data(template, profile)
            )
        except KeyError, TypeError, ValueError:
            got = None
        wrong += got != expected
        print(f"{'ok ' if got == expected else 'BAD'}  {template!r} -> {got!r}")
    pattern = name_pattern(["Pkg", "my-paper", "org"])
    for line, expected in NAME_CASES:
        got = name_hits(line, pattern, "org/Repo")
        wrong += got != expected
        print(f"{'ok ' if got == expected else 'BAD'}  {line!r} -> {got!r}")
    n0, w0 = home_cases()
    n1, w1 = branch_cases()
    n, w = commit_cases()
    ns, ws = schema_cases()
    nm, wm = models_schema_cases()
    n, w = n + n0 + n1 + ns + nm, w + w0 + w1 + ws + wm
    n2, w2 = prepush_case()
    # As inside a git hook: git's exec path first on the PATH.
    exec_path = subprocess.run(
        ["git", "--exec-path"],  # noqa: S607 -- git runs from PATH
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    n3, w3 = prepush_case(exec_path + os.pathsep + os.environ.get("PATH", ""))
    n4, w4 = prepush_branch_cases()
    n5, w5 = prepush_case(kit_fails="update-check")
    n6, w6 = prepush_case(no_environment=True)
    for lacks in (("ruff",), ("basedpyright",), ("ruff", "basedpyright")):
        n7, w7 = prepush_case(lacks=lacks)
        n6, w6 = n6 + n7, w6 + w7
    for fails in STRICT:
        n7, w7 = prepush_case(fails=fails)
        n6, w6 = n6 + n7, w6 + w7
    return len(CASES) + len(NAME_CASES) + n + n2 + n3 + n4 + n5 + n6, wrong + w + w2 + w3 + w4 + w5 + w6


def register(sub: fmt.Subcommands) -> None:
    r = sub.add_parser(
        "render",
        help="print a template rendered with the profile",
        description="Print TEMPLATE with each placeholder `{key}` replaced by its profile value. "
        "Read-only; a placeholder that the profile lacks exits with status 2.",
    )
    r.add_argument("template", help="the path of the template file")
    r.set_defaults(run=cmd_render)
    g = sub.add_parser(
        "get",
        help="print a profile value, one line per item of a list",
        description="Print the profile value of KEY, one line per item of a list. Read-only; a key "
        "that the profile lacks exits with status 2.",
    )
    g.add_argument("key", help="a key of the profile, such as `home`")
    g.set_defaults(run=cmd_get)
    l = sub.add_parser(
        "leaks",
        help="search the repository and its renders for the private strings of the profile's `leak` list",
        description="Search the tracked files of this repository for the private strings of the "
        "profile's `leak` list and for the names of the research tree, and the templates, "
        "rendered with the dummy profile, for the private strings. Read-only; exits 1 on "
        "a hit.",
    )
    l.add_argument(
        "--commits",
        metavar="FILE",
        help="also search the paths and lines that each commit of FILE adds, and its message, "
        "one SHA per line",
    )
    l.set_defaults(run=cmd_leaks)
