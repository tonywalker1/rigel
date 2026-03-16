# Rigel Language Design — Continuation Prompt

## Instructions

You are continuing a language design conversation about **Rigel** — a strongly-typed,
immutable-by-default, Scheme-derived language with first-class constraint-based generics.

The lead designer has deep experience in Linux, systems programming, C++, and
infrastructure-as-code, with formal training in compiler design (Scheme, lambda calculus).

The language is designed around a thesis about AI-assisted coding:

1. Refactoring is much easier with AI
2. Frameworks matter far less
3. Languages matter less
4. Code should be optimized for writing by AI and reading by humans
5. Rigor/structure and tooling are far, far more important

There is also a theory (not yet fully elaborated) that **we will really only need one language in
two forms: compiled and interpreted** (with eval capability). This hasn't been fully fleshed out
yet — ask about it when the moment is right.

The language is inspired by Scheme and Clojure. The current working spec is in the attached
`rigel-spec.md` file.

## Key Design Decisions Made

These are settled unless the lead designer reopens them:

### Syntax
- **S-expressions** as universal syntax (serialized AST, trivially parseable by AI)
- **Parentheses kept as-is** — whitespace-sensitivity rejected (a space/indent change silently
  alters program structure; antithetical to AI-writability and the serialized-AST principle);
  parenthesis fatigue accepted for now, revisit only after reading real code
- **Unified `def`** keyword for all bindings:
  - `(def [x : int32] 42)` — immutable binding
  - `(def mut [counter : int64] 0)` — mutable binding
  - `(def counter (+ counter 1))` — reassignment of mutable
  - `(def (add [a : int32] [b : int32]) -> int32 (+ a b))` — function definition
  - Parser disambiguates structurally — no ambiguity in S-expressions
- **`lambda`** remains separate (it produces a value, not a binding)
- File extension: `.rgl`

### Type System
- **Explicit concrete types**: `int8`, `int16`, `int32`, `int64`, `float32`, `float64` (not `int` or `float`)
- **Constraint names for generics**: `int`, `float`, `number` are constraints, not types
- **Qualifiers as composable modifiers AND constraints**: `unsigned`, `unchecked`
  - Defaults: signed, checked (safe)
  - `(def [x : int32 unsigned unchecked] 255)` — explicit opt-in to danger
- **`bool` is NOT a number** — explicit conversion required
- **Default literal types**: `int64` for integers, `float64` for floats; explicit suffix narrows: `42:int8`
- **Type labels via `as`**: `[a : int as T]` binds resolved concrete type to `T` within scope
- **Constraint composition via `&`** (single ampersand, not `&&`): `(& hashable eq)`
- **No type aliases / typedef** — if you want a new name, wrap with `deftype` and add an invariant
  - Compiler auto-generates default constructor, viewers, release when not provided
  - Nudges toward encoding semantics (e.g., `port-number` with range invariant)

### Data & Mutability
- **Immutable by default** — all bindings immutable unless `mut` specified
- **Two tiers of data structures**:
  - Persistent immutable: `list`, `vec` (RRB-tree), `map` (HAMT), `set` (HAMT)
  - Contiguous mutable: `array` (flat, cache-friendly, bounds-checked by default), `slice` (fat pointer), `buffer` (byte-oriented I/O)
- `array-get` is bounds-checked; `array-get-unchecked` is explicit opt-in (same pattern as arithmetic)
- Runtime may use C++ for high-quality data structure implementations

### Memory Model & Ownership
- **Ref-counted by default** for reference types — invisible to the user; the last reference frees allocation
- **`unique` qualifier**: single owner, move semantics, no ref-count overhead — opt-in for performance
- **`atomic` qualifier**: ref-counted with atomic operations, thread-safe shared mutable state — opt-in
- **`unique` and `atomic` join `unsigned` and `unchecked`** as explicit opt-ins in the qualifier system
- **Slices are fat pointers**: `(pointer, length, shared-ref-to-parent)` — cannot be orphaned; if parent
  is `unique`, compiler promotes to shared ownership at the slice point (no user annotation)
- **Thread boundary enforcement**: compiler detects `mut` (non-atomic) values crossing thread boundaries
  and errors with two options: use `unique` (transfer ownership) or `atomic` (shared access)
- **Immutable ref-counted data is inherently thread-safe**: no mutation possible, no locking needed
- **Design principle: easy to use, hard to misuse** — make illegal states unrepresentable; safe default,
  explicit opt-in to danger/performance; type system enforces correctness statically

### Types & Encapsulation
- **Types are opaque by default** — no direct `.field` access from outside
- **No inheritance** — containment + constraints + generic functions
- **RAII via `:release`** — cleanup runs automatically at scope exit, including early exits from effects
- **Viewer pattern** for controlled read access (pure functions, no `:with` allowed)
- `deftype` sections: `:opaque`, `:construct`, `:viewers`, `:methods`, `:release`, `:satisfies`, `:invariant`

### Effects System
- **Algebraic effects** for control flow (fail, io, yield, ask, user-defined)
- Effects declared in function signature via `:with (fail io)`
- **No `:with` = pure function** — compiler enforces this
- **Handlers** intercept effects: `(handle fail in ... :on [(raise msg) ...])`
- Same code runs with real handlers (production) or mock handlers (testing)
- Compilation: `fail` (non-resuming) → setjmp/longjmp; resumable effects → coroutine state machines; C++ in runtime for complex cases
- `result` type still available as a data type; handlers convert between effects and values

### Compilation
- **Target: C initially** (transpilation) — portability, FFI, debuggability
- LLVM backend is future option once semantics stabilize
- **Monomorphization** for generics (like C++ templates / Rust)
- **Tail recursion → loops** in generated C
- Checked arithmetic via `__builtin_add_overflow`
- Immutability → `const` everywhere in generated C
- **C++ allowed in the runtime library** (persistent data structures, ref counting, effect handlers) — the boundary is the generated code, not the runtime
- Mutual recursion TCO deferred (not in v0.1)

### Concurrency
- **Concurrency is an effect**, not a separate model — `concurrent` effect with `spawn`, `await`,
  `await-all` as effect operations; functions must declare `:with (concurrent)` to spawn work
- **Structured concurrency via effect scoping** — spawned tasks cannot outlive their handler scope;
  RAII/`:release` runs even if child tasks raise `fail`; compiler enforces this statically
- **Main is a task** — `main` receives the root `concurrent` handler from the runtime; not special,
  just the first task. Entry point: `(def (main [args : (vec string)]) -> int32 :with (io concurrent fail) ...)`
- **Channels for communication** — ownership-aware; sending `unique` moves ownership, sending immutable
  is always safe, sending `mut` non-`atomic` is a compile error (existing thread boundary rules)
- **`par-map` for pure parallelism** — requires function argument to have no `:with` clause (pure);
  compiler verifies purity via type system; runtime decides if parallelism is profitable
- **Handler determines runtime strategy** — same code runs on thread pool, green threads, or
  cooperative single-thread (bare metal); handler is the abstraction boundary

### Open Questions (deferred)
- **Higher-level concurrency patterns** — select/alt over channels, task cancellation, back-pressure,
  whether locks/mutexes are exposed at all
- **"One language, two forms"** — the theory that compiled and interpreted (eval) execution share
  the same syntax and semantics; not yet fully elaborated in the spec
- **C++ in the runtime** — generated code is C, but runtime library may use C++ for persistent data
  structures, ref counting, effect handlers, concurrency runtime

## Conversation Tone & Style

The lead designer engages at a very high technical level. They appreciate:
- Direct engagement with design tradeoffs
- Concrete code examples in the language itself
- Connections to C++, Scheme, Clojure, and Rust concepts
- Pushing back when something is wrong or could be better
- References to PL theory when relevant (lambda calculus, recursion schemes, type theory)
- Practical consideration of compilation and implementation strategy

The conversation is highly collaborative — the lead designer proposes core ideas (explicit types,
constraint names, no typedef, opaque-by-default, RAII) and the assistant fills in details (effects
system, C compilation strategy, grammar, examples). Continue in this mode.

## What To Do Next

The lead designer may want to:
1. Elaborate on the "one language, two forms" theory
2. Start implementing a parser or transpiler
3. Refine areas of the spec (higher-level concurrency patterns: select/alt,
   cancellation, back-pressure)
4. Discuss recursion schemes ("reducing" recursion analogous to differentiation
   — likely catamorphisms/anamorphisms from Meijer et al.)
5. Explore how the language interacts with AI-assisted coding workflows

Pick up wherever he leads. The spec file is the living document — edit it as decisions are made.
