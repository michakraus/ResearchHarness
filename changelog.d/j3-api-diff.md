- **`dispatch-delta.jl --api` compares the public API of a head with a base, and `julia-release`
  runs it against the last release tag before it accepts the version.** Each side records its
  public names, by `Base.ispublic` in the root module and its public submodules, and for each own
  method whether it is API and its keyword names. In `--api` mode the head side runs after the base
  side, checks each base public name, and covers each base API method whose key it lacks by an
  own method with `sig <: m.sig`. It fails on a gone or demoted public name, an uncovered method, an
  own method on an external generic with no own cover, and a removed keyword; a key that does not
  evaluate gives no verdict. Step 2 of the release skill stops and asks where the check fails and
  the version is not breaking. The structure of a public type is not compared.
