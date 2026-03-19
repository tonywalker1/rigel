# Plan 02 — Lexer

## Purpose

Tokenizes Rigel source text into a stream of tokens. For an s-expression language this is
intentionally simple — the lexer's job is to identify atoms, parentheses, string literals,
numbers, and comments. The parser handles all structure.

## Spec Sections

- §11 (Grammar) — terminal productions
- §2.1 (Numeric Type Hierarchy) — literal syntax and suffixes
- §7 (String Type) — string literal syntax

## Inputs

- `00-conventions.md` — `Span`, `LexError`, style
- `01-data-model.md` — not directly; the lexer produces tokens, not AST nodes

## Interface Contract

### Source: `src/rigel/lexer.py`

**Token types:**
```python
class TokenKind(Enum):
    LPAREN = "("
    RPAREN = ")"
    LBRACKET = "["          # for future vector literal syntax if needed
    RBRACKET = "]"
    INT = "int"             # integer literal
    FLOAT = "float"         # float literal
    STRING = "string"       # string literal (contents unescaped)
    SYMBOL = "symbol"       # identifier or keyword
    BOOL = "bool"           # true / false
    KEYWORD = "keyword"     # :keyword (colon-prefixed)
    COMMENT = "comment"     # ; to end of line (stripped by default)
    EOF = "eof"
```

**Token:**
```python
@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str               # raw text from source
    span: Span
```

**Public API:**
```python
def tokenize(source: str, filename: str = "<stdin>") -> list[Token]:
    """Tokenize source text into a list of tokens.

    Comments are excluded from the output.
    Raises LexError on invalid input (unterminated string, invalid number).
    """
```

## Behavioral Requirements

1. **Parentheses** — `(` and `)` are single-character tokens.
2. **Integers** — optional `-`, digits, optional type suffix after `:` (e.g. `42:int8`).
   The suffix is part of the token text.
3. **Floats** — digits, `.`, digits, optional type suffix. Scientific notation (`1e10`) is
   a stretch goal.
4. **Strings** — double-quoted, with `\"` and `\\` escapes. Multi-line strings allowed.
5. **Booleans** — `true` and `false` are lexed as `BOOL`, not `SYMBOL`.
6. **Symbols** — any sequence of non-whitespace, non-paren, non-quote characters that isn't
   a number or boolean. Includes operators like `+`, `-`, `*`, `<`.
7. **Keywords** — symbols starting with `:` (e.g. `:capture`, `:with`, `:mut`).
8. **Comments** — `;` to end of line. Stripped from output.
9. **Whitespace** — spaces, tabs, newlines. Separates tokens, not emitted.
10. **Source tracking** — every token carries a `Span` with accurate line/col/offset.

## Error Cases

- Unterminated string literal → `LexError` with span pointing to opening quote.
- Invalid numeric literal (e.g. `12.34.56`) → `LexError` at the token.

## Test Oracle

| Input | Expected Tokens |
|-------|----------------|
| `(+ 1 2)` | `LPAREN SYMBOL("+"") INT("1") INT("2") RPAREN` |
| `42:int8` | `INT("42:int8")` |
| `"hello"` | `STRING("hello")` |
| `true` | `BOOL("true")` |
| `:with` | `KEYWORD(":with")` |
| `; comment\n42` | `INT("42")` |
| `"unterminated` | `LexError` |

## Regeneration Instructions

- Generate `src/rigel/lexer.py`.
- Import `Span`, `LexError` from `src/rigel/common.py`.
- No regex — use a hand-written scanner (a `pos` index walking the source string). This is
  simpler and gives precise span tracking.
- The lexer is stateless — `tokenize()` is a pure function.
