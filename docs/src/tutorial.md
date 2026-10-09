# Tutorial: a first session

This tutorial is for a reader who is new to the harness and fairly new to coding agents. It
explains the words that the other pages use, installs the harness, and then walks through one
session with Claude Code. In the session you see the parts of the harness at work: the
instructions, the sandbox, a guard hook, a skill and a sub-agent.

You need a Mac, a Claude Code account, and a Julia package in a git repository to work on. The
examples use the package `~/Research/Packages/Example`; use your own package in its place. The
session costs tokens, which you pay.

## The words you need

A **coding agent** is a language model that works in your files and your terminal. You give it a
task in plain language. It reads files, runs commands and edits code to do the task, and it
reports what it did. Claude Code, OpenCode and oh-my-pi are coding agents. The harness calls each
of them a **frontend**.

| word | what it means |
|:--|:--|
| **session** | one conversation with the agent, from its start to its end. A new session starts with no memory of the last one |
| **context** | all the text that the agent holds in a session: the instructions, your messages, and the output of each tool call. It has a size limit, and a long output fills it |
| **tool call** | one action of the agent: read a file, edit a file, search, or run a shell command. The frontend shows each tool call |
| **permission prompt** | a question from the frontend before a tool call: may the agent do this? You answer yes or no |
| **sandbox** | an operating-system boundary around each shell command of the agent. It limits the files that a command can write and the hosts that it can reach |
| **instruction file** | text that the agent reads at the start of every session, for example `CLAUDE.md` |
| **rule** | an instruction file that loads only when the agent reads a matching file, for example a Julia source |
| **skill** | a packaged set of instructions for one kind of task. It loads when your request matches its description, or when you type `/<name>` |
| **sub-agent** | a second agent that the session starts for one task. It has its own context and returns a short report |
| **hook** | a program that the frontend runs at a fixed event, for example before each tool call. A hook can refuse the call |

## What the harness adds

Claude Code works without the harness. The harness gives it a configuration for research
software in Julia: instruction files, rules, skills, agents, guard hooks, and permission and
sandbox settings. The harness keeps the sources of this configuration in its repository, and the
`harness` command installs them:

```text
the checkout ~/Research/Harness           the installed layer ~/.claude/
  agents/, skills/, rules/, ...  ── harness install ──▶  agents/, skills/, rules/, ...
  settings/settings.proposal.json  ── harness settings install ──▶  settings.json
```

Claude Code reads the installed layer at the start of each session. So a change of a source
reaches a session only after the next install. [Architecture](architecture.md) describes the
layers, and [Components](components/agents.md) describes each part.

## Step 1: install the harness

Follow [Setup on macOS](setup-macos.md). It installs the dependencies, clones the repository,
makes your profile, and installs the configuration and the settings. Then check the result. Each
command must end as shown:

```bash
harness install            # 0 change(s) to make.
harness settings install   # the owned sections are identical — nothing to install
harness test               # ... cases, 0 wrong
```

The profile tells the harness where your research tree is: its key `repository_roots` names the
directories that hold your repositories, for example `~/Research/Packages`. Mark the tree as
trusted for Claude Code once, in your own terminal:

```bash
harness trust --apply
```

## Step 2: start a session

Go to your package and start Claude Code:

```bash
cd ~/Research/Packages/Example
claude
```

At the start, Claude Code reads the installed `~/.claude/CLAUDE.md`. That file imports the core
working rules (`instructions/core.md`) and your tree instructions
(`instructions/research-tree.md`). The `SessionStart` hook also compares the installed layer with
the sources. When a source changed since the last install, the session starts with a warning
such as this one:

```text
~/.claude is behind its sources (...): an edit there is not installed.
Run `harness install` to see the changes, then `harness install --apply`.
```

The warning blocks nothing. [Daily use](@ref "The drift warning at session start") says what to
do.

## Step 3: ask a question and watch the tool calls

Type a question about the package:

```text
What does this package export? Give each name with the file that defines it.
```

The agent answers with tool calls. It reads `src/Example.jl`, searches for each name, and then
writes its answer. Each tool call shows in the session, with its input and a short output.

Some tool calls ask for permission first. The settings decide which calls run with no prompt,
which ask, and which the frontend refuses. Read each prompt before you answer. Answer no when
you do not understand the call, and tell the agent why. [The security model](security.md)
describes the layers of control.

Each shell command runs in the sandbox. A command that writes outside the allowed directories,
or that connects to a host that is not allowed, fails. The agent sees the failure and must find
another way.

## Step 4: see a guard hook refuse a command

Ask for an edit through the shell:

```text
Replace "old" with "new" in README.md with sed.
```

The agent tries `sed -i s/old/new/ README.md`. Before the command runs, the guard hook
`no-shell-file-write.py` refuses it and gives the agent this message:

```text
Refused: sed -i s/old/new/ README.md

`-i` writes a file in a git working tree through the shell. A shell rewrite reports
success whether or not it matched anything, and BSD `sed` differs from GNU in ways that
corrupt silently on macOS.

Use the internal edit tools instead:

    Edit    one file, one region
    Write   a new file, or a full replacement you have read first
```

The agent reads the message and makes the edit with its `Edit` tool. A refusal is a normal
event: it stops a common mistake and tells the agent what to do instead. A guard hook prevents
accidents; it is not a security boundary. [Guard hooks](components/hooks.md) describes each
hook.

## Step 5: let a skill load

Ask a question about performance, and name a function of your package:

```text
Is the function `solve` type stable?
```

The request matches the description of the skill `julia-performance`, so the session loads it.
The model makes this choice from the description, and `harness skill-triggers` tests it with
queries such as this one. The skill tells the agent how to measure: in a fresh Julia process,
with the right tools, and with the traps that give a wrong number. Without the skill, the agent
answers from general knowledge.

You can also load a skill by name. Type `/julia-performance` and then the question.
[Skills](components/skills.md) lists each skill and the kind of request that loads it.

## Step 6: give a long job to a sub-agent

Ask for the tests:

```text
Run the tests.
```

The request matches the description of the sub-agent `julia-test-runner`, so the session gives
the job to it. If it does not, ask for the sub-agent by name. The sub-agent runs the suite in its
own context, and returns a short report: pass or fail for each testset, and the full text of each
failure. The long test output stays out of the context of your session, so the session keeps its
room for the work.

The harness has sub-agents for other long or wide jobs too: a review of a pull request, a search
of the literature, a check of the CI results. [Agents](components/agents.md) lists them.

## Step 7: make a correction last

When the agent does something wrong, tell it in the session. The correction lasts for that
session only. To make it last, put it into a file:

- A fact about your own research tree goes into your tree instructions, the file
  `instructions/research-tree.md` in the directory that the profile key `tree_agents` names.
- A change of an agent, a skill, a rule or an instruction of the harness goes into its source
  in the checkout, never into its copy in `~/.claude/`.

Then install the change, and start a new session:

```bash
harness install
harness install --apply
```

[Daily use](daily-use.md) describes this and the other work that comes back again and again.

## Next steps

- [Daily use](daily-use.md): the drift warning, a change of the settings, the leak check and the
  verbs for the whole research tree.
- [The security model](security.md): what each layer of control stops, and what it does not.
- [Components](components/agents.md): each agent, skill, rule, hook and script.
- [The `harness` command](harness-command.md): every verb and its flags.
