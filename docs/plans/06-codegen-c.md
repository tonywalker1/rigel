# Plan 06 — C Code Generation

**Status:** Stub. To be elaborated for Slice 3.

## Purpose

Transforms checked IR into C source code.

## Spec Sections

- §6 (Compilation to C) — translation strategy, tail calls, checked arithmetic
- §5 (Memory Model) — ownership, RAII, ref counting in generated C

## Key Concerns (to be designed)

- Monomorphization strategy (generate one C function per concrete type instantiation)
- Tail recursion → loop transformation
- Checked arithmetic via `__builtin_add_overflow`
- RAII via scope-exit cleanup in C (goto-based or similar)
- Effect handler implementation in C (setjmp/longjmp or continuation-passing)
