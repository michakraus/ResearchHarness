- **The organisation tokens on GitHub get read access to administration.** The setup pages for
  macOS and Linux add it to the list of permissions. Without it, an agent gets a 403 when it reads
  a repository's Actions settings, so it cannot see why TagBot fails to create a release with
  "Resource not accessible by integration".
