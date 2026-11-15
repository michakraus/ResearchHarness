- **The probe battery asks an OpenCode listener at its API, names each listener's PID, and accepts
  `rapportd` with no answer.** `scripts/probe-agentbox.py` asks a listener whose command is
  `opencode` at `/api/v2/session`, where OpenCode's server asks for its password, in one row
  `L:<port>/api/v2/session`, and no longer at `/` and `/path`, which serve the web app's HTML
  without one, so that their rows were `MISMATCH`. The `detail` of every listener row starts
  with `<command> <host>:<port> pid <pid>`, so a listener of a `MISMATCH` row can be found after
  the run. A `rapportd` listener, which gives no HTTP answer, is `match` on `000` as well as on
  401, 403 and 407; every other listener with no answer stays `MISMATCH`.
