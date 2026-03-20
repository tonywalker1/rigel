"""Lexer for Rigel source text.

Hand-written scanner producing a flat list of tokens.
No regex — a pos index walks the source string for precise span tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rigel.common import LexError, Span


class TokenKind(Enum):
    LPAREN = "("
    RPAREN = ")"
    LBRACKET = "["
    RBRACKET = "]"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    SYMBOL = "symbol"
    BOOL = "bool"
    KEYWORD = "keyword"
    EOF = "eof"


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str
    span: Span


def tokenize(source: str, filename: str = "<stdin>") -> list[Token]:
    """Tokenize source text into a list of tokens.

    Comments are excluded from the output.
    Raises LexError on invalid input (unterminated string, invalid number).
    """
    tokens: list[Token] = []
    pos = 0
    line = 1
    col = 1
    length = len(source)

    def span_here(tok_len: int) -> Span:
        return Span(file=filename, line=line, col=col, offset=pos, length=tok_len)

    def advance(n: int = 1) -> None:
        nonlocal pos, line, col
        for i in range(n):
            if pos + i < length and source[pos + i] == "\n":
                line += 1
                col = 1
            else:
                col += 1
        pos += n

    while pos < length:
        ch = source[pos]

        # Whitespace
        if ch in " \t\r\n":
            advance()
            continue

        # Comments
        if ch == ";":
            while pos < length and source[pos] != "\n":
                advance()
            continue

        # Single-character tokens
        if ch == "(":
            tokens.append(Token(TokenKind.LPAREN, "(", span_here(1)))
            advance()
            continue
        if ch == ")":
            tokens.append(Token(TokenKind.RPAREN, ")", span_here(1)))
            advance()
            continue
        if ch == "[":
            tokens.append(Token(TokenKind.LBRACKET, "[", span_here(1)))
            advance()
            continue
        if ch == "]":
            tokens.append(Token(TokenKind.RBRACKET, "]", span_here(1)))
            advance()
            continue

        # String literals
        if ch == '"':
            start_pos = pos
            start_line = line
            start_col = col
            advance()  # skip opening quote
            value_chars: list[str] = []
            while pos < length and source[pos] != '"':
                if source[pos] == "\\":
                    advance()
                    if pos >= length:
                        break
                    esc = source[pos]
                    if esc == "n":
                        value_chars.append("\n")
                    elif esc == "t":
                        value_chars.append("\t")
                    elif esc == "\\":
                        value_chars.append("\\")
                    elif esc == '"':
                        value_chars.append('"')
                    else:
                        value_chars.append(esc)
                    advance()
                else:
                    value_chars.append(source[pos])
                    advance()
            if pos >= length:
                raise LexError(
                    "unterminated string literal",
                    Span(filename, start_line, start_col, start_pos, pos - start_pos),
                )
            advance()  # skip closing quote
            tok_text = source[start_pos:pos]
            tok_span = Span(filename, start_line, start_col, start_pos, pos - start_pos)
            tokens.append(Token(TokenKind.STRING, tok_text, tok_span))
            continue

        # Numbers and symbols
        if _is_token_char(ch):
            start_pos = pos
            start_line = line
            start_col = col
            while pos < length and _is_token_char(source[pos]):
                advance()
            text = source[start_pos:pos]
            tok_span = Span(filename, start_line, start_col, start_pos, len(text))

            # Classify
            if text in ("true", "false"):
                tokens.append(Token(TokenKind.BOOL, text, tok_span))
            elif text.startswith(":"):
                tokens.append(Token(TokenKind.KEYWORD, text, tok_span))
            elif _is_numeric(text):
                kind = _classify_number(text, tok_span)
                tokens.append(Token(kind, text, tok_span))
            else:
                tokens.append(Token(TokenKind.SYMBOL, text, tok_span))
            continue

        # Unknown character — for s-expressions this shouldn't happen often,
        # but handle gracefully
        raise LexError(f"unexpected character: {ch!r}", span_here(1))

    return _merge_qualifier_suffixes(tokens)


# Qualifier names that can follow a type-suffixed numeric literal
_QUALIFIER_NAMES = {"unsigned", "unchecked", "mut", "unique", "atomic"}


def _merge_qualifier_suffixes(tokens: list[Token]) -> list[Token]:
    """Merge qualifier words into preceding type-suffixed numeric tokens.

    Transforms: [INT "255:int16", SYMBOL "unsigned"] → [INT "255:int16 unsigned"]
    This handles the spec's "255:int16 unsigned" syntax where the qualifier is
    separated by whitespace but semantically part of the numeric literal.
    """
    result: list[Token] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.kind in (TokenKind.INT, TokenKind.FLOAT) and ":" in tok.text:
            # This numeric token has a type suffix — absorb trailing qualifiers
            merged_text = tok.text
            merged_span = tok.span
            while (i + 1 < len(tokens)
                   and tokens[i + 1].kind == TokenKind.SYMBOL
                   and tokens[i + 1].text in _QUALIFIER_NAMES):
                i += 1
                merged_text += " " + tokens[i].text
                merged_span = Span(
                    file=merged_span.file, line=merged_span.line, col=merged_span.col,
                    offset=merged_span.offset,
                    length=(tokens[i].span.offset + tokens[i].span.length) - merged_span.offset,
                )
            result.append(Token(tok.kind, merged_text, merged_span))
        else:
            result.append(tok)
        i += 1
    return result


def _is_token_char(ch: str) -> bool:
    """Characters that can appear in a symbol/number/keyword token."""
    return ch not in " \t\r\n()[]\";"


def _is_numeric(text: str) -> bool:
    """Check if text looks like a numeric literal (possibly with type suffix)."""
    s = text
    # Strip leading minus
    if s.startswith("-"):
        s = s[1:]
    if not s:
        return False
    # Check for type suffix (after colon)
    if ":" in s:
        num_part = s[:s.index(":")]
    else:
        num_part = s
    if not num_part:
        return False
    # Must start with digit or be .digit
    if num_part[0].isdigit():
        return True
    if num_part.startswith(".") and len(num_part) > 1 and num_part[1].isdigit():
        return True
    return False


def _classify_number(text: str, span: Span) -> TokenKind:
    """Determine if a numeric token is INT or FLOAT."""
    # Extract the numeric part (before any colon suffix)
    s = text
    if s.startswith("-"):
        s = s[1:]
    if ":" in s:
        num_part = s[:s.index(":")]
    else:
        num_part = s
    if "." in num_part:
        # Validate: only one dot
        parts = num_part.split(".")
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            raise LexError(f"invalid numeric literal: {text!r}", span)
        return TokenKind.FLOAT
    else:
        if not num_part.isdigit():
            raise LexError(f"invalid numeric literal: {text!r}", span)
        return TokenKind.INT
