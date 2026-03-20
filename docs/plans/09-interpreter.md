# Plan 09 — Interpreter

**Status:** Elaborated. To be implemented in Slice 3.

## Purpose

Tree-walking evaluator that executes checked IR directly. The interpreter is the fastest path to
running Rigel code: it reuses Python's runtime (GC, closures, exceptions) so there is no need for
a runtime library. Semantics are identical to compiled output — the interpreter is the compiler
with C emission replaced by direct evaluation.

## Spec Sections

- §3 (Core Forms) — evaluation semantics for let, set, if, cond, match, do, lambda, call
- §6 (Compilation to C) — same semantics, different execution strategy
- §8 (Effects System) — raise/handle via Python exceptions

## Inputs

- `05-semantic-analysis.md` — checked IR (`TypedExpr` hierarchy)
- `04-type-system.md` — `Type` representations (used for runtime type tags on closures)
- `00-conventions.md` — error classes, style

## Prerequisites

**One-line IR addition:** `TLetForm` needs a `mutable: bool` field so the interpreter knows
whether a binding can be reassigned with `set`. The checker already tracks mutability in `Env`
but does not emit it on the IR node. Add:

```python
# In check.py, TLetForm:
@dataclass(frozen=True)
class TLetForm(TypedExpr):
    name: str
    value: TypedExpr
    type_ann: Type | None
    mutable: bool           # ← new field
```

Update the checker's `_check_let` to pass `mutable=node.mutable`.

## Interface Contract

### Source: `src/rigel/interp.py`

**Entry point:**
```python
def interpret(ir: list[TypedExpr], *, output: TextIO | None = None) -> Value:
    """Evaluate a checked IR program. Returns the value of the last expression.

    output: stream for println/print builtins (defaults to sys.stdout).
    Raises RuntimeError_ on evaluation errors, RigelEffect on unhandled effects.
    """
```

**Value representation** — Python natives plus two dataclasses:
```python
# Values are plain Python objects:
#   int          → Rigel int8/16/32/64
#   float        → Rigel float32/64
#   str          → Rigel string
#   bool         → Rigel bool
#   None         → Rigel unit
Value = int | float | str | bool | None | Closure | BuiltinFn

@dataclass
class Closure:
    """A Rigel lambda captured at runtime."""
    params: list[str]              # parameter names
    body: list[TypedExpr]          # checked IR body
    env: RuntimeEnv                # captured environment (snapshot)
    name: str | None = None        # for letrec self-reference (None = anonymous)

@dataclass
class BuiltinFn:
    """A built-in function (arithmetic, I/O, etc.)."""
    name: str
    fn: Callable[..., Value]
```

**Runtime environment:**
```python
class RuntimeEnv:
    """Maps names to values. Separate from the checker's Env (which maps names to types)."""

    def __init__(self, parent: RuntimeEnv | None = None) -> None:
        self._bindings: dict[str, Value] = {}
        self._mutables: set[str] = set()     # names that can be reassigned
        self._parent = parent

    def define(self, name: str, value: Value, mutable: bool = False) -> None: ...
    def lookup(self, name: str) -> Value: ...
    def set(self, name: str, value: Value) -> None: ...
    def child(self) -> RuntimeEnv: ...
```

**Error classes** (added to `common.py`):
```python
class RuntimeError_(RigelError):
    """Error during interpretation (division by zero, unhandled effect, etc.)."""

class RigelEffect(Exception):
    """Raised (as Python exception) when a Rigel effect is raised.

    Not a RigelError — it's a control-flow mechanism, not a user-facing error.
    """
    def __init__(self, effect: str, args: list[Value]) -> None:
        self.effect = effect
        self.args = args
```

## Behavioral Requirements

### Phase A — Literals and Bindings

1. **Literals** — `TIntLiteral` → Python `int`, `TFloatLiteral` → `float`,
   `TStringLiteral` → `str`, `TBoolLiteral` → `bool`.
2. **Symbol lookup** — `TSymbol` → look up name in `RuntimeEnv`. Raise `RuntimeError_` if missing
   (should not happen after type checking, but defensive).
3. **Let binding** — `TLetForm` → evaluate value, bind name in current env (mark mutable if
   `mutable=True`). Returns `None` (unit).
4. **Set** — `TSetForm` → evaluate value, call `env.set(name, value)`. Raise `RuntimeError_` if
   name not found or not mutable (defensive — checker should catch this).

### Phase B — Control Flow

5. **If** — `TIfForm` → evaluate condition; if truthy evaluate then-branch, else evaluate
   else-branch (or return `None` if no else).
6. **Cond** — `TCondForm` → evaluate tests in order; first truthy test's body is evaluated.
   If none match, evaluate else clause (or return `None`).
7. **Match** — `TMatchForm` → evaluate target; compare against each pattern (literal equality
   or `_` wildcard). First matching arm's body is evaluated.
8. **Do** — `TDoForm` → evaluate each expression in sequence, return last value.

### Phase C — Functions

9. **Lambda** — `TLambdaForm` → create a `Closure` capturing the current environment. Do not
   evaluate the body yet.
10. **Call** — `TCallForm` → evaluate function position and arguments. If `Closure`: create a
    child env of the closure's captured env, bind params to args, evaluate body, return last value.
    If `BuiltinFn`: call the Python callable with args.
11. **Letrec** — when a `TLetForm` binds a `TLambdaForm`, define the name with a placeholder
    (`None`) before evaluating the lambda, then update the binding. This allows the closure to
    capture a reference to itself for recursion. The `RuntimeEnv` slot is mutable for this purpose
    regardless of the `mutable` flag on the let.

### Phase D — Effects

12. **Raise** — `TRaiseForm` → evaluate args, then `raise RigelEffect(effect, args)`.
13. **Handle** — `THandleForm` → wrap body evaluation in `try/except RigelEffect`. If the caught
    effect matches a handler, bind handler params to effect args, evaluate handler body, return
    its value. If no handler matches, re-raise.

### Built-in Functions

Seeded into the top-level `RuntimeEnv` before evaluation:

| Name | Behavior |
|------|----------|
| `+`, `-`, `*` | Python arithmetic on int/float |
| `/` | Integer: `a // b` (floor division). Float: `a / b`. Division by zero → `RuntimeError_` |
| `mod` | `a % b`. Division by zero → `RuntimeError_` |
| `<`, `>`, `<=`, `>=` | Python comparison → `bool` |
| `=` | Python `==` → `bool` |
| `!=` | Python `!=` → `bool` |
| `and`, `or` | Python `and`/`or` (short-circuit) → `bool` |
| `not` | Python `not` → `bool` |
| `println` | Write `str(arg) + "\n"` to output stream. Returns `None` |
| `print` | Write `str(arg)` to output stream (no newline). Returns `None` |

## Error Cases

| Condition | Error |
|-----------|-------|
| Division by zero (`/` or `mod` with 0 divisor) | `RuntimeError_("division by zero", span)` |
| Unhandled effect (raise reaches top level) | `RuntimeError_("unhandled effect: {name}", span)` |
| Name not found at runtime (defensive) | `RuntimeError_("undefined name: {name}", span)` |
| Set on immutable binding (defensive) | `RuntimeError_("cannot reassign: {name}", span)` |
| Integer overflow | Not checked in interpreter (Python ints are arbitrary precision). Overflow checking is a codegen concern. |

## Test Oracle

| Input (Rigel source) | Expected result |
|----------------------|----------------|
| `42` | `42` |
| `(+ 1 2)` | `3` |
| `(let x 10) x` | `10` |
| `(let x 10) (let y 20) (+ x y)` | `30` |
| `(if true 1 2)` | `1` |
| `(if false 1 2)` | `2` |
| `(do (let x 5) (+ x 1))` | `6` |
| `(let add (lambda (:args (a int64) (b int64)) (:returns int64) (+ a b))) (add 3 4)` | `7` |
| `(let fact (lambda (:args (n int64)) (:returns int64) (if (= n 0) 1 (* n (fact (- n 1))))))` then `(fact 5)` | `120` |
| `(handle (raise fail "oops") (fail (msg) msg))` | `"oops"` |
| `(/ 10 0)` | `RuntimeError_` |

## Design Notes

### Why walk checked IR, not raw AST?

The checker has already verified types, resolved names, and checked effects. The interpreter
doesn't need to re-check anything — it just evaluates. This means the interpreter is simpler,
and any bug in type checking is caught before execution.

### Why Python exceptions for effects?

Non-resumable effects map exactly to Python's exception model: `raise` unwinds the stack,
`handle` is `try/except`. This is both correct and trivial to implement. If we later add
resumable effects (continuations), we'd need a different mechanism — but the spec currently
only requires non-resumable effects.

### Integer division

Uses `//` (floor division) to match Python semantics. This differs from C's truncation toward
zero for negative operands. If C semantics are needed for consistency with codegen, switch to
`int(a / b)` (truncation). Noted here so the decision can be revisited.

## Regeneration Instructions

- Generate `src/rigel/interp.py`.
- Import checked IR nodes from `rigel.check`, types from `rigel.types`, errors from
  `rigel.common`.
- `Closure` and `BuiltinFn` dataclasses defined in this module.
- `RuntimeEnv` is a linked-list scope chain (same pattern as `Env` in check.py, but mapping
  names→values instead of names→types).
- Seed builtins via a `_seed_builtins(env, output_stream)` function.
- Main `interpret()` function creates a top-level env, seeds builtins, then evaluates each
  top-level IR node in sequence.
- `_eval(node, env)` is the recursive evaluator dispatching on `TypedExpr` subtype via
  `match` statement.
- Letrec: detect `TLetForm` whose value is `TLambdaForm`, pre-define name, evaluate lambda,
  update binding.
