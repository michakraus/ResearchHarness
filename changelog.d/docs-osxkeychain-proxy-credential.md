- **The macOS setup also clears the system's `osxkeychain` helper.** Without it, every remote
  `git` under `agentbox` prints `fatal: failed to store: -60008` after the credential manager is
  gone, because srt refuses the keychain store of the proxy's credential.
