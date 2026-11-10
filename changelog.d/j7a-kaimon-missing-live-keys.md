- **The Kaimon check's refusal of an `ex` without `ses` and of a `manage_repl` without `session`
  names the live session keys.** It said only to call `ping`, so the agent spent one more call
  before it could retry. `kaimon_session.py` computes the keys in one function for this refusal
  and for that of a dead key: sorted, each once, and none when the gate directory cannot be listed.
