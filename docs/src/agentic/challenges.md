# Challenges

A coding agent writes code fast, and most of that code is right. The rest is the problem: a test
that passes with the feature deleted, an edge case that nobody decided, a report that says "done"
for work that is half done. A human reviewer catches some of this, but a reviewer who reads every
line of every change is the bottleneck that the agent was to remove. This page names the failure
modes of agentic coding and the answer of the harness to each. The other pages of this section
describe the answers one by one.

## The failure modes

| failure | what happens | the answer of the harness |
|:--|:--|:--|
| **No fixed goal** | the agent stops when the work looks done, and "done" moves with its context | a [spec](specs-and-gates.md) with a *Done when* whose every clause is a command |
| **Self-review** | a context that wrote the code reads what it meant, not what it wrote | a [blind critic](loop.md#why-a-blind-critic) in a new context, with the spec and the branch only |
| **Weak tests** | a test passes, but it passes with the feature deleted too | [named mutants](mutants.md): each test must fail on a stated change of the code |
| **Undecided edges** | `NaN`, an empty input or the other precision has no answer, and each round of review finds one more | [*Decided at the edges*](specs-and-gates.md#what-a-spec-holds), from the [edge catalogue](edges.md) |
| **False premises** | the plan rests on a fact about the code that is not true | [a premise check](specs-and-gates.md#the-premise-check) by a `reader` agent and by `spec-validate.py` |
| **Rules that are not read** | an instruction works only when the agent reads it and acts on it | [static checks](static-checks.md) and gates: a command fires every time |
| **A full context** | test output and file dumps fill the context, and the agent loses the task | [sub-agents](agents.md#sub-agents) for long, wide and bounded work |
| **Forgetting** | a session ends, and the next one starts from nothing | a [task file](tasks.md) that holds the plan, the decisions and the state |
| **Loops that do not close** | each fix brings a new defect in the next round | an [arbitrator](loop.md#the-full-loop-build-part) after the second FAIL, and a part parked for you |
| **Harm outside the task** | a command deletes files, sends a secret, or pushes to the wrong place | the [safeguards](../safeguards/risks.md) |

## From a task to a merge

<PipelineFigure />

*From a task to a merge.* A task becomes a spec. A builder writes the tests and the code, and the
gates run on its branch. Blind critics judge the branch against the spec: two in round 1, then one
in each verify round. A FAIL goes back to a new builder; a PASS opens a pull request, and you merge it. A defect outside every clause of the
spec, in a class that the edge catalogue does not hold, becomes a new line of the catalogue, and
the next spec decides that edge in advance.

Three ideas carry the whole pipeline:

1. **Write the benchmark before the code.** The spec and its named mutants exist before the
   builder starts. So the critic judges against a fixed text, and the builder cannot move the
   goal.
2. **Separate the contexts.** The builder, the critic, the advisor and the arbitrator each work in
   a context of their own. No judgement comes from a context that has a stake in the result.
3. **Turn what you learn into a check.** A defect class that a critic finds becomes a line of the
   edge catalogue, and a mechanical rule becomes a static check. The next part starts with more
   decided, and the loop gets shorter.

## What stays with you

The harness moves review out of your hands where a command or a fresh context does it as well.
Some decisions stay yours:

- **The goal and the plan.** You agree on the task and its done condition, and you decide the
  questions of the `decision` parts ([Tasks](tasks.md#the-life-of-a-task)).
- **An irreversible decision inside the loop.** The advisor decides a question that can change
  inside the pull request; a public interface, for example, goes to you.
- **The merge.** No agent merges a pull request that its own session opened
  ([Review and pull requests](review.md#who-merges)).

## The cost

Each new context costs tokens, and two critics in round 1 cost twice what one costs. The harness
spends this where a defect is expensive: a part that draws a security boundary, predicts what
another tool reads, or has a slow gate gets the full loop. A small part with a fast gate gets the
small loop, and a mechanical change gets no critic at all. [The builder-critic
loop](loop.md#the-tier-of-a-part) gives the four tiers.

[Example: a feature in a Julia package](example.md) follows one task through the whole pipeline.
