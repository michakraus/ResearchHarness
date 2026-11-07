- **The harness drops iTerm2: the component `iterm`, the hook `cc-status` and the doctor check of
  iTerm2 are gone, and the Linux plan of `harness setup` prints the lingering line only where
  lingering is off.** The settings template no longer runs `cc-status`, so the events
  `Notification`, `SessionEnd`, `Stop`, `StopFailure`, `SubagentStop` and `UserPromptSubmit`, in
  which it was the only hook, run no hook. `harness setup` installs no Homebrew cask. A profile
  whose `[setup]` still names `iterm` is refused as any unknown component is: `harness setup`
  exits 2 and `harness doctor` prints a `FAIL` line of `profile`; remove `"iterm"` from
  `components`. `harness install` lists an installed `~/.claude/hooks/cc-status` as `EXTRA` with
  its `rm` line, and `--apply` does not remove it. With
  the jobs on Linux, `harness setup` reads `loginctl show-user <user> -p Linger` and leaves out
  `sudo loginctl enable-linger "$USER"` under *By hand* when it reads `Linger=yes`; a `loginctl`
  that is missing, fails or prints no `Linger=` line keeps the line, and so does a uid with no
  user name.
