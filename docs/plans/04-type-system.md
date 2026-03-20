# Plan 04 — Type System

**Status:** Implemented (Slice 2).

## Purpose

Represents the constraint-based type hierarchy, type compatibility, and qualifier handling.
This module is pure data — it defines types and operations on them, but does not walk the AST.

## Spec Sections

- §2.1 (Numeric Type Hierarchy) — constraint lattice, literal defaults
- §2.2 (Qualifier Semantics) — unsigned, unchecked, mut, unique, atomic
- §2.3 (Constraint-Based Generics) — int, float, number as constraints
- §2.4 (Type Labels) — deferred (type variables exist but labels not yet parsed)

## Inputs

- `00-conventions.md` — `Span`, error classes, style

## Interface Contract

### Source: `src/rigel/types.py`

**Concrete types** (leaves of the type hierarchy):
```python
IntType(bits: int, quals: Qualifiers)      # int8, int16, int32, int64
FloatType(bits: int, quals: Qualifiers)    # float32, float64
BoolType()                                  # bool
StringType()                                # string
UnitType()                                  # unit (void equivalent)
NeverType()                                 # bottom type (raise never returns)
FnType(params, ret, effects)               # function types (-> args ret)
StructType(name, fields, opaque)           # user-defined struct types
TypeVar(id)                                 # inference placeholder
```

**Qualifiers** are a `frozenset[Qualifier]` on numeric types:
```python
class Qualifier(Enum):
    UNSIGNED, UNCHECKED, MUT, UNIQUE, ATOMIC
```

**Constraints** (interior nodes — match sets of concrete types):
```python
IntConstraint(required_quals)   # matches any IntType with ⊇ quals
FloatConstraint(required_quals) # matches any FloatType with ⊇ quals
NumberConstraint()              # matches any IntType or FloatType
AnyConstraint()                 # matches any Type
```

**Key operations:**
```python
satisfies(ty: Type, constraint: Constraint) -> bool   # constraint lattice check
types_equal(a: Type, b: Type) -> bool                  # structural equality
is_assignable(source: Type, target: Type) -> bool      # assignment compatibility
resolve_type_name(name: str) -> Type | Constraint | None
```

**Built-in constants:** `INT8`, `INT16`, `INT32`, `INT64`, `FLOAT32`, `FLOAT64`, `BOOL`,
`STRING`, `UNIT`, `NEVER`.

## Design Decisions

### Qualifiers as frozenset
Qualifiers are a frozenset on the type, not part of the type name. This means `int32` and
`int32 unsigned` are different types (different quals), but the same base. Constraint satisfaction
checks that the type's quals are a superset of the constraint's required quals.

### No implicit widening
`int32` is not assignable to `int64`. Explicit casts required. This matches the spec's philosophy
of explicit concrete types.

### never as bottom type
`NeverType` is assignable to any type (a divergent expression satisfies any expected type).
Nothing except `never` is assignable to `never`.

### Constraints are separate from types
The spec distinguishes `int` (constraint) from `int64` (type). This is modeled as two parallel
hierarchies: `Type` subclasses for concrete types, `Constraint` subclasses for constraints.
`satisfies()` bridges them.

## Known Gaps (Slice 2)

- **Type labels** (`int as T`): `TypeVar` exists but the parser doesn't produce `as` syntax yet.
- **Monomorphization**: not implemented. Generic functions are not instantiated at concrete types.
- **Compound type expressions**: `(list int32)`, `(map K V)`, `(option T)` — not yet represented.
- **Qualifier suffix on literals**: the lexer tokenizes `255:int16 unsigned` as two tokens
  (`255:int16` + `unsigned`). The checker only sees `int16` in the suffix.
- **User-defined constraints** (§2.5): `StructType` exists but constraint satisfaction for
  user-defined types is not implemented.

## Regeneration Instructions

- Generate `src/rigel/types.py`.
- All type classes are frozen dataclasses.
- No AST dependency — types.py is independent of ast.py.
- Export built-in constants and lookup tables.
