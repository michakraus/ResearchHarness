# Scripts

The scripts are command-line tools in `scripts/` of this repository. Agents, skills, git hooks
and people run them from the checkout, for example as
`julia --startup-file=no ~/Research/Harness/scripts/run-tests.jl`. `harness install` does not copy
them. `harness githooks --apply` copies one, `test-layout.jl`, into each repository. A file that
ends in `-test.jl` holds the tests of the script beside it. `.githooks/pre-push` of this
repository runs these test files, as [Development](../development.md) describes.

The Julia scripts load their packages from the environment that `harness install --apply` makes
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
one. A repository in the convention gives no output and exit 0. It does not check D6, the 60 s
limit of a `core` file; `run-tests.jl <repository> core` reports that. It does not check the JET
half of D4 either.

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

The list modes write `<mutants>.result.json` beside the list. `--check` runs nothing and says
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

The verdict is one for all units: PINS when every unit passes, FAILS when one fails. For a
verdict per test file, give one unit per call. An exit of `run-tests.jl` other than 0 or 1 gives
UNKNOWN.

The skill `build-part` and the agents `julia-builder` and `julia-critic` use it.
`run-tests-test.jl` holds its tests.

## `gate.jl` and `gate-test.jl`

`gate.jl` runs the checks that a script can run before a critic reads a head, and writes one
short report, `<out-dir>/gate.md`.

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

Exit 0: each step that can fail passes. 1: a step fails. 2: bad arguments. 3: a step gave no
verdict, and no other step failed. No skill or agent in this repository calls it by name.

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
call dispatches to, and it does not find callers. An empty result exits 1 and is not a negative.

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

The skills `build-part`, `build-reviewed` and `plan-parts` and the agents `advisor`,
`arbitrator`, `julia-builder`, `julia-critic`, `part-builder` and `part-critic` use it.
`spec-gate.py` calls it.

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

It prints one line per part: PASS, MISSING with the labels, or EXEMPT with the reason. Exit 0:
each checked part passes or is exempt. 1: a part misses a label. 3: the script failed. It reads
the parts table through `parts-table.awk`. The skills `build-part` and `build-reviewed` run it.

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

It only proposes. A person decides whether a pair is one issue. Exit 1 when Ollama fails, the
model is missing, or a `--pair` needle does not match exactly one entry; it then writes nothing.
No skill or agent calls it.

## `wiki-lint.jl`

`wiki-lint.jl` checks the structure of the Markdown in the prose repositories of the research
tree: the vaults `Knowledge/` and `Environment/`, and the reference trees `Tasks/`,
`Bibliography/` and `Library/`. It finds a sentence that the tree made false, for example a
broken link, a path that does not exist, or a line citation past the end of its file.

```bash
julia --startup-file=no wiki-lint.jl
julia --startup-file=no wiki-lint.jl Knowledge  # one of them
julia --startup-file=no wiki-lint.jl --strict   # warnings fail too
julia --startup-file=no wiki-lint.jl --quiet    # findings and totals only
```

Without a name, the script checks every tree.

A vault gets every check. A reference tree gets the checks of paths and line citations; `Tasks/`
gets the schema of the task board too. The script skips each `CHANGELOG.md`. A finding is an
ERROR or a WARN. Exit 0: no ERROR, and with `--strict` no WARN. 1: a finding at the failing
level. 2: the lint could not run. It reads only the working tree: no model, no index, no
network. The research root is `$RESEARCH_ROOT`, else `~/Research`.

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
and subagents by agent type and entry point, and prints the medians. It changes no file. No
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
   shell command again with the same output; a call repeated after an error; a run of errors.
4. The compactions.

It estimates the tokens of a tool result at 3.5 characters per token. The usage figures come from
the API. No skill or agent calls it. For the context at the start, use `startup-tokens.py`.

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
fails is a failure, with its output in the log. Exit 1 when a step fails.

`julia-update-test.jl` runs the script on a fixture home with stubs of every tool it calls, on the
system it runs on (`julia --startup-file=no julia-update-test.jl`). CI runs it on Linux.
