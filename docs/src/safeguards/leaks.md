# Leak checks and gitleaks

A public repository keeps every string that a push sends to it, also after a later commit removes
the string. The harness is such a repository, and it is written in a private research tree whose
names, paths and secrets must stay out of it. So every push of the harness passes two checks:
gitleaks, which finds secrets and home paths, and `harness leaks`, which finds the private strings
of your profile. This page describes both checks, where they run, and what they do not find.

## Two kinds of leak

| kind | an example | found by |
|:--|:--|:--|
| **a secret** | a token, a key, a password in a configuration file | gitleaks, with its default rules |
| **a home path** | `/Users/<name>/…` in a log that went into a test fixture | gitleaks, with the rule `home-path` of `.gitleaks.toml` |
| **a private string** | the name of a private project, a host, an institution | `harness leaks`, with the profile's `leak` list |
| **a name of the research tree** | the name of a repository of your tree, or of an organisation | `harness leaks`, from the profile's `repository_roots` and `org` |

gitleaks knows the shapes of secrets, but not your private names. `harness leaks` knows your names,
but not the shapes of secrets. Each check covers what the other cannot.

## gitleaks

[`.gitleaks.toml`](../components/other.md#gitleaks-toml) keeps the default rules of gitleaks and
adds the rule `home-path`, a path below `/Users/` or `/home/` that names a user. Only the two
example homes of the repository, `/Users/me` and `/home/example`, pass. Every call passes
`--redact`, so a finding does not print the secret, and `--ignore-gitleaks-allow`, so a
`gitleaks:allow` comment in a file has no effect. gitleaks 8.21 or later is needed; CI pins
8.30.1.

Remove a false positive by a change of the text, not of the configuration. A new allowlist entry
needs your approval and its own line in the changelog.

## `harness leaks`

[`harness leaks`](../harness-command.md#leaks) searches the tracked files of the harness and their
paths for two sets of words, each as a whole word:

- the strings of the profile's `leak` list;
- the names of the research tree: each directory below each of the profile's `repository_roots`,
  and each organisation of its `org` list.

It also renders the templates with the example profile `examples/profile.toml` and searches the
result, so a template that would write a private string into an installed file is found too. With
`--commits FILE`, it also searches the paths and the lines that each commit of the file adds, and
each commit's message.

```bash
harness leaks
```

It exits 0 with no hit, 1 on a hit, and 2 when the profile does not load. Run it before a commit
of the harness; [Typical use](../daily-use.md#the-leak-check-before-a-push) shows the steps.

## Where the checks run

| where | on | runs |
|:--|:--|:--|
| the pre-push hook of the harness | a push to `main` | gitleaks over the commits of the push, gitleaks over their messages on standard input, gitleaks over the tree at the pushed commit, then `harness leaks --commits` over the tree and the commits |
| the pre-push hook of the harness | a push of another branch | `harness leaks --commits` only |
| CI, the job `leaks` | every push and every pull request | a canary first, a synthetic token and home path that gitleaks must find and redact; then gitleaks over the pushed range and its messages, over the checkout, and over the templates rendered with the example profile |
| you | before a commit | `harness leaks` |

**The hook fails closed.** No gitleaks of 8.21 or later, no profile, an empty `leak` list, or a
check that fails, each refuses the push with one line. The hook runs on a `git clone --shared` of
the pushed commit, so it checks what it pushes, not the working tree. Then it runs the suite.
[Development](../development.md#the-pre-push-hook) describes the hook in full.

**CI has no profile.** It runs gitleaks, but it cannot search for your private strings, because it
does not know them. The hook on your machine is the one check of the private strings.

## The token check of the guard

The guard package has a check of its own, [`token_forms`](guard-hooks.md#the-token-check), which is
independent of the two checks above. It reads each outgoing shell command, web call and Kaimon call
before it runs, and refuses one that holds a token of a known form of GitHub, GitLab or an `sk-`
provider, as it is or percent-decoded. It prevents an accident, such as a token pasted into a
command. It is no boundary: a token that is encoded in another way, split, or read from a file by a
script passes it.

## The limits

- **A push with the hook off is not checked on your machine.** In a clone where `core.hooksPath`
  is not set, the hook does not run; CI still runs gitleaks.
- **A private string that is not in the `leak` list is not found.** Add each new private name to
  the list.
- **Some parts of a commit are not searched:** its author and committer, a tag message, and
  `git notes`.
- **Known issues:** a whole-history gitleaks scan is red until the history is rewritten (K36);
  `useDefault = true` brings the default global path allowlists of gitleaks into the configuration
  (K37); `gitleaks git` exits 0 on a range that it cannot read (K38); the rule `home-path` finds a
  macOS home path but no Linux home path (K81); six branches of the pre-push hook have no case that
  fails when they change (K112).

**In another repository.** The two checks fit any public repository that is written in a private
tree. gitleaks needs only its configuration. `harness leaks` needs a profile with a `leak` list.
