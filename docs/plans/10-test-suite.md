# Plan 10 — Test Suite

## Purpose

Defines the testing strategy and organization. The test suite is the integration contract: if
every component can be regenerated and the tests still pass, the system is healthy.

## Principles

1. **Spec-driven.** Every testable statement in `rigel-spec.md` should have a corresponding test.
   The spec section is referenced in a comment on each test.

2. **Bug-driven.** Every bug found in generated code produces two artifacts:
   - A spec clarification (if the bug reveals ambiguity).
   - A regression test (always).

3. **Phase-isolated.** Each compiler phase has its own test file. Tests for the lexer don't
   depend on the parser working. Tests for the parser use the lexer but test parser-specific
   behavior.

4. **Example-program tests.** The §12 example program is an end-to-end test — it should parse
   (Slice 1), type-check (Slice 2), and compile/run (Slice 3).

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures (helper to parse a string, etc.)
├── test_lexer.py            # Tokenization: atoms, strings, numbers, spans, errors
├── test_parser.py           # Parsing: each form, nesting, error recovery
├── test_parser_roundtrip.py # Parse → pretty-print → re-parse gives same AST
├── test_types.py            # (Slice 2) Type system, constraint matching
├── test_check.py            # (Slice 2) Semantic analysis, effect checking
├── test_codegen.py          # (Slice 3) C emission
├── test_interp.py           # (Slice 3) Interpreter evaluation
└── test_examples.py         # End-to-end: spec examples, tutorial examples
```

## Slice 1 Test Cases (Lexer + Parser)

### Lexer

**Atoms:**
- Integer literals: `42`, `-7`, `0`, `42:int8`, `255:int16 unsigned`
- Float literals: `3.14`, `-0.5`, `3.14:float32`
- String literals: `"hello"`, `"with \"escapes\""`, `"multi\nline"`
- Booleans: `true`, `false`
- Symbols: `x`, `+`, `my-func`, `int64`, `->`, `>=`
- Keywords: `:args`, `:with`, `:capture`, `:returns`

**Structure:**
- Balanced parens: `()`, `(())`, `((()))`
- Comments stripped: `; comment\n42` → just `INT`
- Whitespace variations: spaces, tabs, newlines, mixed

**Errors:**
- Unterminated string
- Unexpected character (if any exist — s-exprs are permissive)

**Spans:**
- Every token's span matches its position in the source
- Multi-line source has correct line/col tracking

### Parser

**Core forms:**
- `let` with value: `(let x 42)`
- `let` with type annotation: `(let x :type int64 42)`
- `set`: `(set x 43)`
- `lambda` minimal: `(lambda (:args (x int64)) x)` (paren syntax, interim)
- `lambda` full: `(lambda (:args (x int64) (y int64)) (:capture (z)) (:returns int64) (:with (io)) (+ x y))` (paren syntax, interim)
- Spec target syntax uses brackets: `(lambda (:args [x : int64]) x)` — bracket parsing is follow-up
- `type` minimal: `(type (:fields (x int64)))`
- `type` with invariant: `(type (:fields (value int64)) (:invariant (>= (.value self) 0)))`
- `if` two-arm: `(if true 1 2)`
- `if` one-arm: `(if true 1)`
- `cond`: `(cond ((> x 0) "positive") ((< x 0) "negative") (:else "zero"))`
- `match`: `(match x (0 "zero") (1 "one") (_ "other"))`
- `do`: `(do 1 2 3)`
- `module`: `(module math (:export add) (let add (lambda ...)))`
- `import` basic: `(import math)`
- `import` selective: `(import math :only (add))`
- `handle`/`raise`: `(handle (raise fail "oops") (fail (msg) (println msg)))`

**Call expressions:**
- `(f)` — no args
- `(f x)` — one arg
- `(f x y z)` — multiple args
- `((get-fn) x)` — computed function position
- Nested: `(f (g x) (h y))`

**Nesting and composition:**
- Let binding a lambda
- Lambda body with multiple expressions
- Nested if/cond/match
- The §12 example program (once complete enough)

**Errors:**
- Unmatched parens
- Wrong arity for special forms
- Missing required parts (e.g. `(lambda)` with no args)

## Slice 2 Test Cases (Type System + Semantic Analysis)

### Type System (`test_types.py`)

**Constraint satisfaction (§2.1):**
- `int64` satisfies `int`, `number`, `any`
- `float64` satisfies `float`, `number`, `any`
- `bool` satisfies `any` but not `int`, `float`, `number`
- `string` satisfies `any` but not `number`

**Qualifiers (§2.2):**
- `int32 unsigned` satisfies `(int unsigned)` and `int`
- Plain `int32` does not satisfy `(int unsigned)`
- `float64 unchecked` satisfies `(float unchecked)`
- Qualifier parsing: empty, single, multiple, unknown-ignored

**Type equality and assignability:**
- Same concrete types are equal
- Different widths are not equal (`int32` ≠ `int64`)
- No implicit widening (`int32` not assignable to `int64`)
- `never` assignable to anything; nothing assignable to `never`

**Function types:**
- FnType repr includes param/return types
- FnType with effects includes effect names
- FnType equality: same params+ret = equal; different = not equal

**Name resolution:**
- Built-in type names resolve (`int64`, `float32`, `bool`)
- Constraint names resolve (`int`, `float`, `number`)
- Unknown names return None

### Semantic Analysis (`test_check.py`)

**Literal defaults (§2.1):**
- `42` → `int64`, `3.14` → `float64`, `"hello"` → `string`, `true` → `bool`
- `42:int8` → `int8` (type suffix)

**Let bindings (§3.1):**
- Type inferred from value
- Explicit type annotation checked against value
- Type mismatch raises `TypeError_`
- Bound name accessible in subsequent expressions

**Set/reassignment (§3.1):**
- Set on immutable binding raises `TypeError_`
- Set on undefined name raises `NameError_`

**Name resolution:**
- Undefined name raises `NameError_`
- Built-in operators (+, -, *, /, <, >, =) are in scope
- Lambda params in scope inside body, not outside

**Lambda (§3.2):**
- Lambda produces `FnType` with correct params and return
- Body type must match declared return type
- No `:returns` defaults to `unit`
- Let-bound lambda records `FnType` on the binding
- Call checks argument count and types
- Wrong arg count/type raises `TypeError_`

**Captures (§3.2):**
- Capture resolves from outer scope
- Undefined capture raises `NameError_`

**Control flow (§3.3):**
- `if` condition must be `bool`
- Two-arm `if` returns branch type
- One-arm `if` returns `unit`
- Branch type mismatch raises `TypeError_`
- `do` returns last expression's type

**Effects (§8):**
- `raise` in pure context raises `EffectError`
- `raise` inside `:with (fail)` lambda is ok
- Calling effectful function from pure context raises `EffectError`
- Calling effectful function from matching effectful context is ok
- `handle` makes effects available to body
- `raise` produces `never` type

**Full pipeline:**
- Simple arithmetic: let + let + call → all typed
- Function definition + call → correct return type
- Nested let + call → types propagate
- `if` with comparison → correct type
- Effectful program: IO function + main → effects propagate

## Slice 3 Test Cases (Interpreter + Driver + End-to-End)

### Interpreter (`test_interp.py`)

Tests call `interpret()` directly on checked IR (via a helper that parses → checks → interprets).

**Fixture:** `conftest.py` gains a new helper:
```python
def run(source: str, *, output: StringIO | None = None) -> Value:
    """Parse, check, and interpret a Rigel source string. Returns the final value."""
```

**Literals (§2.1):**
- `42` → `42` (Python int)
- `3.14` → `3.14` (Python float)
- `"hello"` → `"hello"` (Python str)
- `true` → `True`, `false` → `False`

**Arithmetic (§3, builtins):**
- `(+ 1 2)` → `3`
- `(- 10 3)` → `7`
- `(* 4 5)` → `20`
- `(/ 10 3)` → `3` (floor division for integers)
- `(mod 10 3)` → `1`
- `(+ 1.5 2.5)` → `4.0` (float arithmetic)
- `(/ 7.0 2.0)` → `3.5` (float division)

**Comparison and boolean (§3, builtins):**
- `(< 1 2)` → `True`
- `(> 2 1)` → `True`
- `(= 3 3)` → `True`
- `(!= 3 4)` → `True`
- `(and true false)` → `False`
- `(or true false)` → `True`
- `(not true)` → `False`

**Let bindings (§3.1):**
- `(let x 10) x` → `10`
- `(let x 10) (let y 20) (+ x y)` → `30`
- `(let x :type int64 42) x` → `42`

**Set/mutability (§3.1):**
- `(let mut x 10) (set x 20) x` → `20`
- Immutable set → `RuntimeError_` (defensive — checker catches this, but interpreter
  should also guard)

**If (§3.3):**
- `(if true 1 2)` → `1`
- `(if false 1 2)` → `2`
- `(if true 42)` → `42` (one-arm, condition true)
- `(if false 42)` → `None` (one-arm, condition false → unit)

**Cond (§3.3):**
- `(cond ((= 1 1) "yes") (:else "no"))` → `"yes"`
- `(cond ((= 1 2) "a") ((= 1 1) "b") (:else "c"))` → `"b"` (second clause matches)
- `(cond ((= 1 2) "a") (:else "fallback"))` → `"fallback"`

**Match (§3.3):**
- `(match 1 (1 "one") (2 "two") (_ "other"))` → `"one"`
- `(match 3 (1 "one") (2 "two") (_ "other"))` → `"other"` (wildcard)

**Do (§3.3):**
- `(do 1 2 3)` → `3` (returns last)
- `(do (let x 5) (+ x 1))` → `6`

**Lambda and call (§3.2):**
- Simple function:
  `(let add (lambda (:args (a int64) (b int64)) (:returns int64) (+ a b))) (add 3 4)` → `7`
- Lambda with no return annotation (returns unit):
  `(let greet (lambda (:args (s string)) (:with (io)) (println s)))` — call returns `None`
- Closure/capture:
  `(let x 10) (let add-x (lambda (:args (y int64)) (:capture (x)) (:returns int64) (+ x y))) (add-x 5)` → `15`

**Recursion / letrec (§3.2):**
- Factorial:
  ```
  (let fact (lambda (:args (n int64)) (:returns int64)
    (if (= n 0) 1 (* n (fact (- n 1))))))
  (fact 5)
  ```
  → `120`
- Fibonacci:
  ```
  (let fib (lambda (:args (n int64)) (:returns int64)
    (if (< n 2) n (+ (fib (- n 1)) (fib (- n 2))))))
  (fib 10)
  ```
  → `55`

**Effects (§8):**
- Handle/raise basic:
  `(handle (raise fail "oops") (fail (msg) msg))` → `"oops"`
- Handle with body that doesn't raise:
  `(handle 42 (fail (msg) 0))` → `42`
- Nested handle:
  ```
  (handle
    (handle (raise fail "inner") (fail (msg) (raise fail "outer")))
    (fail (msg) msg))
  ```
  → `"outer"`

**I/O (§8, builtins):**
- `println` writes to output stream (tested via `StringIO` injection):
  ```
  (handle
    (do (println "hello"))
    (io (msg) msg))
  ```
  → stdout captures `"hello\n"`

**Error cases:**
- `(/ 10 0)` → `RuntimeError_` (division by zero)
- `(mod 10 0)` → `RuntimeError_` (division by zero)
- Unhandled effect reaching top level → `RuntimeError_`

### Driver (`test_driver.py`)

Tests call `main(argv)` and check exit code + stdout/stderr.

**Fixture:** tests write temporary `.rgl` files via `tmp_path` fixture.

**Successful runs:**
- `rigel run <file>` with `(let x 42) x` → exit 0, no stdout (no println)
- `rigel run <file>` with println program → exit 0, stdout has output
- `rigel run -` with stdin → exit 0
- `rigel check <file>` with valid program → exit 0
- `rigel --version` → exit 0, stdout contains version string

**Error cases:**
- `rigel run nonexistent.rgl` → exit 1, stderr: file not found
- `rigel check <file>` with type error → exit 1, stderr contains error
- `rigel check <file>` with undefined name → exit 1, stderr contains error
- `rigel compile <file>` → exit 1, stderr: not yet implemented
- `rigel` (no args) → exit 1, stderr: usage

**Dump modes:**
- `rigel run --dump-ast <file>` → exit 0, stderr contains AST repr
- `rigel run --dump-ir <file>` → exit 0, stderr contains IR repr
- `rigel run --dump-ast --dump-ir <file>` → exit 0, stderr contains both

### End-to-End Examples (`test_examples.py`)

Full programs parsed → checked → interpreted. These test the complete pipeline.

**Arithmetic program:**
```rigel
(let a 10)
(let b 20)
(let sum (+ a b))
sum
```
→ `30`

**Function composition:**
```rigel
(let double (lambda (:args (x int64)) (:returns int64) (* x 2)))
(let add1 (lambda (:args (x int64)) (:returns int64) (+ x 1)))
(add1 (double 5))
```
→ `11`

**Recursive GCD:**
```rigel
(let gcd (lambda (:args (a int64) (b int64)) (:returns int64)
  (if (= b 0) a (gcd b (mod a b)))))
(gcd 48 18)
```
→ `6`

**Effect-driven error handling:**
```rigel
(let safe-div (lambda (:args (a int64) (b int64)) (:returns int64) (:with (fail))
  (if (= b 0)
    (raise fail "division by zero")
    (/ a b))))
(handle (safe-div 10 0) (fail (msg) -1))
```
→ `-1`

**Closure over mutable state:**
```rigel
(let mut counter 0)
(let inc (lambda (:args) (:capture (mut counter)) (:returns int64)
  (set counter (+ counter 1))
  counter))
(inc)
(inc)
(inc)
```
→ `3`

**Nested control flow:**
```rigel
(let classify (lambda (:args (n int64)) (:returns string)
  (cond
    ((< n 0) "negative")
    ((= n 0) "zero")
    (:else "positive"))))
(classify -5)
```
→ `"negative"`

## Running Tests

```bash
python -m pytest tests/ -v
```

No special configuration needed beyond pytest.

## Regeneration Instructions

- Test files are generated alongside the component they test.
- When regenerating a component, regenerate its tests too.
- `conftest.py` provides helpers like `parse_one(source) -> Node` that parse a string and
  return the single top-level node, for concise test cases.
