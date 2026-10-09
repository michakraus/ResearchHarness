# The harness command

`harness` is the one command of the harness. [The `harness` command](../harness-command.md)
describes its verbs and their contract for a user: a verb that changes something prints its plan,
and `--apply` makes the change. This page describes the code: which module implements which verb,
and which modules have only test cases.

The entry point is `bin/harness`. The code is the Python package `lib/harness/`, which uses the
standard library only. Each module that owns a verb has a function `register`, which adds its
verb to the argument parser. Most modules also have a function `selftest`, which runs their own
test cases. `harness test` runs every `selftest`, then the hook probe `hooks/probe.py`, then the
contract sweep. Three verbs live in the adapters: `settings` and `trust` in
`adapters/claude/adapter.py`, and `permissions` in `adapters/opencode/adapter.py`.
[The adapters](adapters.md) describes them.

| verb | module |
|:--|:--|
| `install` | `install.py` |
| `render`, `get`, `leaks` | `profile.py` |
| `githooks`, `wiki-lint-hook`, `workflows` | `githooks.py` |
| `push-all` | `pushall.py` |
| `ci-protection` | `protection.py` |
| `format` | `fmt.py` |
| `skill-triggers` | `skill_triggers.py` |
| `test` | `cli.py` |

`frontmatter.py`, `docs.py` and `sweep.py` have no verb. Their cases run only in `harness test`.
`install_cases.py` holds helpers for the cases of other modules. The sections start with the entry
point and the parser, then the verbs, then the shared modules, then the modules of the tests.

## `harness`

The executable script `bin/harness`, the front door of the tooling. Put `bin/` on the `PATH`, then
run `harness --help` for the list of verbs, or `harness <verb> --help` for one verb.

The script first checks the version of Python. It needs Python 3.11 or later, because the profile
and the model tables are TOML and `tomllib` came into the standard library with 3.11. An older
interpreter prints the version that it found and the version that it needs, and the script exits
2. The check uses no new syntax, so an old interpreter reads it without a syntax error.

Then the script adds `lib/` to the module path and calls `main` of `cli.py`. It follows a symlink
to find `lib/`, so a link to the script in another directory also works.

## `__init__.py`

The package file of `lib/harness/`. Its docstring is the contract of every verb, and
`harness --help` prints it: a verb that changes something is dry by default, exits 1 when
something would change and 0 when nothing would, and `--apply` makes the change. Exit 2 is a usage
error or a failure.

It defines what the other modules share:

- `REPO`, the path of the checkout;
- `HarnessError`, a failure that the verb reports in one line, after which `harness` exits 2;
- `changing(parser)`, which gives a verb its `--apply` flag;
- `outcome(args, changes)`, the exit status of a changing verb: 0 after `--apply` or with no
  change, else 1.

A new verb that changes something uses `changing` and `outcome`, so that it keeps the contract.

## `cli.py`

The argument parser of `harness`, and the verb `harness test`. `main` loads the three adapters
through `frontends.py` first. An adapter that fails to load exits 2 before any verb runs. Then
`main` adds the global options `--profile F` and `--models F`, and one sub-command for each verb
of the modules and the adapters. A `HarnessError` of a verb prints one line, `harness <verb>:
<message>`, and exits 2.

`harness test` runs the cases in this order:

1. the `selftest` of `install.py`, then of each adapter, then of `frontmatter.py`,
   `protection.py`, `profile.py`, `skill_triggers.py` and `docs.py`;
2. the hook probe `hooks/probe.py`, in a process of its own;
3. the contract sweep of `sweep.py`.

It prints one summary line, `<n> cases, <w> wrong`, and exits 1 when a case is wrong. A probe
that prints no summary line, or whose exit status does not agree with it, counts as one more wrong
case.

## `frontends.py`

The list of the frontends, `claude`, `opencode` and `omp`, and the loader of their adapters.
`load` imports each `adapters/<frontend>/adapter.py` by its path, in that order, once.

Each adapter must define six members: `NAME`, `TEMPLATES`, `register`, `plan`, `selftest` and
`RESTART`. An adapter that fails to import exits 2 with its path, its line and the last line of
the exception. An adapter that lacks a member exits 2 with its path. No adapter is skipped.

The module also defines `Plan`, the part of `harness install` that one frontend returns: the
files to install, the warnings, the installed files with no source, the refused files with their
messages, and the steps that run after the files. A later frontend reads the plan of an earlier
one; oh-my-pi reads the rules of the Claude Code plan.

The adapters are described in [the adapters](adapters.md).

## `install.py`

The verb `harness install [--apply] [--force]`. It reads the profile and the model tables, and asks
each adapter for its plan, in the order of `frontends.py`. A plan writes nothing, so a refusal
exits 2 before any file is written.

Then the verb installs the Julia environment of the scripts: it copies `Project.toml` to
`~/.local/share/research-harness/julia/`, or to `$RESEARCH_HARNESS_JULIA`, and instantiates it.
Then it installs the files of each plan, prints the warnings, and runs the steps after the files.
It prints the count line, and after `--apply` the restart line of each frontend whose files
changed. A file that differs in its bytes or its mode is a change. `--force` replaces a file that
an adapter refuses to replace.

The module also holds the helpers of a layer that mirrors its sources: `source_files`,
`check_targets` and `stamp_bytes`, the stamp that the `SessionStart` hook `hooks/install-drift.py`
computes again.

Its cases check that a broken profile or `models.toml` exits 2 with the file name, and that an
adapter that fails to load exits 2 and writes nothing. They also run the restart cases of
`install_cases.py`.

## `install_cases.py`

The helpers for the test cases that run `harness install` end to end. It has no verb and no
`selftest` of its own.

`Scratch` makes a scratch `HOME` below a temporary directory: `~/.claude/skills/`, an OpenCode
directory, a Julia directory with a copy of `Project.toml`, the tree instructions, and the dummy
profile with `tree_agents` set. `Scratch.run` runs `harness install` in a process of its own, with
`HOME`, `OPENCODE_CONFIG_DIR`, `RESEARCH_HARNESS_JULIA` and `PI_CODING_AGENT_DIR` in the scratch
directory. A run that takes more than 60 s is a timeout.

`restart_cases` checks the restart lines of `harness install`. Each case changes the files of one
frontend, or of no frontend, and checks that only the restart lines of the frontends that changed
follow the count line. `install.py` calls it, and the adapters use `Scratch` in their own cases.

## `profile.py`

The private profile and the render of a template. It gives three verbs:

```
harness render TEMPLATE
harness get KEY
harness leaks [--commits F]
```

`render` prints a template with each placeholder `{key}` replaced by its profile value. A list
value repeats the line, or the JSON list element, once for each item. A placeholder that the
profile does not have exits 2. `get` prints one value, one line for each item of a list.

`leaks` searches every tracked file and its path for each string of the profile's `leak` list, and
for the name of each directory below a `repository_roots` entry and each `org` entry. It also
renders each template with `examples/profile.toml` and searches the result. With `--commits F` it
also searches the paths, the added lines and the message of each commit that `F` names. The
pre-push hook calls it so. The verb exits 1 on a hit.

The module also reads the model tables for the adapters. A table that names a tier by an old name
exits 2. [Adapting the profile](../profile.md) describes the keys.

## `githooks.py`

Three verbs that copy shared files into the repositories of the research tree. The research root
is `$RESEARCH_ROOT`, else `~/Research`.

```
harness githooks [--apply]
harness wiki-lint-hook [--apply]
harness workflows [--apply]
```

`githooks` copies `githooks/pre-commit`, `githooks/pre-push` and `scripts/test-layout.jl` into
`.githooks/` of each git repository directly below `Packages/` and `Experiments/`, and sets
`core.hooksPath`. `wiki-lint-hook` copies `githooks/pre-commit-wiki` as the pre-commit hook of the
prose repositories that `WIKI_REPOSITORIES` names. `workflows` copies the canonical files of
`githooks/workflows/` and deletes the retired `CompatHelper.yml`.

A session cannot write `.git/config`. So a run that cannot set `core.hooksPath` prints the command
for each repository, and exits 2. The module also gives `research_root`, `repositories` and `git`
to other modules. It has no `selftest`; the sweep runs its dry runs and its `--apply`.
[The git hooks](githooks.md) describes the copied files.

## `pushall.py`

The verb `harness push-all [--apply] [--skip-hooks] [--include-topic-branches]`. It pushes each git
repository directly below `Packages/` and `Experiments/` whose branch is ahead of its upstream, one
at a time.

It skips a repository with no upstream, one that is also behind its upstream, and one on a branch
that is not the default branch, unless `--include-topic-branches`. The dry run names the `.jl`
files of each push. `--skip-hooks` pushes with `--no-verify`, so the pre-push suite does not run.
Use it only for a push with no Julia source and no `[compat]` change. After a push, the verb
compares the local commit with the remote branch, as `git ls-remote` reports it.

Run it in your own terminal. The pre-push hook of each repository can run a full test suite, so
the verb can take hours, and a tool call of a session stops after ten minutes. The module has no
`selftest`; the sweep runs its dry run.

## `protection.py`

The verb `harness ci-protection [--remove-classic] [--apply]`. It protects the default branch of
each repository with a GitHub ruleset named `main`: no deletion, no force push, and the required
status checks of the canonical `CI.yml`. It also turns on auto-merge and the deletion of merged
branches. `--remove-classic` deletes the classic branch protection, but only where the ruleset
passes every check.

The verb first runs `githooks/verify-workflows.jl`, and refuses when the workflows are not
canonical, because the list of required checks depends on them. It calls `gh api` for each
repository, and skips a repository that is private or where the user is not an admin. Run it in
your own terminal: in a sandboxed session, only the first `gh` call of a process succeeds.

Its cases check `ruleset_problem` against the ruleset as GitHub returns it, and against one break
of each check. The sweep does not run this verb, because it needs `gh` with a login.

## `fmt.py`

The verb `harness format [--apply]`. It runs `githooks/format-tree.jl`, which runs JuliaFormatter
over each tracked `.jl` file of the tree.

JuliaFormatter can stop the whole Julia process on some files. `format-tree.jl` records the file
that it is about to format in a marker. When the process stops, the verb moves that file into a
skip list and runs the script again, at most 40 times. At the end it prints the files that
JuliaFormatter cannot handle. The marker, the skip list and the log go to `$FMT_OUT`, else
`$TMPDIR`.

The dry run counts the files that the script would format, from its summary line. The module has
no `selftest`, and the sweep does not run it, because it runs Julia over the tree.

## `skill_triggers.py`

The verb `harness skill-triggers [--skill <name> …] [--apply --model <alias>]`, the test of whether
each skill loads on the right queries.

It reads `tests/skill-triggers/<skill>.toml` for each skill of `skills/`. The dry run prints the
number of queries per skill and the number of sessions that `--apply` starts. `--apply` runs each
query as one `claude -p` session of 3 turns on the model that `--model` names, without the tools
that write or run commands. A query loads a skill when the first `Skill` call of the first three
assistant messages names it. A failed query runs twice more, and the majority counts. A skill
passes when at least 8 of its 10 `load` queries load it and at most 1 of its 5 `near` queries does.
The report goes to `.scratch/skill-triggers/` below the research root. Every session costs tokens.

Its cases run the parser, the verdict, the majority and the pass rule, and run `--apply` on a fake
`claude`. [Daily use](../daily-use.md) shows the commands.

## `sources.py`

The names of the neutral sources: the five directories `agents/`, `skills/`, `rules/`,
`instructions/` and `commands/`, which belong to no one frontend. Each adapter reads them from
here. The module has no verb and no cases.

`curated_skills` lists the curated skills below a directory: each subdirectory with a `SKILL.md`,
except a hidden one and the directories of `EXCLUDED_SKILLS`. `listing` gives the agents of
`agents/` and the `SKILL.md` of each curated skill of `skills/`. `code_list` writes names as
Markdown code in a sentence, for the text that the adapters generate.

## `frontmatter.py`

The strict parser of the frontmatter of an agent or a skill, the block between the first two `---`
lines. It has no verb. Its cases run in `harness test`.

The parser accepts ten keys, each once. A value is plain or in double quotes, and `tools` and
`skills` take a block list. It refuses each other form, such as a flow list, a comment, an unknown
key or a control character, with the file and the line, and `harness` exits 2.

`parse_file` also checks the neutral vocabulary. `model` must be a tier: `large`, `medium` or
`small`. Each `tools` item must be a neutral tool or `mcp/kaimon/<tool>`. The `description` of a
skill has at most 1,024 characters and no `<` or `>`.

Its cases check each refused and each accepted form, and parse every agent of `agents/` and every
curated skill of `skills/`.

## `sweep.py`

The contract sweep, the last set of cases of `harness test`. It has no verb.

The sweep makes a fixture `HOME` in a temporary directory: the dummy profile and model tables, the
files that the verbs read, and a research root with one package and one prose repository. Then:

- it runs the dry run of each verb and checks that it exits 0 or 1, prints no traceback and
  changes no file;
- it removes each precondition alone, such as the profile or `~/.claude.json`, and checks that each
  verb that needs it exits 2 with one line;
- it runs `--apply` of `githooks`, `wiki-lint-hook`, `workflows`, `trust` and `settings install`,
  and checks that the dry run after it exits 0.

It does not run `format`, `ci-protection` or `skill-triggers`.
[Development](../development.md) describes the tests.

## `docs.py`

The check of the component pages of the documentation site, which runs in `harness test`. It has
no verb.

The table `KINDS` maps each page of `docs/src/components/` to the tracked files that are its
components, and to the name of each. The check reads the level-2 headings of each page and the
names in backticks in them. It fails when a component has no heading on its page. It also fails
when a heading names something that is no component of its page, so a removed component leaves no
old section.

It also checks that each tool of the dependency tables of the README has a level-2 heading in
`docs/src/tools.md` that names it as a whole word. So a new agent, skill, hook, script or tool
needs its section in the same change.
