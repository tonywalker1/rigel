# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

Rigel is a **language design project** — a strongly-typed, immutable-by-default, Scheme-derived
programming language with first-class constraint-based generics. Inspired by Scheme and Clojure.

It is designed around a thesis about AI-assisted coding:

1. Refactoring is much easier with AI
2. Frameworks matter far less
3. Languages matter less
4. Code should be optimized for writing by AI and reading by humans
5. Rigor, structure, and tooling are far more important than syntax sugar

The current deliverable is a language specification (`docs/rigel-spec.md`) and eventually a
compiler/transpiler that emits C. There is no build system yet; the project is in the design
phase.

## Source Files

- `docs/rigel-spec.md` — The living language specification. Edit this as design decisions are made.
- `docs/tutorial.md` — Tutorial for programmers learning Rigel.
- Source files will use the `.rgl` extension when the language is implemented.

## Key Design Decisions (Settled)

Read `docs/rigel-spec.md` for full details. Brief summary of non-obvious choices:

- **Declaration separate from definition** — `let` binds names to values. Naming is orthogonal
  to what is being named (a value, a lambda, a type, a constraint, an effect). Reassignment
  uses `set`. No unified `def` keyword.
- **Unified function/closure model** — functions and lambdas are the same construct (`lambda`).
  A "function" is a lambda with no captures, bound with `let`. Lambda syntax uses keyword
  sections: `(:args ...)`, `(:capture ...)`, `(:returns T)`, `(:with (E))`. Closures use
  `(:capture ...)` to explicitly declare closed-over bindings. Self-capture enables recursion.
- **`int`, `float`, `number` are constraints, not types** — concrete types are `int32`, `float64`,
  etc. Familiar short names only appear in generic type parameter positions.
- **Qualifiers (`unsigned`, `unchecked`) are both modifiers and constraints** — safe defaults
  (signed, checked); opt into danger explicitly.
- **No type aliases** — `(let name (type ...))` with an invariant is the only way to name a type.
  Forces semantic justification; compiler auto-generates constructor/viewer/release when not
  provided.
- **Algebraic effects** — declared in lambda keyword section via `(:with (fail io))`. No `:with`
  means pure; compiler enforces this. Same effectful code runs with real or mock handlers.
- **Types are opaque by default** — `.field` access only inside the type's own methods.
- **RAII via `:release`** — runs at scope exit including effect-raise paths.
- **Compilation target: C** — monomorphization for generics, tail recursion → loops,
  checked arithmetic via `__builtin_add_overflow`. Runtime library may use C++.
- **One language, two forms** — compiled and interpreted share identical syntax and semantics.
  The interpreter is the compiler minus the C emission step. No interpreter-only features.

## Open Design Questions

- Dictionary-based parameter model — lambda parameters (captures, args, locals) as a single
  dictionary; recursive self-calls carry forward the full dictionary, updating only named entries
- Named arguments — if the dictionary model is adopted, arguments are passed by name rather than
  position
- Higher-level concurrency patterns (select/alt, cancellation, back-pressure)
- C++ in the runtime — generated code is C, but runtime may use C++ for
  persistent data structures, ref counting, effect handlers, concurrency

## Collaboration Notes

- The spec is the living document — update it as decisions are made
- The lead designer drives architectural decisions; fill in details, provide concrete examples in
  Rigel syntax, and push back when something is wrong
- Reference PL theory when relevant (lambda calculus, catamorphisms/anamorphisms, type classes)
- Connect design choices to C++, Scheme, Clojure, and Rust
- Direct engagement with design tradeoffs — include practical compilation/implementation concerns
- The collaboration is highly collaborative: the lead designer proposes core ideas, the assistant
  fills in details (effects system, C compilation strategy, grammar, examples)

## Implementation Notes

### Upstream IR Audits
Before implementing any compiler phase, audit that all upstream IR nodes carry the data the new
phase needs. Walk each `TXxxForm` and verify every field the evaluator/emitter needs is present.
Missing fields require a checker change first, before any interpreter/codegen work begins.

### Current Checked IR Invariants
- `TLetForm.mutable: bool` — needed by interpreter to enforce set() permission
- `THandleForm.handlers: list[tuple[str, list[str], TypedExpr]]` — carries
  `(effect_name, param_names, handler_body)` so the interpreter can bind effect args to params
- Wildcard `_` in match patterns is handled specially in both checker (`_check_match`) and
  interpreter (`_eval_match`) — not looked up as a name

### Bracket Syntax Is Canonical
Lambda parameters use `[name : type]` syntax. Paren syntax `(name type)` is legacy and should
not appear in new code, tests, or examples. Captures use `[name]` (mutable: `[mut name]`).

### Plans Must Stay Ahead of Implementation
The user implements independently and rapidly once plans are in place. Stub plans are liabilities.
When asked to elaborate plans, treat it as urgent work-in-progress, not documentation cleanup.
Each plan should include a **"Prerequisites / Upstream Gaps"** section listing what needs to be
fixed in previous phases before this plan can be implemented cleanly.

## Possible Next Steps

- Start implementing a parser or transpiler
- Flesh out the dictionary-based parameter model and named arguments
- Refine higher-level concurrency patterns (select/alt, cancellation, back-pressure)
- Discuss recursion schemes (catamorphisms/anamorphisms from Meijer et al.)
- Explore how the language interacts with AI-assisted coding workflows
