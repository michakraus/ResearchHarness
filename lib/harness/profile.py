"""The private profile, and the render of a harness template with it.

    harness render TEMPLATE    # print the rendered text
    harness get KEY            # print a profile value, one line per item
    harness leaks              # the repository and its renders hold no leak string
    harness leaks --commits F  # nor does a line that a commit of F adds or its message, one SHA per line
    harness test               # the render's own cases, with every other module's

The profile is a TOML file of every value that names a person, an institution or a machine:
`harness --profile F`, else $RESEARCH_HARNESS_PROFILE, else ~/.config/research-harness/profile.toml.
`examples/profile.toml` is a dummy that shows every key.

A placeholder is `{name}`: lower case, digits and `_`, no colon, so OpenCode's `{env:…}` and
`{file:…}` pass through. `name` is a profile key. A string value substitutes. A list value
repeats what holds it, once per item in profile order, and removes it for an empty list: in a
parsed JSON list (`render_data`) the string element, in text (`render_text`) the line, which must
then end in a comma. A table value renders in text only, on a line that holds the placeholder
alone: the members of a JSON object, at that line's indentation, with no comma after the last.
More than one list placeholder in one element or line is an error, and so is
a placeholder that the profile does not define: a template that renders with a hole in it is a
grant or a deny that silently matches nothing. The one exception is a key of DEFAULTS, which
`render` and `leaks` fill with its default where the profile has none: `autocommit_branch` renders
`main`, and `providers`, which `harness install` fills from providers.toml, no provider.
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
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

from . import REPO, HarnessError, frontends, frontmatter, network

DEFAULT = pathlib.Path.home() / ".config" / "research-harness" / "profile.toml"
DUMMY = REPO / "examples" / "profile.toml"

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

# The keys that `render` and `leaks` give a value when the profile has none. `harness install`
# fills `providers` from providers.toml.
DEFAULTS = {"autocommit_branch": "main", "providers": {}}


def location(path=None):
    """The path of the profile: `path`, else the environment's, else the default path."""
    return pathlib.Path(path or os.environ.get("RESEARCH_HARNESS_PROFILE") or DEFAULT)


def load(path=None):
    """The profile at `path`, else the environment's, else the default path."""
    path = location(path)
    if not path.is_file():
        raise HarnessError(f"no profile at {path} — copy examples/profile.toml there and fill it in")
    try:
        return tomllib.loads(path.read_bytes().decode("utf-8"))
    except UnicodeDecodeError:
        raise HarnessError(f"{path} is not UTF-8") from None
    except tomllib.TOMLDecodeError as e:
        raise HarnessError(f"{path} is not TOML: {e}") from None


def value(name, profile, where):
    if name not in profile:
        raise KeyError(f"placeholder {{{name}}} in {where!r}: the profile has no key {name!r}")
    return profile[name]


def get(profile, key):
    """The profile's value of `key`; a missing key is a `HarnessError`."""
    if key not in profile:
        raise HarnessError(f"the profile has no key {key!r} — examples/profile.toml shows it")
    return profile[key]


def models_path(args):
    """The model tables: `--models`, else $RESEARCH_HARNESS_MODELS, else models.toml beside the profile."""
    if getattr(args, "models", None):
        return pathlib.Path(args.models)
    if os.environ.get("RESEARCH_HARNESS_MODELS"):
        return pathlib.Path(os.environ["RESEARCH_HARNESS_MODELS"])
    profile = args.profile or os.environ.get("RESEARCH_HARNESS_PROFILE") or DEFAULT
    return pathlib.Path(profile).parent / "models.toml"


def network_path(profile=None):
    """The overlay of the network lists: network.toml beside the profile `profile`, else beside
    the profile of `location`."""
    return location(profile).parent / "network.toml"


def providers_path(profile=None):
    """The model providers of OpenCode and oh-my-pi (`providers.py`): providers.toml beside the
    profile `profile`, else beside the profile of `location`."""
    return location(profile).parent / "providers.toml"


# The old keys of a table of the tiers, Claude Code's names, and the neutral tier of each.
OLD_TIERS = {"opus": "large", "sonnet": "medium", "haiku": "small"}


def read_models(path):
    """The model tables at `path`, parsed; a file that does not exist, cannot be read, is not
    UTF-8 or is not TOML exits 2, and so does a table of the tiers, [claude], [models],
    [opencode.models] or [omp.models], with a key of OLD_TIERS: one message names each rename of
    each table, and a missing [claude]."""
    path = pathlib.Path(path)
    if not path.is_file():
        raise HarnessError(f"no model tables at {path} — copy examples/models.toml there and fill it in")
    try:
        models = tomllib.loads(path.read_bytes().decode("utf-8"))
    except OSError as e:
        raise HarnessError(f"{path} cannot be read: {e.strerror}") from None
    except UnicodeDecodeError:
        raise HarnessError(f"{path} is not UTF-8") from None
    except tomllib.TOMLDecodeError as e:
        raise HarnessError(f"{path} is not TOML: {e}") from None
    opencode, omp = models.get("opencode"), models.get("omp")
    renames = []
    for name, table in [("claude", models.get("claude")), ("models", models.get("models")),
                        ("omp.models", omp.get("models") if isinstance(omp, dict) else None),
                        ("opencode.models", opencode.get("models") if isinstance(opencode, dict) else None)]:
        old = [t for t in OLD_TIERS if isinstance(table, dict) and t in table]
        if old:
            renames.append(f"in [{name}] rename " + ", ".join(f"{t} to {OLD_TIERS[t]}" for t in old))
    if renames:
        add = [] if isinstance(models.get("claude"), dict) else [
            "add a [claude] table of the tiers, which examples/models.toml shows"]
        raise HarnessError(f"{path} names tiers by their old names: " + "; ".join(renames + add))
    return models


def tier_table(path, name, frontend):
    """{tier: model} of the table [`name`] of the model tables at `path`, which maps each tier to a
    model of `frontend`: exactly the tiers of frontmatter.TIERS, each a string that is not blank;
    any other table exits 2."""
    tiers = frontmatter.TIERS
    table = read_models(path).get(name)
    if not isinstance(table, dict):
        raise HarnessError(f"{path} has no [{name}] table, which maps the tiers {', '.join(tiers)} to {frontend}'s "
                           "models — examples/models.toml shows it")
    missing, unknown = [t for t in tiers if t not in table], sorted(set(table) - set(tiers))
    if missing or unknown:
        raise HarnessError(f"{path}: [{name}] holds the tiers {', '.join(tiers)}, one {frontend} model each; "
                           + "; ".join([f"it has no {', '.join(missing)}"] * bool(missing)
                                       + [f"{', '.join(unknown)} is no tier"] * bool(unknown)))
    wrong = [t for t in tiers if not isinstance(table[t], str) or not table[t].strip()]
    if wrong:
        raise HarnessError(f"{path}: the tier {', '.join(wrong)} of [{name}] is not a string that names a model")
    return {t: table[t] for t in tiers}


# The model tables that OpenCode and oh-my-pi share, at the top level of models.toml; each is
# optional. `models` maps a tier to a model; `model_overrides` an agent to its model in place of its
# tier's; `model_variants` a model to the effort of every agent on it; `variants` and
# `reasoning_effort` an agent or a council seat to its effort, over `model_variants`; `councils` an
# agent to its seats; `context_limits` a model to the input tokens it may hold. [opencode] and
# [omp] may hold the same sub-tables, each key of which replaces the shared one for that frontend
# alone. [claude] is Claude Code's table of the tiers, which reads none of them.
MODEL_TABLES = ["models", "model_overrides", "model_variants", "variants", "reasoning_effort", "councils",
                "context_limits"]
# The frontends that read MODEL_TABLES, each with a table of its own overrides.
SHARING = ("opencode", "omp")
# A council has one to eight seats beside its agent.
COUNCIL_SEATS = range(1, 9)


def model_tables(path, name):
    """The shared tables MODEL_TABLES of the model tables at `path`, each with the keys of its
    sub-table of [`name`] over its own, every one present, and `path`. A council is a list of seats
    {name, model}, at most one of them with `verify = true`, the seat that judges each verify
    round alone; no two seats share a name. A context limit is a positive integer. Any other table,
    at the top level or in [`name`], exits 2."""
    path = pathlib.Path(path)
    data = read_models(path)
    tops = ["claude", *MODEL_TABLES, *SHARING]
    if tiers := [t for t in frontmatter.TIERS if t in data]:
        raise HarnessError(f"{path}: the tiers {', '.join(tiers)} are at the top level; move them into [models]")
    if unknown := sorted(set(data) - set(tops)):
        raise HarnessError(f"{path} has no table {', '.join(unknown)}; it has {', '.join(tops)}")
    table = data.get(name, {})
    if not isinstance(table, dict):
        raise HarnessError(f"{path}: [{name}] is not a table")
    if tiers := [t for t in frontmatter.TIERS if t in table]:
        raise HarnessError(f"{path}: [{name}] holds the tiers {', '.join(tiers)}; move them into [models], or "
                           f"into [{name}.models] for {name} alone")
    if unknown := sorted(set(table) - set(MODEL_TABLES)):
        raise HarnessError(f"{path}: [{name}] has no sub-table {', '.join(unknown)}; "
                           f"it has {', '.join(MODEL_TABLES)}")
    models = {}
    for sub in MODEL_TABLES:
        for label, part in ((f"[{sub}]", data.get(sub, {})), (f"[{name}.{sub}]", table.get(sub, {}))):
            if not isinstance(part, dict):
                raise HarnessError(f"{path}: {label} is not a table")
        models[sub] = {**data.get(sub, {}), **table.get(sub, {})}
    where = lambda sub: f"[{sub}] or [{name}.{sub}]"  # noqa: E731
    for sub in ("models", "model_overrides", "model_variants", "variants", "reasoning_effort"):
        if wrong := [k for k, v in models[sub].items() if not (isinstance(v, str) and v.strip())]:
            raise HarnessError(f"{path}: the value of {', '.join(wrong)} in {where(sub)} is not a string that is "
                               "not blank")
    if wrong := [k for k, v in models["context_limits"].items() if not (type(v) is int and v > 0)]:
        raise HarnessError(f"{path}: the value of {', '.join(wrong)} in {where('context_limits')} is not a "
                           "positive integer")
    # Each seat is installed as `<name>.md`, so a second seat of one name would replace the first.
    seen = {}
    for agent, seats in models["councils"].items():
        if not (isinstance(seats, list) and all(
                isinstance(s, dict) and {"name", "model"} <= set(s) <= {"name", "model", "verify"} for s in seats)):
            raise HarnessError(f"{path}: councils.{agent} is a list of {{ name = …, model = … }}, "
                               "and one seat may add `verify = true`")
        if len(seats) not in COUNCIL_SEATS:
            raise HarnessError(f"{path}: councils.{agent} has {len(seats)} seats; a council has 1 to 8")
        for seat in seats:
            for key in ("name", "model"):
                if not isinstance(seat[key], str) or not seat[key].strip():
                    raise HarnessError(f"{path}: the seat {key} {seat[key]!r} of councils.{agent} is not a string")
            if not isinstance(seat.get("verify", False), bool):
                raise HarnessError(f"{path}: `verify` of the seat {seat['name']!r} of councils.{agent} is not true or false")
            if seat["name"] in seen:
                raise HarnessError(f"{path}: the seat {seat['name']!r} of councils.{agent} is also a seat "
                                   f"of councils.{seen[seat['name']]}")
            seen[seat["name"]] = agent
        if sum(s.get("verify", False) for s in seats) > 1:
            raise HarnessError(f"{path}: more than one seat of councils.{agent} has `verify = true`")
    models["path"] = path
    return models


def agent_model(name, tier, models, where):
    """The model of the agent `name` of tier `tier` (None for an agent with no tier), with
    `models` from model_tables: its override, else its tier's model, else None, which leaves the
    agent on its caller's model. A tier with no model exits 2, naming `where`."""
    model = None
    if tier is not None:
        if not isinstance(tier, str) or tier not in models["models"]:
            raise HarnessError(f"{where}: the tier {tier!r} has no entry in the models of {models['path']}")
        model = models["models"][tier]
    return models["model_overrides"].get(name, model)


def agent_effort(name, model, models):
    """The effort of the agent or seat `name` on `model`: its `variants` entry, else its
    `reasoning_effort` entry, else the `model_variants` entry of `model`, else None."""
    return models["variants"].get(name, models["reasoning_effort"].get(name, models["model_variants"].get(model)))


def council_description(source, seat, frontend):
    """The description of the council seat `seat` of the agent `source` under `frontend`."""
    verify = " It also judges each verify round, alone." if seat.get("verify") else ""
    return (f"A member of the round-1 critic council of build-part under {frontend}, on {seat['model']}.{verify} "
            f"The same agent as {source}, which has the full description. Spawn it only as the build-part "
            "dispatcher.")


def render_line(line, profile):
    """Substitute every string placeholder in one line; a list placeholder is an error."""

    def substitute(m):
        v = value(m.group(1), profile, m.group(0))
        if not isinstance(v, str):
            kind = "table" if isinstance(v, dict) else "list"
            raise TypeError(f"placeholder {m.group(0)}: a {kind} renders only on a line of its own")
        return v

    return PLACEHOLDER.sub(substitute, line)


def render_text(text, profile):
    """Substitute string placeholders; repeat a line that holds a list placeholder.

    Such a line becomes one copy per item, and disappears for an empty list. It must end in a
    comma, unless the list has exactly one item: a copy of the last entry of a JSON object or
    list would otherwise need a comma it does not have, or leave one dangling. A line that holds a
    table placeholder alone becomes the table's members as JSON (`members`).
    """
    out = []
    for line in text.splitlines(keepends=True):
        if (m := ALONE.fullmatch(line)) and isinstance(profile.get(m.group(2)), dict):
            out.append(members(profile[m.group(2)], m.group(1)))
            continue
        copies = expand(line, profile)
        if len(copies) != 1 and not line.rstrip().endswith(","):
            raise ValueError(f"{line.strip()!r}: a repeated line must end in a comma")
        out += copies
    return "".join(out)


def members(table, indent):
    """The members of `table` as the lines of a JSON object, each line after `indent`, with no
    comma after the last; "" for an empty table."""
    lines = json.dumps(table, indent=2, ensure_ascii=False).splitlines()[1:-1]
    return "".join(f"{indent}{line[2:]}\n" for line in lines)


def expand(text, profile):
    """One string per item of the list placeholder in `text`, or `[text]` rendered."""
    lists = {n for n in PLACEHOLDER.findall(text) if isinstance(value(n, profile, text), list)}
    if not lists:
        return [render_line(text, profile)]
    if len(lists) > 1:
        raise ValueError(f"{text!r}: more than one list placeholder")
    (name,) = lists
    return [render_line(text.replace("{" + name + "}", item), profile) for item in profile[name]]


def render_data(obj, profile):
    """Render a parsed JSON value: keys and strings substitute, list elements expand."""
    if isinstance(obj, dict):
        return {render_line(k, profile): render_data(v, profile) for k, v in obj.items()}
    if isinstance(obj, list):
        out = []
        for item in obj:
            if isinstance(item, str):
                out += expand(item, profile)
            else:
                out.append(render_data(item, profile))
        return out
    if isinstance(obj, str):
        return render_line(obj, profile)
    return obj


def render_file(path, profile):
    """A template rendered as text, so its bytes stay; parsed and re-serialised only for a
    `.json` that holds a list placeholder, which needs the structure."""
    text = pathlib.Path(path).read_text()
    lists = [n for n in PLACEHOLDER.findall(text) if isinstance(profile.get(n), list)]
    try:
        if lists and pathlib.Path(path).suffix == ".json":
            return json.dumps(render_data(json.loads(text), profile), indent=2, ensure_ascii=False) + "\n"
        return render_text(text, profile)
    except (KeyError, TypeError, ValueError) as e:
        raise HarnessError(f"{path}: {e.args[0]}") from e


def cmd_render(args):
    profile = DEFAULTS | load(args.profile)
    if pathlib.Path(args.template).resolve() == network.TEMPLATE:
        cfg = network.apply(json.loads(render_file(args.template, profile)), profile, network_path(args.profile))
        sys.stdout.write(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(render_file(args.template, profile))
    return 0


def cmd_get(args):
    v = get(load(args.profile), args.key)
    print(v if isinstance(v, str) else "\n".join(v))
    return 0


def tree_names(profile):
    """The directory names below every `repository_roots` entry, and the `org` entries."""
    names = set(get(profile, "org"))
    for root in map(pathlib.Path, get(profile, "repository_roots")):
        if not root.is_dir():
            raise HarnessError(f"repository_roots entry {root} is not a directory")
        names |= {p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")}
    return sorted(names)


def name_pattern(names):
    """A whole-word match of any of `names`: no letter, digit or `_` on either side."""
    return re.compile(r"(?<![A-Za-z0-9_])(?:" + "|".join(map(re.escape, names)) + r")(?![A-Za-z0-9_])")


def own_repository(repo=REPO):
    """`owner/name` of the `origin` URL, or None without one."""
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo, capture_output=True, text=True).stdout
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?\s*$", url)
    return m.group(1) if m else None


def name_hits(line, pattern, allowed):
    """The tree names in `line`, after removing every occurrence of `allowed`, the repository's own
    `owner/name`, and of `owner.github.io`, the host of its GitHub Pages site."""
    if allowed:
        line = line.replace(allowed, "").replace(allowed.split("/")[0] + ".github.io", "")
    return pattern.findall(line)


def templates():
    """The templates that `leaks` renders with the dummy profile: TEMPLATES and each adapter's."""
    return TEMPLATES + [t for adapter in frontends.load() for t in adapter.TEMPLATES]


SHA = re.compile(r"[0-9a-f]{7,64}")
# A hunk header; a merge's combined diff has one `@` and one column per parent more.
HUNK = re.compile(r"(@@+) (?:-\S+ )+\+(\d+)")


def read_commits(path):
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
QUOTED = re.compile(rb'\\([0-7]{3}|.)')
ESCAPES = {b"a": 7, b"b": 8, b"t": 9, b"n": 10, b"v": 11, b"f": 12, b"r": 13}


def unquoted(path):
    """`path` of a diff header with git's quotes removed: git writes a path with a byte outside
    printable ASCII, a `"` or a `\\` in double quotes, with C escapes."""
    if len(path) < 2 or path[0] != '"' or path[-1] != '"':
        return path
    return QUOTED.sub(lambda m: bytes([int(m[1], 8) if len(m[1]) == 3 else ESCAPES.get(m[1], m[1][0])]),
                      path[1:-1].encode()).decode(errors="replace")


def added_lines(sha, repo=REPO):
    """(where, text) for each path and line that the commit `sha` adds. A path is that of each
    file that the commit adds or changes against any parent, a rename's new path too, as line 0.
    A line is a `+` line of `git show --format= --text -U0`, so a binary file's lines too; in a
    merge's combined diff, a line with a `+` in any parent's column. No external diff and no
    textconv driver rewrites them."""
    p = subprocess.run(["git", "diff-tree", "-r", "-z", "-m", "--root", "--no-commit-id", "--name-only",
                        "--no-renames", "--diff-filter=d", sha], cwd=repo, capture_output=True)
    if p.returncode:
        raise HarnessError(f"git diff-tree {sha}: {p.stderr.decode(errors='replace').strip()}")
    paths = dict.fromkeys(p.stdout.decode(errors="replace").split("\0"))  # -m names a path once per parent
    out = [(f"{sha[:12]} {path}:0", path) for path in paths if path]
    p = subprocess.run(["git", "show", "--format=", "--text", "-U0", "--no-color", "--no-ext-diff",
                        "--no-textconv", sha], cwd=repo, capture_output=True)
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


def message_lines(sha, repo=REPO):
    """(where, text) for each line of the message of the commit `sha`, `%B`: the raw subject and
    body, trailers too, numbered from 1. The author, the committer and a signature are not read."""
    p = subprocess.run(["git", "show", "-s", "--no-show-signature", "--format=%B", sha], cwd=repo,
                       capture_output=True)
    if p.returncode:
        raise HarnessError(f"git show -s {sha}: {p.stderr.decode(errors='replace').strip()}")
    return [(f"{sha[:12]} message:{n}", line)
            for n, line in enumerate(p.stdout.decode(errors="replace").split("\n"), 1)]


def commit_hits(shas, leak, pattern, allowed, repo=REPO):
    """(where, string) for each leak string and tree name in a path or on a line that one of `shas`
    adds, or on a line of its message."""
    return [(where, s) for sha in shas for where, line in added_lines(sha, repo) + message_lines(sha, repo)
            for s in [s for s in leak if s in line] + name_hits(line, pattern, allowed)]


def cmd_leaks(args, repo=REPO):
    """`harness leaks` on the tracked files and the commits of `repo`; the templates are this
    repository's."""
    profile = load(args.profile)
    leak = profile.get("leak", [])
    if not leak:
        raise HarnessError("the profile's `leak` list is empty — nothing to check against")
    names = tree_names(profile)
    pattern, allowed = name_pattern(names), own_repository(repo)
    dummy = DEFAULTS | load(DUMMY)
    files = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repo, capture_output=True, text=True, check=True
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


CASES = [
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
    ("{\n  {t}\n}\n", {"t": {"a": {"m/x:1": 2}, "b": []}}, '{\n  "a": {\n    "m/x:1": 2\n  },\n  "b": []\n}\n'),
    ("{\n  {t}\n}\n", {"t": {}}, "{\n}\n"),
    ("  x: {t},\n", {"t": {"a": 1}}, None),
    (["{t}"], {"t": {"a": 1}}, None),
]


NAME_CASES = [
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
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="leaks", GIT_AUTHOR_EMAIL="leaks@example.org",
               GIT_COMMITTER_NAME="leaks", GIT_COMMITTER_EMAIL="leaks@example.org")
    wrong = 0
    with tempfile.TemporaryDirectory(prefix="harness-leaks-") as tmp:
        repo = pathlib.Path(tmp) / "repo"
        repo.mkdir()

        def git(*args, **extra):
            """`git args` in the fixture; `extra` sets variables of its environment."""
            return subprocess.run(["git", *args], cwd=repo, env={**env, **extra}, check=True, capture_output=True,
                                  text=True).stdout.strip()

        def commit(name, data=None, *move):
            if move:
                git("mv", "--", name, *move)
            elif data is None:
                git("rm", "-q", "--", name)
            else:
                (repo / name).write_bytes(data)
                git("add", "--", name)
            git("commit", "-q", "-m", "change")  # a clean message: the cases of a message are below
            return git("rev-parse", "HEAD")

        def note(message):
            """An empty commit with the message `message`, bytes taken as they are."""
            (pathlib.Path(tmp) / "message").write_bytes(message)
            git("commit", "-q", "--allow-empty", "--allow-empty-message", "--cleanup=verbatim",
                "-F", str(pathlib.Path(tmp) / "message"))
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
            ("a tree name in a path that one commit adds and a later one renames away",
             [path_added, path_renamed], 1),
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
        print(f"{'ok ' if got == expected else 'BAD'}  leaks --commits: the place of a leak in a path "
              f"with a space -> {got}")
        got = [where for where, _ in commit_hits([merge], ["LEAK"], pattern, None, repo)]
        expected = [f"{merge[:12]} side-Pkg.md:0"]
        wrong += got != expected
        print(f"{'ok ' if got == expected else 'BAD'}  leaks --commits: a tree name in a path that a "
              f"merge brings from its side parent -> {got}")
        # (label, shas, tree names, allowed owner/name, expected places); the leak string is LEAK.
        message_cases = [
            ("a leak in a message body", [body], ["Pkg"], None, [f"{body[:12]} message:3"]),
            ("a tree name in a message subject", [subject], ["Pkg"], None, [f"{subject[:12]} message:1"]),
            ("the own owner/name in a message", [own], ["Pkg", "org"], "org/Pkg", []),
            ("a clean message and clean content", [clean], ["Pkg"], None, []),
            ("an empty message", [no_message], ["Pkg"], None, []),
            ("a leak in the ASCII part of a message that is not UTF-8", [latin], ["Pkg"], None,
             [f"{latin[:12]} message:1"]),
            ("a leak string and a tree name on one message line", [both], ["Pkg"], None,
             [f"{both[:12]} message:1"] * 2),
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
        (pathlib.Path(tmp) / "profile.toml").write_text(
            f"leak = [\"LEAK\"]\norg = []\nrepository_roots = [{json.dumps(str(pathlib.Path(tmp) / 'roots'))}]\n")
        (pathlib.Path(tmp) / "commits").write_text(git("rev-list", "HEAD") + "\n")
        runs = [
            ("the tree only", None, 0, []),
            ("the tree and every commit", pathlib.Path(tmp) / "commits", 1,
             [f"  {added[:12]} a.txt:2: 'LEAK'", f"  {path_added[:12]} notes-Pkg.md:0: 'Pkg'",
              f"  {body[:12]} message:3: 'LEAK'"]),
        ]
        for label, commits, status, lines in runs:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                got = cmd_leaks(argparse.Namespace(profile=pathlib.Path(tmp) / "profile.toml", commits=commits), repo)
            ok = got == status and all(line in out.getvalue().splitlines() for line in lines)
            wrong += not ok
            print(f"{'ok ' if ok else 'BAD'}  leaks: {label} -> exit {got}")
        # The templates that `harness leaks` renders: TEMPLATES and each adapter's. The leak string is
        # the suffix of a rendered template's name, so each template it renders is one hit on line 0.
        (pathlib.Path(tmp) / "profile-templates.toml").write_text(
            f"leak = [\" (rendered with the dummy)\"]\norg = []\n"
            f"repository_roots = [{json.dumps(str(pathlib.Path(tmp) / 'roots'))}]\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_leaks(argparse.Namespace(profile=pathlib.Path(tmp) / "profile-templates.toml", commits=None), repo)
        rendered = {line.strip().rsplit(" (rendered with the dummy):0: ", 1)[0]
                    for line in out.getvalue().splitlines() if " (rendered with the dummy):0: " in line}
        adapters = {t for adapter in frontends.load() for t in adapter.TEMPLATES}
        ok = bool(adapters - set(TEMPLATES)) and rendered == set(TEMPLATES) | adapters
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  leaks: renders TEMPLATES and each adapter's TEMPLATES -> "
              f"{len(rendered)} templates, missing {sorted((set(TEMPLATES) | adapters) - rendered)}")
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
            ("a leak only in the message of an annotated tag on the commit", tagged,
             git("tag", "-l", "--format=%(contents)", "v1"), 0),
            ("a leak only in a git note on the commit", noted, git("notes", "show", noted), 0),
            ("the same leak in the commit's message", messaged, git("show", "-s", "--format=%B", messaged), 1),
        ]
        for label, sha, shown, expected in limits:
            (pathlib.Path(tmp) / "commits").write_text(sha + "\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = cmd_leaks(argparse.Namespace(profile=pathlib.Path(tmp) / "profile.toml",
                                                      commits=pathlib.Path(tmp) / "commits"), repo)
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
        subprocess.run(["git", "merge", "-q", "--no-ff", "side4"], cwd=repo, env=env, capture_output=True)
        (repo / "f.txt").write_bytes(b"main\nLEAK\n")
        git("add", "--", "f.txt")
        git("commit", "-q", "-m", "merge")
        resolved = git("rev-parse", "HEAD")
        # Paths that git quotes in a diff header: a non-ASCII character, and a `"`.
        cafe = commit("café.txt", b"LEAK\n")
        quote = commit('a"b.txt', b"LEAK\n")
        # (label, SHA, expected places); the leak string is LEAK, the tree name Pkg.
        place_cases = [
            ("an evil merge names each path once, the one that differs from the second parent only too", evil,
             [f"{evil[:12]} evil-Pkg.md:0", f"{evil[:12]} m-Pkg.md:0"]),
            ("a line that a merge's resolution adds, which neither parent has", resolved,
             [f"{resolved[:12]} f.txt:2"]),
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
            status = cmd_leaks(argparse.Namespace(profile=pathlib.Path(tmp) / "profile.toml",
                                                  commits=pathlib.Path(tmp) / "commits"), repo)
        summary = out.getvalue().splitlines()[-1]
        ok = own_repository(repo) == "org/Pkg" != own_repository() and status == 0 and summary.endswith(", 0 hits")
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  leaks --commits: the own owner/name of a repository whose origin is not "
              f"this checkout's -> exit {status}, {summary.strip()!r}")
    return len(cases) + 3 + len(message_cases) + len(runs) + 1 + len(limits) + len(place_cases) + 1, wrong


# The tools that `.githooks/pre-push` starts from the PATH in `prepush_case`, besides the stubs.
PREPUSH_TOOLS = ["bash", "sh", "git", "mktemp", "rm", "cat", "tail", "head", "grep", "awk"]


def prepush_case(path=None):
    """`.githooks/pre-push` on a fixture checkout whose `origin` is a GitHub URL, for a push to
    main, with stubs of gitleaks and of `bin/harness` and no python3.11, shellcheck or julia on the
    PATH: `harness leaks` runs in the hook's clone with that URL as its `origin`, not the path of
    the checkout. The tools are linked from `path`, this process's PATH by default, without a
    directory named `git-core`: git puts its exec path first in a hook's PATH, and a `git` started
    from a link to that copy looks for `git-upload-pack` beside the link. (number of cases, number
    wrong)"""
    search = os.pathsep.join(d for d in (os.environ.get("PATH", "") if path is None else path).split(os.pathsep)
                             if pathlib.PurePath(d).name != "git-core")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="leaks", GIT_AUTHOR_EMAIL="leaks@example.org",
               GIT_COMMITTER_NAME="leaks", GIT_COMMITTER_EMAIL="leaks@example.org")
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
            (tools / tool).symlink_to(shutil.which(tool, path=search))
        (tools / "python3").symlink_to(sys.executable)
        (tools / "gitleaks").write_text('#!/bin/sh\n[ "$1" = version ] && echo v8.24.0\n'
                                        '[ "$1" = stdin ] && cat >/dev/null\nexit 0\n')
        (tools / "gitleaks").chmod(0o755)
        (repo / "bin").mkdir(parents=True)
        (repo / "bin" / "harness").write_text(
            "import os, subprocess, sys\n"
            "if sys.argv[1] == 'leaks':\n"
            "    url = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, text=True).stdout\n"
            "    open(os.environ['ORIGIN_SEEN'], 'w').write(url.strip())\n"
            "print('0 cases, 0 wrong')\n")

        def git(*args):
            return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True,
                                  text=True).stdout.strip()

        git("init", "-q", "-b", "main")
        git("add", "--", "bin/harness")
        git("commit", "-q", "-m", "fixture")
        git("remote", "add", "origin", url)
        sha = git("rev-parse", "HEAD")
        try:
            p = subprocess.run([str(REPO / ".githooks" / "pre-push"), "origin", url],
                               input=f"refs/heads/main {sha} refs/heads/main {'0' * 40}\n", cwd=repo,
                               env={**env, "PATH": str(tools), "ORIGIN_SEEN": str(seen), "TMPDIR": str(tmp)},
                               capture_output=True, text=True, timeout=60)
            code, text = p.returncode, p.stdout + p.stderr
        except subprocess.TimeoutExpired:
            code, text = None, "TIMEOUT"
        got = seen.read_text() if seen.exists() else None
    ok = code == 0 and got == url
    print(f"{'ok ' if ok else 'BAD'}  pre-push: harness leaks runs in the clone with the checkout's origin URL "
          f"-> exit {code}, origin {got!r}, {(text.strip().splitlines() or ['no output'])[-1]!r}")
    return 1, int(not ok)


def prepush_branch_cases():
    """`.githooks/pre-push` for a push of a topic branch, on a fixture checkout whose
    `refs/remotes/origin/main` holds a commit that adds the leak string and one that removes it.
    The stub of `bin/harness leaks` searches the tree at HEAD and each commit of `--commits` for
    the string. A clean branch passes, so the commits of origin/main are not sent; a branch whose
    new commit adds the string and whose next commit removes it is refused; a branch on the
    commit with the string is refused for its tree. No case runs the suite. (number of cases,
    number wrong)"""
    search = os.pathsep.join(d for d in os.environ.get("PATH", "").split(os.pathsep)
                             if pathlib.PurePath(d).name != "git-core")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="leaks", GIT_AUTHOR_EMAIL="leaks@example.org",
               GIT_COMMITTER_NAME="leaks", GIT_COMMITTER_EMAIL="leaks@example.org")
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
            (tools / tool).symlink_to(shutil.which(tool, path=search))
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
            "sys.exit(int(hit))\n")

        def git(*args):
            return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True,
                                  text=True).stdout.strip()

        def commit(name, content=None):
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
        cases = [
            ("a clean new branch on origin/main passes, and the commits of origin/main are not sent",
             clean, 0, "the leak check of the branches passed"),
            ("a branch whose new commit adds the leak string, removed by the next commit, is refused",
             removed, 1, "found a leak"),
            ("a branch whose tree holds the leak string of an earlier commit is refused",
             on_leak, 1, "found a leak"),
        ]
        wrong = 0
        for label, sha, expected, marker in cases:
            try:
                p = subprocess.run([str(REPO / ".githooks" / "pre-push"), "origin", url],
                                   input=f"refs/heads/topic {sha} refs/heads/topic {'0' * 40}\n", cwd=repo,
                                   env={**env, "PATH": str(tools), "TMPDIR": str(tmp)},
                                   capture_output=True, text=True, timeout=60)
                code, text = p.returncode, p.stdout + p.stderr
            except subprocess.TimeoutExpired:
                code, text = None, "TIMEOUT"
            last = (text.strip().splitlines() or ["no output"])[-1]
            ok = code == expected and marker in last and "the suite ran" not in text
            wrong += not ok
            print(f"{'ok ' if ok else 'BAD'}  pre-push: {label} -> exit {code}, {last!r}")
    return len(cases), wrong


def selftest():
    """The render's cases, the tree-name cases, the cases of `--commits`, and the `origin` case and
    the branch cases of the pre-push hook: (number of cases, number wrong)."""
    wrong = 0
    for template, profile, expected in CASES:
        try:
            got = render_text(template, profile) if isinstance(template, str) else render_data(template, profile)
        except (KeyError, TypeError, ValueError):
            got = None
        wrong += got != expected
        print(f"{'ok ' if got == expected else 'BAD'}  {template!r} -> {got!r}")
    pattern = name_pattern(["Pkg", "my-paper", "org"])
    for line, expected in NAME_CASES:
        got = name_hits(line, pattern, "org/Repo")
        wrong += got != expected
        print(f"{'ok ' if got == expected else 'BAD'}  {line!r} -> {got!r}")
    n, w = commit_cases()
    n2, w2 = prepush_case()
    # As inside a git hook: git's exec path first on the PATH.
    exec_path = subprocess.run(["git", "--exec-path"], capture_output=True, text=True, check=True).stdout.strip()
    n3, w3 = prepush_case(exec_path + os.pathsep + os.environ.get("PATH", ""))
    n4, w4 = prepush_branch_cases()
    return len(CASES) + len(NAME_CASES) + n + n2 + n3 + n4, wrong + w + w2 + w3 + w4


def register(sub):
    r = sub.add_parser("render", help="print a template rendered with the profile")
    r.add_argument("template")
    r.set_defaults(run=cmd_render)
    g = sub.add_parser("get", help="print a profile value, one line per item of a list")
    g.add_argument("key")
    g.set_defaults(run=cmd_get)
    l = sub.add_parser("leaks", help="search the repository and its renders for the leak list")
    l.add_argument("--commits", metavar="FILE",
                   help="also search the paths and lines that each commit of FILE adds, and its message, "
                        "one SHA per line")
    l.set_defaults(run=cmd_leaks)
