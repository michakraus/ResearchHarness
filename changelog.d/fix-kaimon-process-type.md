- **The Kaimon launch agent runs as `Interactive`, not `Adaptive`.** launchd moves an `Adaptive`
  job out of the Background class only for activity over XPC connections, and Kaimon serves HTTP,
  so the server and its sessions ran with the CPU and I/O limits of a Background job. Under a load
  average of about 100, a cold start got 2.7 % CPU and compiled `Kaimon.main` for more than seven
  minutes before port 2828 listened. `harness setup` installs the changed plist.
