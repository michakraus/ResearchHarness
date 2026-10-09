# RTK — Rust Token Killer

A token-optimising CLI proxy. A `PreToolUse` hook rewrites many Bash commands transparently —
`cat f.txt` → `rtk read f.txt` — at no token cost. There is nothing to invoke.

⚠️ **`rtk run`, `rtk proxy`, `rtk curl` and `rtk wget` are denied.** Each executes a raw command
with no filtering, which made any denied command reachable through a six-character prefix. Use
`WebFetch` to read a page, or Julia's `Downloads` for a scripted request.

**`rtk hook check '<cmd>'` is the dry run for which *commands* are rewritten.** The set changes
without any change here, so check rather than cite — including this page. It reads the command text
only, so it does **not** model the shell features that switch the hook off: it predicts a rewrite
for a command carrying a redirection, and the live hook then rewrites nothing.

**In Claude Code, a pipeline or a redirection disables the rewrite for the whole command.** `&&`
and `;` do not.
So a self-contained probe — build a fixture and search it in one command — silently measures raw
`grep`, and the missing header reads as a broken hook. Write the fixture in one command and search
it in the next.

Two things that produce a wrong answer rather than an error:

- **`head` and `tail` are excluded from the rewrite** because a proxied `head -N` intermittently
  returned lines lifted from elsewhere in the file. Silent, about one attempt in ten. Do not
  re-enable them.
- **`rtk grep` and `rtk rg` stop at a per-file cap**, 200 here and 25 upstream — a `[limits]`
  setting, so ask the config. `rg` is rewritten too; it is not in `exclude_commands`. The cap
  announces itself: the header states the true total and the last line names the `tail` command for
  the rest. **Read the first and last lines.** A truncated search is not a negative. In Claude
  Code any pipeline bypasses the hook, so `grep -n p f | cat` returns everything.

**Use the `Read` tool when the exact bytes matter** — a permission pattern, a hash, a `[compat]`
bound, anything you are about to quote as evidence. The same caution applies to a *conclusion*
drawn from proxied output.

Configuration, measurements and the failure modes: `~/Research/Environment/Notes/RTK.md`.
