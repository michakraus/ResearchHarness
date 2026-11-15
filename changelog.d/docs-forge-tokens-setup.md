- **The setup pages hold every step of the forge tokens.** A new section *The forge tokens*, on the
  macOS and the Linux page, gives *The organisation tokens* as numbered steps: one fine-grained
  GitHub token for each organisation and one for your account, with its permissions as a list
  (read access to Dependabot alerts, artifact metadata, commit statuses and metadata; read and
  write access to actions, code, discussions, issues, pull requests, repository creation and
  workflows; Checks read is no longer in the list), the GitLab group token, the token store,
  `harness install --apply` and the terminal. The macOS page adds *Your own broad tokens*, the
  steps of the sealed secrets: they say what each flag of `keygen` does and pin
  `--recipient-type se`, write the recipient into `recipient.txt` for `age -R`, and say in which
  clones, such as the dotfiles' `~/.local/share/chezmoi`, a repository's own helper goes, and how
  to check it. The sandbox page keeps the mechanism and links to these steps.
