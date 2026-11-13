- **oh-my-pi's typo detection works under `agentbox`.** It asks the macOS spell service
  `mul-xpc (Apple)_OpenStep` for each typed word, and `srt` refused the Mach lookup, so AppKit
  printed "Sandbox restriction" into the terminal. A new key `mach_lookup` in each frontend table
  of `sandbox/policy.toml` names the services that a frontend looks up, each by its exact name;
  `harness install` writes it as `network.allowMachLookup` into that frontend's `srt` settings
  file. `omp` lists the spell service, the other three frontends none. A command of oh-my-pi can
  reach the service too, which can write learned words to `~/Library/Spelling`. Run
  `harness install --apply` to rewrite the files.
