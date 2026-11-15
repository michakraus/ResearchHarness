- **The setup pages list the forge tokens.** A new section *The forge tokens*, on the macOS and the
  Linux page, says that GitHub needs one fine-grained token for each organisation and one for your
  account, and lists their permissions: read access to Dependabot alerts, artifact metadata, commit
  statuses and metadata; read and write access to actions, code, discussions, issues, pull
  requests, repository creation and workflows; Checks read is no longer in the list. The steps of
  the sandbox page link to it. The steps for the sealed secrets pin `--recipient-type se` and say
  what each flag of `keygen` does, and a new command writes the recipient into `recipient.txt`,
  which `age -R` reads, so that the encryption needs no recipient typed.
