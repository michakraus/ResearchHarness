# The builder-critic loop

A part of a plan is one pull request with a [spec](specs-and-gates.md). The builder-critic loop
takes a part from its spec to an open pull request with no question to you on the way, unless the
spec leaves a decision that only you can take. One agent builds, a second agent that has not seen
the builder's reasoning judges, and the loop repeats until a critic passes the part on a green
suite. This page describes the two loops of the harness, `build-part` and `build-reviewed`, and
the choice between them.

## Why a blind critic

A [context](../concepts.md#context) that wrote the code knows why each line is right, so it reads
what it meant, not what it wrote. A new context with only the spec and the branch reads the code as
a user of it would. The critic therefore never sees the builder's report, and each round has a new
critic. A critic that judged one round would carry its own reasons into the next.

The same holds for the builder: after each critic round, the loop starts a new builder on the same
worktree, with the last builder's report as a handoff note. A resumed builder carries its whole
context, and a new one starts from the reports, which costs less and leaves fewer defects.

## The tier of a part

The plan gives each part a tier. The tier chooses how much review the part gets:

| tier | how it is built | for |
|:--|:--|:--|
| `decision` | not built; it waits for your decision | a part whose spec holds a question that only you can answer |
| `build` | the full loop of [`build-part`](../components/skills.md#build-part): two critics in round 1, verify rounds, the advisor and the arbitrator | a part that draws a security boundary, predicts what another tool reads, or has a slow gate |
| `reviewed` | the small loop of [`build-reviewed`](../components/skills.md#build-reviewed): one builder, one critic, one fix round, and your session's read | a small part with a fast gate, whose every edge the spec decides |
| `direct` | your session or a workflow makes the change, with no critic | a mechanical change whose every check is a command, such as a rename across many repositories |

## The full loop: `build-part`

<WalkThrough name="build-part" />

*From a task to a pull request with build-part.* The `plan-parts` skill writes the parts table,
the list of the parts of a plan, and `build-part` runs one part. In the first critic round, two
critics judge the work at high effort beside a run of the full suite. After a FAIL, a new builder
fixes the work, and one critic judges the fix. The second FAIL goes to the arbitrator. After a
PASS, a new builder finishes the part and opens the pull request. The figure shows the default
models of Claude Code. Your `models.toml` can add a council of critics on other models for
OpenCode and oh-my-pi.

1. **The spec gate.** A `build` part starts only when its spec holds the sections
   *Decided at the edges* and *Tests catch*. The script `spec-gate.py` checks this. Where a section
   is missing, the advisor writes it, or the part waits for you.
2. **The build.** The skill picks the builder and the critic from the part's language:
   `julia-builder` and `julia-critic` for Julia, `python-builder` and `python-critic` for Python,
   and `part-builder` and `part-critic` elsewhere. The builder works in its own
   [worktree](#one-worktree-for-each-part). It writes the tests first, then the code, then runs the
   [mutants](mutants.md) of the spec and its own. It returns `ready for critic` with a table of its
   mutants and a table of the text lines it checked. A report with an open survivor is not ready.
3. **Round 1.** Two critics judge the whole part at high effort, each blind to the other and to
   the builder. Beside them, `julia-test-runner` runs the full suite. The round fails when either
   critic fails, and its findings are the union of both reports. One draw of a critic misses defects
   that a second one finds, and round 1 is the one broad search of the loop.
4. **A fix and a verify round.** After a FAIL, a new builder fixes each blocking defect and the
   other defects that its branch causes, and records the rest in the repository's
   `KNOWN_ISSUES.md`. One new critic then judges only the fix: it gets the earlier blocking defects
   and their reproducers, never the builder's report.
5. **The arbitrator.** The second FAIL goes to the `arbitrator`, not to a third round. Two fix
   attempts that did not close mean that the approach must change. The arbitrator reads the whole
   loop and chooses one move: continue, redesign, decide, a test round, a fresh build, a rerun, a
   known issue, or park the part for you. A FAIL of the round after its ruling stops the loop, and
   the skill reports to you.
6. **The finish.** After a PASS on a green suite, a new builder rereads the text of the whole
   branch, runs [`julia-branch-verifier`](review.md#before-the-pull-request) and opens the pull
   request. The code does not change after the PASS, except for the verifier's fixes and fixes of
   text.
7. **After the loop.** The skill records the rounds, the decisions and the rulings in the part's
   section of the task file. Each defect that a critic found late, in a class that the
   [edge catalogue](edges.md) does not hold, becomes a new line of that catalogue.

### What a critic reports

A critic returns `Verdict: PASS` or `Verdict: FAIL`, an evidence table with one row per clause of
the spec, its *blocking defects* and its *other defects*. A blocking defect is a failure inside the
domain of a clause: the part does not do what the spec says. Each one names its reproducer and one
cause:

| cause | the defect |
|:--|:--|
| `wrong result` | a wrong output, or an unmet clause on an input |
| `evidence` | the code is right on every input tried, but a test cannot fail or a mutant survives |
| `spec` | a clause or an edge is undecided, or two rules disagree on what the branch must do |
| `fix regression` | in a verify round: the defect is in lines that the fix added or changed |
| `neighbour` | in a verify round: a new input of a class that an earlier defect names, in code that predicts what another tool reads or does |
| `harness` | a tool, the environment, a prompt or a moved `main`, not the branch |

An other defect is real, but outside every clause; the builder fixes it when its branch causes it,
and records it otherwise. The causes decide the next move. A round whose every blocking defect is
`harness` does not count. A `spec` defect on a rule outside the part goes to the arbitrator,
because the same rule reaches the other parts of the plan. When the arbitrator rules, the cause
that dominates picks its move: `neighbour` or `fix regression` asks for a redesign, `evidence` for
a round that writes only tests.

### Questions inside the loop

A builder that meets a question that the spec does not decide stops and names the question. The
skill gives it to the `advisor`, which decides it and says how sure it is and whether the decision
can change inside the pull request. A decision that cannot change, such as a public interface,
parks the part for you. Every decision goes into the task file before the next round, so that the
critic judges against the same text as the builder.

## The small loop: `build-reviewed`

<WalkThrough name="build-reviewed" />

*From a task to a pull request with build-reviewed.* The skill spawns one `part-builder`, and one
`part-critic` judges its work. After a FAIL, a new builder fixes the findings, and your session
checks the fix before it tells the builder to finish the part. With a PASS, your session reads
the result, and then it tells the builder to finish the part.

A part of tier `reviewed` is small, and its spec decides every edge. `build-reviewed` runs it in
your session on the large model, with one builder and one blind critic. A FAIL gets one fix round,
and your session checks the fix itself; a FAIL that the fix round does not close goes to you. Your
session decides the questions inside the part, so no advisor and no arbitrator run. Before the
finish, your session reads the result: it is the second reviewer.

## One worktree for each part

Each part is built in a worktree: a second checkout of the repository on its own branch, below
`~/Research/.worktrees/`. The main checkout stays on `main`, and two parts can be built at the same
time in two worktrees. Each new builder and critic of the same part works on the same worktree.
The `WorktreeCreate` hook makes each worktree from `origin/HEAD`, at the place that
[the research tree](../research-tree.md#temporary-work) names. [Git safety](../safeguards/git-safety.md#worktrees)
says how a worktree is made and removed.

## Several parts at once

Parts that touch no common file can run at the same time, each in its own worktree. The collision
map of the plan says which parts share files; [Tasks](tasks.md#the-collision-map) describes it.
A part that is `blocked by` another starts only after that part merges, in a worktree from the
new `main`. Parts that only add lines to a shared `CHANGELOG.md` resolve it by a rebase.
