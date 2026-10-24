## intro

This agent is ported from Claude Code. Where the text below names a Claude Code mechanism, these rules replace it:

## skills

**Activate the {skills} before you start.** Claude Code preloads an agent's skills; Antigravity does not. You may activate no other skill.

## worktree

**Nothing makes a worktree for you.** Antigravity has no `isolation: worktree`. If your caller names an existing worktree, work in it and make none. Otherwise make it yourself before anything else, in the repository your caller names, with `git worktree add`, as the global `GEMINI.md` says, and a short slug of your own. Where the text below says that your caller made the worktree, or that `pwd` is already in it, read it as the worktree that you made. Report its path; your caller removes it.

## agent

The `Agent` tool is `invoke_subagent` here, with the agent's name as `TypeName` and your brief as `Prompt`. Where the text below says to `SendMessage` an agent, make a new `invoke_subagent` call with its last report as the handoff.

## background

**Run every command and every subagent in the foreground.** Antigravity has no `run_in_background`: ignore each instruction about it, and let each call end before you go on.

## mcp

**Call a Kaimon tool through `call_mcp_tool`**, with `ServerName` `kaimon`, `ToolName` the tool's name and its arguments as `Arguments`: `mcp__kaimon__ex` in the text below is `call_mcp_tool` with `ToolName` `ex`.

## pr

**Your caller opens the pull request.** A subagent shows no prompt, and `gh pr create` can need one. Where the text below says to open a pull request, do everything before it: stage, commit, push the branch, and write the body file. Then return the `gh pr create` command, with `--repo <owner>/<repo>` first and `--body-file` with the body file's absolute path, to your caller in your report, name `gh pr create for the caller` as the blocker of your verdict, and stop. The caller runs it.
