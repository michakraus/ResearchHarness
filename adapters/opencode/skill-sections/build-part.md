## Under OpenCode

Where step 3 spawns two critics, spawn the council of the part's critic, `julia-critic` or
`python-critic`, in one message: the critic as `Round: 1a`, and each of its council copies as
`1b`, `1c`, … in the alphabetical order of their names. A council copy is a hidden agent whose
description says "The same agent as julia-critic" or "The same agent as python-critic". Each
critic runs on a different model. The `task` tool takes no effort, so `1a` runs at the variant of
the critic, and each copy at its own. Everything else in step 3 holds for every critic: the round
fails when any critic fails, its findings are the union of the reports, and you wait for all of
them. A verify round spawns one critic alone: the council copy whose description says that it
judges each verify round, else the critic.
