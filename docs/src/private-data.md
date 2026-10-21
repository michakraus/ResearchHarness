# Private data across machines

The harness is public, but a working installation holds private data: your accounts, your
machines, your own instructions, the memory of your sessions. This page says what is private,
how the harness keeps it out of the public repository, and how it reaches each of your machines,
physical or virtual.

## What is private

| data | where it is | what it holds |
|:--|:--|:--|
| the profile and its files | `~/.config/research-harness/` | `profile.toml`, every value that names a person, an institution or a machine; `models.toml`, the model of each tier; `providers.toml`, `network.toml` and `repositories.toml`. [Adapting the profile](profile.md) names each key |
| the tree instructions | the directory that the profile key `tree_agents` names | your own instruction text about your research tree, and your own rules and skills |
| the memory and the plans | `~/.claude/projects/<memory_project>/memory/` and `~/.claude/plans/` | what Claude Code keeps from one session for the next. [Research memory](memory.md) describes it |
| the credentials | `~/.ssh/`, the logins of `gh` and `glab`, the API keys | the keys that let a machine reach your accounts |

The first three are text that the harness reads and installs. The credentials are not: the
harness never reads, copies or installs a credential. The settings template denies a session a
read of `~/.ssh/`, `~/.gnupg/`, `~/.config/api-keys/` and the token file of `gh`, both to the file
tools and to the sandbox.

## Keep private data out of the repository

A source of the harness names no person, no machine and no repository of your tree. Where a
source needs such a value, it is a template that names a key of the profile as `{key}`, and a
subcommand renders it with your profile before it uses it. So the repository holds the keys, and
your profile holds the values.

Two checks keep the values out:

- **`harness leaks`** searches every tracked file, its path, and the templates rendered with the
  example profile. It looks for each string of the profile's `leak` list, each account of `org`,
  and the name of each directory below `repository_roots`.
- **gitleaks** looks for secrets and home paths.

The pre-push hook of the harness runs both before a push to `main`, and refuses the push on a hit.
CI runs gitleaks on every push. CI has no profile, so it cannot search for your private strings:
only the hook on your machine does. [The security model](security.md#the-mechanisms) gives the
limits of this gate, and [Development](development.md#the-pre-push-hook) gives the two checks in
detail.

## One profile for every machine

One profile serves every machine of one user. A value that starts with `~` means the home
directory of the machine that reads it. The key `template_host` names one machine, the template
host, and the value of `autocommit_branch` then follows from the host name of each machine. So you
write the profile once and copy it to each machine unedited.
[One profile for every machine](profile.md#one-profile-for-every-machine) gives the rules.

## Synchronise across machines

Three mechanisms carry the private data to another machine. Each one is git, and each one is
optional.

### The dotfiles kit

The dotfiles kit, `examples/dotfiles/`, is a chezmoi source with placeholder data. You copy it
into a private repository of your own with `harness dotfiles-kit`, and chezmoi applies that
repository on each machine. The copy carries:

- the files of `~/.config/research-harness/`: the profile and the model, provider, network and
  repository tables;
- the public key that signs, in `~/.config/git/allowed_signers`;
- the table of your machines, `.chezmoidata/machines.toml`, with the commit of the harness that
  every machine runs;
- the setup scripts: the tool check; the clones of the remotes of `machines.toml`, such as
  `~/.claude`, the harness and, in the example, the repository of the tree instructions; Julia;
  the harness at its commit, with `harness install --apply`; and the background jobs;
- the command `dotfiles` and its scripts.

One machine signs. Every other machine applies a change only when each new commit carries a good
signature of a key that it already trusts, so a change that nobody signed never reaches a machine.
The harness moves only when the commit of the harness in `machines.toml` changes, so each machine
runs a reviewed commit, not the newest one.
[The `dotfiles` command](dotfiles-command.md#the-update-path) gives the update path, and
[Start a private copy](dotfiles-command.md#start-a-private-copy) the steps.

### The memory and the plans

`~/.claude` is a git repository with a private remote. The job `claude-autocommit` commits the
plans and the memories of `~/.claude` every 15 minutes, and pushes them to the branch of
`autocommit_branch`. That branch is `main` on the template host, and `memory/<short host name>` on
each other machine. So no two machines push to one branch, and the memory of the template host is
the memory that the others start from.
[Jobs and configuration](components/other.md#claude-autocommit-claude-autocommit-test-jl-and-claude-autocommit-plist)
describes the job.

### The tree instructions and the repositories

The tree instructions are a directory of a private repository, in the example
`~/Research/Environment`. The repositories of the research tree each have their own remote.
`harness clone` clones them on a new machine, and `harness repos sync` pulls and pushes them.
[The research tree](research-tree.md#clone-sync-and-trust) describes both.

## The limits

- **The credentials stay on each machine.** A new machine needs its own SSH key and its own logins
  of `gh` and `glab` before its first clone. [A new machine](dotfiles-command.md#a-new-machine)
  gives the steps.
- **The leak check knows only the strings that you give it.** A private string that is not in the
  `leak` list, and not a name of your tree, passes it.
- **The kit installs no tool.** Its tool check names a missing tool and stops the first apply.
- **The installed copies are not synchronised.** Each machine writes its own with
  `harness install --apply`, from its own checkout of the harness. The kit runs the install when
  the commit of the harness in `machines.toml` changes.
