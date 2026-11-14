- **`dotfiles merge <number>` falls back to the source's git credential when glab's own login
  cannot read a merge request, and `harness test opencode` fails when OpenCode's generated
  permission files differ from the settings template.** For an `https://` origin on a host other
  than `github.com`, the kit's driver reads the origin's password with `git credential fill` in the
  source (an empty `GIT_ASKPASS`, `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`, stderr
  discarded, so no askpass program, terminal prompt or dialog asks for it) and runs the same
  `glab mr view` once more in the source with it as `GITLAB_TOKEN` and the parsed host as
  `GITLAB_HOST`; a project access token kept repo-local in the source, with the `read_api` scope,
  reads a personal project that the GitLab group token cannot. The password goes into no argument,
  no output, no file and no environment of `dotfiles-merge`. When no call answers, the driver
  stops with one line that names `dotfiles merge <branch>`. `adapters/opencode/opencode.jsonc` is
  written again by `harness permissions --apply`, which drops two `git push … :**` ask rules that
  the template no longer holds (K160), and a new case of the `opencode` selftest compares
  `opencode.jsonc` and `plugins/guard-paths.json` with their generated text, so the drift fails CI. The setup reference
  no longer tells an SSH machine to run `gh auth login`: `gh` and git reach the forges through the
  token store. The sandbox page records why a git request that succeeds through srt's proxy under
  `agentbox` prints `could not lock config file ~/.gitconfig`: git passes the proxy's credentials to
  a credential manager left in `~/.gitconfig`, whose write srt refuses; removing the credential
  manager ends the line.
