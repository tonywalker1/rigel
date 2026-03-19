# Plan 05 — Semantic Analysis

**Status:** Stub. To be elaborated for Slice 2.

## Purpose

Name resolution, type checking, and effect checking. Transforms the raw AST into a checked IR
with resolved names and verified types/effects.

## Spec Sections

- §3 (Core Forms) — scoping rules
- §4 (Module System) — name resolution across modules
- §8 (Effects System) — effect checking, purity enforcement
- §8b (Opaque Types) — visibility rules

## Key Concerns (to be designed)

- Scope model (lexical scoping, module scoping)
- Effect inference and checking (`:with` clauses)
- Opaque type enforcement (`.field` only inside methods)
- The checked IR — AST + resolved types, resolved names, effect annotations
