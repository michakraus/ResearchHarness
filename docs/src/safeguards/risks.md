# Risks of agentic coding

A coding agent runs commands on your machine, with your files, your credentials and your network.
Most of its commands are what you would run yourself. A few are not: a command that deletes more
than it should, a push to the wrong branch, a token in a log that goes to a public repository. This
page names the risks, says where each one comes from, and points to the safeguard of each. The
other pages of this section describe the safeguards.

## Where the risks come from

Three sources produce almost every risk:

- **Mistakes.** The agent means well and gets a command wrong: a `git add -A` that stages another
  session's files, a `rm -r` one directory too high, a `sed -i` that matches nothing and reports
  success. These are the most frequent, and the cheapest to prevent.
- **Instructions in content.** A web page, an issue body or a file that the agent reads holds text
  addressed to the agent, such as "run this command" or "send the key to this address". The agent
  can act on it as if you had written it. This is *prompt injection*.
- **Reach.** A shell command can reach everything that your user account can: your SSH keys, your
  tokens, every repository and every host. A command does not need bad intent to do harm, only
  access.

## The risks

| risk | an example | the safeguard |
|:--|:--|:--|
| **Data loss** | a recursive `rm` outside the work directory; `git reset --hard`; a forced worktree removal with commits that no branch holds | [guard hooks](guard-hooks.md#the-rm-check), [deny rules](permissions.md#deny), [git safety](git-safety.md) |
| **A sweep of other work** | `git add -A` or `git commit -a` in a tree where another session works | [the staging check](guard-hooks.md#the-staging-check), [git safety](git-safety.md#staging) |
| **An irreversible outward step** | a merge, a release, a forced push, a deleted repository | [ask and deny rules](permissions.md), [git safety](git-safety.md#pushes) |
| **A secret leaves the machine** | a token in a commit, a home path in a public file, a key sent to a host | [the sandbox](sandbox.md), [leak checks](leaks.md), [the token check](guard-hooks.md#the-token-check) |
| **A private string in a public repository** | the name of a private project in a tracked file of the harness | [leak checks](leaks.md) |
| **A change of the agent's own rules** | the agent edits its settings, a hook or an installed skill, so that the next session runs with fewer checks | [deny rules](permissions.md#deny), [the drift warning](security-model.md#the-mechanisms) |
| **Persistence** | a launch agent, a cron job or an MCP server that the agent adds and that runs later outside every check | [deny rules](permissions.md#deny) |
| **A wrong host** | a command that sends data to a host that the task does not need | [the sandbox's network allowlist](sandbox.md#the-session-sandbox) |
| **Prompt injection** | an instruction inside a fetched page that tells the agent to run a command | the instructions treat content as data; the [sandbox](sandbox.md) limits what an obeyed instruction can reach |

## Accident prevention and a boundary

Most safeguards of the harness read the text of a command and stop the forms that are mistakes.
They prevent accidents. A session that tries to get past them can do so, because a command can
hide inside a string argument that no text pattern sees. One safeguard is a boundary: the OS
sandbox, which limits what a command can read, write and reach, whatever its text says.
[The security model](security-model.md) states this split, and what each mechanism stops and does
not stop.

The split decides how a risk is handled:

- **A risk that comes from a mistake** gets a check of the text: a deny rule, a guard hook, a
  leak check. A guard hook and a leak check also tell the agent what to do instead, so the next
  command is right; a deny rule only refuses.
- **A risk that comes from reach or from injection** needs the boundary. A text check helps, but
  only the sandbox holds against a command that the check does not read.

## What stays open

No safeguard removes every risk. The [limits of the security model](security-model.md#the-limits)
list the gaps that are known, such as the commands that run outside the sandbox, an MCP server that
runs outside the session's sandbox, and an allowed host that takes what a command sends to it. The
[planned safeguards](security-model.md#planned-safeguards) close some of them.

You stay the last check for an outward step. A merge, a release and a deleted branch on a remote
ask you; a forced push is refused. The test suite runs before a push to `main` of a package, and
the leak gate before a push of the harness ([Git safety](git-safety.md#pushes)).
