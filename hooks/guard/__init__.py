"""The guard: one program that decides a tool call of an agent before it runs.

`<python> hooks/guard --from <frontend>` reads the frontend's payload on stdin, turns it into the
neutral contract of `contract` with the frontend's table in `frontends/`, runs each check of
`checks/` that the table names for the call, and answers in the frontend's form: the first of
`deny`, `ask`, `allow` and `pass` that a check gives, with the reason of the check that gave it.

The package imports only the standard library and its own modules, by relative imports.
"""


class HarnessError(Exception):
    """A payload that the guard cannot read; the guard denies the call with its message."""
