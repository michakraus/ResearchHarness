---
paths: ["**/CLAUDE.md", "**/SKILL.md", "**/agents/*.md", "**/rules/*.md", "**/AGENTS.md"]
description: An instruction file is written in the present tense and carries no history. Where each kind of instruction belongs, and what it costs.
---

# You are editing an instruction file

A `CLAUDE.md`, a `SKILL.md`, an agent definition and a rule file are all the same kind of document:
**instructions for now**. They tell a session what to do today.

## Present tense. No history. No exceptions.

**Write every rule as a present-tense statement or an imperative.** A rule narrated in the past
reads as lapsed, and a session that reads it as lapsed stops following it.

| do not write | write |
|:--|:--|
| "This rule was added after a sweep committed another session's work." | "A sweep commits another session's work." |
| "We originally used BlueStyle; the tree moved to SciML." | "`style = "sciml"`, from each repository's `.JuliaFormatter.toml`." |
| "As of 2026-09-19 the directory is `Harness/`." | "The directory is `Harness/`." |
| "The old `Grep|Glob` hook is now retired." | *(delete it — a retired thing is not an instruction)* |
| "This used to point at `CLAUDE.md`." | *(delete it — say where it points)* |

**Banned words and phrases**, because each one dates the text invisibly and rots on its own:
*now*, *currently*, *recently*, *as of*, *originally*, *previously*, *used to*, *no longer*,
*has been changed to*, *going forward*, *from now on*, *since <date>*.

**Delete rather than annotate.** When a rule stops being true, remove it. Do not leave it with a
note saying it is superseded — that costs every session the tokens to read a rule it must then
discard.

## Where the history goes instead

`CHANGELOG.md`. That is the whole division: **the instruction file describes the current state, the
changelog records how it got there.** Add the entry in the same change that earns it, and never
correct an old entry — see `~/.claude/rules/changelog.md`.

If you feel the need to explain why a rule exists, state the **mechanism**, not the incident. The
mechanism is present-tense and stays true; the incident is past-tense and dates immediately.

- Incident: "In September an agent reported a total its own rows did not sum to."
- Mechanism: "An agent's total can disagree with its own rows. Quote the rows."

**An instruction file stands on its own.** It cites no GitHub issue, pull request, session id or
transcript as the reason for a rule. A reader must not need a link to act on the rule, and a link
dates the file when the issue changes state. Put the evidence in the Harness page that owns the
topic, and the history in `CHANGELOG.md`.

**A measurement that scopes a fact is not history.** "On 2.1.278 the key is `paths`, not `globs`"
is a present-tense fact with its validity stated. Keep those. What does not belong is the
document's own past.

## Which file a rule belongs in

Three layers, and each costs differently. Put a rule in the cheapest layer that still reaches it.

| layer | loads | put here |
|:--|:--|:--|
| `~/.claude/CLAUDE.md` and its imports | always, every session **and every sub-agent** | rules that must fire anywhere, unprompted: harness-neutral ones in `instructions/core.md`, ones about this user and tree in `instructions/research-tree.md`, Claude Code mechanics in `CLAUDE.md` itself |
| a directory-scoped `CLAUDE.md` | on a Read of a file in its subtree | rules for that tree |
| `~/.claude/rules/*.md` with `paths:` | on a Read of a matching file | a file type or a cross-cutting concern |
| `<project>/.claude/rules/*.md` | **eagerly, at session start, whatever the frontmatter says** | nothing — it costs what `CLAUDE.md` costs |

**Write a rule in user scope, `~/.claude/rules/`.** There `paths:` makes it lazy: it loads on a
`Read` of a matching file and costs nothing otherwise. Write its source, not the installed copy:
`~/Research/Harness/rules/`, or the tree instructions' `rules/` for a rule about this
tree; the user's `harness install --apply` installs it. The key is `paths` — `globs:` is ignored,
and a Bash `cat` triggers nothing; only a `Read` does.

**A rule under a project's own `.claude/rules/` is not lazy.** Every file there is injected at
session start, whether it carries `paths:`, carries `globs:`, or carries no frontmatter at all. A
file parked there "because it does not load" does load, in every session, for as long as it exists.

**The always-on file keeps the imperative; the mechanism and the evidence move.** "Never
`git add -A`" must fire anywhere, so it stays there. The paragraph explaining why belongs in a
rule, a scoped file or an `Environment/Notes/` page.

## Before you write the rule, ask whether it should be a check

Classify the thing you are about to require.

**Mechanical** — a fixed pattern, a banned call, a file location, a normalisation. It gets a
deterministic check: a git hook, a CI job, a lint rule. **Build the check instead of writing the
rule.** A check fires every time. A rule fires when a session reads it and acts on it.

**A judgement call** — cross-file consistency, "match the surrounding style", anything no check can
stand in for. That is what an instruction file is for.

**Where the check goes.** A glob over the command text goes to
`Harness/settings/settings.proposal.json`. What a glob cannot express — a flag cluster, anything
needing the parsed command — goes to `Harness/hooks/` as a script plus a page, and
`Environment/Notes/hooks/README.md` gives the form. A check inside a repository goes to
`Harness/githooks/`. Both `~/.claude/settings.json` and `~/.claude/hooks/` are
deny-write from a session, so the session writes the proposal and the user installs it. Propose it
anyway. The prose rule is the fallback, not the first answer.

## Every line earns its place

**The no-op test: does this line change behaviour against the model's default?** A line that does
not costs tokens on every load and buys nothing. The test is model-relative, not reader-relative:
two people who disagree about a no-op disagree about the default, and they settle it by running the
document rather than by arguing. When a sentence fails, **delete the whole sentence** rather than
trim words from it.

**State the positive target.** A prohibition makes the forbidden behaviour more available, not
less, because naming it puts it in context. Write "stage the paths you changed", not "do not
sweep". A prohibition earns its place only as a hard guardrail you cannot phrase positively, and
then it carries the positive beside it: "Never `git add -A` — stage the paths you changed."

**The environment is a source of truth too** — a `Project.toml`, a `--help` output, a directory
layout. A document that restates one is a cache, and a cache earns its load only when the lookup is
expensive. Cache what a session cannot find by looking: the unwritten convention, the reason behind
a choice, the measurement that costs a session to repeat. Leave a one-command lookup where it is,
because there it cannot go stale.

**Repeat a word, never a meaning.** A compact word the model already holds — *part*, *finding*,
*witness*, *sweep*, *frontier* — anchors a region of behaviour in one token, and it sharpens every
description that carries it. Repeating the *meaning* instead is duplication, which the last line of
this file rules out.

**A file that only grows is already wrong.** Stale layers settle because adding feels safe and
removing feels risky, until a reader must dig through them to find what is still live. Prune on the
same pass that adds.

## A step ends on a criterion the agent can check

Two levers, and they work independently.

**Clarity** — can a session tell done from not-done? A vague bound invites it to stop early, with
attention already on the step after. Sharpen the bound first, because that is local and cheap.
Hiding the later steps works only across a real context boundary — a hand-off, or a sub-agent
dispatch. An inline call leaves them in context and clears nothing.

**Demand** — how much the criterion requires. "Every changed file accounted for" forces more work
than "produce a change list". Demand binds a body of reference as well as a sequence: "every rule
applied" is what makes an all-reference document exhaustive.

## Style

Prose for the user, and every instruction file, is **ASD-STE100 Simplified Technical English**:
short sentences, active voice, simple tenses, one word for one meaning. This does not govern code,
identifiers, commit messages or quoted output.

Keep each fact in exactly one place. Two copies disagree eventually, and the reader cannot tell
which one is current.
