- **`skills/build-part/edges.md` names, under *A numerical method*, a widened exponent that a
  reader outside the part takes as one power of two.** A fix let a factor's scale exponent go below
  `-emax`, and a helper outside the part built `ldexp(one(R), -e)` from it, which is `Inf`, so the
  solve returned NaN; the critics' read of the part's own files passed it. The edge tells the
  planner to list every reader of a field or return value whose range the part widens, and to probe
  each one at the new ends of the range. The docs page on edges counts 53 entries for a numerical
  method.
