# Setup on macOS

This page sets up a Mac in four steps: the prerequisites, the clone, `harness setup` and the check
that it worked. Then you make the [forge tokens](#the-forge-tokens). `harness setup` puts the tools
and the [frontends](concepts.md#frontend) that you choose on the machine, and then sets up the
harness, with its [install](concepts.md#install).
[setup-reference.md](setup-reference.md) gives each step of `harness setup`: what it does, why,
and how to do it by hand. [setup-linux.md](setup-linux.md) is the page for Linux.

The steps are checked on macOS 27 on Apple silicon (`arm64`) only, and they use
`~/Research/Harness` as the path of the checkout. [Introduction](concepts.md) explains the terms
that this page uses, and the glossary there has an entry for each.

## The prerequisites

`harness setup` needs Homebrew, Python 3.14, uv and git. When `command -v brew` prints nothing,
install Homebrew first. Its installer needs the password of an administrator, once. This line
runs the installer, and the second line puts `brew` on the `PATH` of the shell that you are in:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Add the `eval` line to `~/.zprofile` too, as the installer says. Then this line installs the
other three:

```bash
brew install python@3.14 uv git
```

[Dependencies](dependencies.md#you-provide) says why each one is a prerequisite.

## The clone

These commands clone the harness repository and put its `bin/` directory on the `PATH`, so that
your shell finds the command `harness`:

```bash
git clone https://github.com/michakraus/ResearchHarness.git ~/Research/Harness
export PATH="$HOME/Research/Harness/bin:$PATH"
```

Add the `export` line to `~/.zshrc` too, so that each new shell finds `harness`. The first run of
`harness` outside a [session](concepts.md#session) makes the Python environment of the harness,
with `uv sync`, and names it in one line; in a session, its line names `harness install --apply`,
which makes it. With a Python older than 3.14, the first run lets uv fetch Python 3.14 for the
environment; a session cannot fetch it, and stops `harness` with exit status 2. A Python older
than 3.9 stops `harness` with exit status 2, an error that names the version found. This line
lists the subcommands:

```bash
harness --help
```

## `harness setup`

Run `harness setup` in your own terminal:

```bash
~/Research/Harness/bin/harness setup
```

Without a [profile](concepts.md#profile), it copies the example profile and asks for the keys
that have no default: `memory_project`, `tree_agents`, `org`, `repository_roots` and `leak`.
Before each question it says what the key holds and whether the answer is the same on every
machine, as the table of [The questions of harness setup](profile.md#the-questions-of-harness-setup)
gives it. An empty answer keeps the example's value; a list takes items separated by commas or a
TOML list, and replaces the example's list. Then it asks for the frontends and the components, and
whether this machine develops the harness. In a terminal, the frontends and the components are a
checkbox list: the arrow keys move, space checks or unchecks a name, and Enter accepts. Without a
terminal on both standard input and standard output, with `TERM` unset, empty or `dumb`, without
curses, or in a window too small for the list, it asks from a numbered list instead. With the
component `jobs` and a profile without `claude_remote`, it asks for the URL of your `~/.claude`
repository; an empty answer means no autocommit job. It writes the answers into the profile, shows
its plan, and runs the plan after y/N: `git clone` of `claude_remote` into a `~/.claude` that is
missing or empty, first, before an installer can write below `~/.claude`; the directories, the
Homebrew packages, the installers of Julia, Kaimon and Claude Code, `harness install --apply`,
`git config core.hooksPath .githooks`, `harness trust --apply`, the jobs and the Kaimon token
where `[setup]` chooses their components, and `harness doctor`. After the jobs start the Kaimon
server, the token step waits up to 60 s for the server's key.
[setup-reference.md](setup-reference.md) has a section for each step.

Two options change the run:

```bash
harness setup --dry-run   # print every command of the plan, and change nothing
harness setup --yes       # read [setup] of the profile, and ask nothing
```

**When a step fails**, `harness setup` prints its output and stops with exit status 2. Fix the
cause, then run `harness setup` again: it plans again and skips what is done. On a new machine,
the step `harness trust --apply` waits for `~/.claude.json`, which Claude Code writes at its first
start: the run names the step and goes on. Start `claude` once, then run `harness trust --apply`.

**By hand.** `harness setup` prints the steps that it cannot do under *By hand*, before its last
step. With the frontend `antigravity`, install the Antigravity app from
<https://antigravity.google/>, start it once, then run `harness install --apply`. With `jobs` and
without `claude_remote`, a line names the key that the autocommit job needs; the script
`claude-autocommit` is still copied into `~/.local/bin`, but its job is not enabled. One line is an
`export PATH=…` line. It holds each directory that the installed programs are in and that the
`PATH` of the shell that started `harness setup` lacks: `~/.local/bin`, and with `julia` also
`~/.juliaup/bin` and `~/.julia/bin`. With zsh as your login shell, `harness setup` asks y/N to
append the line to `~/.zshrc`, after a comment line, unless `~/.zshrc` holds the line already;
with another shell, with `--yes`, or with a `~/.zshrc` that is a symlink, add the line to your
shell startup file yourself.

## The check that it worked

The last step of `harness setup` is `harness doctor`. It checks the machine, the tools, the
profile, the install and the jobs, read-only, and prints one line for each check: `PASS`, `WARN`,
`FAIL` or `SKIP`. A `FAIL` line names the section of [setup-reference.md](setup-reference.md)
that fixes it. Run it again after each fix, in a plain terminal:

```bash
harness doctor
```

It exits with status 0 when no check fails, and 1 when one fails. Then run the harness's own test
cases. The last line gives the number of cases, and it must say `0 wrong`:

```bash
harness test
```

At the start of each new Claude Code or Antigravity session, a [hook](concepts.md#hook) compares
`~/.claude/` with the sources. When a source changed after the last install, the session starts
with a warning about [drift](concepts.md#drift). The [tutorial](tutorial.md) starts your first
session.

## The forge tokens

**`harness setup` makes no token.** You make two kinds of token:

- **The organisation tokens**, which the [agents](concepts.md#agent) use: on GitHub, one
  fine-grained token for each organisation and one for your account; on GitLab, one group access
  token. The forge limits each token to its owner, so an agent can write only to the repositories
  of that owner. A broad login, such as `gh auth login`, gives an agent write access to every
  repository that you can write.
- **Your own broad tokens**, which only you unlock, with Touch ID or the Mac's password: `ghx`,
  `glabx` and `git-credential-sealed` use them, and `harness ci-protection` uses your GitHub
  token.

[The forge tokens](components/sandbox.md#the-forge-tokens) explains how the harness passes the
tokens.

### The organisation tokens

1. On GitHub, make one fine-grained token for each organisation and one for your account. Set the
   resource owner to that organisation or to your account, select all repositories, and give the
   token these permissions:

   - Read access to administration, Dependabot alerts, artifact metadata, commit statuses and
     metadata
   - Read and write access to actions, code, discussions, issues, pull requests, repository
     creation and workflows

   Administration read lets an agent read a repository's Actions settings, such as the workflow
   token permissions that decide whether TagBot may create a release. Give the token no Gists
   permission. An organisation can require that it approves a token.
2. On GitLab, make one group access token of the group, with the scopes `api`, `read_repository`
   and `write_repository`, and a role that can create projects in the group. By GitLab's default,
   that role is Maintainer; the group's setting *Roles allowed to create projects* decides it.
3. Put each token into `~/.config/research-harness/forge/<host>/<owner>.store` as the one line
   `https://x-access-token:<token>@github.com` or `https://oauth2:<token>@<gitlab host>`, mode
   600, the directories mode 700. Make `github.com/default.store` a copy of, or a symbolic link
   to, your account's file.
4. Run `harness install --apply`.
5. Remove the broad credentials and route your terminal the same way: `gh auth logout`, replace
   glab's stored token by the group token (`glab auth login --hostname <gitlab host>`), erase the
   credential manager's GitHub and GitLab entries, and, in your dotfiles, remove the credential
   manager and `gh auth git-credential` helpers from `~/.gitconfig`, clear the system's
   `osxkeychain` helper with an empty `helper` in a general `[credential]` section, and end its
   credential lines with `[include] path = ~/.config/research-harness/forge.gitconfig`. A Claude
   Code session runs git and gh outside its [sandbox](concepts.md#sandbox), so a broad credential
   that stays there stays usable.

### Your own broad tokens

On macOS only. After step 5 above, your terminal has the organisation tokens, not your own broad
access. The broad tokens become secrets that only you decrypt, with Touch ID or the Mac's
password. Each run that reads a secret asks for Touch ID; a Touch ID prompt that you did not start
comes from a session, so refuse it. [The sealed secrets](components/sandbox.md#the-forge-tokens) explains the protection.

1. Install the tools: `brew install age age-plugin-se`.
2. Make the identity in the Secure Enclave, in a directory with mode 700:

   ```sh
   mkdir -m 700 -p ~/.config/research-harness/sealed
   age-plugin-se keygen --access-control any-biometry-or-passcode --recipient-type se \
       -o ~/.config/research-harness/sealed/identity.txt
   ```

   `keygen` prints one line, `Public key: age1se1…`. That key is the identity's recipient, and it
   is no secret. `--access-control any-biometry-or-passcode` makes each decryption ask for Touch
   ID, or for the Mac's password where no Touch ID is at hand; a session can give neither.
   `--recipient-type se` keeps the recipient an `age1se1…` key: a later version of
   `age-plugin-se` makes a `tag` key, `age1tag1…`, by default. The flags are those of
   `age-plugin-se` 0.2.1, which `age-plugin-se --help` lists.
3. Write the recipient into a file, so that no command needs the key typed:

   ```sh
   age-plugin-se recipients --recipient-type se -i ~/.config/research-harness/sealed/identity.txt \
       -o ~/.config/research-harness/sealed/recipient.txt
   ```

   Then encrypt each secret to it: `github.age` with your broad GitHub token, `gitlab.age` with
   your broad GitLab token, and `<name>.age` for a repository of its own. Each secret is one line
   `https://<user>:<token>@<host>`. Run the command, type the line, press Enter, then Ctrl-D: the
   token is then in no argument and not in the shell's history.

   ```sh
   age -R ~/.config/research-harness/sealed/recipient.txt \
       -o ~/.config/research-harness/sealed/github.age
   ```

4. Give a repository that has a token of its own its helper in place of a plain token file. An
   example is the dotfiles source on GitLab: its project access token reads the personal project
   that the group token cannot read ([`dotfiles merge`](dotfiles-command.md#dotfiles-merge)).
   Seal that token as in step 3, for example as `dotfiles.age` with the line
   `https://oauth2:<token>@<gitlab host>`. Then set the helper in each clone of the repository.
   For the dotfiles, the clones are the applied source `~/.local/share/chezmoi` and your own
   clone, such as `~/src/dotfiles`. `git config` without `--global` writes the configuration of
   the repository in the current directory, so `cd` into the clone first:

   ```sh
   cd ~/.local/share/chezmoi
   git config --unset-all credential.https://<host>.helper
   git config credential.https://<host>.helper ''
   git config --add credential.https://<host>.helper 'sealed <name> https://<host>'
   git config --get-all credential.https://<host>.helper
   ```

   The first `git config` removes the clone's helpers for that host, such as the helper of the
   plain token file; it exits with status 5 where the clone has no such helper. git asks the
   helpers of `~/.gitconfig`, `forge.gitconfig` included, before those of the repository, and
   stops once a helper gives a username and a password. So the empty `helper` clears those first,
   and the `sealed` helper then answers, only for that host. The last command prints two lines: an
   empty line and the `sealed` line. Then delete the plain token file.
5. Keep glab's stored login as the group token of step 5 of
   [The organisation tokens](#the-organisation-tokens); your broad GitLab access goes through
   `glabx`.

**More.** To keep several machines the same, see
[Dotfiles (optional)](setup-reference.md#dotfiles-optional).
