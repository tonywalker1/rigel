# Rigel

A strongly-typed, immutable-by-default, Scheme-derived programming language with
first-class constraint-based generics.

## Design Thesis

Rigel is built around a thesis about AI-assisted coding:

1. Refactoring is much easier
2. Frameworks matter far less
3. Languages matter less
4. Code should be optimized for writing by AI and reading by humans
5. Rigor, structure, and tooling are far more important than syntactic sugar

The language uses S-expressions as a universal syntax — the source *is* a
serialized AST, trivially parseable by both humans and LLMs. There is no
ambiguous grammar and no operator precedence. The type system enforces
correctness statically wherever possible, with safe defaults and explicit
opt-in to danger.

## Status

**Design phase.** The language specification is largely complete. No compiler
exists yet.

One language, two execution forms: compiled (transpiles to C) and interpreted
(REPL/eval). Both share identical syntax and semantics — no interpreter-only
features. The interpreter is the compiler minus the C emission step.

## Key Features

- **S-expression syntax** — serialized AST, no parsing ambiguity
- **Explicit concrete types** — `int32`, `float64` (not `int`, `float`)
- **Constraint-based generics** — `int`, `float`, `number` are constraints for
  generic programming, not types
- **Immutable by default** — `mut` is explicit opt-in
- **Safe by default** — checked arithmetic, bounds-checked arrays; `unchecked`
  and `unsigned` are explicit opt-ins
- **Algebraic effects** — side effects declared in function signatures; the
  compiler enforces purity
- **Opaque types with RAII** — no inheritance; containment + constraints +
  automatic resource cleanup
- **Structured concurrency** — concurrency is an effect; spawned tasks cannot
  outlive their handler scope
- **Compilation target: C** — monomorphization, tail recursion to loops,
  runtime may use C++

## Documentation

| File | Description |
|------|-------------|
| [Language Specification](docs/rigel-spec.md) | The living spec — the source of truth |
| [Tutorial](docs/tutorial.md) | Learn Rigel in one sitting |

## Inspirations

Scheme, Clojure, Rust, C++. The type system draws from Haskell's type classes
and Rust's traits. The effects system draws from algebraic effects research
(Eff, Koka, OCaml 5).

## File Extension

`.rgl`
