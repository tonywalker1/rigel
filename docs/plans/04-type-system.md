# Plan 04 — Type System

**Status:** Stub. To be elaborated for Slice 2.

## Purpose

Represents the constraint-based type hierarchy, type unification, and monomorphization strategy.

## Spec Sections

- §2 (Type System) — constraint hierarchy, qualifiers, numeric types
- §3 (Core Forms) — type annotations in let/lambda/type

## Key Concerns (to be designed)

- Representation of the constraint lattice (`number > int > int64`, qualifiers as constraints)
- Type inference for let-bindings (local, not global Hindley-Milner)
- Monomorphization: instantiating generic functions at concrete types
- Interaction between qualifiers (`unsigned`, `unchecked`, `mut`, `unique`) and constraints
