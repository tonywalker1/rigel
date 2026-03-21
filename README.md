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

**Early implementation.** The language specification is largely complete. The
interpreter (parse → type-check → evaluate) is working. The C compiler backend
is not yet implemented.

One language, two execution forms: compiled (transpiles to C) and interpreted.
Both share identical syntax and semantics — no interpreter-only features. The
interpreter is the compiler minus the C emission step.

## Key Features

- **S-expression syntax** — serialized AST, no parsing ambiguity
- **Declaration separate from definition** — `let` binds names; lambdas, types,
  constraints, and effects describe what they are
- **Unified function/closure model** — functions are lambdas bound with `let`;
  closures use explicit `:capture` declarations
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

## Getting Started

Requires Python 3.12+.

```bash
# Install the toolchain
git clone https://github.com/tonywalker1/rigel.git
cd rigel
pip install -e .

# Interpret a Rigel program
rigel run hello.rgl

# Type-check without running
rigel check hello.rgl

# Compile to C (not yet implemented)
rigel compile hello.rgl
```

A minimal Rigel program:

```scheme
(let main (lambda ()
    (print "hello, world")))
```

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

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community standards.

## License

[MIT](LICENSE)
