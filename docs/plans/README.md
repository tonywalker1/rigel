# Rigel Toolchain — Regenerative Build Plans

## Philosophy

This directory contains the **plans** from which the Rigel toolchain is generated. The plans are
the source of truth, not the generated code. Any component can be regenerated from its plan at
any time — analogous to rebuilding a container from its Dockerfile rather than mutating a running
system.

### Why Regenerative?

1. **The spec evolves.** When the language design changes, we update the spec, update the affected
   plans, and regenerate. No archaeology through months of accumulated patches.
2. **AI-native workflow.** The plans are written for an AI to consume and produce code from. Each
   plan is self-contained enough to be a single generation prompt.
3. **Fearless iteration.** Throwing away generated code is free. The investment is in the plans
   and the test suite, not in the implementation.
4. **Test suite as integration contract.** If every component can be regenerated and the tests
   still pass, the system is healthy.

### Invariant: Spec ↔ Test ↔ Plan

Every bug found in generated code triggers two actions:
1. Fix or clarify the spec (`docs/rigel-spec.md`) if the bug reveals ambiguity.
2. Add a test case to prevent regression.

The plan is then updated if needed, and the component regenerated.

## Implementation Language

**Phase 1 (current): Python.**

- S-expressions are trivial to parse in Python — the lexer/parser are ~100 lines.
- Iteration speed is critical in early design. Python lets us test language ideas in minutes.
- The data model (AST) is natural in Python dataclasses.
- No build system friction — `python -m pytest` runs the test suite.

**Phase 2 (future): C.**

- Once the language design stabilizes, we regenerate the toolchain in C.
- The regenerative approach makes this transition cheap: rewrite the plans for C, regenerate.
- The C version becomes the self-hosting foundation.

The transition point is when the spec is stable enough that we're spending more time on
performance than on language design.

## Plan Hierarchy

```
00-conventions.md          Shared style, error handling, data representation
01-data-model.md           AST node definitions, source locations
02-lexer.md                Tokenization of s-expression source text
03-parser.md               Token stream → AST
04-type-system.md          Constraint hierarchy, type representation, unification
05-semantic-analysis.md    Name resolution, type checking, effect checking
06-codegen-c.md            AST → C emission, monomorphization, tail-call optimization
07-runtime.md              Runtime library (refcounting, effects, persistent data structures)
08-driver.md               CLI entry point, pipeline orchestration
09-interpreter.md          Tree-walking evaluator (compiler minus codegen step)
10-test-suite.md           Test strategy and organization
```

## Dependency Graph

```
00-conventions ─────────────────────────────────────────────────────┐
       │                                                            │
01-data-model ──────────────────────────────────────┐               │
       │                                            │               │
02-lexer                                            │               │
       │                                            │               │
03-parser                                           │               │
       │                                            │               │
04-type-system ─────────────┐                       │               │
       │                    │                       │               │
05-semantic-analysis        │                       │               │
       │                    │                       │               │
       ├── 06-codegen-c ────┤── 07-runtime          │               │
       │                    │                       │               │
       └── 09-interpreter   │                       │               │
                            │                       │               │
08-driver ──────────────────┴───────────────────────┘               │
                                                                    │
10-test-suite ──────────────────────────────────────────────────────┘
```

## Vertical Slices

Rather than building all components to completion, we build in vertical slices — each slice
adds end-to-end capability.

**Slice 1 — Parse:** Plans 00–03 + 10. Source text → validated AST. Validates the regeneration
workflow itself.

**Slice 2 — Type:** Plans 04–05 + 10. AST → type-checked, effect-checked IR.

**Slice 3 — Run:** Plans 06–09 + 10. IR → executable (compiled or interpreted).

Each slice is usable on its own. Slice 1 gives us a syntax validator and pretty-printer.
Slice 2 gives us a type checker. Slice 3 gives us a working language.
