- **`harness setup` explains each question, and reads a list answer as you mean it.** Before
  each question for a required key of a new profile, `setup` prints what the key holds and
  whether its answer is the same on every machine that shares the tree; the lists of frontends
  and components give one description per name, and the `develop` question says that it is for
  a machine that changes the harness's own code. A list answer is either items separated by
  commas or a TOML list such as `["a", "b"]`, and the prompt says that it replaces the example's
  list. An item that holds a bracket or a quote, a TOML list that does not parse, holds a value
  that is not a string or holds an empty string, an answer with no item, and an `org` item that
  is no GitHub account name are refused with one line, and the question comes again; before,
  such an answer went into the profile as it was, brackets and quotes included. The profile now
  refuses an `org` entry that is no GitHub account name (letters, digits and single hyphens, 1
  to 39 characters, not starting or ending with a hyphen) with exit 2, naming the entry: correct
  such an entry in an existing profile. `docs/src/profile.md` gives the table of the questions,
  and the setup pages link it.
