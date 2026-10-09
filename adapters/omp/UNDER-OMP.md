## intro

This agent is ported from Claude Code. Where the text below names a Claude Code mechanism, these rules replace it:

## skills

**oh-my-pi loads the {skills} for you** before your first turn. If one of them is not in your context, read its `SKILL.md` below `~/.agents/skills/` before you start. You may load no other skill.

## worktree

**Nothing makes a worktree for you.** oh-my-pi has no `isolation: worktree`. If your caller names an existing worktree, work in it and make none. Otherwise make it yourself before anything else, in the repository your caller names, with `git worktree add`, as the global `AGENTS.md` says, and a short slug of your own. Where the text below says that your caller made the worktree, or that `pwd` is already in it, read it as the worktree that you made. Report its path; your caller removes it.

## agent

The `Agent` tool is the `task` tool here. Ignore each instruction about `run_in_background` for an agent call.

## bash

There is no sandbox here. Where the text below gives a rule that exists only because of the Claude Code sandbox or its permission matcher, the global `AGENTS.md` overrides it. The `bash` tool's default `timeout` is 300 seconds. Give a test suite, a precompile or any other long run a `timeout` in seconds that covers it, at most 3600, or `0` for no deadline.

## mcp

A Kaimon tool is named `mcp__kaimon_<tool>` here, with one underscore after the server: `mcp__kaimon__ex` in the text below is `mcp__kaimon_ex`.
