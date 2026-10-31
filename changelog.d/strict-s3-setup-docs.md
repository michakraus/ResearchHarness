- **The setup pages run `harness setup`, and a new setup reference gives each of its steps by
  hand.** `setup-macos.md` and `setup-linux.md` shrink to the prerequisites, the clone,
  `harness setup` with its questions, `--dry-run` and `--yes`, and the check with
  `harness doctor`. The new `setup-reference.md` holds each step of the plan in its order, from
  the profile to `harness doctor`: what `harness setup` does there, why, and the commands for
  macOS and Ubuntu, with every command of the old pages; and the steps that `harness setup` does
  not do: checking the machine, the Antigravity app, lingering, the dotfiles and a machine reached
  over SSH. `dependencies.md` groups the tools into *You provide* (Python, uv and git, with the
  `brew` and `apt-get` lines) and *`harness setup` installs*, whose rows now include chezmoi and
  Antigravity; each row says which component or frontend needs it, and the page says that the
  install needs Julia only with the component `julia`. Each `FAIL` of `harness doctor` now names
  a section of `setup-reference.md`, or *The check that it worked* for `harness test`, and a case
  of `harness test doctor:minimum` holds every section that `FIX` names to a heading of its page.
  Where `harness trust --apply` stops the run on a machine without `~/.claude.json` (K126), the
  pages tell the user to start Claude Code once, or, without the frontend `claude`, to write `{}`
  into that file.
