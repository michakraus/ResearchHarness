- **A sandboxed command reads GitHub Actions logs.** `gh run view --log-failed` failed with
  "host is not on the allow list" for `results-receiver.actions.githubusercontent.com`, and the
  jobs API `actions/jobs/<id>/logs` redirects to a blob of
  `productionresultssa<N>.blob.core.windows.net`, whose number changes between runs. The
  `infrastructure` list of `settings/network.toml` gains
  `results-receiver.actions.githubusercontent.com` and `*.blob.core.windows.net`. The wildcard
  lets a sandboxed command reach every Azure blob storage account; the WebFetch tool reaches
  neither host.
