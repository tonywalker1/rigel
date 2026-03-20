# Plan 05 — Semantic Analysis

**Status:** Implemented (Slice 2).

## Purpose

Walks the parsed AST and produces a checked IR with resolved names and verified types/effects.
This is the bridge between parsing (Slice 1) and code generation (Slice 3).

## Spec Sections

- §3.1 (Bindings) — let/set scoping, type annotations, mutability
- §3.2 (Functions/Closures) — lambda params, captures, return types
- §3.3 (Control Flow) — if/cond/match type consistency
- §8 (Effects System) — :with declarations, raise checking, handle
- §8b (Opaque Types) — deferred (visibility not enforced yet)

## Inputs

- `01-data-model.md` — AST node types (the input)
- `04-type-system.md` — Type/Constraint representations (the output types)
- `00-conventions.md` — error classes, style

## Interface Contract

### Source: `src/rigel/check.py`

**Entry point:**
```python
def check(nodes: list[Node]) -> list[TypedExpr]
```

**Checked IR** — mirrors the AST but every node carries a resolved `Type`:
```python
@dataclass(frozen=True)
class TypedExpr:
    ty: Type        # resolved type of this expression
    span: Span      # source location (preserved from AST)

# Concrete subtypes: TIntLiteral, TFloatLiteral, TStringLiteral, TBoolLiteral,
# TSymbol, TLetForm, TSetForm, TLambdaForm, TIfForm, TCondForm, TMatchForm,
# TCallForm, TDoForm, THandleForm, TRaiseForm
```

**Environment** (lexical scope):
```python
class Env:
    def define(name, ty, mutable=False)
    def lookup(name) -> Binding | None
    def child() -> Env           # push a new scope
```

**Checker class:**
```python
class Checker:
    def check_program(nodes) -> list[TypedExpr]    # top-level entry
    def check_node(node, env) -> TypedExpr         # per-node dispatch
```

### Error classes (in `common.py`):
- `TypeError_` — type mismatches, unknown types
- `EffectError` — effect violations (raise without :with, effectful call from pure context)
- `NameError_` — undefined names, undefined captures

## Design Decisions

### Parallel checked IR (not AST mutation)
The checker produces new `TypedExpr` nodes rather than mutating or annotating the AST. This keeps
the AST immutable and makes the two representations independently useful: the AST for
pretty-printing/source tools, the IR for codegen.

### Lexical scoping via Env stack
`Env` is a linked list of scope frames (child → parent). Each `let`, `lambda`, `handle` pushes
a new frame. Lookup walks up the chain. This naturally handles shadowing and lambda capture.

### Effect context tracking
The checker maintains a `_effects: frozenset[str]` — the set of effects currently allowed.
- Top-level context: empty (pure).
- Inside a lambda with `:with (io fail)`: `{"io", "fail"}`.
- Inside a `handle` body: parent effects ∪ handled effects.
- `raise` checks that the named effect is in the current set.
- Calling a function checks that the callee's effects ⊆ caller's effects.

### Built-in operators as environment entries
Arithmetic (`+`, `-`, `*`, `/`), comparison (`<`, `>`, `=`), and boolean operators are seeded
into the top-level environment as `FnType` values. Currently typed as `(int64, int64) -> int64`
and `(int64, int64) -> bool`. This is a simplification — proper polymorphic builtins require
monomorphization.

### Lambda return type defaults to unit
A lambda with no `:returns` clause has return type `unit`. If the body's last expression has a
different type, it's a type error. This forces explicit return type annotations, which aligns
with the spec's emphasis on explicitness.

## What the Checker Catches

1. **Undefined names** — any symbol not in scope
2. **Type mismatches** — let annotation vs value, lambda return vs body, if branch mismatch,
   call argument types
3. **Immutability violations** — set on a non-mutable binding
4. **Effect violations** — raise in pure context, calling effectful function from pure context
5. **Arity mismatches** — wrong number of arguments in function calls
6. **Undefined captures** — lambda captures a name not in the enclosing scope

## Known Gaps (Slice 2)

- **Polymorphic builtins**: `+` is typed as `(int64, int64) -> int64`. It should work on any
  numeric type.
- **Generic functions**: no monomorphization. A generic function is checked but not instantiated.
- **Module scoping**: only single-file programs. No cross-module name resolution.
- **Opaque type enforcement**: `.field` access is not checked for visibility.
- **Pattern matching types**: match patterns are checked as expressions, not as patterns with
  bindings.
- **Handle result type**: the handle form's result type should be the handler's return type,
  not the body's type (which may be `never` if the body always raises).
- **Mutable let bindings**: the parser doesn't yet produce `mut` on let bindings (bracket syntax
  needed). The checker supports it via `Env.define(name, ty, mutable=True)`.

## Regeneration Instructions

- Generate `src/rigel/check.py`.
- Import AST nodes from `rigel.ast`, types from `rigel.types`, errors from `rigel.common`.
- The `TypedExpr` hierarchy mirrors the AST — one class per AST node type that can appear in
  expressions.
- `Checker` is stateful (tracks current effect context). Instantiate per check_program call.
- Seed built-in operators in `_seed_builtins()`.
