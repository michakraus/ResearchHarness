# Agents

An agent here is a sub-agent: a separate agent with its own context. The main session starts it
for one task and gives it a prompt. The sub-agent does the task and returns one report, which the
main session reads as the result. Its work does not fill the context of the main session. A skill
or another agent can also start a sub-agent.

Each source is a Markdown file in `agents/`. Its frontmatter holds `name`, the name that a caller
uses; `description`, the text from which the frontend selects the agent for a request; `tools`,
the neutral tools that the agent can call; and `model`, a tier (`large`, `medium` or `small`). An
agent with no `model` uses the model of its caller. Some agents also set `effort`, `skills` (the
skills that load at the start), `isolation: worktree` or `omitClaudeMd: true` (the agent does not
load `CLAUDE.md`). The body is the instruction text of the agent. Most bodies prescribe the exact
shape of the report.

`harness install` copies each agent to `~/.claude/agents/` for Claude Code, with the tier and the
tools written as Claude Code names them. It renders each agent for OpenCode, with an "Under
OpenCode" section before the body, and for oh-my-pi. [Architecture](../architecture.md) gives the
map of the tools and tiers. Two agents, `local` and `qwen-worker`, are for OpenCode only: their
sources are in `adapters/opencode/agents/`. The sections below come in five groups: the
builder-critic loop, pull requests and CI, Julia diagnosis and tests, research, and the
general-purpose agents.

## `julia-builder`

The builder of the builder-critic loop. It builds one part of a task file: a plan that is split
into parts, where each part is one pull request. The `build-part` skill starts it and runs the
loop. Call it directly only for a part that you have already chosen.

The builder reads the rows of the parts table and the sections of its own part, never the whole
task file. It works in a worktree that its caller makes. It writes the tests first, then the code,
and verifies each clause of the part's *Done when*. Then it commits and returns
`Verdict: ready for critic`. After each critic round, the caller starts a new builder on the same
worktree. After a FAIL, it fixes the blocking defects and records other defects in the
repository's `KNOWN_ISSUES.md`. After a PASS, it runs `julia-branch-verifier` and opens the pull
request.

It runs no command longer than 5 minutes. A longer run goes to its caller under *Left for the
dispatcher*. It never merges, and it does not edit the task file. Use `julia-pr-shepherd` to take
the pull request to green CI.

## `julia-critic`

The critic of the builder-critic loop. It judges one built part against the part's *Done when*
and returns `Verdict: PASS` or `FAIL`, with the defects. The `build-part` skill starts it. It
edits nothing in the worktree.

In round 1, two critics judge the whole part apart, and neither sees the builder's report. A
critic writes its own evidence table and runs every check itself. It runs the new tests on the
base, runs each named mutant, and probes the edges of each clause. It writes its probes only to a
scratch directory for its round. A verify round judges only the fix diff, against the earlier
blocking defects and their reproducers.

Each blocking defect has a reproducer and one cause, for example `wrong result`, `spec` or
`fix regression`. The dispatcher uses the cause to decide whether the loop continues. The critic
does not run the full suite, does not start a sub-agent, and does not comment on a pull request.
Use `julia-pr-reviewer` for a pull request that exists.

## `advisor`

The advisor decides one question in an autonomous loop, in place of a question to the user. Only
the dispatcher of the `build-part` skill calls it; a builder or a critic never does. Typical
questions: a builder stops on a decision that its section does not make, a clause is ambiguous,
or a finding may be out of scope.

It reads the part's sections and every decision that the task file records. It checks a claim
itself before a decision rests on it. It returns the decision, the reasons, the rejected options,
a confidence (`high`, `medium` or `low`), and whether the decision is reversible inside the pull
request. A `low` decision parks the part for the user.

It edits nothing. It does not decide a `decision` part, a weaker *Done when*, a change to a public
API beyond the part, or an action outside the pull request. Use `arbitrator` when the loop does
not converge.

## `arbitrator`

The arbitrator rules on the course of a builder-critic loop that does not converge. The dispatcher
of the `build-part` skill calls it on one of four triggers: a second FAIL, a stop after a PASS
that asks for a code change, a defect class that already failed another part, or a blocked loop.

It reads the whole loop: every builder's and critic's report, the diffs of each round, the suite
runs and the decisions. It gives each blocking defect a cause and measures the progress from round
to round. Then it chooses one move from a fixed list, for example `continue`, `redesign`,
`test round`, `fresh build` or `park`. It returns the move, the decision text for the task file,
a confidence, and whether the move parks the part for the user.

It edits nothing and does not ask the user. Use `advisor` for one question in a loop that
converges.

## `part-builder`

The builder for a part whose tier cell is `reviewed`, in any language. The `build-reviewed` skill
starts it. One builder holds the whole part: the caller sends it the critic's findings and the
finish by message.

It reads its part's sections and the plan's §V and §L, which name the gate: the suite and the
checks that the change must pass. It writes the tests first, then the code, and verifies each
clause. It commits and returns `Verdict: ready for critic`. After the critic's report, it fixes
the blocking defects and records other defects. On `Round: finish` it does what §L says. In a
package repository, it runs `julia-branch-verifier` and opens the pull request.

It runs no command longer than 5 minutes and does not edit the task file. Use `julia-builder` for
a part of tier `build`, and `worker` for a task with no part and no critic.

## `part-critic`

The critic for a part of tier `reviewed`. The `build-reviewed` skill starts it once per part. It
judges the part blind against its *Done when* and returns `PASS` or `FAIL`.

It writes its own evidence table, runs the gate that §V and §L name, breaks each named mutant in a
copy, and probes each clause's domain. It writes probes only under a scratch directory. A defect
blocks only when it is a failure inside a clause's domain, a test that cannot fail, a surviving
named mutant, or a hidden failure. Every other defect goes into the report for the record.

It edits nothing in the work's directory and does not start a sub-agent. Use `julia-critic` for a
part of tier `build`, and `julia-pr-reviewer` for a pull request that exists.

## `julia-pr-shepherd`

The shepherd takes a pull request on a Julia package from review to green CI. Use it with a
request such as "review and fix PR #NN" or "take PR #NN all the way". Start it from a directory
in the package's checkout; it then works in a worktree of its own.

It checks first that the pull request is open, is no draft, and accepts a push. Then it starts
`julia-pr-reviewer`, which posts the review. It fixes the findings of severity `blocker`, `bug`
and `correctness-risk`, and starts `changelog-scribe` for a changelog entry. It commits the paths
by name, pushes, and waits for CI in the foreground. When CI is red across several jobs, it can
start `ci-triage`. At the end, it posts one comment that answers each finding.

It never merges and never approves. It makes one fix round only, and it stops on a design
decision. Use `julia-pr-reviewer` when you want only a review.

## `julia-pr-reviewer`

The reviewer reviews a pull request on a Julia package and posts the review. Use it with a request
such as "review PR #NN", "is this PR ready to merge" or "why is CI red on this PR".
`julia-pr-shepherd` also starts it.

It works in a worktree of its own at the head of the pull request. It takes the file list from
`git diff`, because `gh pr view --json files` stops at 100 files. It reads the CI jobs, not only
the workflow result, and measures again each figure that the pull request claims. It reviews
blind: the account of the change is a claim to check. It writes only the review body and its
probes, under a scratch directory, and posts the review with `gh`.

It returns a findings table with `file:line` and evidence, and the CI verdict. It does not edit
code. Use `julia-pr-shepherd` to fix the findings, and the `julia-package-audit` skill for a sweep
of a whole package.

## `julia-branch-verifier`

The verifier checks and fixes a topic branch of a Julia package before its pull request exists.
`julia-builder` and `part-builder` start it before they open a pull request.

It finds the diff against the merge base and the set of changed symbols. Then it runs a
seven-point pass on the diff only, for example correctness, type piracy, type instability,
avoidable allocations, stale comments and history outside `CHANGELOG.md`. A finding counts
against the branch only when its source is in the changed lines, or when the branch made it
wrong. It fixes what it can, under the rules of the `julia-surgical-fix` skill.

It returns a verdict, the exact paths to stage, and a block for the pull-request body. It does not
stage, commit, push or open the pull request, and it does not run `Pkg.test()`. For a missing
changelog entry it names `changelog-scribe`. Use `julia-pr-reviewer` after the pull request
exists.

## `ci-triage`

This agent reads the GitHub Actions results of one or more repositories. It separates real
regressions from failures that are already known. Use it with a request such as "why is CI red"
or "check CI across the packages". `julia-pr-shepherd` also starts it.

It reads with `gh` and with the jobs of each run, not only the run's result. Its source lists many
traps, for example a check that is missing instead of failed, or a cache that went bad on one
operating system. It never reports green for a repository that it could not read.

It returns one verdict per repository: `green`, `FAIL`, `expected red`, `no runs` or `drift`. An
`expected red` is a real answer, not a hedge. It changes nothing. Use `git-hook-triage` for local
git hooks, and `julia-pr-reviewer` for the content of one pull request.

## `git-hook-triage`

This agent finds out why a git hook blocked, failed or seems to hang. Use it with a request such
as "the commit was refused", "pre-push failed" or "the push has printed nothing for twenty
minutes".

It decides between three cases. A `pre-commit` stage blocked the commit; a `pre-push` run found a
real test failure; or a push to `main` is silent because `pre-push` runs the full suite. In the
last case it checks the remote branch with `git ls-remote` and reports that nothing is wrong. It
also compares the hook with the source in the harness, to find drift, and checks
`core.hooksPath`. [Git hooks](githooks.md) describes the hooks.

It does not edit a hook and never proposes `--no-verify`. When the load test of `pre-commit`
fails, it hands over to `julia-load-doctor`. Use `ci-triage` for GitHub Actions.

## `julia-load-doctor`

This agent finds out why a Julia package does not load, and proposes the smallest fix. Use it with
a request such as "using X fails" or "the pre-commit hook says loads FAILED". A package that does
not load blocks every commit that stages a `.jl` file, because `pre-commit` runs a load test.

It reproduces the failure and reads the first error, not the last. It puts the cause into one of
four classes: an undeclared dependency, a name moved to an extension, an upstream regression, or
code that needs a rewrite. Before it blames upstream, it checks whether the manifest is out of
date. It probes in a scratch environment outside the repository.

It returns the cause class, the `file:line`, the minimal fix, and whether the fix is local or
needs an upstream release. It diagnoses only and edits nothing. Use `git-hook-triage` when the
hook itself is the suspect.

## `julia-test-runner`

This agent runs Julia tests and returns only the verdict, so that the test output stays out of the
main context. Use it with a request such as "run the tests" or "run that one testset". The
`build-part` and `build-reviewed` skills start it for the full suite and for the long runs of a
builder.

It runs a selection of test files with `run-tests.jl`, or the full suite, with
`--check-bounds=auto` when allocations are in scope. It can also use a warm Kaimon session, or
the `testrunner` command for one test file and line range. It reports the Julia version and the
check-bounds setting. Under `--check-bounds=yes` it says that the run is no evidence for an
allocation bound.

It returns pass or fail per testset, with each failure quoted in full. It does not edit source,
change a tolerance or skip a testset. Use `julia-perf-analyst` for speed or allocation questions.

## `julia-perf-analyst`

This agent answers a Julia performance or allocation question by measurement. Use it with a
request such as "why does this allocate", "did this change help" or "reproduce the allocation
figure from that PR". It follows the `julia-performance` skill, which it loads.

It first reproduces the reported number. If the number does not reproduce, it reports that and
stops. It measures each variant in a fresh process, after a warm-up, with the median over repeats.
It uses `--check-bounds=auto` and prints the resolved package versions next to each reading. Then
it changes only the change under test, and only after that looks for the cause.

It returns a table of allocations and times, the method, the cause with `file:line`, and a
conclusion. "Not reproducible" is a complete answer. Use the `julia-package-audit` skill for a
static sweep with no measurement.

## `literature-scout`

This agent searches the literature and returns a triaged list of candidates with DOIs. Use it with
a request such as "find papers on X", "is there prior work on this" or "track down this citation".

It searches the structured indexes first, for example Crossref, OpenAlex and arXiv, and publisher
pages last. For a paper behind a paywall it uses the link resolver that the tree instructions
name. It marks each candidate as new, already in the bibliography, already in the library,
superseded or retracted. It proposes a citation key in the scheme `AuthorSurname:Year`.

It returns a table of candidates, BibTeX entries for the new ones, a retrieval worklist, and what
it did not find. It writes no prose review and has no write tools. If a fetched page tells it to
act, it quotes the text and stops.

## `latex-verifier`

This agent checks the mathematics of a `.tex` manuscript claim by claim, and writes a Julia script
that checks each claim. Use it with a request such as "check the derivation in this paper" or
"verify the proof in section 3". It loads the `math-verify` and `latex-revision` skills.

It lists and numbers all claims first. For each claim it decides what a check is and what makes
the check fail. It writes the check in Julia, runs it, and runs a control that can fail too. It
puts each script into the paper's `scripts/` directory and cites it with `\script{}`.

It returns a verdict per claim (`holds`, `fails`, `holds under` a condition, or `inconclusive`)
and the scripts. It does not change prose, the structure or the change markings. For one statement
with no paper, use the `math-verify` skill.

## `reader`

A lean read-only agent: it searches, reads and returns the conclusion. Use it in place of a
general-purpose agent for a search whose answer is a list, a location or a short verdict. A
workflow script can name it as the agent of a read-only stage. It has no `model`, so it uses the
model of its caller.

It loads no `CLAUDE.md`, memory or skill list, so it starts with a small context. It runs only
read-only shell commands. It cites each fact as `path:line`, separates what it read from what it
infers, and says what it did not search. A truncated search is no negative for it.

It changes nothing. Use `exhaustive-auditor` for an all, none or absence claim that you publish,
and `worker` when files change.

## `worker`

A lean agent for one bounded task that reads, edits and runs commands: a stage of a fan-out, a
mechanical change in a named set of files, or a scripted check. Use it in place of a
general-purpose agent when the prompt specifies the task fully. A workflow script can name it as
the agent of a stage. It has no `model`, so it uses the model of its caller.

It loads no `CLAUDE.md`, so the caller names the rules that the task needs. It touches only what
the task names, and edits files only with `Edit` and `Write`. It does not stage, commit or push
unless the prompt says so. It puts temporary files under a scratch directory, never in a
repository.

It returns what it changed, what it ran and what that returned. Use `reader` when nothing changes,
and a `julia-*` agent when the task needs that agent's protocol.

## `exhaustive-auditor`

This agent audits a bounded scope completely, for a claim that you publish in a review, an issue
or a paper. Use it with a request such as "is this function dead code" or "list every use of X in
this package". It is slow and expensive, and it needs an explicit scope.

It sweeps the whole scope with a text search, then reads and classifies each hit. A comment, a
keyword argument and a real call can match the same pattern. It adds `julia-methods.jl`, which
lists the definitions of a name without loading the package, and `julia-callers.jl`, which lists
callers in a Kaimon session. It runs in plan mode and changes nothing.

It returns the scope, the verdict, the classified hits, and every limitation that could make the
verdict false. The verdict is "cannot be established" unless it read or swept every path of the
scope. For a quick check, use `reader`.

## `changelog-scribe`

This agent writes the `CHANGELOG.md` entry for a change that is already made. Use it with a
request such as "write the changelog entry" or "does this need a changelog entry".
`julia-pr-shepherd` starts it, and `julia-branch-verifier` names it for a missing entry.

It reads the top of the file first, because the convention differs from tree to tree: version
headings for a package, dated passes for a paper, a research log for a project. It writes one
entry in that convention: what changed and why it matters to a user. For a format pass, a typo or
a rename with no effect, it reports "no entry needed".

It edits `CHANGELOG.md` and no other file. Under OpenCode, a path rule limits its edits to that
file. It does not stage or commit, and it does not change a version number. Use the
`julia-release` skill for a release.

## `local`

An OpenCode-only agent, from `adapters/opencode/agents/local.md`. It is a primary agent for
offline work: a local model controls the work and does it, with no network. Select it with
`opencode --agent local`, or with the Tab key in a session.

Its instructions are short, because a local model cannot hold the full set of rules. It works in
small steps and reports each result. Before it adds a name, it runs `julia-methods.jl`. It
follows rules for Julia performance and for the tests of type stability and allocations. It uses
Kaimon `ex` for a type instability and `fatou lint` for one file. It stops after two failed
attempts.

It does not commit to `main` in a package repository, never uses `git add -A`, and does not delete
dead code. It has no Claude Code or oh-my-pi copy.

## `qwen-worker`

An OpenCode-only agent, from `adapters/opencode/agents/qwen-worker.md`. It is a sub-agent that
runs on the local model, for mechanical Julia work: a bounded edit, a format pass, a named
testset, or the diagnosis of one allocation. Use it when the result is checkable and the method
is known.

Its rules are the same short set as those of `local`. Its frontmatter denies the `task` tool and
all Kaimon tools. So it cannot start a sub-agent or use a live Julia session. It reports a type
instability to the primary agent, which has a session.

Do not use it to select an approach, to design an algorithm, or for work over many files. It has
no Claude Code or oh-my-pi copy.
