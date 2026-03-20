# Plan 03 — Parser

## Purpose

Transforms a flat list of tokens into a structured AST. For Rigel's s-expression syntax, this
means: read parenthesized lists, then recognize special forms (`let`, `lambda`, `type`, etc.)
and build the corresponding AST nodes from `01-data-model`.

## Spec Sections

- §3 (Core Forms) — `let`, `set`, `if`, `cond`, `match`, `do`, `lambda`
- §3b (No Type Aliases) — `type` form
- §4 (Module System) — `module`, `import`
- §8 (Effects System) — `handle`, `raise`
- §11 (Grammar) — full EBNF

## Inputs

- `00-conventions.md` — `Span`, `ParseError`, style
- `01-data-model.md` — all AST node classes
- `02-lexer.md` — `Token`, `TokenKind`, `tokenize()`

## Interface Contract

### Source: `src/rigel/parser.py`

**Public API:**
```python
def parse(source: str, filename: str = "<stdin>") -> list[Node]:
    """Parse Rigel source text into a list of top-level AST nodes.

    Calls tokenize() internally.
    Raises ParseError on malformed input.
    """

def parse_tokens(tokens: list[Token]) -> list[Node]:
    """Parse a token list into AST nodes.

    Useful for testing the parser independently of the lexer.
    """
```

**Parsing strategy — two passes:**

1. **S-expression pass:** tokens → nested lists (generic s-expression structure). An atom token
   becomes an AST leaf (`IntLiteral`, `FloatLiteral`, `StringLiteral`, `BoolLiteral`, `Symbol`).
   A parenthesized group becomes a Python list of these.

2. **Form recognition pass:** walk the nested lists. If a list starts with a known keyword
   (`let`, `lambda`, `type`, `if`, `cond`, `match`, `do`, `module`, `import`, `handle`, `raise`,
   `set`), parse it into the corresponding AST node. Otherwise, treat it as a `CallForm`.

This two-pass approach keeps each pass simple and independently testable.

## Behavioral Requirements

1. **let** — `(let name value)` or `(let name :type ann value)`.
2. **set** — `(set name value)`.
3. **lambda** — `(lambda (:args ...) (:capture ...) (:returns type) (:with effects) body...)`.
   All keyword sections are optional except `:args`.
4. **type** — `(type (:fields ...) (:invariant expr) (:constructor ...) (:viewer ...) (:release ...))`.
5. **if** — `(if cond then else?)`.
6. **cond** — `(cond (test body)... (:else body)?)`.
7. **match** — `(match target (pattern body)... )`.
8. **do** — `(do expr...)`. Sequences expressions.
9. **module** — `(module name (:export ...) body...)`.
10. **import** — `(import module)` or `(import module :only (names...))` or `(import module :as alias)`.
11. **handle** — `(handle body (effect-name (params...) handler-body)...)`.
12. **raise** — `(raise effect args...)`.
13. **Call** — any list not starting with a special form keyword: `(f x y)` → `CallForm(f, [x, y])`.
14. **Nested expressions** — arbitrary nesting works naturally from the s-expression pass.

## Error Cases

- Unmatched `(` → `ParseError` at the opening paren.
- Unmatched `)` → `ParseError` at the closing paren.
- `(let)` with wrong arity → `ParseError` with message about expected form.
- Unknown keyword section in lambda (e.g. `:bogus`) → `ParseError`.

## Test Oracle

| Input | Expected AST |
|-------|-------------|
| `(let x 42)` | `LetForm(Symbol("x"), IntLiteral(42))` |
| `(+ 1 2)` | `CallForm(Symbol("+"), [IntLiteral(1), IntLiteral(2)])` |
| `(if true 1 2)` | `IfForm(BoolLiteral(true), IntLiteral(1), IntLiteral(2))` |
| `(let add (lambda (:args (a int64) (b int64)) (:returns int64) (+ a b)))` | `LetForm(Symbol("add"), LambdaForm(...))` |
| `(do (let x 1) (let y 2) (+ x y))` | `DoForm([LetForm(...), LetForm(...), CallForm(...)])` |

**Note:** The spec target syntax uses bracket bindings `[a : int32]` in `:args`, but the parser
currently accepts paren syntax `(a int64)` as an implementation shortcut. Bracket binding parsing
is a follow-up task.

## Regeneration Instructions

- Generate `src/rigel/parser.py`.
- Import AST nodes from `src/rigel/ast.py`, tokens from `src/rigel/lexer.py`.
- The two-pass approach (s-expr → form recognition) should be two clearly separated internal
  functions.
- Form recognizers can be a dispatch table: `{"let": parse_let, "lambda": parse_lambda, ...}`.
- Spans for compound nodes should cover the full extent from `(` to `)`.
