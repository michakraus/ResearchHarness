- **On macOS, `harness install` puts `scripts/sealed.py` on the `PATH` as `ghx`, `glabx` and
  `git-credential-sealed`, and no session can read or run the sealed secrets.** The three names go
  to `~/.local/bin` beside the gh wrapper, mode 755. The settings template denies
  `~/.config/research-harness/sealed` to Claude Code's read tools, its sandbox and
  `credentials.files`, and so to every frontend's srt file and to the guard lists of OpenCode,
  oh-my-pi and Antigravity, and its `permissions.deny` refuses the three commands, also in
  OpenCode. *The forge tokens* gives the fine-grained tokens Actions read and write, and the
  user's steps for the sealed secrets: `age` and `age-plugin-se`, an identity that asks for Touch
  ID, and each secret typed on stdin. The page *Scripts* names the two scripts that the install
  copies (K164).
