- **`harness repos pull` fast-forwards past a local change that already equals the incoming
  content.** After `harness githooks --apply` wrote the same hooks and workflow that a merged pull
  request brought, every checkout was skipped with "the incoming commits change local changes",
  and the user had to restore each file by hand. Such a file is now no clash: `pull` resets it to
  `HEAD` and fast-forwards, which writes the same content back, and the line names the files it
  dropped. A local change that differs from the upstream still skips the repository.
