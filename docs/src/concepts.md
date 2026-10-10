# Introduction

This page explains the ideas behind Research Harness. It is for a reader who has not used the
harness and is fairly new to [coding agents](#coding-agent). You need no Julia to read it. Each section ends with a
note on how its idea carries to another language. The [glossary](#glossary) at the end of the page
gives a short entry for each word that the other pages use.

## What a coding agent is

A [coding agent](#coding-agent) is a language model that works in your files and your terminal.
You give it a task in plain language. It reads files, runs commands and edits code to do the
task, and then it reports what it did. The program that you talk to is the
[frontend](#frontend): Claude Code, OpenCode and oh-my-pi are three frontends.

One conversation with the coding agent is a [session](#session). The coding agent holds all the
text of a session in its [context](#context): its instructions, your messages, and the output of
each action. The context has a size limit, and a new session starts with an empty context. So the
coding agent forgets each session when it ends.

Each action of the coding agent is a [tool call](#tool-call): read a file, edit a file, search, or
run a shell command. The frontend shows each tool call in the session. Before some tool calls, it asks
you first: this is a [permission prompt](#permission-prompt).

**In another language.** Nothing in this section depends on Julia. The three frontends work on
code in any language.

## What a harness adds

A coding agent with no configuration knows only what the model learned and what it reads in the
session. It does not know your conventions, your tools or your traps. A harness is the
configuration around the coding agent. It gives the coding agent instructions, procedures for
common tasks, helpers for long jobs, and limits on what it can do.

Research Harness keeps this configuration as source files in one repository. The command
`harness` [installs](#install) the sources into the configuration directory of each frontend, and
checks the result. These are the parts that it adds:

- **Instructions.** An [instruction file](#instruction-file) loads at the start of every session.
  A [rule](#rule) loads only when the coding agent reads a matching file, for example a Julia
  source.
- **[Skills](#skill).** A skill is a procedure for one kind of task, for example a performance
  measurement. It loads when your request matches its description.
- **[Agents](#agent).** An agent of the harness is a helper with its own task, model and tools.
  The session starts it as a [sub-agent](#sub-agent) for a long or a wide job.
- **[Hooks](#hook).** A hook is a program that the frontend runs at a fixed event. The guard hooks
  of the harness refuse unsafe shell commands before they run.
- **Settings.** The permission settings decide which tool calls run, which ask you, and which the
  frontend refuses. They also turn on the [sandbox](#sandbox) of Claude Code.

A research project needs these more than most projects. It has many repositories: packages,
experiments, papers. Each has the same conventions, and a session in each must keep them. Its
test suites and numerical runs take a long time, and their output fills the context. Its results
must be correct and reproducible, so a wrong edit that passes in silence is expensive. And its
files name people, institutions and machines that must not go into a public repository.

**In another language.** The idea is the same for any language: write the conventions down once,
and let them load where they apply. Only the content of some rules, skills and agents is for Julia.

## The three layers

An installation comes from three layers. Two of them are private, so that the public repository
names no person and no machine.

<LayersFigure />

*The harness, the [profile](#profile) and the [tree instructions](#tree-instructions).*
`harness install` reads the three layers
and writes the configuration of each frontend.

- **The harness** is this repository. It is public and the same for every user. It holds the
  agents, the skills, the rules, the core instruction file, the guard hooks and the settings
  template.
- **The [profile](#profile)** is private and stays on your machine. It holds every value that
  names a person, an institution or a machine: your home directory, your accounts on GitHub, the
  strings that must never go into the repository. Beside it, the model tables give the model of
  each [tier](#tier) for each frontend.
- **The [tree instructions](#tree-instructions)** are private too. They are a directory of your
  own instruction text: the facts about your research tree, and your own rules and skills if you
  want them.

To [install](#install) is to copy the sources of the three layers into the configuration
directory of each frontend. You edit a source, never its installed copy: the next install
overwrites the copy. When a source changes after the last install, the installed copy is behind
it. This is [drift](#drift). A hook at the start of each Claude Code session warns about it.

[Architecture](architecture.md#the-three-layers) describes the three layers in detail, and
[Adapting the profile](profile.md) names each value of the profile.

**In another language.** The split works for any language: keep the shared configuration public,
and the personal values in a private file that a template reads.

## The parts of the harness

The figure below shows the harness from another side: where the work is, what the harness
supplies, and which programs read it.

<OverviewFigure />

*The harness and its three layers.* These are not the three layers of the section above.

- **The research tree** is where the work is: the directories that hold your repositories and
  your notes. The figure shows the tree of the harness's author, as an example: a library of
  papers, a store of knowledge, the packages, the experiments, the projects and the papers. Your
  tree holds your own directories.
- **The components** are what the harness supplies: the agents, skills, commands, rules, guard
  hooks, git hooks and workflows, scripts and settings. [Components](components/agents.md)
  describes each one.
- **The frontends** read the components. Each frontend gets its own configuration directory:
  `~/.claude/` for Claude Code, `~/.config/opencode/` for OpenCode and `~/.omp/agent/` for
  oh-my-pi.

**In another language.** The components are the same for any language. Of the eight kinds, the
git hooks, the workflows and most scripts are for Julia packages.
[Dependencies](dependencies.md#julia-and-its-packages) says what needs Julia.

## The layers of control

The harness controls a tool call in four layers. Each layer stops a different kind of mistake,
and only one of them is a security boundary.

<ControlFigure />

*The layers of control around one tool call.* The instructions guide the agent. The checks
before the call refuse it, ask you, or let it run. A shell command then runs inside the sandbox.

1. **The instructions** tell the agent what to do and what to avoid. The model follows them most
   of the time, but nothing forces it. They are guidance, not control.
2. **The permission settings** are lists of patterns. A tool call that matches a `deny` pattern
   does not run. A call that matches an `ask` pattern shows you a permission prompt. Read the
   prompt before you answer, and answer no when you do not understand the call. A pattern
   matches the text of a call, so a command inside a string can get past it.
3. **The guard hooks** read each shell command before it runs. A hook refuses a command of a
   known unsafe shape and tells the agent what to do in its place, for example to edit a file
   with the edit tool and not with `sed -i`. A hook prevents accidents. A session that tries to
   get past it can do so.
4. **The sandbox** of Claude Code is a boundary of the operating system around each shell
   command. It limits the files that a command can write and the hosts that it can reach,
   whatever the command text is. It is the only security boundary of the four. It does not wrap
   the edit tools of the frontend, which the permission settings control. OpenCode has no
   sandbox.

[The security model](security.md) describes what each layer stops and what it does not.

**In another language.** The four layers do not depend on the language. A hook that refuses a
command shape is a short program in any language; the guard hooks of the harness are Python.

## The division of work among agents

You talk to one session. The session can start a sub-agent for one job. The sub-agent works in
its own context and returns a short report, so the long output of its job never fills the context
of your session. The harness gives the sub-agents three kinds of jobs:

- **A long job**, such as a test suite: the sub-agent runs it and returns pass or fail with the
  failures.
- **A wide job**, such as a change across many repositories: one sub-agent for each, and one
  verdict for each.
- **A bounded diagnosis**, such as a package that does not load: the sub-agent reports the cause.

Some work goes to two agents that check each other. In the builder-critic loop of the skill
`build-part`, one agent builds a change and a second agent judges it. The critic has not seen how
the builder worked, so it reads the result with fresh eyes.

Each agent names a tier, `large`, `medium` or `small`, and the model tables choose the model of
each tier. A larger model is better at hard work and costs more. An agent can also name an
[effort](#effort): how long the model thinks before it answers. [Agents at work](agents-at-work.md)
shows which agents start which, with their models and efforts.

**In another language.** The agents that run tests, review a pull request or diagnose a load
error are for Julia. The same division carries to any language: a sub-agent that runs the test
suite of your language and returns only the verdict.

## Glossary

### Coding agent

A language model that works in your files and your terminal. It reads, runs commands and edits
code to do a task in plain language. Claude Code, OpenCode and oh-my-pi are coding agents.

### Frontend

The program of a coding agent that you talk to, and that runs its tool calls. The harness
configures three frontends: Claude Code, OpenCode and oh-my-pi.

### Session

One conversation with a coding agent, from its start to its end. A new session starts with no
memory of the last one.

### Context

All the text that the agent holds in a session: the instructions, your messages and the output of
each tool call. It has a size limit, and a long output fills it.

### Tool call

One action of the agent: read a file, edit a file, search, or run a shell command. The frontend
shows each tool call.

### Permission prompt

A question of the frontend before a tool call: may the agent do this? You answer yes or no. The
permission settings decide which tool calls ask.

### Sandbox

A boundary of the operating system around each shell command of a Claude Code session. It limits
the files that a command can write and the hosts that it can reach.

### Instruction file

A text file that the agent reads at the start of every session, for example `CLAUDE.md`. The core
instruction file of the harness is `instructions/core.md`.

### Rule

An instruction file that loads only when the agent reads a matching file, for example a Julia
source. Its `paths:` field names the files that it matches.

### Skill

A procedure for one kind of task. It loads when your request matches its description, or when you
type `/` and its name.

### Agent

A helper with its own task, model, effort and tools. Its file is in `agents/`. A session starts
it as a sub-agent.

### Sub-agent

An agent that a session starts for one job. It has its own context and returns a short report to
the session.

### Hook

A program that the frontend runs at a fixed event: before a tool call, or at the start of a
session. A hook before a tool call can refuse the call.

### Tier

The size of the model that an agent or a skill asks for: `large`, `medium` or `small`. The model
tables give the model of each tier for each frontend.

### Effort

How long the model thinks before it answers. An agent names it in its `effort:` field; with no
field, it gets the effort of the session.

### Profile

The private file of your values: your home directory, your accounts and the strings that must not
go into the repository. Its default path is `~/.config/research-harness/profile.toml`.

### Tree instructions

A private directory of your own instruction text about your research tree. The profile names it,
and `harness install` installs it beside the sources of the harness.

### Install

To copy the sources of the harness, the profile's values and the tree instructions into the
configuration directory of each frontend. `harness install` shows what it would change, and
`harness install --apply` makes the change.

### Drift

The state in which an installed copy is behind its source, because the source changed after the
last install. A hook at the start of each Claude Code session warns about it.
