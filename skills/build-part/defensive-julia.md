# Defensive Julia

How a builder writes Julia code that holds against the defects that reviews find. Before you write
`src/` code, read the section of this file for the code you write. `edges.md` says what a critic
probes; this file says how the code holds. A rule for test files is in
`~/.claude/rules/julia-tests.md`, and a rule for all Julia code is in
`~/.claude/rules/julia-code.md`; this file does not repeat them.

Each entry has a **Rule**, one `julia` block with the code that fails (`# fails`) and the code that
holds (`# holds`), a **Check** that a test makes, and an **Edge** line. The **Edge** line names the
section of `edges.md` and the opening words of the entry that the rule answers, or none. The names
in the code are examples.

**Contents**

- [Arguments and guards](#arguments-and-guards)
- [Element types and precision](#element-types-and-precision)
- [Floating-point arithmetic](#floating-point-arithmetic)
- [Types and interfaces](#types-and-interfaces)
- [Results, status and state](#results-status-and-state)
- [Scripts and processes](#scripts-and-processes)
- [Tests that can fail](#tests-that-can-fail)
- [Method-specific](#method-specific)

## Arguments and guards

### D1. Check the full shape of every array argument before the first write

**Rule:** A function compares `size(x)` with the full expected tuple, for every array argument,
before it reads or writes by index. Where the body indexes from 1, it refuses other axes.

```julia
# fails: a 3-row v passes; the rows of x past 2N drop silently
size(v, 2) == N || throw(DimensionMismatch("v has the wrong size"))
q, p = x[1:N, :], x[(N + 1):2N, :]

# holds
size(v) == (2, N) || throw(DimensionMismatch("v has size $(size(v)), expected (2, $N)"))
size(x, 1) == 2N || throw(DimensionMismatch("x has $(size(x, 1)) rows, expected $(2N)"))
Base.require_one_based_indexing(x)
```

- **Check:** a test per argument with one wrong extent (an extra row, a short vector, another
  grid, an `OffsetArray`), which expects `DimensionMismatch`; and each mixed pair of shapes.
- **Edge:** *A type or an interface*: "a size guard shared behind methods that dispatch on the
  shapes of both arguments", "an index form that the signature admits and the parent refuses";
  *A numerical method*: "an empty, a one-element or a zero-width case; the edge of a grid", "a
  recording fake that stores one property of its arguments".

### D4. Give a method only the arguments that its body can serve

**Rule:** A signature admits exactly the types that the body handles. A wider signature fails deep
inside with an unrelated error, or gives a wrong result; a missing method falls through to a
generic fallback.

```julia
# fails: a matrix passes here and fails deep in update!; a new factor type has no method
Field(grid, X::AbstractArray) = Field(grid, X, similar(X))
factor_parts(F::DenseLUData) = (F.L, F.U)

# holds: narrow the argument, give the abstract type a fallback, refuse the rest at entry
Field(grid, X::AbstractVector) = Field(grid, X, similar(X))
factor_parts(::AbstractLUData) = nothing
init(prob, x::StaticArray, alg) = throw(ArgumentError("init needs a mutable iterate"))
```

- **Check:** for each supertype, call every exported function on every subtype; for each refused
  type, `@test_throws` at the entry point, not inside.
- **Edge:** *A type or an interface*: "a default accessor on a supertype that one of the package's
  own subtypes cannot answer", "an untyped keyword that a length guard reads and a typed field
  rejects".

### D9. Use every argument, or refuse it

**Rule:** A function reads every argument and every keyword that it accepts. An argument that has
no effect raises an error, or the signature drops it. A wrapper forwards every keyword that it
names.

```julia
# fails: kwargs are dropped when options is given; initializer never reaches the inner call
solve(prob, x0; options = Settings(), kwargs...) = solve!(init(prob, x0, options))
Net(a, b; initializer = default_init, kwargs...) = Net(core(a), b; kwargs...)

# holds
function solve(prob, x0; options = nothing, kwargs...)
    options !== nothing && !isempty(kwargs) &&
        throw(ArgumentError("give options or keyword tolerances, not both"))
    return solve!(init(prob, x0, something(options, Settings(; kwargs...))))
end
Net(a, b; initializer = default_init, kwargs...) = Net(core(a), b; initializer, kwargs...)
```

- **Check:** for each keyword and each positional argument, a test with a value other than the
  default whose effect it observes; a test that two contradictory arguments raise.
- **Edge:** *A type or an interface*: "a parameter set read by position instead of by name".

### D13. Guard the domain of every argument at the entry point

**Rule:** The entry point states the valid range of each scalar argument and each structural
precondition, such as symmetry, and refuses the rest with an `ArgumentError` that names the
argument and its value.

```julia
# fails: a negative count builds and fails later; the sign check covers v > 0 only
Layer(n; nforcing) = new(n, nforcing)
all(q -> f[q] < 0, findall(>(0), v)) || throw(ArgumentError("f must oppose v"))

# holds
nforcing ≥ 0 || throw(ArgumentError("nforcing must be ≥ 0, got $nforcing"))
all(q -> v[q] * f[q] < 0, eachindex(v)) || throw(ArgumentError("f must oppose v"))
issymmetric(A) || throw(ArgumentError("a Cholesky factor needs a symmetric matrix"))
```

- **Check:** one case on each side of every bound (zero, a negative value, a reversed interval, a
  duplicate key, a non-permutation), each of which expects the guard's own message.
- **Edge:** *A numerical method*: "a first trial step of `Inf`, or above the caller's ceiling; an
  invalid ceiling".

### D20. Validate before the first side effect, in the constructor that every path uses

**Rule:** All checks run before the first write and before expensive work. An invariant lives in
the inner constructor, so `adapt`, `convert` and every outer constructor pass through it.

```julia
# fails: v is overwritten before the short history throws
function step!(v, dv_history, rhs)
    solve!(v, rhs)
    dv_history[:, 2] .= v                       # DimensionMismatch after v changed
end

# holds
function step!(v, dv_history, rhs)
    size(dv_history) == (length(v), 2) || throw(DimensionMismatch("history has the wrong size"))
    solve!(v, rhs)
    dv_history[:, 2] .= v
end
struct Rate{T}
    α::T
    Rate(α::T) where {T} = isfinite(α) && α > 0 ? new{T}(α) :
        throw(ArgumentError("α must be finite and positive, got $α"))
end
```

- **Check:** after each refused call, assert that every mutable argument is unchanged; build the
  object through each constructor and through `adapt`.
- **Edge:** none.

### D26. Decide the empty and the one-element input before a reduction or a `first`

**Rule:** A function that reduces or indexes its input decides the empty case: it returns the
neutral value, or raises an `ArgumentError` that says that the input is empty. Where a batch, a
difference or a plot needs two elements, it decides the one-element case too.

```julia
# fails: Base raises "reducing over an empty collection"; iterate reads c[1] of an empty c
l2dist(x, y) = sqrt(mapfoldl(z -> (z[1] - z[2])^2, +, zip(x, y)))
Base.iterate(c::Collection) = (c[1], 1)

# holds
l2dist(x, y) = sqrt(mapfoldl(z -> (z[1] - z[2])^2, +, zip(x, y); init = zero(eltype(x))))
Base.iterate(c::Collection, state...) = iterate(c.items, state...)
```

- **Check:** call every public function with a zero-length input (`Float64[]`, a `0:-1` range, a
  batch of zero samples) and with one sample.
- **Edge:** *A numerical method*: "an empty, a one-element or a zero-width case; the edge of a
  grid".

### D27. Accept every argument that converts without loss

**Rule:** A signature ties two arguments to one type parameter only where the body needs it. A
signature, a type guard or a type assertion accepts views, the other float type and integer
targets that the body converts.

```julia
# fails: a view beside an Array misses the method; an Int target misses it too
(loss::Loss)(model, ps, input::T, output::T) where {T} = loss.f(model(input, ps), output)
Loader(input::AbstractMatrix{T}, output::AbstractMatrix{T}) where {T} = make(input, output)

# holds
(loss::Loss)(model, ps, input::AbstractArray, output::AbstractArray) =
    loss.f(model(input, ps), output)
Loader(input::AbstractMatrix{T}, output::AbstractMatrix{S}) where {T, S <: Union{T, Integer}} =
    make(input, output)
```

- **Check:** call with a view, a `SubArray` beside an `Array`, a `Float32` beside a `Float64`
  argument, and an `Int` target.
- **Edge:** *A type or an interface*: "an argument of another integer type, such as `Int32`".

### D28. Refuse a non-finite input, or document that it propagates

**Rule:** A function that cannot give a meaningful result for `NaN` or `Inf` refuses it at entry.
A function that drops non-finite data says so in its docstring.

```julia
# fails: a NaN snapshot gives a basis with a NaN spectrum; m = NaN passes `m ≤ 0 && throw`
basis = svd(S).U[:, 1:k]
m ≤ zero(T) && throw(ArgumentError("mass must be positive"))

# holds
all(isfinite, S) || throw(ArgumentError("the snapshot has a non-finite entry"))
m > zero(T) || throw(ArgumentError("mass must be positive, got $m"))
```

- **Check:** a case with `NaN` and one with `Inf` per public entry point.
- **Edge:** *A numerical method*: "`NaN` and `Inf` in an input, and at a trial point".

### D29. Throw the documented exception with a message that names the cause

**Rule:** User input is refused with `ArgumentError` or `DimensionMismatch`, never with `@assert`.
Two guards of one kind of fault throw one exception type. The message names the argument, the value
and the expectation, and shows sizes, not whole arrays.

```julia
# fails: @assert can be disabled; the message prints every array of the axes
@assert size(input, 3) == size(output, 3)
throw(ArgumentError("bad axes $(axes(t))"))

# holds
size(input, 3) == size(output, 3) || throw(ArgumentError(
    "input has $(size(input, 3)) samples and output $(size(output, 3))"))
throw(ArgumentError("bad axes, sizes $(map(size, axes(t)))"))
```

- **Check:** `@test_throws` per refused case, and `length(sprint(showerror, e)) < 200`.
- **Edge:** none.

## Element types and precision

### D2. Compute the result type from every input

**Rule:** A result, a buffer or an accumulator takes `promote_type` of every input that reaches
it. It never takes the type of the first element, of one argument or of a literal. An integer
element type goes through `float` before a division.

```julia
# fails: a Float32 basis with Float64 data gives ±Inf32; the Float64 literal promotes Float32
T = eltype(runs[1].q[1]); Z = zeros(T, n, m)
out = similar(basis, n)
rms(dx) = sqrt(sum(abs2, dx)) / √length(dx)
c = zeros(promote_type(eltype(a), eltype(b)), n); c .= a ./ b    # InexactError for two Int

# holds
T = mapreduce(r -> eltype(r.q[begin]), promote_type, runs); Z = zeros(T, n, m)
out = similar(basis, promote_type(eltype(basis), eltype(coords)), n)
rms(dx) = sqrt(sum(abs2, dx) / oftype(real(zero(eltype(dx))), length(dx)))
c = zeros(float(promote_type(eltype(a), eltype(b))), n); c .= a ./ b
```

- **Check:** each public function with a `Float32` and `Float64` pair in every argument order;
  `@test eltype(result) == promote_type(...)` and a finite result.
- **Edge:** *A type or an interface*: "a copy removed by preallocating the result with
  `similar(operand, …)`"; *A numerical method*: "a `Float32` precision row whose fixture builds
  its scale as a `Float64` literal".

### D19. Narrow a value only after the work that needs its range

**Rule:** Subtract, scale and divide in the wide type; convert to the narrow type last. A range
check runs on the converted value. A silent narrowing into a caller's buffer is refused.

```julia
# fails: 1e8 and 1e8 + 1 both round to 1e8f0, so the division gives NaN
Q(knot_j) - Q(knot_i)
d .= T.(rhs) .* frac                            # a subnormal entry rounds to 0 in Float16
0 < x ≤ 1 || throw(ArgumentError("x out of range")); y = T(x)    # T(x) can round to 0

# holds
Q(knot_j - knot_i)
d .= T.(rhs .* frac)
y = T(x); 0 < y ≤ 1 || throw(ArgumentError("x is $x, which rounds to $y in $T"))
promote_type(eltype(buf), R) === eltype(buf) ||
    throw(ArgumentError("a buffer of $(eltype(buf)) would round $(R) values"))
```

- **Check:** inputs near the narrow type's limits (`1e8` in `Float32`, a subnormal in `Float16`),
  and a narrow buffer, or an integer one, with wide data.
- **Edge:** *A numerical method*: "the other precision: `Float32` and `Float64`", "a subnormal
  input".

### D25. Keep generic element types generic

**Rule:** Code that a `ForwardDiff.Dual`, a `BigFloat` or another non-`isbits` type can reach
builds its buffers from that type, and calls no method that is defined only for hardware floats.

```julia
# fails: a zero leaf takes the primal eltype beside Dual leaves; the cache fixes an inner solver
zero_leaf(x) = zero(x)
Workspace{T}() where {T} = (; work = Vector{T}(), inner = InnerSolver{T}())

# holds
zero_leaf(x, Δ) = zero(similar(x, eltype(Δ)))
Workspace{T}() where {T} = (; work = Vector{T}())   # the inner solver lives in the model
```

- **Check:** one call per public entry point with `ForwardDiff.Dual` arguments and one with
  `BigFloat`.
- **Edge:** *A type or an interface*: "a non-`isbits` element type, such as `BigFloat`, on a path
  that builds an `MMatrix`".

## Floating-point arithmetic

### D10. Scale before a product, a square or a conversion can overflow

**Rule:** A norm, a Gram matrix, a power or a narrowing conversion of unscaled data first divides
by a power of two of the data's magnitude, and rescales the result.

```julia
# fails: Inf above sqrt(floatmax); 1/|u|³ and |u|^(γ+3) overflow apart
fnorm = sqrt(sum(abs2, F))
K = (I / nd - u * u' / nd^3) * nd^(γ + 3)

# holds
fnorm = norm(F)                                 # LinearAlgebra scales inside
û = u / hypot(u...); K = nd^(T(γ) + 2) * (I - û * û')
s = 2.0^exponent(maximum(abs, J)); J32 .= T.(J ./ s)    # then rescale the solution by s
```

- **Check:** inputs scaled by `1e±160` (`Float64`) and `1e±30` (`Float32`) against a `BigFloat`
  reference.
- **Edge:** *A numerical method*: "a square or a product of unscaled quantities", "one scale formed
  as a scalar and applied to the whole gradient", "a scale by the largest absolute entry".

### D14. Write the form that does not cancel

**Rule:** Where a difference of nearly equal values feeds the result, write the algebraically equal
form that avoids it, and state the accuracy against a `BigFloat` reference. A finite-difference
step scales with the point.

```julia
# fails: 0 for θ = 1e-9; σ(1-σ) is 0 at 20f0; the Gram matrix squares the condition number
p = sqrt(2g * l * (1 - cos(θ)))
d2 = σ(x) * (1 - σ(x))
U = eigen(Symmetric(S * S')).vectors
h = 1e-6; df = (f(x + h) - f(x)) / h

# holds
p = 2 * sqrt(g * l) * abs(sin(θ / 2))
d2 = σ(x) * σ(-x)
U = svd(S).U
h = cbrt(eps(T)) * max(one(T), abs(x)); df = (f(x + h) - f(x - h)) / 2h
```

- **Check:** the value at the far end of the domain against `BigFloat`; a graded spectrum over 8
  decades for a factorisation; a point of magnitude `1e6` for a finite difference.
- **Edge:** *A numerical method*: "a clause that asks a difference of two nearly equal numbers to
  keep its relative accuracy", "a finite-difference reference whose error the check divides by a
  quantity that can approach zero".

### D16. Compare floats, ranges and ties on purpose

**Rule:** A float comparison names its tolerance and its reference scale. A grid is built with
`range(a, b; length = n)`, not with a float step, and refuses a cell whose width rounds to zero. A
tie decides by an explicit second key.

```julia
# fails: ≈ against 0 never holds; a:h:b stops one point short; argmax keeps the input order
last(xgrid) ≈ 0 || throw(ArgumentError("the grid must end at 0"))
xgrid = a:h:b
finest = argmax(r -> length(r["x"]), runs)

# holds
abs(last(xgrid)) ≤ sqrt(eps(T)) * max(h, abs(a), abs(b)) ||
    throw(ArgumentError("the grid must end at 0"))
xgrid = range(a, b; length = round(Int, (b - a) / h) + 1)
all(>(0), diff(xgrid)) || throw(ArgumentError("a cell of the grid has zero width"))
finest = argmin(r -> (-length(r["x"]), r["timestep"]), runs)
```

- **Check:** random spans with `h = (b - a) / m` assert `last(xgrid) == b`; a pair one ulp apart;
  a span a few ulps wide; a tie in the sort key.
- **Edge:** *A numerical method*: "a tie that round-off decides".

### D32. Guard a division by a quantity that can be zero

**Rule:** A relative measure, a normalisation or a quotient checks its denominator, or takes the
limit where one exists. A derivative that divides by the quantity, such as the derivative of a
determinant through its inverse, takes a form that has no division.

```julia
# fails: Inf on a batch at the equilibrium; refuses f = 0 where f log|f| → 0
loss = norm(ŷ - y) / norm(y)
f > 0 || throw(DomainError(f))

# holds
ny = norm(y); loss = iszero(ny) ? norm(ŷ - y) : norm(ŷ - y) / ny
flogf(f) = iszero(f) ? zero(f) : f * log(abs(f))
```

- **Check:** a zero reference, an equilibrium point, a zero variance, a singular matrix.
- **Edge:** *A numerical method*: "a penalty built on a determinant of a matrix that can be
  singular".

### D33. Do integer arithmetic that cannot wrap or throw

**Rule:** Index arithmetic on large or user-given counts uses checked or widened operations, or
refuses a count above a limit that it states. A float that goes to an integer type is checked
finite and in range first. Unsigned values are not subtracted.

```julia
# fails: floor(Int, NaN) throws InexactError; UInt8 targets wrap; (2w + 1)^D wraps
i = floor(Int, (x - xa) / Δx) + 1
errors = sum(abs.(output .- predicted)) / 2
len = (2w + 1)^D

# holds
isfinite(x) || return nothing
i = floor(Int, (x - xa) / Δx) + 1
errors = sum(max.(output, predicted) .- min.(output, predicted)) / 2
len = Base.checked_pow(Base.checked_add(Base.checked_mul(2, w), 1), D)
```

- **Check:** `typemax(Int) ÷ 2`, `NaN`, a `UInt8` target.
- **Edge:** *A type or an interface*: "a stencil width whose length `(2w+1)^D` overflows `Int`".

## Types and interfaces

### D18. Tie every type parameter to what the fields hold

**Rule:** A type parameter that names an element type is bound by the field types, so `eltype` and
`getindex` agree; a state type gives separate parameters to values of different types.

```julia
# fails: getindex returns Float64 where eltype says Float32
struct Coefficients{DT, VT}; v::VT; end
Base.getindex(t::Tensor{DT}, i...) where {DT} = parent(t)[i...]

# holds
struct Coefficients{DT, VT <: AbstractVector{DT}}; v::VT; end
Base.getindex(t::Tensor{DT}, i...) where {DT} = convert(DT, parent(t)[i...])
```

- **Check:** `@test typeof(x[1]) == eltype(x)`; `@inferred` on the accessor.
- **Edge:** none.

### D35. Define `hash` with `==`, and keep interface methods consistent with their fallbacks

**Rule:** A type that defines `==` defines `hash` over the same fields. A method of an
`AbstractArray` or an iteration interface agrees with the generic fallback outside its own range.

```julia
# fails: unique([r, deepcopy(r)]) has two entries; size(w, 4) throws
Base.:(==)(a::Record, b::Record) = a.x == b.x && a.v == b.v
Base.size(w::Wrapped, i) = (w.m, w.n, w.k)[i]

# holds
Base.hash(r::Record, h::UInt) = hash(r.x, hash(r.v, h))
Base.size(w::Wrapped) = (w.m, w.n, w.k)         # the fallback gives size(w, i) = 1 for i > 3
```

- **Check:** `@test hash(r) == hash(deepcopy(r))`; `@test size(x, ndims(x) + 1) == 1`.
- **Edge:** none.

### D17. Keep the exported surface consistent

**Rule:** Every export names a local binding with a method. Sibling entry points accept the same
keywords, with the same defaults. `solve` and `solve!(init(...))` give the same result and the same
side effects.

```julia
# fails: no local `run` remains, so the module exports Base.run
export run
x, status = solve(args...)                      # while solve!(init(args...)) returns status

# holds: `export run` is deleted, and the two forms agree
x, status = solve(args...); @test (x, status) == solve!(init(args...))
```

- **Check:** for each export, `parentmodule(getfield(M, n)) === M` and `!isempty(methods(f))`;
  the same keyword set and defaults on every entry point.
- **Edge:** none.

## Results, status and state

### D6. Report success only after checking the claim

**Rule:** A solver, a combinator or a step returns success only after it checks the residual, the
finiteness of the iterate and the status of every inner solve. Every count and every norm that the
result reports describes the steps taken. A failure keeps the last valid state.

```julia
# fails: a zero rotated diagonal gives resnorm 0 and converged = true on a singular J
radius == 0 && (cs = one(T); sn = zero(T))
return :success                                 # whatever the inner solve returned

# holds
inner.status === :success || return :maxiters
isfinite(fnorm) || return :nonfinite            # the iterate stays at the last finite point
converged = resnorm ≤ tol * bnorm               # resnorm keeps g[j] on breakdown
```

- **Check:** a singular, a non-finite and a non-converging case per method, each of which asserts
  a status other than success; for success, an independent residual check of the returned point.
- **Edge:** *A numerical method*: "a status that hides a failure", "a stationary point that is a
  maximum".

### D8. Copy what you store; key a cache on what its contents depend on

**Rule:** A value stored beside a result, a returned view or a converted argument is a copy, unless
the docstring states the aliasing. A cache checks the identity of what its tables depend on, and
shared state is rebuilt at the point where each reader expects it.

```julia
# fails: every stored entry equals the last; convert returns the caller's array
push!(sol.vals, cache.v)
index = convert(Vector{Int}, index)

# holds
push!(sol.vals, copy(cache.v))
index = collect(Int, index)
dist.quadrature === cache.quadrature || throw(ArgumentError("cache built for another quadrature"))
Base.mightalias(vn, history) && throw(ArgumentError("vn shares memory with history"))
```

- **Check:** a fixture whose value changes per step; a mutation of the caller's argument after
  construction; a call with an argument of the same size, built from another object.
- **Edge:** *A numerical method*: "a value read out of a live cache and stored beside the
  solution", "a function that reads tables a cache built from one object"; *A type or an
  interface*: "a constructor that stores the caller's mutable argument".

### D7. Keep a device array on its device

**Rule:** Device code allocates from `get_backend(x)`, passes `isbits` arguments to kernels,
indexes no element on the host, and picks a backend from the array, not from a wrapper type.

```julia
# fails: a JLArray broadcast reads a host Matrix; the closure captures a Type, not isbits
enc = zeros(T, n)
mapreduce(x -> exponent(R(abs(x))), max, A)

# holds
enc = KernelAbstractions.zeros(get_backend(x), T, n)
mapreduce(ExponentOf{R}(), max, A)              # a functor that captures nothing
@test get_backend(out) == get_backend(x)
```

- **Check:** each path under `allowscalar(false)` on `JLArray`; a device claim measured on the
  device itself, in `test/devices/`; `isbits(Adapt.adapt(backend, arg))` for each kernel argument.
- **Edge:** *A type or an interface*: "a device array under `allowscalar(false)`", "a device claim
  read from a `JLArray` run", "a host array mixed into a device broadcast", "the scalar-indexing
  state restored by copying one value into both stores", "the backend of a result", "the precision
  of a device".

### D5. Allocate nothing on a hot path that the clause says is free

**Rule:** A function that runs per step, per point or per call holds its buffers in a cache that
is built once, writes in place, and calls a function barrier where a type is known only at run
time.

```julia
# fails: zeros(n) at every call; fit_coefficients allocates at every step
function rhs!(r, x, c)
    u = zeros(n)
    coeffs = fit_coefficients(basis, f)
end

# holds
function rhs!(r, x, c)
    u = c.u                                     # allocated once in the cache
    fit_coefficients!(c.coeffs, basis, f, c.work)
end
```

- **Check:** `@test (@allocated rhs!(r, x, c)) == 0` after a warm-up, behind a function
  barrier, at two sizes.
- **Edge:** *A type or an interface*: "a mutable static array offered as an iterate", "a batch
  applied by indexing one sample per step".

### D24. Measure the thing that the claim is about

**Rule:** A timing warms the code, synchronises the device before and after, pins the BLAS
threads, times the first call where compile time matters, and records the conditions beside the
number.

```julia
# fails: device work of the warm-up lands in the first sample; build time stands for the first call
f(x); t = @elapsed (f(x); synchronize())
t = @elapsed g = generate_gradient(m)

# holds
BLAS.set_num_threads(1)
f(x); synchronize(); t = @elapsed (f(x); synchronize())
t_build = @elapsed g = generate_gradient(m); t_first = @elapsed g(x)
```

- **Check:** the first timed sample against the later ones; a script that asserts
  `BLAS.get_num_threads()`.
- **Edge:** *A numerical method*: "an untimed warm-up of a device measurement"; *A type or an
  interface*: "a cost premise that times the build of a generated function".

## Scripts and processes

### D15. Keep a failure visible in the output

**Rule:** A script writes each result when it is measured, removes or marks the output of a failed
run, and never archives a truncated or unconverged run as a success.

```julia
# fails: rows are collected and written at the end; a run that stopped early is stored
rows = [time_case(c) for c in cases]; write_csv(path, rows)
save_run(stem, data(run_case(problem)))

# holds
open(path, "w") do io
    for c in cases; println(io, format_row(time_case(c))); flush(io); end
end
r = run_case(problem)
length(r.traces) == nsteps || error("$(stem): the run stopped at step $(length(r.traces))")
save_run(stem, data(r))
```

- **Check:** a throw injected in the middle of a run, then a read of the file; a run that stops
  early counts as failed.
- **Edge:** none.

### D21. Signal and wait on the process group, with a bound

**Rule:** Code that runs a child kills and waits on its process group, reads the PID straight after
`run`, keeps a handle to every `Timer` and closes it on every exit, and bounds every wait.

```julia
# fails: descendants survive; the timer fires on a reused group ID after return
kill(p, Base.SIGKILL)
Timer(_ -> signal_group(group, Base.SIGKILL), 5)

# holds
killer = Ref{Union{Nothing, Timer}}(nothing)
try
    killer[] = Timer(_ -> signal_group(group, Base.SIGKILL), 5)
    timedwait(() -> !group_alive(group), 10.0)
finally
    killer[] === nothing || close(killer[])
end
```

- **Check:** a child that ignores SIGINT and forks a grandchild; a child that exits at once, in a
  loop under load.
- **Edge:** *A step that runs a user's script*: "a child started in a session of its own", "a test
  that a killed child is gone", "a PID read from a Julia `Process` after a call that yields".

### D30. Parse command-line options strictly

**Rule:** A script parses `ARGS` and `ENV` in one function, refuses an unknown flag, a missing
value and an out-of-range number with an `ArgumentError`, and runs no check at the top level of an
included file.

```julia
# fails: unknown flags pass; --results-dir as the last argument reads past the end
for (i, a) in enumerate(args); a == "--results-dir" && (dir = args[i + 1]); end

# holds
function parse_arguments(args)
    options = Dict{String, String}()
    i = 1
    while i ≤ length(args)
        a = args[i]
        a in FLAGS || throw(ArgumentError("unknown flag $a"))
        i < length(args) || throw(ArgumentError("$a needs a value"))
        options[a] = args[i + 1]
        i += 2
    end
    return options
end
```

- **Check:** `@test_throws r"^ArgumentError: unknown flag --bogus$" parse_arguments(["--bogus"])`,
  and the flag without a value.
- **Edge:** none.

### D31. Make the exit status say what happened

**Rule:** A script or a probe exits non-zero when a check fails or when every backend fails. A
process that a signal kills counts as a failure.

```julia
# fails: prints the disagreement and exits 0; SIGABRT gives exitcode 0
@printf("agrees: %s\n", d == p)
ok = p.exitcode == 0

# holds
d == p || error("the probe and the reference disagree")
ok = success(p)                                 # false on a signal
```

- **Check:** run the script against a diverged copy, and a child that aborts; assert a non-zero
  status.
- **Edge:** none.

## Tests that can fail

The test side of these entries is a bullet of `~/.claude/rules/julia-tests.md`, which loads with
every test file. An entry here keeps the `src/` side, where it has one, and links to its bullet.

### D3. Give every branch, keyword and stated property a test

**Rule:** the bullet "Every branch, keyword value, component and stated property has a test" of
`julia-tests.md`. The rule has no `src/` side.

- **Edge:** none.

### D11. Derive each tolerance from its error source

**Rule:** the bullet "A tolerance comes from the error source of the computed value" of
`julia-tests.md`. In `src/`, a default tolerance comes from the same derivation, not from a value
tuned until a test passes.

```julia
# fails: a constant tuned until the test passes
default_reltol(::Type{Float32}) = 3.0f-2

# holds: the rounding and the truncation error of a difference with the step δ
default_reltol(::Type{T}, δ) where {T} = 10 * (δ + eps(T) / δ)
```

- **Check:** one input inside the bound and one outside; a mutant must exceed the bound.
- **Edge:** *A numerical method*: "a test of a decided threshold brackets it"; *A migration of
  tests or of text*: "a round-off tolerance given as a constant relative factor", "a decided bound
  whose evidence was measured in another metric", "a moved test that gains a `Float32` run".

### D12. Pick fixtures where every factor and component differs

**Rule:** the bullet "A fixture gives each factor a value other than 1" of `julia-tests.md`. The
rule has no `src/` side.

- **Edge:** *A migration of tests or of text*: "a constant factor of a formula tested only where it
  equals 1", "a mutant that only an error bound over a window can kill"; *A numerical method*: "a
  control of a seeded problem generator".

### D22. Write a guard message that only the guard writes

**Rule:** the bullet "`@test_throws` matches a phrase that only the guard writes" of
`julia-tests.md`. In `src/`, each guard writes a phrase that no library error and no other guard
writes, so a test can tell it apart.

```julia
# fails: Base's matrix product writes "a matrix of size" too
size(A, 2) == length(x) || throw(DimensionMismatch("a matrix of size $(size(A))"))

# holds
size(A, 2) == length(x) ||
    throw(DimensionMismatch("solve!: x has length $(length(x)), A has $(size(A, 2)) columns"))
```

- **Check:** remove the guard; the test that matches its phrase must fail, not error.
- **Edge:** *A part that predicts what another tool reads or does*: "a guard's phrase that a
  library error also writes", "a case meant for one guard that a *later* guard",
  "a refusal message that names several values"; *A migration of tests or of text*: "a reworded
  error message in an upstream package".

### D23. Take the reference from a method that can be right where the code is wrong

**Rule:** the bullet "A reference value comes from a method that can be right where the code is
wrong" of `julia-tests.md`. In `src/`, a function that makes a reference runs in wider precision,
to a stated stop, and returns a converged result only.

```julia
# fails: the reference comes from the method under test, and an unconverged run is kept
make_reference(prob, u0, alg) = solve(prob, u0, alg).u

# holds: alg is not the method that the reference measures
function make_reference(prob, u0, alg)
    r = solve(prob, big.(u0), alg; abstol = big"1e-60")
    r.converged || error("the reference run did not converge")
    return r.u
end
```

- **Check:** the reference's own error is far below the smallest error that it measures.
- **Edge:** *A numerical method*: "a reference solved by the same method from the same start".

## Method-specific

### D34. Match the index rule to the boundary condition of the axis

**Rule:** A periodic wrap or reflection applies only to a periodic axis; a bounded axis uses its own
rule, and a function that gets the wrong kind of axis refuses it.

```julia
# fails: mod1 on a bounded grid
k = mod1(j + 1, nv)

# holds
k = axis isa PeriodicAxis ? mod1(j + 1, nv) : j + 1
axis isa PeriodicAxis || 1 ≤ k ≤ nv || throw(BoundsError(axis, k))
```

- **Check:** the boundary rows against a dense reference on a bounded axis; the parity blocks on a
  periodic axis.
- **Edge:** none.

### D36. Build the basis that the index rule of its consumer assumes

**Rule:** A basis passed to a coupling has the boundary condition that the coupling's corner or
index rule is written for, and the test pins the count against a basis of a stated condition.

```julia
# fails: the corner rule drops two interior functions of a Dirichlet basis
trace = build_basis(degree, ncells; boundary = :dirichlet)

# holds
trace = build_basis(degree, ncells; boundary = :free)
@test nmultipliers(coupling) == expected_count(:free, degree, ncells)
```

- **Check:** the rank of the multiplier set against the dimension of the space that it spans.
- **Edge:** *A numerical method*: "a trace basis whose boundary condition silently shrinks the
  space its coupling's corner rule assumes".

### D37. Count a schedule in the unit that it advances in, and give it a floor

**Rule:** The horizon of a schedule is the number of steps that it advances, not epochs, and its
value stays at the floor after the horizon.

```julia
# fails: the schedule advances per minibatch
schedule = DecaySchedule(nepochs)

# holds
schedule = DecaySchedule(nepochs * nbatches)
η(t) = t ≥ n ? η₂ : decay(t)
```

- **Check:** the rate at the last step equals `η₂`; the rate after the horizon equals `η₂`.
- **Edge:** none.

### D38. Keep a sparse pattern closed under the operations applied to it

**Rule:** Code that adds to a sparse matrix in place, such as a diagonal shift, first adds the
structural entries that it writes to the pattern.

```julia
# fails: J[i, i] += μ on a pattern without a structural diagonal
J[i, i] += μ

# holds: before the factorisation, where the shift is not zero
pattern = pattern .| sparse(I, n, n)
```

- **Check:** a shift of `1e-10` with a residual whose pattern is a permutation, and an explicit
  prototype without a diagonal.
- **Edge:** none.
