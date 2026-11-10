- **The global instruction files of OpenCode, oh-my-pi and Antigravity share one budget of 5,120
  bytes, and a case of `harness test` holds each delta to it.** The council rule of `build-part`
  moves out of `OPENCODE-DELTA.md` and `OMP-DELTA.md` into an *Under OpenCode* and an *Under
  oh-my-pi* section of each frontend's copy of that skill, from `skill-sections/build-part.md` in
  the adapter's directory, so it loads only with the skill; OpenCode's `--auto` warning moves into
  the documentation. A section file whose skill the install does not copy stops the install with
  exit status 2.
