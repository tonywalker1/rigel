# Plan 01 — Data Model (AST)

## Purpose

Defines the abstract syntax tree that every other component produces or consumes. This is the
most critical plan — it's the schema everything else conforms to. Changes here ripple everywhere,
so it should stabilize early.

## Spec Sections

- §2 (Type System) — type representation in AST nodes
- §3 (Core Forms) — one AST node class per form
- §3b (No Type Aliases) — `TypeForm` with invariants
- §11 (Grammar) — the EBNF maps directly to AST structure

## Inputs

- `00-conventions.md` — `Span`, error classes, style

## Interface Contract

### Source: `src/rigel/ast.py`

The AST is the parsed representation of Rigel source. Each node is a frozen dataclass carrying
a `Span` for source location.

**Atoms** (leaf nodes):
```python
@dataclass(frozen=True)
class IntLiteral:
    value: int
    type_suffix: str | None    # e.g. "int8", "int16 unsigned"
    span: Span

@dataclass(frozen=True)
class FloatLiteral:
    value: float
    type_suffix: str | None
    span: Span

@dataclass(frozen=True)
class StringLiteral:
    value: str
    span: Span

@dataclass(frozen=True)
class BoolLiteral:
    value: bool
    span: Span

@dataclass(frozen=True)
class Symbol:
    name: str
    span: Span
```

**Core forms** (compound nodes — each maps to a Rigel special form):
```python
@dataclass(frozen=True)
class LetForm:
    name: Symbol
    value: Node               # the expression being bound
    type_ann: Node | None     # optional type annotation
    span: Span

@dataclass(frozen=True)
class SetForm:
    name: Symbol
    value: Node
    span: Span

@dataclass(frozen=True)
class LambdaForm:
    params: list[Param]
    captures: list[Capture]
    return_type: Node | None
    effects: list[Symbol]     # :with clause
    body: list[Node]
    span: Span

@dataclass(frozen=True)
class Param:
    name: Symbol
    type_ann: Node
    default: Node | None
    span: Span

@dataclass(frozen=True)
class Capture:
    name: Symbol
    mut: bool
    span: Span

@dataclass(frozen=True)
class TypeForm:
    fields: list[Field]
    invariant: Node | None
    constructor: Node | None   # :constructor
    viewer: Node | None        # :viewer
    release: Node | None       # :release
    span: Span

@dataclass(frozen=True)
class Field:
    name: Symbol
    type_ann: Node
    mut: bool
    span: Span

@dataclass(frozen=True)
class IfForm:
    condition: Node
    then_branch: Node
    else_branch: Node | None
    span: Span

@dataclass(frozen=True)
class CondForm:
    clauses: list[tuple[Node, Node]]  # (test, body) pairs
    else_clause: Node | None
    span: Span

@dataclass(frozen=True)
class MatchForm:
    target: Node
    arms: list[MatchArm]
    span: Span

@dataclass(frozen=True)
class MatchArm:
    pattern: Node
    guard: Node | None
    body: Node
    span: Span

@dataclass(frozen=True)
class CallForm:
    func: Node
    args: list[Node]
    span: Span

@dataclass(frozen=True)
class DoForm:
    body: list[Node]
    span: Span

@dataclass(frozen=True)
class ModuleForm:
    name: Symbol
    exports: list[Symbol]
    body: list[Node]
    span: Span

@dataclass(frozen=True)
class ImportForm:
    module: Symbol
    names: list[Symbol] | None   # None = import all
    alias: Symbol | None
    span: Span

@dataclass(frozen=True)
class ConstraintForm:
    params: list[Symbol]
    requirements: list[Node]
    span: Span

@dataclass(frozen=True)
class HandleForm:
    body: Node
    handlers: list[HandlerClause]
    span: Span

@dataclass(frozen=True)
class HandlerClause:
    effect: Symbol
    params: list[Param]
    body: Node
    resume: Symbol | None      # name bound to continuation
    span: Span

@dataclass(frozen=True)
class RaiseForm:
    effect: Symbol
    args: list[Node]
    span: Span
```

**Union type for all nodes:**
```python
Node = (IntLiteral | FloatLiteral | StringLiteral | BoolLiteral | Symbol
        | LetForm | SetForm | LambdaForm | TypeForm
        | IfForm | CondForm | MatchForm | CallForm | DoForm
        | ModuleForm | ImportForm | ConstraintForm
        | HandleForm | RaiseForm)
```

### Design Notes

- The AST is **concrete syntax** — it preserves enough structure to round-trip back to source
  (for pretty-printing, error messages). It does not desugar.
- The parser builds this AST. Semantic analysis transforms it into a checked/annotated form
  (a future plan will define that IR).
- `Node` is a union type, not a class hierarchy. Pattern matching via `match` statement.

## Behavioral Requirements

- All nodes are immutable (frozen dataclasses).
- All nodes carry a `Span`.
- The `Node` union is exhaustive — every Rigel syntactic form has exactly one AST class.

## Test Oracle

See `10-test-suite.md` for parser round-trip tests that validate AST structure.

## Regeneration Instructions

- Generate `src/rigel/ast.py`.
- Import `Span` from a shared `src/rigel/common.py` (which also holds error classes).
- Use `from __future__ import annotations` for forward references.
- No methods on AST nodes — they are pure data. Traversal is done externally.
