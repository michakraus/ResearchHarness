# Scripts

The scripts are command-line tools in `scripts/` of this repository. Agents, skills, git hooks
and people run them from the checkout, for example as
`julia --startup-file=no ~/Research/Harness/scripts/run-tests.jl`. `harness install` does not copy
them. `harness githooks --apply` copies one, `test-layout.jl`, into each repository. A file that
ends in `-test.jl` holds the tests of the script beside it. `.githooks/pre-push` of this
repository runs these test files, as [Development](../development.md) describes.

The Julia scripts load their packages from the environment that `harness install --apply` creates
in `~/.local/share/research-harness/julia/` (see
[The Julia environment](../harness-command.md#the-julia-environment)). The variable
`RESEARCH_HARNESS_JULIA` names another location. So no caller gives `--project`. Always give
`--startup-file=no`: the startup file can load Revise, and its errors then fill the output.

The sections come in groups: the test layout and the test runs, the mutation tests and the
gate, the structure of Julia code, the task files, the lint of the prose repositories, the
token use of sessions, and the update job.

## `test-layout.jl` and `test-layout-test.jl`

`test-layout.jl` parses the test layout of a Julia repository and checks it against the test
convention. The rule `julia-tests` (`rules/julia-tests.md`) describes the convention. The rules
have the tags D1 to D10, and `using`, `seed`, `label` and `compat`.

```bash
julia --startup-file=no test-layout.jl --check <repository> ...
```

It prints one line per violation, `<repository>: [<rule>] <what>`, and exits 1 when it finds
one. A repository in the convention gives no output and exit status 0. It does not check rule D6,
the 60 s limit of a `core` file; `run-tests.jl <repository> core` reports that. Nor does it check
the JET part of rule D4, the quality files: `test/quality/jet.jl` where the package has a hot or
kernel path.

`harness githooks --apply` copies the script into `.githooks/` of each repository. The
`pre-commit` hook (see [Git hooks and workflows](githooks.md)) runs that copy on a commit that
touches `test/`.
`run-tests.jl` and `test-census.jl` read its parser, `layout`.

`test-layout-test.jl` checks the script on a fixture repository in the convention. Each change
of the fixture breaks one rule, and the script must name exactly that rule.

```bash
julia --startup-file=no test-layout-test.jl
```

## `run-tests.jl` and `run-tests-test.jl`

`run-tests.jl` runs the tests of a Julia package and prints a short verdict. The exit status is
the status of the tests: 0 pass, 1 fail, 2 bad arguments or a layout outside the convention, 3 a
failure of the script.

```bash
julia --startup-file=no run-tests.jl <package> [--jobs <n>] [affected [<base>] | select [<base>] | full | list | <unit> ...]
```

- `affected`, the default, runs the `core` test files that the diff against `<base>` (default
  `origin/main`) can reach, and the quality files. A changed `Project.toml` runs `full`.
- `select` prints what `affected` runs, and runs nothing. `list` prints the test files, their
  groups and their labels. `full` runs `Pkg.test()`.
- A `<unit>` is a group, a path relative to `test/`, or a part of a testset label.
- `--jobs <n>` runs the selection in n worker processes.

A selection runs in one fresh process through `TestEnv`. The log goes to
`~/Research/.scratch/tests/`. A manifest that another minor version of Julia resolved stays out
of the run: the run then uses a copy of the package. Outside the convention's layout, only `full`
runs.

The agents `julia-test-runner`, `julia-builder` and `julia-critic`, the skill `build-part` and the
rules `julia-code` and `julia-tests` use it. `mutate.jl`, `pins.jl` and `gate.jl` call it.

`run-tests-test.jl` checks `run-tests.jl`, `mutate.jl` and `test-census.jl` on fixtures. It runs
for about 11 minutes with no output.

```bash
julia --startup-file=no run-tests-test.jl
```

## `test-census.jl`

`test-census.jl` writes a Markdown table of the test layout of each package and experiment
repository. It reads the layout with the parser of `test-layout.jl`.

```bash
julia --startup-file=no test-census.jl [<root> ...]
```

The default roots are `~/Research/Packages` and `~/Research/Experiments`. For each repository
with a `Project.toml` and a `.git`, a row gives these values:

- how `runtests.jl` reaches its files;
- the gates on `ARGS` or `ENV`;
- where the test dependencies are;
- whether Aqua and JET run;
- the test files that `runtests.jl` does not reach;
- the number of test files whose path mirrors a file of `src/`.

It only reports. No skill or agent calls it. `run-tests-test.jl` holds its tests. Use
`test-layout.jl --check` for a verdict on one repository.

## `mutate.jl`, `mutate-worker.jl`, `mutants.jl` and `mutants-test.jl`

A mutation test changes the source code on purpose, then runs the tests. A test that still
passes does not see the change. These scripts work on a copy of the package under
`~/Research/.scratch/mutants/` and never change the package.

`mutants.jl` writes a mutant list from the lines of `src/` that the diff against `<base>`
(default `origin/main`) adds. It writes one mutant per operator node, for example `<` to `<=`,
`min` to `max`, or a deleted statement. It needs Julia 1.12 or later.

```bash
julia --startup-file=no mutants.jl <package> <out.toml> [<base>]
```

`mutate.jl` runs the mutants. It gives each mutant a verdict: CAUGHT when a unit fails, SURVIVED
when every unit passes, and also NO-COVERAGE, UNKNOWN and INVALID.

```bash
julia --startup-file=no mutate.jl <package> <file> <from> <to> [<unit> ...]
julia --startup-file=no mutate.jl <package> --list <mutants.toml> [--only <verdict>] [<unit> ...]
julia --startup-file=no mutate.jl <package> --warm <mutants.toml> [--jobs <n>] [--only <verdict>] [<unit> ...]
julia --startup-file=no mutate.jl <package> --check <mutants.toml>
```

The list modes write a result file under `~/Research/.scratch/mutants/`, named for the package
directory and the list, and print its path on the `result:` line. `--check` runs nothing and says
VALID or INVALID for each mutant. The checks need `fatou` on the `PATH` and Julia 1.12 or later.
Without units, the script runs the units that the diff against `origin/main` reaches.

`mutate-worker.jl` is the warm worker of `mutate.jl --warm`. `mutate.jl` starts it. Do not run
it by hand.

The skills `build-part` and `plan-parts` and the agents `julia-builder` and `julia-critic` use
`mutate.jl`. The skill `build-part` uses `mutants.jl`. `mutants-test.jl` checks `mutants.jl`
(`julia --startup-file=no mutants-test.jl`). The tests of `mutate.jl` are in
`run-tests-test.jl`.

## `pins.jl`

`pins.jl` runs the tests of a branch on the code of its base. A test that passes there pins
behaviour. A test that fails there reproduces the defect that it names.

```bash
julia --startup-file=no pins.jl <package> <base> [<unit> ...]
```

`<base>` is a git ref, such as `origin/main`, or a directory that holds the `src/` and `ext/` of
the base. The run uses a copy under `~/Research/.scratch/mutants/`: the tree of the branch with
`src/` and `ext/` of the base. A `<unit>` is as for `run-tests.jl`. Without units, the script
runs the units that the diff against `origin/main` reaches.

The script gives one verdict for all units: PINS when every unit passes, FAILS when one fails. For a
verdict per test file, give one unit per call. An exit of `run-tests.jl` other than 0 or 1 gives
UNKNOWN.

The skill `build-part` and the agents `julia-builder` and `julia-critic` use it.
`run-tests-test.jl` holds its tests.

## `base-tree.jl` and `base-tree-test.jl`

`base-tree.jl` puts the tree of one commit of a package into a new or empty directory, for a probe
on the unmodified tree.

```bash
julia --startup-file=no base-tree.jl <package> <ref> <dir> [<path> ...]
```

With paths, it writes only those paths of the tree. It prints the directory, the number of files
and the commit. It refuses a directory that is not empty, so that no old file stays in the tree.
It does in one call what `git archive <ref> | tar -x` does, but with no permission prompt: a
worktree-isolated agent cannot run a pipeline that holds `git`, and `git archive -o` asks.

The skill `build-part` names it for the agents `julia-builder` and `julia-critic`, and the agent
`julia-pr-reviewer` names it for its probes. `base-tree-test.jl` checks it on the commits of this repository, in about 3 s.

## `gate.jl` and `gate-test.jl`

`gate.jl` runs the checks that a script can run before a critic reviews the head of the branch,
and writes one short report, `<out-dir>/gate.md`.

```bash
julia --startup-file=no gate.jl <package> <out-dir> [--base <ref>] [--named <list>]... [--jobs <n>] [--no-sweep]
```

The steps run in this order, each with its full log under `<out-dir>`:

1. `tests`: `run-tests.jl <package> affected`.
2. `named`: `mutate.jl --warm` on a copy of each `--named` list. A mutant that is not CAUGHT
   fails the step.
3. `generated`: `mutants.jl` against `<base>`, then `mutate.jl --warm --jobs <n>` (4 by
   default). The survivors are information for the critic, not a failure. `--no-sweep` omits
   this step.
4. `format`: JuliaFormatter on the `.jl` files that the diff against `<base>` adds or changes.

The exit status is 0 when each step that can fail passes, 1 when a step fails, 2 on bad
arguments, and 3 when a step gave no verdict and no other step failed. No skill or agent in this
repository calls it by name.

`gate-test.jl` checks each step on given outputs, and the refusal of bad arguments
(`julia --startup-file=no gate-test.jl`). It does not run the whole gate.

## `julia-methods.jl`

`julia-methods.jl` lists every method of a Julia name, with its signature and location. It does
not load the package, so it works on a package that does not load. It finds a module-qualified
definition such as `Base.length(x::Problem) = …` too.

```bash
julia --startup-file=no julia-methods.jl <package-dir> <name> [<name> …]
julia --startup-file=no julia-methods.jl <package-dir> --all
```

The first argument is a path. The script asks the language server of `fatou` for the symbols of
each file, through `fatou-lsp.jl`. It reports definitions only. It does not say which method a
call dispatches to, and it does not find callers. On an empty result, the script exits with
status 1; an empty result is not a negative result.

The skill `julia-structure`, the rule `julia-code` and the agents `exhaustive-auditor`,
`julia-branch-verifier`, `julia-critic` and `julia-load-doctor` use it. For dispatch, use
Kaimon's `search_methods` on a warm session. For callers, use `julia-callers.jl`.

## `fatou-lsp.jl` and `fatou-lsp-test.jl`

`fatou-lsp.jl` is a small client of the language server `fatou lsp`. It is a module that other
scripts include; it has no command line. `julia-methods.jl` uses it.

It gives these functions: `lsp_open`, `lsp_close`, `initialize`, `did_open`, `document_symbol`,
`references` and `flatten`. `document_symbol` returns every symbol of one file. A method is a
symbol of LSP kind 12, and only such a symbol carries a signature. `references` answers only for
an unqualified name; treat an empty result as unknown.

`lsp_close` stops the server with the `shutdown` and `exit` messages of the protocol, and returns
whether the server stopped. Do not ignore a `false`: a server that does not stop stays in memory.
The variable `FATOU_LSP_BIN` names the `fatou` binary, when the script cannot find it.

`fatou-lsp-test.jl` checks that the script finds a native `fatou` on the `PATH`, and the platform
binary below an npm prefix. It also runs the client against the real `fatou`, or prints a skip
line where none is on the `PATH` (`julia --startup-file=no fatou-lsp-test.jl`). CI runs it on
Linux.

## `julia-callers.jl`

`julia-callers.jl` finds the callers of a function in a running Julia session. It reads the
lowered code of each method that the target modules define. So it also sees a module-qualified
definition. Include it in a session that has loaded the packages, for example through Kaimon:

```julia
include(".../julia-callers.jl")
callers(ExampleBase.nsamples, [Example, Other])
dead(Example.compute_difference, [Example])
```

It sees only what the session has loaded, and the copy of each package that the manifest
resolves, not the working tree. Test files and unloaded package extensions are not in the
result. So a `dead` verdict means "nothing loaded calls it", not "nothing calls it".

The skill `julia-structure`, the rule `julia-code` and the agents `exhaustive-auditor` and
`julia-branch-verifier` use it. For a package that does not load, use `julia-methods.jl` for the
definitions, and a text search for the uses.

## `parts-table.awk`

`parts-table.awk` extracts the parts table and the file-collision map from a task file. A task
file is a Markdown plan in `Tasks/`, and a part is one unit of its work. The output is much
shorter than the file.

```bash
awk -f parts-table.awk "Tasks/<file>.md"
```

It writes two record types, separated by tabs, in the order of the file:

```text
PART       part  repository  sections  tier  state
COLLISION  repository  file  parts
```

It reads the columns by name, not by position. A column that the table does not have gives an
empty cell. A file with no `## Parts` section gives no output: the task has no parts. The script
does not change the file.

The skills `build-part` and `build-reviewed` and the agents `advisor`, `arbitrator` and
`part-critic` run it; `part-builder` gets its output from its caller. `spec-gate.py` and
`spec-bundle.py` call it.

## `spec-gate.py`

`spec-gate.py` is the spec gate of the skill `build-part`. It checks that a part of tier `build`
in `Packages/` or `Experiments/` has its edges and its mutants. The sections that the part names
must hold the labels **Decided at the edges** and **Tests catch**.

```bash
python3 spec-gate.py "<task file>" [<part> ...]
```

With no part named, it checks each open `build` part of the file. A part that is merged,
declined, done or in review is not open. A named part is checked in any state. A part outside
`Packages/` and `Experiments/` is exempt.

It also checks that the **Files** of each checked part other than a `direct` one lie in one
repository. An isolated builder cannot write outside its worktree, so a file in another
repository is a step of the dispatcher, the session that runs the `build-part` or
`build-reviewed` skill.

A part whose `sections` cell names `spec` has its spec in the spec-delta format, in
`Evidence/<task file's name>/<part>/spec.md` beside the task file. For such a part, in any
repository, the gate runs `spec-validate.py` on the spec, with the premises on the base commit of
the repository's main checkout. `--no-run` checks the structure only. A premise that needs a
device runs only with `--devices`; without it, the part is `UNMEASURED`, with exit status 2.

It prints one line per part: PASS, MISSING with the labels, INVALID with the number of errors and
the validator's lines below it, SPANS with the repositories, or EXEMPT with the reason. The exit
status is 0 when each checked part passes or is exempt, 1 when a part misses a label, is invalid
or spans two repositories, and 3 when the script failed. It reads the parts table
through `parts-table.awk`. The skills `build-part`, `build-reviewed` and `plan-parts` run it.

## `spec-bundle.py`

`spec-bundle.py` writes the spec bundle of one part: every text of the task file that the part's
builder and critics read, in one file. `julia-builder` and `julia-critic` read the bundle and
nothing else of the task file, so a rule reaches them only through it.

```bash
python3 spec-bundle.py "<task file>" <part> [--out <file>]
```

The bundle holds the part's `PART` row and the `COLLISION` rows that name it, the sections that
its `sections` cell names, §V and §L, and the sections that §L's two lines **The builder also
reads:** and **The critic also reads:** name. A key such as `§6` names a section, a heading in
italics such as `*Traps*` names a section by its title, and `the preamble of §<key>` names a
section's text up to its first subheading. A key with no heading, such as a T-number, gives each
table row whose first cell is the key, under its table's header. §V and §L end at their next
heading, so a handover filed below §L stays out, and the `PART` row keeps only the state, not the
narration that a state cell gathers over the builds. The key `spec` gives the part's spec in the
spec-delta format, whole, and the header names the spec's directory as `$SPEC`.

The header lists each section with its line range in the task file, the task file's commit, and
a SHA-256 of the body, which a report names. It prints the path, the line count and the hash, and
one `unresolved: <name>` line on stderr for each name that matches nothing. The exit status is 0
when every name resolves, 1 when one does not or the part is not in the table, and 3 when the
script failed. The skill `build-part` runs it before every spawn of a builder or a critic, and
`plan-parts` runs it on each part before a plan is done.

## `spec-validate.py`

`spec-validate.py` is the strict validator of a part spec in the spec-delta format, which
`skills/plan-parts/spec-format.md` defines: a living spec of the base, a change proposal, a delta
of requirements with WHEN/THEN scenarios, and what stays from the plan.

```bash
python3 spec-validate.py <spec.md> [--repo <checkout> | --base <tree>] [--no-run] [--env NAME=VALUE ...]
python3 spec-validate.py <spec.md> --head <tree> --out <dir> [--env NAME=VALUE ...]
```

It checks the structure by headings, not by substrings: the four sections, SHALL or MUST in each
requirement, a WHEN, a THEN, a `check:` and a `catches:` in each scenario, no block that refers to
another, the files under `$SPEC/`, the mutant table against the `catches:` lines, the base commit,
a `domain:` in each scenario of a requirement that names a reference, and no `git grep` without
`-P` that uses `\b`, `\s`, `\w` or `\d`, which Apple Git ignores. Then it runs each
premise of the living spec on the base: `--repo` exports the base commit with `git archive`. With
`--head`, it runs each `check:` of the delta on a head instead, and fails a check that changes the
head's `git status`. A check bullet that ends in `(device: metal)` runs only with
`--devices metal`, from a Kaimon session, which has the GPU that the Bash sandbox lacks; elsewhere
it is `not run` and the result `UNMEASURED`. The exit status is 0 on a pass, 2 when a device
command did not run and everything else passed, 1 on a fail, and 3 when the script failed.
`spec-gate.py` runs it in planning and before a build; the skills `build-part` and
`build-reviewed` run its `--head` form in the gate of every round.

## `known-issues-similar.py`

`known-issues-similar.py` makes a shortlist of open issues that can be duplicates. It reads the
`## Open Issues` section of `CHANGELOG.md` and the whole `KNOWN_ISSUES.md` of each repository in
`Packages/` and `Experiments/`, and splits them into entries.

```bash
python3 known-issues-similar.py --model <name> [--threshold <cos>] [--out <file>]
                                [--pair <repo> <needle> <repo> <needle>] ...
```

It embeds each entry with the local Ollama server (`/api/embed`) and the model `<name>`. Then it
computes the cosine of each pair of entries. A `--pair` names a known pair; the script prints its
rank to stderr. `--threshold` and `--out` go together: the script then writes each pair at or
above the threshold, with both texts, to the file.

It only proposes. A person decides whether a pair is one issue. The script exits with status 1
when Ollama fails, the model is missing, or a `--pair` needle does not match exactly one entry;
it then writes nothing.
No skill or agent calls it.

## `wiki-lint.jl`

`wiki-lint.jl` checks the structure of the Markdown in the prose repositories of the research
tree: the vaults `Knowledge/` and `Environment/`, and the reference trees `Tasks/`,
`Bibliography/` and `Library/`. It finds text that a later change of the tree made false, for
example a broken link, a path that does not exist, or a line citation past the end of its file.

```bash
julia --startup-file=no wiki-lint.jl
julia --startup-file=no wiki-lint.jl Knowledge  # one of them
julia --startup-file=no wiki-lint.jl --strict   # warnings fail too
julia --startup-file=no wiki-lint.jl --quiet    # findings and totals only
```

Without a name, the script checks every tree.

A vault gets every check. A reference tree gets the checks of paths and line citations; `Tasks/`
gets the schema of the task board too. The script skips each `CHANGELOG.md`. A finding is an
ERROR or a WARN. The exit status is 0 when there is no ERROR, and with `--strict` no WARN; 1 on a
finding at the failing level; and 2 when the lint could not run. It reads only the working tree:
no model, no index, no network. The research root is `$RESEARCH_ROOT`, or `~/Research` if it is
not set.

The hook `pre-commit-wiki` (see [Git hooks and workflows](githooks.md)) runs it with `--quiet`
before each commit in a prose repository.

## `startup-tokens.py`

`startup-tokens.py` measures the size of the context at the start of each session. It reads the
transcripts below `~/.claude/projects/`.

```bash
python3 startup-tokens.py            # the last 7 days
python3 startup-tokens.py --days 30
```

For each transcript it takes the usage of the first API call: the total input, the cache read
and the cache write. That call includes the first prompt. It groups main sessions by entry point,
and sub-agents by agent type and entry point, and prints the medians. It changes no file. No
skill or agent calls it. For the token use after the start, use `session-tokens.py`.

## `session-tokens.py`

`session-tokens.py` shows where the tokens go inside a session. It reads the transcripts below
`~/.claude/projects/` and changes no file.

```bash
python3 session-tokens.py            # the last 7 days
python3 session-tokens.py --days 30
```

It prints four reports:

1. The size of the context per API call, in bands, with its cost in input-token equivalents.
2. The tool results by tool, with the cost that each result carries in the later calls.
3. Waste patterns: a whole-file read of a file that the session read before and did not edit; a
   shell command repeated with the same output; a call repeated after an error; a run of errors.
4. The compactions.

It estimates the tokens of a tool result at 3.5 characters per token. The usage figures come from
the API. No skill or agent calls it. For the context at the start, use `startup-tokens.py`.

## The audit scripts

The scripts in `scripts/audit/` measure the harness over a window of time: where the tokens go,
how the builder-critic loop converges, and which failures it has. They read the transcripts of
Claude Code, OpenCode and oh-my-pi, and change no source file. No skill or agent calls them. Run
them from the directory that is to hold the tables.

```bash
julia --startup-file=no -t 8 scripts/audit/transcripts.jl . --from 2026-10-02T00:00:00Z --to 2026-10-16T00:00:00Z
julia --startup-file=no scripts/audit/report.jl .
julia --startup-file=no scripts/audit/sample.jl . <seed> 40
julia --startup-file=no scripts/audit/taxonomy.jl <lines-dir>
scripts/audit/crosscheck.sh 2026-10-02T00:00:00Z 2026-10-16T00:00:00Z
julia --startup-file=no -t 8 scripts/audit/instructions.jl . <lines-dir> --from 2026-10-02T00:00:00Z --to 2026-10-16T00:00:00Z \
    --harness <checkout> --tree <dir> --claude-md <root> --notes <dir>
julia --startup-file=no scripts/audit/citations.jl instructions.tsv --kind agent --root <dir> --tools tools.tsv
julia --startup-file=no scripts/audit/tense-lint.jl instructions.tsv --kind agent
```

- `transcripts.jl` writes one row per run to `runs.tsv`: a main session or a sub-agent, with its
  agent type, model, effort, tokens by kind, input cost, first-call context, tool calls, wall time,
  verdict, task file, part, pull requests, skills, the rules that loaded on a read, and the cache
  rewrites after a pause. It also writes the tool calls per run, the 500 largest tool results, and
  the prompt and report of each run of a loop agent. Only records with a timestamp in the window
  count.
- `report.jl` reads those tables and writes the reports: tokens per part and part tier, critic
  rounds to a PASS, the advisor and arbitrator calls, the largest tool results, the first-call
  context per agent type, and the cache rewrites. It also writes a GraphQL query for the loop's
  pull requests. `gh` reads a token that the Claude Code sandbox denies to a script, so the query
  runs as a command of its own, and its output goes into `prs.tsv`; the script's header gives the
  command. With `prs.tsv`, the
  reports add the state, the commits after opening and the failing checks of each pull request.
- `sample.jl` draws a sample of parts, seeded by a SHA-256 hash, so the draw does not depend on the
  Julia version. It writes one dossier per part for a reader.
- `taxonomy.jl` counts the failure lines that the readers return: by class, by stage, by the file
  that could prevent the failure, and by reason.
- `crosscheck.sh` computes two totals of `transcripts.jl` again with `jq`, on a path that shares
  no code with it: all context tokens, and the cache reads of the `julia-builder` runs.
- `instructions.jl` writes `instructions.tsv`, one row per instruction file: the agents, skills,
  rules, commands and global files of a harness checkout, the tree's instructions and rules, every
  `CLAUDE.md` below a root, the pages below an evidence directory, and every memory file. Each row
  gives the tokens at 3.5 characters each, when the file loads, the runs that loaded it in the
  window, and the failure classes whose lines cite it. A load is a record in `runs.tsv` (agent
  type, Skill call, rule or `CLAUDE.md` on a Read) or in a Claude Code transcript (the
  `instructions` record at the start of a run, a Read of the file, a slash command). It prints the
  table, the totals per kind, the files that no run loaded, and the files that loaded and that no
  failure line cites.
- `citations.jl` reads the rows of `instructions.tsv` and checks what each file cites in a code
  span, a fenced shell block or a link: a path exists, a command is an executable, a long flag is
  in the help of its command or in the source of its script, a tool name is one that a run called,
  and an agent or skill name is in the table. It prints the citations that do not resolve.
- `tense-lint.jl` reports each word of `rules/instruction-files.md` that dates a text or tells its
  history (*now*, *as of*, *no longer*, *since* a date, and the others), outside code, quotations
  and mentions, with `file:line`. It skips a `CHANGELOG.md`, and exits 1 on a hit.

Output tokens are not in the cost. A transcript writes one API message as several records, and
only the last one holds the full output count, so a sum of output is complete only where the
column `out_complete` is near 1.

## `julia-update.jl` and `julia-update-test.jl`

`julia-update.jl` keeps the Julia installation, the default environments and the Kaimon MCP
server current. It runs four steps in order:

1. `juliaup update`.
2. `Pkg.update()` in the default environment of each installed `X.Y` channel, then in the
   installed harness environment.
3. `Pkg.Apps.update("Kaimon")`, then a check that Kaimon loads.
4. A check of the Kaimon server. When the server runs from a Julia binary that `juliaup`
   deleted, the job restarts it. It reports any other reason for a restart, and does not restart.

The header gives no command line. A job of the service manager runs the installed copy in
`~/.local/bin/` each day, not the copy in the checkout:

```bash
~/.juliaup/bin/julia --startup-file=no ~/.local/bin/julia-update.jl
```

The script runs on macOS and on Linux, and stops with an error before the first step on any other
system. It finds each tool on the `PATH`, which the job fixes. The two systems differ in four
places:

| | macOS | Linux |
|:--|:--|:--|
| the job | launchd, `launchagents/julia-update.plist` | `systemd --user`, the unit `julia-update.service` |
| the binary of the Kaimon server | `ps -o comm=` of the process that `lsof` finds on port 2828 | the link `/proc/<pid>/exe` of that process, without its ` (deleted)` suffix |
| the restart of the server | `launchctl kickstart -k gui/<uid>/<launchd_prefix>.kaimon` | `systemctl --user restart kaimon.service` |
| the notification, and the log that it names | `osascript`; `~/Library/Logs/julia-update/` | `notify-send`; `journalctl --user -u julia-update.service` |

On macOS the script reads the profile key `launchd_prefix` for the label of the Kaimon job (see
[Profile](../profile.md)); on Linux it reads no profile. A failure or a restart that is due also
shows a notification. Without the notifier on the `PATH`, the log line is the only report. When
no `lsof` is on the `PATH`, the server check fails and the job restarts nothing. A restart that
fails is a failure, with its output in the log, and so is a restart with no service manager on
the `PATH`. The script exits with status 1 when a step fails.

`julia-update-test.jl` runs the script on a fixture home with stubs of every tool it calls, on the
system it runs on (`julia --startup-file=no julia-update-test.jl`). CI runs it on Linux.
