- **Each frontend's `srt` settings file allows pseudo-terminals with `"allowPty": true`.** A
  frontend's terminal user interface can then put its terminal in raw mode under `agentbox`; a
  sandboxed command can also read from and write to every terminal of the user, on macOS.
