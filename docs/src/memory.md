# Research memory

::: info In development
The research memory is the least complete feature of the harness. This page describes the parts
that exist.
:::

A session starts with an empty context, and it forgets everything when it ends. Research work
takes weeks, and one task runs over many sessions. So what one session learns must go into a file
that a later session reads. The research memory is the set of these files: what each holds, who
writes it, and when a session reads it.

## The kinds of memory

| kind | what it holds | who writes it | when a session reads it | how long it lasts |
|:--|:--|:--|:--|:--|
| the instruction files: `instructions/core.md`, `CLAUDE.md` and the tree instructions | the conventions that apply in every session | you, as a source of the harness or of the tree instructions, then `harness install` | at the start of every session | until you change it |
| the `CLAUDE.md` of a directory | the conventions of one directory of the tree | you | in Claude Code, when a session works in its directory | until you change it |
| a rule | the conventions of one kind of file | you, then `harness install` | when the agent reads a file that the rule's `paths:` matches | until you change it |
| a skill | the procedure of one kind of task | you, then `harness install` | when a request matches its description | until you change it |
| the project memory | a fact that one session learned and a later one needs: a preference, a trap of one repository, a pointer to a resource | the agent, during a session | its index at the start of each Claude Code session in the tree; a memory file when the agent reads it | until the agent or you delete it |
| a task file | the plan of one task: its parts, the state of each part, the decisions and the open questions | you and the session; [`plan-parts`](components/skills.md#plan-parts) writes the parts table and the specs, and [`build-part`](components/skills.md#build-part) the state of each part | when a session works on the task | until the task is done |
| the knowledge vault | what is established: facts, methods and measurements, with links between the notes | you and the session | when a session reads a note | permanently |
| `CHANGELOG.md` and `KNOWN_ISSUES.md` | the history of one repository, and its open defects with their evidence | the session, [`changelog-scribe`](components/agents.md#changelog-scribe), and the builders of a part | when a session reads the file | permanently |

The first four are instructions: text that tells the agent what to do. They are sources, so each
one has a version, a review and a diff. The other four are records: text that says what is true or
what happened. A session reads a record only when it opens the file, so a record costs no context
in a session that does not need it.

The project memory is Claude Code's auto memory. The profile key `memory_project` gives its
directory, `~/.claude/projects/<memory_project>/memory/`, so every session in the tree shares one
memory, whatever the path of the tree on the machine. Each memory is one file, and the file `MEMORY.md` is its index. The
harness gives the project memory to Claude Code only.

## Where a fact belongs

A fact that you tell a session lasts for that session only. Put it into the narrowest file that
loads when the fact applies:

- a fact for every session, whatever the task: an instruction file;
- a fact about one kind of file: a rule;
- a fact about one directory: that directory's `CLAUDE.md`;
- a fact about your tree and no other: the tree instructions;
- a procedure for one kind of task: a skill;
- the state of one task: its task file;
- an established result: a note of the vault;
- what changed, and why: `CHANGELOG.md`;
- a fact that a later session needs and that no file above loads: the project memory.

Keep each fact in one place. A fact in two files goes out of date in one of them. The rule
[`instruction-files`](components/rules.md#instruction-files) gives the layers of the instruction
files, and step 8 of the tutorial,
[Make a correction that lasts](tutorial.md#step-8-make-a-correction-that-lasts), moves one
correction into a file from the start to the end.

## Keep the memory correct

A memory that is false is worse than none, because a later session acts on it. These checks find
text that a later change made false:

- **The present tense.** An instruction file says what is true, in the present tense, and holds
  no history. The rule [`instruction-files`](components/rules.md#instruction-files) requires it,
  and the audit script `tense-lint.jl` finds each word that dates a text. The history goes into
  `CHANGELOG.md`.
- **The structure of the notes.** [`harness wiki-lint`](harness-command.md#wiki-lint) checks the
  links, the paths and the line citations of the vaults, and the paths, the line citations and the
  schema of the task files, and
  [`pre-commit-wiki`](components/githooks.md#pre-commit-wiki) runs it before each commit there.
- **The citations of the instructions.** The audit script `citations.jl` checks that each path,
  command, flag and agent name that an instruction file cites exists. The audit scripts are in
  [Scripts](components/scripts.md#the-audit-scripts).
- **The installed copies.** The drift warning at each session start says when an installed
  instruction file is behind its source:
  [Typical use](daily-use.md#the-drift-warning-at-session-start).

## Across machines

The job `claude-autocommit` commits the project memory and the plans of `~/.claude`, and pushes
them to a branch of each machine. The instruction files and the records are in git repositories.
[Private data across machines](private-data.md#synchronise-across-machines) describes both.
