- **A transient download failure is tried again, in `bin/harness` and in CI.** The bootstrap's
  download of the pinned uv release made one attempt, and each `curl` of a release archive in the
  workflows too, so one HTTP 504 from the release host failed the job: on one pull request, eight
  jobs of two runs failed this way, twice. `bin/harness` waits 5, 15 and 45 s and tries again
  after an HTTP 408, 429 or 5xx, or a network error, with one line on stderr per wait; a 404, a
  bad URL or a local write error still refuses at once. Each `curl` takes `--retry 6`. New cases
  of `environment` serve 504 twice, then the archive; 504 always; and 404 and a refused redirect,
  each asked once.
