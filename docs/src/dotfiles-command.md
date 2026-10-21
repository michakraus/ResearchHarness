# The `dotfiles` command

The dotfiles kit of the harness, `examples/dotfiles/`, is a chezmoi source with placeholder data.
It keeps a private chezmoi source signed and applied on several machines, and it sets each machine
up: the tool check, the clones, Julia, the harness at a pinned commit, and the jobs of the harness.
On each machine it installs the command `dotfiles` and the scripts that `dotfiles` runs, in
`~/.local/bin`.

The kit is optional. The setup pages for [macOS](setup-macos.md#dotfiles-optional) and
[Linux](setup-linux.md#dotfiles-optional) work without it.

The harness never installs these scripts itself. The scripts check and move the pin of the
harness, so the checker must not come from the thing that it checks. You copy the kit into a
private repository with [`harness dotfiles-kit`](harness-command.md#dotfiles-kit), and chezmoi
applies that repository on each machine. [Start a private copy](#start-a-private-copy) gives the
steps.

## Synopsis

```text
dotfiles update
dotfiles check [--full]
dotfiles merge <number | branch>
dotfiles --help
```

## Description

`dotfiles` is the one front door to the dotfiles scripts. Each subcommand runs the script
`dotfiles-<subcommand>` beside it in `~/.local/bin`, which does the work and asks its own
questions:

| subcommand | runs | where |
|:--|:--|:--|
| [`update`](#dotfiles-update) | `dotfiles-update` | every host |
| [`check`](#dotfiles-check) | `dotfiles-check` | every host |
| [`merge`](#dotfiles-merge) | `dotfiles-merge` | the template host only |

`dotfiles --help` prints the three subcommands and where each one runs. No subcommand, a
subcommand that is not in the list, or a `merge` without exactly one argument prints the usage
line and exits 2.

The *template host* is the one machine that signs: the key `template_host` of
`.chezmoidata/machines.toml` names it. Only it receives `dotfiles-merge` and git's
`user.signingkey`.

## Subcommands

### `dotfiles update`

```text
dotfiles update
```

Brings the applied source `~/.local/share/chezmoi` to `origin/main`, and applies it. It replaces
`chezmoi update` on every host. It stops when standard input is not a terminal. Then it runs
`git fetch`, and checks every commit on the first-parent path from `HEAD` to `origin/main`, as
[The update path](#the-update-path) says. When each commit passes, it merges `--ff-only`, shows
`chezmoi diff`, asks `y/N`, and applies on `y`. A check that fails names each commit that fails,
merges nothing and applies nothing: `HEAD` stays where it was.

An answer other than `y` or `Y` applies nothing, and the source stays at the merged commit. So
the next `dotfiles update` finds nothing new. To review the change again, run `chezmoi diff` and
then `chezmoi apply` yourself.

[The review](#the-review) must be read to its end. When you quit the pager early, it stops before
the question, applies nothing, and prints one line:

```text
dotfiles-update: you quit the review early; the source is at <commit> and nothing is applied. Run chezmoi diff, read it to its end, then run chezmoi apply.
```

**Exit status:** 0 when nothing is new, or after the question, whatever the answer; 1 when
standard input is not a terminal, when the check fails: a commit without a good signature by a
listed key, an `origin/main` that is not a fast-forward of `HEAD`, or an `allowed_signers` that is
missing or lists no key, and when you quit the review early. When `git`, `chezmoi` or the pager
fails, it stops with the status of that command.

**Reads:** `~/.config/git/allowed_signers` as it is applied. **Writes:** the source
`~/.local/share/chezmoi`, and, after `y`, the files that chezmoi applies.

**Where to run it:** in your own terminal, on every host. A session has no terminal for the
question, and the [sandbox](security.md) does not let it write the source.

### `dotfiles check`

```text
dotfiles check [--full]
```

Checks the setup of this machine. It prints one line for each check in the form of
[`harness doctor`](harness-command.md#doctor), `PASS`, `WARN`, `FAIL` or `SKIP` with the name of
the check and a detail, then a count line. The checks, in order:

- `harness doctor`, with `--full` when it is given; its check lines pass through;
- `chezmoi verify --exclude=scripts` passes, and `chezmoi diff --exclude=scripts` is empty;
- the head of `~/.local/share/chezmoi` carries a good signature by a key of the applied
  `allowed_signers`, as `dotfiles update` checks each commit;
- the head is `origin/main` as the last fetch saw it, and `WARN` when it is behind;
- the `HEAD` of `~/Research/Harness` is `harness_commit`, or contains it on the template host;
- each code file of the kit in the source equals the kit of the harness at `harness_commit`. A file
  that differs is a `WARN`, not a `FAIL`, because a machine on an older pin has an older kit. The
  check is `SKIP` when the harness checkout lacks that commit or that commit has no kit;
- with `--full`, Revise loads on each `X.Y` channel of the host's `julia_channels`, and the
  host's GPU package (`Metal`, `CUDA` or `AMDGPU`) says that it is functional.

It is read-only: it needs no terminal, asks nothing, fetches nothing and writes no file. With
`--full`, Julia can still precompile a stale package into its depot.

| option | meaning |
|:--|:--|
| `--full` | also run `harness doctor --full`, and the checks of Julia |

**Exit status:** 1 when a line is `FAIL`, else 0. A `WARN` or a `SKIP` does not count. 2 on a
usage error.

**Reads:** the source, `~/.config/git/allowed_signers`, the harness checkout
`~/Research/Harness`, and `examples/dotfiles/kit.toml` at `harness_commit`. **Writes:** nothing.

**Where to run it:** in a plain terminal, on every host, after each apply. In a session, the
sandbox can refuse a `chezmoi` or `julia` command: a command that does not pass there is `SKIP`,
as in `harness doctor`.

### `dotfiles merge`

```text
dotfiles merge <number | branch>
```

Merges a reviewed branch into `main` of the source. A number, digits only, is a pull request or a
merge request of the source's `origin`: `gh` names its branch for an `origin` on `github.com`,
and `glab` for any other host. A request that is not open stops `dotfiles merge` before the
merge. Any other argument is a branch name.

Then `dotfiles-merge <branch>` stops when standard input is not a terminal, when the host data
gives no `signing_key`, when the source has local changes, untracked files included, and when its
`HEAD` is not `main` at `origin/main`. It prints `git log --first-parent main..origin/<branch>`
and the diff `main...origin/<branch>`, and asks `y/N`. On `y`, it makes a `--no-ff` merge signed
by the `signing_key`, checks the merge as `dotfiles update` checks a commit, and pushes `main`.
Then it shows `chezmoi diff`, asks again, and applies on `y`.

A conflict or a failed signature leaves no merge. A merge that fails the check is undone. A
refused push leaves the local merge, names it, and applies nothing.

Each part of [the review](#the-review) must be read to its end. When you quit the pager of the log
or the diff early, it stops before the first question, and nothing is merged, signed or pushed.
When you quit the pager of `chezmoi diff` early, the merge is already pushed, and nothing is
applied. Each stop prints one line:

```text
dotfiles-merge: you quit the review early; nothing is merged. Run dotfiles merge <branch> again and read the review to its end.
dotfiles-merge: you quit the review early; the merge <commit> is pushed and nothing is applied. Run chezmoi diff, read it to its end, then run chezmoi apply.
```

**Exit status:** 0 when `main` already contains the branch, when the answer to the first question
is not `y`, or after the second question, whatever the answer; 1 when a stop above applies, on a
host without `dotfiles-merge`, when the request is not open or not found, when the remote has no
such branch, when the merge, its signature or its check fails, when the push is refused, and when
you quit the review early; 2 on a usage error.

**Reads:** `~/.config/git/allowed_signers`, and the `signing_key` and `sk_provider` of the host
data, which chezmoi writes into the script when it applies it. **Writes:** the source, the branch
`main` of its `origin`, and, after the second `y`, the files that chezmoi applies.

**Where to run it:** in your own terminal, on the template host only, after you read the pull
request or the merge request. A signing key in hardware asks for a touch: touch it only during a
`dotfiles merge` of your own.

```bash
dotfiles merge 12              # pull request or merge request 12 of the origin
dotfiles merge kit-update      # the branch kit-update
```

## The review

`dotfiles update` and `dotfiles merge` show each part of the review, the log, the diff and
`chezmoi diff`, in git's pager: `GIT_PAGER`, then `core.pager`, then `PAGER`, then `less`, with
`LESS=FRX` and `LV=-c` when they are not set, as git runs it. The pager setting of chezmoi does
not count here.

A pager that quits before the command has written all of its output breaks the pipe, and the
script stops with the line that the subcommand names. A review that fits in the pipe's buffer,
about 64 KB, is written before you quit, so quitting it early does not stop the script. With
`LESS=FRX`, `less` quits by itself at the end of a review that fits on one screen; a `LESS`
without `F`, such as the `-R` that oh-my-zsh sets, waits for `q` at the end.

## The update path

A Git host does not always let you refuse an unsigned commit, so each machine checks the
signatures itself. A machine applies `main` only when every commit on the first-parent path from
its applied `HEAD` to `origin/main` carries a good signature, `%G?` is `G`, by a key of its
`~/.config/git/allowed_signers`, **as applied before the update**. An incoming commit that adds a
key to the source's copy of `allowed_signers` does not make that key count.

- **Only an SSH signature counts.** The check reads `%G?` and the principal, not only the exit
  status of `git verify-commit`. An OpenPGP or an X.509 signature never gives `G` here, whichever
  keys the host's `gpg` trusts.
- **One machine signs.** The template `.chezmoitemplates/gitconfig-signing`, which your
  `.gitconfig` template includes, writes the signing settings of git. With it, only the template
  host's `~/.gitconfig` names the key in `user.signingkey`. Every host has `gpg.format = ssh` and
  `gpg.ssh.allowedSignersFile`, and no host has `commit.gpgsign`, so a commit is signed only with
  an explicit `-S`.
- **A key that needs a provider**, such as a key in the Secure Enclave of a Mac, gets its
  `SSH_SK_PROVIDER` from `sk_provider` in `dotfiles merge` alone. No other file of the kit sets it,
  so a `git commit -S` that a session starts finds no provider and cannot sign. The prompt of such
  a key cannot name the signature that it is for; the line before it,
  `dotfiles-merge: <key> now signs the merge of origin/<branch> (<commit>) into main.`, names it.
- **The harness moves only with the source.** `harness_commit` in `.chezmoidata/machines.toml` is
  the commit of the harness for every machine. When it changes, the harness script of
  `.chezmoiscripts/` checks out that commit in `~/Research/Harness` and runs
  `harness install --apply`. On the template host, where `~/Research/Harness` is the development
  checkout, it moves no checkout, and stops when `HEAD` does not contain the commit. So a machine
  moves to a new harness only through a reviewed and signed change of that line.

### A new machine

A new machine gets its `allowed_signers` by hand, before `chezmoi init`. Write the line of the
signing key into `~/.config/git/allowed_signers`, in the form of the ALLOWED SIGNERS section of
`ssh-keygen(1)`:

```text
owner@example.org namespaces="git" ssh-ed25519 <the public key>
```

Compare its fingerprint with the fingerprint that the README of your private copy names. On the
template host, `ssh-keygen -l -f` of the key's `.pub` file prints it.

`chezmoi init` clones your private repository before chezmoi applies any `~/.gitconfig`, and the
first apply clones the remotes of `[remotes]`. So git needs credentials for each of their hosts
first: an SSH key that the host accepts, for an SSH URL, or a credential helper, for an HTTPS URL.
A helper goes into `~/.gitconfig`, such as `gh auth login` and then `gh auth setup-git` for a host
of `gh`, or, for a host of `glab`:

```sh
glab auth login --hostname <host>
git config --global credential.https://<host>.helper '!glab auth git-credential'
```

When your `.gitconfig` template writes the same helper, the first `chezmoi diff` shows
`~/.gitconfig` as replaced.

Then run `chezmoi init <repository>` without `--apply`, and check the head of the source. No
`~/.gitconfig` names `allowed_signers` before the first apply, so the command names it:

```sh
git -C ~/.local/share/chezmoi -c gpg.ssh.allowedSignersFile="$HOME/.config/git/allowed_signers" \
    -c gpg.openpgp.program=false -c gpg.x509.program=false log -1 --format='%G? %GS'
```

It must print `G` and the principal, such as `G owner@example.org`. Then read the whole
`chezmoi diff`, and run `chezmoi apply`. Before any file changes, the apply runs the tool check
of the kit: when a tool is missing, it names the tool and stops the apply; it installs nothing.
It requires `git`, `zsh`, `curl`, `python3` 3.11 or later, `lsof`, `rtk`, `juliaup`, `gh` and
`glab` on every host, and `bwrap`, `socat` and `secret-tool` on Linux. So a host needs `glab` even
when all its remotes are on GitHub, and `gh` even when none is: install both, or the first apply
stops. From then on, the machine updates with `dotfiles update` only.

### The first signed commit

`dotfiles merge` is not on any machine before the first apply, so the first signed commit of
`main` is made by hand, on the template host, in a terminal, in your clone. Write the line of your
key into `~/.config/git/allowed_signers`, as [A new machine](#a-new-machine) shows, and set the
three lines that the template writes once it is applied:

```sh
git config --global user.signingkey ~/.ssh/<your signing key>
git config --global gpg.format ssh
git config --global gpg.ssh.allowedSignersFile ~/.config/git/allowed_signers
```

In a new private copy, `main` has no commit yet: commit the kit on `main`, signed. In a copy whose
`main` exists, bring `main` up to `origin/main`, and merge the branch, signed:

```sh
git commit -S -m '<message>'              # a new copy
git merge --no-ff -S origin/<branch>      # a copy whose main exists
```

Then check the signature, and push:

```sh
git -c gpg.openpgp.program=false -c gpg.x509.program=false show -s --format='%G? %GS'
git push origin main
```

The `show` must print `G` and the principal before the push. A key that needs a provider gets it
on the command that signs alone, as `SSH_SK_PROVIDER=<provider> git commit -S …`. From then on,
merge with `dotfiles merge` only.

## The data of `machines.toml`

`.chezmoidata/machines.toml` is a seed file of the kit: `harness dotfiles-kit` copies it once,
and then it belongs to your copy. Each template that reads the host table stops with chezmoi's
`fail` on a hostname that the table does not list, so a new machine needs its entry before its
first apply.

| key | meaning |
|:--|:--|
| `harness_commit` | the commit of the harness for every machine, 40 hex digits |
| `template_host` | the hostname of the one machine that signs |
| `[remotes]` | the clone URLs of `claude` (`~/.claude`), `environment` (`~/Research/Environment`), `harness` (`~/Research/Harness`) and `meta`, the meta repository, whose work tree is `~/Research` |
| `[machines.<hostname>]` | one table for each machine, under its `hostname -s` |
| `os` | `darwin` or `linux` |
| `arch` | the machine's `uname -m` |
| `gpu` | `metal`, `cuda`, `amdgpu` or `none`: the GPU package that Julia gets |
| `julia_channels` | the juliaup channels to install |
| `julia_default` | the default channel among them |
| `signing_key` | the key that signs the merges of `dotfiles merge`, as git's `user.signingkey` reads it; only the template host reads it |
| `sk_provider` | the `SSH_SK_PROVIDER` that the signing key needs, such as `/usr/lib/ssh-keychain.dylib` for a key in the Secure Enclave of a Mac; empty for a key that needs none |

The keys from `os` to `sk_provider` are the keys of each `[machines.<hostname>]` table.
`.chezmoidata/julia.toml`, a seed too, names the Julia packages of every host, each with its
minimum channel.

## Start a private copy

1. Make an empty private repository, and clone it to a directory of your own, such as
   `~/src/dotfiles`. Do not use the source that chezmoi applies, `~/.local/share/chezmoi`:
   `harness dotfiles-kit` refuses it.
2. List the files of the kit that the clone lacks, then copy them:

   ```bash
   harness dotfiles-kit ~/src/dotfiles
   harness dotfiles-kit --apply ~/src/dotfiles
   ```

3. Write your own values into the seed files: your machines, `template_host`, the remotes and
   `harness_commit` in `.chezmoidata/machines.toml`; the public key of your signing key in
   `dot_config/git/allowed_signers`; and your profile and model tables in
   `dot_config/research-harness/`. Write a `README.md` that names the fingerprint of the signing
   key, which `ssh-keygen -l -f` of the key's `.pub` file prints, and links this page: each
   [new machine](#a-new-machine) compares with it. The kit's `.chezmoiignore` keeps `README.md`
   off the machines.
4. Add your own files beside the kit's. The kit does not own `~/.gitconfig`: your own
   `dot_gitconfig.tmpl` includes the signing settings of git with this line:

   ```text
   {{ template "gitconfig-signing" . }}
   ```

   The ignore lines of your copy alone go into `.chezmoitemplates/chezmoiignore.local`.
5. Run the five tests of the kit in `tests/` of the clone, such as
   `python3 tests/render-check.py`; [development.md](development.md#the-pre-push-hook) names
   them. They need Python 3.11 or later and chezmoi. `script-check.py` also reads
   `~/Research/Harness` at `harness_commit`.
6. Make [the first signed commit](#the-first-signed-commit), and push it. Then set up each
   machine as [A new machine](#a-new-machine) says.

A *code* file of the kit stays identical to the kit, and a *seed* file is yours once it is there.
To move to a new harness, change `harness_commit`, and run `harness dotfiles-kit` again from a
harness checkout at that commit: it lists each code file that changed. Until you copy them,
`dotfiles check` reports the kit as a `WARN`.

## Files

| file | what it is |
|:--|:--|
| `~/.local/bin/dotfiles` | the driver |
| `~/.local/bin/dotfiles-update`, `dotfiles-check` | the scripts of every host |
| `~/.local/bin/dotfiles-merge` | the merge script, on the template host only |
| `~/.local/share/chezmoi` | the applied source, which `chezmoi init` clones, and only `dotfiles update` and `dotfiles merge` move |
| `~/.config/git/allowed_signers` | the keys whose signatures count, as applied |
| `.chezmoidata/machines.toml` | the data of the source; see [The data of `machines.toml`](#the-data-of-machines-toml) |
| `.chezmoitemplates/dotfiles-update-steps.sh` | the steps that `dotfiles-update` and `dotfiles-merge` share: the terminal test, the question, the check, and the review and apply |
| `.chezmoitemplates/dotfiles-signature.sh` | the signature test of one commit, which `dotfiles-check` uses too |
| `.chezmoitemplates/gitconfig-signing` | the signing settings of git, for your `.gitconfig` template |
| `kit.toml` | each file of the kit and its class, `code` or `seed` |
