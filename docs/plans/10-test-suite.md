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
- Keywords: `:args`, `:with`, `:capture`, `:mut`, `:returns`

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
- `lambda` minimal: `(lambda (:args (x int64)) x)`
- `lambda` full: `(lambda (:args (x int64) (y int64)) (:capture (z)) (:returns int64) (:with (io)) (+ x y))`
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
