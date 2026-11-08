- **The audit skill asks for concretely typed struct fields.** `julia-package-audit` told an
  auditor to prefer "abstract rather than concrete field annotations", the opposite of the rule it
  audits for: an abstract field makes every read of it infer as `Any`. It now says that every field
  is concretely typed, with a type parameter where the field would be `Any`, a bare `Matrix` or an
  abstract type. The same paragraph dropped its count of the repositories that run JET, which had
  gone stale. `rules/julia-code.md` and `julia-structure` route the question "which methods take
  this type" to Kaimon `search_methods` with the type as the query, which runs `methodswith(T)`;
  the rule names its blind spot, the methods of `T`'s supertypes.
