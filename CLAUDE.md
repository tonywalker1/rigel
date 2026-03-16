# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

Rigel is a **language design project** — a strongly-typed, immutable-by-default, Scheme-derived
programming language with first-class constraint-based generics. It is designed around the thesis
that code should be optimized for AI writing and human reading, with rigor and tooling as the
primary differentiators.

The current deliverable is a language specification (`docs/rigel-spec.md`) and eventually a
compiler/transpiler that emits C. There is no build system yet; the project is in the design
phase.

## Source Files

- `docs/rigel-spec.md` — The living language specification. Edit this as design decisions are made.
- `docs/prompts/rigel-continuation-prompt.md` — Context prompt for resuming the design
  conversation in a new session.
- Source files will use the `.rgl` extension when the language is implemented.

## Key Design Decisions (Settled)

Read `docs/rigel-spec.md` for full details. Brief summary of non-obvious choices:

- **`def` is unified** — one keyword for immutable bindings, mutable bindings, reassignment, and
  function definitions. Parser disambiguates structurally (no ambiguity in S-expressions).
- **`int`, `float`, `number` are constraints, not types** — concrete types are `int32`, `float64`,
  etc. Familiar short names only appear in generic type parameter positions.
- **Qualifiers (`unsigned`, `unchecked`) are both modifiers and constraints** — safe defaults
  (signed, checked); opt into danger explicitly.
- **No type aliases** — `deftype` with an invariant is the only way to name a type. Forces
  semantic justification; compiler auto-generates constructor/viewer/release when not provided.
- **Algebraic effects** — declared in function signature via `:with (fail io)`. No `:with` means
  pure; compiler enforces this. Same effectful code runs with real or mock handlers.
- **Types are opaque by default** — `.field` access only inside the type's own methods.
- **RAII via `:release`** — runs at scope exit including effect-raise paths.
- **Compilation target: C** — monomorphization for generics, tail recursion → loops,
  checked arithmetic via `__builtin_add_overflow`. Runtime library may use C++.

## Open Design Questions

- Higher-level concurrency patterns (select/alt, cancellation, back-pressure)
- "One language, two forms" (compiled + interpreted with eval) theory — not yet
  fully elaborated in the spec

## Collaboration Notes

- The spec is the living document — update it as decisions are made
- The lead designer drives architectural decisions; fill in details, provide concrete examples in
  Rigel syntax, and push back when something is wrong
- Reference PL theory when relevant (lambda calculus, catamorphisms/anamorphisms, type classes)
- Connect design choices to C++, Scheme, Clojure, and Rust
