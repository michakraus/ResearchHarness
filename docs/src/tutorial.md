# Tutorial: a first session

This tutorial walks you through a first conversation with Claude Code and the installed harness,
in eight steps. Each step says what you should see, and what to do when it does not happen.

You need a Mac, a Claude Code account, the harness installed as [Setup](setup-macos.md) describes,
and a repository to work in. The conversation costs tokens, which you pay.

**Two tracks.** The steps use a Julia package in a git repository, for example
`~/Research/Packages/Example`; use your own package in its place. If you have no Julia package,
use any git repository. A paragraph that starts with **Without a Julia package** says where your
step differs.

## The terms

The tutorial uses the words below. Each word links its entry in the glossary of
[Concepts](concepts.md#glossary), which also explains the ideas behind them.

- **At work:** [coding agent](concepts.md#coding-agent),
  [frontend](concepts.md#frontend), [session](concepts.md#session),
  [context](concepts.md#context), [tool call](concepts.md#tool-call).
- **The control:** [permission prompt](concepts.md#permission-prompt),
  [sandbox](concepts.md#sandbox), [hook](concepts.md#hook).
- **The configuration:** [instruction file](concepts.md#instruction-file),
  [rule](concepts.md#rule), [skill](concepts.md#skill), [agent](concepts.md#agent),
  [sub-agent](concepts.md#sub-agent), [tier](concepts.md#tier), [effort](concepts.md#effort).
- **Your own files:** [profile](concepts.md#profile),
  [tree instructions](concepts.md#tree-instructions), [install](concepts.md#install),
  [drift](concepts.md#drift).

In the session you see the parts of the harness at work: a question and its tool calls, a
permission prompt, a guard hook that refuses a command, a skill, a sub-agent, a review of a change,
and a correction that lasts.

## Before you start

Do each step of [Setup](setup-macos.md), and its last check,
[The check that it worked](setup-macos.md#the-check-that-it-worked). The tutorial does not repeat
them.

## Step 1: start a session

Go to your package and start Claude Code:

```bash
cd ~/Research/Packages/Example
claude
```

**Without a Julia package**, go to your git repository in its place.

**What you should see.** The first time in a directory, Claude Code asks whether you trust the
folder. Answer yes. Then it shows an input field, and no warning of the harness.

At the start, Claude Code reads the installed `~/.claude/CLAUDE.md`. That file imports the core
working rules, `instructions/core.md`, and your tree instructions,
`instructions/research-tree.md`. A hook also compares the installed files with their sources.

**When it does not happen.** If your shell does not find `claude`, install Claude Code first, as
[Dependencies](dependencies.md#claude-code) says. If the session starts with a warning that
`~/.claude is behind its sources`, a source changed after the last install. End the session with
`/exit`, and do what [Daily use](daily-use.md#the-drift-warning-at-session-start) says. Step 8
shows this warning on purpose.

## Step 2: ask a question and watch the tool calls

Type a question about the package:

```text
What does this package export? Give each name with the file that defines it.
```

**Without a Julia package**, ask: `What does this repository hold? Name the files that matter
most.`

**What you should see.** The agent answers with tool calls before it writes its answer. It reads
files, for example `src/Example.jl`, and it searches for each name. Each tool call shows in the
session with its input and a short output. The output of each call goes into the context of the
session.

**When it does not happen.** If the agent answers with no tool call, its answer comes from general
knowledge. Ask it to read the files first and to name each file that it read.

## Step 3: answer a permission prompt

Ask for a small edit:

```text
Add the line "<!-- tutorial -->" at the end of README.md.
```

**What you should see.** The agent calls its edit tool. Before the edit, Claude Code shows the
change and asks whether to allow it. Read the change, then answer yes. The settings of the harness
decide which tool calls run with no prompt, which ask, and which Claude Code refuses. An edit of a
file asks, because no rule of the settings allows it. Answer no when you do not understand a
call, and tell the agent why.

**When it does not happen.** If the edit runs with no prompt, the session is in a mode that
accepts edits with no question. Claude Code shows the mode below the input field, and
`Shift+Tab` changes it. If the agent cannot find `README.md`, name a text file of your repository
in its place.

## Step 4: see a guard hook refuse a command

Ask for an edit through the shell:

```text
Replace "old" with "new" in README.md with sed -i.
```

**What you should see.** The agent tries the shell command `sed -i s/old/new/ README.md`. Before
the command runs, the guard hook `no-shell-file-write.py` refuses it and gives the agent this
message:

```text
Refused: sed -i s/old/new/ README.md

`-i` writes a file in a git working tree through the shell. A shell rewrite reports
success whether or not it matched anything, and BSD `sed` differs from GNU in ways that
corrupt silently on macOS.

Use the internal edit tools instead:

    Edit    one file, one region
    Write   a new file, or a full replacement you have read first

For a mechanical change over many files, use Kaimon's `rename_symbol` or `edit_code`:
both abort the whole batch untouched on one failure and return the diff.

A scratch file is not this rule: write it under `$TMPDIR` or `~/Research/.scratch/` and it
passes. A log redirect there, `> ~/Research/.scratch/<task>/run.log 2>&1`, passes too.
```

The agent reads the message and makes the edit with its edit tool, which asks you first, as in
step 3. A refusal is a normal event: it stops a common mistake and tells the agent what to do in
its place. A guard hook prevents accidents; it is not a security boundary.
[Guard hooks](components/hooks.md) describes each hook.

**When it does not happen.** The core instructions also tell the agent not to edit a file through
the shell, so the agent can use its edit tool at once and never try `sed`. That is the first layer
of control at work. To see the hook, ask: `Run exactly this command: sed -i s/old/new/ README.md`.
If the command runs and changes the file, the hooks of the settings are not installed: run
`harness settings install` in your own terminal, and do what
[Setup](setup-macos.md#harness-settings-install-apply) says.

## Step 5: let a skill load

Ask a question about performance, and name a function of your package:

```text
Is the function `solve` type stable?
```

**What you should see.** The request matches the description of the skill `julia-performance`,
so the session loads it, and the session shows its name. The skill tells the agent how to measure:
in a fresh Julia process, with the right tools, and with the traps that give a wrong number.

**When it does not happen.** The model chooses a skill from its description, so it can miss one.
Type `/julia-performance` and then the question: a skill also loads by its name.
[Skills](components/skills.md) lists each skill and the kind of request that loads it.

**Without a Julia package**, use the skill `wait-what`. It loads only by its name. After an answer
of the agent that you do not follow, type `/wait-what`. The agent then gives the answer again, with
more context and in short sentences.

## Step 6: give a long job to a sub-agent

Ask for the tests:

```text
Run the tests.
```

**What you should see.** The request matches the description of the agent `julia-test-runner`, so
the session starts it as a sub-agent. The session shows the start of the sub-agent and, at the
end, its short report: pass or fail for each testset, and the full text of each failure. The
sub-agent ran the suite in its own context, so the long test output never filled the context of
your session.

**When it does not happen.** If the session runs the tests itself, ask for the sub-agent by name:
`Use the julia-test-runner agent to run the tests.` [Agents](components/agents.md) lists the
sub-agents and their jobs.

**Without a Julia package**, ask the agent `reader` for a search:
`Use the reader agent to list each file that mentions README, with one line on each.` The
sub-agent searches and reads, and returns only the list.

## Step 7: review a change

Steps 3 and 4 changed `README.md`. Review the change before you keep it. In your own terminal, in
the repository, show the difference:

```bash
git diff
```

Then ask the agent for its own review:

```text
Review your change: show the diff, and say for each changed line why my request needs it.
```

**What you should see.** The agent shows the diff and gives a reason for each changed line. Each
line traces to your request. The core instructions tell the agent to touch only what the request
names, so a line with no reason is a defect.

**When it does not happen.** If the diff holds a line that you did not ask for, tell the agent to
remove it, and run `git diff` again. When you are done, undo the change of the tutorial in your
own terminal with `git restore README.md`.

**With a Julia package**, a change on a branch can also go to a pull request. The agent
`julia-pr-reviewer` then reviews it and posts its findings.

## Step 8: make a correction that lasts

When the agent does something wrong, you tell it in the session. The correction lasts for that
session only, because the next session starts with an empty context. To make it last, put it into
a file that every session reads. A fact about your own work goes into your tree instructions.

1. End the session with `/exit`.

2. Add a line to the file `instructions/research-tree.md` in the directory of your tree
   instructions. With the example profile, this command adds it:

   ```bash
   echo "Answer in short sentences." >> ~/Research/Environment/Agents/instructions/research-tree.md
   ```

3. Start a new session with `claude`. **What you should see:** a warning before the input field.
   The parentheses hold the source directories:

   ```text
   ~/.claude is behind its sources (…): an edit there is not installed. Run `harness install` to see the changes, then `harness install --apply`.
   ```

   The installed copy is behind its source: this is drift. The warning blocks nothing; the
   session uses the old installed files. End it with `/exit`.

4. Run the dry run of the install, and read its plan:

   ```bash
   harness install
   ```

   **What you should see:** among the lines of the plan are these two, and the last line gives
   the number of changes. The dry run exits 1, which means that it would change files.

   ```text
   ~/.claude/instructions/research-tree.md REPLACE
   ~/.claude/.harness-install.json    REPLACE
   2 change(s) to make.
   ```

   Then install the change:

   ```bash
   harness install --apply
   ```

   **What you should see:** the last line of the output is this one:

   ```text
   Restart Claude Code: its installed files changed, and a running session keeps the files it has read.
   ```

5. Start a new session with `claude`. **What you should see:** no warning, and short sentences in
   each answer.

**When it does not happen.** If the warning comes back, the install did not finish: run
`harness install` again and read its last line. If the agent ignores the new line, check that you
edited the source and not the installed copy in `~/.claude/`; the settings refuse an edit of an
installed copy from a session, and the next install overwrites it. A change of an agent, a skill or
a rule of the harness goes into its source in the checkout in the same way.
[Daily use](daily-use.md) describes this and the other work that comes back again and again.

## Next steps

- [Daily use](daily-use.md): a change of the settings, the leak check and the verbs for the whole
  research tree.
- [Concepts](concepts.md): the ideas behind each step of this tutorial.
- [The security model](security.md): what each layer of control stops, and what it does not.
- [Agents at work](agents-at-work.md): which agents start which sub-agents.
