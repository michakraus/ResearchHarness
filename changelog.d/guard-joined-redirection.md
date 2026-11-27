- **The checks read a redirection that follows a separator or a parenthesis with no blank between
  them as a redirection (K223).** The reader made one operator of a run such as `;>`, `&&>` or
  `(>`, so the target of the redirection read as the command word: `true;>/dev/null rm -rf
  Papers`, `true&&>/dev/null rm -rf Papers` and `(>/dev/null rm -rf Papers)` passed, though bash
  and zsh run the `rm` in `~/Research`. They are now refused. The reader splits such a run as the
  shells do, the longest operator first, so `&>` stays one redirection and
  `true&>/dev/null rm -rf Papers`, which runs only `true`, still passes.
