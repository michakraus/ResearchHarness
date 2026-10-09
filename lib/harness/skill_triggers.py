"""The triggering test of the skills: does each skill load on the queries that should load it,
and stay unloaded on its near misses?

    harness skill-triggers [--skill <name> …] [--apply --model <alias>]

The queries are `tests/skill-triggers/<skill>.toml`, one file for each skill of `skills/`. A skill
that the model can invoke has `load`, 10 queries that should load it, and `near`, 5 entries of a
query that should not and the skill it belongs to (a skill name, or `none`). A skill with
`disable-model-invocation: true` has one `near` entry and no `load`. `--skill`, which can repeat,
limits the dry run and `--apply` to the query files of the skills it names.

The dry run prints the counts per skill and the number of sessions an `--apply` starts. `--apply`
runs each query as one `claude -p` session of 3 turns on the model it names, in the research root,
without `Edit`, `Write`, `NotebookEdit`, `Agent` and `Bash`, and reads its `stream-json` output: a
query loads skill s when the first `Skill` call in the first 3 top-level assistant messages names
s. A query whose verdict fails its expectation runs twice more, and the majority of the three
counts. A session that errors or times out is UNKNOWN and runs once more.

A skill passes with at least 8 of its 10 `load` queries loading it and at most 1 of its 5 `near`
queries loading it; a skill with model invocation off passes when its `near` query does not load
it. A skill whose verdict turns on an UNKNOWN query is UNKNOWN. `--apply` prints one row per
skill and the tokens and cost of the sessions, writes the table and every query's verdict to
$RESEARCH_ROOT/.scratch/skill-triggers/<date>-<model>.md, and exits 0 when every skill passes
and no session gave UNKNOWN twice, else 1; the row's unknown column counts those queries. Every session costs tokens, at the user's expense.
"""

import datetime
import json
import os
import pathlib
import subprocess
import tempfile
import tomllib

from . import REPO, HarnessError, changing
from .frontmatter import parse_file
from .githooks import research_root
from .sources import curated_skills

SKILLS = REPO / "skills"
QUERIES = REPO / "tests" / "skill-triggers"
FIXTURES = QUERIES / "fixtures"

LOAD, NEAR = 10, 5          # the counts of a skill that the model can invoke
LOAD_MIN, NEAR_MAX = 8, 1   # its pass rule
MESSAGES = 3                # the assistant messages that a Skill call counts in, and the session's --max-turns
TIMEOUT = 120               # seconds per session
UNKNOWN = "UNKNOWN"         # the verdict of a session that errors or times out


def skill_names(directory=SKILLS):
    """{name: whether the model can invoke it}, for each curated skill below `directory`."""
    return {name: parse_file(directory / name / "SKILL.md").meta.get("disable-model-invocation") is not True
            for name in curated_skills(directory)}


def read_queries(directory=QUERIES, skills_dir=SKILLS):
    """{skill: (its load queries, its near entries as (query, the skill it belongs to))}.

    Exits 2, naming the file, on a file for a skill not in `skills_dir`, a skill with no file,
    another count, a duplicate query in one file, an empty query, a query that starts with `/`,
    a `near` entry that names neither a skill nor `none`, or the file's own skill, and a file
    that cannot be read or is not TOML."""
    skills = skill_names(skills_dir)
    files = {path.stem: path for path in sorted(directory.glob("*.toml"))}
    for name, path in files.items():
        if name not in skills:
            raise HarnessError(f"{path}: no skill {name} in {skills_dir}")
    for name in skills:
        if name not in files:
            raise HarnessError(f"skill {name} has no query file {directory / (name + '.toml')}")
    queries = {}
    for name, path in files.items():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
            raise HarnessError(f"{path}: {e}") from None
        except OSError as e:
            raise HarnessError(f"cannot read {path}: {e.strerror}") from None
        load, near = data.get("load", []), data.get("near", [])
        if not isinstance(load, list) or not isinstance(near, list) or not all(isinstance(e, dict) for e in near):
            raise HarnessError(f"{path}: `load` is not a list, or `near` is not a list of tables")
        near = [(e.get("query"), e.get("skill")) for e in near]
        want = (LOAD, NEAR) if skills[name] else (0, 1)
        if (len(load), len(near)) != want:
            raise HarnessError(f"{path}: {len(load)} load and {len(near)} near queries, not {want[0]} and {want[1]}")
        seen = set()
        for query in load + [q for q, _ in near]:
            if not isinstance(query, str) or not query.strip():
                raise HarnessError(f"{path}: an empty query, or one that is not a string")
            if query.lstrip().startswith("/"):
                raise HarnessError(f"{path}: the query {query!r} starts with /")
            if query.strip() in seen:
                raise HarnessError(f"{path}: the query {query!r} twice")
            seen.add(query.strip())
        for query, skill in near:
            if not isinstance(skill, str) or (skill != "none" and skill not in skills):
                raise HarnessError(f"{path}: the near query {query!r} names {skill!r}, neither a skill nor none")
            if skill == name:
                raise HarnessError(f"{path}: the near query {query!r} names the file's own skill")
        queries[name] = (load, near)
    return queries


def verdict(stream):
    """(the skill that the first MESSAGES assistant messages of a `stream-json` output load, None,
    or UNKNOWN; the `result` event, or None).

    An assistant message is every top-level assistant event with one `message.id`, because Claude
    Code prints one event per content block; an event of a subagent, with a `parent_tool_use_id`,
    belongs to none. The skill is that of the first `Skill` call in the first MESSAGES messages, in
    the order of the stream. A stream with a line that is not JSON, with no `result` event, with an
    error result, or with no assistant message is UNKNOWN; a result of `error_max_turns` is the
    normal end of a session that called a tool."""
    try:
        events = [json.loads(line) for line in stream.splitlines() if line.strip()]
    except json.JSONDecodeError:
        return UNKNOWN, None
    if not all(isinstance(e, dict) for e in events):
        return UNKNOWN, None
    results = [e for e in events if e.get("type") == "result"]
    result = results[-1] if results else None
    if result is None or not (result.get("subtype") == "error_max_turns"
                              or (result.get("subtype") == "success" and not result.get("is_error"))):
        return UNKNOWN, result
    messages = [e.get("message") for e in events
                if e.get("type") == "assistant" and e.get("parent_tool_use_id") is None]
    messages = [m if isinstance(m, dict) else {} for m in messages]
    if not messages:
        return UNKNOWN, result
    # The message of each event: its id, or the event's own index where it has no string id.
    ids = [m.get("id") if isinstance(m.get("id"), str) else ("event", i) for i, m in enumerate(messages)]
    first = list(dict.fromkeys(ids))[:MESSAGES]
    for message in [m for m, key in zip(messages, ids) if key in first]:
        content = message.get("content")
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill":
                skill = block.get("input").get("skill") if isinstance(block.get("input"), dict) else None
                return (skill if isinstance(skill, str) else None), result
    return None, result


def decide(run, met):
    """(True when the query meets its expectation, False when not, or UNKNOWN; every verdict).

    `run()` gives one session's verdict, and `met(verdict)` whether it meets the expectation. A
    session that gives UNKNOWN runs once more. A verdict that fails runs twice more, and the
    majority of the three counts; with no majority, the outcome is UNKNOWN."""
    verdicts = []

    def once():
        for _ in range(2):
            verdicts.append(run())
            if verdicts[-1] != UNKNOWN:
                break
        return verdicts[-1]

    first = once()
    if first == UNKNOWN or met(first):
        return (UNKNOWN if first == UNKNOWN else True), verdicts
    votes = [first, once(), once()]
    good = sum(v != UNKNOWN and met(v) for v in votes)
    bad = sum(v != UNKNOWN and not met(v) for v in votes)
    return (True if good >= 2 else False if bad >= 2 else UNKNOWN), verdicts


def second_unknown(verdicts):
    """Whether a session of `decide` gave UNKNOWN on its run and on its one re-run: two UNKNOWN
    in a row, since a session's first UNKNOWN is always followed by its re-run."""
    return any(a == b == UNKNOWN for a, b in zip(verdicts, verdicts[1:]))


def skill_verdict(fires, loads, load_unknown, false_loads, near_unknown):
    """PASS, FAIL, or UNKNOWN when the UNKNOWN queries decide between the two."""
    need, allowed = (LOAD_MIN, NEAR_MAX) if fires else (0, 0)
    if loads >= need and false_loads + near_unknown <= allowed:
        return "PASS"
    if loads + load_unknown < need or false_loads > allowed:
        return "FAIL"
    return UNKNOWN


def session(query, model, root, claude, timeout):
    """One `claude -p` session on `query`: (its verdict, its `result` event or None). The query
    goes in on stdin, so a query that starts with `-` is no flag; `--output-format stream-json`
    under `-p` needs `--verbose`. The session has MESSAGES turns, and lacks `Edit`, `Write`,
    `NotebookEdit`, `Agent` and `Bash`, so it runs nothing in the research root."""
    command = [claude, "-p", "--verbose", "--output-format", "stream-json", "--max-turns", str(MESSAGES),
               "--disallowedTools", "Edit", "Write", "NotebookEdit", "Agent", "Bash", "--model", model]
    try:
        p = subprocess.run(command, input=query, cwd=root, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return UNKNOWN, None
    except OSError as e:
        raise HarnessError(f"cannot run {claude}: {e.strerror}") from None
    return verdict(p.stdout)


def cell(text):
    return str(text).replace("|", "\\|")


def apply(queries, skills, model, root, claude="claude", timeout=TIMEOUT):
    """Run every query, print the table and the totals, write the report; the exit status."""
    if not pathlib.Path(root).is_dir():
        raise HarnessError(f"the research root {root} is not a directory")
    totals = {"sessions": 0, "tokens": 0, "cost": 0.0}

    def run(query):
        loaded, result = session(query, model, root, claude, timeout)
        usage = (result or {}).get("usage") or {}
        totals["sessions"] += 1
        totals["tokens"] += sum(usage.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens",
                                                              "cache_read_input_tokens", "output_tokens"))
        totals["cost"] += (result or {}).get("total_cost_usd") or 0
        return loaded

    rows, records = [], []
    for name, (load, near) in queries.items():
        outcomes = {"load": [], "near": []}
        others = set()
        for kind, entries in (("load", [(q, name) for q in load]), ("near", near)):
            met = (lambda v: v == name) if kind == "load" else (lambda v: v != name)
            for query, belongs in entries:
                outcome, verdicts = decide(lambda: run(query), met)
                outcomes[kind].append(outcome)
                others |= {v for v in verdicts if v not in (None, UNKNOWN, name)}
                records.append((name, kind, query, belongs, verdicts, outcome))
                print(f"  {name:<20} {kind:<4} {'met' if outcome is True else 'FAILED' if outcome is False else UNKNOWN:<7}"
                      f" {query!r} -> {verdicts}", flush=True)
        loads, false_loads = outcomes["load"].count(True), outcomes["near"].count(False)
        unknown = [outcomes[k].count(UNKNOWN) for k in ("load", "near")]
        # The unknown column counts the queries with a second UNKNOWN, also where a majority of
        # the other runs decides the query.
        twice = sum(second_unknown(r[4]) for r in records if r[0] == name)
        rows.append((name, f"{loads}/{len(load)}", f"{false_loads}/{len(near)}", twice,
                     skill_verdict(skills[name], loads, unknown[0], false_loads, unknown[1]), ", ".join(sorted(others))))

    header = ("skill", "loads", "false loads", "unknown", "verdict", "loaded instead")
    print()
    for row in [header] + rows:
        print(f"{row[0]:<22} {row[1]:<7} {row[2]:<12} {row[3]!s:<8} {row[4]:<8} {row[5]}")
    summary = f"{totals['sessions']} sessions, {totals['tokens']} tokens, ${totals['cost']:.4f}"
    print("\n" + summary)

    try:
        version = subprocess.run([claude, "--version"], capture_output=True, text=True,
                                 stdin=subprocess.DEVNULL, timeout=30).stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        version = "unknown"
    today = datetime.date.today().isoformat()
    report = pathlib.Path(root) / ".scratch" / "skill-triggers" / f"{today}-{model.replace(os.sep, '-')}.md"
    lines = [f"# Skill triggers, {today}, model {model}", "", f"Claude Code {version}; {summary}.", "",
             "| " + " | ".join(header) + " |", "|" + ":--|" * len(header)]
    lines += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    lines += ["", "## Queries", "", "| skill | kind | query | belongs to | verdicts | outcome |", "|" + ":--|" * 6]
    lines += [f"| {name} | {kind} | {cell(query)} | {belongs} | {', '.join(str(v) for v in verdicts)} | "
              f"{'met' if outcome is True else 'failed' if outcome is False else UNKNOWN} |"
              for name, kind, query, belongs, verdicts, outcome in records]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n")
    print(f"report:  {report}")
    every = all(row[4] == "PASS" for row in rows) and not any(second_unknown(r[4]) for r in records)
    return 0 if every else 1


def cmd_skill_triggers(args):
    if args.apply and not args.model:
        raise HarnessError("--apply needs --model <alias>; there is no default model")
    queries, skills = read_queries(), skill_names()
    if args.skill:
        for name in args.skill:
            if name not in queries:
                raise HarnessError(f"--skill {name}: no query file {QUERIES / (name + '.toml')}")
        queries = {name: entries for name, entries in queries.items() if name in args.skill}
    if args.apply:
        return apply(queries, skills, args.model, research_root())
    print(f"{'skill':<22} {'load':>4} {'near':>4}  model invocation")
    for name, (load, near) in queries.items():
        print(f"{name:<22} {len(load):>4} {len(near):>4}  {'on' if skills[name] else 'off'}")
    sessions = sum(len(load) + len(near) for load, near in queries.values())
    print(f"\n--apply starts {sessions} session{'' if sessions == 1 else 's'}, one per query, and more: a query that fails its"
          f" expectation runs twice more, and a session that gives UNKNOWN once more.")
    return 1


# The fake `claude` of the selftest: it logs its arguments, working directory and query, and prints
# the fixtures that plan.json names for the query, one per call, the last one again after that.
FAKE_CLAUDE = """
import json, os, pathlib, sys, time
here = pathlib.Path(__file__).parent
if sys.argv[1:] == ["--version"]:
    print("9.9.9 (Claude Code)")
    sys.exit(0)
query = sys.stdin.read()
with open(here / "calls.jsonl", "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "query": query}) + "\\n")
calls = [json.loads(line)["query"] for line in open(here / "calls.jsonl")]
plan = json.loads((here / "plan.json").read_text())
names = plan.get(query, plan["default"])
name = names[min(calls.count(query) - 1, len(names) - 1)]
if name == "hang":
    time.sleep(10)
sys.stdout.write((pathlib.Path(plan["fixtures"]) / (name + ".jsonl")).read_text())
sys.exit(1 if name != "no-skill" else 0)
"""

SKILL_MD = '---\nname: {name}\ndescription: "A fixture skill."\n{extra}---\n\nBody.\n'


def selftest():
    """The parser, the verdict, the majority, the pass rule and the verb: (cases, wrong)."""
    import contextlib
    import io
    import sys

    total = wrong = 0

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  skill-triggers: {label}")

    def refused(call):
        try:
            call()
        except HarnessError as e:
            return str(e)
        except Exception as e:  # a traceback, which exits 1, not 2
            return f"TRACEBACK {type(e).__name__}: {e}"
        return None

    # The parser on the repository's own tree: 12 skills, of which 10 can fire.
    try:
        queries, skills = read_queries(), skill_names()
        sizes = sorted((len(load), len(near)) for load, near in queries.values())
        ok = len(queries) == 12 and sum(skills.values()) == 10 and sizes == [(0, 1)] * 2 + [(10, 5)] * 10
        check(ok, f"the repository's query files: {len(queries)} skills, sizes {sorted(set(sizes))}")
    except HarnessError as e:
        check(False, f"the repository's query files: {e}")

    # The parser on a fixture tree: skill `a` can fire, skill `b` cannot; then each refusal alone.
    load = [f"query number {i}" for i in range(LOAD)]
    near = [(f"near miss {i}", "b" if i == 0 else "none") for i in range(NEAR)]

    def toml(load, near):
        lines = ["load = ["] + [f"    {json.dumps(q)}," for q in load] + ["]", "near = ["]
        lines += [f"    {{ query = {json.dumps(q)}, skill = {json.dumps(s)} }}," for q, s in near] + ["]"]
        return "\n".join(lines) + "\n"

    valid = {"a.toml": toml(load, near), "b.toml": toml([], [("the purpose of b", "none")])}
    refusals = [
        ("a file for a skill not in skills/", {"c.toml": toml([], [("x", "none")])}),
        ("a skill with no file", {"b.toml": None}),
        ("9 load queries", {"a.toml": toml(load[:9], near)}),
        ("11 load queries", {"a.toml": toml(load + ["one more"], near)}),
        ("4 near queries", {"a.toml": toml(load, near[:4])}),
        ("a load query for a skill with model invocation off", {"b.toml": toml(["x"], [("y", "none")])}),
        ("2 near queries for a skill with model invocation off",
         {"b.toml": toml([], [("x", "none"), ("y", "none")])}),
        ("a duplicate load query", {"a.toml": toml(load[:9] + [load[0]], near)}),
        ("a near query that repeats a load query", {"a.toml": toml(load, [(load[3], "b")] + near[1:])}),
        ("an empty query", {"a.toml": toml(load[:9] + ["   "], near)}),
        ("a near entry with no query", {"a.toml": toml(load, near[:4]).replace(
            "near = [", 'near = [\n    { skill = "b" },')}),
        ("a query that starts with /", {"a.toml": toml(load[:9] + ["/build-part next"], near)}),
        ("a near entry that names an unknown skill", {"a.toml": toml(load, near[:4] + [("z", "c")])}),
        ("a near entry with no skill", {"a.toml": toml(load, near[:4]).replace(
            "near = [", 'near = [\n    { query = "z" },')}),
        ("a file that is not TOML", {"a.toml": "load = [\n"}),
        ("a near entry whose skill is a list", {"a.toml": toml(load, near[:4]).replace(
            "near = [", 'near = [\n    { query = "z", skill = ["b"] },')}),
        ("a near entry whose skill is a table", {"a.toml": toml(load, near[:4]).replace(
            "near = [", 'near = [\n    { query = "z", skill = { b = 1 } },')}),
        ("a near entry that names the file's own skill", {"a.toml": toml(load, near[:4] + [("z", "a")])}),
        ("a query file that cannot be read", {"a.toml": "a directory"}),
    ]
    with tempfile.TemporaryDirectory(prefix="harness-skill-triggers-") as tmp:
        tmp = pathlib.Path(tmp)
        for name, extra in (("a", ""), ("b", "disable-model-invocation: true\n")):
            (tmp / "skills" / name).mkdir(parents=True)
            (tmp / "skills" / name / "SKILL.md").write_text(SKILL_MD.format(name=name, extra=extra))

        def tree(change):
            qdir = tmp / "queries"
            for path in qdir.glob("*.toml") if qdir.is_dir() else []:
                path.rmdir() if path.is_dir() else path.unlink()
            qdir.mkdir(exist_ok=True)
            for file, text in (valid | change).items():
                if text == "a directory":
                    (qdir / file).mkdir()
                elif text is not None:
                    (qdir / file).write_text(text)
            return lambda: read_queries(qdir, tmp / "skills")

        got = refused(tree({}))
        check(got is None, f"a valid fixture tree parses: {got!r}")
        for label, change in refusals:
            got = refused(tree(change))
            check(got is not None and not got.startswith("TRACEBACK"), f"refused, {label}: {got!r}")

    # The verdict on the streams. The first five and the two `read-` ones are recorded from Claude
    # Code sessions, with their private content stripped: `read-then-skill` calls Read, then Skill
    # in its second message, then Bash in its third, whose result is an error; `read-read-read`
    # calls Read in each of its 3 messages. The others are written by hand for the shapes that a session does not
    # give on demand: an error, a Skill call after a tool in one message, two Skill calls.
    for fixture, expected in [("skill-first", "julia-performance"), ("skill-then-tool", "build-reviewed"),
                              ("no-skill", None), ("thinking-text", None), ("two-tools", None),
                              ("read-then-skill", "build-part"), ("read-read-read", None),
                              ("skill-after-tool", "julia-performance"), ("skill-second-message", "build-part"),
                              ("two-skills", "julia-package-audit"), ("error", UNKNOWN),
                              ("no-result", UNKNOWN), ("api-error", UNKNOWN)]:
        got = verdict((FIXTURES / f"{fixture}.jsonl").read_text())[0]
        check(got == expected, f"verdict of {fixture}.jsonl: {got!r}, expected {expected!r}")
    got = verdict("not json\n" + (FIXTURES / "skill-first.jsonl").read_text())[0]
    check(got == UNKNOWN, f"verdict of a stream with a line that is not JSON: {got!r}")
    end = json.dumps({"type": "result", "subtype": "success", "is_error": False})

    def tool(name, skill=None):
        """A tool_use block: a call of `name`, with `skill` as its input when given."""
        return {"type": "tool_use", "name": name, "input": {"skill": skill} if skill else {"file_path": "f"}}

    def message(n, *blocks):
        return {"id": f"m{n}", "content": list(blocks)}

    for label, lines, expected in [
        ("a JSON line that is not an object", ["[1, 2]", end], UNKNOWN),
        ("a message whose content is a string", [{"id": "m", "content": "text"}, end], None),
        ("a Skill call whose skill is not a string",
         [{"id": "m", "content": [{"type": "tool_use", "name": "Skill", "input": {"skill": ["a"]}}]}, end], None),
        ("a Skill call in message 3", [message(1, tool("Read")), message(2, tool("Read")),
                                       message(3, tool("Skill", "a")), end], "a"),
        ("a Skill call in message 4", [message(1, tool("Read")), message(2, tool("Read")), message(3, tool("Read")),
                                       message(4, tool("Skill", "a")), end], None),
        ("message 2 in two events, its Skill call in the second",
         [message(1, tool("Read")), message(2, tool("Read")), message(2, tool("Skill", "a")),
          message(3, tool("Skill", "b")), end], "a"),
        ("a Skill call in message 2 and another in message 3",
         [message(1, tool("Read")), message(2, tool("Skill", "a")), message(3, tool("Skill", "b")), end], "a"),
        ("a subagent's Skill call before the session's own",
         [message(1, tool("Agent")), (message(9, tool("Skill", "a")), "toolu_1"), message(2, tool("Skill", "b")), end],
         "b"),
        ("a subagent's Skill call alone, in the first 3 messages",
         [message(1, tool("Agent")), (message(9, tool("Skill", "a")), "toolu_1"), message(2, tool("Read")), end],
         None),
        ("a session that ends with success after 2 messages, text only",
         [message(1, tool("Read")), message(2, {"type": "text", "text": "done"}), end], None),
    ]:
        stream = "\n".join(line if isinstance(line, str) else
                           json.dumps({"type": "assistant", "message": line[0], "parent_tool_use_id": line[1]})
                           if isinstance(line, tuple) else
                           json.dumps({"type": "assistant", "message": line, "parent_tool_use_id": None})
                           for line in lines)
        try:
            got = verdict(stream)[0]
        except Exception as e:  # a traceback would end the whole --apply run
            got = f"{type(e).__name__}: {e}"
        check(got == expected, f"verdict of {label}: {got!r}, expected {expected!r}")

    # The majority: the verdicts a query's runs give, in order, and the outcome expected.
    met = lambda v: v == "s"  # noqa: E731
    # The third value: whether a session gave UNKNOWN twice in a row, which the row reports.
    for runs, expected, twice in [
            (["s"], True, False), (["x", "s", "s"], True, False), (["x", "s", "x"], False, False),
            ([None, None, "s"], False, False), ([UNKNOWN, "s"], True, False), ([UNKNOWN, UNKNOWN], UNKNOWN, True),
            (["x", UNKNOWN, UNKNOWN, "s"], UNKNOWN, True), (["x", UNKNOWN, "x", "s"], False, False),
            (["x", UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN], UNKNOWN, True), (["x", UNKNOWN, UNKNOWN, "x"], False, True)]:
        given = iter(runs)
        outcome, verdicts = decide(lambda: next(given), met)
        check(outcome == expected and verdicts == runs and second_unknown(verdicts) == twice,
              f"majority of {runs}: {outcome!r} after {verdicts}, a second UNKNOWN {second_unknown(verdicts)};"
              f" expected {expected!r}, {twice}")

    # The pass rule at its bounds: (fires, loads, load UNKNOWN, false loads, near UNKNOWN).
    for counts, expected in [((True, 8, 0, 1, 0), "PASS"), ((True, 7, 0, 0, 0), "FAIL"),
                             ((True, 10, 0, 2, 0), "FAIL"), ((True, 10, 0, 0, 0), "PASS"),
                             ((False, 0, 0, 0, 0), "PASS"), ((False, 0, 0, 1, 0), "FAIL"),
                             ((True, 7, 1, 0, 0), UNKNOWN), ((True, 8, 0, 1, 1), UNKNOWN),
                             ((True, 8, 2, 0, 0), "PASS"), ((True, 6, 1, 0, 0), "FAIL"),
                             ((True, 7, 2, 2, 0), "FAIL"), ((False, 0, 0, 0, 1), UNKNOWN)]:
        got = skill_verdict(*counts)
        check(got == expected, f"pass rule on {counts}: {got!r}, expected {expected!r}")

    # The verb's exits: the dry run exits 1 and counts the sessions; --apply without --model exits 2.
    harness = [sys.executable, str(REPO / "bin" / "harness"), "skill-triggers"]
    p = subprocess.run(harness, capture_output=True, text=True)
    check(p.returncode == 1 and "152 sessions" in p.stdout and "Traceback" not in p.stderr,
          f"the dry run exits {p.returncode}: {p.stdout.strip().splitlines()[-1:]!r}")
    p = subprocess.run(harness + ["--apply"], capture_output=True, text=True)
    check(p.returncode == 2 and len(p.stderr.strip().splitlines()) == 1 and "--model" in p.stderr,
          f"--apply without --model exits {p.returncode}: {p.stderr.strip()!r}")
    # --skill, which can repeat, limits the dry run to its query files: 15 sessions each, 1 for wait-what.
    for names, sessions in [(["julia-performance", "build-part"], "30 sessions,"), (["wait-what"], "1 session,")]:
        p = subprocess.run(harness + [a for n in names for a in ("--skill", n)], capture_output=True, text=True)
        rows = [line.split()[0] for line in p.stdout.splitlines()[1:] if line.strip() and not line.startswith("--")]
        check(p.returncode == 1 and f"starts {sessions}" in p.stdout and sorted(rows) == sorted(names),
              f"the dry run with --skill {' --skill '.join(names)} exits {p.returncode}, rows {rows}:"
              f" {p.stdout.strip().splitlines()[-1:]!r}")
    for argv in (["--skill", "no-such-skill"], ["--skill", "build-part", "--skill", "no-such-skill"],
                 ["--apply", "--model", "fixture-model", "--skill", "no-such-skill"]):
        p = subprocess.run(harness + argv, capture_output=True, text=True)
        check(p.returncode == 2 and len(p.stderr.strip().splitlines()) == 1 and "no-such-skill" in p.stderr,
              f"{' '.join(argv)} exits {p.returncode}: {p.stderr.strip()!r}")

    # --apply on a fake `claude`, which prints the streams: skill `julia-performance` can fire,
    # `wait-what` cannot.
    def scenario(plan, queries, timeout=TIMEOUT):
        with tempfile.TemporaryDirectory(prefix="harness-skill-triggers-") as tmp:
            tmp = pathlib.Path(tmp)
            (tmp / "bin").mkdir()
            (tmp / "root").mkdir()
            claude = tmp / "bin" / "claude"
            claude.write_text(f"#!{sys.executable}\n" + FAKE_CLAUDE)
            claude.chmod(0o755)
            (tmp / "bin" / "plan.json").write_text(json.dumps(plan | {"fixtures": str(FIXTURES)}))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = apply(queries, {"julia-performance": True, "wait-what": False}, "fixture-model",
                               tmp / "root", claude=str(claude), timeout=timeout)
            calls = [json.loads(line) for line in (tmp / "bin" / "calls.jsonl").read_text().splitlines()]
            written = sorted(str(p.relative_to(tmp / "root")) for p in (tmp / "root").rglob("*") if p.is_file())
            report = (tmp / "root" / written[0]).read_text() if len(written) == 1 else ""
            return status, out.getvalue(), calls, written, report, (tmp / "root").resolve()

    load = [f"load query {i}" for i in range(LOAD)]
    near = [(f"near query {i}", "none") for i in range(NEAR)]
    queries = {"julia-performance": (load, near), "wait-what": ([], [("the purpose", "none")])}

    status, out, calls, written, report, root = scenario(
        {"default": ["no-skill"], **{q: ["skill-first"] for q in load}}, queries)
    argv = ["-p", "--verbose", "--output-format", "stream-json", "--max-turns", "3",
            "--disallowedTools", "Edit", "Write", "NotebookEdit", "Agent", "Bash", "--model", "fixture-model"]
    check(len(calls) == 16 and all(c["argv"] == argv and pathlib.Path(c["cwd"]).resolve() == root for c in calls)
          and sorted(c["query"] for c in calls) == sorted(load + [q for q, _ in near] + ["the purpose"]),
          f"--apply starts one session per query, with {argv} in the research root: {len(calls)} sessions")
    today = datetime.date.today().isoformat()
    check(written == [f".scratch/skill-triggers/{today}-fixture-model.md"],
          f"--apply writes only the report below .scratch/skill-triggers: {written}")
    # 10 recorded loads of 38939 tokens and $0.1059428, 6 recorded misses of 38862 and $0.1052268.
    check(status == 0 and "16 sessions, 622562 tokens, $1.6908" in out,
          f"every skill passes: exit {status}, the totals {[l for l in out.splitlines() if 'tokens' in l]!r}")
    check(all(q in report for q in load) and "| julia-performance | 10/10 | 0/5 | 0 | PASS |" in report
          and "| wait-what | 0/0 | 0/1 | 0 | PASS |" in report,
          "the report holds the table and every query")

    plan = {"default": ["no-skill"],
            **{q: ["skill-first"] for q in load[:7]},
            load[7]: ["no-skill", "skill-first", "skill-first"],    # a majority loads it
            load[8]: ["no-skill"],                                 # a miss
            load[9]: ["hang", "error"],                            # UNKNOWN twice
            near[0][0]: ["skill-first", "no-skill", "no-skill"],   # a majority does not load it
            near[1][0]: ["skill-first"],                           # a false load
            near[2][0]: ["error", "no-skill"],                     # UNKNOWN, then not loaded
            "the purpose": ["two-skills"]}                         # another skill loads
    status, out, calls, written, report, root = scenario(plan, queries, timeout=2)
    check(status == 1 and "| julia-performance | 8/10 | 1/5 | 1 | PASS |" in report
          and "| wait-what | 0/0 | 0/1 | 0 | PASS | julia-package-audit |" in report,
          f"an UNKNOWN query exits 1 although every skill passes: exit {status}, {len(calls)} sessions")
    check(len(calls) == 26, f"the re-runs: 16 queries and 10 more sessions, {len(calls)} in all")

    # A second UNKNOWN in the re-runs of a miss: the outcome is the miss, the row reports it, exit 1.
    status, out, calls, written, report, root = scenario(
        {"default": ["no-skill"], **{q: ["skill-first"] for q in load[1:]},
         load[0]: ["no-skill", "error", "error", "no-skill"]}, queries)
    check(status == 1 and "| julia-performance | 9/10 | 0/5 | 1 | PASS |" in report and len(calls) == 19,
          f"a second UNKNOWN inside a majority exits 1: exit {status}, {len(calls)} sessions")

    status, out, calls, written, report, root = scenario(
        {"default": ["skill-first"], **{q: ["no-skill"] for q in load[:3]}}, queries)
    check(status == 1 and "| julia-performance | 7/10 | 5/5 | 0 | FAIL |" in report,
          f"a failing skill exits 1: exit {status}")

    # The verb's --apply with --skill, on the fake `claude` in PATH and a fixture research root:
    # one session, the near query of wait-what.
    with tempfile.TemporaryDirectory(prefix="harness-skill-triggers-") as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "bin").mkdir()
        (tmp / "root").mkdir()
        (tmp / "bin" / "claude").write_text(f"#!{sys.executable}\n" + FAKE_CLAUDE)
        (tmp / "bin" / "claude").chmod(0o755)
        (tmp / "bin" / "plan.json").write_text(json.dumps({"default": ["no-skill"], "fixtures": str(FIXTURES)}))
        env = os.environ | {"PATH": f"{tmp / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
                            "RESEARCH_ROOT": str(tmp / "root")}
        p = subprocess.run(harness + ["--apply", "--model", "fixture-model", "--skill", "wait-what"],
                           capture_output=True, text=True, env=env)
        calls = [json.loads(line) for line in (tmp / "bin" / "calls.jsonl").read_text().splitlines()] \
            if (tmp / "bin" / "calls.jsonl").is_file() else []
        reports = list((tmp / "root").rglob("*.md"))
        report = reports[0].read_text() if len(reports) == 1 else ""
        near = read_queries()["wait-what"][1]
        check(p.returncode == 0 and [c["query"] for c in calls] == [near[0][0]]
              and "| wait-what | 0/0 | 0/1 | 0 | PASS |" in report and report.count(" | PASS |") == 1,
              f"--apply --skill wait-what runs only its query and reports only its row: exit {p.returncode},"
              f" {len(calls)} sessions, {p.stderr.strip()[-200:]!r}")
    return total, wrong


def register(sub):
    p = changing(sub.add_parser("skill-triggers", help="test whether each skill loads on its queries, with claude -p"))
    p.add_argument("--model", metavar="ALIAS", help="the model of the sessions; --apply needs it")
    p.add_argument("--skill", metavar="NAME", action="append",
                   help="only the query file of this skill; can repeat")
    p.set_defaults(run=cmd_skill_triggers)
