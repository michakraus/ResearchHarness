# Typical use

This page describes the recurring tasks after the setup. The [tutorial](tutorial.md) shows most
of them once, step by step; this page is the reference. [harness-command.md](harness-command.md)
describes the contract of every subcommand: a subcommand that changes something prints its plan,
and `--apply` makes the change.

## Change an agent, a skill, a rule or an instruction

Edit the source in this repository, never its installed copy in `~/.claude/`. The sources are in
the neutral directories `agents/`, `skills/`, `rules/`, `instructions/` and `commands/`, and in
`adapters/claude/` for `CLAUDE.md` and `RTK.md`. A fact about your own research tree goes into the
[tree instructions](concepts.md#tree-instructions). The next `harness install --apply` overwrites
an edit of an installed copy, and the installed settings refuse such an edit from a
[session](concepts.md#session).

Then read the plan and [install](concepts.md#install) the change:

```bash
harness install
harness install --apply
```

A running session keeps the files that it has read. After an `--apply`, the subcommand prints one
line for each [frontend](concepts.md#frontend) whose files changed, which tells you to restart
that frontend.

**Put a correction into a file.** A fact that you tell a session lasts for that session only. A
fact in an [instruction file](concepts.md#instruction-file), a [rule](concepts.md#rule), a
[skill](concepts.md#skill) or the tree instructions reaches every later session. Step 8 of the
tutorial, [Make a correction that lasts](tutorial.md#step-8-make-a-correction-that-lasts), shows
it once from the start to the end.

## Change the settings

The settings template `settings/settings.proposal.json` is the source of the sections
`permissions`, `hooks`, `sandbox` and `modelSettings` of `~/.claude/settings.json`. Edit the
template, then read the diff and install it, in your own terminal. The dry run prints the diff
of the four sections after the line of `~/.claude/settings.json`:

```bash
harness install
harness install --apply
```

A permission rule that names you, your institution or your machine goes into the
[profile](concepts.md#profile), not into the
template. Commit the template when you install a change: the commit is the record of the
installed sections. To undo a change, revert the commit of the template and install again. Run
these commands in the checkout:

```bash
git revert <commit>
harness install --apply
```

[security.md](security.md#check-a-change-of-the-settings) says how to check the result.

## The drift warning at session start

`harness install --apply` writes the stamp `~/.claude/.harness-install.json`. At each session
start, the `SessionStart` [hook](concepts.md#hook) `hooks/install-drift.py` computes the stamp's
digest again from the sources. It warns when the installed layer is behind its sources, when the
stamp is missing, and when it cannot read a source or the stamp. The warning names the cause and
the command.

<WalkThrough name="install" />

*From an edit to the [drift](concepts.md#drift) check.* You edit a source. At the next session
start, the hook finds the installed layer behind its sources and warns. You run the dry run and
apply the plan. At the session start after that, the hook finds no difference.

When the warning appears, an edit of a source is not installed yet. Run the dry run, read the
plan, and apply it:

```bash
harness install
harness install --apply
```

The hook only warns. It blocks nothing, and the session continues with the old installed layer.
[architecture.md](architecture.md#the-claude-code-layer) describes the stamp.

## Update the harness

`harness update` brings a checkout on `main` up to `origin/main`. The dry run fetches, prints
the new commits and the files that they change, and exits 1 when there is a new commit.
`--apply` also shows the whole diff and asks `y/N` in the terminal. On `y` it merges
`--ff-only` and runs `harness install --apply`:

```bash
harness update
harness update --apply
```

It stops when a tracked file has changes, and when `main` has commits that `origin/main` lacks.
A checkout at a detached HEAD is pinned to a commit, for example by the dotfiles of a machine.
`harness update` does not move it: move the pin where it is set.

## The leak check before a push

The pre-push hook of this repository runs two leak checks before a push to `main`: gitleaks finds
secrets and home paths, and `harness leaks --commits` finds the strings of the profile's `leak`
list and the names of your research tree. A hit refuses the push. A push to another branch runs
only `harness leaks --commits` in the hook, and CI runs gitleaks on it.

Run the check yourself before a commit, too:

```bash
harness leaks
```

It searches every tracked file, its path and the templates rendered with the example profile.
Remove the matched string from the file. [development.md](development.md#the-pre-push-hook) describes
both checks.

## Keep the research tree in sync

Some subcommands act on every repository of the research tree: they clone it, pull and push it,
and give each repository the same git hooks and workflows.
[The research tree](research-tree.md#clone-sync-and-trust) describes each of them and the order in
which to run them.

## The triggering test of the skills

`harness skill-triggers` tests whether each skill loads on the queries that must load it, and
stays unloaded on its near misses. The queries are in `tests/skill-triggers/<skill>.toml`. The dry
run prints the number of queries per skill and the number of sessions that an `--apply` starts:

```bash
harness skill-triggers
```

`--apply --model <alias>` runs each query as one `claude -p` session on that model. Each session
costs tokens, which you pay. `--skill <name>` limits the test to one skill, and it can repeat:

```bash
harness skill-triggers --skill plan-parts --apply --model sonnet
```

The result goes to `.scratch/skill-triggers/` in the research tree. Run the test after you change
the `description` of a skill.
