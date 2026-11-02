- **The `gh api` check passes a Git Data write in an own organisation.** A POST to
  `repos/<owner>/<repo>/git/blobs`, `git/trees`, `git/commits` or `git/refs` passes when `<owner>`
  is in the `org` list of the profile, compared without case, so a branch made through the Git Data
  API no longer asks once per call. A PATCH of a ref, any DELETE, a call with `--hostname`, and a
  write elsewhere still ask or are refused as before; a profile that is missing or has no `org`
  list of strings makes every such write ask.
