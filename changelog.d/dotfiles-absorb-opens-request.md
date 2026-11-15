- **`dotfiles absorb` opens the pull request or merge request itself after the push.** It runs
  `gh pr create` for an `origin` on `github.com` and `glab mr create` for any other host. For an
  `https://` `origin`, `glab` gets the password of the source's own git credential as
  `GITLAB_TOKEN`, as `dotfiles merge` reads it, so the dotfiles project access token (scopes
  `read_repository`, `write_repository` and `api`) opens the request; otherwise `glab` uses its
  own login. When the request does not open, it names the pushed branch and the command that
  opens it, and exits 1. The `glab` call that holds the password, here and in the fallback of
  `dotfiles merge`, runs without the caller's `glab` variables of another token, host, protocol
  or TLS check, such as `GITLAB_API_HOST` and `API_PROTOCOL`, which sent the password to another
  host or in clear text, and with a new empty `GLAB_CONFIG_DIR` in place of the caller's `glab`
  configuration, whose per-host settings could do the same.
